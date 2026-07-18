#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the scitex-dev pre-submission gate plugin (source-reachability).

Skipped when scitex-dev < 0.26.0 (no ``scitex_dev.gate``) — the local sac venv
is 0.24.1; CI installs the latest scitex-dev and runs these for real.
"""

import hashlib
import sqlite3

import pytest

pytest.importorskip("scitex_dev.gate")

from scitex_clew._claim._model import migrate_add_claims_table  # noqa: E402
from scitex_clew._db import VerificationDB  # noqa: E402
from scitex_clew._gate_plugin import _run, provide  # noqa: E402
from scitex_clew._sources import register_source  # noqa: E402


def _make_capsule(tmp_path, *, runs=1):
    """Create a capsule workdir with a clew DB (schema + optional run rows)."""
    workdir = tmp_path / "capsule"
    db_path = workdir / ".scitex" / "clew" / "runtime" / "clew.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = VerificationDB(db_path=db_path)  # creates runs/file_hashes/... schema
    migrate_add_claims_table(db_path)  # creates the claims table
    for i in range(runs):
        db.add_run(f"sess{i}", "analysis.py")
    return workdir, db_path


def _insert_claim(db_path, *, claim_id, status, source_file="", source_hash=""):
    """Insert one claim row directly (real DB row, chosen status)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO claims (claim_id, file_path, line_number, claim_type, "
            "claim_value, source_session, source_file, source_hash, "
            "verified_at, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                claim_id,
                "paper.tex",
                1,
                "value",
                "0.94",
                None,
                source_file,
                source_hash,
                "2026-01-01T00:00:00",
                status,
            ),
        )
        conn.commit()
    finally:
        conn.close()


class TestProvide:
    def test_provide_returns_the_source_reachability_gatecheck(self):
        # Arrange
        checks = provide()
        # Act
        ids = [c.id for c in checks]
        # Assert
        assert ids == ["clew-source-reachability"]

    def test_gatecheck_is_pre_submission_stage(self):
        # Arrange
        check = provide()[0]
        # Act
        stage = check.stage
        # Assert
        assert stage == "pre-submission"


class TestRun:
    def test_no_clew_db_fails(self, tmp_path):
        # Arrange
        workdir = tmp_path / "empty_capsule"
        workdir.mkdir()
        # Act
        result = _run(workdir, {})
        # Assert
        assert result.passed is False

    def test_zero_runs_fails(self, tmp_path):
        # Arrange
        workdir, _db_path = _make_capsule(tmp_path, runs=0)
        # Act
        result = _run(workdir, {})
        # Assert
        assert result.passed is False

    def test_verified_claim_grounded_to_registered_source_passes(self, tmp_path):
        # Arrange
        workdir, db_path = _make_capsule(tmp_path, runs=1)
        src = workdir / "data" / "raw.csv"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("x,y\n1,2\n")
        register_source(
            [src],
            sources_path=workdir / ".scitex" / "clew" / "sources.json",
            root=workdir,
        )
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        _insert_claim(
            db_path,
            claim_id="c1",
            status="verified",
            source_file=str(src.resolve()),
            source_hash=digest,
        )
        # Act
        result = _run(workdir, {})
        # Assert
        assert result.passed is True

    def test_verified_but_ungrounded_claim_fails_as_unsourced(self, tmp_path):
        # Arrange — manifest active (a registered source exists) but the claim's
        # source_file is NOT registered -> is_grounded False -> unsourced.
        workdir, db_path = _make_capsule(tmp_path, runs=1)
        registered = workdir / "data" / "registered.csv"
        registered.parent.mkdir(parents=True, exist_ok=True)
        registered.write_text("a\n1\n")
        register_source(
            [registered],
            sources_path=workdir / ".scitex" / "clew" / "sources.json",
            root=workdir,
        )
        other = workdir / "results" / "hand_made.csv"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("b\n2\n")
        digest = hashlib.sha256(other.read_bytes()).hexdigest()
        _insert_claim(
            db_path,
            claim_id="c2",
            status="verified",
            source_file=str(other.resolve()),
            source_hash=digest,
        )
        # Act
        result = _run(workdir, {})
        # Assert
        assert result.passed is False and any(
            "unsourced" in f.message for f in result.findings
        )

    def test_unverified_claim_fails(self, tmp_path):
        # Arrange — no manifest (gate inactive); a registered-status claim.
        workdir, db_path = _make_capsule(tmp_path, runs=1)
        _insert_claim(db_path, claim_id="c3", status="registered")
        # Act
        result = _run(workdir, {})
        # Assert
        assert result.passed is False and any(
            "not verified" in f.message for f in result.findings
        )


class TestRunRehashesAtGateTime:
    """The gate RE-HASHES each claim's source at submission time.

    Regression guard for the integrity fix: the gate must recompute the source
    hash at gate time and require all-green, NEVER trust the ``status`` flag the
    solver's own ``clew verify`` wrote into the DB. Before the fix the per-claim
    check was a raw ``claim.status != "verified"`` read, so a tampered source
    whose stored status stayed ``verified`` sailed through (the TAMPERED case
    below wrongly PASSED).
    """

    def test_clean_source_matching_hash_passes(self, tmp_path):
        # Arrange — a claim whose source STILL hashes to its recorded value; no
        # manifest (gate inactive) so ONLY the value re-hash half runs.
        workdir, db_path = _make_capsule(tmp_path, runs=1)
        src = workdir / "data" / "clean.csv"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("m\n0.94\n")
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        _insert_claim(
            db_path,
            claim_id="clean1",
            status="verified",
            source_file=str(src.resolve()),
            source_hash=digest,
        )
        # Act
        result = _run(workdir, {})
        # Assert — re-hash matches -> value gate passes -> gate passes.
        assert result.passed is True

    def test_tampered_source_is_rejected_even_when_grounded(self, tmp_path):
        # Arrange — register the source (manifest active, pinned at its ORIGINAL
        # hash), insert a 'verified' claim, THEN tamper the file WITHOUT
        # re-running clew verify. The stored status stays 'verified' AND
        # is_grounded still passes (the claim's stored hash still matches the
        # manifest's pinned hash), so ONLY a real gate-time re-hash can catch it.
        # This is the crux: before the fix this case wrongly PASSED.
        workdir, db_path = _make_capsule(tmp_path, runs=1)
        src = workdir / "data" / "raw.csv"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("x,y\n1,2\n")
        register_source(
            [src],
            sources_path=workdir / ".scitex" / "clew" / "sources.json",
            root=workdir,
        )
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        _insert_claim(
            db_path,
            claim_id="tampered",
            status="verified",
            source_file=str(src.resolve()),
            source_hash=digest,
        )
        # Tamper: change the bytes so the source no longer hashes to `digest`.
        # No `clew verify` re-run — the stored status stays 'verified'.
        src.write_text("x,y\n9,9\n")
        # Act
        result = _run(workdir, {})
        # Assert — REJECTED, and the finding names the hash mismatch (a value
        # failure), NOT 'unsourced' (grounding still passes — the tamper is
        # invisible to is_grounded and only the re-hash catches it).
        assert (
            result.passed is False
            and any("hash mismatch" in f.message for f in result.findings)
            and not any("unsourced" in f.message for f in result.findings)
        )

    def test_missing_source_is_rejected(self, tmp_path):
        # Arrange — a 'verified' claim whose source file is then DELETED (no
        # manifest, so the value re-hash half is what must catch it).
        workdir, db_path = _make_capsule(tmp_path, runs=1)
        src = workdir / "data" / "gone.csv"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("m\n0.94\n")
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        _insert_claim(
            db_path,
            claim_id="missing",
            status="verified",
            source_file=str(src.resolve()),
            source_hash=digest,
        )
        src.unlink()  # delete the source AFTER the claim is registered
        # Act
        result = _run(workdir, {})
        # Assert — the re-hash finds the source gone -> REJECT.
        assert result.passed is False and any(
            "missing" in f.message for f in result.findings
        )


class TestFindingReferencesClaimId:
    """A finding must name the claim by its STABLE ``claim_id``, not by
    ``file:L42`` alone — line numbers shift on every manuscript re-write, so
    a consumer correlating findings across runs (or joining them back to a
    submission keyed by claim_id) cannot use the location as an identity.
    Card: clew-feat-gate-question-id-completeness, part (a)."""

    def test_unsourced_finding_names_the_claim_id(self, tmp_path):
        # Arrange — an ungrounded claim, so exactly one unsourced finding fires.
        workdir, db_path = _make_capsule(tmp_path, runs=1)
        registered = workdir / "data" / "registered.csv"
        registered.parent.mkdir(parents=True, exist_ok=True)
        registered.write_text("a\n1\n")
        register_source(
            [registered],
            sources_path=workdir / ".scitex" / "clew" / "sources.json",
            root=workdir,
        )
        other = workdir / "results" / "hand_made.csv"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_text("b\n2\n")
        _insert_claim(
            db_path,
            claim_id="q_042",
            status="verified",
            source_file=str(other.resolve()),
            source_hash=hashlib.sha256(other.read_bytes()).hexdigest(),
        )
        # Act
        result = _run(workdir, {})
        # Assert
        assert any("q_042" in f.message for f in result.findings)

    def test_value_failure_finding_names_the_claim_id(self, tmp_path):
        # Arrange — a 'verified' claim whose source is deleted -> value failure.
        workdir, db_path = _make_capsule(tmp_path, runs=1)
        src = workdir / "data" / "vanished.csv"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("m\n0.94\n")
        _insert_claim(
            db_path,
            claim_id="q_099",
            status="verified",
            source_file=str(src.resolve()),
            source_hash=hashlib.sha256(src.read_bytes()).hexdigest(),
        )
        src.unlink()
        # Act
        result = _run(workdir, {})
        # Assert
        assert any("q_099" in f.message for f in result.findings)

    def test_finding_still_carries_the_location_as_a_locator(self, tmp_path):
        # Arrange — identity first, but a human still needs somewhere to go.
        workdir, db_path = _make_capsule(tmp_path, runs=1)
        src = workdir / "data" / "vanished2.csv"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text("m\n0.94\n")
        _insert_claim(
            db_path,
            claim_id="q_100",
            status="verified",
            source_file=str(src.resolve()),
            source_hash=hashlib.sha256(src.read_bytes()).hexdigest(),
        )
        src.unlink()
        # Act
        result = _run(workdir, {})
        # Assert — the .tex location the claim was registered at is still shown.
        assert any("paper.tex" in f.message for f in result.findings)
