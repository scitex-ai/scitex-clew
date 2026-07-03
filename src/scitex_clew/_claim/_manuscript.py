#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified manuscript-claims export — one render feed for value + citation + figure.

This is the compile-time bridge scitex-writer's "Clew Render" pre-flight calls
(Option A, agreed 2026-07-01): it reads BOTH clew ledgers — value/figure claims
(the ``claims`` table via :func:`list_claims`) and citation nodes (the
``citations`` table via :func:`scitex_clew.list_citations`) — and emits ONE
inline ``claims`` list in writer's FROZEN render schema, so the compiler renders
all three kinds with the same green/amber/red marker + link.

Per-entry frozen schema (what writer joins/renders on)::

    {
      "claim_id":     join key — value: claim_id; citation: cite_key;
                                 figure: the (explicit) claim_id (image save-path),
      "claim_type":   "value" | "citation" | "figure"  (render style),
      "status":       4-bucket "verified" | "suspect" | "failed" | "exception",
      "claim_value":  verbatim value (value; optional for citation/figure),
      "display_color": resolved 6-hex for the status (no '#'),
      "link":         href — citation: DOI url; value/figure: source path,
      ... extra provenance (raw_status / resolved_status / doi / …) — writer
      ignores for rendering.
    }

Top-level adds ``palette`` (4-bucket display palette), ``status_palette``
(full-7 status→hex), ``display_groups`` (full-7 status → display bucket) +
``attestation`` (badge facts: ``badge_state`` + ``counts``). Status mapping
for citations: verified→verified, stub→failed (red), unverified→suspect
(amber) — clew's stored citation statuses; ``unknown`` is a verify-time
verdict only, never a stored row, so it never appears here.

Emit model (writer's Option A): the compile calls this LAST (last-write-wins) so
render_clew reads the complete unified shape. It writes to the same canonical
``.scitex/clew/runtime/claims.json`` by default (``path=`` overrides for a
dedicated file). clew-absent → the compiler skips this call and render_clew
no-ops.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

from ._export import _resolve_chain_flags
from ._model import (
    _CLAIM_PALETTE,
    _DISPLAY_GROUPS,
    _DISPLAY_PALETTE,
    _resolve_status,
)
from ._register import list_claims

# Stored citation status -> writer's 4-bucket render group.
_CITATION_STATUS_TO_GROUP: Dict[str, str] = {
    "verified": "verified",
    "stub": "failed",  # hallucinated / placeholder -> RED
    "unverified": "suspect",  # cited, not yet scholar-confirmed -> amber
}


def _claim_entry(claim, grounded=None) -> Dict:
    """Map a value/figure/statistic/table/text claim to a unified render entry.

    ``grounded`` is the registered-source gate signal (None => gate inactive,
    identical to the pre-gate behavior; False => demote to ``unsourced``).
    """
    has_exception, has_frozen = _resolve_chain_flags(claim)
    resolved = _resolve_status(claim.status, has_exception, has_frozen, grounded)
    group = _DISPLAY_GROUPS[resolved]
    claim_type = "figure" if claim.claim_type == "figure" else "value"
    return {
        "claim_id": claim.claim_id,
        "claim_type": claim_type,
        "status": group,
        "claim_value": claim.claim_value,
        "display_color": _DISPLAY_PALETTE[group],
        # value -> its source; figure -> its recipe/data (both source_file).
        "link": claim.source_file,
        # --- provenance (writer ignores for rendering) ---
        "raw_claim_type": claim.claim_type,
        "raw_status": claim.status,
        # Full-7 resolved status (author tooling / DAG fidelity).
        "resolved_status": resolved,
        "file_path": claim.file_path,
        "line_number": claim.line_number,
        "source_file": claim.source_file,
        "source_session": claim.source_session,
        "chain_has_exception": has_exception,
        "chain_has_frozen": has_frozen,
    }


def _citation_entry(citation) -> Dict:
    """Map a citation node to a unified render entry."""
    group = _CITATION_STATUS_TO_GROUP.get(citation.status, "failed")
    return {
        "claim_id": citation.cite_key,
        "claim_type": "citation",
        "status": group,
        "claim_value": None,
        "display_color": _DISPLAY_PALETTE[group],
        "link": citation.link,  # scholar url > https://doi.org/<doi> > None
        # --- provenance (writer ignores for rendering) ---
        "raw_status": citation.status,
        "doi": citation.doi,
        "source_id": citation.source_id,
        "is_stub": citation.is_stub,
        "manuscript_file": citation.manuscript_file,
        "line_number": citation.line_number,
    }


def export_manuscript_claims(
    path: Optional[Union[str, Path]] = None,
    *,
    read_only: bool = True,
) -> Path:
    """Emit the unified render feed (value + citation + figure) to claims.json.

    Reads both clew ledgers and writes ONE ``claims`` list in scitex-writer's
    frozen render schema. This is the compile-time exporter behind
    ``clew export-claims --unified``; the compiler calls it last so render_clew
    reads the complete unified shape.

    Parameters
    ----------
    path : str | Path, optional
        Output path. Resolution mirrors :func:`export_claims_json`:
        explicit ``path`` > ``$SCITEX_CLEW_CLAIMS_JSON`` >
        ``<project_root>/.scitex/clew/runtime/claims.json`` (the canonical file
        render_clew reads). Pass an explicit path for a dedicated file.
    read_only : bool, optional
        ``chmod 0o444`` the file after writing (default True — it is derived).

    Returns
    -------
    Path
        The path written (absolute).
    """
    from .._db import _core as _db_core

    if path is None:
        env_path = os.environ.get("SCITEX_CLEW_CLAIMS_JSON")
        if env_path:
            path = Path(env_path)
        else:
            path = _db_core._default_claims_json_path(_db_core._find_project_root())
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Registered-source gate (opt-in): load the manifest ONCE. Absent -> None
    # -> gate inactive (grounded stays None). Malformed -> ValueError.
    from .._db import get_db
    from .._sources import is_grounded, load_sources_manifest

    _manifest = load_sources_manifest()
    _gate_active = _manifest is not None and _manifest.active
    _gate_db = get_db()

    def _grounded_for(claim):
        if not _gate_active:
            return None
        return is_grounded(claim, _manifest, _gate_db)

    entries: List[Dict] = [
        _claim_entry(c, _grounded_for(c)) for c in list_claims(limit=100_000)
    ]

    # Citations live in their own ledger; a missing citations table (e.g. no
    # citations ever registered) must not break the export.
    try:
        from .._citation import list_citations

        entries.extend(_citation_entry(c) for c in list_citations(limit=100_000))
    except Exception:  # noqa: BLE001 — citation ledger optional
        pass

    total = len(entries)
    bucket_counts = {
        bucket: sum(1 for e in entries if e["status"] == bucket)
        for bucket in ("verified", "suspect", "failed", "exception", "unsourced")
    }
    verified_count = bucket_counts["verified"]
    # Raw ledger statuses (claims only; citations never carry these).
    mismatch_count = sum(1 for e in entries if e.get("raw_status") == "mismatch")
    missing_count = sum(1 for e in entries if e.get("raw_status") == "missing")

    # Badge state: failing if ANY entry is in the failed bucket (claim
    # mismatch/missing or stub citation); all_verified iff every entry is
    # verified (vacuously true for an empty ledger); else partial.
    if bucket_counts["failed"] > 0:
        badge_state = "failing"
    elif verified_count == total:
        badge_state = "all_verified"
    else:
        badge_state = "partial"

    try:
        _pkg_version = importlib.metadata.version("scitex-clew")
    except importlib.metadata.PackageNotFoundError:
        _pkg_version = "0.0.0"

    payload = {
        "_note": (
            "AUTO-GENERATED by scitex_clew.export_manuscript_claims() — the "
            "UNIFIED render feed (value + citation + figure) in scitex-writer's "
            "frozen schema. Regenerated at compile; do NOT edit by hand. "
            "Per-entry status is the 4-bucket display group "
            "(verified|suspect|failed|exception); attestation.counts maps the "
            "ledger statuses onto it: failed = claim mismatch+missing + stub "
            "citations; suspect includes registered (never-verified) claims "
            "and scholar-unconfirmed citations; unverified = total - verified. "
            "Superseded claims are excluded from all entries and counts."
        ),
        "schema_version": "1.6-unified",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # 4-bucket display palette (what writer renders with).
        "palette": dict(_DISPLAY_PALETTE),
        # Full-7 status palette + collapse map (author tooling / DAG fidelity).
        "status_palette": dict(_CLAIM_PALETTE),
        "display_groups": dict(_DISPLAY_GROUPS),
        "attestation": {
            "text": "Provenance checked by SciTeX Clew.",
            "tool": "scitex-clew",
            "version": _pkg_version,
            "total": total,
            "verified_count": verified_count,
            "unverified_count": total - verified_count,
            # Badge facts (writer renders the badge from attestation+palette).
            "badge_state": badge_state,
            "counts": {
                "total": total,
                "verified": verified_count,
                "unverified": total - verified_count,
                "suspect": bucket_counts["suspect"],
                "failed": bucket_counts["failed"],
                "exception": bucket_counts["exception"],
                # Schema v1.6-unified: source-gate demotions (0 if inactive).
                "unsourced": bucket_counts["unsourced"],
                "mismatch": mismatch_count,
                "missing": missing_count,
            },
        },
        "claims": entries,
    }

    if path.exists():
        try:
            path.chmod(0o644)
        except OSError:
            pass

    path.write_text(json.dumps(payload, indent=2, default=str))

    if read_only:
        try:
            path.chmod(0o444)
        except OSError:
            pass

    return path


# EOF
