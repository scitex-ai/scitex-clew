#!/usr/bin/env python3
"""The per-session journal file: what a killed run had recorded.

WHY
---
clew 0.30.0 queues a session's file rows in memory and writes them to the
store in one transaction (:mod:`scitex_clew._db._deferred`). A process killed
outright (``SIGKILL``, the OOM killer, a container or agent-harness timeout, a
dead kernel) runs no exit handler, so its queue — every input and output the
run had recorded — was lost and its run record stayed ``running``. Agent
harnesses kill runs on timeouts routinely, so the record went missing exactly
where it matters.

WHAT
----
Every queued row is ALSO appended to this file the moment it is queued: one
``os.write`` of one JSON line on an ``O_APPEND`` descriptor. The bytes are in
the kernel's page cache when ``write`` returns, so they survive the death of
the process (not a power loss — that is what the store's commit is for; the
journal never ``fsync``s, which keeps recording at its 0.30.0 cost). When the
store commits the rows, a ``flushed`` marker is appended. A session that
closes normally deletes its journal; one that does not leaves it behind for
:func:`~scitex_clew._journal._recover.recover_journals`.

Liveness is an advisory lock, not a pid check: the owner holds ``flock``
(``LOCK_EX``) on the file for its whole life and the kernel drops it when the
process dies, however it dies. A journal whose lock can be taken has no live
owner. Pids are reused; locks are not inherited by an ``exec``'d program
(``O_CLOEXEC``), and a ``fork``'d child that shares the session keeps the lock
— and the session — alive until it exits too.

Layout: ``$SCITEX_CLEW_JOURNAL_DIR`` (default ``$SCITEX_DIR/clew/journal``,
i.e. ``~/.scitex/clew/journal``) ``/<host>/<session>.<pid>.jsonl``, mode 0600.
Lines (``k`` = kind)::

    {"k": "h", "v": 1, "session_id", "project", "store", "pid", "host",
     "row_host", "started_at"}                         header (always first)
    {"k": "r", "s": seq, "row": {...}}                  a queued file_hashes row
    {"k": "f", "s": seq}                                rows <= seq committed
    {"k": "c", "path", "hash", "size", "external", "at"}  captured input
    {"k": "w", "path"}                                  captured write target
    {"k": "x", "signal": n, "at"}                       terminating signal seen

``store`` is a fingerprint (SHA-256 prefix) of the store DSN — never the DSN,
which may carry a password — so a journal is replayed only into the store its
rows were meant for.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import socket
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .._core._logging import getLogger

logger = getLogger(__name__)

__all__ = [
    "JOURNAL_DIR_ENV",
    "JOURNAL_ENV",
    "SessionJournal",
    "journal_dir",
    "journal_enabled",
    "store_fingerprint",
]

#: ``0`` / ``false`` / ``no`` / ``off`` disables the journal (and the SIGTERM
#: / SIGHUP handlers that write to it). A kill then loses the queued rows.
JOURNAL_ENV = "SCITEX_CLEW_JOURNAL"

#: Directory that holds the per-host journal directories.
JOURNAL_DIR_ENV = "SCITEX_CLEW_JOURNAL_DIR"

_FALSY = {"0", "false", "no", "off"}
_VERSION = 1
_SAFE = re.compile(r"[^A-Za-z0-9_.-]")

#: Journals THIS process holds open (recovery never touches them).
_OWN: set[str] = set()
_OWN_LOCK = threading.Lock()


def journal_enabled() -> bool:
    """False when :data:`JOURNAL_ENV` turns the journal off."""
    return os.environ.get(JOURNAL_ENV, "1").strip().lower() not in _FALSY


def _safe(name: str) -> str:
    cleaned = _SAFE.sub("_", name)[:120]
    if cleaned != name:
        cleaned += "-" + hashlib.sha256(name.encode()).hexdigest()[:8]
    return cleaned or "unnamed"


def _machine() -> str:
    """The machine whose kernel holds the locks (not a logical host alias)."""
    try:
        return socket.gethostname() or "localhost"
    except OSError:
        return "localhost"


def journal_dir() -> Path:
    """This machine's journal directory (see module doc for the layout)."""
    override = os.environ.get(JOURNAL_DIR_ENV)
    if override:
        base = Path(override).expanduser()
    else:
        from .._core._config import _user_root

        base = _user_root() / "journal"
    return base / _safe(_machine())


def store_fingerprint(dsn: str) -> str:
    """A non-reversible identity for the store ``dsn`` names."""
    return hashlib.sha256(dsn.encode("utf-8")).hexdigest()[:24]


def own_paths() -> set[str]:
    with _OWN_LOCK:
        return set(_OWN)


def _now() -> str:
    return datetime.now().isoformat()


class SessionJournal:
    """Append-only journal of ONE session (see module doc).

    Every append is a no-op in a forked child (the parent owns the session's
    record) and after a write failure (warned once: the run is then only as
    durable as 0.30.0 made it).
    """

    def __init__(self, path: Path, fd: int, header: dict[str, Any]) -> None:
        self.path = path
        self._fd: int | None = fd
        self.header = header
        self.pid = os.getpid()
        self._seq = 0
        self._lock = threading.Lock()
        self.broken: str | None = None

    # ------------------------------------------------------------- creation
    @classmethod
    def create(
        cls, session_id: str, *, project: str, store: str, row_host: str | None
    ) -> SessionJournal | None:
        """Create, lock and publish a journal; None (warned) when impossible.

        The file is written under a hidden temporary name, locked, given its
        header and only then renamed into place, so recovery never sees a
        journal that has no owner lock or no header.
        """
        if not journal_enabled():
            return None
        pid = os.getpid()
        directory = journal_dir()
        final = directory / f"{_safe(session_id)}.{pid}.jsonl"
        temp = directory / f".{final.name}.tmp"
        header = {
            "k": "h",
            "v": _VERSION,
            "session_id": session_id,
            "project": project,
            "store": store,
            "pid": pid,
            "host": _machine(),
            "row_host": row_host,
            "started_at": _now(),
        }
        fd = None
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            fd = os.open(temp, flags | getattr(os, "O_CLOEXEC", 0), 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _write_all(fd, _line(header))
            os.replace(temp, final)
        except OSError as exc:
            if fd is not None:
                os.close(fd)
                try:
                    os.unlink(temp)
                except OSError:
                    pass
            logger.warning(
                "clew: could not create the recording journal for session %s "
                "in %s (%s: %s) — if this process is killed before the session "
                "closes, the rows it queued are LOST",
                session_id,
                directory,
                type(exc).__name__,
                exc,
            )
            return None
        with _OWN_LOCK:
            _OWN.add(str(final))
        return cls(final, fd, header)

    # --------------------------------------------------------------- appends
    def _append(self, event: dict[str, Any]) -> bool:
        if self._fd is None or self.broken or os.getpid() != self.pid:
            return False
        try:
            _write_all(self._fd, _line(event))
        except (OSError, TypeError, ValueError) as exc:
            self.broken = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "clew: recording journal %s stopped (%s) — rows queued from now "
                "on are lost if this process is killed before the session closes",
                self.path,
                self.broken,
            )
            return False
        return True

    def row(self, values: dict[str, Any]) -> int:
        """Journal one queued store row; returns its sequence number (0 = not)."""
        with self._lock:
            self._seq += 1
            seq = self._seq
            return seq if self._append({"k": "r", "s": seq, "row": values}) else 0

    def flushed(self, seq: int) -> None:
        """Rows up to ``seq`` are COMMITTED to the store."""
        if seq:
            with self._lock:
                self._append({"k": "f", "s": seq})

    def captured_read(
        self, path: str, digest: str, size: int | None, external: dict | None
    ) -> None:
        """An ``open()`` read hashed now and recorded at close (see _capture)."""
        with self._lock:
            self._append(
                {
                    "k": "c",
                    "path": path,
                    "hash": digest,
                    "size": size,
                    "external": external,
                    "at": _now(),
                }
            )

    def captured_write(self, path: str) -> None:
        """A file opened for writing; its final bytes are hashed at close."""
        with self._lock:
            self._append({"k": "w", "path": path})

    def signal(self, signum: int) -> None:
        """A terminating signal arrived (written from the signal handler)."""
        self._append({"k": "x", "signal": int(signum), "at": _now()})

    # ---------------------------------------------------------------- close
    def close(self, *, delete: bool) -> None:
        """Release the lock; ``delete`` once the store holds the whole run."""
        if self._fd is None or os.getpid() != self.pid:
            return
        try:
            if delete:
                try:
                    os.unlink(self.path)
                except FileNotFoundError:
                    pass
        finally:
            os.close(self._fd)
            self._fd = None
            with _OWN_LOCK:
                _OWN.discard(str(self.path))


def _line(event: dict[str, Any]) -> bytes:
    return (json.dumps(event, separators=(",", ":"), default=str) + "\n").encode()


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def read_events(fd: int) -> list[dict[str, Any]]:
    """Every complete event of a journal (a torn last line is ignored)."""
    chunks = []
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        chunk = os.read(fd, 1 << 20)
        if not chunk:
            break
        chunks.append(chunk)
    events = []
    for raw in b"".join(chunks).split(b"\n"):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except ValueError:
            continue  # the write the kill interrupted
        if isinstance(event, dict):
            events.append(event)
    return events


# EOF
