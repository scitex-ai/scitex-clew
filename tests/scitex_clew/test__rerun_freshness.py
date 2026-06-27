#!/usr/bin/env python3
"""Tests for scitex_clew._rerun_freshness and the skip_unchanged param of rerun_dag.

Covers:
- _is_session_fresh: unchanged inputs+script → True
- _is_session_fresh: mutated input → False
- _is_session_fresh: missing input → False
- _is_session_fresh: changed script → False
- _is_session_fresh: no script_hash recorded → False
- rerun_dag(skip_unchanged=True): fresh session → level=CACHE, not verified_from_scratch
- rerun_dag(skip_unchanged=True): mutated input → _execute_script IS called
- rerun_dag(skip_unchanged=False): unchanged session → _execute_script IS called
"""

from __future__ import annotations

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._chain import VerificationLevel, VerificationStatus
from scitex_clew._rerun_freshness import _is_session_fresh, _skipped_result


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Inject a fresh temp DB and reset global state after each test."""
    db_path = tmp_path / "freshness_test.db"
    set_db(db_path)
    yield
    _db_module._DB_INSTANCE = None


def _build_session(db, tmp_path, session_id, script_content="# script"):
    """Build a fully-recorded session with real files in the DB.

    Returns (script_path, input_path, output_path).
    """
    script = tmp_path / f"{session_id}_script.py"
    script.write_text(script_content)

    input_file = tmp_path / f"{session_id}_input.csv"
    input_file.write_text("col1,col2\n1,2\n")

    output_file = tmp_path / f"{session_id}_output.csv"
    output_file.write_text("result\n42\n")

    from scitex_clew._hash import hash_file

    script_h = hash_file(str(script))
    input_h = hash_file(str(input_file))
    output_h = hash_file(str(output_file))

    db.add_run(session_id, str(script), script_hash=script_h)
    db.add_file_hash(session_id, str(input_file), input_h, "input")
    db.add_file_hash(session_id, str(output_file), output_h, "output")
    db.finish_run(session_id, status="success")

    return script, input_file, output_file


# ---------------------------------------------------------------------------
# _is_session_fresh
# ---------------------------------------------------------------------------


class TestIsSessionFresh:
    def test_unchanged_inputs_and_script_returns_true(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        _build_session(db, tmp_path, "sess_a")
        # Act
        result = _is_session_fresh("sess_a")
        # Assert
        assert result is True

    def test_mutated_input_returns_false(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        script, input_file, output_file = _build_session(db, tmp_path, "sess_b")
        input_file.write_text("col1,col2\n99,99\n")
        # Act
        result = _is_session_fresh("sess_b")
        # Assert
        assert result is False

    def test_missing_input_returns_false(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        script, input_file, output_file = _build_session(db, tmp_path, "sess_c")
        input_file.unlink()
        # Act
        result = _is_session_fresh("sess_c")
        # Assert
        assert result is False

    def test_changed_script_returns_false(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        script, input_file, output_file = _build_session(db, tmp_path, "sess_d")
        script.write_text("# modified script\nprint('changed')\n")
        # Act
        result = _is_session_fresh("sess_d")
        # Assert
        assert result is False

    def test_missing_script_file_returns_false(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        script, input_file, output_file = _build_session(db, tmp_path, "sess_e")
        script.unlink()
        # Act
        result = _is_session_fresh("sess_e")
        # Assert
        assert result is False

    def test_no_script_hash_recorded_returns_false(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        script = tmp_path / "no_hash_script.py"
        script.write_text("# no hash")
        # Add run WITHOUT script_hash (None)
        db.add_run("sess_f", str(script), script_hash=None)
        db.finish_run("sess_f", status="success")
        # Act
        result = _is_session_fresh("sess_f")
        # Assert
        assert result is False

    def test_nonexistent_session_returns_false(self, tmp_path):
        # Arrange
        # (no session created)
        # Act
        result = _is_session_fresh("nonexistent_xyz")
        # Assert
        assert result is False

    def test_session_with_no_inputs_and_valid_script_returns_true(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        script = tmp_path / "no_input_script.py"
        script.write_text("# no inputs")

        from scitex_clew._hash import hash_file

        script_h = hash_file(str(script))
        db.add_run("sess_g", str(script), script_hash=script_h)
        db.finish_run("sess_g", status="success")
        # Act
        result = _is_session_fresh("sess_g")
        # Assert
        assert result is True


# ---------------------------------------------------------------------------
# _skipped_result
# ---------------------------------------------------------------------------


class TestSkippedResult:
    def test_level_is_cache_not_rerun(self, tmp_path):
        # Arrange
        # Act
        result = _skipped_result("s1", "/path/script.py")
        # Assert
        assert result.level == VerificationLevel.CACHE

    def test_status_is_verified(self, tmp_path):
        # Arrange
        # Act
        result = _skipped_result("s1", "/path/script.py")
        # Assert
        assert result.status == VerificationStatus.VERIFIED

    def test_is_verified_from_scratch_is_false(self, tmp_path):
        # Arrange
        # Act
        result = _skipped_result("s1", "/path/script.py")
        # Assert
        assert result.is_verified_from_scratch is False

    def test_session_id_preserved(self, tmp_path):
        # Arrange
        # Act
        result = _skipped_result("my_session", "/path/script.py")
        # Assert
        assert result.session_id == "my_session"


# ---------------------------------------------------------------------------
# rerun_dag(skip_unchanged=...) integration
# ---------------------------------------------------------------------------


class TestRerunDagSkipUnchanged:
    """Integration tests: rerun_dag with the skip_unchanged opt-in flag."""

    def test_unchanged_session_result_level_is_cache(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        from scitex_clew._rerun import rerun_dag

        _script, _inp, output_file = _build_session(db, tmp_path, "rdag_fresh_1")
        # Act
        result = rerun_dag(targets=[str(output_file)], skip_unchanged=True)
        # Assert
        assert result.runs[0].level == VerificationLevel.CACHE

    def test_unchanged_session_is_not_verified_from_scratch(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        from scitex_clew._rerun import rerun_dag

        _script, _inp, output_file = _build_session(db, tmp_path, "rdag_fresh_2")
        # Act
        result = rerun_dag(targets=[str(output_file)], skip_unchanged=True)
        # Assert
        assert not result.runs[0].is_verified_from_scratch

    def test_mutated_input_falls_through_to_rerun_level_is_rerun(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        from scitex_clew._rerun import rerun_dag

        _script, inp, output_file = _build_session(db, tmp_path, "rdag_mut_1")
        # Mutate input AFTER recording — freshness check will now fail
        inp.write_text("col1,col2\n99,99\n")
        # Act — skip_unchanged=True but session is NOT fresh → must fall through
        result = rerun_dag(targets=[str(output_file)], skip_unchanged=True)
        # Assert: level=RERUN proves the real rerun path was entered, not skipped
        assert result.runs[0].level == VerificationLevel.RERUN

    def test_default_false_unchanged_session_level_is_rerun(self, tmp_path):
        # Arrange
        db = _db_module.get_db()
        from scitex_clew._rerun import rerun_dag

        _script, _inp, output_file = _build_session(db, tmp_path, "rdag_def_1")
        # Act — skip_unchanged=False (default) must always attempt rerun
        result = rerun_dag(targets=[str(output_file)], skip_unchanged=False)
        # Assert: level=RERUN proves the subprocess path was entered even for fresh session
        assert result.runs[0].level == VerificationLevel.RERUN


# EOF
