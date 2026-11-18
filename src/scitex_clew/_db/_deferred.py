#!/usr/bin/env python3
"""Deferred writes: a session's file rows reach the store in ONE transaction.

WHY
---
Every ``Store.put`` outside a batch is its own durable transaction, and a
durable commit waits on the disk. Recording a run's inputs one put at a time
therefore cost a commit (~4 ms of waiting, little CPU) per file: a session
reading 1000 files spent seconds blocked on the store, which is why recording
showed more wall time than CPU time.

WHAT
----
:class:`DeferredWritesMixin` (mixed into
:class:`~scitex_clew._db._scope.ProjectScopedStore`) lets a writer QUEUE a put
(:meth:`~DeferredWritesMixin.defer_put`). The queue is written, in order and
in one transaction, when ANY of these happens first:

* any other access to the same store in this process — a read
  (``rows`` / ``search`` / ``get``), an immediate write, a ``batch`` — so a
  reader in this process always sees what was queued (read-your-writes);
* the session closes (the tracker flushes explicitly);
* the queue reaches :data:`MAX_PENDING` rows (bounds memory and what a crash
  could lose);
* the store is closed, or the interpreter exits (``atexit``).

What is written is exactly what immediate puts would have written — the same
rows, the same values (each row carries the time it was RECORDED, not the
time it was flushed), the same order. Only the number of commits changes.

* the oldest queued row has waited :func:`flush_interval` seconds (so a
  long run's rows become visible to other processes while it runs).

A process killed outright (``SIGKILL``, OOM, a harness timeout) runs none of
these. A row queued with a ``journal`` (every row a session tracker queues)
is therefore also appended to that session's journal file
(:mod:`scitex_clew._journal`) as it is queued, and a ``flushed`` marker is
appended once the OUTERMOST transaction holding it commits — never before, so
a marker always means "in the store". The next clew start replays what a dead
process left unflushed. A failed flush is never swallowed: it raises to the
caller (the session close hook records it on the run) and the queue is kept
for the next flush.
"""

from __future__ import annotations

import atexit
import os
import threading
import time
import weakref
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any

from scitex_dev.store import ANY_REVISION

from .._core._logging import getLogger

logger = getLogger(__name__)

__all__ = [
    "FLUSH_SECONDS_ENV",
    "MAX_PENDING",
    "DeferredWritesMixin",
    "flush_all_deferred",
    "flush_interval",
]

#: Queue length that forces a flush.
MAX_PENDING = 500

#: Seconds the oldest queued row may wait before a queue write flushes.
FLUSH_SECONDS_ENV = "SCITEX_CLEW_FLUSH_SECONDS"
_DEFAULT_FLUSH_SECONDS = 30.0


def flush_interval() -> float:
    """:data:`FLUSH_SECONDS_ENV` (default 30 s; ``0`` = flush every row)."""
    raw = os.environ.get(FLUSH_SECONDS_ENV, "").strip()
    try:
        return max(0.0, float(raw)) if raw else _DEFAULT_FLUSH_SECONDS
    except ValueError:
        return _DEFAULT_FLUSH_SECONDS

#: Stores holding queued rows, flushed at interpreter exit.
_WITH_PENDING: weakref.WeakSet = weakref.WeakSet()
_ATEXIT_REGISTERED = False


def flush_all_deferred() -> int:
    """Flush every store's queue (``atexit``); returns the rows written."""
    written = 0
    for store in list(_WITH_PENDING):
        try:
            written += store.flush()
        except Exception as exc:  # noqa: BLE001 - at exit there is no caller
            logger.warning(
                "clew: could not write %d queued provenance row(s) at exit (%s: "
                "%s) — those records are LOST",
                store.pending,
                type(exc).__name__,
                exc,
            )
    return written


def _ensure_atexit() -> None:
    global _ATEXIT_REGISTERED
    if not _ATEXIT_REGISTERED:
        atexit.register(flush_all_deferred)
        _ATEXIT_REGISTERED = True


class DeferredWritesMixin:
    """Queued puts on a ``ProjectScopedStore`` (see module doc).

    Requires ``self._store`` (the raw ``Store``) and ``self._values`` (scope
    stamping). Call :meth:`_init_deferred` from ``__init__`` and
    :meth:`flush` at the top of every other store access.
    """

    def _init_deferred(self) -> None:
        #: ``(values, journal, seq)``: the row, and where it is journaled.
        self._pending: list[tuple[dict, Any, int]] = []
        self._pending_lock = threading.RLock()
        self._flushing = False
        self._oldest_at = 0.0
        self._interval = flush_interval()
        #: journal -> highest seq written but not yet COMMITTED (nested batch).
        self._uncommitted: dict[Any, int] = {}
        self._batch_depth = 0

    @property
    def pending(self) -> int:
        """Queued rows not yet written."""
        return len(self._pending)

    def defer_put(self, values: Mapping[str, Any], journal=None) -> None:
        """Queue ``put(values, expected_revision=ANY_REVISION)``.

        ``journal`` (a :class:`~scitex_clew._journal.SessionJournal`) gets the
        row appended NOW, so a kill before the flush cannot lose it.
        """
        with self._pending_lock:
            stamped = self._values(values)
            seq = journal.row(stamped) if journal is not None else 0
            if not self._pending:
                self._oldest_at = time.monotonic()
            self._pending.append((stamped, journal if seq else None, seq))
            _WITH_PENDING.add(self)
            _ensure_atexit()
            full = len(self._pending) >= MAX_PENDING or (
                time.monotonic() - self._oldest_at >= self._interval
            )
        if full:
            self.flush()

    def flush(self) -> int:
        """Write the queue in ONE transaction, in order; returns rows written.

        On failure the transaction rolls back, the queue is KEPT and the error
        propagates — nothing is dropped silently.
        """
        with self._pending_lock:
            if not self._pending or self._flushing:
                return 0
            batch = list(self._pending)
            self._flushing = True
            try:
                with self._store.batch():
                    for values, _journal, _seq in batch:
                        self._store.put(values, expected_revision=ANY_REVISION)
            finally:
                self._flushing = False
            del self._pending[: len(batch)]
            if not self._pending:
                _WITH_PENDING.discard(self)
            for _values, journal, seq in batch:
                if journal is not None and seq > self._uncommitted.get(journal, 0):
                    self._uncommitted[journal] = seq
            if self._batch_depth == 0:
                self._mark_committed()
            return len(batch)

    def _mark_committed(self) -> None:
        """Tell each journal its rows are in the store (outermost commit only)."""
        marks, self._uncommitted = self._uncommitted, {}
        for journal, seq in marks.items():
            journal.flushed(seq)

    @contextmanager
    def _tracked_batch(self):
        """``Store.batch`` that marks journals only when the OUTERMOST commits."""
        with self._pending_lock:
            self._batch_depth += 1
        try:
            with self._store.batch() as store:
                yield store
        except BaseException:
            with self._pending_lock:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    self._uncommitted.clear()  # rolled back: not in the store
            raise
        with self._pending_lock:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self._mark_committed()

# EOF
