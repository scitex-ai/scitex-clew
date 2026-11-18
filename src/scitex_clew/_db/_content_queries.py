#!/usr/bin/env python3
"""Content-addressed file-hash queries for VerificationDB.

"Who recorded these BYTES?" — by content hash, regardless of path or host.
Split out of ``_file_hashes.py`` (path-keyed CRUD) to keep each module under
the project's 512-line limit. Requires ``self._file_hashes`` (a Store).
"""

from __future__ import annotations

from ._file_hashes import _dedup

__all__ = ["ContentQueryMixin"]


class ContentQueryMixin:
    """Queries keyed by content hash (see :class:`FileHashMixin` for paths)."""

    def find_sessions_by_hash(
        self,
        content_hash: str,
        role: str | None = None,
    ) -> list[str]:
        """Find sessions that recorded a file with a given CONTENT hash.

        Content-addressed counterpart to :meth:`find_session_by_file` (which
        keys on ``file_path``). A match here proves the exact bytes exist
        somewhere in the ledger regardless of path or host — the primitive a
        multi-host / path-tolerant verify builds on. Uses ``idx_hash``.

        NOTE: existence of matching content is NOT the same as path/host
        provenance; callers that verify MUST still gate the result by trust
        level (path/host agreement) before treating it as fully verified. This
        method only answers "who recorded these bytes?", never "is this the
        right file?".

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
        from scitex_dev.store import Query, eq

        query = Query().where(eq("hash", content_hash))
        if role is not None:
            query = query.where(eq("role", role))
        rows = self._file_hashes.search(query)
        rows.sort(key=lambda r: r.values.get("recorded_at") or "", reverse=True)
        return _dedup([r.values.get("session_id") for r in rows])

    def hosts_for_hash(self, content_hash: str) -> list[str]:
        """Return the distinct known hosts that recorded a given content hash.

        A NULL host (recorded before Phase 5, or when host resolution failed)
        is omitted. Useful for surfacing "this exact artifact was produced on
        hosts X and Y" in multi-host provenance views. Uses ``idx_hash``.

        Parameters
        ----------
        content_hash : str
            The file content hash to look up.

        Returns
        -------
        list of str
            Distinct non-null host names, ordered alphabetically.
        """
        from scitex_dev.store import Query, eq

        hosts = {
            r.values.get("host")
            for r in self._file_hashes.search(Query().where(eq("hash", content_hash)))
            if r.values.get("host") is not None
        }
        return sorted(hosts)


# EOF
