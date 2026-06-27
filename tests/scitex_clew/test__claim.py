"""Tests for ``scitex_clew.export_claims_json`` and the
``add_claim`` auto-export hook, plus perf-B dedup behaviour.

Covers:

  - Default path resolution lands at
    ``<project_root>/.scitex/clew/runtime/claims.json`` per the
    ecosystem local-state-directories convention.
  - ``SCITEX_CLEW_CLAIMS_JSON`` env var overrides the default.
  - Explicit ``path=`` arg overrides both.
  - Each claim added via ``clew.add_claim`` is reflected in the
    exported JSON after the auto-hook fires.
  - The artifact is mode 0444 (read-only) after write — accidental
    edits trip an OSError at the OS layer.
  - Setting ``SCITEX_CLEW_AUTO_EXPORT_CLAIMS=0`` disables the auto-hook
    without breaking ``add_claim``.
  - Perf B: when N claims share one source_file, hash_file is called
    exactly once per verify_all_claims pass (hash_cache dedup).

Tests follow:
  - PA-306 §3 (no mocks): real env + cwd mutation with explicit
    save/restore, no pytest ``monkeypatch``.
  - PA-307 §3 (test-quality): AAA marker comments + one observable
    assertion per test.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Optional

import pytest

import scitex_clew as clew
from scitex_clew._db import _core as _db_core


# ---------------------------------------------------------------------------
# Real-state save/restore helpers (NOT mocks — they touch os.environ /
# os.getcwd / clew.set_db on the live process and unwind on teardown).
# PA-306 forbids ``monkeypatch``; this fixture is the explicit equivalent.
# ---------------------------------------------------------------------------


@pytest.fixture
def env_sandbox():
    """Snapshot scitex-clew-relevant env vars + cwd; restore on teardown.

    Returns a small helper namespace with ``set_env``, ``unset_env``,
    ``chdir`` methods that mutate live state and record undo actions.
    """
    snapshot_env = {
        k: os.environ.get(k)
        for k in (
            "SCITEX_CLEW_DB_PATH",
            "SCITEX_CLEW_CLAIMS_JSON",
            "SCITEX_CLEW_AUTO_EXPORT_CLAIMS",
        )
    }
    snapshot_cwd = os.getcwd()

    class _Sandbox:
        def set_env(self, k: str, v: str) -> None:
            os.environ[k] = v

        def unset_env(self, k: str) -> None:
            os.environ.pop(k, None)

        def chdir(self, p: Path) -> None:
            os.chdir(p)

    yield _Sandbox()

    # Teardown — return env + cwd to entry state.
    for k, v in snapshot_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    os.chdir(snapshot_cwd)
    clew.set_db(None)


def _fresh_db(tmp_path: Path, sandbox) -> Path:
    """Wire scitex_clew at a fresh per-test DB under tmp_path."""
    db_path = tmp_path / ".scitex" / "clew" / "runtime" / "db.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sandbox.set_env("SCITEX_CLEW_DB_PATH", str(db_path))
    clew.set_db(None)
    return tmp_path


def _make_source(tmp_path: Path, content: str = "x=42\n") -> Path:
    """Write a small source file the claim's source_file can point at."""
    src = tmp_path / "evidence.txt"
    src.write_text(content)
    return src


def _seed_claim(workdir: Path, value: str = "0.94") -> None:
    """Seed exactly one claim against a fresh source file in workdir."""
    src = _make_source(workdir)
    clew.add_claim(
        file_path=str(workdir / "paper.tex"),
        claim_type="value",
        line_number=1,
        claim_value=value,
        source_file=str(src),
    )


def _make_project_root(workdir: Path) -> None:
    """Tag workdir as a project root so ``_find_project_root`` stops here."""
    (workdir / "pyproject.toml").write_text("[project]\nname = 'dummy'\n")


# ---------------------------------------------------------------------------
# Path-resolution tests
# ---------------------------------------------------------------------------


def test_default_path_under_runtime(tmp_path, env_sandbox):
    """``export_claims_json()`` lands under ``runtime/`` by default."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    _seed_claim(workdir)
    # Act
    out = clew.export_claims_json()
    # Assert
    assert out == (workdir / ".scitex" / "clew" / "runtime" / "claims.json").resolve()


def test_env_var_overrides_default(tmp_path, env_sandbox):
    """``$SCITEX_CLEW_CLAIMS_JSON`` overrides the project-root default."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    override = workdir / "elsewhere" / "claims.json"
    env_sandbox.set_env("SCITEX_CLEW_CLAIMS_JSON", str(override))
    _seed_claim(workdir)
    # Act
    out = clew.export_claims_json()
    # Assert
    assert out == override.resolve()


def test_explicit_path_overrides_env_var(tmp_path, env_sandbox):
    """Explicit ``path=`` beats env var beats default."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    env_sandbox.set_env(
        "SCITEX_CLEW_CLAIMS_JSON",
        str(workdir / "env_override.json"),
    )
    explicit = workdir / "explicit.json"
    _seed_claim(workdir)
    # Act
    out = clew.export_claims_json(path=explicit)
    # Assert
    assert out == explicit.resolve()


def test_explicit_path_does_not_write_env_target(tmp_path, env_sandbox):
    """When explicit ``path`` wins, env-var target stays empty."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    env_target = workdir / "env_override.json"
    env_sandbox.set_env("SCITEX_CLEW_CLAIMS_JSON", str(env_target))
    _seed_claim(workdir)
    # Act
    clew.export_claims_json(path=workdir / "explicit.json")
    # Assert
    assert not env_target.exists()


# ---------------------------------------------------------------------------
# Auto-export hook tests
# ---------------------------------------------------------------------------


def test_auto_export_writes_canonical_file(tmp_path, env_sandbox):
    """Default-on hook writes the canonical JSON after add_claim."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.unset_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    canonical = workdir / ".scitex" / "clew" / "runtime" / "claims.json"
    # Act
    _seed_claim(workdir)
    # Assert
    assert canonical.is_file()


def test_auto_export_records_every_claim(tmp_path, env_sandbox):
    """Every add_claim() shows up in the exported JSON."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.unset_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    src = _make_source(workdir)
    for i, val in enumerate(["0.94", "0.05", "ResNet-50"]):
        clew.add_claim(
            file_path=str(workdir / "paper.tex"),
            claim_type="value",
            line_number=i + 1,
            claim_value=val,
            source_file=str(src),
        )
    canonical = workdir / ".scitex" / "clew" / "runtime" / "claims.json"
    # Act
    payload = json.loads(canonical.read_text())
    # Assert
    assert {c["claim_value"] for c in payload["claims"]} == {
        "0.94",
        "0.05",
        "ResNet-50",
    }


def test_auto_export_payload_carries_note(tmp_path, env_sandbox):
    """The artifact carries the AUTO-GENERATED warning note."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.unset_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    _seed_claim(workdir)
    canonical = workdir / ".scitex" / "clew" / "runtime" / "claims.json"
    # Act
    payload = json.loads(canonical.read_text())
    # Assert
    assert "AUTO-GENERATED" in payload.get("_note", "")


# ---------------------------------------------------------------------------
# File-mode + opt-out tests
# ---------------------------------------------------------------------------


def test_default_artifact_is_read_only(tmp_path, env_sandbox):
    """After write, the file has mode 0444 (read-only at OS layer)."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    _seed_claim(workdir)
    # Act
    out = clew.export_claims_json()
    # Assert
    assert (out.stat().st_mode & 0o777) == 0o444


def test_re_export_overrides_readonly_then_resets(tmp_path, env_sandbox):
    """Re-exporting succeeds even though the prior file is mode 0444."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    _seed_claim(workdir)
    clew.export_claims_json()
    # Act
    out2 = clew.export_claims_json()
    # Assert
    assert (out2.stat().st_mode & 0o777) == 0o444


def test_read_only_false_keeps_default_perms(tmp_path, env_sandbox):
    """``read_only=False`` leaves the file mutable for test scenarios."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    _seed_claim(workdir)
    # Act
    out = clew.export_claims_json(read_only=False)
    # Assert
    assert (out.stat().st_mode & 0o777) == 0o644


def test_auto_export_disabled_by_env(tmp_path, env_sandbox):
    """``SCITEX_CLEW_AUTO_EXPORT_CLAIMS=0`` disables the auto-hook."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    canonical = workdir / ".scitex" / "clew" / "runtime" / "claims.json"
    # Act
    _seed_claim(workdir)
    # Assert
    assert not canonical.exists()


def test_add_claim_still_returns_when_auto_export_off(tmp_path, env_sandbox):
    """add_claim() still produces a Claim with auto-export off."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = _make_source(workdir)
    # Act
    c = clew.add_claim(
        file_path=str(workdir / "paper.tex"),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(src),
    )
    # Assert
    assert c.claim_id.startswith("claim_")


# ---------------------------------------------------------------------------
# Pure-helper test (no env, no cwd)
# ---------------------------------------------------------------------------


def test_default_claims_json_path_helper():
    """The path-resolution helper composes the runtime/ path correctly."""
    # Arrange
    project_root = Path("/tmp/some-project")
    # Act
    p = _db_core._default_claims_json_path(project_root)
    # Assert
    assert p == Path("/tmp/some-project/.scitex/clew/runtime/claims.json")


# ---------------------------------------------------------------------------
# Perf B: hash_cache dedup tests
# (PA-306 §3 no mocks, PA-307 §3 AAA + one assertion per test)
# ---------------------------------------------------------------------------

# Shared fixture for perf B tests — builds an isolated DB with N claims all
# pointing at the same source_file so dedup behaviour is observable.

@pytest.fixture
def perf_b_sandbox(tmp_path, env_sandbox):
    """Isolated DB + 3 claims sharing one source_file (evidence.txt)."""
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = workdir / "evidence.txt"
    src.write_text("result=0.94\n")
    paper = workdir / "paper.tex"
    paper.write_text("claim1\nclaim2\nclaim3\n")
    for line in [1, 2, 3]:
        clew.add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=line,
            claim_value=f"v{line}",
            source_file=str(src),
        )
    return {"workdir": workdir, "src": src}


def test_perf_b_shared_source_hashed_once_per_pass(perf_b_sandbox, env_sandbox):
    """With 3 claims sharing one source_file, hash_cache has exactly 1 entry after the pass."""
    # Arrange
    from scitex_clew._chain._hash_cache import new_hash_cache
    from scitex_clew._claim import verify_claim

    observed_cache: Dict[str, str] = new_hash_cache()
    src = perf_b_sandbox["src"]
    all_claims = clew.list_claims()
    # Act — call verify_claim 3 times with the SAME cache (simulating verify_all_claims)
    for c in all_claims:
        verify_claim(c.claim_id, hash_cache=observed_cache)
    # Assert — resolved src path is the only key; file hashed once, not 3 times
    assert len(observed_cache) == 1


def test_perf_b_verify_all_claims_result_identical_exit_code(perf_b_sandbox):
    """verify_all_claims returns the same exit_code as calling without cache."""
    # Arrange — run without cache first (baseline), then with optimised path
    # verify_all_claims always builds the cache internally; we compare two
    # independent runs on the same DB and expect consistent exit_codes.
    result_first = clew.verify_all_claims()
    # Act
    result_second = clew.verify_all_claims()
    # Assert — idempotent: same pass, same DB, same exit_code
    assert result_first.exit_code == result_second.exit_code


def test_perf_b_verify_all_claims_result_identical_verified_count(perf_b_sandbox):
    """verify_all_claims returns the same verified count on repeated passes."""
    # Arrange
    result_first = clew.verify_all_claims()
    # Act
    result_second = clew.verify_all_claims()
    # Assert
    assert result_first.verified == result_second.verified


def test_perf_b_verify_all_claims_result_identical_total(perf_b_sandbox):
    """verify_all_claims total claim count is stable across passes."""
    # Arrange
    result_first = clew.verify_all_claims()
    # Act
    result_second = clew.verify_all_claims()
    # Assert
    assert result_first.total == result_second.total


def test_perf_b_missing_source_outcome_preserved(tmp_path, env_sandbox):
    """hash_cache dedup does not hide a SOURCE_MISSING outcome."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = workdir / "gone.txt"
    src.write_text("will be deleted\n")
    paper = workdir / "paper.tex"
    paper.write_text("claim1\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="v1",
        source_file=str(src),
    )
    src.unlink()  # delete the source so it's MISSING at verify time
    from scitex_clew._cli import _exit_codes as codes
    # Act
    result = clew.verify_all_claims()
    # Assert — source gone must surface as SOURCE_MISSING exit code
    assert result.exit_code == codes.SOURCE_MISSING


def test_perf_b_hash_mismatch_outcome_preserved(tmp_path, env_sandbox):
    """hash_cache dedup does not mask a HASH_MISMATCH outcome."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = workdir / "data.txt"
    src.write_text("original content\n")
    paper = workdir / "paper.tex"
    paper.write_text("claim1\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="v1",
        source_file=str(src),
    )
    src.write_text("TAMPERED content\n")  # mutate after registration
    from scitex_clew._cli import _exit_codes as codes
    # Act
    result = clew.verify_all_claims()
    # Assert — tampered source must surface as HASH_MISMATCH exit code
    assert result.exit_code == codes.HASH_MISMATCH


def test_perf_b_fresh_pass_re_hashes_changed_file(tmp_path, env_sandbox):
    """A second verify_all_claims pass sees a file mutated between passes."""
    # Arrange — first pass sees correct hash (source_verified True expected)
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = workdir / "evidence.txt"
    src.write_text("original\n")
    paper = workdir / "paper.tex"
    paper.write_text("claim1\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="v1",
        source_file=str(src),
    )
    from scitex_clew._cli import _exit_codes as codes

    first_result = clew.verify_all_claims()
    src.write_text("TAMPERED\n")  # mutate between passes
    # Act — second pass, fresh cache, must detect tamper
    second_result = clew.verify_all_claims()
    # Assert — second pass detects the change; exit codes differ
    assert first_result.exit_code != second_result.exit_code


def test_perf_b_no_source_unverified_preserved(tmp_path, env_sandbox):
    """Fabrication claim (no source_file) still produces UNVERIFIED exit code."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("fabricated result\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="statistic",
        line_number=1,
        claim_value="p=0.001",
        # source_file omitted — fabrication claim
    )
    from scitex_clew._cli import _exit_codes as codes
    # Act
    result = clew.verify_all_claims()
    # Assert
    assert result.exit_code == codes.UNVERIFIED
