#!/usr/bin/env python3
# Timestamp: "2026-08-28 (sqlite-migration-scitex-clew-20260828)"
# File: src/scitex_clew/_db/_file_hashes.py
"""File-hash record operations for VerificationDB (Store-backed).

Every read is ``self._file_hashes.rows()`` (a ``scitex_dev.store.Store``
built in ``_core.py``) filtered/sorted in Python — Store has no
WHERE/JOIN/ORDER-BY. This is an accepted O(n)-scan trade-off for what is
normally a small per-project DB (see the PR body). No sqlite3 import here;
the legacy `file_hashes` mirror write goes through `VerificationDB._connect()`
(defined in `_core.py`) via the small `_mirror_file_hash` helper below.
"""

from __future__ import annotations

import os
import socket
from typing import Dict, List, Optional

from scitex_dev.store import ANY_REVISION


def _resolve_host() -> Optional[str]:
    """Resolve the recording host for a file-hash row.

    Precedence: ``$SCITEX_CLEW_HOST`` > ``$SAC_HOST`` > ``socket.gethostname()``.
    The env overrides let a multi-node SIF/HPC run stamp a stable logical host
    (e.g. the login-node name) instead of a transient compute-node hostname.
    Returns ``None`` only if every source fails — the column stays nullable so
    existing behavior is never affected.
    """
    for env_key in ("SCITEX_CLEW_HOST", "SAC_HOST"):
        val = os.environ.get(env_key)
        if val:
            return val
    try:
        name = socket.gethostname()
        return name or None
    except OSError:
        return None


class FileHashMixin:
    """Mixin providing file-hash CRUD operations.

    Requires ``self._file_hashes`` (a Store instance) and
    ``self._connect()``/``self.db_path`` from VerificationDB.
    """

    # -------------------------------------------------------------------------
    # Legacy mirror migrations — called from _core.py._init_legacy_mirror()
    # -------------------------------------------------------------------------

    def _migrate_file_hashes_size_bytes(self) -> None:
        """Add size_bytes column to pre-existing legacy file_hashes tables (idempotent).

        Safe to call even when the column already exists: the PRAGMA check
        guards the ALTER TABLE so no exception is raised on repeated runs.
        """
        with self._connect() as conn:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(file_hashes)").fetchall()
            }
            if "size_bytes" not in columns:
                conn.execute("ALTER TABLE file_hashes ADD COLUMN size_bytes INTEGER")

    def _migrate_file_hashes_frozen(self) -> None:
        """Add frozen column to pre-existing legacy file_hashes tables (idempotent).

        frozen INTEGER DEFAULT 0 — trusts the recorded hash without
        re-reading the file during verification. Safe to call even when the
        column already exists: the PRAGMA check guards the ALTER TABLE so no
        exception is raised on repeated runs. Existing rows receive 0
        (not frozen) automatically.
        """
        with self._connect() as conn:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(file_hashes)").fetchall()
            }
            if "frozen" not in columns:
                conn.execute("ALTER TABLE file_hashes ADD COLUMN frozen INTEGER DEFAULT 0")

    def _migrate_file_hashes_host(self) -> None:
        """Add host column to pre-existing legacy file_hashes tables (idempotent).

        host TEXT (nullable) — records which host produced each artifact so
        provenance can be reasoned about across machines/nodes. Safe to call
        even when the column already exists: the PRAGMA check guards the
        ALTER TABLE so no exception is raised on repeated runs. Existing rows
        receive NULL (unknown host) automatically.
        """
        with self._connect() as conn:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(file_hashes)").fetchall()
            }
            if "host" not in columns:
                conn.execute("ALTER TABLE file_hashes ADD COLUMN host TEXT")

    # -------------------------------------------------------------------------
    # Mirror write helper (legacy `file_hashes` table — see _core.py docstring)
    # -------------------------------------------------------------------------

    def _mirror_file_hash(
        self,
        session_id: str,
        file_path: str,
        hash_value: str,
        role: str,
        size_bytes: Optional[int],
        frozen: bool,
        host: Optional[str],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO file_hashes
                (session_id, file_path, hash, role, size_bytes, frozen, host)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, file_path, hash_value, role, size_bytes, int(frozen), host),
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
        frozen: bool = False,
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
        frozen : bool, optional
            When True, verification trusts the recorded hash without re-reading
            the file.  Use for huge/external files (e.g. 4.1 TB datasets) where
            re-hashing on every ``clew verify`` is prohibitively expensive.
            Default False keeps all existing callers behavior-identical.

            A frozen file is NEVER silently rendered as fully hash-verified —
            it always carries the "FROZEN (trusted, not re-hashed)" marker in
            Mermaid output and CLI text so the trust is explicit and visible.
            Freezing skips hashing but still notes when the file is absent
            (frozen means "trust the hash without re-reading", not "ignore
            missing files").
        """
        host = _resolve_host()
        self._file_hashes.put(
            {
                "session_id": session_id,
                "file_path": file_path,
                "role": role,
                "hash": hash_value,
                "size_bytes": size_bytes,
                "frozen": frozen,
                "host": host,
                "recorded_at": _now_iso(),
            },
            expected_revision=ANY_REVISION,
        )
        self._mirror_file_hash(session_id, file_path, hash_value, role, size_bytes, frozen, host)

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
            Role of the files (input, output).
        """
        host = _resolve_host()
        for path, hash_value in hashes.items():
            self._file_hashes.put(
                {
                    "session_id": session_id,
                    "file_path": path,
                    "role": role,
                    "hash": hash_value,
                    "size_bytes": None,
                    "frozen": False,
                    "host": host,
                    "recorded_at": _now_iso(),
                },
                expected_revision=ANY_REVISION,
            )
            self._mirror_file_hash(session_id, path, hash_value, role, None, False, host)

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
        rows = self._rows_for_session(session_id, role)
        return {r.values.get("file_path"): r.values.get("hash") for r in rows}

    def get_frozen_files(
        self,
        session_id: str,
        role: Optional[str] = None,
    ) -> set:
        """Return the set of file paths that are marked frozen for a session.

        Additive helper — does not change the return type of ``get_file_hashes``
        so all existing callers remain behavior-identical.

        Parameters
        ----------
        session_id : str
            Session identifier.
        role : str, optional
            Filter by role (input, output, script, …).

        Returns
        -------
        set of str
            File paths whose ``frozen`` flag is 1 in the DB for this session.
        """
        rows = self._rows_for_session(session_id, role)
        return {r.values.get("file_path") for r in rows if r.values.get("frozen")}

    def _rows_for_session(self, session_id: str, role: Optional[str]):
        return [
            r
            for r in self._file_hashes.rows()
            if r.values.get("session_id") == session_id
            and (role is None or r.values.get("role") == role)
        ]

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
        rows = [
            r
            for r in self._file_hashes.rows()
            if r.values.get("file_path") == file_path
            and (role is None or r.values.get("role") == role)
        ]
        rows.sort(key=lambda r: r.values.get("recorded_at") or "", reverse=True)
        return _dedup([r.values.get("session_id") for r in rows])

    def find_sessions_by_files(
        self,
        file_paths: List[str],
        role: str,
    ) -> Dict[str, List[str]]:
        """Batch lookup: producers of multiple files, grouped by file_path.

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
            newest-first (``recorded_at`` desc), matching the order that
            ``find_session_by_file`` returns.  Files with no producers are
            absent from the dict (not present with an empty list).
        """
        if not file_paths:
            return {}
        wanted = set(file_paths)
        rows = [
            r
            for r in self._file_hashes.rows()
            if r.values.get("role") == role and r.values.get("file_path") in wanted
        ]
        rows.sort(key=lambda r: r.values.get("recorded_at") or "", reverse=True)
        result: Dict[str, List[str]] = {}
        for r in rows:
            fp = r.values.get("file_path")
            result.setdefault(fp, []).append(r.values.get("session_id"))
        return result

    def find_sessions_by_hash(
        self,
        content_hash: str,
        role: Optional[str] = None,
    ) -> List[str]:
        """Find sessions that recorded a file with a given CONTENT hash.

        Parameters
        ----------
        content_hash : str
            The file content hash to look up.
        role : str, optional
            Filter by role (input, output, script, …).

        Returns
        -------
        list of str
            Session IDs that recorded the content, newest-first
            (``recorded_at`` desc). Empty when the content is unknown.
        """
        rows = [
            r
            for r in self._file_hashes.rows()
            if r.values.get("hash") == content_hash
            and (role is None or r.values.get("role") == role)
        ]
        rows.sort(key=lambda r: r.values.get("recorded_at") or "", reverse=True)
        return _dedup([r.values.get("session_id") for r in rows])

    def hosts_for_hash(self, content_hash: str) -> List[str]:
        """Return the distinct known hosts that recorded a given content hash.

        Parameters
        ----------
        content_hash : str
            The file content hash to look up.

        Returns
        -------
        list of str
            Distinct non-null host names, ordered alphabetically.
        """
        hosts = {
            r.values.get("host")
            for r in self._file_hashes.rows()
            if r.values.get("hash") == content_hash and r.values.get("host") is not None
        }
        return sorted(hosts)


def _dedup(items: List[str]) -> List[str]:
    """First-occurrence-preserving dedup (mirrors SQL SELECT DISTINCT)."""
    seen: set = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat()


def _stat_size(path: str) -> Optional[int]:
    """Return os.path.getsize for *path*, or None if the file is inaccessible."""
    try:
        return os.path.getsize(path)
    except OSError:
        return None


# EOF
