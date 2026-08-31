#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The claims :class:`~scitex_dev.store.Store` — schema + open helper.

Split out of ``_model.py`` (which was about to cross the repo's 512-line
limit) so the schema declaration and the Store-construction plumbing have
their own home, separate from the ``Claim`` dataclasses and the
resolve/update helpers that use them.

Why ``host_store()``
--------------------
``host_store()`` resolves THE store this host uses (ADR-0006):
``SCITEX_STORE_DSN`` when set, otherwise the per-host PostgreSQL over its
UNIX socket. It is the single switch — this module constructs no DSN and
no path of its own.

An earlier revision opened a local file-backed target instead, on the
argument that clew's claims ledger is many portable per-PROJECT files that
must work with zero fleet infrastructure and stay readable as a plain
``.db``. That rationale is overruled: a file has no concept of WHO, so the
portability it buys is the portability of a store nobody can be
authenticated against.

The claims store's physical tables (``claims_rows`` / ``claims_oplog`` /
``claims_cursor`` / ``claims_identity``) share the one host database with
clew's other stores. The names do not collide — the dialect always
suffixes the store name.

WHAT THE PER-PROJECT FILE USED TO DO, AND WHAT DOES IT NOW. ``claim_id`` is
author-chosen, and the old per-project file was what kept two manuscripts'
``acute_n_sig_pathways`` apart. One host database would have made them the
SAME row, with ``MergeRule.LAST_WRITER_WINS`` picking a winner silently.

So the identity is ``(project, claim_id)``, not ``claim_id``. The scope is
resolved in one place — :mod:`scitex_clew._db._scope` — and applied by
:class:`~scitex_clew._db._scope.ProjectScopedStore` to reads and writes
alike, so a lookup cannot miss a row it just wrote. Call sites never
mention the project; a scope threaded by hand through every call site is
one that gets forgotten at exactly one of them, silently.
"""

from __future__ import annotations

import socket

from scitex_dev.store import (
    FieldKind,
    FieldPolicy,
    FieldRole,
    MergeRule,
    Schema,
    Store,
    WriterPolicy,
    host_store,
)

from .._db._scope import ProjectScopedStore

__all__ = ["_CLAIMS_SCHEMA", "_node_id", "_open_store"]


def _node_id() -> str:
    """The Store node id — the oplog's origin and the HLC's tie-breaker.

    clew has no fleet identity of its own to draw on, so the hostname — the
    Store docstring's own suggested stand-in — is what identifies "who
    wrote this" across the many concurrent local processes that touch the
    host store.
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
        "project": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        ),
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


def _open_store() -> Store:
    """Open (creating if absent) the claims :class:`Store` on the host store.

    A fresh ``Store`` per call — mirroring the open / do-work / close
    lifecycle every caller in this package already used. Callers are
    responsible for ``store.close()`` (wrap the call in ``try/finally``,
    exactly as before).
    """
    target = host_store(pkg="scitex_clew", name="claims")
    return ProjectScopedStore(
        Store(
            target,
            _CLAIMS_SCHEMA,
            node=_node_id(),
            # clew stores are written by many concurrent processes on one
            # project — there is no single durable "owner" per claim, so
            # MULTI_WRITER (no per-record ownership check) is correct.
            writer_policy=WriterPolicy.MULTI_WRITER,
        )
    )

# EOF
