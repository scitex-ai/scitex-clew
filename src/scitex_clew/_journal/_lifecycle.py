#!/usr/bin/env python3
"""A tracker's journal over its life: open, SIGTERM/SIGHUP, interpreter exit.

How each way a run can end is recorded
--------------------------------------
* **Closed** (``on_session_close`` / ``stop_tracking`` / ``clew.session``
  exit): the queue is flushed, the run finished, the journal deleted.
* **Interpreter exit with the session still open** (the script returned or
  called ``sys.exit`` without closing; ``SIGINT`` that nobody caught ends up
  here as an uncaught ``KeyboardInterrupt``): ``atexit`` records the captured
  files and closes the run with status ``incomplete``.
* **SIGTERM / SIGHUP** (a harness timeout, a closed terminal) — whose default
  action ends the process WITHOUT exit handlers: when the handler slot is the
  default, clew installs one that records the signal in the journal, writes
  everything the journal holds and closes the run as ``killed`` (exit code
  ``-signum``), then restores the default action and re-sends the signal, so
  the process still dies of it, exactly as before. If the signal interrupted
  a store write (a transaction may be open on the connection), nothing is
  written from the handler; the journal holds it all for the next start.
  A handler someone else installed is left alone (it usually exits, which
  reaches the ``atexit`` path).
* **SIGKILL / OOM / power cut of the container**: nothing runs. The journal
  holds every row recorded up to the kill; the next clew start on this
  machine (or ``clew recover-journals``) replays it and closes the run as
  ``killed`` (:mod:`._recover`).
"""

from __future__ import annotations

import os
import signal
import threading
from typing import Any

from .._core._logging import getLogger
from ._file import SessionJournal, journal_enabled

logger = getLogger(__name__)

__all__ = ["finish_at_exit", "install_signal_handlers", "open_journal"]

_SIGNALS = tuple(
    s for s in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGHUP", None)) if s
)
_INSTALLED: set[int] = set()

#: Modules whose frames on the interrupted stack mean a store call is under way.
_STORE_MODULES = ("scitex_dev.store", "psycopg", "scitex_clew._db")


def open_journal(tracker) -> SessionJournal | None:
    """Create ``tracker``'s journal (None when off or impossible — warned)."""
    if not journal_enabled():
        return None
    db = tracker._db
    fingerprint = getattr(db, "store_fingerprint", None)
    project = getattr(getattr(db, "_runs", None), "project", None)
    if fingerprint is None or project is None:
        return None
    from .._db._file_hashes import _resolve_host

    return SessionJournal.create(
        tracker.session_id,
        project=project,
        store=fingerprint,
        row_host=_resolve_host(),
    )


def install_signal_handlers() -> None:
    """Handle SIGTERM/SIGHUP where their action is the default (main thread)."""
    if (
        not journal_enabled()
        or threading.current_thread() is not threading.main_thread()
    ):
        return
    for signum in _SIGNALS:
        if signum in _INSTALLED:
            continue
        try:
            if signal.getsignal(signum) is signal.SIG_DFL:
                signal.signal(signum, _on_terminate)
                _INSTALLED.add(signum)
        except (ValueError, OSError):  # not the main interpreter / unsupported
            continue


def _on_terminate(signum: int, frame) -> None:
    try:
        _record_termination(signum, frame)
    except Exception as exc:  # noqa: BLE001 - the journal still holds the run
        logger.warning(
            "clew: could not close the run on signal %d (%s: %s) — its journal "
            "is kept and replayed at the next clew start",
            signum,
            type(exc).__name__,
            exc,
        )
    finally:
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)


def _store_busy(db, frame) -> bool:
    """True when the signal interrupted a store write (a transaction may be open)."""
    stores = [getattr(db, "_runs", None), getattr(db, "_file_hashes", None)]
    stores += list(getattr(db, "_lazy", {}).values())
    for store in stores:
        if store is not None and (
            getattr(store, "_flushing", False) or getattr(store, "_batch_depth", 0)
        ):
            return True
    while frame is not None:
        if frame.f_globals.get("__name__", "").startswith(_STORE_MODULES):
            return True
        frame = frame.f_back
    return False


def _owned_tracker():
    from .._tracker import get_tracker

    tracker = get_tracker()
    if tracker is None or tracker._finalized:
        return None
    if getattr(tracker, "_pid", None) != os.getpid():
        return None  # a forked child: the parent owns the run
    return tracker


def _record_termination(signum: int, frame) -> None:
    tracker = _owned_tracker()
    if tracker is None:
        return
    journal = tracker._journal
    if journal is None:
        return
    journal.signal(signum)
    if _store_busy(tracker._db, frame):
        return  # the journal is replayed at the next start instead
    from ._recover import recover_journal

    # Producers of the queued inputs are bound in memory; the journal replay
    # binds every input again, so both paths agree.
    tracker.flush_pending()
    journal.close(delete=False)
    tracker._journal = None
    recover_journal(journal.path, db=tracker._db)
    tracker._finalized = True


def finish_at_exit() -> dict[str, Any] | None:
    """``atexit``: close a still-open session as ``incomplete``.

    Records what the session's capture saw (as a close would) and finalizes
    the run; on failure the journal is kept for recovery.
    """
    tracker = _owned_tracker()
    if tracker is None:
        return None
    try:
        from .. import _capture

        summary = _capture.finish(tracker)
        if summary is not None:
            tracker._db.merge_run_metadata(tracker.session_id, {"capture": summary})
        return tracker.finalize(status="incomplete", exit_code=None)
    except Exception as exc:  # noqa: BLE001 - at exit there is no caller
        logger.warning(
            "clew: could not close session %s at exit (%s: %s) — its journal is "
            "kept and replayed at the next clew start",
            tracker.session_id,
            type(exc).__name__,
            exc,
        )
        return None


# EOF
