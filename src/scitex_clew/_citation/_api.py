#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Citation public API — add_citation (push), list, verify, aggregate, format."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .._db import get_db
from ._heuristics import (
    classify_entry,
    coerce_entries,
    derive_status,
    metadata_hash,
)
from ._model import (
    Citation,
    ensure_citations_table,
    lookup_citation,
    row_to_citation,
)


def add_citation(
    cite_key: str,
    *,
    manuscript_file: Optional[str] = None,
    line_number: Optional[int] = None,
    doi: Optional[str] = None,
    source_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
    is_stub: bool = False,
    resolved: bool = True,
) -> Citation:
    """Register (push) a citation node resolved by scitex-scholar.

    This is the ledger-write half of the push model: scholar resolves a
    ``\\cite`` key to a real source and records the outcome here. clew stores
    the node plus a content hash over the normalized metadata so a later
    out-of-band edit to the bib entry is caught (drift -> hash mismatch).

    Parameters
    ----------
    cite_key : str
        The BibTeX citation key (e.g. ``"Berens2009CircStat"``).
    manuscript_file : str, optional
        Manuscript the key is cited from (e.g. ``paper.tex``).
    line_number : int, optional
        Line number of the ``\\cite`` in the manuscript.
    doi : str, optional
        Resolved DOI of the real source (None for a stub / unresolved).
    source_id : str, optional
        Scholar's internal source identifier for the resolved record.
    metadata : dict, optional
        Bib fields (author/year/title/journal/doi) used for the content hash.
    is_stub : bool, optional
        True if scholar flagged this as a stub / placeholder. Default False.
    resolved : bool, optional
        True if scholar resolved the key to a real source. Default True.

    Returns
    -------
    Citation
        The stored citation node.
    """
    if not cite_key or not str(cite_key).strip():
        raise ValueError("cite_key must be a non-empty string")

    status = derive_status(resolved=resolved, is_stub=is_stub, doi=doi)
    meta_hash = metadata_hash(metadata)
    verified_at = datetime.now().isoformat() if status == "verified" else None

    citation = Citation(
        cite_key=cite_key,
        manuscript_file=(
            str(Path(manuscript_file).resolve()) if manuscript_file else None
        ),
        line_number=line_number,
        doi=doi,
        source_id=source_id,
        resolved=resolved,
        is_stub=is_stub,
        status=status,
        metadata_hash=meta_hash,
        verified_at=verified_at,
    )

    db = get_db()
    ensure_citations_table(db)
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO citations
                (cite_key, manuscript_file, line_number, doi, source_id,
                 resolved, is_stub, status, metadata_json, metadata_hash,
                 verified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                citation.cite_key,
                citation.manuscript_file,
                citation.line_number,
                citation.doi,
                citation.source_id,
                1 if resolved else 0,
                1 if is_stub else 0,
                citation.status,
                json.dumps(metadata, default=str) if metadata else None,
                citation.metadata_hash,
                citation.verified_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return citation


def list_citations(
    manuscript_file: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 1000,
) -> List[Citation]:
    """List registered citation nodes with optional filters."""
    db = get_db()
    ensure_citations_table(db)

    query = "SELECT * FROM citations WHERE 1=1"
    params: list = []
    if manuscript_file:
        query += " AND manuscript_file = ?"
        params.append(str(Path(manuscript_file).resolve()))
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY cite_key LIMIT ?"
    params.append(limit)

    conn = sqlite3.connect(str(db.db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query, params).fetchall()
        return [row_to_citation(row) for row in rows]
    finally:
        conn.close()


def verify_citations(entries) -> Dict[str, Dict]:
    """Verify a set of cited keys against the clew citation ledger.

    This is the primitive the compiler's pre-flight calls. For each entry it
    returns the per-key verdict the writer gate branches on.

    Parameters
    ----------
    entries : list[dict] | list[str]
        Cited keys. Each dict carries at least ``"key"`` plus any bib fields
        the compiler extracted (``doi``/``journal``/``note``/``title``/
        ``author``/``year``). A bare string is treated as ``{"key": ...}``.

    Returns
    -------
    dict[str, dict]
        ``{cite_key: {"status", "doi", "source_id", "reason"}}`` where
        ``status`` is one of ``{verified, stub, unverified, unknown}``. The
        compiler treats anything other than ``"verified"`` as a gate hit.
    """
    coerced = coerce_entries(entries)
    db = get_db()
    ensure_citations_table(db)

    out: Dict[str, Dict] = {}
    for entry in coerced:
        key = entry["key"]
        record = lookup_citation(db, key)
        verdict = classify_entry(record, entry)
        out[key] = {
            "status": verdict.status,
            "doi": verdict.doi,
            "source_id": verdict.source_id,
            "reason": verdict.reason,
        }
    return out


def verify_all_citations(entries, *, strict: bool = False, config=None):
    """Reduce a set of cited keys to a fail-loud ``VerificationResult``.

    Same aggregate contract as :func:`scitex_clew.verify_all_claims`, so the
    compiler gets a single ``result.ok`` DONE-gate covering citations. Per-key
    verdicts reduce onto the citation exit codes (CITATION_STUB / _UNRESOLVED /
    _UNLINKED, plus HASH_MISMATCH on drift), each config-tunable via
    ``.scitex/clew`` ``verify.severity``.

    Parameters
    ----------
    entries : list[dict] | list[str]
        Cited keys (see :func:`verify_citations`).
    strict : bool, optional
        Reserved for parity with the claim gate; currently a no-op for
        citations (every citation pattern already defaults to ERROR).
    config : str | pathlib.Path, optional
        Explicit ``.scitex/clew`` config overriding the resolved severity map.

    Returns
    -------
    VerificationResult
        ``result.ok`` (exit 0) iff every cited key is ``verified``.
    """
    from .._claim import ClaimVerification, VerificationResult
    from .._cli._exit_codes import (
        KEY_BY_CODE,
        NO_CLAIMS,
        OK,
        classify_exit,
        name_of,
        reason_of,
        resolve_severity,
    )

    severities = resolve_severity(explicit=config, strict=strict)
    severity_view = {
        KEY_BY_CODE[code]: lvl.value
        for code, lvl in severities.items()
        if code in KEY_BY_CODE
    }

    coerced = coerce_entries(entries)
    if not coerced:
        exit_code, errors, warnings = classify_exit([NO_CLAIMS], severities)
        return VerificationResult(
            exit_code=exit_code,
            exit_name=name_of(exit_code),
            reason=reason_of(exit_code),
            strict=strict,
            total=0,
            verified=0,
            counts={name_of(NO_CLAIMS): 1},
            claims=[],
            severities=severity_view,
            errors=errors,
            warnings=warnings,
        )

    db = get_db()
    ensure_citations_table(db)

    rows: List[ClaimVerification] = []
    codes: List[int] = []
    counts: Dict[str, int] = {}
    verified = 0

    for entry in coerced:
        key = entry["key"]
        record = lookup_citation(db, key)
        verdict = classify_entry(record, entry)
        codes.append(verdict.code)
        cname = name_of(verdict.code)
        counts[cname] = counts.get(cname, 0) + 1
        if verdict.code == OK:
            verified += 1
        sev = "ok" if verdict.code == OK else severities[verdict.code].value
        rows.append(
            ClaimVerification(
                claim_id=key,
                location=record.location if record else key,
                claim_value=verdict.doi,
                status=verdict.status,
                source_file=verdict.source_id,
                source_session=None,
                source_verified=(verdict.status == "verified"),
                chain_verified=False,
                outcome=cname,
                severity=sev,
                details=[verdict.reason],
            )
        )

    exit_code, errors, warnings = classify_exit(codes, severities)
    return VerificationResult(
        exit_code=exit_code,
        exit_name=name_of(exit_code),
        reason=reason_of(exit_code),
        strict=strict,
        total=len(coerced),
        verified=verified,
        counts=counts,
        claims=rows,
        severities=severity_view,
        errors=errors,
        warnings=warnings,
    )


def format_citations(citations: List[Citation]) -> str:
    """Format citation nodes for terminal display."""
    if not citations:
        return "No citations registered."
    icons = {"verified": "✓", "stub": "✗", "unverified": "~", "unknown": "?"}
    lines = []
    for c in citations:
        icon = icons.get(c.status, "?")
        doi = f" doi:{c.doi}" if c.doi else ""
        lines.append(f"  {icon} [{c.status}] {c.cite_key}{doi}")
    return "\n".join(lines)


def format_verify_map(result: Dict[str, Dict]) -> str:
    """Format a :func:`verify_citations` map for terminal display."""
    if not result:
        return "No citations checked."
    icons = {"verified": "✓", "stub": "✗", "unverified": "~", "unknown": "?"}
    lines = []
    for key in sorted(result):
        v = result[key]
        icon = icons.get(v["status"], "?")
        lines.append(f"  {icon} {key}: {v['status']} — {v['reason']}")
    return "\n".join(lines)


# EOF
