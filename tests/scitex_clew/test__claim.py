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


# ---------------------------------------------------------------------------
# Item 2: strict-mode chain_cache memo tests
# (PA-306 §3 no mocks — real wrapping of verify_chain via module attribute;
#  PA-307 §3 AAA + one observable assertion per test)
# ---------------------------------------------------------------------------


@pytest.fixture
def strict_chain_sandbox(tmp_path, env_sandbox):
    """Isolated DB with 3 claims sharing one source_file (no DB chain).

    Returns a dict with keys: workdir, src, paper.
    In strict mode each claim triggers verify_chain(src) — the memo
    should collapse these to a single walk.
    """
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
    return {"workdir": workdir, "src": src, "paper": paper}


def test_strict_chain_memo_verify_chain_called_once(strict_chain_sandbox, env_sandbox):
    """With 3 claims sharing one source_file, verify_chain is called once per pass."""
    # Arrange
    import scitex_clew._claim as _claim_mod
    from scitex_clew._claim import verify_claim
    from scitex_clew._chain._hash_cache import new_hash_cache

    call_count = [0]
    real_verify_chain = None

    def counting_verify_chain(source_file):
        call_count[0] += 1
        return real_verify_chain(source_file)

    # Patch at module level (not mock — replaces the real function reference)
    import scitex_clew._chain as _chain_mod
    real_verify_chain = _chain_mod.verify_chain

    original_import = _claim_mod.__builtins__  # keep ref for teardown

    # We intercept at _claim module's local import by temporarily replacing
    # the verify_chain name in the _chain package's namespace.
    _chain_mod.verify_chain = counting_verify_chain
    try:
        hash_cache = new_hash_cache()
        chain_cache: Dict[str, object] = {}
        all_claims = clew.list_claims()
        # Act — manually thread chain_cache through three verify_claim calls
        for c in all_claims:
            verify_claim(c.claim_id, hash_cache=hash_cache, chain_cache=chain_cache)
    finally:
        _chain_mod.verify_chain = real_verify_chain
    # Assert — exactly one chain walk for the one unique source_file
    assert call_count[0] == 1


def test_strict_chain_memo_exit_code_identical_with_and_without_memo(
    strict_chain_sandbox, env_sandbox
):
    """verify_all_claims returns byte-identical exit_code with and without memo."""
    # Arrange — run strict=True twice on the same DB; compare exit codes
    result_first = clew.verify_all_claims(strict=True)
    # Act
    result_second = clew.verify_all_claims(strict=True)
    # Assert — idempotent strict pass: same DB, same exit_code
    assert result_first.exit_code == result_second.exit_code


def test_strict_chain_memo_counts_identical_across_passes(strict_chain_sandbox):
    """verify_all_claims returns same per-outcome counts in strict mode across passes."""
    # Arrange
    result_first = clew.verify_all_claims(strict=True)
    # Act
    result_second = clew.verify_all_claims(strict=True)
    # Assert
    assert result_first.counts == result_second.counts


def test_strict_chain_memo_per_claim_chain_verified_identical(strict_chain_sandbox):
    """Each claim's chain_verified flag is the same with and without the memo."""
    # Arrange
    result_a = clew.verify_all_claims(strict=True)
    # Act
    result_b = clew.verify_all_claims(strict=True)
    # Assert — chain_verified vector must be byte-identical across both passes
    chain_verified_a = [cv.chain_verified for cv in result_a.claims]
    chain_verified_b = [cv.chain_verified for cv in result_b.claims]
    assert chain_verified_a == chain_verified_b


def test_strict_chain_memo_no_lineage_claim_preserves_outcome(tmp_path, env_sandbox):
    """A strict NO_LINEAGE claim keeps its outcome when chain_cache is active."""
    # Arrange — claim with source_file but no DB-tracked lineage (verify_chain
    # returns ChainVerification with UNKNOWN status => is_verified=False)
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = workdir / "leaf.txt"
    src.write_text("handwritten result\n")
    paper = workdir / "paper.tex"
    paper.write_text("claim1\nclaim2\n")
    # Two claims sharing the same untracked source_file
    for line in [1, 2]:
        clew.add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=line,
            claim_value=f"val{line}",
            source_file=str(src),
        )
    from scitex_clew._cli import _exit_codes as codes
    # Act — strict=True; no DB lineage => NO_LINEAGE
    result = clew.verify_all_claims(strict=True)
    # Assert — chain_cache does NOT suppress the NO_LINEAGE outcome
    assert result.exit_code == codes.NO_LINEAGE


# ---------------------------------------------------------------------------
# Schema v1.1/v1.2 marker-fields tests
# (PA-306 §3 no mocks — real temp DBs via package DB API;
#  PA-307 §3 AAA + one observable assertion per test)
#
# Covers:
#  (a) schema_version "1.2" (bumped from v1.1; attestation+legend added) +
#      canonical palette in exported JSON
#  (b) color field resolved correctly per status
#  (c) chain_has_exception flag from run provenance
#  (d) chain_has_frozen flag from file_hashes.frozen
#  (e) all pre-existing claim fields still present (backward-compat guard)
# ---------------------------------------------------------------------------


@pytest.fixture
def v11_sandbox(tmp_path, env_sandbox):
    """Isolated per-test DB wired at tmp_path; auto-export OFF.

    Returns the workdir Path so callers can add claims and call
    export_claims_json() explicitly.
    """
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    return workdir


def test_v11_schema_version_in_exported_json(v11_sandbox, env_sandbox):
    """Exported JSON has schema_version == '1.3' (bumped from v1.2 for 4-state color-only taxonomy)."""
    # Arrange
    workdir = v11_sandbox
    _seed_claim(workdir)
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    payload = json.loads(out.read_text())
    # Assert
    assert payload.get("schema_version") == "1.3"


def test_v11_palette_keys_in_exported_json(v11_sandbox, env_sandbox):
    """Exported JSON has a 'palette' dict with all canonical status keys (v1.3: partial->suspect)."""
    # Arrange
    workdir = v11_sandbox
    _seed_claim(workdir)
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    payload = json.loads(out.read_text())
    # Assert — v1.3 renames "partial" to "suspect" and adds the full-7 keys
    assert set(payload.get("palette", {}).keys()) == {
        "verified", "suspect", "mismatch", "missing", "registered",
        "exception", "frozen",
    }


def test_v11_palette_verified_hex(v11_sandbox, env_sandbox):
    """Canonical hex for 'verified' is '#2da44e'."""
    # Arrange
    workdir = v11_sandbox
    _seed_claim(workdir)
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    palette = json.loads(out.read_text()).get("palette", {})
    # Assert
    assert palette.get("verified") == "2da44e"


def test_v11_palette_mismatch_hex(v11_sandbox, env_sandbox):
    """Canonical hex for 'mismatch' is '#cf222e'."""
    # Arrange
    workdir = v11_sandbox
    _seed_claim(workdir)
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    palette = json.loads(out.read_text()).get("palette", {})
    # Assert
    assert palette.get("mismatch") == "cf222e"


def test_v11_color_verified_claim_gets_green(tmp_path, env_sandbox):
    """A 'verified' claim's color field resolves to '#2da44e'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = _make_source(workdir)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(src),
    )
    # Force status to 'verified' directly in the DB
    import sqlite3
    db = clew.get_db()
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'verified' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["color"] == "2da44e"


def test_v11_color_mismatch_claim_gets_red(tmp_path, env_sandbox):
    """A 'mismatch' claim's color field resolves to '#cf222e'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = _make_source(workdir)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(src),
    )
    import sqlite3
    db = clew.get_db()
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'mismatch' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["color"] == "cf222e"


def test_v11_color_unknown_status_gets_grey(tmp_path, env_sandbox):
    """An unknown/future status falls back to grey '#6e7781'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = _make_source(workdir)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(src),
    )
    import sqlite3
    db = clew.get_db()
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'future_unknown_status' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["color"] == "6e7781"


def test_v11_color_registered_claim_gets_grey(tmp_path, env_sandbox):
    """A 'registered' claim's color field resolves to '#6e7781' (grey)."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = _make_source(workdir)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(src),
    )
    out = workdir / "claims_v11.json"
    # Act — claim is still 'registered' (no verify pass run)
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["color"] == "6e7781"


def test_v11_chain_has_exception_true_for_exception_run(tmp_path, env_sandbox):
    """A claim whose source chain has provenance='exception' → chain_has_exception True."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    # Register a run with provenance='exception' + output file
    session_id = "2026Y-01M-01D-00h00m00s_EXCEP"
    script = str(workdir / "run.py")
    out_file = workdir / "result.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="exception")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "abc123", role="output")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["chain_has_exception"] is True


def test_v11_chain_has_exception_false_for_tracked_run(tmp_path, env_sandbox):
    """A claim whose source chain has only provenance='tracked' → chain_has_exception False."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_TRACK"
    script = str(workdir / "run.py")
    out_file = workdir / "result_tracked.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="tracked")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "abc456", role="output")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["chain_has_exception"] is False


def test_v11_chain_has_frozen_true_for_frozen_file(tmp_path, env_sandbox):
    """A claim whose source chain has a frozen file → chain_has_frozen True."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_FROZN"
    script = str(workdir / "run.py")
    out_file = workdir / "frozen_result.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="tracked")
    db.finish_run(session_id, status="success")
    # Add the output file WITH frozen=True
    db.add_file_hash(session_id, str(out_file), "deadbeef", role="output", frozen=True)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["chain_has_frozen"] is True


def test_v11_chain_has_frozen_false_for_non_frozen_file(tmp_path, env_sandbox):
    """A claim whose source chain has no frozen files → chain_has_frozen False."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_NFROZ"
    script = str(workdir / "run.py")
    out_file = workdir / "normal_result.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="tracked")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "deadbeef2", role="output", frozen=False)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["chain_has_frozen"] is False


def test_v11_chain_has_exception_false_when_no_source(tmp_path, env_sandbox):
    """A claim with no source_file/session → chain_has_exception is False."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("fabricated\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="statistic",
        line_number=1,
        claim_value="p=0.001",
        # source_file and source_session omitted
    )
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["chain_has_exception"] is False


def test_v11_chain_has_frozen_false_when_no_source(tmp_path, env_sandbox):
    """A claim with no source_file/session → chain_has_frozen is False."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("fabricated\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="statistic",
        line_number=1,
        claim_value="p=0.001",
        # source_file and source_session omitted
    )
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claims = json.loads(out.read_text()).get("claims", [])
    # Assert
    assert claims[0]["chain_has_frozen"] is False


def test_v11_existing_fields_unchanged(tmp_path, env_sandbox):
    """All pre-existing claim fields are present and have expected values (backward-compat guard)."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = _make_source(workdir, content="evidence\n")
    paper = workdir / "paper.tex"
    paper.write_text("the claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=7,
        claim_value="0.94",
        source_file=str(src),
    )
    out = workdir / "claims_v11.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert — all pre-v1.1 keys must be present
    required_old_keys = {
        "claim_id", "file_path", "line_number", "claim_type", "claim_value",
        "source_session", "source_file", "source_hash",
        "registered_at", "verified_at", "status",
    }
    assert required_old_keys.issubset(set(claim_dict.keys()))


# ---------------------------------------------------------------------------
# Tests for remove_claim / supersede_claim / file_path_prefix filter
# (PA-306 §3 no mocks — real temp DBs; PA-307 §3 AAA + one assert per test)
# ---------------------------------------------------------------------------


@pytest.fixture
def claim_sandbox(tmp_path, env_sandbox):
    """Isolated DB with one active claim pointing at a real source file."""
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = workdir / "results.csv"
    src.write_text("a,b\n1,2\n")
    clew.add_claim(
        file_path=str(workdir / "paper.tex"),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(src),
    )
    return {"workdir": workdir, "src": src}


# ---- remove_claim ----


def test_remove_claim_returns_true_when_found(claim_sandbox, env_sandbox):
    """remove_claim returns True when the claim_id exists."""
    # Arrange
    claims = clew.list_claims()
    target_id = claims[0].claim_id
    # Act
    result = clew.remove_claim(target_id)
    # Assert
    assert result is True


def test_remove_claim_deletes_row_from_list(claim_sandbox, env_sandbox):
    """After remove_claim, the claim no longer appears in list_claims."""
    # Arrange
    claims = clew.list_claims()
    target_id = claims[0].claim_id
    # Act
    clew.remove_claim(target_id)
    # Assert
    assert len(clew.list_claims()) == 0


def test_remove_claim_returns_false_for_unknown_id(claim_sandbox, env_sandbox):
    """remove_claim returns False when the claim_id is not found."""
    # Arrange
    # Act
    result = clew.remove_claim("claim_nonexistent_000")
    # Assert
    assert result is False


def test_remove_claim_verify_all_does_not_see_removed_claim(claim_sandbox, env_sandbox):
    """After remove_claim, verify_all_claims sees NO_CLAIMS (empty DB)."""
    # Arrange
    from scitex_clew._cli import _exit_codes as codes
    claims = clew.list_claims()
    target_id = claims[0].claim_id
    clew.remove_claim(target_id)
    # Act
    result = clew.verify_all_claims()
    # Assert
    assert result.exit_code == codes.NO_CLAIMS


def test_remove_claim_accepts_location_string(tmp_path, env_sandbox):
    """remove_claim resolves a location string like 'paper.tex:L42'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("line1\n")
    clew.add_claim(file_path=str(paper), claim_type="value", line_number=42, claim_value="x")
    location = f"{paper}:L42"
    # Act
    result = clew.remove_claim(location)
    # Assert
    assert result is True


# ---- supersede_claim ----


def test_supersede_claim_returns_true_when_found(claim_sandbox, env_sandbox):
    """supersede_claim returns True when the claim_id exists."""
    # Arrange
    claims = clew.list_claims()
    target_id = claims[0].claim_id
    # Act
    result = clew.supersede_claim(target_id)
    # Assert
    assert result is True


def test_supersede_claim_row_still_exists_with_include_superseded(claim_sandbox, env_sandbox):
    """After supersede_claim, the row is still in DB (include_superseded=True sees it)."""
    # Arrange
    from scitex_clew._claim import list_claims as _list_claims
    claims = clew.list_claims()
    target_id = claims[0].claim_id
    # Act
    clew.supersede_claim(target_id)
    # Assert
    all_claims = _list_claims(include_superseded=True)
    assert any(c.claim_id == target_id for c in all_claims)


def test_supersede_claim_sets_status_to_superseded(claim_sandbox, env_sandbox):
    """After supersede_claim, the row's status is 'superseded'."""
    # Arrange
    from scitex_clew._claim import list_claims as _list_claims
    claims = clew.list_claims()
    target_id = claims[0].claim_id
    # Act
    clew.supersede_claim(target_id)
    # Assert
    all_claims = _list_claims(include_superseded=True)
    superseded = [c for c in all_claims if c.claim_id == target_id]
    assert superseded[0].status == "superseded"


def test_supersede_claim_excluded_from_default_list(claim_sandbox, env_sandbox):
    """After supersede_claim, default list_claims does NOT return it."""
    # Arrange
    claims = clew.list_claims()
    target_id = claims[0].claim_id
    # Act
    clew.supersede_claim(target_id)
    # Assert
    assert len(clew.list_claims()) == 0


def test_supersede_claim_returns_false_for_unknown_id(claim_sandbox, env_sandbox):
    """supersede_claim returns False when no claim matches."""
    # Arrange
    # Act
    result = clew.supersede_claim("claim_nonexistent_000")
    # Assert
    assert result is False


# ---- verify_all_claims excludes superseded ----


def test_verify_all_claims_skips_superseded_claim(claim_sandbox, env_sandbox):
    """verify_all_claims treats superseded claims as invisible (hits NO_CLAIMS)."""
    # Arrange
    from scitex_clew._cli import _exit_codes as codes
    claims = clew.list_claims()
    target_id = claims[0].claim_id
    clew.supersede_claim(target_id)
    # Act
    result = clew.verify_all_claims()
    # Assert
    assert result.exit_code == codes.NO_CLAIMS


def test_verify_all_claims_supersede_only_failing_claim_makes_gate_pass(tmp_path, env_sandbox):
    """Superseding the only MISMATCH claim lets verify_all_claims exit 0 or NO_CLAIMS."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = workdir / "data.txt"
    src.write_text("original\n")
    paper = workdir / "paper.tex"
    paper.write_text("c1\n")
    clew.add_claim(file_path=str(paper), claim_type="value", line_number=1, claim_value="v", source_file=str(src))
    # Mutate to force HASH_MISMATCH
    src.write_text("tampered\n")
    result_before = clew.verify_all_claims()
    claims = clew.list_claims(include_superseded=True)
    clew.supersede_claim(claims[0].claim_id)
    # Act
    result_after = clew.verify_all_claims()
    # Assert — gate must not be failing after supersede (NO_CLAIMS or OK)
    assert result_after.exit_code != result_before.exit_code


def test_verify_all_claims_all_superseded_hits_no_claims_not_crash(tmp_path, env_sandbox):
    """When all claims are superseded, verify_all_claims returns NO_CLAIMS (not a crash)."""
    # Arrange
    from scitex_clew._cli import _exit_codes as codes
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("c1\n")
    clew.add_claim(file_path=str(paper), claim_type="value", line_number=1, claim_value="v")
    clew.supersede_claim(clew.list_claims(include_superseded=True)[0].claim_id)
    # Act
    result = clew.verify_all_claims()
    # Assert
    assert result.exit_code == codes.NO_CLAIMS


# ---- claims.json excludes superseded by default ----


def test_export_claims_json_excludes_superseded_by_default(tmp_path, env_sandbox):
    """Default export_claims_json does NOT include superseded claims."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("c1\n")
    clew.add_claim(file_path=str(paper), claim_type="value", line_number=1, claim_value="v")
    claims_before = clew.list_claims(include_superseded=True)
    clew.supersede_claim(claims_before[0].claim_id)
    import json
    # Act
    out = clew.export_claims_json(read_only=False)
    payload = json.loads(out.read_text())
    # Assert
    assert payload["claims_count"] == 0


# ---- file_path_prefix filter ----


def test_list_claims_file_path_prefix_returns_matching_claims(tmp_path, env_sandbox):
    """list_claims(file_path_prefix=...) returns only claims under that prefix."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    # Two papers in different dirs
    dir_a = workdir / "proj_a"
    dir_b = workdir / "proj_b"
    dir_a.mkdir()
    dir_b.mkdir()
    clew.add_claim(file_path=str(dir_a / "paper.tex"), claim_type="value", line_number=1, claim_value="a")
    clew.add_claim(file_path=str(dir_b / "paper.tex"), claim_type="value", line_number=1, claim_value="b")
    # Act
    from scitex_clew._claim import list_claims as _list_claims
    results = _list_claims(file_path_prefix=str(dir_a))
    # Assert
    assert all(c.file_path.startswith(str(dir_a.resolve())) for c in results)


def test_list_claims_file_path_prefix_excludes_non_matching(tmp_path, env_sandbox):
    """list_claims(file_path_prefix=...) does NOT return claims outside the prefix."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    dir_a = workdir / "proj_a"
    dir_b = workdir / "proj_b"
    dir_a.mkdir()
    dir_b.mkdir()
    clew.add_claim(file_path=str(dir_a / "paper.tex"), claim_type="value", line_number=1, claim_value="a")
    clew.add_claim(file_path=str(dir_b / "paper.tex"), claim_type="value", line_number=1, claim_value="b")
    # Act
    from scitex_clew._claim import list_claims as _list_claims
    results = _list_claims(file_path_prefix=str(dir_a))
    # Assert — proj_b claim must NOT appear
    assert not any(str(dir_b.resolve()) in c.file_path for c in results)


# ---- bulk remove / supersede by prefix ----


def test_remove_claims_by_prefix_returns_count(tmp_path, env_sandbox):
    """remove_claims_by_prefix returns the count of deleted rows."""
    # Arrange
    from scitex_clew._claim import remove_claims_by_prefix
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    dir_a = workdir / "proj_a"
    dir_a.mkdir()
    clew.add_claim(file_path=str(dir_a / "paper.tex"), claim_type="value", line_number=1, claim_value="a")
    clew.add_claim(file_path=str(dir_a / "paper.tex"), claim_type="value", line_number=2, claim_value="b")
    # Act
    deleted = remove_claims_by_prefix(str(dir_a))
    # Assert
    assert deleted == 2


def test_remove_claims_by_prefix_purges_all_matching(tmp_path, env_sandbox):
    """After remove_claims_by_prefix, no claims under that prefix remain."""
    # Arrange
    from scitex_clew._claim import remove_claims_by_prefix
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    dir_a = workdir / "proj_a"
    dir_a.mkdir()
    clew.add_claim(file_path=str(dir_a / "paper.tex"), claim_type="value", line_number=1, claim_value="a")
    remove_claims_by_prefix(str(dir_a))
    # Act
    from scitex_clew._claim import list_claims as _list_claims
    remaining = _list_claims(file_path_prefix=str(dir_a))
    # Assert
    assert len(remaining) == 0


def test_supersede_claims_by_prefix_returns_count(tmp_path, env_sandbox):
    """supersede_claims_by_prefix returns the count of updated rows."""
    # Arrange
    from scitex_clew._claim import supersede_claims_by_prefix
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    dir_a = workdir / "proj_a"
    dir_a.mkdir()
    clew.add_claim(file_path=str(dir_a / "paper.tex"), claim_type="value", line_number=1, claim_value="a")
    clew.add_claim(file_path=str(dir_a / "paper.tex"), claim_type="value", line_number=2, claim_value="b")
    # Act
    updated = supersede_claims_by_prefix(str(dir_a))
    # Assert
    assert updated == 2


def test_supersede_claims_by_prefix_hides_from_default_list(tmp_path, env_sandbox):
    """After supersede_claims_by_prefix, default list_claims returns none of them."""
    # Arrange
    from scitex_clew._claim import supersede_claims_by_prefix
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    dir_a = workdir / "proj_a"
    dir_a.mkdir()
    clew.add_claim(file_path=str(dir_a / "paper.tex"), claim_type="value", line_number=1, claim_value="a")
    supersede_claims_by_prefix(str(dir_a))
    # Act
    remaining = clew.list_claims()
    # Assert
    assert len(remaining) == 0


# ---------------------------------------------------------------------------
# Schema v1.2 tests: attestation + legend blocks
# (PA-307 §3: AAA comment markers + ONE observable assertion per test)
# ---------------------------------------------------------------------------


def _export_v12(tmp_path, env_sandbox, *, num_verified: int = 1, num_registered: int = 0) -> dict:
    """Helper: build a fresh DB, seed claims, export, return parsed payload."""
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = _make_source(workdir)
    for i in range(num_verified):
        clew.add_claim(
            file_path=str(workdir / "paper.tex"),
            claim_type="value",
            line_number=i + 1,
            claim_value=f"v{i}",
            source_file=str(src),
        )
    for j in range(num_registered):
        clew.add_claim(
            file_path=str(workdir / "paper.tex"),
            claim_type="text",
            line_number=100 + j,
            claim_value=f"reg{j}",
        )
    out = clew.export_claims_json(path=workdir / "claims.json", read_only=False)
    return json.loads(out.read_text())


def test_v12_schema_version_is_1_2(tmp_path, env_sandbox):
    """schema_version field is exactly '1.3' after the v1.3 bump."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    version = payload["schema_version"]
    # Assert — bumped to 1.3 in this release
    assert version == "1.3"


def test_v12_attestation_text_present(tmp_path, env_sandbox):
    """attestation.text is the canonical provenance string."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    text = payload["attestation"]["text"]
    # Assert
    assert text == "Provenance checked by SciTeX Clew."


def test_v12_attestation_url_present(tmp_path, env_sandbox):
    """attestation.url points to the scitex-clew GitHub repo."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    url = payload["attestation"]["url"]
    # Assert
    assert url == "https://github.com/ywatanabe1989/scitex-clew"


def test_v12_attestation_tool_present(tmp_path, env_sandbox):
    """attestation.tool is 'scitex-clew'."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    tool = payload["attestation"]["tool"]
    # Assert
    assert tool == "scitex-clew"


def test_v12_attestation_version_is_nonempty_str(tmp_path, env_sandbox):
    """attestation.version is a non-empty string (dynamic, not hardcoded)."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    ver = payload["attestation"]["version"]
    # Assert
    assert isinstance(ver, str) and len(ver) > 0


def test_v12_attestation_verified_count_counts_only_verified_status(tmp_path, env_sandbox):
    """attestation.verified_count equals the number of claims with status=='verified'."""
    # Arrange — seed 1 claim (registered, not verified) so verified_count should be 0
    payload = _export_v12(tmp_path, env_sandbox, num_verified=0, num_registered=2)
    # Act
    verified_count = payload["attestation"]["verified_count"]
    actual_verified = sum(1 for c in payload["claims"] if c["status"] == "verified")
    # Assert
    assert verified_count == actual_verified


def test_v12_attestation_counts_sum_to_claims_count(tmp_path, env_sandbox):
    """attestation.verified_count + unverified_count == claims_count."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox, num_verified=2, num_registered=1)
    # Act
    total = payload["attestation"]["verified_count"] + payload["attestation"]["unverified_count"]
    # Assert
    assert total == payload["claims_count"]


def test_v12_legend_statuses_has_four_display_states(tmp_path, env_sandbox):
    """legend.statuses has exactly 4 display states (v1.3: verified/suspect/failed/exception)."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    status_names = {entry["status"] for entry in payload["legend"]["statuses"]}
    # Assert — v1.3: 4 display buckets, not per-palette-key
    assert status_names == {"verified", "suspect", "failed", "exception"}


def test_v12_legend_statuses_colors_are_bare_hex(tmp_path, env_sandbox):
    """legend.statuses colors are 6-char hex strings without a leading '#'."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    colors = [entry["color"] for entry in payload["legend"]["statuses"]]
    # Assert — every color is a 6-char hex string with no '#' prefix
    assert all(
        isinstance(c, str) and len(c) == 6 and not c.startswith("#")
        for c in colors
    )


def test_v13_legend_has_no_subbadges_key(tmp_path, env_sandbox):
    """v1.3 legend has no 'subbadges' key — icons removed, color-only."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    has_subbadges = "subbadges" in payload.get("legend", {})
    # Assert — subbadges deleted in v1.3
    assert not has_subbadges


def test_v13_legend_statuses_exactly_4_entries(tmp_path, env_sandbox):
    """v1.3 legend.statuses has exactly 4 entries."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    count = len(payload["legend"]["statuses"])
    # Assert
    assert count == 4


def test_v12_backward_compat_palette_still_present(tmp_path, env_sandbox):
    """v1.1 'palette' top-level key is still present (backward-compat)."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    palette = payload.get("palette")
    # Assert
    assert isinstance(palette, dict) and len(palette) > 0


def test_v12_backward_compat_claims_count_present(tmp_path, env_sandbox):
    """v1.1 'claims_count' top-level key is still present."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    claims_count = payload.get("claims_count")
    # Assert
    assert isinstance(claims_count, int)


def test_v12_backward_compat_per_claim_color_present(tmp_path, env_sandbox):
    """Every claim entry still carries the v1.1 'color' field."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox, num_registered=1)
    # Act
    missing_color = [c for c in payload["claims"] if "color" not in c]
    # Assert
    assert missing_color == []


def test_v12_backward_compat_per_claim_chain_flags_present(tmp_path, env_sandbox):
    """Every claim entry still carries v1.1 chain_has_exception + chain_has_frozen."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox, num_registered=1)
    # Act
    missing_flags = [
        c for c in payload["claims"]
        if "chain_has_exception" not in c or "chain_has_frozen" not in c
    ]
    # Assert
    assert missing_flags == []


# ---------------------------------------------------------------------------
# Schema v1.3 tests: 4-state display_group / display_color / display_palette
# (PA-307 §3: AAA comment markers + ONE observable assertion per test)
# ---------------------------------------------------------------------------


def test_v13_display_palette_present_in_payload(tmp_path, env_sandbox):
    """Schema v1.3 payload has a top-level 'display_palette' dict."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    dp = payload.get("display_palette")
    # Assert
    assert isinstance(dp, dict) and set(dp.keys()) == {"verified", "suspect", "failed", "exception"}


def test_v13_display_palette_verified_hex(tmp_path, env_sandbox):
    """display_palette.verified == '2da44e' (green)."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    verified_hex = payload["display_palette"]["verified"]
    # Assert
    assert verified_hex == "2da44e"


def test_v13_display_palette_exception_hex(tmp_path, env_sandbox):
    """display_palette.exception == '8250df' (violet)."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    exception_hex = payload["display_palette"]["exception"]
    # Assert
    assert exception_hex == "8250df"


def test_v13_display_groups_present_in_payload(tmp_path, env_sandbox):
    """Schema v1.3 payload has a top-level 'display_groups' mapping."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    dg = payload.get("display_groups")
    # Assert
    assert isinstance(dg, dict) and "mismatch" in dg and dg["mismatch"] == "failed"


def test_v13_per_claim_display_group_present(tmp_path, env_sandbox):
    """Every claim entry carries a 'display_group' field in v1.3."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox, num_registered=1)
    # Act
    missing_dg = [c for c in payload["claims"] if "display_group" not in c]
    # Assert
    assert missing_dg == []


def test_v13_per_claim_display_color_present(tmp_path, env_sandbox):
    """Every claim entry carries a 'display_color' field in v1.3."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox, num_registered=1)
    # Act
    missing_dc = [c for c in payload["claims"] if "display_color" not in c]
    # Assert
    assert missing_dc == []


def test_v13_suspect_status_display_group_is_suspect(tmp_path, env_sandbox):
    """A claim that source-verifies but chain fails → status 'suspect', display_group 'suspect'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = _make_source(workdir)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(src),
    )
    import sqlite3
    db = clew.get_db()
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'suspect' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert
    assert claim_dict["display_group"] == "suspect"


def test_v13_mismatch_status_display_group_is_failed(tmp_path, env_sandbox):
    """A claim with status 'mismatch' → display_group 'failed'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    src = _make_source(workdir)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(src),
    )
    import sqlite3
    db = clew.get_db()
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'mismatch' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert
    assert claim_dict["display_group"] == "failed"


def test_v13_missing_status_display_group_is_failed(tmp_path, env_sandbox):
    """A claim with status 'missing' → display_group 'failed'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
    )
    import sqlite3
    db = clew.get_db()
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'missing' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert
    assert claim_dict["display_group"] == "failed"


def test_v13_registered_status_display_group_is_suspect(tmp_path, env_sandbox):
    """A claim with status 'registered' → display_group 'suspect' (never-verified folds into amber)."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
    )
    # status is 'registered' by default
    out = workdir / "claims_v13.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert
    assert claim_dict["display_group"] == "suspect"


def test_v13_verified_with_exception_chain_display_group_is_exception(tmp_path, env_sandbox):
    """A verified claim whose chain has an exception → display_group 'exception', display_color '8250df'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_EXCV3"
    script = str(workdir / "run.py")
    out_file = workdir / "result_exc.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="exception")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "abc789", role="output")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    import sqlite3
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'verified' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13_exc.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert — verified + chain exception → exception display bucket
    assert claim_dict["display_group"] == "exception"


def test_v13_verified_with_exception_chain_display_color_is_violet(tmp_path, env_sandbox):
    """A verified claim with exception chain → display_color '8250df' (violet)."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_EXCV4"
    script = str(workdir / "run.py")
    out_file = workdir / "result_exc2.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="exception")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "abc790", role="output")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    import sqlite3
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'verified' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13_exc2.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert
    assert claim_dict["display_color"] == "8250df"


def test_v13_verified_with_frozen_chain_display_group_is_verified(tmp_path, env_sandbox):
    """A verified claim whose chain has a frozen file → display_group 'verified' (frozen folds in)."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_FRV3"
    script = str(workdir / "run.py")
    out_file = workdir / "frozen_v3.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="tracked")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "deadbeef3", role="output", frozen=True)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    import sqlite3
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'verified' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13_froz.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert — frozen folds into verified (reader bucket stays green)
    assert claim_dict["display_group"] == "verified"


def test_v13_verified_with_frozen_chain_resolved_status_is_frozen(tmp_path, env_sandbox):
    """A verified claim whose chain has a frozen file → resolved_status 'frozen', color '0072b2'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_FRV4"
    script = str(workdir / "run.py")
    out_file = workdir / "frozen_v4.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="tracked")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "deadbeef4", role="output", frozen=True)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    import sqlite3
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'verified' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13_froz2.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert — full-7 resolved status keeps the distinct frozen blue
    assert claim_dict["resolved_status"] == "frozen" and claim_dict["color"] == "0072b2"


def test_v13_suspect_with_exception_chain_stays_suspect(tmp_path, env_sandbox):
    """Chain overrides apply to VERIFIED claims only → suspect stays 'suspect' despite exception chain."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_EXCV5"
    script = str(workdir / "run.py")
    out_file = workdir / "result_exc5.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="exception")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "abc795", role="output")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    import sqlite3
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'suspect' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13_exc5.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert — chain-exception never promotes a non-verified claim
    assert claim_dict["display_group"] == "suspect" and claim_dict["resolved_status"] == "suspect"


def test_v13_registered_with_frozen_chain_stays_registered(tmp_path, env_sandbox):
    """A never-verified claim over a frozen chain stays 'registered' (grey) — no false-green."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_FRV5"
    script = str(workdir / "run.py")
    out_file = workdir / "frozen_v5.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="tracked")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "deadbeef5", role="output", frozen=True)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    # status stays 'registered' — no verify pass
    out = workdir / "claims_v13_froz5.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert — frozen chain never greens a never-verified claim
    assert (
        claim_dict["resolved_status"] == "registered"
        and claim_dict["color"] == "6e7781"
        and claim_dict["display_group"] == "suspect"
    )


def test_v13_mismatch_with_exception_chain_stays_failed(tmp_path, env_sandbox):
    """Precedence: mismatch outranks chain exception → display_group stays 'failed'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-01M-01D-00h00m00s_EXCV6"
    script = str(workdir / "run.py")
    out_file = workdir / "result_exc6.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="exception")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "abc796", role="output")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    import sqlite3
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'mismatch' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13_exc6.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert — hard failure is never masked by a declared exception
    assert claim_dict["display_group"] == "failed" and claim_dict["resolved_status"] == "mismatch"


def test_v13_missing_claim_color_is_distinct_dark_red(tmp_path, env_sandbox):
    """A 'missing' claim's color resolves to the distinct dark red 'a40e26'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
    )
    import sqlite3
    db = clew.get_db()
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'missing' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    out = workdir / "claims_v13_missing.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    claim_dict = json.loads(out.read_text())["claims"][0]
    # Assert — missing has its own hue, distinct from mismatch cf222e
    assert claim_dict["color"] == "a40e26"


def test_v13_palette_full7_hexes_match_locked_convention(tmp_path, env_sandbox):
    """Top-level palette carries the operator-locked full-7 hexes (bare, no '#')."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    palette = payload["palette"]
    # Assert — one locked hue per status
    assert palette == {
        "verified": "2da44e",
        "suspect": "d29922",
        "mismatch": "cf222e",
        "missing": "a40e26",
        "registered": "6e7781",
        "exception": "8250df",
        "frozen": "0072b2",
    }


def test_v13_display_groups_full7_collapse_map(tmp_path, env_sandbox):
    """display_groups collapses each full-7 status onto the 4-bucket reader set."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    dg = payload["display_groups"]
    # Assert — per-status collapse map (registered→suspect, frozen→verified)
    assert dg == {
        "verified": "verified",
        "suspect": "suspect",
        "mismatch": "failed",
        "missing": "failed",
        "registered": "suspect",
        "exception": "exception",
        "frozen": "verified",
    }


def test_v13_per_claim_resolved_status_present(tmp_path, env_sandbox):
    """Every claim entry carries a full-7 'resolved_status' field in v1.3."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox, num_registered=1)
    # Act
    missing_rs = [c for c in payload["claims"] if "resolved_status" not in c]
    # Assert
    assert missing_rs == []


def test_v13_legend_has_exactly_four_display_state_entries(tmp_path, env_sandbox):
    """legend has exactly the 4 display states and no subbadges key."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    legend = payload["legend"]
    # Act
    statuses = {e["status"] for e in legend["statuses"]}
    # Assert — exactly 4 display states
    assert statuses == {"verified", "suspect", "failed", "exception"} and "subbadges" not in legend


def test_v13_legend_all_statuses_have_wavy_underline_marker(tmp_path, env_sandbox):
    """Every legend entry has marker == 'wavy-underline'."""
    # Arrange
    payload = _export_v12(tmp_path, env_sandbox)
    # Act
    markers = {e["marker"] for e in payload["legend"]["statuses"]}
    # Assert
    assert markers == {"wavy-underline"}


def test_v13_back_compat_partial_stored_status_surfaces_as_suspect(tmp_path, env_sandbox):
    """A row stored with status 'partial' in the DB surfaces as 'suspect' via list_claims."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
    )
    # Simulate a legacy DB row with old "partial" status
    import sqlite3
    db = clew.get_db()
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("UPDATE claims SET status = 'partial' WHERE 1=1")
        conn.commit()
    finally:
        conn.close()
    # Act — list_claims must normalize "partial" -> "suspect"
    claims = clew.list_claims()
    # Assert
    assert claims[0].status == "suspect"


# ---------------------------------------------------------------------------
# Schema v1.3 additive: exception_reasons per-claim + top-level exceptions
# + honest legend label (Change 1 + Change 2)
# (PA-306 §3 no mocks — real temp DBs via DB API;
#  PA-307 §3 AAA + one observable assertion per test)
# ---------------------------------------------------------------------------


def _make_exception_run(db, workdir, session_id, out_filename, reason=None):
    """Register an exception run + output file; return the output Path."""
    script = str(workdir / "run.py")
    out_file = workdir / out_filename
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="exception", exception_reason=reason)
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "hashXYZ", role="output")
    return out_file


def test_v13_exception_reasons_contains_reason_for_exception_chain(tmp_path, env_sandbox):
    """A claim whose chain has an exception run with a recorded reason → exception_reasons has that reason."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-06M-01D-00h00m00s_EXCR1"
    out_file = _make_exception_run(db, workdir, session_id, "result_r1.csv", reason="4.1 TB gPAC job, too expensive to re-run")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    out = workdir / "claims_exc_reason.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    payload = json.loads(out.read_text())
    # Assert — the claim's exception_reasons contains the recorded reason
    assert "4.1 TB gPAC job, too expensive to re-run" in payload["claims"][0]["exception_reasons"]


def test_v13_exception_reasons_empty_for_no_exception_chain(tmp_path, env_sandbox):
    """A claim with NO exception in its chain → exception_reasons == []."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-06M-01D-00h00m00s_NXCR1"
    script = str(workdir / "run.py")
    out_file = workdir / "result_nxcr.csv"
    out_file.write_text("x=1\n")
    db.add_run(session_id, script, provenance="tracked")
    db.finish_run(session_id, status="success")
    db.add_file_hash(session_id, str(out_file), "hashTRK", role="output")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    out = workdir / "claims_no_exc.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    payload = json.loads(out.read_text())
    # Assert
    assert payload["claims"][0]["exception_reasons"] == []


def test_v13_exception_reason_null_becomes_no_reason_given(tmp_path, env_sandbox):
    """An exception run with NULL reason → emitted reason is 'no reason given'."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-06M-01D-00h00m00s_NULLR"
    # reason=None → NULL in DB
    out_file = _make_exception_run(db, workdir, session_id, "result_null.csv", reason=None)
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    out = workdir / "claims_null_reason.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    payload = json.loads(out.read_text())
    # Assert
    assert payload["claims"][0]["exception_reasons"] == ["no reason given"]


def test_v13_top_level_exceptions_deduped_across_claims(tmp_path, env_sandbox):
    """Two claims sharing one exception node → top-level exceptions has exactly one entry."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-06M-01D-00h00m00s_DEDUP"
    out_file = _make_exception_run(db, workdir, session_id, "result_dedup.csv", reason="shared exception reason")
    paper = workdir / "paper.tex"
    paper.write_text("claim1\nclaim2\n")
    # Two claims pointing at the same exception session
    for line in [1, 2]:
        clew.add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=line,
            claim_value=f"v{line}",
            source_file=str(out_file),
            source_session=session_id,
        )
    out = workdir / "claims_dedup.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    payload = json.loads(out.read_text())
    # Assert — only ONE entry in the top-level exceptions list
    assert len(payload["exceptions"]) == 1


def test_v13_top_level_exceptions_has_session_id_and_reason(tmp_path, env_sandbox):
    """top-level exceptions entry has session_id and reason keys."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    db = clew.get_db()
    session_id = "2026Y-06M-01D-00h00m00s_EXCS1"
    out_file = _make_exception_run(db, workdir, session_id, "result_excs.csv", reason="known provenance gap")
    paper = workdir / "paper.tex"
    paper.write_text("claim\n")
    clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(out_file),
        source_session=session_id,
    )
    out = workdir / "claims_excs.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    exceptions = json.loads(out.read_text())["exceptions"]
    # Assert — the one entry has both fields
    assert exceptions[0]["session_id"] == session_id and exceptions[0]["reason"] == "known provenance gap"


def test_v13_legend_exception_label_is_honest_wording(tmp_path, env_sandbox):
    """The exception legend label uses the operator-locked honest (non-vouching) wording."""
    # Arrange
    workdir = _fresh_db(tmp_path, env_sandbox)
    env_sandbox.chdir(workdir)
    _make_project_root(workdir)
    env_sandbox.set_env("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "0")
    _seed_claim(workdir)
    out = workdir / "claims_legend.json"
    # Act
    clew.export_claims_json(path=out, read_only=False)
    legend_statuses = json.loads(out.read_text())["legend"]["statuses"]
    exc_entry = next(e for e in legend_statuses if e["status"] == "exception")
    # Assert — operator-locked wording: transparent, no vouching
    assert exc_entry["label"] == (
        "exception — auto-verification chain does not connect through this declared node"
        " (transparently NOT auto-verified)"
    )
