#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the transparent db.sqlite -> clew.db auto-rename migration.

Real DBs, no mocks. The correctness-critical scenario is the WAL sidecar
case: a predecessor ``db.sqlite`` may carry an uncheckpointed ``-wal``
holding committed-but-not-yet-checkpointed rows, and a naive rename of
only the main file would lose that data. These tests seed exactly that
state and assert the migration preserves it (checkpoint-then-rename).
"""

import os
import shutil
import sqlite3
import warnings
from pathlib import Path

from scitex_clew._db._core import _default_db_path, resolve_db_path


def _seed_wal_predecessor(tmp_path: Path, runtime_dir: Path) -> Path:
    """Seed ``runtime_dir/db.sqlite`` with a row that lives only in the -wal.

    Builds the DB in a staging dir with autocheckpoint disabled, commits a
    row (which lands in the ``-wal``), then copies the still-uncheckpointed
    main + ``-wal`` + ``-shm`` files into ``runtime_dir`` and only then
    closes the staging connection. The runtime copies therefore hold the
    committed row in the ``-wal`` with no connection open on them.
    """
    stage = tmp_path / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    stage_db = stage / "db.sqlite"
    conn = sqlite3.connect(str(stage_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE t (v TEXT)")
    conn.execute("INSERT INTO t VALUES ('walonly')")
    conn.commit()
    runtime_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(stage_db) + suffix)
        if src.exists():
            shutil.copy2(src, runtime_dir / ("db.sqlite" + suffix))
    conn.close()
    return runtime_dir / "db.sqlite"


def _migrate(project_root: Path) -> Path:
    """Run the default-path resolver (which performs the migration)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return _default_db_path(project_root)


class TestWalPredecessorMigration:
    """A runtime/db.sqlite with uncheckpointed -wal data migrates safely."""

    def test_wal_predecessor_migrates_creating_clew_db_file(self, tmp_path):
        # Arrange
        runtime = tmp_path / ".scitex" / "clew" / "runtime"
        _seed_wal_predecessor(tmp_path, runtime)
        # Act
        _migrate(tmp_path)
        # Assert
        assert (runtime / "clew.db").exists()

    def test_wal_predecessor_migration_preserves_wal_only_row(self, tmp_path):
        # Arrange
        runtime = tmp_path / ".scitex" / "clew" / "runtime"
        _seed_wal_predecessor(tmp_path, runtime)
        # Act
        new = _migrate(tmp_path)
        conn = sqlite3.connect(str(new))
        try:
            value = conn.execute("SELECT v FROM t").fetchone()[0]
        finally:
            conn.close()
        # Assert
        assert value == "walonly"

    def test_wal_predecessor_migration_removes_legacy_db_sqlite(self, tmp_path):
        # Arrange
        runtime = tmp_path / ".scitex" / "clew" / "runtime"
        _seed_wal_predecessor(tmp_path, runtime)
        # Act
        _migrate(tmp_path)
        # Assert
        assert not (runtime / "db.sqlite").exists()

    def test_wal_predecessor_migration_leaves_no_stale_wal_sidecar(self, tmp_path):
        # Arrange
        runtime = tmp_path / ".scitex" / "clew" / "runtime"
        _seed_wal_predecessor(tmp_path, runtime)
        # Act
        _migrate(tmp_path)
        # Assert
        assert not (runtime / "db.sqlite-wal").exists()


class TestLegacyFlatPredecessorMigration:
    """A legacy flat .scitex/clew/db.sqlite migrates to runtime/clew.db."""

    def _seed_flat(self, tmp_path: Path) -> Path:
        clew_dir = tmp_path / ".scitex" / "clew"
        clew_dir.mkdir(parents=True, exist_ok=True)
        flat = clew_dir / "db.sqlite"
        conn = sqlite3.connect(str(flat))
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('flat')")
        conn.commit()
        conn.close()
        return flat

    def test_legacy_flat_predecessor_migrates_creating_clew_db(self, tmp_path):
        # Arrange
        self._seed_flat(tmp_path)
        # Act
        new = _migrate(tmp_path)
        # Assert
        assert new == tmp_path / ".scitex" / "clew" / "runtime" / "clew.db"

    def test_legacy_flat_predecessor_migration_preserves_row(self, tmp_path):
        # Arrange
        self._seed_flat(tmp_path)
        # Act
        new = _migrate(tmp_path)
        conn = sqlite3.connect(str(new))
        try:
            value = conn.execute("SELECT v FROM t").fetchone()[0]
        finally:
            conn.close()
        # Assert
        assert value == "flat"

    def test_legacy_flat_predecessor_is_removed_after_migration(self, tmp_path):
        # Arrange
        flat = self._seed_flat(tmp_path)
        # Act
        _migrate(tmp_path)
        # Assert
        assert not flat.exists()


class TestFreshAndExplicitResolution:
    """A fresh project defaults to clew.db; an explicit override is honored."""

    def test_fresh_project_default_path_is_runtime_clew_db(self, tmp_path):
        # Arrange
        expected = tmp_path / ".scitex" / "clew" / "runtime" / "clew.db"
        # Act
        resolved = _default_db_path(tmp_path)
        # Assert
        assert resolved == expected

    def test_fresh_project_default_creates_no_predecessor_file(self, tmp_path):
        # Arrange
        legacy = tmp_path / ".scitex" / "clew" / "runtime" / "db.sqlite"
        # Act
        _default_db_path(tmp_path)
        # Assert
        assert not legacy.exists()

    def test_explicit_env_var_db_path_is_honored_unchanged(self, tmp_path):
        # Arrange
        override = tmp_path / "custom" / "elsewhere.db"
        previous = os.environ.get("SCITEX_CLEW_DB_PATH")
        os.environ["SCITEX_CLEW_DB_PATH"] = str(override)
        # Act
        try:
            resolved, _tier = resolve_db_path()
        finally:
            if previous is None:
                del os.environ["SCITEX_CLEW_DB_PATH"]
            else:
                os.environ["SCITEX_CLEW_DB_PATH"] = previous
        # Assert
        assert resolved == override


# EOF
