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

What a deferral can lose: rows queued in a process killed outright
(``SIGKILL``, power loss) before any of the triggers above. Such a run never
closed, so it is not evidence either way; its run record stays ``running``.
A failed flush is never swallowed: it raises to the caller (the session
close hook records it on the run) and the queue is kept for the next flush.
"""

from __future__ import annotations

import atexit
import threading
import weakref
from collections.abc import Mapping
from typing import Any

from scitex_dev.store import ANY_REVISION

from .._core._logging import getLogger

logger = getLogger(__name__)

__all__ = ["MAX_PENDING", "DeferredWritesMixin", "flush_all_deferred"]

#: Queue length that forces a flush.
MAX_PENDING = 500

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
        self._pending: list[dict] = []
        self._pending_lock = threading.RLock()
        self._flushing = False

    @property
    def pending(self) -> int:
        """Queued rows not yet written."""
        return len(self._pending)

    def defer_put(self, values: Mapping[str, Any]) -> None:
        """Queue ``put(values, expected_revision=ANY_REVISION)``."""
        with self._pending_lock:
            self._pending.append(self._values(values))
            _WITH_PENDING.add(self)
            _ensure_atexit()
            full = len(self._pending) >= MAX_PENDING
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
                    for values in batch:
                        self._store.put(values, expected_revision=ANY_REVISION)
            finally:
                self._flushing = False
            del self._pending[: len(batch)]
            if not self._pending:
                _WITH_PENDING.discard(self)
            return len(batch)


# EOF
