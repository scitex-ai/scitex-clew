#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail-loud, nuanced exit codes for ``clew verify`` (claim-set mode).

These tests pin the *agent contract*: a solver runs ``clew verify
[--strict]`` before signalling DONE, and DONE is legitimate ONLY on exit
0. Each distinct integrity outcome MUST surface as its own documented
exit code so a harness can branch on it (the concrete motivating failure:
a Haiku agent hand-coded metrics into ``results.json``, registered claims
pointing at it, and printed "DONE" — the claims were never verified).

Strategy (mirrors test_cli_claim_hash_stamp.py / PA-306 §3 no-mocks):
  - drive the real CLI via ``click.testing.CliRunner`` in-process,
  - isolate the DB with ``set_db()`` (autouse),
  - seed REAL runs / file hashes via the live ``VerificationDB`` rather
    than mocking — every assertion observes a real verification pass.
  - AAA marker comments + one observable assertion per test (PA-307 §3).
"""

from __future__ import annotations

import json
import os

import pytest

# click is in the [cli] extra (not [project] deps) — PA-303.
CliRunner = pytest.importorskip("click.testing").CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli import _exit_codes as codes
from scitex_clew._cli._main import main
from scitex_clew._db import set_db
from scitex_clew._hash import hash_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    # Disable the claims.json auto-export so the read-only artifact does not
    # leak between the per-test temp DBs (PA-306: real state, explicit undo).
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    db_path = tmp_path / "verify_failloud.db"
    set_db(db_path)
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


@pytest.fixture
def runner():
    return CliRunner()


def _seed_tracked_source(db, tmp_path, name="results.json", body='{"acc": 0.94}\n'):
    """Write a source file AND record a verified @stx.session that produced it.

    Returns the absolute source path. This is the "honest" case — the
    source has real upstream lineage, so a strict verify passes.
    """
    src = tmp_path / name
    src.write_text(body)
    sid = "2026Y-06M-19D-00h00m00s_Seed-main"
    db.add_run(sid, str(tmp_path / "make_results.py"))
    db.add_file_hash(sid, str(src.resolve()), hash_file(src), "output")
    db.finish_run(sid, status="success")
    return src


def _add_claim(runner, paper_path, source_file=None, value="0.94"):
    args = [
        "claim",
        "add",
        "--file-path",
        str(paper_path),
        "--type",
        "value",
        "--line-number",
        "1",
        "--value",
        value,
    ]
    if source_file is not None:
        args += ["--source-file", str(source_file)]
    return runner.invoke(main, args)


# ---------------------------------------------------------------------------
# NO_CLAIMS (20)
# ---------------------------------------------------------------------------


class TestVerifyNoClaims:
    def test_no_claims_exit_code_is_no_claims(self, runner, isolated_db):
        # Arrange — empty DB.
        # Act
        result = runner.invoke(main, ["verify"])
        # Assert
        assert result.exit_code == codes.NO_CLAIMS

    def test_no_claims_json_exit_name(self, runner, isolated_db):
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "verify"])
        parsed = json.loads(result.output)
        # Assert
        assert parsed["exit_name"] == "NO_CLAIMS"


# ---------------------------------------------------------------------------
# UNVERIFIED (10) — the fabrication case
# ---------------------------------------------------------------------------


class TestVerifyUnverified:
    def test_claim_without_source_is_unverified(self, runner, isolated_db, tmp_path):
        # Arrange — a claim registered against NOTHING computable (the
        # hand-coded-metrics fabrication: no source_file linked).
        paper = tmp_path / "paper.tex"
        paper.write_text("p=0.003\n")
        _add_claim(runner, paper, source_file=None, value="p=0.003")
        # Act
        result = runner.invoke(main, ["verify"])
        # Assert
        assert result.exit_code == codes.UNVERIFIED

    def test_unverified_json_counts(self, runner, isolated_db, tmp_path):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("p=0.003\n")
        _add_claim(runner, paper, source_file=None, value="p=0.003")
        # Act
        result = runner.invoke(main, ["--json", "verify"])
        parsed = json.loads(result.output)
        # Assert
        assert parsed["counts"].get("UNVERIFIED") == 1


# ---------------------------------------------------------------------------
# OK (0) — source-verified
# ---------------------------------------------------------------------------


class TestVerifyOk:
    def test_source_verified_claim_exit_zero(self, runner, isolated_db, tmp_path):
        # Arrange — claim whose source is a recorded, verified session output.
        src = _seed_tracked_source(isolated_db, tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        _add_claim(runner, paper, source_file=src)
        # Act
        result = runner.invoke(main, ["verify"])
        # Assert
        assert result.exit_code == codes.OK

    def test_source_verified_claim_strict_exit_zero(
        self, runner, isolated_db, tmp_path
    ):
        # Arrange — same source has real @stx.session lineage, so strict passes.
        src = _seed_tracked_source(isolated_db, tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        _add_claim(runner, paper, source_file=src)
        # Act
        result = runner.invoke(main, ["verify", "--strict"])
        # Assert
        assert result.exit_code == codes.OK

    def test_ok_json_verified_count(self, runner, isolated_db, tmp_path):
        # Arrange
        src = _seed_tracked_source(isolated_db, tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        _add_claim(runner, paper, source_file=src)
        # Act
        result = runner.invoke(main, ["--json", "verify"])
        parsed = json.loads(result.output)
        # Assert
        assert parsed["verified"] == parsed["total"] == 1


# ---------------------------------------------------------------------------
# HASH_MISMATCH (12) — source changed after registration
# ---------------------------------------------------------------------------


class TestVerifyHashMismatch:
    def test_tampered_source_is_hash_mismatch(self, runner, isolated_db, tmp_path):
        # Arrange — register against a good source, then tamper with it.
        src = _seed_tracked_source(isolated_db, tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        _add_claim(runner, paper, source_file=src)
        src.write_text('{"acc": 0.99}\n')  # out-of-band edit
        # Act
        result = runner.invoke(main, ["verify"])
        # Assert
        assert result.exit_code == codes.HASH_MISMATCH


# ---------------------------------------------------------------------------
# SOURCE_MISSING (11) — source file gone
# ---------------------------------------------------------------------------


class TestVerifySourceMissing:
    def test_deleted_source_is_source_missing(self, runner, isolated_db, tmp_path):
        # Arrange
        src = _seed_tracked_source(isolated_db, tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        _add_claim(runner, paper, source_file=src)
        src.unlink()  # artifact gone
        # Act
        result = runner.invoke(main, ["verify"])
        # Assert
        assert result.exit_code == codes.SOURCE_MISSING


# ---------------------------------------------------------------------------
# NO_LINEAGE (13) — strict only: hand-written leaf with no @stx.session
# ---------------------------------------------------------------------------


class TestVerifyNoLineage:
    def test_hand_written_leaf_passes_non_strict(self, runner, isolated_db, tmp_path):
        # Arrange — source exists + hash matches, but NO session produced it.
        leaf = tmp_path / "hand_written.json"
        leaf.write_text('{"acc": 0.94}\n')
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        _add_claim(runner, paper, source_file=leaf)
        # Act — non-strict only needs a hash match.
        result = runner.invoke(main, ["verify"])
        # Assert
        assert result.exit_code == codes.OK

    def test_hand_written_leaf_fails_strict_with_no_lineage(
        self, runner, isolated_db, tmp_path
    ):
        # Arrange — the exact "hand-coded results.json" case.
        leaf = tmp_path / "hand_written.json"
        leaf.write_text('{"acc": 0.94}\n')
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        _add_claim(runner, paper, source_file=leaf)
        # Act — strict requires upstream @stx.session lineage.
        result = runner.invoke(main, ["verify", "--strict"])
        # Assert
        assert result.exit_code == codes.NO_LINEAGE


# ---------------------------------------------------------------------------
# Single-run mode (SESSION_ID given) stays fail-loud + backward compatible
# ---------------------------------------------------------------------------


class TestVerifySingleRun:
    def test_verified_run_exits_zero(self, runner, isolated_db, tmp_path):
        # Arrange — a fully verified session.
        _seed_tracked_source(isolated_db, tmp_path)
        # Act
        result = runner.invoke(main, ["verify", "2026Y-06M-19D-00h00m00s_Seed-main"])
        # Assert
        assert result.exit_code == codes.OK

    def test_missing_run_exits_nonzero_without_traceback(self, runner, isolated_db):
        # Arrange
        # Act
        result = runner.invoke(main, ["verify", "nonexistent_session_xyz"])
        # Assert — fail loud, but never crash.
        assert result.exit_code != 0 and "Traceback" not in result.output


# ---------------------------------------------------------------------------
# --config: per-pattern severity overrides flow end-to-end through the CLI
# ---------------------------------------------------------------------------


class TestVerifyConfig:
    def test_config_downgrade_tolerates_fabrication(
        self, runner, isolated_db, tmp_path
    ):
        # Arrange — a no-source claim is UNVERIFIED (would be exit 10)...
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        _add_claim(runner, paper)
        cfg = tmp_path / "clew.yaml"
        cfg.write_text("verify:\n  severity:\n    unverified: warning\n")
        # Act — ...but a project that downgrades it to a warning tolerates it.
        result = runner.invoke(main, ["verify", "--config", str(cfg)])
        # Assert
        assert result.exit_code == codes.OK

    def test_config_invalid_severity_fails_loud(self, runner, isolated_db, tmp_path):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        _add_claim(runner, paper)
        cfg = tmp_path / "clew.yaml"
        cfg.write_text("verify:\n  severity:\n    unverified: bogus\n")
        # Act
        result = runner.invoke(main, ["verify", "--config", str(cfg)])
        # Assert — a bad config must NOT silently pass.
        assert result.exit_code != 0


# EOF
