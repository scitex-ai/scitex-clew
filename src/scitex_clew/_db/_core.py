#!/usr/bin/env python3
# Timestamp: "2026-03-04 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_db.py
"""Store-backed database for verification tracking (sqlite-migration-scitex-clew-20260828).

Historically this module drove SQLite directly. It now drives
``scitex_dev.store.Store`` — a local file-backed target
(``StoreTarget.sqlite``), not a fleet Postgres — for the ``runs``,
``file_hashes``, ``verification_results`` and ``session_parents`` tables.
clew keeps its zero-Postgres-dependency, single-file-portability property;
only the *mechanism* moves off raw ``sqlite3`` calls onto the store's
oplog + hide/unhide primitives. Schemas live in ``_schema.py``, path
resolution in ``_paths.py`` (both split out of this file to respect the
project's 512-line limit; see ``GITIGNORED/REFACTORING.md``).

Store has NO WHERE/JOIN/ORDER-BY/LIMIT support: every query below is
``store.rows()`` (or ``store.get(key)`` for exact lookups) plus a Python
filter/sort/aggregate, an accepted O(n)-scan trade-off for what is normally
a small per-project DB.

DELIBERATE EXCEPTION — a legacy raw-sqlite *mirror* of ``runs`` and
``file_hashes`` (exact original schema) is still written on every
``add_run``/``finish_run``/``add_file_hash``/``add_file_hashes`` call, and
``VerificationDB._connect()`` still opens a raw ``sqlite3`` connection to
it. This is why ``import sqlite3`` remains in this file (only). As of this
PR's stacked follow-ups, the remaining call sites outside this migration's
scope that open a raw connection to ``db.db_path`` and read the
``runs``/``file_hashes`` tables directly (no public-API equivalent this PR
is permitted to introduce for them) are:

- ``src/scitex_clew/_gate_plugin.py`` (``SELECT COUNT(*) FROM runs``)
- ``src/scitex_clew/_attest/_stamp.py`` (``SELECT session_id, combined_hash FROM runs``)
- ``src/scitex_clew/_core/_node_class.py`` (reads/writes ``file_hashes.id``/``node_class``)
- ``src/scitex_clew/_estimate.py`` (five ``db._connect()`` call sites)

(``src/scitex_clew/_claim/_export.py`` — the two ``db._connect()`` call
sites inside ``_resolve_chain_flags``/``_resolve_exception_reasons`` — has
been migrated onto ``db._runs``/``db._file_hashes`` Store reads; see the
``sqlite-migration-scitex-clew-20260828`` card.)

``_gate_plugin.py``, ``_attest/*`` and ``_core/_node_class.py`` are named
exclusions from this PR's scope; ``_estimate.py`` is a sibling in-flight
migration. Breaking them silently was not an option, so the legacy tables
are kept as a write-only-by-us mirror: this module's own reads
(``get_run``, ``list_runs``, ``get_chain``, ...) go through the Store
exclusively; the mirror exists only so those remaining external call sites
keep working unmodified. See the PR description for the full rationale.

Legacy ``verification_results`` and ``session_parents`` raw tables are
RETIRED (no longer created or written) — a repo-wide grep found no code
outside ``_db/`` ever reads them directly, so there is nothing to mirror.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from scitex_dev.store import ANY_REVISION, Store, StoreTarget, WriterPolicy

from ._chain import ChainMixin
from ._connect import connect as _clew_sqlite_connect
from ._file_hashes import FileHashMixin
from ._paths import (
    _default_claims_json_path,
    _default_db_path,
    _find_project_root,
    resolve_db_path,
)
from ._queries import VerificationQueryMixin
from ._schema import (
    FILE_HASHES_SCHEMA,
    RUNS_SCHEMA,
    SESSION_PARENTS_SCHEMA,
    VERIFICATION_RESULTS_SCHEMA,
    resolve_node_id,
)

__all__ = [
    "VerificationDB",
    "get_active_db_path",
    "get_db",
    "resolve_db_path",
    "set_db",
    "use_db",
]


class VerificationDB(VerificationQueryMixin, FileHashMixin, ChainMixin):
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

    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        """
        Initialize database connection.

        Parameters
        ----------
        db_path : str or Path, optional
            Path to database file. Resolution order:
            1. Explicit db_path argument
            2. SCITEX_CLEW_DB_PATH environment variable
            3. {project_root}/.scitex/clew/runtime/clew.db where
               project_root is found by walking up from cwd until a
               .git / pyproject.toml is found; falls back to cwd if no
               root marker is found.
        """
        db_path, _tier = resolve_db_path(db_path)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        node = resolve_node_id()

        def _target(name: str) -> StoreTarget:
            return StoreTarget.sqlite(self.db_path, pkg="scitex_clew", name=name)

        self._runs = Store(
            _target("runs"), RUNS_SCHEMA, node=node, writer_policy=WriterPolicy.MULTI_WRITER
        )
        self._file_hashes = Store(
            _target("file_hashes"),
            FILE_HASHES_SCHEMA,
            node=node,
            writer_policy=WriterPolicy.MULTI_WRITER,
        )
        self._verifications = Store(
            _target("verification_results"),
            VERIFICATION_RESULTS_SCHEMA,
            node=node,
            writer_policy=WriterPolicy.MULTI_WRITER,
        )
        self._session_parents = Store(
            _target("session_parents"),
            SESSION_PARENTS_SCHEMA,
            node=node,
            writer_policy=WriterPolicy.MULTI_WRITER,
        )

        # Legacy raw-sqlite mirror of `runs` + `file_hashes` — see module
        # docstring for exactly why this stays.
        self._init_legacy_mirror()

    def _init_legacy_mirror(self) -> None:
        """Create (and additively migrate) the legacy `runs`/`file_hashes` mirror.

        Identical DDL to the pre-migration schema, minus `verification_results`
        and `session_parents` (retired — nothing outside `_db/` ever read them).
        """
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    session_id TEXT PRIMARY KEY,
                    script_path TEXT,
                    script_hash TEXT,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    status TEXT,
                    exit_code INTEGER,
                    parent_session TEXT,
                    combined_hash TEXT,
                    metadata TEXT,
                    provenance TEXT DEFAULT 'tracked',
                    exception_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS file_hashes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    size_bytes INTEGER,
                    frozen INTEGER DEFAULT 0,
                    host TEXT,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES runs(session_id),
                    UNIQUE(session_id, file_path, role)
                );

                CREATE INDEX IF NOT EXISTS idx_file_path
                    ON file_hashes(file_path);
                CREATE INDEX IF NOT EXISTS idx_session
                    ON file_hashes(session_id);
                CREATE INDEX IF NOT EXISTS idx_role
                    ON file_hashes(role);
                CREATE INDEX IF NOT EXISTS idx_hash
                    ON file_hashes(hash);
                CREATE INDEX IF NOT EXISTS idx_runs_status
                    ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_runs_parent
                    ON runs(parent_session);
                """
            )

        # Additive migrations for legacy mirror tables opened from an
        # older-shaped file (idempotent — see each method's docstring).
        self._migrate_runs_provenance()
        self._migrate_file_hashes_size_bytes()
        self._migrate_file_hashes_frozen()
        self._migrate_file_hashes_host()

    @contextmanager
    def _connect(self):
        """Context manager for the legacy raw-sqlite mirror connection.

        Kept ONLY because ``_estimate.py`` — out of scope for this
        migration — still calls this method directly (``_claim/_export.py``
        migrated off it; see the ``sqlite-migration-scitex-clew-20260828``
        card). Internal `_db` logic no longer uses it for reads;
        `get_run`/`list_runs`/etc. read the Store exclusively.
        """
        conn = _clew_sqlite_connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Migration helpers (legacy mirror only)
    # -------------------------------------------------------------------------

    def _migrate_runs_provenance(self) -> None:
        """Add provenance and exception_reason columns to pre-existing runs tables (idempotent).

        Safe to call even when the columns already exist: the PRAGMA check
        guards the ALTER TABLE so no exception is raised on repeated runs.
        Existing rows receive the default value ('tracked' / NULL) automatically.
        """
        with self._connect() as conn:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()
            }
            if "provenance" not in columns:
                conn.execute(
                    "ALTER TABLE runs ADD COLUMN provenance TEXT DEFAULT 'tracked'"
                )
            if "exception_reason" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN exception_reason TEXT")

    # -------------------------------------------------------------------------
    # Mirror write helpers
    # -------------------------------------------------------------------------

    def _mirror_run(self, values: Dict[str, Any]) -> None:
        """Full-replace mirror write for one `runs` row (matches legacy INSERT OR REPLACE)."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs
                (session_id, script_path, script_hash, started_at, finished_at,
                 status, exit_code, parent_session, combined_hash, metadata,
                 provenance, exception_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values.get("session_id"),
                    values.get("script_path"),
                    values.get("script_hash"),
                    values.get("started_at"),
                    values.get("finished_at"),
                    values.get("status"),
                    values.get("exit_code"),
                    values.get("parent_session"),
                    values.get("combined_hash"),
                    values.get("metadata"),
                    values.get("provenance"),
                    values.get("exception_reason"),
                ),
            )

    def _mirror_run_field(self, session_id: str, **fields: Any) -> None:
        """Partial mirror UPDATE for `runs` (matches legacy UPDATE ... WHERE session_id=?)."""
        if not fields:
            return
        with self._connect() as conn:
            set_clause = ", ".join(f"{name} = ?" for name in fields)
            conn.execute(
                f"UPDATE runs SET {set_clause} WHERE session_id = ?",
                (*fields.values(), session_id),
            )

    # -------------------------------------------------------------------------
    # Run operations
    # -------------------------------------------------------------------------

    def add_run(
        self,
        session_id: str,
        script_path: str,
        script_hash: Optional[str] = None,
        parent_session: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        provenance: str = "tracked",
        exception_reason: Optional[str] = None,
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
            "metadata": json.dumps(metadata) if metadata else None,
            "provenance": provenance,
            "exception_reason": exception_reason,
        }
        self._runs.put(values, expected_revision=ANY_REVISION)
        self._mirror_run(values)

    def finish_run(
        self,
        session_id: str,
        status: str = "success",
        exit_code: int = 0,
        combined_hash: Optional[str] = None,
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
        self._mirror_run_field(
            session_id,
            finished_at=finished_at,
            status=status,
            exit_code=exit_code,
            combined_hash=combined_hash,
        )

    def get_run(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get run information by session ID."""
        row = self._runs.get((session_id,))
        if row is None:
            return None
        return {name: row.values.get(name) for name in RUNS_SCHEMA.fields}

    def list_runs(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
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
        rows = self._runs.rows()
        if status:
            rows = [r for r in rows if r.values.get("status") == status]
        rows.sort(key=lambda r: r.values.get("started_at") or "", reverse=True)
        page = rows[offset : offset + limit]
        return [{name: r.values.get(name) for name in RUNS_SCHEMA.fields} for r in page]

    # -------------------------------------------------------------------------
    # File hash operations — implemented in FileHashMixin (_file_hashes.py)
    # -------------------------------------------------------------------------


# Global instance
_DB_INSTANCE: Optional[VerificationDB] = None


def get_db() -> VerificationDB:
    """Get or create the global database instance."""
    global _DB_INSTANCE
    if _DB_INSTANCE is None:
        _DB_INSTANCE = VerificationDB()
    return _DB_INSTANCE


def set_db(db_path: Union[str, Path]) -> VerificationDB:
    """Set the global database instance to use a specific path.

    Parameters
    ----------
    db_path : str or Path
        Path to database file (e.g. "./.scitex/clew/runtime/clew.db" for project-relative).

    Returns
    -------
    VerificationDB
        The new database instance.
    """
    global _DB_INSTANCE
    _DB_INSTANCE = VerificationDB(db_path=db_path)
    return _DB_INSTANCE


def get_active_db_path() -> Optional[Path]:
    """Return the path of the already-configured global DB instance, if any.

    ``None`` means no global instance has been created yet (neither
    ``get_db()`` nor ``set_db()`` has run in this process).
    """
    return _DB_INSTANCE.db_path if _DB_INSTANCE is not None else None


@contextmanager
def use_db(db_path: Union[str, Path]):
    """Temporarily point the global DB instance at ``db_path``.

    Restores the previous global instance on exit, so scoped out-of-tree
    reads (e.g. ``render_dag(..., db_path=...)``) do not leak into later
    calls in the same process.
    """
    global _DB_INSTANCE
    previous = _DB_INSTANCE
    _DB_INSTANCE = VerificationDB(db_path=db_path)
    try:
        yield _DB_INSTANCE
    finally:
        _DB_INSTANCE = previous


# EOF
