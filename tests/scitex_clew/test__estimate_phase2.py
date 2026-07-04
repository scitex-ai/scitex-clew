#!/usr/bin/env python3
# Timestamp: "2026-06-27 (clew-feature-impl)"
# File: tests/scitex_clew/test__estimate_phase2.py
"""Tests for Phase 2 additions to scitex_clew._estimate.

Coverage:
  (h) schema migration adds size_bytes column to pre-existing DB without data loss
  (i) size_bytes populated on record_output via SessionTracker
  (j) typical_output_bytes is median of per-run total output bytes
  (k) missing size_bytes data yields None — no fabrication
  (l) cached-intermediate hint fires when inputs exist as prior outputs
  (m) typical_output_bytes None in cold-start result

All test DBs are built via the package DB API (no raw SQL fixtures).
No mocks used.
PA-307: one assertion per test, with Arrange/Act/Assert markers.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytest

from scitex_clew import VerificationDB
from scitex_clew._estimate import (
    EstimateResult,
    _build_cold_start,
    _cached_intermediate_hints,
    _typical_output_bytes,
    estimate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> VerificationDB:
    """Create an isolated VerificationDB in a temp directory."""
    return VerificationDB(tmp_path / "test_p2.db")


def _iso(dt: datetime) -> str:
    """Format a datetime as the ISO-8601 string the DB stores."""
    return dt.isoformat()


def _add_completed_run(
    db: VerificationDB,
    session_id: str,
    script_path: str,
    script_hash: str,
    duration_seconds: float,
    status: str = "success",
) -> None:
    """Add a completed run with the given wall-clock duration."""
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=duration_seconds)
    db.add_run(session_id, script_path, script_hash=script_hash)
    db.finish_run(session_id, status=status)
    with db._connect() as conn:
        conn.execute(
            "UPDATE runs SET started_at=?, finished_at=? WHERE session_id=?",
            (_iso(start), _iso(end), session_id),
        )


# ---------------------------------------------------------------------------
# (h) Schema migration — pre-existing DB gains size_bytes without data loss
# ---------------------------------------------------------------------------


class TestMigrationAddsSizeBytes:
    def test_migration_column_exists_after_open(self, tmp_path):
        # Arrange — create DB manually without size_bytes column
        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE file_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                hash TEXT NOT NULL,
                role TEXT NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE runs (
                session_id TEXT PRIMARY KEY,
                script_path TEXT,
                script_hash TEXT,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                status TEXT,
                exit_code INTEGER,
                parent_session TEXT,
                combined_hash TEXT,
                metadata TEXT
            )
            """
        )
        conn.commit()
        conn.close()
        # Act — open via VerificationDB triggers migration
        db = VerificationDB(db_path)
        with db._connect() as conn2:
            columns = {row[1] for row in conn2.execute("PRAGMA table_info(file_hashes)").fetchall()}
        # Assert
        assert "size_bytes" in columns

    def test_migration_preserves_existing_rows(self, tmp_path):
        # Arrange — create DB manually, insert a row, then open via VerificationDB
        db_path = tmp_path / "legacy2.db"
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE file_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                hash TEXT NOT NULL,
                role TEXT NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE runs (
                session_id TEXT PRIMARY KEY,
                script_path TEXT,
                script_hash TEXT,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                status TEXT,
                exit_code INTEGER,
                parent_session TEXT,
                combined_hash TEXT,
                metadata TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO runs (session_id, script_path, status) VALUES (?, ?, ?)",
            ("sess-old", "/old/script.py", "success"),
        )
        conn.execute(
            "INSERT INTO file_hashes (session_id, file_path, hash, role) VALUES (?, ?, ?, ?)",
            ("sess-old", "/old/out.csv", "abc123", "output"),
        )
        conn.commit()
        conn.close()
        # Act — open via VerificationDB migrates and preserves data
        db = VerificationDB(db_path)
        hashes = db.get_file_hashes("sess-old", role="output")
        # Assert
        assert "/old/out.csv" in hashes

    def test_migration_idempotent_on_second_open(self, tmp_path):
        # Arrange — open twice; second open should not raise
        db = _make_db(tmp_path)
        # Act — second open of the same path
        db2 = VerificationDB(tmp_path / "test_p2.db")
        with db2._connect() as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(file_hashes)").fetchall()}
        # Assert
        assert "size_bytes" in columns


# ---------------------------------------------------------------------------
# (i) size_bytes populated via SessionTracker.record_output
# ---------------------------------------------------------------------------


class TestSizeBytesPopulatedOnRecordOutput:
    def test_size_bytes_stored_after_record_output(self, tmp_path):
        # Arrange — create a real file and a tracker
        from scitex_clew._tracker import SessionTracker

        db = _make_db(tmp_path)
        out_file = tmp_path / "result.csv"
        out_file.write_bytes(b"a,b,c\n1,2,3\n")
        tracker = SessionTracker("sz-sess-1", db=db)
        # Act
        tracker.record_output(out_file)
        with db._connect() as conn:
            row = conn.execute(
                "SELECT size_bytes FROM file_hashes WHERE session_id=? AND role='output'",
                ("sz-sess-1",),
            ).fetchone()
        # Assert
        assert row is not None and row[0] == out_file.stat().st_size

    def test_size_bytes_stored_after_record_input(self, tmp_path):
        # Arrange
        from scitex_clew._tracker import SessionTracker

        db = _make_db(tmp_path)
        in_file = tmp_path / "data.csv"
        in_file.write_bytes(b"x\n" * 100)
        tracker = SessionTracker("sz-sess-2", db=db)
        # Act
        tracker.record_input(in_file)
        with db._connect() as conn:
            row = conn.execute(
                "SELECT size_bytes FROM file_hashes WHERE session_id=? AND role='input'",
                ("sz-sess-2",),
            ).fetchone()
        # Assert
        assert row is not None and row[0] == in_file.stat().st_size


# ---------------------------------------------------------------------------
# (j) typical_output_bytes is the median per-run total output bytes
# ---------------------------------------------------------------------------


class TestTypicalOutputBytes:
    def test_typical_output_bytes_is_median_across_sessions(self, tmp_path):
        # Arrange — sessions with total output sizes 100, 200, 300 bytes
        script = tmp_path / "vol.py"
        script.write_text("print('volume')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        for sid, total in [("v1", 100), ("v2", 200), ("v3", 300)]:
            _add_completed_run(db, sid, str(script), h, 10.0)
            # Write one output of exactly `total` bytes
            db.add_file_hash(sid, f"/out/{sid}.bin", f"hash-{sid}", "output", size_bytes=total)
        # Act
        result = estimate(str(script), db=db)
        # Assert — median of [100, 200, 300] = 200
        assert result.typical_output_bytes == 200

    def test_typical_output_bytes_sums_multiple_outputs_per_session(self, tmp_path):
        # Arrange — one session with two outputs of 60 and 40 bytes → total 100
        script = tmp_path / "multi.py"
        script.write_text("print('multi')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "m1", str(script), h, 5.0)
        db.add_file_hash("m1", "/out/a.bin", "ha", "output", size_bytes=60)
        db.add_file_hash("m1", "/out/b.bin", "hb", "output", size_bytes=40)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.typical_output_bytes == 100


# ---------------------------------------------------------------------------
# (k) No fabrication when size_bytes data is absent
# ---------------------------------------------------------------------------


class TestNoFabricationWhenSizeBytesAbsent:
    def test_typical_output_bytes_none_when_no_size_recorded(self, tmp_path):
        # Arrange — add output rows with NULL size_bytes (legacy style)
        script = tmp_path / "nosiz.py"
        script.write_text("print('nosiz')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "ns1", str(script), h, 8.0)
        # Insert with no size_bytes (None → NULL)
        db.add_file_hash("ns1", "/out/nosiz.bin", "hnosiz", "output", size_bytes=None)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.typical_output_bytes is None

    def test_cold_start_typical_output_bytes_is_none(self, tmp_path):
        # Arrange — empty DB
        script = tmp_path / "cold.py"
        script.write_text("print('cold')\n")
        db = _make_db(tmp_path)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.typical_output_bytes is None

    def test_build_cold_start_typical_output_bytes_is_none(self):
        # Arrange
        # Act
        result = _build_cold_start("/path/to/script.py")
        # Assert
        assert result.typical_output_bytes is None


# ---------------------------------------------------------------------------
# (l) Cached-intermediate hint fires when inputs exist as prior session outputs
# ---------------------------------------------------------------------------


class TestCachedIntermediateHint:
    def test_hint_contains_reuse_suggestion_when_input_is_prior_output(self, tmp_path):
        # Arrange — s2 uses s1's output as input; the intermediate exists on
        # disk and still matches s1's recorded hash (fresh → reuse advised)
        script = tmp_path / "step.py"
        script.write_text("print('step')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        shared = tmp_path / "intermediate.csv"
        shared.write_text("intermediate data")
        shared_file = str(shared)
        shared_hash = _hf(shared)
        _add_completed_run(db, "s1", str(script), h, 5.0)
        db.add_file_hash("s1", shared_file, shared_hash, "output")
        _add_completed_run(db, "s2", str(script), h, 5.0)
        db.add_file_hash("s2", shared_file, shared_hash, "input")
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert "cached intermediate" in result.hint.lower() or "reusing" in result.hint.lower()

    def test_cached_intermediate_hints_returns_non_empty_list(self, tmp_path):
        # Arrange — s4 inputs a file s3 produced; it exists on disk and still
        # matches s3's recorded output hash (fresh → hint emitted)
        from scitex_clew._hash import hash_file as _hf

        db = _make_db(tmp_path)
        shared = tmp_path / "data.csv"
        shared.write_text("shared data")
        shared_file = str(shared)
        shared_hash = _hf(shared)
        db.add_run("s3", "/produce.py")
        db.finish_run("s3")
        db.add_file_hash("s3", shared_file, shared_hash, "output")
        db.add_run("s4", "/consume.py")
        db.finish_run("s4")
        db.add_file_hash("s4", shared_file, shared_hash, "input")
        # Act
        hints = _cached_intermediate_hints(db, ["s4"])
        # Assert
        assert len(hints) > 0

    def test_no_reuse_hint_when_no_shared_files(self, tmp_path):
        # Arrange — two sessions with disjoint files
        db = _make_db(tmp_path)
        db.add_run("a1", "/scriptA.py")
        db.finish_run("a1")
        db.add_file_hash("a1", "/out/A.csv", "ha", "output")
        db.add_run("a2", "/scriptB.py")
        db.finish_run("a2")
        db.add_file_hash("a2", "/in/B.csv", "hb", "input")
        # Act
        hints = _cached_intermediate_hints(db, ["a2"])
        # Assert
        assert hints == []


# ---------------------------------------------------------------------------
# (m) hint includes volume text when bytes data is present
# ---------------------------------------------------------------------------


class TestHintIncludesVolumeText:
    def test_hint_mentions_output_volume_when_bytes_known(self, tmp_path):
        # Arrange — session with known output bytes (1 MB)
        script = tmp_path / "bigout.py"
        script.write_text("print('big')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "b1", str(script), h, 10.0)
        db.add_file_hash("b1", "/out/big.bin", "hbig", "output", size_bytes=1024 * 1024)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert "mb" in result.hint.lower() or "volume" in result.hint.lower()


# EOF
