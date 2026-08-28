#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The claims :class:`~scitex_dev.store.Store` — schema + open helper.

Split out of ``_model.py`` (which was about to cross the repo's 512-line
limit) so the schema declaration and the Store-construction plumbing have
their own home, separate from the ``Claim`` dataclasses and the
resolve/update helpers that use them.

Why ``StoreTarget.sqlite(...)`` and not ``host_store()``
----------------------------------------------------------
``host_store()`` resolves exactly ONE Postgres-backed store PER HOST
(ADR-0006). clew's claims ledger is the opposite shape: MANY portable
per-PROJECT sqlite files (one per manuscript/repo, written by many
concurrent LOCAL processes — see the docstring that used to live on
``_db/_connect.py``), each expected to work with zero fleet infrastructure
(an author verifying a paper on a laptop with no Postgres) and to stay
directly readable as a raw ``.db`` file by scitex-io. ``StoreTarget.sqlite``
is the store's local, file-backed target — the escape hatch documented in
``_target.py`` for exactly this case — so it keeps clew's
zero-Postgres-dependency, portable-single-file property while still moving
this module off raw ``sqlite3`` calls onto the store's oplog +
hide/unhide semantics (card ``sqlite-migration-scitex-clew-20260828``).

The claims store's physical tables (``claims_rows`` / ``claims_oplog`` /
``claims_cursor`` / ``claims_identity``) live in the SAME ``.db`` file as
the (not-yet-migrated) raw-sqlite ``runs`` / ``file_hashes`` tables. The
names do not collide — the dialect always suffixes the schema name — so
one project keeps exactly one ``.db`` file.
"""

from __future__ import annotations

import socket
from pathlib import Path

from scitex_dev.store import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Schema,
    Store,
    StoreTarget,
    WriterPolicy,
)

__all__ = ["_CLAIMS_SCHEMA", "_node_id", "_open_store"]


def _node_id() -> str:
    """The Store node id — the oplog's origin and the HLC's tie-breaker.

    clew's claims store is a plain per-project file with no fleet identity
    to draw on, so the hostname — the Store docstring's own suggested
    stand-in — is what identifies "who wrote this" across the many
    concurrent local processes that touch one project's ``clew.db``.
    """
    return socket.gethostname() or "clew"


# ---------------------------------------------------------------------------
# One record per claim, keyed by claim_id.
#
# ``hidden`` is new: the old table did a real ``DELETE FROM claims`` for
# ``remove_claim`` / ``remove_claims_by_prefix`` (see ``_mutate.py``). A
# Store never deletes a row — ``Store.hide()`` sets this flag instead — so a
# HIDE_FLAG field is required where there was none before.
# ---------------------------------------------------------------------------
_CLAIMS_SCHEMA = Schema.build(
    "claims",
    {
        "claim_id": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        ),
        "file_path": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=True,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "line_number": FieldPolicy(
            kind=FieldKind.INTEGER,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "claim_type": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=True,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "claim_value": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "source_session": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "source_file": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=True,
        ),
        "source_hash": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "registered_at": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "verified_at": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "status": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=True,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "hidden": FieldPolicy(
            kind=FieldKind.BOOL,
            role=FieldRole.HIDE_FLAG,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
    },
)


def _open_store(db_path) -> Store:
    """Open (creating if absent) the claims :class:`Store` at ``db_path``.

    A fresh ``Store`` per call — mirroring the open-connection /
    do-work / close-connection lifecycle every caller in this package used
    to run against a raw ``sqlite3.Connection`` (the pre-migration
    ``_clew_sqlite_connect``). Callers are responsible for ``store.close()``
    (wrap the call in ``try/finally``, exactly as before).
    """
    target = StoreTarget.sqlite(Path(db_path), pkg="scitex_clew", name="claims")
    return Store(
        target,
        _CLAIMS_SCHEMA,
        node=_node_id(),
        # clew's provenance DBs are written by many concurrent processes on
        # one project — there is no single durable "owner" per claim, so
        # MULTI_WRITER (no per-record ownership check) is correct.
        writer_policy=WriterPolicy.MULTI_WRITER,
    )

# EOF
