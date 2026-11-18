#!/usr/bin/env python3
"""Batched recording + record maintenance for :class:`~scitex_clew._tracker.SessionTracker`.

Bound onto the tracker as :meth:`SessionTracker.record_hashed_inputs` /
:meth:`SessionTracker.flush_pending`. A session's file rows are QUEUED as they
are recorded (:mod:`scitex_clew._db._deferred`) and its inputs' producers are
bound in one lookup at flush time, so recording costs no store round trip per
file — neither inside the user's ``open()`` nor inside ``stx.io.load``.
"""

from __future__ import annotations

import atexit
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ._db._file_hashes import _stat_size
from ._links import absolute, link_entries, merge_link_entries


#: Queued inputs that force a producer-binding flush (see _flush_pending).
_MAX_UNBOUND = 500


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now().isoformat()


def _captured_hash(path_str: str) -> str | None:
    """The hash the active ``open()`` capture took of ``path_str``'s CURRENT
    bytes, or None (no capture, never read, or changed since)."""
    from ._capture import active_capture

    capture = active_capture()
    return capture.hash_at_open(path_str) if capture is not None else None


def record_hashed_inputs(
    tracker, hashes: dict[str, str], external: dict[str, dict] | None = None
) -> dict[str, str]:
    """Record many inputs whose bytes were ALREADY hashed.

    ``hashes`` maps resolved paths to the hash of the bytes that were read.
    Paths already recorded as inputs of this run are skipped (first record
    wins, as in ``record_input``). The rows are queued and their producers
    bound at the next flush, exactly as ``record_input`` does. ``external``
    maps the paths among them that were read from OUTSIDE the project root to
    their ``external`` payload.

    Returns the ``{path: hash}`` newly recorded.
    """
    if tracker._finalized:
        return {}
    new = {p: h for p, h in hashes.items() if p not in tracker._inputs}
    if not new:
        return {}
    db = tracker._db
    external = external or {}
    for path_str, file_hash in new.items():
        tracker._inputs[path_str] = file_hash
        info = external.get(path_str)
        if info is not None:
            tracker._external[path_str] = info
        recorded_at = _now_iso()
        db.add_file_hash(
            session_id=tracker.session_id,
            file_path=path_str,
            hash_value=file_hash,
            role="input",
            size_bytes=_stat_size(path_str),
            external=info,
            defer=True,
            recorded_at=recorded_at,
            journal=tracker._journal,
        )
        tracker._unbound[path_str] = (file_hash, recorded_at)
    tracker.flush_pending()
    return new


def bind_producers(
    db, session_id: str, pending: dict[str, tuple[str | None, str | None]]
) -> list[str]:
    """The producer each pending input binds to (one lookup for all).

    ``pending`` maps input paths to ``(hash, recorded_at)``. Binding is the
    lineage resolver's rule (:func:`scitex_clew._chain._routes.bind_input`):
    the newest producer that recorded these bytes no later than the input
    was recorded — the producer a lookup at load time would have found.
    Returns the bound producers in input order (repeats possible).
    """
    if not pending:
        return []
    from ._chain._routes import bind_input

    producers = db.find_producer_records(list(pending))
    bound = []
    for path_str, (file_hash, recorded_at) in pending.items():
        producer = bind_input(
            producers.get(path_str, []),
            consumer_session=session_id,
            input_hash=file_hash,
            input_recorded_at=recorded_at,
        )
        if producer is not None:
            bound.append(producer)
    return bound


def _flush_pending(tracker) -> int:
    """Bind queued inputs to their producers, then write every queued row.

    One producer lookup for all queued inputs (the lookup is a read, so the
    queued rows are written first, in one transaction); see
    :func:`bind_producers`. Returns the number of inputs bound to a producer.
    """
    pending, tracker._unbound = tracker._unbound, {}
    db = tracker._db
    bound = bind_producers(db, tracker.session_id, pending)
    for producer in bound:
        if producer not in tracker._parent_sessions:
            tracker._parent_sessions.add(producer)
            db.add_parent(tracker.session_id, producer)
            if tracker._parent_session is None:
                tracker._parent_session = producer
    db._file_hashes.flush()
    return len(bound)


def _flush_current_at_exit() -> None:
    """At interpreter exit, close a session that was never closed.

    The captured files are recorded and the run is closed with status
    ``incomplete`` (see :mod:`scitex_clew._journal._lifecycle`).
    """
    from ._journal._lifecycle import finish_at_exit

    finish_at_exit()


atexit.register(_flush_current_at_exit)


def _explicit_external(path: Path) -> dict | None:
    """``external`` payload when an explicitly recorded input lies outside the
    active capture's project root (None without an active capture)."""
    from ._capture import active_capture

    capture = active_capture()
    return capture.external_for(path) if capture is not None else None


def explicit_links(path: str | Path, real: str) -> list[dict]:
    """In-project symlinks an EXPLICITLY recorded path went through (#192).

    The project root is the active capture's; without one there is no root to
    tell the project's links from the machine's, so nothing is recorded.
    """
    from ._capture import active_capture

    capture = active_capture()
    if capture is None:
        return []
    return link_entries(absolute(str(path)), capture.root, real)


def note_links(tracker, entries) -> None:
    """Fold symlink entries (see :mod:`scitex_clew._links`) into the run."""
    merge_link_entries(tracker._links, list(entries))


def write_links(tracker) -> list[dict]:
    """Store the run's symlinks as ``metadata["links"]`` (at finalize).

    Only links that reach a RECORDED file are kept, each listing those files;
    a link that led only to an intermediate or a temp file is not a
    dependency. Returns what was stored.
    """
    recorded = set(tracker._inputs) | set(tracker._outputs)
    stored = []
    for link in sorted(tracker._links):
        entry = tracker._links[link]
        files = sorted(f for f in entry["files"] if f in recorded)
        if files:
            stored.append({**entry, "files": files})
    if stored:
        tracker._db.merge_run_metadata(tracker.session_id, {"links": stored})
    return stored


def warn_external_inputs(session_id: str, external: dict[str, dict]) -> None:
    """One WARNING when a run depends on files outside its project."""
    if not external:
        return
    from ._core import getLogger

    paths = sorted(external)
    more = f", ... (+{len(paths) - 5})" if len(paths) > 5 else ""
    getLogger(__name__).warning(
        "clew: session %s depends on %d file(s) outside the project: %s%s — "
        "the slice cannot bundle them; they must exist at these paths with "
        "the recorded hashes to re-run or verify",
        session_id,
        len(paths),
        ", ".join(paths[:5]),
        more,
    )


def relocate(tracker, old_prefix: str, new_prefix: str) -> int:
    """Re-key this run's recorded paths from ``old_prefix`` to ``new_prefix``.

    For a session manager that MOVES its run directory at close (scitex-session
    >= 0.3.6: ``RUNNING/<ID>`` -> ``FINISHED_*/<ID>``, reported as close-hook
    ``relocations``). The in-memory inputs/outputs/declarations/external maps
    and the session's ``file_hashes`` rows are rewritten, so the combined hash
    and every later ``verify`` see the final paths. Returns rows changed.
    """
    from ._db._relocate import relocated

    # Bind queued inputs at the paths they were READ from, before any moves.
    tracker.flush_pending()

    def move(path: str) -> str:
        return relocated(path, old_prefix, new_prefix) or path

    for name in ("_inputs", "_outputs", "_external"):
        mapping = getattr(tracker, name)
        setattr(tracker, name, {move(p): v for p, v in mapping.items()})
    tracker._links = {
        move(link): {
            **entry,
            "link": move(link),
            "files": [move(f) for f in entry["files"]],
        }
        for link, entry in tracker._links.items()
    }
    tracker._declared = {
        move(p): (h, [move(d) for d in deps])
        for p, (h, deps) in tracker._declared.items()
    }
    return tracker._db.relocate_session_paths(
        tracker.session_id, old_prefix, new_prefix
    )


def record_input(path: str | Path, track: bool = True) -> str | None:
    """Record ``path`` as an input of the CURRENT clew session.

    Convenience over ``get_tracker().record_input`` for the module-level
    ``clew.record_input`` style. Raises if no session is active (start one with
    :func:`session` or :func:`start_tracking`).
    """
    from ._tracker import get_tracker

    tracker = get_tracker()
    if tracker is None:
        raise RuntimeError(
            "record_input requires an active clew.session()/start_tracking()"
        )
    return tracker.record_input(path, track=track)


def record_output(
    path: str | Path,
    track: bool = True,
    derived_from: list[str | Path] | None = None,
) -> str | None:
    """Record ``path`` as an output of the CURRENT clew session (see :func:`record_input`).

    ``derived_from`` declares the files this output was computed from (the
    level-2 minimal-slice hook; see :meth:`SessionTracker.record_output`).
    """
    from ._tracker import get_tracker

    tracker = get_tracker()
    if tracker is None:
        raise RuntimeError(
            "record_output requires an active clew.session()/start_tracking()"
        )
    return tracker.record_output(path, track=track, derived_from=derived_from)



@contextmanager
def session(
    script_path: str | None = None,
    session_id: str | None = None,
    parent_session: str | None = None,
    metadata: dict[str, Any] | None = None,
):
    """Zero-dependency provenance-recording context manager.

    Records a REAL run in the clew DB — the ``runs`` row plus the
    ``input -> output`` file-hash edges — using ONLY clew's pure-stdlib core.
    So it works in stripped environments where ``import scitex`` / the
    ``@stx.session`` decorator cannot load (no numpy/h5py/matplotlib/system
    libs), giving a minimal-mode script a way to produce ``runs >= 1`` and a
    source-reachable DAG that passes the provenance gate.

    Inside the block, call ``run.record_input(path)`` / ``run.record_output(path)``
    (or the module-level :func:`record_input` / :func:`record_output`, which act
    on the current session) to hash + link files. A claim registered against a
    recorded OUTPUT then grounds through the recorded run to whatever registered
    source feeds it.

    This is clew's OWN recorder — it does NOT import scitex-session; it is the
    zero-dep counterpart to ``@stx.session`` (the full-stack path), sharing the
    same ``runs`` / ``file_hashes`` tables. Use one or the other per run, not both.

    Parameters
    ----------
    script_path : str, optional
        Path to the script being run. Defaults to ``sys.argv[0]`` (the invoking
        script) when not given.
    session_id : str, optional
        Unique run id. A random hex id is generated when omitted.
    parent_session : str, optional
        Explicit parent run id (parents are also auto-linked from inputs).
    metadata : dict, optional
        Extra run metadata.

    Yields
    ------
    SessionTracker
        The active tracker; call ``.record_input`` / ``.record_output`` on it.

    Examples
    --------
    >>> import scitex_clew as clew
    >>> with clew.session(script_path=__file__) as run:
    ...     run.record_input("data/raw.csv")
    ...     # ... stdlib compute; write results/out.json with open()/json ...
    ...     run.record_output("results/out.json")
    ...     clew.add_claim("paper.tex", "value", 42, "0.94",
    ...                    source_file="results/out.json")
    """
    import sys
    import uuid

    from ._tracker import get_tracker, start_tracking, stop_tracking

    sid = session_id or uuid.uuid4().hex
    spath = script_path if script_path is not None else (sys.argv[0] or None)
    start_tracking(
        sid,
        script_path=spath,
        parent_session=parent_session,
        metadata=metadata,
    )
    status, exit_code = "success", 0
    try:
        yield get_tracker()
    except BaseException:
        status, exit_code = "error", 1
        raise
    finally:
        stop_tracking(status=status, exit_code=exit_code)


# EOF
