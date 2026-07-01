#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Citation classification — hashing, the local stub heuristic, verdicts."""

from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Optional

from ._model import (
    METADATA_FIELDS,
    STUB_JOURNAL_MARKER,
    STUB_NOTE_MARKER,
    Citation,
    Verdict,
)


def normalize_metadata(metadata: Optional[Dict]) -> Dict[str, str]:
    """Reduce a bib entry to the stable subset used for the content hash."""
    if not metadata:
        return {}
    out: Dict[str, str] = {}
    for field in ("author", "year", "title", "journal", "doi"):
        value = metadata.get(field)
        if value is not None and str(value).strip():
            out[field] = str(value).strip().lower()
    return out


def metadata_hash(metadata: Optional[Dict]) -> Optional[str]:
    """SHA256 over the normalized metadata subset (None if empty)."""
    norm = normalize_metadata(metadata)
    if not norm:
        return None
    payload = json.dumps(norm, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def local_stub_reason(entry: Dict) -> Optional[str]:
    """Return why ``entry`` looks like a stub locally, or None.

    Byte-identical to scitex-writer's pre-flight heuristic so the two layers
    never disagree when scholar has not (yet) pushed a record.
    """
    note = str(entry.get("note") or "")
    journal = str(entry.get("journal") or "")
    doi = entry.get("doi")
    if STUB_NOTE_MARKER in note:
        return f'note="{STUB_NOTE_MARKER}"'
    if STUB_JOURNAL_MARKER in journal:
        return f'journal="{STUB_JOURNAL_MARKER}"'
    if not doi or not str(doi).strip():
        return "no DOI"
    return None


def derive_status(*, resolved: bool, is_stub: bool, doi: Optional[str]) -> str:
    """Derive the public status from scholar's pushed signals."""
    if is_stub:
        return "stub"
    if resolved and doi and str(doi).strip():
        return "verified"
    return "unverified"


def coerce_entries(entries) -> List[Dict]:
    """Accept ``list[dict]`` (each with a 'key') or ``list[str]`` of keys."""
    out: List[Dict] = []
    for e in entries:
        if isinstance(e, str):
            out.append({"key": e})
        elif isinstance(e, dict):
            if not e.get("key"):
                raise ValueError(f"citation entry missing 'key': {e!r}")
            out.append(dict(e))
        else:
            raise TypeError(f"citation entry must be str or dict, got {type(e)}")
    return out


def classify_entry(record: Optional[Citation], entry: Dict) -> Verdict:
    """Classify one cited key into a :class:`Verdict` (single source of truth).

    ``record`` is the scholar-pushed node (authoritative) or None. ``entry`` is
    the compiler-supplied bib entry (key + fields) used for the local fallback
    heuristic and drift detection.
    """
    from .._cli._exit_codes import (
        CITATION_STUB,
        CITATION_UNLINKED,
        CITATION_UNRESOLVED,
        HASH_MISMATCH,
        OK,
    )

    if record is not None:
        # Scholar is authoritative. Check for drift first: the DOI is the
        # source identity, so if the cited entry now carries a DIFFERENT DOI
        # than scholar registered, the reference was edited to point at another
        # source and must be re-verified. Formatting changes to other fields
        # (title/journal reformatting, partial field coverage) are NOT drift —
        # keying on the DOI avoids false positives from partial bib entries.
        entry_doi = str(entry.get("doi") or "").strip().lower()
        rec_doi = str(record.doi or "").strip().lower()
        if entry_doi and rec_doi and entry_doi != rec_doi:
            return Verdict(
                status="unverified",
                code=HASH_MISMATCH,
                doi=record.doi,
                source_id=record.source_id,
                reason=(
                    "cited DOI differs from scholar-registered DOI "
                    "(reference changed since registration)"
                ),
            )
        if record.status == "verified":
            return Verdict(
                status="verified",
                code=OK,
                doi=record.doi,
                source_id=record.source_id,
                reason="scholar-verified real source (DOI resolved)",
            )
        if record.status == "stub":
            return Verdict(
                status="stub",
                code=CITATION_STUB,
                doi=record.doi,
                source_id=record.source_id,
                reason="scholar flagged as a stub / placeholder reference",
            )
        return Verdict(
            status="unverified",
            code=CITATION_UNRESOLVED,
            doi=record.doi,
            source_id=record.source_id,
            reason="registered but not resolved to a real source yet",
        )

    # No scholar record — judge the bib entry locally.
    has_metadata = any(
        entry.get(f) is not None and str(entry.get(f)).strip()
        for f in METADATA_FIELDS
    )
    if not has_metadata:
        return Verdict(
            status="unknown",
            code=CITATION_UNLINKED,
            doi=None,
            source_id=None,
            reason="no clew citation node and no bib metadata for this key",
        )

    stub_reason = local_stub_reason(entry)
    if stub_reason:
        return Verdict(
            status="stub",
            code=CITATION_STUB,
            doi=entry.get("doi"),
            source_id=None,
            reason=f"local stub heuristic ({stub_reason})",
        )
    return Verdict(
        status="unverified",
        code=CITATION_UNRESOLVED,
        doi=entry.get("doi"),
        source_id=None,
        reason="present in bib but not scholar-registered",
    )


# EOF
