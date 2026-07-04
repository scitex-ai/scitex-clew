#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for ``scitex_clew._chain._verify_ops`` — provenance surfacing.

Mirrors src/scitex_clew/_chain/_verify_ops.py per the project mirror rule.

All tests build real temp DBs via the package DB API — no mocks (PA-307).
Each test has exactly one assertion, with # Arrange / # Act / # Assert
markers each on their own lines in that order.
"""

from __future__ import annotations

import pytest

import scitex_clew._db as _db_module
from scitex_clew._chain._types import FileVerification, RunVerification, VerificationStatus
from scitex_clew._chain._verify_ops import verify_file, verify_run
from scitex_clew._db import get_db, set_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Fresh DB for every test; reset the global singleton after."""
    # Arrange
    db_path = tmp_path / "verify_ops_test.db"
    set_db(db_path)
    # Act
    yield get_db()
    # Assert (teardown)
    _db_module._DB_INSTANCE = None


class TestVerifyRunProvenanceSurfacing:
    """verify_run must populate provenance + exception_reason from the DB."""

    def test_verify_run_returns_tracked_provenance_by_default(self, isolated_db):
        # Arrange
        isolated_db.add_run("tracked_001", "/script.py")
        # Act
        result = verify_run("tracked_001")
        # Assert
        assert result.provenance == "tracked"

    def test_verify_run_returns_none_exception_reason_for_tracked(self, isolated_db):
        # Arrange
        isolated_db.add_run("tracked_002", "/script.py")
        # Act
        result = verify_run("tracked_002")
        # Assert
        assert result.exception_reason is None

    def test_verify_run_surfaces_exception_provenance(self, isolated_db):
        # Arrange
        isolated_db.add_run(
            "exception_001",
            "/script.py",
            provenance="exception",
            exception_reason="4.1TB gPAC, recipe-known, never re-run",
        )
        # Act
        result = verify_run("exception_001")
        # Assert
        assert result.provenance == "exception"

    def test_verify_run_surfaces_exception_reason(self, isolated_db):
        # Arrange
        isolated_db.add_run(
            "exception_002",
            "/script.py",
            provenance="exception",
            exception_reason="4.1TB gPAC, recipe-known, never re-run",
        )
        # Act
        result = verify_run("exception_002")
        # Assert
        assert result.exception_reason == "4.1TB gPAC, recipe-known, never re-run"

    def test_verify_run_result_is_runverification_instance(self, isolated_db):
        # Arrange
        isolated_db.add_run("check_type_001", "/script.py")
        # Act
        result = verify_run("check_type_001")
        # Assert
        assert isinstance(result, RunVerification)

    def test_verify_run_exception_with_no_files_is_verified(self, isolated_db):
        # Arrange — an exception node with no file hashes and success status
        # should be VERIFIED (all files verify vacuously).
        isolated_db.add_run(
            "exception_nf_001",
            "/script.py",
            provenance="exception",
            exception_reason="reason",
        )
        isolated_db.finish_run("exception_nf_001", status="success")
        # Act
        result = verify_run("exception_nf_001")
        # Assert
        assert result.status == VerificationStatus.VERIFIED

    def test_verify_run_exception_node_with_missing_output_is_not_verified(
        self, isolated_db, tmp_path
    ):
        # Arrange — exception node registers an output file that doesn't exist;
        # the exception marker must NOT mask the missing-file failure.
        gone_path = str(tmp_path / "gone.csv")
        isolated_db.add_run(
            "exception_missing_001",
            "/script.py",
            provenance="exception",
            exception_reason="external job",
        )
        isolated_db.add_file_hash(
            "exception_missing_001",
            gone_path,
            "deadbeef" * 8,
            "output",
        )
        # Act
        result = verify_run("exception_missing_001")
        # Assert
        assert not result.is_verified


# ---------------------------------------------------------------------------
# Frozen / trusted-input short-circuit
# ---------------------------------------------------------------------------


class TestVerifyFileFrozen:
    """verify_file with frozen=True must not call hash_file."""

    def test_verify_file_frozen_returns_frozen_true_flag(self, tmp_path):
        # Arrange
        f = tmp_path / "huge.npz"
        f.write_bytes(b"data")
        # Act
        result = verify_file(str(f), "recorded_hash_abc", role="input", frozen=True)
        # Assert
        assert result.frozen is True

    def test_verify_file_frozen_returns_verified_status(self, tmp_path):
        # Arrange
        f = tmp_path / "huge2.npz"
        f.write_bytes(b"original content")
        # Act
        result = verify_file(str(f), "any_recorded_hash", role="input", frozen=True)
        # Assert
        assert result.status == VerificationStatus.VERIFIED

    def test_verify_file_frozen_does_not_rehash_file(self, tmp_path):
        # Arrange — wrap the module-level hash_file to count real calls (no mock).
        # A frozen verify_file must not invoke hash_file at all.
        import scitex_clew._chain._verify_ops as _ops_mod

        call_count = []
        _real_hash_file = _ops_mod.hash_file

        def _counting_hash_file(path, **kwargs):
            call_count.append(path)
            return _real_hash_file(path, **kwargs)

        _ops_mod.hash_file = _counting_hash_file
        try:
            f = tmp_path / "huge3.npz"
            f.write_bytes(b"4.1TB large file placeholder content")
            # Act
            verify_file(str(f), "precomputed_hash_not_on_disk", role="input", frozen=True)
        finally:
            _ops_mod.hash_file = _real_hash_file  # restore unconditionally
        # Assert — hash_file must NOT have been called for a frozen file.
        assert len(call_count) == 0

    def test_verify_file_frozen_trusts_hash_even_when_different(self, tmp_path):
        # Arrange — different on-disk content from recorded hash; frozen must pass.
        f = tmp_path / "huge4.npz"
        f.write_bytes(b"A" * 100)
        # Act
        result = verify_file(str(f), "completely_different_hash_xyz", role="input", frozen=True)
        # Assert — frozen is marked on the result
        assert result.frozen is True

    def test_verify_file_frozen_missing_file_returns_missing(self, tmp_path):
        # Arrange — frozen file that does not exist on disk must still surface MISSING.
        gone = str(tmp_path / "nonexistent_4tb_dataset.npz")
        # Act
        result = verify_file(gone, "some_recorded_hash", role="input", frozen=True)
        # Assert
        assert result.status == VerificationStatus.MISSING

    def test_verify_file_frozen_missing_still_has_frozen_flag(self, tmp_path):
        # Arrange
        gone = str(tmp_path / "nonexistent_4tb_dataset2.npz")
        # Act
        result = verify_file(gone, "some_recorded_hash", role="input", frozen=True)
        # Assert
        assert result.frozen is True

    def test_verify_file_not_frozen_detects_tamper(self, tmp_path):
        # Arrange — default frozen=False path must still detect tampered content.
        f = tmp_path / "normal.csv"
        f.write_bytes(b"original")
        wrong_hash = "0" * 64
        # Act
        result = verify_file(str(f), wrong_hash, role="input", frozen=False)
        # Assert
        assert result.status == VerificationStatus.MISMATCH

    def test_verify_file_not_frozen_has_frozen_false(self, tmp_path):
        # Arrange
        f = tmp_path / "normal2.csv"
        f.write_bytes(b"data")
        from scitex_clew._hash import hash_file

        correct_hash = hash_file(str(f))
        # Act
        result = verify_file(str(f), correct_hash, role="input", frozen=False)
        # Assert
        assert result.frozen is False


class TestVerifyRunFrozen:
    """verify_run with a frozen input must propagate the frozen flag upward."""

    def test_verify_run_frozen_input_is_verified(self, isolated_db, tmp_path):
        # Arrange — register a frozen input with a hash that does NOT match
        # the file's actual content; the run must still be VERIFIED.
        f = tmp_path / "huge_input.npz"
        f.write_bytes(b"4.1 TB of data placeholder")
        isolated_db.add_run("frz_run_001", "/script.py")
        isolated_db.add_file_hash(
            "frz_run_001",
            str(f.resolve()),
            "precomputed_hash_not_matching_disk",
            "input",
            frozen=True,
        )
        # Act
        result = verify_run("frz_run_001")
        # Assert
        assert result.is_verified

    def test_verify_run_frozen_input_file_has_frozen_flag(self, isolated_db, tmp_path):
        # Arrange
        f = tmp_path / "huge_input2.npz"
        f.write_bytes(b"placeholder")
        isolated_db.add_run("frz_run_002", "/script.py")
        isolated_db.add_file_hash(
            "frz_run_002",
            str(f.resolve()),
            "precomputed_hash_xyz",
            "input",
            frozen=True,
        )
        # Act
        result = verify_run("frz_run_002")
        frozen_files = [fv for fv in result.files if getattr(fv, "frozen", False)]
        # Assert
        assert len(frozen_files) == 1

    def test_verify_run_non_frozen_input_detects_tamper(self, isolated_db, tmp_path):
        # Arrange — default (not frozen) input with wrong hash must fail.
        f = tmp_path / "normal_input.csv"
        f.write_bytes(b"original content")
        isolated_db.add_run("nfrz_run_001", "/script.py")
        isolated_db.add_file_hash(
            "nfrz_run_001",
            str(f.resolve()),
            "0000000000000000",
            "input",
            frozen=False,
        )
        # Act
        result = verify_run("nfrz_run_001")
        # Assert — non-frozen: tamper detected.
        assert not result.is_verified


# EOF
