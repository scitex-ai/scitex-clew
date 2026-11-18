#!/usr/bin/env python3
# Timestamp: "2026-03-04 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_db.py
"""Store-backed database for verification tracking.

This module drives ``scitex_dev.store.Store`` for the ``runs``,
``file_hashes``, ``verification_results``, ``session_parents`` and
``environments`` (package provenance once per environment,
``_environments.py``) tables.
The target is resolved by :func:`scitex_dev.store.host_store` — THE store
this host uses, per ADR-0006 — and nothing here constructs a DSN or a file
path of its own. There is exactly one switch (``SCITEX_STORE_DSN``, read by
``host_store()``), not a constant per call site.

Storage is the per-host PostgreSQL instance. clew has no database file: an
earlier revision of this module used a local file-backed target for a
"portable single file, zero fleet infrastructure" property, and that
rationale is overruled — a file store has no concept of WHO, so handing a
collaborator one is sharing, not collaborating. What is genuinely lost by
the change is recorded in the PR body, not papered over here.

The four stores differ only by ``name=``, which is what separates their
tables inside the one database. What separates one PROJECT's records from
another's inside those tables is the ``project`` identity field — see
``_scope.py``, which resolves the scope once for reads and writes alike.
The per-project database file used to do that job; nothing else would have
picked it up.

Point reads are ``store.get(key)``; filtered reads are
``store.search(Query...)`` (WHERE / ORDER BY / LIMIT in SQL), so a lookup
decodes only the rows it returns. ``store.rows()`` (a whole project) is kept
for genuinely whole-project views.

Schemas live in ``_schema.py``; the project-root walk that resolves the
regenerable ``claims.json`` artifact lives in ``_paths.py`` (both split out
of this file to respect the project's 512-line limit; see
``GITIGNORED/REFACTORING.md``).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from scitex_dev.store import ANY_REVISION, Store, WriterPolicy, host_store

from ._chain import ChainMixin
from ._content_queries import ContentQueryMixin
from ._environments import EnvironmentStoreMixin
from ._file_hashes import FileHashMixin

#: Re-exported: several modules import these from ``._db._core``.
from ._paths import (  # noqa: F401
    _default_claims_json_path,
    _default_hints_json_path,
    _find_project_root,
)
from ._queries import VerificationQueryMixin
from ._relocate import RelocationMixin
from ._schema import (
    FILE_HASHES_SCHEMA,
    RUNS_SCHEMA,
    SESSION_PARENTS_SCHEMA,
    VERIFICATION_RESULTS_SCHEMA,
    resolve_node_id,
)
from ._scope import ProjectScopedStore

__all__ = [
    "VerificationDB",
    "get_db",
    "reset_db",
]


class VerificationDB(
    VerificationQueryMixin,
    FileHashMixin,
    ContentQueryMixin,
    RelocationMixin,
    ChainMixin,
    EnvironmentStoreMixin,
):
    """
    Store-backed database for tracking session runs and file hashes.

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

    def __init__(self, project: str | None = None) -> None:
        """Open clew's four stores against THE store this host uses.

        Takes no path and no DSN. ``host_store()`` answers "which store does
        this host use" — ``SCITEX_STORE_DSN`` when set, otherwise the
        per-host Postgres over its UNIX socket — and it is the only switch.

        ``project`` pins the scope instead of resolving it from the working
        directory — for replaying a journal written by another project's run
        (:mod:`scitex_clew._journal`), whose rows already carry their scope.
        """
        node = resolve_node_id()

        # Every store is project-scoped: one host database holds every
        # project on this machine, and clew keys like ``claim_id`` and
        # ``cite_key`` are author-chosen. See ``_scope.py`` — the scope is
        # resolved there, once, for reads and writes alike.
        #
        # WHICH store and WHICH project are decided here, at construction,
        # for all four — even the two opened lazily below — so a store opened
        # later can never answer for a different target or project.
        targets = {
            name: host_store(pkg="scitex_clew", name=name)
            for name in (
                "runs",
                "file_hashes",
                "verification_results",
                "session_parents",
                "environments",
            )
        }

        def _open(name: str, schema, project: str | None = None) -> ProjectScopedStore:
            return ProjectScopedStore(
                Store(
                    targets[name],
                    schema,
                    node=node,
                    writer_policy=WriterPolicy.MULTI_WRITER,
                ),
                project=project,
            )

        #: Which store this is, without the DSN (it may hold a password).
        from .._journal._file import store_fingerprint

        self.store_fingerprint = store_fingerprint(targets["runs"].dsn)
        self._runs = _open("runs", RUNS_SCHEMA, project)
        self._file_hashes = _open("file_hashes", FILE_HASHES_SCHEMA, self._runs.project)
        # Opened on first use: opening a store is a connection plus its
        # schema checks (~0.2 s), and a recording session never touches
        # verification results and rarely the parent junction.
        self._opener = _open
        self._lazy: dict[str, ProjectScopedStore] = {}
        self._env_cache: dict[str, dict] = {}

    def _lazy_store(self, name: str, schema) -> ProjectScopedStore:
        if name not in self._lazy:
            self._lazy[name] = self._opener(name, schema, self._runs.project)
        return self._lazy[name]

    @property
    def _verifications(self) -> ProjectScopedStore:
        return self._lazy_store("verification_results", VERIFICATION_RESULTS_SCHEMA)

    @property
    def _session_parents(self) -> ProjectScopedStore:
        return self._lazy_store("session_parents", SESSION_PARENTS_SCHEMA)

    # -------------------------------------------------------------------------
    # Run operations
    # -------------------------------------------------------------------------

    def add_run(
        self,
        session_id: str,
        script_path: str,
        script_hash: str | None = None,
        parent_session: str | None = None,
        metadata: dict[str, Any] | None = None,
        provenance: str = "tracked",
        exception_reason: str | None = None,
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
        values = {
            "session_id": session_id,
            "script_path": script_path,
            "script_hash": script_hash,
            "started_at": datetime.now().isoformat(),
            # A re-registration (add_run called again for an existing
            # session_id) FULL-REPLACES the row under the original
            # `INSERT OR REPLACE` semantics — terminal fields reset.
            # Store's put() is a PARTIAL update, so these are passed
            # explicitly to reproduce the reset.
            "finished_at": None,
            "status": "running",
            "exit_code": None,
            "parent_session": parent_session,
            "combined_hash": None,
            # package provenance is stored once per environment and
            # referenced here (``_environments.py``)
            "metadata": self._metadata_json(metadata),
            "provenance": provenance,
            "exception_reason": exception_reason,
        }
        self._runs.put(values, expected_revision=ANY_REVISION)

    def finish_run(
        self,
        session_id: str,
        status: str = "success",
        exit_code: int = 0,
        combined_hash: str | None = None,
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
        finished_at = datetime.now().isoformat()
        self._runs.put(
            {
                "session_id": session_id,
                "finished_at": finished_at,
                "status": status,
                "exit_code": exit_code,
                "combined_hash": combined_hash,
            },
            expected_revision=ANY_REVISION,
        )

    def merge_run_metadata(self, session_id: str, extra: dict[str, Any]) -> bool:
        """Merge ``extra`` into a run's JSON metadata (list values extend).

        Returns False when the run does not exist. Used to attach capture
        failures reported after the run record was opened (e.g. a
        session-close payload, or a failed clew hook).
        """
        row = self._runs.get((session_id,))
        if row is None:
            return False
        # the row as stored (a provenance reference stays a reference)
        raw = row.values.get("metadata")
        meta = json.loads(raw) if raw else {}
        for key, value in extra.items():
            if isinstance(value, list) and isinstance(meta.get(key), list):
                meta[key] = meta[key] + value
            else:
                meta[key] = value
        self._runs.put(
            {"session_id": session_id, "metadata": self._metadata_json(meta, default=str)},
            expected_revision=ANY_REVISION,
        )
        return True

    def get_run(self, session_id: str) -> dict[str, Any] | None:
        """Get run information by session ID."""
        row = self._runs.get((session_id,))
        if row is None:
            return None
        return self._run_dict(row)

    def _run_dict(self, row) -> dict[str, Any]:
        """A run row as a dict, its package-provenance reference resolved."""
        out = {name: row.values.get(name) for name in RUNS_SCHEMA.fields}
        out["metadata"] = self._resolve_metadata(out["metadata"])
        return out

    def list_runs(
        self,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
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
        from scitex_dev.store import Query, eq

        # Filtered, ordered and paged in SQL: only the page is decoded.
        query = Query().ordered_by("started_at", descending=True)
        if status:
            query = query.where(eq("status", status))
        page = self._runs.search(query.limited(limit, offset=offset))
        return [self._run_dict(r) for r in page]

    # -------------------------------------------------------------------------
    # File hash operations — implemented in FileHashMixin (_file_hashes.py)
    # -------------------------------------------------------------------------

    def close(self) -> None:
        """Close every opened store (queued rows are written first).

        Idempotent — Store.close() tolerates repeats. A store never opened is
        not opened just to be closed.
        """
        for store in (self._runs, self._file_hashes, *self._lazy.values()):
            store.close()


# Global instance
_DB_INSTANCE: VerificationDB | None = None


#: One instance per explicit project root (``project_root=`` / ``with
#: scitex_clew.project_root(...)``); each captures that project's scope.
_ROOT_DB_INSTANCES: dict[str, VerificationDB] = {}


def get_db() -> VerificationDB:
    """Get or create the database instance for the current project.

    Inside a :func:`scitex_clew._db._paths.project_root` block the instance is
    scoped to that root's project; otherwise the cwd-resolved global one.
    """
    global _DB_INSTANCE
    from ._paths import project_root_override

    root = project_root_override()
    if root is not None:
        key = str(root)
        if key not in _ROOT_DB_INSTANCES:
            _ROOT_DB_INSTANCES[key] = VerificationDB()
        return _ROOT_DB_INSTANCES[key]
    if _DB_INSTANCE is None:
        _DB_INSTANCE = VerificationDB()
    return _DB_INSTANCE


def reset_db() -> None:
    """Drop the cached global instance so the next ``get_db()`` re-resolves.

    ``host_store()`` reads ``SCITEX_STORE_DSN`` once per ``VerificationDB``
    construction, and ``get_db()`` caches the instance for the life of the
    process. Anything that changes which store this process should reach —
    a test that gives itself a throwaway schema, an operator flipping the
    env var — must call this so the change is actually picked up.

    This is NOT a store selector. The selector is ``SCITEX_STORE_DSN``,
    owned by the primitive; this only invalidates a cache.
    """
    global _DB_INSTANCE
    if _DB_INSTANCE is not None:
        _DB_INSTANCE.close()
    _DB_INSTANCE = None
    for db in _ROOT_DB_INSTANCES.values():
        db.close()
    _ROOT_DB_INSTANCES.clear()


# EOF
