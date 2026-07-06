#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_clew._db._connect — the stdlib-only connect helper.

Real SQLite databases on tmp paths; no mocks. Verifies that the mirrored
scitex-db PRAGMA tuning (busy_timeout / WAL / synchronous) is applied and
that concurrent writers retry on a lock instead of failing instantly.
"""

import sqlite3
import threading
import time

from scitex_clew._db._connect import connect


def test_writable_connect_returns_sqlite_connection_instance(tmp_path):
    # Arrange
    db_path = tmp_path / "instance.db"
    # Act
    conn = connect(db_path)
    # Assert
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_writable_connect_sets_busy_timeout_default_value(tmp_path):
    # Arrange
    db_path = tmp_path / "busy_writable.db"
    conn = connect(db_path)
    # Act
    busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    conn.close()
    # Assert
    assert busy_timeout == 300000


def test_writable_connect_enables_wal_journal_mode(tmp_path):
    # Arrange
    db_path = tmp_path / "wal_writable.db"
    conn = connect(db_path)
    # Act
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    # Assert
    assert journal_mode == "wal"


def test_writable_connect_sets_synchronous_normal_level(tmp_path):
    # Arrange
    db_path = tmp_path / "sync_writable.db"
    conn = connect(db_path)
    # Act
    synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
    conn.close()
    # Assert
    assert synchronous == 1  # NORMAL


def test_read_only_connect_still_sets_busy_timeout(tmp_path):
    # Arrange
    db_path = tmp_path / "busy_read_only.db"
    connect(db_path).close()  # create the file first
    conn = connect(db_path, read_only=True)
    # Act
    busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    conn.close()
    # Assert
    assert busy_timeout == 300000


def test_read_only_connect_skips_wal_journal_mode(tmp_path):
    # Arrange
    db_path = tmp_path / "read_only_journal.db"
    conn = connect(db_path, read_only=True)
    # Act
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    # Assert
    assert journal_mode != "wal"


def test_concurrent_writers_retry_on_locked_database(tmp_path):
    # Arrange
    db_path = tmp_path / "concurrent_writers.db"
    setup = connect(db_path)
    setup.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    setup.commit()
    setup.close()
    lock_held = threading.Event()

    def _hold_write_lock_briefly():
        # Each sqlite3 connection must stay in its creating thread.
        holder = connect(db_path)
        holder.execute("INSERT INTO t (v) VALUES ('holder')")  # acquires lock
        lock_held.set()
        time.sleep(0.3)
        holder.commit()
        holder.close()

    holder_thread = threading.Thread(target=_hold_write_lock_briefly)
    holder_thread.start()
    lock_held.wait(timeout=5)  # ensure the holder owns the write lock now
    conn_b = connect(db_path, timeout=0.0)  # disable driver-level retry
    conn_b.execute("PRAGMA busy_timeout = 5000")  # bounded C-level retry window
    # Act — B's write must WAIT for the holder then succeed, not raise "locked"
    conn_b.execute("INSERT INTO t (v) VALUES ('b')")
    conn_b.commit()
    holder_thread.join()
    row_count = conn_b.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    conn_b.close()
    # Assert
    assert row_count == 2


# EOF
