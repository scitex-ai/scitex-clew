#!/usr/bin/env python3
"""Read-through cache of the store reads ONE verify pass makes.

A ``verify`` of a claim touches each run of its slice several times: the
slice walk reads the run's file rows and binds its inputs, the per-run check
reads the rows again (hashes, frozen flags, external inputs), re-binds the
inputs to find failed parents, and the environment / symlink / notebook
records read the run row once each. Uncached, those were a dozen store
round trips per run.

:class:`PassRecords` wraps a ``VerificationDB`` for the life of one pass:

* ``session_file_records(sid)`` — one query per session, then every
  per-session view (:class:`~scitex_clew._db._record_views.RecordViewsMixin`)
  is derived from it;
* ``get_run(sid)`` — one point read per run;
* ``find_producer_records(paths)`` — only paths not seen yet in this pass are
  queried, in ONE query.

Everything else passes through to the wrapped database. The cache lives as
long as the pass (it is never module-global), so a file or run changed
between two passes is always read afresh. ``verify`` only READS the
provenance tables, so nothing it caches can go stale within the pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .._db._record_views import RecordViewsMixin

__all__ = ["PassRecords", "pass_records"]


class PassRecords(RecordViewsMixin):
    """A ``VerificationDB`` whose provenance reads are memoized (see module doc)."""

    def __init__(self, db) -> None:
        self._db = db
        self._files: dict[str, list[dict]] = {}
        self._runs: dict[str, dict | None] = {}
        self._producers: dict[str, list[dict]] = {}

    def __getattr__(self, name: str) -> Any:
        # Only reached for attributes not defined here: pass through.
        return getattr(self._db, name)

    @property
    def wrapped(self):
        """The underlying database."""
        return self._db

    def session_file_records(self, session_id: str) -> list[dict]:
        if session_id not in self._files:
            self._files[session_id] = self._db.session_file_records(session_id)
        return self._files[session_id]

    def get_run(self, session_id: str) -> dict | None:
        if session_id not in self._runs:
            self._runs[session_id] = self._db.get_run(session_id)
        run = self._runs[session_id]
        return dict(run) if run is not None else None

    def find_producer_records(self, file_paths: list[str]) -> dict[str, list[dict]]:
        """Same contract as ``VerificationDB.find_producer_records``: keyed by
        the caller's first spelling of each resolved path, absent when none."""
        resolved_to_original: dict[str, str] = {}
        for original in file_paths:
            resolved_to_original.setdefault(str(Path(original).resolve()), original)
        missing = [p for p in resolved_to_original if p not in self._producers]
        if missing:
            found = self._db.find_producer_records(missing)
            for path in missing:
                self._producers[path] = found.get(path, [])
        return {
            original: [dict(r) for r in self._producers[path]]
            for path, original in resolved_to_original.items()
            if self._producers[path]
        }


def pass_records(db):
    """``db`` wrapped for one pass.

    Only a real :class:`~scitex_clew._db._core.VerificationDB` is wrapped (an
    already-wrapped one is reused as is): a hand-rolled stand-in injected
    through a ``db_factory`` seam keeps its own lookup semantics.
    """
    from .._db._core import VerificationDB

    return PassRecords(db) if isinstance(db, VerificationDB) else db


# EOF
