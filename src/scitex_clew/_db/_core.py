#!/usr/bin/env python3
# Timestamp: "2026-03-04 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_db.py
"""SQLite database for verification tracking."""

from __future__ import annotations

import json
import os
import sqlite3
import warnings
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ._chain import ChainMixin
from ._file_hashes import FileHashMixin
from ._queries import VerificationQueryMixin


def _find_project_root() -> Path:
    """Walk up from cwd to find the project root (contains .git or pyproject.toml)."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return current


def _default_claims_json_path(project_root: Path) -> Path:
    """Resolve the default canonical claims.json artifact path.

    Returns ``<project_root>/.scitex/clew/runtime/claims.json`` per the
    ecosystem local-state-directories convention. The runtime/ subdir
    is the canonical home for regenerable per-host outputs — claims.json
    is regenerable from the DB at any time, so it lives there alongside
    ``db.sqlite``.

    The resolved path is **just the path** — this function does not
    write or read the file. ``scitex_clew.export_claims_json()`` writes
    to it.
    """
    return project_root / ".scitex" / "clew" / "runtime" / "claims.json"


def _default_db_path(project_root: Path) -> Path:
    """Resolve the default database path under ``runtime/``.

    Returns ``<project_root>/.scitex/clew/runtime/db.sqlite`` per the
    ecosystem local-state-directories convention.

    Back-compat (skill §8): if the legacy path
    ``<project_root>/.scitex/clew/db.sqlite`` exists and the new path
    does not, migrate silently on first access and emit a one-time
    deprecation warning.
    """
    new = project_root / ".scitex" / "clew" / "runtime" / "db.sqlite"
    if new.exists():
        return new

    old = project_root / ".scitex" / "clew" / "db.sqlite"
    if old.exists():
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)
        warnings.warn(
            f"Moved database from {old} to {new}. "
            "The legacy location is deprecated and will be removed "
            "in a future version. Set SCITEX_CLEW_DB_PATH to suppress.",
            DeprecationWarning,
            stacklevel=2,
        )
    return new


class VerificationDB(VerificationQueryMixin, FileHashMixin, ChainMixin):
    """
    SQLite database for tracking session runs and file hashes.

    Stores:
    - runs: session_id, script_path, timestamps, status
    - file_hashes: session_id, file_path, hash, role (input/script/output)
    - session_parents: multi-parent DAG junction table

    Examples
    --------
    >>> db = VerificationDB()
    >>> db.add_run("2025Y-11M-18D-09h12m03s_HmH5", "/path/script.py")
    >>> db.add_file_hash("2025Y-11M-18D-09h12m03s_HmH5", "data.csv", "a1b2c3", "input")
    """

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        """
        Initialize database connection.

        Parameters
        ----------
        db_path : str or Path, optional
            Path to database file. Resolution order:
            1. Explicit db_path argument
            2. SCITEX_CLEW_DB_PATH environment variable
            3. {project_root}/.scitex/clew/runtime/db.sqlite where
               project_root is found by walking up from cwd until a
               .git / pyproject.toml is found; falls back to cwd if no
               root marker is found.
        """
        if db_path is None:
            env_path = os.environ.get("SCITEX_CLEW_DB_PATH")
            if env_path:
                db_path = Path(env_path)
            else:
                db_path = _default_db_path(_find_project_root())
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    session_id TEXT PRIMARY KEY,
                    script_path TEXT,
                    script_hash TEXT,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    status TEXT,
                    exit_code INTEGER,
                    parent_session TEXT,
                    combined_hash TEXT,
                    metadata TEXT,
                    provenance TEXT DEFAULT 'tracked',
                    exception_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS file_hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    size_bytes INTEGER,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES runs(session_id),
                    UNIQUE(session_id, file_path, role)
                );

                CREATE INDEX IF NOT EXISTS idx_file_path
                    ON file_hashes(file_path);
                CREATE INDEX IF NOT EXISTS idx_session
                    ON file_hashes(session_id);
                CREATE INDEX IF NOT EXISTS idx_role
                    ON file_hashes(role);
                CREATE INDEX IF NOT EXISTS idx_runs_status
                    ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_parent
                    ON runs(parent_session);

                CREATE TABLE IF NOT EXISTS verification_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    level TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES runs(session_id)
                );

                CREATE INDEX IF NOT EXISTS idx_verification_session
                    ON verification_results(session_id);

                CREATE TABLE IF NOT EXISTS session_parents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    parent_session TEXT NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES runs(session_id),
                    FOREIGN KEY (parent_session) REFERENCES runs(session_id),
                    UNIQUE(session_id, parent_session)
                );

                CREATE INDEX IF NOT EXISTS idx_session_parents_session
                    ON session_parents(session_id);
                CREATE INDEX IF NOT EXISTS idx_session_parents_parent
                    ON session_parents(parent_session);
                """
            )

        # Migrate existing parent_session data to junction table
        self._migrate_session_parents()
        # Phase 2: add size_bytes column to pre-existing DBs (idempotent)
        self._migrate_file_hashes_size_bytes()
        # Phase 3: add provenance + exception_reason to pre-existing runs tables (idempotent)
        self._migrate_runs_provenance()

    @contextmanager
    def _connect(self):
        """Context manager for database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Migration helpers
    # -------------------------------------------------------------------------

    def _migrate_runs_provenance(self) -> None:
        """Add provenance and exception_reason columns to pre-existing runs tables (idempotent).

        Safe to call even when the columns already exist: the PRAGMA check
        guards the ALTER TABLE so no exception is raised on repeated runs.
        Existing rows receive the default value ('tracked' / NULL) automatically.
        """
        with self._connect() as conn:
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(runs)"
                ).fetchall()
            }
            if "provenance" not in columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN provenance TEXT DEFAULT 'tracked'"
                )
            if "exception_reason" not in columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN exception_reason TEXT"
                )

    # -------------------------------------------------------------------------
    # Run operations
    # -------------------------------------------------------------------------

    def add_run(
        self,
        session_id: str,
        script_path: str,
        script_hash: Optional[str] = None,
        parent_session: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        provenance: str = "tracked",
        exception_reason: Optional[str] = None,
    ) -> None:
        """
        Add a new run to the database.

        Parameters
        ----------
        session_id : str
            Unique session identifier
        script_path : str
            Path to the script that was run
        script_hash : str, optional
            Hash of the script file
        parent_session : str, optional
            Parent session ID for chain tracking
        metadata : dict, optional
            Additional metadata to store
        provenance : str, optional
            Provenance marker: 'tracked' (auto-tracked via @stx.session, default)
            or 'exception' (manually/retrospectively registered by hand).
        exception_reason : str, optional
            Structured justification for exception nodes (required when
            provenance='exception' for operator accountability). E.g.
            '4.1 TB gPAC job, recipe-known, never re-run'. NULL for tracked nodes.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs
                (session_id, script_path, script_hash, started_at, status,
                 parent_session, metadata, provenance, exception_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    script_path,
                    script_hash,
                    datetime.now().isoformat(),
                    "running",
                    parent_session,
                    json.dumps(metadata) if metadata else None,
                    provenance,
                    exception_reason,
                ),
            )

    def finish_run(
        self,
        session_id: str,
        status: str = "success",
        exit_code: int = 0,
        combined_hash: Optional[str] = None,
    ) -> None:
        """
        Mark a run as finished.

        Parameters
        ----------
        session_id : str
            Session identifier
        status : str, optional
            Final status (success, failed, error)
        exit_code : int, optional
            Exit code of the script
        combined_hash : str, optional
            Combined hash of all inputs/outputs
        """
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runs
                SET finished_at = ?, status = ?, exit_code = ?, combined_hash = ?
                WHERE session_id = ?
                """,
                (
                    datetime.now().isoformat(),
                    status,
                    exit_code,
                    combined_hash,
                    session_id,
                ),
            )

    def get_run(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get run information by session ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE session_id = ?", (session_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_runs(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List runs with optional filtering.

        Parameters
        ----------
        status : str, optional
            Filter by status
        limit : int, optional
            Maximum number of results
        offset : int, optional
            Offset for pagination

        Returns
        -------
        list of dict
            List of run records
        """
        with self._connect() as conn:
            if status:
                rows = conn.execute(
                    """
                    SELECT * FROM runs
                    WHERE status = ?
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (status, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM runs
                    ORDER BY started_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
            return [dict(row) for row in rows]

    # -------------------------------------------------------------------------
    # File hash operations — implemented in FileHashMixin (_file_hashes.py)
    # -------------------------------------------------------------------------


# Global instance
_DB_INSTANCE: Optional[VerificationDB] = None


def get_db() -> VerificationDB:
    """Get or create the global database instance."""
    global _DB_INSTANCE
    if _DB_INSTANCE is None:
        _DB_INSTANCE = VerificationDB()
    return _DB_INSTANCE


def set_db(db_path: Union[str, Path]) -> VerificationDB:
    """Set the global database instance to use a specific path.

    Parameters
    ----------
    db_path : str or Path
        Path to database file (e.g. "./.scitex/clew/runtime/db.sqlite" for project-relative).

    Returns
    -------
    VerificationDB
        The new database instance.
    """
    global _DB_INSTANCE
    _DB_INSTANCE = VerificationDB(db_path=db_path)
    return _DB_INSTANCE


# EOF
