"""`clew bundle {keygen,export,verify,rerun}` through the real CLI entry point.

Click's CliRunner invokes the real ``main`` group in process (no mocks). The
bundle here is a real file with real hashes, signed with a real key, written
by hand so these tests need no recorded project (the store-built bundle and a
real re-execution are covered by ``tests/scitex_clew/_exchange/``).
"""

from __future__ import annotations

import json
import stat

import pytest
from click.testing import CliRunner
from scitex_clew._cli._main import main
from scitex_clew._exchange import (
    generate_private_key_file,
    sha256_file,
    sign_document,
    write_bundle,
)


def _invoke(*args):
    return CliRunner().invoke(main, list(args), catch_exceptions=False)


@pytest.fixture
def project(tmp_path):
    """A checkout with one recorded run and its signed bundle (no store)."""
    root = tmp_path / "proj"
    (root / "data").mkdir(parents=True)
    (root / "out").mkdir()
    (root / "data" / "in.csv").write_text("x\n1\n")
    (root / "run.py").write_text("print('hi')\n")
    (root / "out" / "r.json").write_text('{"n": 1}\n')
    doc = {
        "schema": "scitex-clew.evidence-bundle",
        "schema_version": "1.0.0",
        "exported_at": "2026-11-19T00:00:00+00:00",
        "clew_version": "test",
        "project": {"project_id": "clew-test", "root_name": "proj"},
        "runs": [{
            "run_id": "R1", "script": "run.py", "argv": ["run.py"],
            "interpreter": {"name": "python", "version": "3.12"}, "cwd": ".",
            "inputs": {"data/in.csv": sha256_file(root / "data" / "in.csv")},
            "outputs": {"out/r.json": sha256_file(root / "out" / "r.json")},
            "external_inputs": [], "status": "success",
            "started_at": "2026-11-19T00:00:00", "finished_at": "2026-11-19T00:00:01",
        }],
        "edges": [],
        "claims": [],
    }  # fmt: skip
    signer = generate_private_key_file(tmp_path / "k.pem")
    write_bundle(
        sign_document(doc, signer), root / ".scitex" / "clew" / "evidence-bundle.json"
    )
    return root


def _bundle(root):
    return str(root / ".scitex" / "clew" / "evidence-bundle.json")


def test_bundle_group_lists_its_four_verbs():
    # Arrange
    args = ("bundle", "--help")
    # Act
    out = _invoke(*args).output
    # Assert
    assert all(verb in out for verb in ("keygen", "export", "verify", "rerun"))


def test_keygen_writes_a_0600_key_and_prints_its_id(tmp_path):
    # Arrange
    key = tmp_path / "k.pem"
    # Act
    payload = json.loads(
        _invoke("bundle", "keygen", "--out", str(key), "--json").output
    )
    # Assert
    assert (len(payload["key_id"]), stat.S_IMODE(key.stat().st_mode)) == (16, 0o600)


def test_keygen_refuses_to_overwrite(tmp_path):
    # Arrange
    key = tmp_path / "k.pem"
    _invoke("bundle", "keygen", "--out", str(key))
    # Act
    result = _invoke("bundle", "keygen", "--out", str(key))
    # Assert
    assert result.exit_code != 0


def test_keygen_dry_run_writes_nothing(tmp_path):
    # Arrange
    key = tmp_path / "k.pem"
    # Act
    _invoke("bundle", "keygen", "--out", str(key), "--dry-run")
    # Assert
    assert not key.exists()


def test_export_dry_run_writes_nothing(tmp_path):
    # Arrange
    out = tmp_path / "bundle.json"
    # Act
    _invoke(
        "bundle",
        "export",
        "--project-root",
        str(tmp_path),
        "--out",
        str(out),
        "--dry-run",
    )
    # Assert
    assert not out.exists()


def test_export_of_a_project_without_records_is_empty(tmp_path):
    # Arrange
    (tmp_path / ".git").mkdir()
    out = tmp_path / "bundle.json"
    # Act
    payload = json.loads(
        _invoke(
            "bundle",
            "export",
            "--project-root",
            str(tmp_path),
            "--out",
            str(out),
            "--json",
        ).output
    )
    # Assert
    assert (payload["runs"], payload["claims"], payload["signed"]) == (0, 0, False)


def test_verify_exits_zero_on_an_intact_project(project):
    # Arrange
    args = ("bundle", "verify", _bundle(project), "--project-root", str(project))
    # Act
    result = _invoke(*args, "--json")
    # Assert
    assert result.exit_code == 0, result.output


def test_verify_reports_the_signature(project):
    # Arrange
    args = (
        "bundle",
        "verify",
        _bundle(project),
        "--project-root",
        str(project),
        "--json",
    )
    # Act
    payload = json.loads(_invoke(*args).output)
    # Assert
    assert (payload["signed"], payload["signature"]["valid"]) == (True, True)


def test_verify_exits_nonzero_with_json_findings_on_tamper(project):
    # Arrange
    (project / "data" / "in.csv").write_text("tampered\n")
    args = (
        "bundle",
        "verify",
        _bundle(project),
        "--project-root",
        str(project),
        "--json",
    )
    # Act
    result = _invoke(*args)
    # Assert
    assert (result.exit_code, json.loads(result.output)["findings"][0]["code"]) == (
        1,
        "file_mismatch",
    )


def test_rerun_dry_run_lists_the_replay_command(project):
    # Arrange
    args = ("bundle", "rerun", _bundle(project), "--project-root", str(project))
    # Act
    plan = json.loads(_invoke(*args, "--dry-run", "--json").output)["runs"]
    # Assert
    assert plan == [{"run_id": "R1", "cwd": ".", "argv": ["run.py"]}]


# EOF
