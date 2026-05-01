#!/usr/bin/env python3
"""Tests for scitex_clew._rerun module."""

from __future__ import annotations

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._chain import (
    FileVerification,
    VerificationLevel,
    VerificationStatus,
)
from scitex_clew._rerun import (
    _compare_hashes,
    _determine_status,
    verify_by_rerun,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Inject a fresh temp DB and reset global state after each test."""
    db_path = tmp_path / "rerun_test.db"
    set_db(db_path)
    yield
    _db_module._DB_INSTANCE = None


def _make_file_verification(path, role, expected, current, status):
    return FileVerification(
        path=path,
        role=role,
        expected_hash=expected,
        current_hash=current,
        status=status,
    )


# ---------------------------------------------------------------------------
# _compare_hashes
# ---------------------------------------------------------------------------


class TestCompareHashes:
    def test_matching_hashes_return_verified(self):
        original = {"/path/to/output.csv": "abc123"}
        new = {"/other/path/output.csv": "abc123"}
        result = _compare_hashes(original, new)
        assert len(result) == 1
        assert result[0].status == VerificationStatus.VERIFIED

    def test_mismatched_hashes_return_mismatch(self):
        original = {"/path/output.csv": "abc123"}
        new = {"/path/output.csv": "different_hash"}
        result = _compare_hashes(original, new)
        assert len(result) == 1
        assert result[0].status == VerificationStatus.MISMATCH

    def test_missing_file_in_new_returns_missing(self):
        original = {"/path/output.csv": "abc123"}
        new = {}
        result = _compare_hashes(original, new)
        assert len(result) == 1
        assert result[0].status == VerificationStatus.MISSING

    def test_matches_by_filename_not_full_path(self):
        original = {"/original/dir/results.csv": "hash_a"}
        new = {"/new/run/dir/results.csv": "hash_a"}
        result = _compare_hashes(original, new)
        assert result[0].status == VerificationStatus.VERIFIED

    def test_multiple_files(self):
        original = {
            "/path/out1.csv": "hash1",
            "/path/out2.png": "hash2",
            "/path/out3.csv": "hash3",
        }
        new = {
            "/new/out1.csv": "hash1",
            "/new/out2.png": "different",
            # out3 is missing
        }
        result = _compare_hashes(original, new)
        statuses = {fv.path: fv.status for fv in result}
        assert statuses["out1.csv"] == VerificationStatus.VERIFIED
        assert statuses["out2.png"] == VerificationStatus.MISMATCH
        assert statuses["out3.csv"] == VerificationStatus.MISSING

    def test_empty_original_returns_empty_list(self):
        result = _compare_hashes({}, {"path/file.csv": "hash"})
        assert result == []

    def test_result_contains_expected_hash(self):
        original = {"/path/file.csv": "expected_hash"}
        new = {"/new/file.csv": "expected_hash"}
        result = _compare_hashes(original, new)
        assert result[0].expected_hash == "expected_hash"

    def test_result_contains_current_hash_when_matched(self):
        original = {"/path/file.csv": "my_hash"}
        new = {"/new/file.csv": "my_hash"}
        result = _compare_hashes(original, new)
        assert result[0].current_hash == "my_hash"

    def test_result_current_hash_none_when_missing(self):
        original = {"/path/file.csv": "my_hash"}
        new = {}
        result = _compare_hashes(original, new)
        assert result[0].current_hash is None

    def test_role_is_output(self):
        original = {"/path/file.csv": "h"}
        new = {"/new/file.csv": "h"}
        result = _compare_hashes(original, new)
        assert result[0].role == "output"


# ---------------------------------------------------------------------------
# _determine_status
# ---------------------------------------------------------------------------


class TestDetermineStatus:
    def test_all_verified_returns_verified(self):
        fvs = [
            _make_file_verification(
                "a.csv", "output", "h1", "h1", VerificationStatus.VERIFIED
            ),
            _make_file_verification(
                "b.csv", "output", "h2", "h2", VerificationStatus.VERIFIED
            ),
        ]
        assert _determine_status(fvs) == VerificationStatus.VERIFIED

    def test_one_mismatch_returns_mismatch(self):
        fvs = [
            _make_file_verification(
                "a.csv", "output", "h1", "h1", VerificationStatus.VERIFIED
            ),
            _make_file_verification(
                "b.csv", "output", "h2", "wrong", VerificationStatus.MISMATCH
            ),
        ]
        assert _determine_status(fvs) == VerificationStatus.MISMATCH

    def test_one_missing_no_mismatch_returns_unknown(self):
        fvs = [
            _make_file_verification(
                "a.csv", "output", "h1", "h1", VerificationStatus.VERIFIED
            ),
            _make_file_verification(
                "b.csv", "output", "h2", None, VerificationStatus.MISSING
            ),
        ]
        # No MISMATCH, so returns UNKNOWN
        assert _determine_status(fvs) == VerificationStatus.UNKNOWN

    def test_empty_list_returns_verified(self):
        # all() on empty is True
        assert _determine_status([]) == VerificationStatus.VERIFIED

    def test_mismatch_takes_priority_over_missing(self):
        fvs = [
            _make_file_verification(
                "a.csv", "output", "h1", None, VerificationStatus.MISSING
            ),
            _make_file_verification(
                "b.csv", "output", "h2", "wrong", VerificationStatus.MISMATCH
            ),
        ]
        assert _determine_status(fvs) == VerificationStatus.MISMATCH


# ---------------------------------------------------------------------------
# verify_by_rerun — basic cases (no actual script execution)
# ---------------------------------------------------------------------------


class TestVerifyByRerun:
    def test_nonexistent_session_id_returns_unknown(self):
        result = verify_by_rerun("nonexistent_session_xyz")
        assert result.status == VerificationStatus.UNKNOWN

    def test_missing_script_path_returns_missing(self):
        db = _db_module.get_db()
        db.add_run("sess_no_script", "/nonexistent/script.py")
        result = verify_by_rerun("sess_no_script")
        assert result.status == VerificationStatus.MISSING
        assert result.session_id == "sess_no_script"

    def test_no_output_hashes_returns_unknown(self, tmp_path):
        script = tmp_path / "empty_script.py"
        script.write_text("# no outputs")
        db = _db_module.get_db()
        db.add_run("sess_no_outputs", str(script))
        result = verify_by_rerun("sess_no_outputs")
        assert result.status == VerificationStatus.UNKNOWN

    def test_returns_run_verification_object(self):
        from scitex_clew._chain import RunVerification

        result = verify_by_rerun("nonexistent_xyz")
        assert isinstance(result, RunVerification)

    def test_result_level_is_rerun(self):
        result = verify_by_rerun("nonexistent_xyz")
        assert result.level == VerificationLevel.RERUN

    def test_list_target_returns_list(self):
        results = verify_by_rerun(["nonexistent_1", "nonexistent_2"])
        assert isinstance(results, list)
        assert len(results) == 2

    def test_list_target_each_is_run_verification(self):
        from scitex_clew._chain import RunVerification

        results = verify_by_rerun(["nonexistent_1", "nonexistent_2"])
        for r in results:
            assert isinstance(r, RunVerification)

    def test_single_string_target_returns_single_result(self):
        result = verify_by_rerun("nonexistent_xyz")
        # Should not be a list
        assert not isinstance(result, list)

    def test_verify_session_with_empty_script_path(self):
        db = _db_module.get_db()
        db.add_run("sess_empty_path", "")
        result = verify_by_rerun("sess_empty_path")
        assert result.status in {
            VerificationStatus.MISSING,
            VerificationStatus.UNKNOWN,
        }

    def test_resolve_by_session_id_directly(self):
        db = _db_module.get_db()
        db.add_run("direct_session_id", "/nonexistent/script.py")
        result = verify_by_rerun("direct_session_id")
        # Resolved as session_id; script doesn't exist -> MISSING
        assert result.status == VerificationStatus.MISSING
        assert result.session_id == "direct_session_id"


# ---------------------------------------------------------------------------
# verify_by_rerun alias
# ---------------------------------------------------------------------------


class TestBackwardCompatAlias:
    def test_verify_run_from_scratch_alias(self):
        from scitex_clew._rerun import verify_run_from_scratch

        assert verify_run_from_scratch is verify_by_rerun


# EOF
