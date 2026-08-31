#!/usr/bin/env python3
# Timestamp: "2026-08-29 (clew-postgres-store-migration)"
# File: src/scitex_clew/_db/_chain.py
"""Chain and DAG relationship operations for VerificationDB (Store-backed).

Every method reads via ``self._runs`` / ``self._session_parents``
(``scitex_dev.store.Store`` instances built in ``_core.py``) with a
Python-side filter/sort — Store has no WHERE/JOIN/ORDER-BY. No raw DB
import here: `set_parent`/`add_parent` write through `VerificationDB.put`
methods only (the legacy raw `runs` mirror and its `_mirror_run_field`
helper are gone).

The legacy raw `session_parents` table (and its startup backfill,
`_migrate_session_parents`) is RETIRED — a repo-wide grep found nothing
outside `_db/` ever read it, so there is nothing to mirror or migrate.
`get_dag`'s runs.parent_session FALLBACK (below) already gives the same
observable result live, at query time, without needing a backfill pass.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from scitex_dev.store import ANY_REVISION, NEW_RECORD


class ChainMixin:
    """Mixin providing chain and multi-parent DAG operations.

    Requires ``self._runs`` and ``self._session_parents`` (Store instances)
    from VerificationDB.
    """

    # -------------------------------------------------------------------------
    # Chain operations
    # -------------------------------------------------------------------------

    def get_chain(self, session_id: str) -> List[str]:
        """Get the chain of parent sessions for a given session.

        Parameters
        ----------
        session_id : str
            Session identifier

        Returns
        -------
        list of str
            List of session IDs from current to root
        """
        chain = [session_id]
        current = session_id
        while True:
            row = self._runs.get((current,))
            parent = row.values.get("parent_session") if row else None
            if not parent:
                break
            current = parent
            chain.append(current)
        return chain

    def get_children(self, session_id: str) -> List[str]:
        """Get child sessions that depend on this session."""
        children = [
            r for r in self._runs.rows() if r.values.get("parent_session") == session_id
        ]
        children.sort(key=lambda r: r.values.get("started_at") or "")
        return [r.values.get("session_id") for r in children]

    def set_parent(self, session_id: str, parent_session: str) -> None:
        """Set the parent session for a run.

        Parameters
        ----------
        session_id : str
            Session identifier
        parent_session : str
            Parent session identifier
        """
        self._runs.put(
            {"session_id": session_id, "parent_session": parent_session},
            expected_revision=ANY_REVISION,
        )
        self._record_parent_edge(session_id, parent_session)

    def add_parent(self, session_id: str, parent_session: str) -> None:
        """Add a parent relationship for a session.

        Stores in the junction table for multi-parent DAG support.
        Also sets runs.parent_session if currently NULL (backward compat).

        Parameters
        ----------
        session_id : str
            Child session identifier
        parent_session : str
            Parent session identifier
        """
        self._record_parent_edge(session_id, parent_session)

        # Set primary parent if not yet set (backward compat).
        current = self._runs.get((session_id,))
        if current is not None and current.values.get("parent_session") is None:
            self._runs.put(
                {"session_id": session_id, "parent_session": parent_session},
                expected_revision=ANY_REVISION,
            )

    def _record_parent_edge(self, session_id: str, parent_session: str) -> None:
        """INSERT OR IGNORE into session_parents (idempotent junction write)."""
        key = (session_id, parent_session)
        if self._session_parents.get(key) is not None:
            return
        self._session_parents.put(
            {
                "session_id": session_id,
                "parent_session": parent_session,
                "recorded_at": datetime.now().isoformat(),
            },
            expected_revision=NEW_RECORD,
        )

    def get_parents(self, session_id: str) -> List[str]:
        """Get all parent sessions for a given session.

        Parameters
        ----------
        session_id : str
            Session identifier

        Returns
        -------
        list of str
            List of parent session IDs
        """
        edges = [
            r
            for r in self._session_parents.rows()
            if r.values.get("session_id") == session_id
        ]
        edges.sort(key=lambda r: r.values.get("recorded_at") or "")
        return [r.values.get("parent_session") for r in edges]

    def get_dag(self, session_ids: List[str]) -> tuple:
        """BFS backward from leaf sessions to collect the full DAG.

        Parameters
        ----------
        session_ids : list of str
            Leaf session IDs to start from

        Returns
        -------
        tuple of (dict, set)
            - adjacency: {child_session: [parent_sessions, ...]}
            - all_ids: set of all session IDs in the DAG
        """
        from collections import deque

        adjacency: Dict[str, List[str]] = {}
        all_ids: set = set()
        queue = deque(session_ids)
        visited: set = set()

        while queue:
            sid = queue.popleft()
            if sid in visited:
                continue
            visited.add(sid)
            all_ids.add(sid)

            parents = self.get_parents(sid)

            # Fallback: if no junction table entries, check runs.parent_session.
            if not parents:
                row = self._runs.get((sid,))
                parent = row.values.get("parent_session") if row else None
                if parent:
                    parents = [parent]

            adjacency[sid] = parents
            for p in parents:
                all_ids.add(p)
                if p not in visited:
                    queue.append(p)

        # Ensure root nodes have empty parent lists.
        for sid in all_ids:
            if sid not in adjacency:
                adjacency[sid] = []

        return adjacency, all_ids


# EOF
