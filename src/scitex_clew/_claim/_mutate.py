#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim lifecycle mutations — remove / supersede (single + by-prefix)."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from .._db import get_db
from .._db._connect import connect as _clew_sqlite_connect
from ._model import _ensure_claims_table, _resolve_claim


def _auto_export(context: str) -> None:
    """Re-emit claims.json after a mutation (best-effort, never fatal)."""
    if os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "1") == "0":
        return
    try:
        from ._export import export_claims_json

        export_claims_json()
    except Exception as exc:  # noqa: BLE001
        import warnings as _w

        _w.warn(
            f"scitex_clew auto-export of claims.json failed after {context}: {exc!r}",
            RuntimeWarning,
            stacklevel=3,
        )


def remove_claim(claim_id_or_location: str) -> bool:
    """Hard-delete a claim from the database.

    Permanently removes the claim row identified by ``claim_id_or_location``
    (a claim_id string, a location like ``"paper.tex:L42"``, or a bare file
    path — resolved via the same logic as :func:`verify_claim`).

    After deletion :func:`export_claims_json` is called so the JSON
    artifact stays in sync with the DB.

    Parameters
    ----------
    claim_id_or_location : str
        Claim identifier.  Resolution order:
        1. Exact ``claim_id`` match.
        2. Location string ``"file.tex:L42"``.
        3. File path only (first row).

    Returns
    -------
    bool
        ``True`` if a row was deleted; ``False`` if nothing matched.
    """
    db = get_db()
    _ensure_claims_table(db)

    claim = _resolve_claim(claim_id_or_location, db)
    if claim is None:
        return False

    conn = _clew_sqlite_connect(str(db.db_path))
    try:
        conn.execute("DELETE FROM claims WHERE claim_id = ?", (claim.claim_id,))
        conn.commit()
    finally:
        conn.close()

    _auto_export("remove_claim")
    return True


def remove_claims_by_prefix(file_path_prefix: str) -> int:
    """Hard-delete all claims whose file_path starts with ``file_path_prefix``.

    Parameters
    ----------
    file_path_prefix : str
        Path prefix (resolved).  All claims under this root are deleted.

    Returns
    -------
    int
        Number of rows deleted.
    """
    db = get_db()
    _ensure_claims_table(db)

    resolved_prefix = str(Path(file_path_prefix).resolve())
    if not resolved_prefix.endswith("/"):
        resolved_prefix = resolved_prefix + "/"

    conn = _clew_sqlite_connect(str(db.db_path))
    try:
        conn.execute(
            "DELETE FROM claims WHERE file_path LIKE ? OR file_path = ?",
            (resolved_prefix + "%", resolved_prefix.rstrip("/")),
        )
        conn.commit()
        deleted = conn.execute("SELECT changes()").fetchone()[0]
    finally:
        conn.close()

    _auto_export("remove_claims_by_prefix")
    return deleted


def supersede_claim(claim_id_or_location: str) -> bool:
    """Soft-retire a claim by setting its status to ``"superseded"``.

    The row is kept in the database (audit trail) but excluded from the
    default :func:`list_claims` view (``include_superseded=False`` is the
    default), from :func:`verify_all_claims`, and from the default
    :func:`export_claims_json` output.

    This allows a user to retire stale/dead claims so that ``clew verify``
    can reach exit 0 without deleting the historical record.

    Parameters
    ----------
    claim_id_or_location : str
        Claim identifier resolved the same way as :func:`remove_claim`.

    Returns
    -------
    bool
        ``True`` if the claim existed and was updated; ``False`` if nothing
        matched.
    """
    db = get_db()
    _ensure_claims_table(db)

    claim = _resolve_claim(claim_id_or_location, db)
    if claim is None:
        return False

    conn = _clew_sqlite_connect(str(db.db_path))
    try:
        conn.execute(
            "UPDATE claims SET status = 'superseded', verified_at = ? WHERE claim_id = ?",
            (datetime.now().isoformat(), claim.claim_id),
        )
        conn.commit()
    finally:
        conn.close()

    _auto_export("supersede_claim")
    return True


def supersede_claims_by_prefix(file_path_prefix: str) -> int:
    """Soft-retire all claims whose file_path starts with ``file_path_prefix``.

    Parameters
    ----------
    file_path_prefix : str
        Path prefix (resolved).

    Returns
    -------
    int
        Number of rows updated to status ``"superseded"``.
    """
    db = get_db()
    _ensure_claims_table(db)

    resolved_prefix = str(Path(file_path_prefix).resolve())
    if not resolved_prefix.endswith("/"):
        resolved_prefix = resolved_prefix + "/"

    conn = _clew_sqlite_connect(str(db.db_path))
    try:
        conn.execute(
            "UPDATE claims SET status = 'superseded', verified_at = ? "
            "WHERE file_path LIKE ? OR file_path = ?",
            (
                datetime.now().isoformat(),
                resolved_prefix + "%",
                resolved_prefix.rstrip("/"),
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT changes()").fetchone()[0]
    finally:
        conn.close()

    _auto_export("supersede_claims_by_prefix")
    return updated


# EOF
