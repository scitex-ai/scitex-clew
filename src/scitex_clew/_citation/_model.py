#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Citation node model + storage primitives (table, row I/O, lookup)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, NamedTuple, Optional

# Public per-key status vocabulary (matches the writer/compiler contract).
CITATION_STATUSES = ("verified", "stub", "unverified", "unknown")

# Local stub heuristic markers — kept byte-identical to scitex-writer's
# pre-flight fallback so clew and the compiler never disagree on what a stub is.
STUB_NOTE_MARKER = "Auto-generated stub"
STUB_JOURNAL_MARKER = "Pending scitex-scholar metadata lookup"

# Bib fields that carry judgeable metadata. A key with none of these (a bare
# ``\cite`` with no bib entry) is "unknown", not merely "unverified".
METADATA_FIELDS = ("doi", "journal", "title", "author", "year", "note")


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
    registered_at: Optional[str] = None
    verified_at: Optional[str] = None

    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.manuscript_file and self.line_number:
            return f"{self.manuscript_file}:L{self.line_number}"
        return self.manuscript_file or self.cite_key

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
    reason: str


def migrate_add_citations_table(db_path: Path) -> None:
    """Create the citations table if not present. Safe to call repeatedly."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cite_key TEXT UNIQUE NOT NULL,
                manuscript_file TEXT,
                line_number INTEGER,
                doi TEXT,
                source_id TEXT,
                resolved INTEGER DEFAULT 1,
                is_stub INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                metadata_json TEXT,
                metadata_hash TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_citations_key ON citations(cite_key)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_citations_manuscript "
            "ON citations(manuscript_file)"
        )
        conn.commit()
    finally:
        conn.close()


def ensure_citations_table(db) -> None:
    migrate_add_citations_table(db.db_path)


def row_to_citation(row) -> Citation:
    return Citation(
        cite_key=row["cite_key"],
        manuscript_file=row["manuscript_file"],
        line_number=row["line_number"],
        doi=row["doi"],
        source_id=row["source_id"],
        resolved=bool(row["resolved"]),
        is_stub=bool(row["is_stub"]),
        status=row["status"],
        metadata_hash=row["metadata_hash"],
        registered_at=row["registered_at"],
        verified_at=row["verified_at"],
    )


def lookup_citation(db, cite_key: str) -> Optional[Citation]:
    conn = sqlite3.connect(str(db.db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM citations WHERE cite_key = ?", (cite_key,)
        ).fetchone()
        return row_to_citation(row) if row else None
    finally:
        conn.close()


# EOF
