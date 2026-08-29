#!/usr/bin/env python3
# Timestamp: "2026-08-29 (clew-postgres-store-migration)"
# File: src/scitex_clew/_estimate_queries.py
"""DB-query layer for :mod:`scitex_clew._estimate` (Store-backed).

Extracted from ``_estimate.py`` purely to keep that file under the
project's 512-line limit (see ``GITIGNORED/REFACTORING.md`` while the
split is in flight). These are the same module-private helpers that used
to live in ``_estimate.py`` and reached into ``VerificationDB._connect()``
for a raw DB-API connection; ``_estimate.py`` re-exports every name
here so ``from scitex_clew._estimate import _cached_intermediate_hints``
(used by this package's own tests) keeps working unchanged.

Every function below now reads ``db._runs`` / ``db._file_hashes``
(``scitex_dev.store.Store`` instances built in ``_db/_core.py``) via
``.rows()`` and filters/sorts/joins in Python — Store has no
WHERE/JOIN/ORDER-BY/LIMIT support, an accepted O(n)-scan trade-off for
what is normally a small per-project DB (same trade-off ``_db/_queries.py``
and ``_db/_file_hashes.py`` already made). No raw DB driver import, no
``db._connect()`` call anywhere in this file.
"""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def _query_runs_by_field(db, field: str, value: str) -> List[dict]:
    """Return completed runs (``finished_at IS NOT NULL``) filtered by *field* == *value*.

    Store-backed equivalent of::

        SELECT session_id, started_at, finished_at, status, exit_code
        FROM runs
        WHERE {field} = ? AND finished_at IS NOT NULL
        ORDER BY started_at DESC

    Sorted by the actual ``started_at`` DATA value (a real timestamp
    column), not insertion/HLC order — matching the original
    ``ORDER BY started_at DESC`` exactly.
    """
    matched = [
        r.values
        for r in db._runs.rows()
        if r.values.get(field) == value and r.values.get("finished_at") is not None
    ]
    matched.sort(key=lambda v: v.get("started_at") or "", reverse=True)
    return [
        {
            "session_id": v.get("session_id"),
            "started_at": v.get("started_at"),
            "finished_at": v.get("finished_at"),
            "status": v.get("status"),
            "exit_code": v.get("exit_code"),
        }
        for v in matched
    ]


def _query_runs_by_hash(db, script_hash: str) -> List[dict]:
    """Return completed runs whose script_hash matches exactly."""
    return _query_runs_by_field(db, "script_hash", script_hash)


def _query_runs_by_path(db, script_path: str) -> List[dict]:
    """Return completed runs whose script_path matches (fallback tier)."""
    return _query_runs_by_field(db, "script_path", script_path)


# ---------------------------------------------------------------------------
# Output volume / count
# ---------------------------------------------------------------------------


def _output_bytes_for_sessions(db, session_ids: List[str]) -> List[Optional[int]]:
    """Return per-session total output bytes (None when all size_bytes are NULL)."""
    file_hash_rows = db._file_hashes.rows()
    results: List[Optional[int]] = []
    for sid in session_ids:
        sizes = [
            r.values.get("size_bytes")
            for r in file_hash_rows
            if r.values.get("session_id") == sid and r.values.get("role") == "output"
        ]
        sizes = [s for s in sizes if s is not None]
        results.append(sum(sizes) if sizes else None)
    return results


def _typical_output_bytes(db, session_ids: List[str]) -> Optional[int]:
    """Median total output bytes across sessions; None if no size data exists."""
    per_session = _output_bytes_for_sessions(db, session_ids)
    known = [v for v in per_session if v is not None]
    if not known:
        return None
    return int(statistics.median(known))


def _count_outputs_for_sessions(db, session_ids: List[str]) -> List[int]:
    """Return a list of output-file counts, one entry per session."""
    file_hash_rows = db._file_hashes.rows()
    counts = []
    for sid in session_ids:
        n = sum(
            1
            for r in file_hash_rows
            if r.values.get("session_id") == sid and r.values.get("role") == "output"
        )
        counts.append(n)
    return counts


# ---------------------------------------------------------------------------
# Cached-intermediate reuse hints
# ---------------------------------------------------------------------------


def _cached_intermediate_hints(
    db,
    session_ids: List[str],
    hash_cache: "Optional[dict]" = None,
) -> List[str]:
    """Return hints when recorded inputs exist as FRESH outputs of prior sessions.

    A "fresh" artifact is one whose on-disk content hashes to the same value
    the producer session originally recorded.  PATH equality alone is not
    sufficient: a later run may have overwritten the file (stale artifact).
    Only artifacts that pass the freshness check get a reuse hint.

    Store-backed equivalent of, executed once PER ``sid`` in ``session_ids``::

        SELECT fh.file_path, r.session_id AS producer_session
        FROM file_hashes fh
        JOIN file_hashes fh2
            ON fh2.file_path = fh.file_path AND fh2.role = 'output'
        JOIN runs r ON r.session_id = fh2.session_id
        WHERE fh.session_id = ? AND fh.role = 'input'
          AND fh2.session_id != ?
        ORDER BY r.started_at DESC
        LIMIT 5

    Read carefully: the self-join is over ``file_path`` (not
    ``session_id``); the ORDER BY is by the *producer's* ``started_at``
    (``r`` joins to ``fh2.session_id``, not ``fh.session_id``/``sid``);
    the ``JOIN runs r`` is an INNER JOIN, so a producer session with no
    matching ``runs`` row is excluded entirely (not merely un-ordered);
    and ``LIMIT 5`` is scoped to a single ``sid`` iteration — a fresh
    top-5 candidate set is drawn *per session* in the caller's loop, not
    once globally across every session in ``session_ids``.

    Parameters
    ----------
    db : VerificationDB
        Database to query.
    session_ids : list of str
        Session IDs to check for cached-intermediate candidates.
    hash_cache : dict or None, optional
        Per-pass hash cache (see :func:`scitex_clew._hash.hash_file`).
        When provided, each unique file path is hashed at most once per
        call.  Pass ``None`` to disable caching.
    """
    from ._hash import hash_file

    hints: List[str] = []
    seen: set = set()

    file_hash_rows = db._file_hashes.rows()
    started_at_by_session = {
        r.values.get("session_id"): r.values.get("started_at") for r in db._runs.rows()
    }

    for sid in session_ids:
        input_paths = {
            r.values.get("file_path")
            for r in file_hash_rows
            if r.values.get("session_id") == sid and r.values.get("role") == "input"
        }
        if not input_paths:
            continue

        # fh2 JOIN runs r — producer sessions with no `runs` row are
        # dropped by the INNER JOIN, not merely sorted last.
        candidates = []
        for r in file_hash_rows:
            if r.values.get("role") != "output":
                continue
            file_path = r.values.get("file_path")
            if file_path not in input_paths:
                continue
            producer_session = r.values.get("session_id")
            if producer_session == sid:
                continue
            if producer_session not in started_at_by_session:
                continue
            candidates.append(
                (file_path, producer_session, started_at_by_session[producer_session])
            )

        # ORDER BY r.started_at DESC LIMIT 5 — scoped to THIS sid.
        candidates.sort(key=lambda c: c[2] or "", reverse=True)
        candidates = candidates[:5]

        for file_path, producer_session, _started_at in candidates:
            key = (file_path, producer_session)
            if key in seen:
                continue
            seen.add(key)

            # --- Freshness check -------------------------------------------
            # Retrieve the hash the producer session recorded for this output.
            producer_hashes = db.get_file_hashes(producer_session, role="output")
            recorded_hash = producer_hashes.get(file_path)

            # If the artifact is missing or the stored hash is unavailable,
            # we cannot vouch for freshness — skip the hint silently.
            artifact = Path(file_path)
            if recorded_hash is None or not artifact.exists():
                continue

            try:
                current_hash = hash_file(artifact, hash_cache=hash_cache)
            except Exception:
                continue

            # Compare truncated hashes (hash_file returns first 32 chars of
            # sha256 hex; the DB may store the same or a full hex — align by
            # comparing the shorter prefix of each).
            min_len = min(len(recorded_hash), len(current_hash))
            if recorded_hash[:min_len] != current_hash[:min_len]:
                # Artifact has changed on disk since the producer session —
                # do NOT suggest reuse of a stale intermediate.
                continue

            hints.append(
                f"Input '{file_path}' already produced by session "
                f"{producer_session} — consider reusing the cached intermediate."
            )
    return hints


# EOF
