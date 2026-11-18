#!/usr/bin/env python3
# Timestamp: "2026-08-29 (clew-postgres-store-migration)"
# File: src/scitex_clew/_db/_file_hashes.py
"""File-hash record operations for VerificationDB (Store-backed).

Reads are ``self._file_hashes.search(Query...)``: filtered in SQL, so a
per-session or per-path lookup decodes only the rows it returns, never the
whole table (``verify`` and recording make one such lookup per run / per
input, and a table scan per call made both grow with the project). No raw DB
driver import here.
"""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Dict, List, Optional

from scitex_dev.store import ANY_REVISION

from ._record_views import RecordViewsMixin, decode_record


def _resolve_host() -> str | None:
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


def _resolve_abspath(file_path: str) -> str:
    """Normalize a query path to the SAME absolute form used at record time.

    Every file path is stored resolved-absolute (``str(Path(p).resolve())``,
    see ``Tracker.record_input``/``record_output``), and ``verify_chain``
    resolves its own ``target`` argument the identical way before querying.
    Query-side lookups here must use the same resolution or a relative-path
    query silently (no error, no log) matches nothing even though the
    absolute equivalent matches fine — the
    clew-fix-path-normalization-find-session bug. ``Path.resolve()`` does
    not require the path to exist, so this is safe for a query about a
    session/file combination the caller doesn't have on the local
    filesystem right now.
    """
    return str(Path(file_path).resolve())


class FileHashMixin(RecordViewsMixin):
    """Mixin providing file-hash CRUD operations.

    Requires ``self._file_hashes`` (a Store instance) from VerificationDB.
    """

    # -------------------------------------------------------------------------
    # Insert
    # -------------------------------------------------------------------------

    def add_file_hash(
        self,
        session_id: str,
        file_path: str,
        hash_value: str,
        role: str,
        size_bytes: int | None = None,
        frozen: bool = False,
        derived_from: list[str] | None = None,
        external: dict | None = None,
        defer: bool = False,
        recorded_at: str | None = None,
        journal=None,
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
        derived_from : list of str, optional
            OUTPUT rows only: the resolved paths this output was derived from,
            as declared by the writing tool (level-2 minimal slice). ``None``
            records "undeclared".
        external : dict, optional
            INPUT rows only: ``{"via", "size", "mtime"}`` when the file was
            read from OUTSIDE the project root (``via`` is the in-project
            path used, e.g. a symlink, else None). ``None`` = in-project.
        defer : bool, optional
            Queue the row instead of committing it now (see
            :mod:`scitex_clew._db._deferred`): written in one transaction with
            the rest of the queue at the next access to the store, at session
            close, or at exit. The row is identical either way — it carries
            the time it was recorded, not the time it was flushed.
        recorded_at : str, optional
            ISO time the file was recorded (default: now).
        journal : SessionJournal, optional
            With ``defer``: the session journal the queued row is also
            appended to, so a killed process cannot lose it
            (:mod:`scitex_clew._journal`).
        """
        host = _resolve_host()
        write = self._file_hashes.defer_put if defer else self._file_hashes.put
        if defer:
            kwargs = {"journal": journal} if journal is not None else {}
        else:
            kwargs = {"expected_revision": ANY_REVISION}
        write(
            {
                "session_id": session_id,
                "file_path": file_path,
                "role": role,
                "hash": hash_value,
                "size_bytes": size_bytes,
                "frozen": frozen,
                "host": host,
                "recorded_at": recorded_at or _now_iso(),
                "derived_from": (
                    json.dumps(list(derived_from)) if derived_from is not None else None
                ),
                "external": json.dumps(external) if external is not None else None,
            },
            **kwargs,
        )

    def add_file_hashes(
        self,
        session_id: str,
        hashes: dict[str, str],
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

    # -------------------------------------------------------------------------
    # Query — per-session views (get_file_hashes, get_frozen_files,
    # get_file_records, get_external_files) live in RecordViewsMixin and all
    # derive from session_file_records(): ONE query per session.
    # -------------------------------------------------------------------------

    def session_file_records(self, session_id: str) -> list[dict]:
        """Every file row of one session, decoded (``frozen`` included).

        Filtered in SQL: a client-side scan of the table per session made
        ``verify`` cost (runs in the slice) x (rows in the project).
        """
        return [decode_record(r.values) for r in self._rows_for_session(session_id, None)]

    def find_producer_records(
        self,
        file_paths: list[str],
    ) -> dict[str, list[dict[str, str | None]]]:
        """Every OUTPUT row recorded for each of ``file_paths``, newest-first.

        The content-addressed counterpart of :meth:`find_sessions_by_files`:
        each record carries the producer's recorded output ``hash`` and
        ``recorded_at`` so a caller can bind a consumer's input to the
        producer of THOSE bytes rather than to whoever wrote the path last.
        Keyed by the caller's spelling; paths are matched in resolved form.

        Returns
        -------
        dict
            ``{file_path: [{"session_id", "hash", "recorded_at"}, ...]}``.
            Paths with no producer are absent.
        """
        if not file_paths:
            return {}
        resolved_to_original: dict[str, str] = {}
        for original in file_paths:
            resolved_to_original.setdefault(_resolve_abspath(original), original)
        from scitex_dev.store import Query, eq, is_in

        # Filtered in SQL: called once per recorded input, so a client-side
        # scan of every row (``rows()``) made recording O(table) per file —
        # measured 0.4 s/input at ~10k rows.
        rows = self._file_hashes.search(
            Query().where(
                eq("role", "output"), is_in("file_path", list(resolved_to_original))
            )
        )
        rows.sort(key=lambda r: r.values.get("recorded_at") or "", reverse=True)
        result: dict[str, list[dict[str, str | None]]] = {}
        for r in rows:
            stored = r.values.get("file_path")
            key = resolved_to_original.get(stored, stored)
            result.setdefault(key, []).append(
                {
                    "session_id": r.values.get("session_id"),
                    "hash": r.values.get("hash"),
                    "recorded_at": r.values.get("recorded_at"),
                }
            )
        return result

    def _rows_for_session(self, session_id: str, role: str | None):
        """A session's rows (optionally one role), in record order — in SQL."""
        from scitex_dev.store import Query, eq

        query = Query().where(eq("session_id", session_id))
        if role is not None:
            query = query.where(eq("role", role))
        return self._file_hashes.search(
            query.ordered_by("recorded_at", descending=False)
        )

    def find_session_by_file(
        self,
        file_path: str,
        role: str | None = None,
    ) -> list[str]:
        """Find sessions that used a specific file.

        Parameters
        ----------
        file_path : str
            Path to the file. May be relative or absolute — normalized to
            the same resolved-absolute form ``verify_chain`` uses and every
            file path is recorded under, so a relative path and its
            absolute equivalent return the SAME result
            (clew-fix-path-normalization-find-session).
        role : str, optional
            Filter by role (input, output).

        Returns
        -------
        list of str
            List of session IDs.
        """
        from scitex_dev.store import Query, eq

        query = Query().where(eq("file_path", _resolve_abspath(file_path)))
        if role is not None:
            query = query.where(eq("role", role))
        rows = self._file_hashes.search(query)
        rows.sort(key=lambda r: r.values.get("recorded_at") or "", reverse=True)
        return _dedup([r.values.get("session_id") for r in rows])

    def find_sessions_by_files(
        self,
        file_paths: list[str],
        role: str,
    ) -> dict[str, list[str]]:
        """Batch lookup: producers of multiple files, grouped by file_path.

        Parameters
        ----------
        file_paths : list of str
            File paths to look up producers for. Each may be relative or
            absolute — normalized the same way as :meth:`find_session_by_file`
            (clew-fix-path-normalization-find-session) so lookups are
            consistent regardless of how the path was spelled.
        role : str
            Role to filter by (``"output"`` for producer lookup).

        Returns
        -------
        dict[str, list[str]]
            ``{file_path: [session_id, ...]}`` — producers per file, ordered
            newest-first (``recorded_at`` desc), matching the order that
            ``find_session_by_file`` returns.  Files with no producers are
            absent from the dict (not present with an empty list). Keyed by
            the ORIGINAL (caller-supplied) path spelling, not the resolved
            form, so ``result[p]`` works for whatever ``p`` the caller passed
            in ``file_paths`` — internal callers (e.g. ``_parents_via_files``)
            already pass already-resolved paths, so this is a no-op for them.
        """
        if not file_paths:
            return {}
        # Map resolved-form -> original spelling so the returned dict is keyed
        # by what the caller passed in, even though the match must use the
        # resolved form to find what is actually stored.
        resolved_to_original: dict[str, str] = {}
        for original in file_paths:
            resolved_to_original.setdefault(_resolve_abspath(original), original)

        from scitex_dev.store import Query, eq, is_in

        rows = self._file_hashes.search(
            Query().where(
                eq("role", role), is_in("file_path", list(resolved_to_original))
            )
        )
        rows.sort(key=lambda r: r.values.get("recorded_at") or "", reverse=True)
        result: dict[str, list[str]] = {}
        for r in rows:
            stored = r.values.get("file_path")
            fp = resolved_to_original.get(stored, stored)
            session_id = r.values.get("session_id")
            bucket = result.setdefault(fp, [])
            if session_id not in bucket:
                bucket.append(session_id)
        return result


def _dedup(items: list[str]) -> list[str]:
    """First-occurrence-preserving dedup (mirrors SQL SELECT DISTINCT)."""
    seen: set = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat()


def _stat_size(path: str) -> int | None:
    """Return os.path.getsize for *path*, or None if the file is inaccessible."""
    try:
        return os.path.getsize(path)
    except OSError:
        return None


# EOF
