#!/usr/bin/env python3
# Timestamp: "2026-06-27 (clew-feature-impl)"
# File: src/scitex_clew/_db/_file_hashes.py
"""File-hash record operations for VerificationDB (Phase 2: adds size_bytes)."""

from __future__ import annotations

import os
from typing import Dict, List, Optional


class FileHashMixin:
    """Mixin providing file-hash CRUD operations.

    Requires ``_connect()`` context manager from VerificationDB.

    Phase 2 adds ``size_bytes`` (nullable INTEGER) to every insert so the
    estimate engine can predict output data volume.
    """

    # -------------------------------------------------------------------------
    # Migration helper — called from _core.py _init_schema
    # -------------------------------------------------------------------------

    def _migrate_file_hashes_size_bytes(self) -> None:
        """Add size_bytes column to pre-existing file_hashes tables (idempotent).

        Safe to call even when the column already exists: the PRAGMA check
        guards the ALTER TABLE so no exception is raised on repeated runs.
        """
        with self._connect() as conn:
            columns = {
                row[1]
                for row in conn.execute(
                    "PRAGMA table_info(file_hashes)"
                ).fetchall()
            }
            if "size_bytes" not in columns:
                conn.execute(
                    "ALTER TABLE file_hashes ADD COLUMN size_bytes INTEGER"
                )

    # -------------------------------------------------------------------------
    # Insert
    # -------------------------------------------------------------------------

    def add_file_hash(
        self,
        session_id: str,
        file_path: str,
        hash_value: str,
        role: str,
        size_bytes: Optional[int] = None,
    ) -> None:
        """Add a file hash record.

        Parameters
        ----------
        session_id : str
            Session identifier.
        file_path : str
            Path to the file.
        hash_value : str
            Hash of the file.
        role : str
            Role of the file (input, script, output).
        size_bytes : int, optional
            File size in bytes at recording time.  ``None`` when unknown or
            the file is no longer accessible.
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO file_hashes
                (session_id, file_path, hash, role, size_bytes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, file_path, hash_value, role, size_bytes),
            )

    def add_file_hashes(
        self,
        session_id: str,
        hashes: Dict[str, str],
        role: str,
    ) -> None:
        """Add multiple file hashes at once (without size_bytes — batch variant).

        Parameters
        ----------
        session_id : str
            Session identifier.
        hashes : dict
            Mapping of file paths to hashes.
        role : str
            Role of the files (input, script, output).
        """
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO file_hashes
                (session_id, file_path, hash, role)
                VALUES (?, ?, ?, ?)
                """,
                [(session_id, path, h, role) for path, h in hashes.items()],
            )

    # -------------------------------------------------------------------------
    # Query
    # -------------------------------------------------------------------------

    def get_file_hashes(
        self,
        session_id: str,
        role: Optional[str] = None,
    ) -> Dict[str, str]:
        """Get file hashes for a session.

        Parameters
        ----------
        session_id : str
            Session identifier.
        role : str, optional
            Filter by role.

        Returns
        -------
        dict
            Mapping of file paths to hashes.
        """
        with self._connect() as conn:
            if role:
                rows = conn.execute(
                    """
                    SELECT file_path, hash FROM file_hashes
                    WHERE session_id = ? AND role = ?
                    """,
                    (session_id, role),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT file_path, hash FROM file_hashes
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchall()
            return {row["file_path"]: row["hash"] for row in rows}

    def find_session_by_file(
        self,
        file_path: str,
        role: Optional[str] = None,
    ) -> List[str]:
        """Find sessions that used a specific file.

        Parameters
        ----------
        file_path : str
            Path to the file.
        role : str, optional
            Filter by role (input, output).

        Returns
        -------
        list of str
            List of session IDs.
        """
        with self._connect() as conn:
            if role:
                rows = conn.execute(
                    """
                    SELECT DISTINCT session_id FROM file_hashes
                    WHERE file_path = ? AND role = ?
                    ORDER BY recorded_at DESC
                    """,
                    (file_path, role),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT DISTINCT session_id FROM file_hashes
                    WHERE file_path = ?
                    ORDER BY recorded_at DESC
                    """,
                    (file_path,),
                ).fetchall()
            return [row["session_id"] for row in rows]

    def find_sessions_by_files(
        self,
        file_paths: List[str],
        role: str,
    ) -> Dict[str, List[str]]:
        """Batch lookup: producers of multiple files in a single SQL query.

        Replaces the per-file loop in ``_parents_via_files`` (the N+1 pattern)
        with one ``WHERE file_path IN (...) AND role=?`` query, grouped by
        file_path.  The ``idx_file_path`` index already covers this.

        Note: a single session's input count is typically small (well under
        SQLite's ~999-variable SQLITE_MAX_VARIABLE_NUMBER limit), so no
        chunking is needed here.  If callers ever pass very large lists they
        should chunk externally.

        Parameters
        ----------
        file_paths : list of str
            File paths to look up producers for.
        role : str
            Role to filter by (``"output"`` for producer lookup).

        Returns
        -------
        dict[str, list[str]]
            ``{file_path: [session_id, ...]}`` — producers per file, ordered
            newest-first (``recorded_at DESC``), matching the order that
            ``find_session_by_file`` returns.  Files with no producers are
            absent from the dict (not present with an empty list).
        """
        if not file_paths:
            return {}

        placeholders = ", ".join("?" * len(file_paths))
        params = list(file_paths) + [role]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT file_path, session_id, MAX(recorded_at) AS latest_at
                FROM file_hashes
                WHERE file_path IN ({placeholders}) AND role = ?
                GROUP BY file_path, session_id
                ORDER BY file_path, latest_at DESC
                """,
                params,
            ).fetchall()

        result: Dict[str, List[str]] = {}
        for row in rows:
            fp = row["file_path"]
            if fp not in result:
                result[fp] = []
            result[fp].append(row["session_id"])
        return result


def _stat_size(path: str) -> Optional[int]:
    """Return os.path.getsize for *path*, or None if the file is inaccessible."""
    try:
        return os.path.getsize(path)
    except OSError:
        return None


# EOF
