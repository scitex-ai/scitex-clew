#!/usr/bin/env python3
# Timestamp: "2026-08-28 (sqlite-migration-scitex-clew-20260828)"
# File: src/scitex_clew/_db/_queries.py
"""Verification recording, history, and statistics queries (Store-backed).

Every read is ``self._verifications.rows()`` / ``self._runs.rows()`` /
``self._file_hashes.rows()`` (``scitex_dev.store.Store`` instances built in
``_core.py``) filtered/sorted/counted in Python — Store has no
WHERE/JOIN/ORDER-BY/COUNT. No sqlite3 import here.

``verification_results`` uses a synthetic uuid4 IDENTITY (``verification_id``)
rather than a composite of (session_id, level, verified_at): the original
AUTOINCREMENT PK guaranteed every ``record_verification()`` call created a
NEW row even when (session_id, level, verified_at) repeats (e.g. two calls
in the same microsecond), and a composite business key cannot give that
guarantee. See ``_schema.py`` and the PR body.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from scitex_dev.store import NEW_RECORD


class VerificationQueryMixin:
    """Mixin providing verification recording and statistics methods.

    Requires ``self._verifications``, ``self._runs`` and
    ``self._file_hashes`` (Store instances) from VerificationDB.
    """

    def record_verification(
        self,
        session_id: str,
        level: str,
        status: str,
    ) -> None:
        """Record a verification result.

        Parameters
        ----------
        session_id : str
            Session identifier
        level : str
            Verification level (cache, from_scratch)
        status : str
            Verification status (verified, mismatch, missing, unknown)
        """
        self._verifications.put(
            {
                "verification_id": uuid.uuid4().hex,
                "session_id": session_id,
                "level": level,
                "status": status,
                "verified_at": datetime.now().isoformat(),
            },
            expected_revision=NEW_RECORD,
        )

    def get_latest_verification(
        self,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent verification result for a session.

        Parameters
        ----------
        session_id : str
            Session identifier

        Returns
        -------
        dict or None
            Latest verification result with level, status, and timestamp
        """
        history = self.get_verification_history(session_id, limit=1)
        return history[0] if history else None

    def get_verification_history(
        self,
        session_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get verification history for a session.

        Parameters
        ----------
        session_id : str
            Session identifier
        limit : int, optional
            Maximum number of results

        Returns
        -------
        list of dict
            Verification results ordered by timestamp (newest first)
        """
        rows = [
            r for r in self._verifications.rows() if r.values.get("session_id") == session_id
        ]
        rows.sort(key=lambda r: r.values.get("verified_at") or "", reverse=True)
        return [
            {
                "level": r.values.get("level"),
                "status": r.values.get("status"),
                "verified_at": r.values.get("verified_at"),
            }
            for r in rows[:limit]
        ]

    def stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        runs = self._runs.rows()
        file_hashes = self._file_hashes.rows()
        return {
            "total_runs": len(runs),
            "success_runs": sum(1 for r in runs if r.values.get("status") == "success"),
            "failed_runs": sum(1 for r in runs if r.values.get("status") == "failed"),
            "total_file_records": len(file_hashes),
            "unique_files": len({r.values.get("file_path") for r in file_hashes}),
            "db_path": str(self.db_path),
        }


# EOF
