#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Citation node model + storage primitives (schema, row I/O, lookup).

Backed by ``scitex_dev.store.Store`` at a local SQLite target
(:func:`StoreTarget.sqlite`) rather than raw ``sqlite3`` — clew's citation
ledger is portable, zero-dependency, per-project product state (not fleet
coordination state), so it deliberately keeps the single-local-file property
rather than moving to a per-host Postgres (``host_store()``). The store
primitive still gives us oplog-backed writes and hide/unhide semantics in
place of hand-rolled SQL.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, NamedTuple, Optional

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

# Public per-key status vocabulary (matches the writer/compiler contract).
CITATION_STATUSES = ("verified", "stub", "unverified", "unknown")

# Local stub heuristic markers — kept byte-identical to scitex-writer's
# pre-flight fallback so clew and the compiler never disagree on what a stub is.
STUB_NOTE_MARKER = "Auto-generated stub"
STUB_JOURNAL_MARKER = "Pending scitex-scholar metadata lookup"

# Bib fields that carry judgeable metadata. A key with none of these (a bare
# ``\cite`` with no bib entry) is "unknown", not merely "unverified".
METADATA_FIELDS = ("doi", "journal", "title", "author", "year", "note")


def resolve_link(url: Optional[str], doi: Optional[str]) -> Optional[str]:
    """Resolve a citation's source URL for rendering an href.

    Precedence: an explicit scholar-supplied ``url`` (needed for no-DOI cases
    like SemanticScholar CorpusId-only records) wins; otherwise the universal
    DOI resolver ``https://doi.org/<doi>`` (which correctly handles arXiv
    ``10.48550/arXiv.*`` and DataCite DOIs); otherwise None. Kept here so every
    renderer (LaTeX / HTML / notebook) consumes the same link, never
    reconstructs URLs.
    """
    if url and str(url).strip():
        return str(url).strip()
    if doi and str(doi).strip():
        return f"https://doi.org/{str(doi).strip()}"
    return None


@dataclass
class Citation:
    """A manuscript ``\\cite`` key linked to a scholar-resolved source."""

    cite_key: str
    manuscript_file: Optional[str]
    line_number: Optional[int]
    doi: Optional[str]
    source_id: Optional[str]
    resolved: bool
    is_stub: bool
    status: str
    metadata_hash: Optional[str]
    url: Optional[str] = None
    registered_at: Optional[str] = None
    verified_at: Optional[str] = None

    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.manuscript_file and self.line_number:
            return f"{self.manuscript_file}:L{self.line_number}"
        return self.manuscript_file or self.cite_key

    @property
    def link(self) -> Optional[str]:
        """Resolved source URL for rendering an href (None if unavailable)."""
        return resolve_link(self.url, self.doi)

    def to_dict(self) -> Dict:
        return {
            "cite_key": self.cite_key,
            "manuscript_file": self.manuscript_file,
            "line_number": self.line_number,
            "doi": self.doi,
            "source_id": self.source_id,
            "resolved": self.resolved,
            "is_stub": self.is_stub,
            "status": self.status,
            "metadata_hash": self.metadata_hash,
            "url": self.url,
            "link": self.link,
            "registered_at": self.registered_at,
            "verified_at": self.verified_at,
        }


class Verdict(NamedTuple):
    """Internal per-key classification — single source of truth.

    ``status`` is the public 4-value vocabulary; ``code`` is the aggregate
    exit code the reducer uses (they differ only for drift, where the status
    is ``unverified`` but the code is the more specific ``HASH_MISMATCH``).
    """

    status: str
    code: int
    doi: Optional[str]
    source_id: Optional[str]
    link: Optional[str]
    reason: str


# -- store schema -------------------------------------------------------
#
# Columns kept 1:1 with the previous raw-sqlite ``citations`` table, minus
# the autoincrement ``id`` (the store has its own row identity keyed by
# ``cite_key``). No hard delete exists anywhere in this package (grepped the
# whole ``_citation/`` tree), so there is no HIDE_FLAG field either.
CITATIONS_SCHEMA = Schema.build(
    "citations",
    {
        "cite_key": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.IDENTITY,
            required=True,
            merge=MergeRule.IMMUTABLE,
            indexed=False,
        ),
        "manuscript_file": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
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
        "doi": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "source_id": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "resolved": FieldPolicy(
            kind=FieldKind.BOOL,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "is_stub": FieldPolicy(
            kind=FieldKind.BOOL,
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
        "metadata_json": FieldPolicy(
            kind=FieldKind.JSON,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "metadata_hash": FieldPolicy(
            kind=FieldKind.TEXT,
            role=FieldRole.DATA,
            required=False,
            merge=MergeRule.LAST_WRITER_WINS,
            indexed=False,
        ),
        "url": FieldPolicy(
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
    },
)


def citations_store(db_path: Path) -> Store:
    """Open (creating if absent) the citations ``Store`` for ``db_path``.

    ``StoreTarget.sqlite`` — a LOCAL file-backed target, not ``host_store()``
    — is the deliberate scope decision recorded on the sqlite-migration card:
    clew's citation ledger is portable per-project state, so it keeps the
    single-file/zero-Postgres property while moving off raw ``sqlite3`` onto
    the store primitive.

    Table creation (and any additive-column migration) happens inside the
    ``Store`` constructor itself, so this is also what
    :func:`migrate_add_citations_table` calls. ``writer_policy`` is
    ``MULTI_WRITER``: clew's DBs are written by many concurrent processes on
    one project with no single durable "owner" per citation (see
    ``_db/_connect.py``'s docstring).

    The caller is responsible for closing the returned store — use it as a
    context manager (``with citations_store(path) as store: ...``).
    """
    target = StoreTarget.sqlite(Path(db_path), pkg="scitex_clew", name="citations")
    return Store(
        target,
        CITATIONS_SCHEMA,
        node=socket.gethostname(),
        writer_policy=WriterPolicy.MULTI_WRITER,
    )


def migrate_add_citations_table(db_path: Path) -> None:
    """Create the citations store schema if not present. Safe to call repeatedly."""
    citations_store(db_path).close()


def ensure_citations_table(db) -> None:
    migrate_add_citations_table(db.db_path)


def row_to_citation(row) -> Citation:
    values = row.values
    return Citation(
        cite_key=values["cite_key"],
        manuscript_file=values.get("manuscript_file"),
        line_number=values.get("line_number"),
        doi=values.get("doi"),
        source_id=values.get("source_id"),
        resolved=bool(values.get("resolved")),
        is_stub=bool(values.get("is_stub")),
        status=values["status"],
        metadata_hash=values.get("metadata_hash"),
        url=values.get("url"),
        registered_at=values.get("registered_at"),
        verified_at=values.get("verified_at"),
    )


def lookup_citation(db, cite_key: str) -> Optional[Citation]:
    with citations_store(db.db_path) as store:
        row = store.get({"cite_key": cite_key})
        return row_to_citation(row) if row else None


# EOF
