#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim registration + listing — add_claim, list_claims, format_claims."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import List, Optional

from .._db import get_db
from ._model import (
    CLAIM_TYPES,
    Claim,
    _ensure_claims_table,
    _generate_claim_id,
    _LEGACY_STATUS_MAP,
)


def add_claim(
    file_path: str,
    claim_type: str,
    line_number: Optional[int] = None,
    claim_value: Optional[str] = None,
    source_file: Optional[str] = None,
    source_session: Optional[str] = None,
    *,
    claim_id: Optional[str] = None,
) -> Claim:
    """Register a claim linking a manuscript assertion to the verification chain.

    Parameters
    ----------
    file_path : str
        Path to the manuscript file (e.g., paper.tex).
    claim_type : str
        One of: statistic, figure, table, text, value.
    line_number : int, optional
        Line number in the manuscript.
    claim_value : str, optional
        The asserted value (e.g., "p = 0.003").
    source_file : str, optional
        Path to the source file that produced this claim.
    source_session : str, optional
        Session ID that produced the source.
    claim_id : str, optional
        Explicit, stable claim id used VERBATIM as the primary key (keyword-
        only). Supply this when the caller owns a meaningful identity — e.g. a
        figure's image save-path, or a semantic key per manuscript number — so
        the id never collapses and downstream ``\\clew*{id}`` render macros can
        join on it deterministically. When omitted, the id is DERIVED from
        ``(file_path, line_number, claim_type, claim_value)`` — folding the
        value in so two distinct numbers on one line no longer collapse. Re-
        registering the same explicit id (or the same derived tuple) overwrites
        idempotently.

    Returns
    -------
    Claim
        The registered claim object.
    """
    if claim_type not in CLAIM_TYPES:
        raise ValueError(
            f"Invalid claim_type '{claim_type}'. Must be one of: {CLAIM_TYPES}"
        )

    file_path = str(Path(file_path).resolve())
    if claim_id is not None:
        resolved_id = str(claim_id).strip()
        if not resolved_id:
            raise ValueError("claim_id, when given, must be a non-empty string")
    else:
        resolved_id = _generate_claim_id(
            file_path, line_number, claim_type, claim_value
        )

    # Compute source hash if source_file exists
    source_hash = None
    if source_file:
        source_file = str(Path(source_file).resolve())
        source_path = Path(source_file)
        if source_path.exists():
            from .._hash import hash_file

            source_hash = hash_file(source_path)

    # Auto-detect source session if not provided
    if source_file and not source_session:
        db = get_db()
        sessions = db.find_session_by_file(source_file, role="output")
        if sessions:
            source_session = sessions[0]

    claim = Claim(
        claim_id=resolved_id,
        file_path=file_path,
        line_number=line_number,
        claim_type=claim_type,
        claim_value=claim_value,
        source_session=source_session,
        source_file=source_file,
        source_hash=source_hash,
    )

    # Store in database
    db = get_db()
    _ensure_claims_table(db)
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO claims
                (claim_id, file_path, line_number, claim_type, claim_value,
                 source_session, source_file, source_hash, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'registered')
            """,
            (
                claim.claim_id,
                claim.file_path,
                claim.line_number,
                claim.claim_type,
                claim.claim_value,
                claim.source_session,
                claim.source_file,
                claim.source_hash,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Auto-export the canonical claims.json so consumers (verifier,
    # scitex-writer, human eyes) can read a stable artifact without
    # talking to sqlite. Default ON; opt out with
    # SCITEX_CLEW_AUTO_EXPORT_CLAIMS=0 if you're streaming thousands of
    # claims and the per-call rewrite cost matters. The cost is O(N×K)
    # where N is total claims in the DB and K is rewrite size — for
    # typical research papers (N < 100, K < 50 KB) it's negligible.
    if os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "1") != "0":
        try:
            from ._export import export_claims_json

            export_claims_json()
        except Exception as exc:  # noqa: BLE001
            # Auto-export is a convenience layer — must not break the
            # add_claim primary path if e.g. the runtime/ dir is
            # read-only on this host. Log and continue. The user can
            # call export_claims_json() explicitly to surface failures.
            import warnings as _w

            _w.warn(
                f"scitex_clew auto-export of claims.json failed "
                f"(set SCITEX_CLEW_AUTO_EXPORT_CLAIMS=0 to silence): "
                f"{exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )

    return claim


def list_claims(
    file_path: Optional[str] = None,
    claim_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    *,
    include_superseded: bool = False,
    file_path_prefix: Optional[str] = None,
) -> List[Claim]:
    """List registered claims with optional filters.

    Parameters
    ----------
    file_path : str, optional
        Filter by manuscript file path (exact match).
    claim_type : str, optional
        Filter by claim type.
    status : str, optional
        Filter by verification status.
    limit : int
        Maximum number of claims to return.
    include_superseded : bool, optional
        When False (default), excludes claims with status ``"superseded"``
        so they do not pollute the active-claim view or fail-loud gate.
        Pass True to see the full audit trail including superseded rows.
    file_path_prefix : str, optional
        Prefix-match on file_path (resolved).  Only claims whose
        ``file_path`` starts with this prefix are returned.  If both
        ``file_path`` and ``file_path_prefix`` are given, both filters
        apply (intersection).

    Returns
    -------
    list of Claim
    """
    db = get_db()
    _ensure_claims_table(db)

    query = "SELECT * FROM claims WHERE 1=1"
    params = []

    if file_path:
        file_path = str(Path(file_path).resolve())
        query += " AND file_path = ?"
        params.append(file_path)
    if file_path_prefix:
        resolved_prefix = str(Path(file_path_prefix).resolve())
        # Ensure the prefix ends with separator so /foo/bar doesn't match /foo/barbaz
        if not resolved_prefix.endswith("/"):
            resolved_prefix = resolved_prefix + "/"
        query += " AND (file_path LIKE ? OR file_path = ?)"
        params.append(resolved_prefix + "%")
        params.append(resolved_prefix.rstrip("/"))
    if claim_type:
        query += " AND claim_type = ?"
        params.append(claim_type)
    if status:
        query += " AND status = ?"
        params.append(status)
    if not include_superseded:
        # Exclude superseded rows unless the caller explicitly filters by
        # status="superseded" (allow explicit status filter to override).
        if not status:
            query += " AND status != 'superseded'"

    query += " ORDER BY file_path, line_number LIMIT ?"
    params.append(limit)

    conn = sqlite3.connect(str(db.db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query, params).fetchall()
        return [
            Claim(
                claim_id=row["claim_id"],
                file_path=row["file_path"],
                line_number=row["line_number"],
                claim_type=row["claim_type"],
                claim_value=row["claim_value"],
                source_session=row["source_session"],
                source_file=row["source_file"],
                source_hash=row["source_hash"],
                registered_at=row["registered_at"],
                verified_at=row["verified_at"],
                # Back-compat: normalize legacy "partial" -> "suspect"
                status=_LEGACY_STATUS_MAP.get(row["status"], row["status"]),
            )
            for row in rows
        ]
    finally:
        conn.close()


def format_claims(claims: List[Claim], verbose: bool = False) -> str:
    """Format claims list for terminal display."""
    if not claims:
        return "No claims registered."

    lines = []
    status_icons = {
        "registered": "○",  # ○
        "verified": "✓",  # ✓
        "mismatch": "✗",  # ✗
        "missing": "?",
        "suspect": "~",
        "superseded": "⊘",  # ⊘
    }

    for c in claims:
        icon = status_icons.get(c.status, "?")
        loc = c.location
        val = f" = {c.claim_value}" if c.claim_value else ""
        lines.append(f"  {icon} [{c.claim_type}] {loc}{val}")
        if verbose and c.source_file:
            src = Path(c.source_file).name
            lines.append(
                f"      source: {src} (session: {c.source_session or 'unknown'})"
            )

    return "\n".join(lines)


# EOF
