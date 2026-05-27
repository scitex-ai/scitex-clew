#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/tests/scitex/verify/test__chain.py

"""Tests for scitex.clew._chain module."""

from scitex_clew import (
    ChainVerification,
    FileVerification,
    RunVerification,
    VerificationLevel,
    VerificationStatus,
    verify_file,
)


class TestVerificationStatus:
    """Tests for VerificationStatus enum."""

    def test_status_values_verificationstatus_verified_value_verified(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert VerificationStatus.VERIFIED.value == "verified"

    def test_status_values_verificationstatus_mismatch_value_mismatch(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert VerificationStatus.MISMATCH.value == "mismatch"

    def test_status_values_verificationstatus_missing_value_missing(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert VerificationStatus.MISSING.value == "missing"

    def test_status_values_verificationstatus_unknown_value_unknown(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert VerificationStatus.UNKNOWN.value == "unknown"



class TestVerificationLevel:
    """Tests for VerificationLevel enum."""

    def test_level_values_verificationlevel_cache_value_cache(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert VerificationLevel.CACHE.value == "cache"

    def test_level_values_verificationlevel_rerun_value_rerun(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert VerificationLevel.RERUN.value == "rerun"



class TestFileVerification:
    """Tests for FileVerification dataclass."""

    def test_file_verification_creation_fv_path_equals_path_to_file_csv(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        fv = FileVerification(
            path="/path/to/file.csv",
            role="input",
            expected_hash="abc123",
            current_hash="abc123",
            status=VerificationStatus.VERIFIED,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert fv.path == "/path/to/file.csv"

    def test_file_verification_creation_fv_role_equals_input(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        fv = FileVerification(
            path="/path/to/file.csv",
            role="input",
            expected_hash="abc123",
            current_hash="abc123",
            status=VerificationStatus.VERIFIED,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert fv.role == "input"

    def test_file_verification_creation_fv_is_verified_is_true(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        fv = FileVerification(
            path="/path/to/file.csv",
            role="input",
            expected_hash="abc123",
            current_hash="abc123",
            status=VerificationStatus.VERIFIED,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert fv.is_verified is True


    def test_file_verification_mismatch(self):
        """Test FileVerification with mismatch."""
        # Arrange
        # Act
        fv = FileVerification(
            path="/path/to/file.csv",
            role="output",
            expected_hash="abc123",
            current_hash="def456",
            status=VerificationStatus.MISMATCH,
        )
        # Assert
        assert fv.is_verified is False

    def test_file_verification_missing_fv_is_verified_is_false(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        fv = FileVerification(
            path="/path/to/missing.csv",
            role="input",
            expected_hash="abc123",
            current_hash=None,
            status=VerificationStatus.MISSING,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert fv.is_verified is False

    def test_file_verification_missing_fv_current_hash_is_none(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        fv = FileVerification(
            path="/path/to/missing.csv",
            role="input",
            expected_hash="abc123",
            current_hash=None,
            status=VerificationStatus.MISSING,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert fv.current_hash is None



class TestRunVerification:
    """Tests for RunVerification dataclass."""

    def test_run_verification_creation_rv_session_id_equals_test_session(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        rv = RunVerification(
            session_id="test_session",
            script_path="/path/to/script.py",
            status=VerificationStatus.VERIFIED,
            files=[],
            combined_hash_expected="hash1",
            combined_hash_current="hash1",
            level=VerificationLevel.CACHE,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert rv.session_id == "test_session"

    def test_run_verification_creation_rv_is_verified_is_true(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        rv = RunVerification(
            session_id="test_session",
            script_path="/path/to/script.py",
            status=VerificationStatus.VERIFIED,
            files=[],
            combined_hash_expected="hash1",
            combined_hash_current="hash1",
            level=VerificationLevel.CACHE,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert rv.is_verified is True


    def test_run_verification_with_files_len_rv_files_is_2(self):
        # Arrange
        # Arrange
        # Arrange
        files = [
            FileVerification(
                "/input.csv", "input", "h1", "h1", VerificationStatus.VERIFIED
            ),
            FileVerification(
                "/output.csv", "output", "h2", "h2", VerificationStatus.VERIFIED
            ),
        ]
        # Act
        # Act
        rv = RunVerification(
            session_id="test",
            script_path="/script.py",
            status=VerificationStatus.VERIFIED,
            files=files,
            combined_hash_expected=None,
            combined_hash_current=None,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert len(rv.files) == 2

    def test_run_verification_with_files_len_rv_inputs_is_1(self):
        # Arrange
        # Arrange
        # Arrange
        files = [
            FileVerification(
                "/input.csv", "input", "h1", "h1", VerificationStatus.VERIFIED
            ),
            FileVerification(
                "/output.csv", "output", "h2", "h2", VerificationStatus.VERIFIED
            ),
        ]
        # Act
        # Act
        rv = RunVerification(
            session_id="test",
            script_path="/script.py",
            status=VerificationStatus.VERIFIED,
            files=files,
            combined_hash_expected=None,
            combined_hash_current=None,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert len(rv.inputs) == 1

    def test_run_verification_with_files_len_rv_outputs_is_1(self):
        # Arrange
        # Arrange
        # Arrange
        files = [
            FileVerification(
                "/input.csv", "input", "h1", "h1", VerificationStatus.VERIFIED
            ),
            FileVerification(
                "/output.csv", "output", "h2", "h2", VerificationStatus.VERIFIED
            ),
        ]
        # Act
        # Act
        rv = RunVerification(
            session_id="test",
            script_path="/script.py",
            status=VerificationStatus.VERIFIED,
            files=files,
            combined_hash_expected=None,
            combined_hash_current=None,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert len(rv.outputs) == 1


    def test_run_verification_mismatched_files_len_rv_mismatched_files_is_1(self):
        # Arrange
        # Arrange
        # Arrange
        files = [
            FileVerification(
                "/good.csv", "input", "h1", "h1", VerificationStatus.VERIFIED
            ),
            FileVerification(
                "/bad.csv", "output", "h2", "h3", VerificationStatus.MISMATCH
            ),
        ]
        # Act
        # Act
        rv = RunVerification(
            session_id="test",
            script_path="/script.py",
            status=VerificationStatus.MISMATCH,
            files=files,
            combined_hash_expected=None,
            combined_hash_current=None,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert len(rv.mismatched_files) == 1

    def test_run_verification_mismatched_files_rv_mismatched_files_0_path_bad_csv(self):
        # Arrange
        # Arrange
        # Arrange
        files = [
            FileVerification(
                "/good.csv", "input", "h1", "h1", VerificationStatus.VERIFIED
            ),
            FileVerification(
                "/bad.csv", "output", "h2", "h3", VerificationStatus.MISMATCH
            ),
        ]
        # Act
        # Act
        rv = RunVerification(
            session_id="test",
            script_path="/script.py",
            status=VerificationStatus.MISMATCH,
            files=files,
            combined_hash_expected=None,
            combined_hash_current=None,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert rv.mismatched_files[0].path == "/bad.csv"


    def test_run_verification_missing_files_len_rv_missing_files_is_1(self):
        # Arrange
        # Arrange
        # Arrange
        files = [
            FileVerification(
                "/exists.csv", "input", "h1", "h1", VerificationStatus.VERIFIED
            ),
            FileVerification(
                "/missing.csv", "input", "h2", None, VerificationStatus.MISSING
            ),
        ]
        # Act
        # Act
        rv = RunVerification(
            session_id="test",
            script_path="/script.py",
            status=VerificationStatus.MISSING,
            files=files,
            combined_hash_expected=None,
            combined_hash_current=None,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert len(rv.missing_files) == 1

    def test_run_verification_missing_files_rv_missing_files_0_path_missing_csv(self):
        # Arrange
        # Arrange
        # Arrange
        files = [
            FileVerification(
                "/exists.csv", "input", "h1", "h1", VerificationStatus.VERIFIED
            ),
            FileVerification(
                "/missing.csv", "input", "h2", None, VerificationStatus.MISSING
            ),
        ]
        # Act
        # Act
        rv = RunVerification(
            session_id="test",
            script_path="/script.py",
            status=VerificationStatus.MISSING,
            files=files,
            combined_hash_expected=None,
            combined_hash_current=None,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert rv.missing_files[0].path == "/missing.csv"


    def test_run_verification_rerun_level(self):
        """Test RunVerification with rerun level."""
        # Arrange
        # Act
        rv = RunVerification(
            session_id="test",
            script_path="/script.py",
            status=VerificationStatus.VERIFIED,
            files=[],
            combined_hash_expected=None,
            combined_hash_current=None,
            level=VerificationLevel.RERUN,
        )
        # Assert
        assert rv.is_verified_from_scratch is True


class TestChainVerification:
    """Tests for ChainVerification dataclass."""

    def test_chain_verification_creation_cv_target_file_equals_path_to_output_csv(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        cv = ChainVerification(
            target_file="/path/to/output.csv",
            runs=[],
            status=VerificationStatus.VERIFIED,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert cv.target_file == "/path/to/output.csv"

    def test_chain_verification_creation_cv_is_verified_is_true(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        cv = ChainVerification(
            target_file="/path/to/output.csv",
            runs=[],
            status=VerificationStatus.VERIFIED,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert cv.is_verified is True


    def test_chain_verification_with_runs(self):
        """Test ChainVerification with multiple runs."""
        # Arrange
        runs = [
            RunVerification(
                "s1",
                "/p1.py",
                VerificationStatus.VERIFIED,
                [],
                None,
                None,
            ),
            RunVerification(
                "s2",
                "/p2.py",
                VerificationStatus.VERIFIED,
                [],
                None,
                None,
            ),
        ]
        # Act
        cv = ChainVerification(
            target_file="/output.csv",
            runs=runs,
            status=VerificationStatus.VERIFIED,
        )
        # Assert
        assert len(cv.runs) == 2

    def test_chain_verification_failed_runs_len_cv_failed_runs_is_1(self):
        # Arrange
        # Arrange
        # Arrange
        runs = [
            RunVerification(
                "s1",
                "/p1.py",
                VerificationStatus.VERIFIED,
                [],
                None,
                None,
            ),
            RunVerification(
                "s2",
                "/p2.py",
                VerificationStatus.MISMATCH,
                [],
                None,
                None,
            ),
        ]
        # Act
        # Act
        cv = ChainVerification(
            target_file="/output.csv",
            runs=runs,
            status=VerificationStatus.MISMATCH,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert len(cv.failed_runs) == 1

    def test_chain_verification_failed_runs_cv_failed_runs_0_session_id_s2(self):
        # Arrange
        # Arrange
        # Arrange
        runs = [
            RunVerification(
                "s1",
                "/p1.py",
                VerificationStatus.VERIFIED,
                [],
                None,
                None,
            ),
            RunVerification(
                "s2",
                "/p2.py",
                VerificationStatus.MISMATCH,
                [],
                None,
                None,
            ),
        ]
        # Act
        # Act
        cv = ChainVerification(
            target_file="/output.csv",
            runs=runs,
            status=VerificationStatus.MISMATCH,
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert cv.failed_runs[0].session_id == "s2"



class TestVerifyFile:
    """Tests for verify_file function."""

    def test_verify_file_match_result_status_equals_verificationstatus_verified(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import hash_file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        expected_hash = hash_file(test_file)
        # Act
        # Act
        result = verify_file(test_file, expected_hash)
        # Act
        # Assert
        # Assert
        # Assert
        assert result.status == VerificationStatus.VERIFIED

    def test_verify_file_match_result_is_verified_is_true(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import hash_file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        expected_hash = hash_file(test_file)
        # Act
        # Act
        result = verify_file(test_file, expected_hash)
        # Act
        # Assert
        # Assert
        # Assert
        assert result.is_verified is True


    def test_verify_file_mismatch_result_status_equals_verificationstatus_mismatch(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        # Act
        # Act
        result = verify_file(test_file, "wronghash1234567890123456789012")
        # Act
        # Assert
        # Assert
        # Assert
        assert result.status == VerificationStatus.MISMATCH

    def test_verify_file_mismatch_result_is_verified_is_false(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        # Act
        # Act
        result = verify_file(test_file, "wronghash1234567890123456789012")
        # Act
        # Assert
        # Assert
        # Assert
        assert result.is_verified is False


    def test_verify_file_missing_result_status_equals_verificationstatus_missing(self, tmp_path):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = verify_file(tmp_path / "missing.txt", "somehash")
        # Act
        # Assert
        # Assert
        # Assert
        assert result.status == VerificationStatus.MISSING

    def test_verify_file_missing_result_is_verified_is_false(self, tmp_path):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = verify_file(tmp_path / "missing.txt", "somehash")
        # Act
        # Assert
        # Assert
        # Assert
        assert result.is_verified is False

    def test_verify_file_missing_result_current_hash_is_none(self, tmp_path):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = verify_file(tmp_path / "missing.txt", "somehash")
        # Act
        # Assert
        # Assert
        # Assert
        assert result.current_hash is None



# EOF
