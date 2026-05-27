#!/usr/bin/env python3
"""Tests for scitex_clew._stamp module."""

from __future__ import annotations

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._stamp import (
    STAMP_BACKENDS,
    Stamp,
    check_stamp,
    compute_root_hash,
    list_stamps,
    migrate_add_stamps_table,
    stamp,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Inject a temp DB for each test."""
    db_path = tmp_path / "stamp_test.db"
    set_db(db_path)
    yield
    _db_module._DB_INSTANCE = None


def _add_successful_run(session_id: str, combined_hash: str = "deadbeef"):
    """Helper: insert a run with status=success and combined_hash."""
    db = _db_module.get_db()
    db.add_run(session_id, "/path/script.py")
    db.finish_run(session_id, status="success", combined_hash=combined_hash)


# ---------------------------------------------------------------------------
# STAMP_BACKENDS constant
# ---------------------------------------------------------------------------


class TestStampBackends:
    def test_is_tuple_stamp_backends_is_tuple(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert isinstance(STAMP_BACKENDS, tuple)

    def test_contains_file_file_in_stamp_backends(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "file" in STAMP_BACKENDS

    def test_contains_rfc3161_rfc3161_in_stamp_backends(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "rfc3161" in STAMP_BACKENDS

    def test_contains_zenodo_zenodo_in_stamp_backends(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "zenodo" in STAMP_BACKENDS


# ---------------------------------------------------------------------------
# Stamp dataclass
# ---------------------------------------------------------------------------


class TestStampDataclass:
    def test_to_dict_d_stamp_id_stamp_abc123(self):
        # Arrange
        # Arrange
        # Arrange
        s = Stamp(
            stamp_id="stamp_abc123",
            root_hash="deadbeef" * 8,
            timestamp="2026-01-01T00:00:00+00:00",
            backend="file",
            service_url="/path/to/stamp.json",
            response_token=None,
            run_count=3,
            metadata={"session_ids": ["s1", "s2", "s3"]},
        )
        # Act
        # Act
        d = s.to_dict()
        # Act
        # Assert
        # Assert
        # Assert
        assert d["stamp_id"] == "stamp_abc123"

    def test_to_dict_d_backend_file(self):
        # Arrange
        # Arrange
        # Arrange
        s = Stamp(
            stamp_id="stamp_abc123",
            root_hash="deadbeef" * 8,
            timestamp="2026-01-01T00:00:00+00:00",
            backend="file",
            service_url="/path/to/stamp.json",
            response_token=None,
            run_count=3,
            metadata={"session_ids": ["s1", "s2", "s3"]},
        )
        # Act
        # Act
        d = s.to_dict()
        # Act
        # Assert
        # Assert
        # Assert
        assert d["backend"] == "file"

    def test_to_dict_d_run_count_3(self):
        # Arrange
        # Arrange
        # Arrange
        s = Stamp(
            stamp_id="stamp_abc123",
            root_hash="deadbeef" * 8,
            timestamp="2026-01-01T00:00:00+00:00",
            backend="file",
            service_url="/path/to/stamp.json",
            response_token=None,
            run_count=3,
            metadata={"session_ids": ["s1", "s2", "s3"]},
        )
        # Act
        # Act
        d = s.to_dict()
        # Act
        # Assert
        # Assert
        # Assert
        assert d["run_count"] == 3

    def test_to_dict_d_metadata_session_ids_s1_s2_s3(self):
        # Arrange
        # Arrange
        # Arrange
        s = Stamp(
            stamp_id="stamp_abc123",
            root_hash="deadbeef" * 8,
            timestamp="2026-01-01T00:00:00+00:00",
            backend="file",
            service_url="/path/to/stamp.json",
            response_token=None,
            run_count=3,
            metadata={"session_ids": ["s1", "s2", "s3"]},
        )
        # Act
        # Act
        d = s.to_dict()
        # Act
        # Assert
        # Assert
        # Assert
        assert d["metadata"] == {"session_ids": ["s1", "s2", "s3"]}


    def test_to_dict_keys(self):
        # Arrange
        # Arrange
        s = Stamp(
            stamp_id="x",
            root_hash="y",
            timestamp="t",
            backend="file",
            service_url=None,
            response_token=None,
            run_count=0,
        )
        keys = set(s.to_dict().keys())
        # Act
        # Act
        expected = {
            "stamp_id",
            "root_hash",
            "timestamp",
            "backend",
            "service_url",
            "response_token",
            "run_count",
            "metadata",
        }
        # Assert
        # Assert
        assert keys == expected


# ---------------------------------------------------------------------------
# migrate_add_stamps_table
# ---------------------------------------------------------------------------


class TestMigrateAddStampsTable:
    def test_creates_stamps_table(self, tmp_path):
        # Arrange
        # Arrange
        import sqlite3

        db_path = tmp_path / "migrate_test.db"
        migrate_add_stamps_table(db_path)
        conn = sqlite3.connect(str(db_path))
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stamps'"
        ).fetchone()
        # Act
        # Act
        conn.close()
        # Assert
        # Assert
        assert result is not None

    def test_idempotent_result_is_not_none(self, tmp_path):
        # Arrange
        # Arrange
        import sqlite3

        db_path = tmp_path / "migrate_test.db"
        migrate_add_stamps_table(db_path)
        migrate_add_stamps_table(db_path)  # Should not raise
        conn = sqlite3.connect(str(db_path))
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stamps'"
        ).fetchone()
        # Act
        # Act
        conn.close()
        # Assert
        # Assert
        assert result is not None


# ---------------------------------------------------------------------------
# compute_root_hash
# ---------------------------------------------------------------------------


class TestComputeRootHash:
    def test_empty_db_returns_none_hash_result_root_hash_is_none(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = compute_root_hash()
        # Act
        # Assert
        # Assert
        # Assert
        assert result["root_hash"] is None

    def test_empty_db_returns_none_hash_result_run_count_0(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = compute_root_hash()
        # Act
        # Assert
        # Assert
        # Assert
        assert result["run_count"] == 0

    def test_empty_db_returns_none_hash_result_session_ids(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = compute_root_hash()
        # Act
        # Assert
        # Assert
        # Assert
        assert result["session_ids"] == []


    def test_single_successful_run_result_root_hash_is_not_none(self):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        # Act
        # Act
        result = compute_root_hash()
        # Act
        # Assert
        # Assert
        # Assert
        assert result["root_hash"] is not None

    def test_single_successful_run_result_run_count_1(self):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        # Act
        # Act
        result = compute_root_hash()
        # Act
        # Assert
        # Assert
        # Assert
        assert result["run_count"] == 1

    def test_single_successful_run_s1_in_result_session_ids(self):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        # Act
        # Act
        result = compute_root_hash()
        # Act
        # Assert
        # Assert
        # Assert
        assert "s1" in result["session_ids"]


    def test_multiple_successful_runs(self):
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        # Act
        # Act
        result = compute_root_hash()
        # Assert
        # Assert
        assert result["run_count"] == 2

    def test_running_status_not_included(self):
        # Arrange
        # Arrange
        db = _db_module.get_db()
        db.add_run("still_running", "/path/script.py")
        # Do NOT call finish_run, so status remains "running"
        # Act
        # Act
        result = compute_root_hash()
        # Assert
        # Assert
        assert "still_running" not in result["session_ids"]

    def test_specific_session_ids_s1_in_result_session_ids(self):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        # Act
        # Act
        result = compute_root_hash(session_ids=["s1"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "s1" in result["session_ids"]

    def test_specific_session_ids_s2_not_in_result_session_ids(self):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        # Act
        # Act
        result = compute_root_hash(session_ids=["s1"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "s2" not in result["session_ids"]


    def test_root_hash_is_deterministic(self):
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        r1 = compute_root_hash()
        # Act
        # Act
        r2 = compute_root_hash()
        # Assert
        # Assert
        assert r1["root_hash"] == r2["root_hash"]

    def test_root_hash_changes_with_new_run(self):
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        r1 = compute_root_hash()
        _add_successful_run("s2", "def456")
        # Act
        # Act
        r2 = compute_root_hash()
        # Assert
        # Assert
        assert r1["root_hash"] != r2["root_hash"]


# ---------------------------------------------------------------------------
# stamp
# ---------------------------------------------------------------------------


class TestStamp:
    def test_invalid_backend_raises(self):
        # Arrange
        # Act
        # Arrange
        # Act
        _add_successful_run("s1", "abc123")
        # Assert
        # Assert
        with pytest.raises(ValueError, match="Invalid backend"):
            stamp(backend="nonexistent_backend")

    def test_empty_db_raises(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        with pytest.raises(ValueError, match="No runs to stamp"):
            stamp(backend="file")

    def test_file_backend_returns_stamp_s_is_stamp(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        # Act
        # Act
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(s, Stamp)

    def test_file_backend_returns_stamp_s_backend_equals_file(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        # Act
        # Act
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Assert
        # Assert
        # Assert
        assert s.backend == "file"

    def test_file_backend_returns_stamp_s_stamp_id_startswith_stamp(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        # Act
        # Act
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Assert
        # Assert
        # Assert
        assert s.stamp_id.startswith("stamp_")

    def test_file_backend_returns_stamp_s_run_count_equals_n_1(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        # Act
        # Act
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Assert
        # Assert
        # Assert
        assert s.run_count == 1


    def test_file_backend_writes_json(self, tmp_path):
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        stamp_dir = tmp_path / "stamps"
        s = stamp(backend="file", output_dir=str(stamp_dir))
        # File should exist
        # Act
        # Act
        stamp_file = stamp_dir / f"{s.stamp_id}.json"
        # Assert
        # Assert
        assert stamp_file.exists()

    def test_stamp_stored_in_db(self, tmp_path):
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Act
        stamps = list_stamps()
        # Assert
        # Assert
        assert any(st.stamp_id == s.stamp_id for st in stamps)

    def test_stamp_specific_sessions_s_run_count_equals_n_1(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        # Act
        # Act
        s = stamp(
            backend="file",
            session_ids=["s1"],
            output_dir=str(tmp_path / "stamps"),
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert s.run_count == 1

    def test_stamp_specific_sessions_s_metadata_is_not_none(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        # Act
        # Act
        s = stamp(
            backend="file",
            session_ids=["s1"],
            output_dir=str(tmp_path / "stamps"),
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert s.metadata is not None

    def test_stamp_specific_sessions_s1_in_s_metadata_get_session_ids(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        # Act
        # Act
        s = stamp(
            backend="file",
            session_ids=["s1"],
            output_dir=str(tmp_path / "stamps"),
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert "s1" in s.metadata.get("session_ids", [])


    def test_zenodo_raises_not_implemented(self):
        # Arrange
        # Act
        # Arrange
        # Act
        _add_successful_run("s1", "abc123")
        # Assert
        # Assert
        with pytest.raises(NotImplementedError):
            stamp(backend="zenodo")


# ---------------------------------------------------------------------------
# check_stamp
# ---------------------------------------------------------------------------


class TestCheckStamp:
    def test_no_stamps_returns_not_found(self):
        # Arrange
        # Act
        # Arrange
        # Act
        result = check_stamp()
        # Assert
        # Assert
        assert result["status"] == "not_found"

    def test_check_latest_stamp_matches_result_matches_is_true(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Act
        result = check_stamp()
        # Act
        # Assert
        # Assert
        # Assert
        assert result["matches"] is True

    def test_check_latest_stamp_matches_stamp_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Act
        result = check_stamp()
        # Act
        # Assert
        # Assert
        # Assert
        assert "stamp" in result

    def test_check_latest_stamp_matches_current_root_hash_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Act
        result = check_stamp()
        # Act
        # Assert
        # Assert
        # Assert
        assert "current_root_hash" in result

    def test_check_latest_stamp_matches_details_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Act
        result = check_stamp()
        # Act
        # Assert
        # Assert
        # Assert
        assert "details" in result


    def test_check_specific_stamp_id(self, tmp_path):
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Act
        result = check_stamp(stamp_id=s.stamp_id)
        # Assert
        # Assert
        assert result["matches"] is True

    def test_check_nonexistent_stamp_id(self):
        # Arrange
        # Act
        # Arrange
        # Act
        result = check_stamp(stamp_id="stamp_nonexistent")
        # Assert
        # Assert
        assert result["status"] == "not_found"

    def test_details_is_list(self, tmp_path):
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Act
        result = check_stamp()
        # Assert
        # Assert
        assert isinstance(result["details"], list)


# ---------------------------------------------------------------------------
# list_stamps
# ---------------------------------------------------------------------------


class TestListStamps:
    def test_empty_db_returns_empty_list(self):
        # Arrange
        # Act
        # Arrange
        # Act
        stamps = list_stamps()
        # Assert
        # Assert
        assert stamps == []

    def test_returns_stamp_objects_len_stamps_is_1(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Act
        stamps = list_stamps()
        # Act
        # Assert
        # Assert
        # Assert
        assert len(stamps) == 1

    def test_returns_stamp_objects_isinstance_stamps_0_stamp(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        # Act
        # Act
        stamps = list_stamps()
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(stamps[0], Stamp)


    def test_multiple_stamps_ordered_newest_first_len_stamps_2(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        stamp_dir = str(tmp_path / "stamps")
        s1 = stamp(backend="file", session_ids=["s1"], output_dir=stamp_dir)
        s2 = stamp(backend="file", session_ids=["s1", "s2"], output_dir=stamp_dir)
        # Act
        # Act
        stamps = list_stamps()
        # Act
        # Assert
        # Assert
        # Assert
        assert len(stamps) >= 2

    def test_multiple_stamps_ordered_newest_first_stamps_0_stamp_id_s2_stamp_id(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        stamp_dir = str(tmp_path / "stamps")
        s1 = stamp(backend="file", session_ids=["s1"], output_dir=stamp_dir)
        s2 = stamp(backend="file", session_ids=["s1", "s2"], output_dir=stamp_dir)
        # Act
        # Act
        stamps = list_stamps()
        # Act
        # Assert
        # Assert
        # Assert
        assert stamps[0].stamp_id == s2.stamp_id


    def test_limit_parameter_len_stamps_3(self, tmp_path):
        # Arrange
        # Arrange
        _add_successful_run("s1", "abc123")
        stamp_dir = str(tmp_path / "stamps")
        for _ in range(5):
            stamp(backend="file", session_ids=["s1"], output_dir=stamp_dir)
        # Act
        # Act
        stamps = list_stamps(limit=3)
        # Assert
        # Assert
        assert len(stamps) <= 3


# EOF
