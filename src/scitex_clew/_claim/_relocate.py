#!/usr/bin/env python3
"""Apply a session's run-dir move to the CLAIMS that point into it (#191).

scitex-session >= 0.3.6 moves ``<script>_out/RUNNING/<ID>`` to
``FINISHED_*/<ID>`` before the close hooks and reports the move as
``relocations``. The session's ``file_hashes`` rows are re-keyed by
:meth:`VerificationDB.relocate_session_paths`; a claim registered DURING the
session against a file in the run dir (``clew.add_claim(...,
source_file=<RUNNING path>)``) must move with them, or ``verify`` reports it
``SOURCE_MISSING`` and its slice has no producing run.

Every claim of the project whose ``source_file`` — or manuscript
``file_path`` — is the moved directory or lies below it is rewritten to the
same relative path under the new directory, in ONE store transaction. A
claim's ``source_keys`` are locators INTO the file (JSON pointers, row/column)
and its ``source_hash`` is content, so neither changes. A claim registered
before the run recorded its source (``source_session`` still empty) is bound
to this session when the session recorded the very bytes the claim hashed.
"""

from __future__ import annotations

from scitex_dev.store import ANY_REVISION

from .._db._relocate import relocated
from ._store import _open_store

__all__ = ["relocate_claim_paths"]

#: Path-valued claim fields a run-dir move rewrites.
_PATH_FIELDS = ("source_file", "file_path")


def relocate_claim_paths(
    old_prefix: str,
    new_prefix: str,
    *,
    session_id: str | None = None,
    outputs: dict[str, str] | None = None,
) -> list[str]:
    """Rewrite claim paths under ``old_prefix`` to ``new_prefix``.

    ``outputs`` (``{final path: hash}`` of the closing session, already
    relocated) lets a claim with no ``source_session`` be bound to
    ``session_id`` when its ``source_hash`` matches the recorded output.
    Returns the ids of the claims changed.
    """
    outputs = outputs or {}
    changed: list[str] = []
    store = _open_store()
    try:
        with store.batch():
            for row in store.rows():
                values = row.values
                payload = {}
                for name in _PATH_FIELDS:
                    moved = relocated(values.get(name), old_prefix, new_prefix)
                    if moved is not None:
                        payload[name] = moved
                if not payload:
                    continue
                source = payload.get("source_file", values.get("source_file"))
                if (
                    session_id
                    and not values.get("source_session")
                    and values.get("source_hash")
                    and outputs.get(source) == values.get("source_hash")
                ):
                    payload["source_session"] = session_id
                store.put(
                    {"claim_id": values["claim_id"], **payload},
                    expected_revision=ANY_REVISION,
                )
                changed.append(values["claim_id"])
    finally:
        store.close()
    return changed


# EOF
