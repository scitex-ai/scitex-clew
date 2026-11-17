#!/usr/bin/env python3
"""External inputs: files a run reads from OUTSIDE its project root.

Real research reads shared datasets, downloads and sibling projects' outputs,
often through an in-project symlink. These tests use a real project tree and a
real sibling directory (pytest ``tmp_path``), the real session hooks
(``on_session_start`` / ``on_session_close``), the real audit hook and a real
PostgreSQL store. No mocks.

``tmp_path`` lives under the temporary directory, which the external policy
excludes by default (temp files are scratch, not data), so the tests that
need a sibling "shared dataset" opt it in through the documented
``SCITEX_CLEW_EXTERNAL_INCLUDE`` knob — exactly what a user does for a data
tree under an excluded prefix (e.g. ``/opt/lab-data``).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import sysconfig
import tempfile
import uuid
import warnings
from pathlib import Path

import pytest
from click.testing import CliRunner

import scitex_clew as clew
from scitex_clew import _capture, _capture_external
from scitex_clew._capture_external import ExternalPolicy
from scitex_clew._claim._verify import verify_all_claims, verify_claim
from scitex_clew._cli._exit_codes import EXTERNAL_MISSING, STALE_LINEAGE
from scitex_clew._db import get_db
from scitex_clew._hash import hash_file
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._tracker import set_tracker

_STDLIB = Path(sysconfig.get_paths()["stdlib"])
_STDLIB_DATA = next(
    (p for p in sorted(_STDLIB.glob("*")) if p.is_file() and p.suffix != ".py"),
    None,
)
_SYSTEM_FILES = [
    pytest.param(
        p,
        marks=pytest.mark.skipif(not os.path.isfile(p), reason=f"no {p} here"),
    )
    for p in ("/etc/hosts", "/proc/self/status")
]

_ENVS = (
    _capture.ENV_VAR,
    _capture_external.ENV_EXTERNAL,
    _capture_external.ENV_EXTERNAL_INCLUDE,
    _capture_external.ENV_EXTERNAL_EXCLUDE,
)


@pytest.fixture(autouse=True)
def _clean_state():
    saved = {k: os.environ.pop(k, None) for k in _ENVS}
    set_tracker(None)
    _capture._ACTIVE = None
    yield
    set_tracker(None)
    _capture._ACTIVE = None
    for key, value in saved.items():
        os.environ.pop(key, None)
        if value is not None:
            os.environ[key] = value


@pytest.fixture
def project(tmp_path):
    """A project tree plus a SIBLING shared-data directory outside it."""
    root = tmp_path / "proj"
    (root / "scripts").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "scripts" / "run.py").write_text("print('entry')\n")
    shared = tmp_path / "shared"
    shared.mkdir()
    (shared / "raw.csv").write_text("a,b\n1,2\n")
    (shared / "labels.txt").write_text("x\ny\n")
    return root


@pytest.fixture
def shared(project):
    """The sibling data tree, opted in (it lives under the temp dir)."""
    path = project.parent / "shared"
    os.environ[_capture_external.ENV_EXTERNAL_INCLUDE] = str(path)
    return path


def _start(project, **extra):
    sid = f"ext_{uuid.uuid4().hex[:12]}"
    meta = {"project_root": str(project), **extra}
    on_session_start(
        sid, script_path=str(project / "scripts" / "run.py"), metadata=meta
    )
    return sid


def _inputs(sid):
    return {
        r["file_path"]: r
        for r in get_db().get_file_records(sid)
        if r["role"] == "input"
    }


def _capture_meta(sid):
    meta = get_db().get_run(sid)["metadata"]
    meta = json.loads(meta) if isinstance(meta, str) else meta
    return meta["capture"]


def _run_and_claim(project, shared):
    """A run reading a shared file, writing a result, and a claim on it."""
    out = project / "results.json"
    sid = _start(project)
    rows = (shared / "raw.csv").read_text().splitlines()
    out.write_text(json.dumps({"n": len(rows)}))
    on_session_close()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        claim = clew.add_claim(
            str(project / "paper.tex"), "value", 1, "2", source_file=str(out)
        )
    return sid, claim


class TestExternalReadsAreRecorded:
    def test_read_from_a_sibling_directory_is_an_external_input(self, project, shared):
        # Arrange
        ext = shared / "raw.csv"
        sid = _start(project)
        # Act
        ext.read_text()
        on_session_close()
        # Assert
        row = _inputs(sid)[str(ext.resolve())]
        assert (row["hash"], row["external"]["via"], row["external"]["size"]) == (
            hash_file(ext),
            None,
            ext.stat().st_size,
        )

    def test_symlink_in_the_project_to_an_outside_file_records_target_and_link(
        self, project, shared
    ):
        # Arrange
        link = project / "data" / "raw.csv"
        link.symlink_to(shared / "raw.csv")
        sid = _start(project)
        # Act
        with open(link) as f:
            f.read()
        on_session_close()
        # Assert
        row = _inputs(sid)[str((shared / "raw.csv").resolve())]
        assert row["external"]["via"] == str(link)

    def test_symlinked_directory_in_the_project_is_followed(self, project, shared):
        # Arrange: data/raw -> /mnt/shared/raw style directory link
        (project / "data" / "raw").symlink_to(shared, target_is_directory=True)
        sid = _start(project)
        # Act
        (project / "data" / "raw" / "labels.txt").read_text()
        on_session_close()
        # Assert
        row = _inputs(sid)[str((shared / "labels.txt").resolve())]
        assert row["external"]["via"] == str(project / "data" / "raw" / "labels.txt")

    def test_external_inputs_are_listed_in_the_capture_metadata(self, project, shared):
        # Arrange
        sid = _start(project)
        # Act
        (shared / "raw.csv").read_text()
        on_session_close()
        # Assert
        assert _capture_meta(sid)["external_inputs"] == [
            str((shared / "raw.csv").resolve())
        ]

    def test_explicit_record_input_outside_the_root_is_external(self, project, shared):
        # Arrange
        sid = _start(project)
        # Act
        clew.record_input(shared / "labels.txt")
        on_session_close()
        # Assert
        assert _inputs(sid)[str((shared / "labels.txt").resolve())]["external"] == {
            "via": None,
            "size": (shared / "labels.txt").stat().st_size,
            "mtime": (shared / "labels.txt").stat().st_mtime,
        }

    def test_in_project_input_is_not_flagged_external(self, project, shared):
        # Arrange
        data = project / "data" / "local.txt"
        data.write_text("local\n")
        sid = _start(project)
        # Act
        data.read_text()
        on_session_close()
        # Assert
        assert _inputs(sid)[str(data.resolve())]["external"] is None

    def test_outside_file_written_then_read_back_is_not_an_input(self, project, shared):
        # Arrange
        scratch = shared / "made_by_this_run.bin"
        sid = _start(project)
        # Act
        scratch.write_bytes(b"intermediate")
        scratch.read_bytes()
        on_session_close()
        # Assert
        assert str(scratch.resolve()) not in _inputs(sid)


class TestPrecision:
    def test_stdlib_and_library_imports_are_not_recorded(self, project, shared):
        # Arrange
        name = "colorsys"
        sys.modules.pop(name, None)
        sid = _start(project)
        # Act
        __import__(name)
        import pytest as _pytest_module  # noqa: F401 - re-import is a no-op

        on_session_close()
        # Assert
        assert [p for p in _inputs(sid) if not p.startswith(str(project))] == []

    def test_package_data_of_an_imported_package_is_not_recorded(self, project, shared):
        # Arrange: a non-.py data file shipped inside an imported package
        package_dir = Path(clew.__file__).resolve().parent
        data = next(
            p
            for p in sorted(package_dir.rglob("*"))
            if p.is_file() and p.suffix not in (".py", ".pyc")
        )
        sid = _start(project)
        # Act
        data.read_bytes()
        on_session_close()
        # Assert
        assert str(data.resolve()) not in _inputs(sid)

    @pytest.mark.skipif(_STDLIB_DATA is None, reason="no non-.py stdlib file")
    def test_stdlib_data_file_is_not_recorded(self, project, shared):
        # Arrange
        sid = _start(project)
        # Act
        _STDLIB_DATA.read_bytes()
        on_session_close()
        # Assert
        assert str(_STDLIB_DATA.resolve()) not in _inputs(sid)

    @pytest.mark.parametrize("system_file", _SYSTEM_FILES)
    def test_system_file_read_is_not_recorded(self, project, shared, system_file):
        # Arrange
        sid = _start(project)
        # Act
        with open(system_file, "rb") as f:
            f.read()
        on_session_close()
        # Assert
        assert os.path.realpath(system_file) not in _inputs(sid)

    def test_temp_dir_is_excluded_by_default(self, project):
        # Arrange: no include knob; a file in a fresh temp dir
        ext = Path(tempfile.mkdtemp()) / "scratch.csv"
        ext.write_text("a\n1\n")
        sid = _start(project)
        # Act
        ext.read_text()
        on_session_close()
        # Assert
        assert str(ext.resolve()) not in _inputs(sid)

    def test_directory_read_is_not_recorded(self, project, shared):
        # Arrange
        sid = _start(project)
        # Act
        fd = os.open(shared, os.O_RDONLY)
        os.close(fd)
        on_session_close()
        # Assert
        assert str(shared.resolve()) not in _inputs(sid)

    def test_exclude_knob_wins_over_include(self, project, shared):
        # Arrange
        os.environ[_capture_external.ENV_EXTERNAL_EXCLUDE] = str(shared)
        sid = _start(project)
        # Act
        (shared / "raw.csv").read_text()
        on_session_close()
        # Assert
        assert _inputs(sid) == {}

    def test_hidden_tool_state_is_excluded_below_the_common_ancestor(self, project):
        # Arrange
        policy = ExternalPolicy(str(project), include=[], exclude=[])
        base = project.parent
        # Act
        decisions = (
            policy._hidden(str(base / ".cache" / "fonts.json")),
            policy._hidden(str(base / "shared" / "raw.csv")),
        )
        # Assert
        assert decisions == (True, False)

    def test_interpreter_prefix_is_excluded(self, project):
        # Arrange
        policy = ExternalPolicy(str(project), include=[], exclude=[])
        # Act
        excluded = policy.builtin_excluded(os.path.realpath(sys.prefix) + "/x.dat")
        # Assert
        assert excluded is True

    def test_external_opt_out_keeps_in_project_capture(self, project, shared):
        # Arrange
        os.environ[_capture_external.ENV_EXTERNAL] = "0"
        local = project / "data" / "local.txt"
        local.write_text("local\n")
        sid = _start(project)
        # Act
        (shared / "raw.csv").read_text()
        local.read_text()
        on_session_close()
        # Assert
        assert (
            sorted(_inputs(sid)),
            _capture_meta(sid)["external"]["enabled"],
        ) == ([str(local.resolve())], False)


class TestSliceRequiresButDoesNotBundle:
    @pytest.mark.parametrize("level", [0, 1, 2])
    def test_slice_lists_external_input_as_required_not_bundled(
        self, project, shared, level
    ):
        # Arrange
        sid, claim = _run_and_claim(project, shared)
        ext = str((shared / "raw.csv").resolve())
        # Act
        manifest = clew.slice(claim.claim_id, level=level).to_dict()
        # Assert
        assert (
            [
                (r["path"], r["hash"], r["runs"])
                for r in manifest["required_not_bundled"]
            ],
            [f["external"] for f in manifest["files"] if f["path"] == ext],
        ) == ([(ext, hash_file(ext), [sid])], [True])

    def test_cli_slice_marks_external_nodes(self, project, shared):
        # Arrange
        from scitex_clew._cli._verification_dag import slice_cmd

        _sid, claim = _run_and_claim(project, shared)
        # Act
        result = CliRunner().invoke(slice_cmd, [claim.claim_id])
        # Assert
        assert (
            result.exit_code,
            "[EXTERNAL: outside the project, not bundled]" in result.output,
            "REQUIRED BUT NOT BUNDLED: 1 external input(s)" in result.output,
        ) == (0, True, True)


class TestVerifyChecksExternalInputs:
    def test_unchanged_external_input_verifies(self, project, shared):
        # Arrange
        _sid, claim = _run_and_claim(project, shared)
        # Act
        result = verify_claim(claim.claim_id)
        # Assert
        assert result["claim"]["status"] == "verified"

    def test_changed_external_input_is_stale_lineage(self, project, shared):
        # Arrange
        _sid, claim = _run_and_claim(project, shared)
        (shared / "raw.csv").write_text("a,b\n9,9\n")
        # Act
        result = verify_all_claims()
        # Assert
        assert result.exit_code == STALE_LINEAGE

    def test_missing_external_input_is_a_distinct_status(self, project, shared):
        # Arrange
        _sid, claim = _run_and_claim(project, shared)
        (shared / "raw.csv").unlink()
        # Act
        result = verify_all_claims()
        detail = verify_claim(claim.claim_id)
        # Assert
        assert (result.exit_code, detail["external_missing"]) == (
            EXTERNAL_MISSING,
            [str((shared / "raw.csv").resolve())],
        )

    def test_missing_external_never_passes_single_run_verify(self, project, shared):
        # Arrange
        from scitex_clew._cli._verification_core import verify

        sid, _claim = _run_and_claim(project, shared)
        (shared / "raw.csv").unlink()
        # Act
        result = CliRunner().invoke(verify, [sid])
        # Assert
        assert (result.exit_code, "EXTERNAL (outside the project" in result.output) == (
            EXTERNAL_MISSING,
            True,
        )


class TestWarnings:
    def test_session_close_warns_about_external_dependencies(
        self, project, shared, caplog
    ):
        # Arrange
        sid = _start(project)
        (shared / "raw.csv").read_text()
        # Act
        with caplog.at_level(logging.WARNING, logger="scitex_clew._tracker"):
            on_session_close()
        # Assert
        assert f"session {sid} depends on 1 file(s) outside the project" in caplog.text

    def test_claim_registration_warns_about_external_dependencies(
        self, project, shared
    ):
        # Arrange
        out = project / "results.json"
        _start(project)
        (shared / "raw.csv").read_text()
        out.write_text("{}")
        on_session_close()
        # Act
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            claim = clew.add_claim(
                str(project / "paper.tex"), "value", 1, "2", source_file=str(out)
            )
        # Assert
        assert any(
            f"claim {claim.claim_id} depends on 1 file(s) outside the project"
            in str(w.message)
            and "the slice cannot bundle them" in str(w.message)
            for w in record
        )

    def test_in_project_only_run_does_not_warn(self, project, shared, caplog):
        # Arrange
        (project / "data" / "local.txt").write_text("x\n")
        _start(project)
        (project / "data" / "local.txt").read_text()
        # Act
        with caplog.at_level(logging.WARNING, logger="scitex_clew._tracker"):
            on_session_close()
        # Assert
        assert "outside the project" not in caplog.text
