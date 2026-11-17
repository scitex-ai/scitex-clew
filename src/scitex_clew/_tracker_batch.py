#!/usr/bin/env python3
"""Batched recording + record maintenance for :class:`~scitex_clew._tracker.SessionTracker`.

Bound onto the tracker as :meth:`SessionTracker.record_hashed_inputs`; kept in
its own module because it is the bulk counterpart of ``record_input``, used by
the file-access capture (:mod:`scitex_clew._capture`) that must hash at read
time but must not pay a store round-trip per file inside the user's ``open()``.
"""

from __future__ import annotations

from pathlib import Path

from ._db._file_hashes import _stat_size


def record_hashed_inputs(
    tracker, hashes: dict[str, str], external: dict[str, dict] | None = None
) -> dict[str, str]:
    """Record many inputs whose bytes were ALREADY hashed, in one batch.

    ``hashes`` maps resolved paths to the hash of the bytes that were read.
    Paths already recorded as inputs of this run are skipped (first record
    wins, as in ``record_input``). Producers are bound by content hash exactly
    as ``record_input`` does, with ONE producer lookup and ONE store
    transaction for all of them. ``external`` maps the paths among them that
    were read from OUTSIDE the project root to their ``external`` payload.

    Returns the ``{path: hash}`` newly recorded.
    """
    if tracker._finalized:
        return {}
    new = {p: h for p, h in hashes.items() if p not in tracker._inputs}
    if not new:
        return {}
    from ._chain._routes import bind_input

    db = tracker._db
    external = external or {}
    with db._file_hashes.batch():
        for path_str, file_hash in new.items():
            tracker._inputs[path_str] = file_hash
            info = external.get(path_str)
            if info is not None:
                tracker._external[path_str] = info
            db.add_file_hash(
                session_id=tracker.session_id,
                file_path=path_str,
                hash_value=file_hash,
                role="input",
                size_bytes=_stat_size(path_str),
                external=info,
            )
    producers = db.find_producer_records(list(new))
    for path_str, file_hash in new.items():
        producer = bind_input(
            producers.get(path_str, []),
            consumer_session=tracker.session_id,
            input_hash=file_hash,
        )
        if producer is not None and producer not in tracker._parent_sessions:
            tracker._parent_sessions.add(producer)
            db.add_parent(tracker.session_id, producer)
            if tracker.parent_session is None:
                tracker.parent_session = producer
    return new


def _explicit_external(path: Path) -> dict | None:
    """``external`` payload when an explicitly recorded input lies outside the
    active capture's project root (None without an active capture)."""
    from ._capture import active_capture

    capture = active_capture()
    return capture.external_for(path) if capture is not None else None


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

    def move(path: str) -> str:
        return relocated(path, old_prefix, new_prefix) or path

    for name in ("_inputs", "_outputs", "_external"):
        mapping = getattr(tracker, name)
        setattr(tracker, name, {move(p): v for p, v in mapping.items()})
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


# EOF
