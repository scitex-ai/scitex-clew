#!/usr/bin/env python3
"""Replay the journals of processes that died with a session open.

When it runs
------------
At every session start (``start_tracking`` / ``@stx.session`` /
``clew.session``) and every ``clew`` CLI command, for THIS machine's journal
directory; explicitly via :func:`scitex_clew.recover_journals` or ``clew
recover-journals``. With no journal to replay it costs a directory listing.

What it does, per journal whose owner is gone (its ``flock`` can be taken)
and whose store fingerprint is the store this process uses (another store's
journal is left for a process configured for it):

1. writes the rows queued after the last ``flushed`` marker — the rows the
   dead process never committed — exactly as its flush would have;
2. records the files its ``open()`` capture had read but not yet recorded
   (a clean close records them; first record wins, so a path the run also
   recorded through ``stx.io`` keeps that row);
3. binds every input of the run to its producer (the lineage rule, as at
   flush time; parent edges are upserts);
4. closes a run still marked ``running`` as ``killed`` (``finished_at`` = the
   journal's last write, ``exit_code`` = ``-signum`` when a signal was
   seen) and attaches ``metadata["clew_recovery"]``: what was replayed, and
   the files the run opened for writing whose final bytes were never hashed
   (a killed run's partial output is not recorded as its output);
5. deletes the journal.

Idempotent: every write is an upsert on the row's identity (``project,
session_id, file_path, role``), so replaying a journal twice writes nothing
new, and a journal whose owner closed the run but died before deleting it
replays to no change. ``killed`` / ``incomplete`` runs are FAILED runs for
``verify`` (their files are not evidence), but their rows show what they read
and wrote up to the kill.
"""

from __future__ import annotations

import fcntl
import os
import signal
from datetime import datetime
from pathlib import Path
from typing import Any

from .._core._logging import getLogger
from ._file import journal_dir, own_paths, read_events, store_fingerprint

logger = getLogger(__name__)

__all__ = ["KILLED", "recover_journal", "recover_journals"]

#: Status of a run whose process died without closing it.
KILLED = "killed"
_LISTED = 1_000
#: A temp journal older than this with no owner lock was never published.
_STALE_TEMP_SECONDS = 3600


def _current_fingerprint() -> str:
    """The fingerprint of the store a VerificationDB here would open."""
    from scitex_dev.store import host_store

    return store_fingerprint(host_store(pkg="scitex_clew", name="runs").dsn)


def _lock_dead(path: Path) -> int | None:
    """An fd holding ``path``'s lock when its owner is gone, else None."""
    try:
        fd = os.open(path, os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Still the published file (not one another recoverer just removed)?
        if os.fstat(fd).st_ino != os.stat(path).st_ino:
            raise FileNotFoundError(path)
    except OSError:
        os.close(fd)
        return None
    return fd


def _sweep_temps(directory: Path) -> None:
    """Remove unpublished temp journals whose creator died before the rename."""
    now = datetime.now().timestamp()
    for temp in directory.glob(".*.jsonl.tmp"):
        try:
            if now - temp.stat().st_mtime < _STALE_TEMP_SECONDS:
                continue
        except OSError:
            continue
        fd = _lock_dead(temp)
        if fd is not None:
            try:
                temp.unlink()
            except OSError:
                pass
            finally:
                os.close(fd)


def recover_journals(dry_run: bool = False) -> list[dict[str, Any]]:
    """Replay every dead process's journal on this machine; returns reports.

    ``dry_run`` reports what would be replayed and changes nothing (the
    journals stay). Journals of live processes and of other stores are
    skipped silently; a journal that cannot be replayed is warned about and
    kept for the next attempt.
    """
    directory = journal_dir()
    if not directory.is_dir():
        return []
    paths = sorted(directory.glob("*.jsonl"))
    if not paths:
        _sweep_temps(directory)
        return []
    mine = own_paths()
    fingerprint = None
    reports = []
    dbs: dict[str, Any] = {}
    try:
        for path in paths:
            if str(path) in mine:
                continue
            fd = _lock_dead(path)
            if fd is None:
                continue  # its process is alive (or the file just went away)
            try:
                events = read_events(fd)
                header = events[0] if events and events[0].get("k") == "h" else None
                if header is None:
                    _drop(path, dry_run)  # never published a header: empty
                    continue
                if fingerprint is None:
                    fingerprint = _current_fingerprint()
                if header.get("store") != fingerprint:
                    continue  # another store's run: not ours to write
                db = dbs.get(header["project"])
                if db is None:
                    from .._db._core import VerificationDB

                    db = dbs[header["project"]] = VerificationDB(
                        project=header["project"]
                    )
                reports.append(_replay(path, events, db, dry_run))
            except Exception as exc:  # noqa: BLE001 - kept for the next attempt
                logger.warning(
                    "clew: could not replay recording journal %s (%s: %s) — "
                    "kept; it is retried at the next clew start",
                    path,
                    type(exc).__name__,
                    exc,
                )
            finally:
                os.close(fd)
        _sweep_temps(directory)
    finally:
        for db in dbs.values():
            db.close()
    return reports


def recover_journal(path: str | Path, db=None, dry_run: bool = False) -> dict | None:
    """Replay ONE journal whose owner is gone (None if it is still locked)."""
    path = Path(path)
    fd = _lock_dead(path)
    if fd is None:
        return None
    try:
        events = read_events(fd)
        if not events or events[0].get("k") != "h":
            _drop(path, dry_run)
            return None
        owned = db is None
        if owned:
            from .._db._core import VerificationDB

            db = VerificationDB(project=events[0]["project"])
        try:
            return _replay(path, events, db, dry_run)
        finally:
            if owned:
                db.close()
    finally:
        os.close(fd)


def _drop(path: Path, dry_run: bool) -> None:
    if not dry_run:
        try:
            path.unlink()
        except OSError:
            pass


# ------------------------------------------------------------------ replay


def _split(events: list[dict]) -> dict[str, Any]:
    """The journal's rows to write, captured files, and signal."""
    flushed = max((e.get("s", 0) for e in events if e.get("k") == "f"), default=0)
    rows = [e for e in events if e.get("k") == "r" and isinstance(e.get("row"), dict)]
    signals = [e for e in events if e.get("k") == "x"]
    return {
        "unflushed": [e["row"] for e in rows if e.get("s", 0) > flushed],
        "all_rows": [e["row"] for e in rows],
        "reads": [e for e in events if e.get("k") == "c" and e.get("path")],
        "writes": [e["path"] for e in events if e.get("k") == "w" and e.get("path")],
        "signal": signals[-1] if signals else None,
    }


def _captured_rows(header: dict, parts: dict) -> list[dict]:
    """Input rows for captured reads a clean close would have recorded."""
    import json

    recorded = {
        r.get("file_path") for r in parts["all_rows"] if r.get("role") == "input"
    }
    rows = []
    for event in parts["reads"]:
        path = event["path"]
        if path in recorded:
            continue
        recorded.add(path)
        external = event.get("external")
        rows.append(
            {
                "project": header["project"],
                "session_id": header["session_id"],
                "file_path": path,
                "role": "input",
                "hash": event["hash"],
                "size_bytes": event.get("size"),
                "frozen": False,
                "host": header.get("row_host"),
                "recorded_at": event.get("at"),
                "derived_from": None,
                "external": json.dumps(external) if external is not None else None,
            }
        )
    return rows


def _bind_inputs(db, session_id: str, rows: list[dict]) -> list[str]:
    """Bind every input row to its producer; returns the parents added."""
    from .._tracker_batch import bind_producers

    pending = {
        r["file_path"]: (r.get("hash"), r.get("recorded_at"))
        for r in rows
        if r.get("role") == "input"
    }
    parents = []
    for producer in bind_producers(db, session_id, pending):
        if producer not in parents:
            parents.append(producer)
            db.add_parent(session_id, producer)
    return parents


def _replay(path: Path, events: list[dict], db, dry_run: bool) -> dict[str, Any]:
    from scitex_dev.store import ANY_REVISION

    header = events[0]
    sid = header["session_id"]
    parts = _split(events)
    captured = _captured_rows(header, parts)
    outputs = {
        r.get("file_path") for r in parts["all_rows"] if r.get("role") == "output"
    }
    unhashed = sorted({w for w in parts["writes"] if w not in outputs})
    run = db.get_run(sid)
    report: dict[str, Any] = {
        "session_id": sid,
        "journal": str(path),
        "pid": header.get("pid"),
        "rows_replayed": len(parts["unflushed"]),
        "captured_inputs": len(captured),
        "unhashed_writes": unhashed[:_LISTED],
        "status_before": run.get("status") if run else None,
        "status": run.get("status") if run else None,
        "dry_run": dry_run,
    }
    if dry_run:
        return report
    writes = parts["unflushed"] + captured
    if writes:
        store = db._file_hashes
        with store.batch() as raw:
            for values in writes:
                raw.put(values, expected_revision=ANY_REVISION)
    if run is not None:
        report["parents"] = _bind_inputs(db, sid, parts["all_rows"] + captured)
        if run.get("status") == "running":
            report["status"] = _close_killed(db, sid, path, parts, report)
        elif writes or unhashed:
            db.merge_run_metadata(sid, {"clew_recovery": _recovery_meta(report, parts)})
    path.unlink()
    if run is not None and (writes or report["status"] != report["status_before"]):
        logger.warning(
            "clew: recovered session %s (process %s ended without closing it): "
            "replayed %d queued row(s) and %d captured input(s); run status %s",
            sid,
            header.get("pid"),
            report["rows_replayed"],
            report["captured_inputs"],
            report["status"],
        )
    return report


def _signal_name(signum: int | None) -> str | None:
    if signum is None:
        return None
    try:
        return signal.Signals(signum).name
    except ValueError:
        return str(signum)


def _recovery_meta(report: dict, parts: dict) -> dict[str, Any]:
    sig = parts["signal"]
    meta = {
        "recovered_at": datetime.now().isoformat(),
        "journal_pid": report["pid"],
        "rows_replayed": report["rows_replayed"],
        "captured_inputs": report["captured_inputs"],
        "signal": _signal_name(sig.get("signal")) if sig else None,
        "unhashed_writes": report["unhashed_writes"],
    }
    if len(report["unhashed_writes"]) >= _LISTED:
        meta["unhashed_writes_truncated"] = True
    return meta


def _close_killed(db, sid: str, path: Path, parts: dict, report: dict) -> str:
    """Close a ``running`` run as killed, at the journal's last write."""
    from scitex_dev.store import ANY_REVISION

    sig = parts["signal"]
    try:
        ended = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
    except OSError:
        ended = datetime.now().isoformat()
    db._runs.put(
        {
            "session_id": sid,
            "finished_at": sig.get("at") if sig else ended,
            "status": KILLED,
            "exit_code": -int(sig["signal"]) if sig else None,
        },
        expected_revision=ANY_REVISION,
    )
    db.merge_run_metadata(sid, {"clew_recovery": _recovery_meta(report, parts)})
    return KILLED


# EOF
