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
    def test_is_tuple(self):
        assert isinstance(STAMP_BACKENDS, tuple)

    def test_contains_file(self):
        assert "file" in STAMP_BACKENDS

    def test_contains_rfc3161(self):
        assert "rfc3161" in STAMP_BACKENDS

    def test_contains_zenodo(self):
        assert "zenodo" in STAMP_BACKENDS


# ---------------------------------------------------------------------------
# Stamp dataclass
# ---------------------------------------------------------------------------


class TestStampDataclass:
    def test_to_dict(self):
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
        d = s.to_dict()
        assert d["stamp_id"] == "stamp_abc123"
        assert d["backend"] == "file"
        assert d["run_count"] == 3
        assert d["metadata"] == {"session_ids": ["s1", "s2", "s3"]}

    def test_to_dict_keys(self):
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
        assert keys == expected


# ---------------------------------------------------------------------------
# migrate_add_stamps_table
# ---------------------------------------------------------------------------


class TestMigrateAddStampsTable:
    def test_creates_stamps_table(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "migrate_test.db"
        migrate_add_stamps_table(db_path)
        conn = sqlite3.connect(str(db_path))
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stamps'"
        ).fetchone()
        conn.close()
        assert result is not None

    def test_idempotent(self, tmp_path):
        import sqlite3

        db_path = tmp_path / "migrate_test.db"
        migrate_add_stamps_table(db_path)
        migrate_add_stamps_table(db_path)  # Should not raise
        conn = sqlite3.connect(str(db_path))
        result = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='stamps'"
        ).fetchone()
        conn.close()
        assert result is not None


# ---------------------------------------------------------------------------
# compute_root_hash
# ---------------------------------------------------------------------------


class TestComputeRootHash:
    def test_empty_db_returns_none_hash(self):
        result = compute_root_hash()
        assert result["root_hash"] is None
        assert result["run_count"] == 0
        assert result["session_ids"] == []

    def test_single_successful_run(self):
        _add_successful_run("s1", "abc123")
        result = compute_root_hash()
        assert result["root_hash"] is not None
        assert result["run_count"] == 1
        assert "s1" in result["session_ids"]

    def test_multiple_successful_runs(self):
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        result = compute_root_hash()
        assert result["run_count"] == 2

    def test_running_status_not_included(self):
        db = _db_module.get_db()
        db.add_run("still_running", "/path/script.py")
        # Do NOT call finish_run, so status remains "running"
        result = compute_root_hash()
        assert "still_running" not in result["session_ids"]

    def test_specific_session_ids(self):
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        result = compute_root_hash(session_ids=["s1"])
        assert "s1" in result["session_ids"]
        assert "s2" not in result["session_ids"]

    def test_root_hash_is_deterministic(self):
        _add_successful_run("s1", "abc123")
        r1 = compute_root_hash()
        r2 = compute_root_hash()
        assert r1["root_hash"] == r2["root_hash"]

    def test_root_hash_changes_with_new_run(self):
        _add_successful_run("s1", "abc123")
        r1 = compute_root_hash()
        _add_successful_run("s2", "def456")
        r2 = compute_root_hash()
        assert r1["root_hash"] != r2["root_hash"]


# ---------------------------------------------------------------------------
# stamp
# ---------------------------------------------------------------------------


class TestStamp:
    def test_invalid_backend_raises(self):
        _add_successful_run("s1", "abc123")
        with pytest.raises(ValueError, match="Invalid backend"):
            stamp(backend="nonexistent_backend")

    def test_empty_db_raises(self):
        with pytest.raises(ValueError, match="No runs to stamp"):
            stamp(backend="file")

    def test_file_backend_returns_stamp(self, tmp_path):
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        assert isinstance(s, Stamp)
        assert s.backend == "file"
        assert s.stamp_id.startswith("stamp_")
        assert s.run_count == 1

    def test_file_backend_writes_json(self, tmp_path):
        _add_successful_run("s1", "abc123")
        stamp_dir = tmp_path / "stamps"
        s = stamp(backend="file", output_dir=str(stamp_dir))
        # File should exist
        stamp_file = stamp_dir / f"{s.stamp_id}.json"
        assert stamp_file.exists()

    def test_stamp_stored_in_db(self, tmp_path):
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        stamps = list_stamps()
        assert any(st.stamp_id == s.stamp_id for st in stamps)

    def test_stamp_specific_sessions(self, tmp_path):
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        s = stamp(
            backend="file",
            session_ids=["s1"],
            output_dir=str(tmp_path / "stamps"),
        )
        assert s.run_count == 1
        assert s.metadata is not None
        assert "s1" in s.metadata.get("session_ids", [])

    def test_zenodo_raises_not_implemented(self):
        _add_successful_run("s1", "abc123")
        with pytest.raises(NotImplementedError):
            stamp(backend="zenodo")


# ---------------------------------------------------------------------------
# check_stamp
# ---------------------------------------------------------------------------


class TestCheckStamp:
    def test_no_stamps_returns_not_found(self):
        result = check_stamp()
        assert result["status"] == "not_found"

    def test_check_latest_stamp_matches(self, tmp_path):
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        result = check_stamp()
        assert result["matches"] is True
        assert "stamp" in result
        assert "current_root_hash" in result
        assert "details" in result

    def test_check_specific_stamp_id(self, tmp_path):
        _add_successful_run("s1", "abc123")
        s = stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        result = check_stamp(stamp_id=s.stamp_id)
        assert result["matches"] is True

    def test_check_nonexistent_stamp_id(self):
        result = check_stamp(stamp_id="stamp_nonexistent")
        assert result["status"] == "not_found"

    def test_details_is_list(self, tmp_path):
        _add_successful_run("s1", "abc123")
        stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        result = check_stamp()
        assert isinstance(result["details"], list)


# ---------------------------------------------------------------------------
# list_stamps
# ---------------------------------------------------------------------------


class TestListStamps:
    def test_empty_db_returns_empty_list(self):
        stamps = list_stamps()
        assert stamps == []

    def test_returns_stamp_objects(self, tmp_path):
        _add_successful_run("s1", "abc123")
        stamp(backend="file", output_dir=str(tmp_path / "stamps"))
        stamps = list_stamps()
        assert len(stamps) == 1
        assert isinstance(stamps[0], Stamp)

    def test_multiple_stamps_ordered_newest_first(self, tmp_path):
        _add_successful_run("s1", "abc123")
        _add_successful_run("s2", "def456")
        stamp_dir = str(tmp_path / "stamps")
        s1 = stamp(backend="file", session_ids=["s1"], output_dir=stamp_dir)
        s2 = stamp(backend="file", session_ids=["s1", "s2"], output_dir=stamp_dir)
        stamps = list_stamps()
        assert len(stamps) >= 2
        # Most recent first
        assert stamps[0].stamp_id == s2.stamp_id

    def test_limit_parameter(self, tmp_path):
        _add_successful_run("s1", "abc123")
        stamp_dir = str(tmp_path / "stamps")
        for _ in range(5):
            stamp(backend="file", session_ids=["s1"], output_dir=stamp_dir)
        stamps = list_stamps(limit=3)
        assert len(stamps) <= 3


# EOF
