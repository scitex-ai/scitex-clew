#!/usr/bin/env python3
"""Deferred writes on a project-scoped store (``scitex_clew._db._deferred``).

A real ``VerificationDB`` on a real PostgreSQL store (the autouse
``isolated_store`` fixture). No mocks: queued rows are observed through the
store itself and through a SECOND, independent connection.
"""

from __future__ import annotations

import pytest
from scitex_clew._db import get_db
from scitex_clew._db._core import VerificationDB
from scitex_clew._db._deferred import MAX_PENDING, flush_all_deferred


def _row(i: int) -> dict:
    return {
        "session_id": "sess_deferred",
        "file_path": f"/data/f{i:04d}.txt",
        "role": "input",
        "hash": f"{i:064x}",
        "recorded_at": f"2026-11-18T00:00:{i % 60:02d}.{i:06d}",
    }


def _other_connection_paths(project: str) -> set[str]:
    """What a DIFFERENT process would see: a fresh connection, same scope."""
    other = VerificationDB()
    try:
        return {
            r.values["file_path"]
            for r in other._file_hashes.rows()
            if r.values.get("project") == project
        }
    finally:
        other.close()


class TestQueue:
    def test_deferred_put_is_not_committed_before_a_flush(self):
        # Arrange
        db = get_db()
        # Act
        db._file_hashes.defer_put(_row(1))
        # Assert
        assert _other_connection_paths(db._file_hashes.project) == set()

    def test_a_read_in_this_process_sees_queued_rows(self):
        # Arrange
        db = get_db()
        db._file_hashes.defer_put(_row(1))
        # Act
        seen = db.get_file_hashes("sess_deferred")
        # Assert
        assert seen == {"/data/f0001.txt": f"{1:064x}"}

    def test_flush_commits_every_queued_row(self):
        # Arrange
        db = get_db()
        for i in range(5):
            db._file_hashes.defer_put(_row(i))
        # Act
        written = db._file_hashes.flush()
        # Assert
        assert (written, len(_other_connection_paths(db._file_hashes.project))) == (
            5,
            5,
        )

    def test_queue_is_empty_after_flush(self):
        # Arrange
        db = get_db()
        db._file_hashes.defer_put(_row(1))
        # Act
        db._file_hashes.flush()
        # Assert
        assert db._file_hashes.pending == 0

    def test_queue_flushes_itself_at_max_pending(self):
        # Arrange
        db = get_db()
        # Act
        for i in range(MAX_PENDING):
            db._file_hashes.defer_put(_row(i))
        # Assert
        assert db._file_hashes.pending == 0

    def test_close_writes_queued_rows(self):
        # Arrange
        db = VerificationDB()
        project = db._file_hashes.project
        db._file_hashes.defer_put(_row(7))
        # Act
        db.close()
        # Assert
        assert _other_connection_paths(project) == {"/data/f0007.txt"}

    def test_exit_flush_writes_queued_rows(self):
        # Arrange
        db = get_db()
        db._file_hashes.defer_put(_row(3))
        # Act
        flush_all_deferred()
        # Assert
        assert _other_connection_paths(db._file_hashes.project) == {"/data/f0003.txt"}


class TestOrderAndContent:
    def test_later_queued_put_of_same_row_wins(self):
        # Arrange
        db = get_db()
        first, second = _row(1), {**_row(1), "hash": "f" * 64}
        db._file_hashes.defer_put(first)
        db._file_hashes.defer_put(second)
        # Act
        stored = db.get_file_hashes("sess_deferred")
        # Assert
        assert stored == {"/data/f0001.txt": "f" * 64}

    def test_immediate_write_after_queued_one_keeps_order(self):
        # Arrange
        db = get_db()
        db._file_hashes.defer_put(_row(1))
        # Act
        db.add_file_hash("sess_deferred", "/data/f0001.txt", "e" * 64, "input")
        # Assert
        assert db.get_file_hashes("sess_deferred") == {"/data/f0001.txt": "e" * 64}

    @pytest.mark.parametrize("defer", [False, True])
    def test_deferred_row_equals_immediate_row(self, defer):
        # Arrange
        db = get_db()
        expected = {
            "file_path": "/data/x.csv",
            "hash": "a" * 64,
            "recorded_at": "2026-11-18T01:02:03.000004",
            "role": "input",
            "derived_from": None,
            "external": {"via": None, "size": 3, "mtime": 1.0},
            "size_bytes": 3,
        }
        # Act
        db.add_file_hash(
            "sess_eq",
            "/data/x.csv",
            "a" * 64,
            "input",
            size_bytes=3,
            external={"via": None, "size": 3, "mtime": 1.0},
            defer=defer,
            recorded_at="2026-11-18T01:02:03.000004",
        )
        # Assert
        assert db.get_file_records("sess_eq") == [expected]


# EOF
