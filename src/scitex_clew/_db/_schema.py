#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex_dev.store schema definitions for clew's four tables.

Extracted from `_core.py` only to keep that file under the project's
512-line limit; the schemas and the node-id resolver are otherwise exactly
what `_core.py` would have declared inline.

See the PR body for
the design rationale behind each schema, in particular:

- ``file_hashes`` / ``session_parents``: composite IDENTITY replacing the
  original ``UNIQUE(...)`` constraint + a dropped AUTOINCREMENT ``id``.
- ``verification_results``: a synthetic uuid4 IDENTITY (not a composite of
  session_id/level/verified_at) so every ``record_verification()`` call is
  guaranteed to create a NEW row, matching the AUTOINCREMENT PK it replaces.
- ``runs.metadata``: kept as FieldKind.TEXT (pre-serialized JSON), not
  FieldKind.JSON — existing callers read ``run["metadata"]`` as the raw
  JSON string.
"""

from __future__ import annotations

import os
import socket

from scitex_dev.store import FieldKind, FieldPolicy, FieldRole, MergeRule, Schema

__all__ = [
    "RUNS_SCHEMA",
    "FILE_HASHES_SCHEMA",
    "VERIFICATION_RESULTS_SCHEMA",
    "SESSION_PARENTS_SCHEMA",
    "resolve_node_id",
]


def _identity_field() -> FieldPolicy:
    return FieldPolicy(
        kind=FieldKind.TEXT,
        role=FieldRole.IDENTITY,
        required=True,
        merge=MergeRule.IMMUTABLE,
        indexed=False,
    )


def _data_field(
    kind: FieldKind,
    *,
    required: bool = False,
    merge: MergeRule = MergeRule.LAST_WRITER_WINS,
    indexed: bool = False,
) -> FieldPolicy:
    return FieldPolicy(kind=kind, role=FieldRole.DATA, required=required, merge=merge, indexed=indexed)


RUNS_SCHEMA = Schema.build(
    "runs",
    {
        "session_id": _identity_field(),
        "script_path": _data_field(FieldKind.TEXT),
        "script_hash": _data_field(FieldKind.TEXT),
        "started_at": _data_field(FieldKind.TEXT, indexed=True),
        "finished_at": _data_field(FieldKind.TEXT),
        "status": _data_field(FieldKind.TEXT, indexed=True),
        "exit_code": _data_field(FieldKind.INTEGER),
        "parent_session": _data_field(FieldKind.TEXT, indexed=True),
        "combined_hash": _data_field(FieldKind.TEXT),
        "metadata": _data_field(FieldKind.TEXT),
        "provenance": _data_field(FieldKind.TEXT),
        "exception_reason": _data_field(FieldKind.TEXT),
    },
)

#: Composite IDENTITY (session_id, file_path, role) matches the original
#: UNIQUE(session_id, file_path, role) — the table's real natural key.
#: The synthetic AUTOINCREMENT `id` is dropped (grep-verified: nothing in
#: the migrated public API reads it). The FK to runs(session_id) becomes
#: an unenforced convention — Store has no FK enforcement.
FILE_HASHES_SCHEMA = Schema.build(
    "file_hashes",
    {
        "session_id": _identity_field(),
        "file_path": _identity_field(),
        "role": _identity_field(),
        "hash": _data_field(FieldKind.TEXT, required=True, indexed=True),
        "size_bytes": _data_field(FieldKind.INTEGER),
        "frozen": _data_field(FieldKind.BOOL),
        "host": _data_field(FieldKind.TEXT),
        "recorded_at": _data_field(FieldKind.TEXT, required=True, indexed=True),
        # Added by the store migration's node-class PR
        # (feat/clew-node-class-store-migration) — was a raw
        # `ALTER TABLE file_hashes ADD COLUMN node_class TEXT` in the
        # pre-migration `_core/_node_class.py::migrate_add_node_class`.
        # Nullable/optional: unset until `auto_classify()`/`set_node_class()`
        # populates it, matching the old ALTER-TABLE column's default NULL.
        "node_class": _data_field(FieldKind.TEXT),
    },
)

#: A fresh verification_id (uuid4) is minted per record_verification() call
#: and used as the SOLE identity field — see module docstring. Every other
#: field is IMMUTABLE: a verification result is a write-once fact.
VERIFICATION_RESULTS_SCHEMA = Schema.build(
    "verification_results",
    {
        "verification_id": _identity_field(),
        "session_id": _data_field(
            FieldKind.TEXT, required=True, merge=MergeRule.IMMUTABLE, indexed=True
        ),
        "level": _data_field(FieldKind.TEXT, required=True, merge=MergeRule.IMMUTABLE),
        "status": _data_field(FieldKind.TEXT, required=True, merge=MergeRule.IMMUTABLE),
        "verified_at": _data_field(
            FieldKind.TEXT, required=True, merge=MergeRule.IMMUTABLE, indexed=True
        ),
    },
)

#: Composite IDENTITY (session_id, parent_session) matches the original
#: UNIQUE(session_id, parent_session); the synthetic `id` is dropped for
#: the same reason as file_hashes.
SESSION_PARENTS_SCHEMA = Schema.build(
    "session_parents",
    {
        "session_id": _identity_field(),
        "parent_session": _identity_field(),
        "recorded_at": _data_field(
            FieldKind.TEXT, required=True, merge=MergeRule.IMMUTABLE, indexed=True
        ),
    },
)


def resolve_node_id() -> str:
    """Resolve the Store ``node`` id: a stable, non-empty per-host identity.

    Precedence mirrors ``_file_hashes._resolve_host``: ``$SCITEX_CLEW_HOST``
    > ``$SAC_HOST`` > ``socket.gethostname()``. Store requires a non-empty
    node id (it is the oplog's origin and the HLC's tie-breaker), so this
    falls back to a fixed literal rather than ever returning empty/None.
    """
    for env_key in ("SCITEX_CLEW_HOST", "SAC_HOST"):
        val = os.environ.get(env_key)
        if val:
            return val
    try:
        name = socket.gethostname()
    except OSError:
        name = ""
    return name or "clew-local"


# EOF
