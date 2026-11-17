#!/usr/bin/env python3
"""Batched input recording for :class:`~scitex_clew._tracker.SessionTracker`.

Bound onto the tracker as :meth:`SessionTracker.record_hashed_inputs`; kept in
its own module because it is the bulk counterpart of ``record_input``, used by
the file-access capture (:mod:`scitex_clew._capture`) that must hash at read
time but must not pay a store round-trip per file inside the user's ``open()``.
"""

from __future__ import annotations

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


# EOF
