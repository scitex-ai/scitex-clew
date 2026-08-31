#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manuscript hints export — prose-level "things wrong with this manuscript" feed.

Companion export to :func:`scitex_clew._claim._manuscript.export_manuscript_claims`
but a DIFFERENT, SEPARATE concern with a different consumer (confirmed by
contract with scitex-writer, 2026-07-14; do not merge the two):

* ``export_manuscript_claims`` -> ``.scitex/clew/runtime/claims.json`` -> the
  compile-time claim/value/citation VERIFICATION feed (per-entry render
  markers: green/amber/red + link).
* ``export_manuscript_hints`` (this module) -> ``.scitex/writer/hints.json``
  -> scitex-writer's prose-level MANUSCRIPT-HINTS feed: citation problems,
  ungrounded claims, source-gate failures — an author-facing "what needs
  fixing" list, not a per-claim render marker.

Locked design (scitex-todo card ``clew-feat-manuscript-findings-producer``,
decided 2026-07-04). Do not deviate from field names/shapes without
renegotiating the contract with scitex-writer + scitex-scholar.

Schema ``"manuscript-hints/1"``::

    {
      "schema": "manuscript-hints/1",
      "generated_at": "2026-07-14T00:00:00Z",
      "hints": [
        {
          "id": "hint_<12-hex>",   # deterministic: sha256(claim_id:kind)[:12]
          "kind": "claim-mismatch",  # machine-readable reason tag
          "severity": "error",       # error | warning | advice
          "message": "...",          # prose, human-readable
          "location": {"file": ..., "line": ..., "page": null},
          "claim_id": "...",         # join key back to the claim/citation
          "source": "scitex-clew",
        },
        ...
      ]
    }

Topology: clew is the SINGLE producer of citation + claim + stat hints. It
reads (a) clew's own claim ledger (:func:`scitex_clew._claim.list_claims`,
full-8 resolved status via the same chain-flags / registered-source-gate
logic as :func:`export_manuscript_claims`) and (b) clew's own citation
ledger (:func:`scitex_clew.list_citations`, populated from scholar's
``citation_status``-schema artifact via the EXISTING io-observer ingest seam,
:mod:`scitex_clew._citation._ingest` / :mod:`scitex_clew._observers`) — it
does NOT re-read scholar's raw artifact directly; clew's citation ledger IS
the already-ingested view of it.

Severity mapping
-----------------
Claim domain (full-8 resolved status — the same taxonomy as
``scitex_clew._claim._model._CLAIM_PALETTE`` / ``_resolve_status``):

* ``mismatch`` / ``missing``     -> error   (broken provenance — hash drift
  or a vanished source file)
* ``suspect`` / ``registered``   -> warning (unconfirmed chain / not yet
  verified at all)
* ``unsourced`` / ``exception``  -> advice  (needs a look, not broken —
  ungrounded per the opt-in source gate, or an author-declared exception)
* ``verified`` / ``frozen``      -> silent  (omit — a clean, passing claim)

Citation domain (clew's INGESTED ``Citation.status`` — the 4-value
vocabulary in ``scitex_clew._citation.CITATION_STATUSES``). Note scholar's
richer future distinctions (DOI-mismatch / hallucinated / semantic_mismatch)
are not yet separate stored values on the ingested ledger — they collapse
onto ``stub`` / ``unverified`` today. Any status this module does not
recognize (e.g. a future ``semantic_mismatch``) falls back to ``advice`` —
forward-compatible without requiring that value to exist yet:

* ``verified``            -> silent (resolved, omit)
* ``stub`` / ``unverified`` -> warning
* ``unknown``              -> advice
* anything else (future)   -> advice (safe fallback)

``\\ref`` / citation-key rendering stays scitex-writer's responsibility —
each hint only carries ``claim_id`` (the join key back to the claim/
citation); this module never tries to resolve ``\\cite{...}`` text itself.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

from ._export import _resolve_chain_flags
from ._model import _resolve_status
from ._register import list_claims

# Claim full-8 resolved-status -> hint severity. A status absent from this
# map (``verified`` / ``frozen``) is deliberately silent -> no hint emitted.
_CLAIM_SEVERITY: Dict[str, str] = {
    "mismatch": "error",
    "missing": "error",
    "suspect": "warning",
    "registered": "warning",
    "unsourced": "advice",
    "exception": "advice",
}

_CLAIM_MESSAGE: Dict[str, str] = {
    "mismatch": "Claim value does not match its recorded source (hash mismatch).",
    "missing": "Claim's source file is missing.",
    "suspect": "Claim's provenance chain is broken or unconfirmed.",
    "registered": "Claim has been registered but not yet verified.",
    "unsourced": "Claim does not trace to any registered source.",
    "exception": "Claim's provenance chain contains a declared exception.",
}

# Citation ledger status -> hint severity. Any status not listed here (a
# future scholar-side value) falls back to "advice" at the call site.
_CITATION_SEVERITY: Dict[str, Optional[str]] = {
    "verified": None,  # silent -- resolved, omit
    "stub": "warning",
    "unverified": "warning",
    "unknown": "advice",
}

_CITATION_MESSAGE: Dict[str, str] = {
    "stub": (
        "Citation is an unresolved stub/placeholder -- scitex-scholar has "
        "not confirmed a real source."
    ),
    "unverified": "Citation has not yet been confirmed by scitex-scholar.",
    "unknown": (
        "Citation key carries no bibliographic metadata (bare \\cite, no "
        "bib entry)."
    ),
}
_CITATION_MESSAGE_FALLBACK = (
    "Citation has an unrecognized scholar status; needs manual review."
)


def _generate_hint_id(claim_id: str, kind: str) -> str:
    """Deterministic hint id -- ``hint_<sha256(claim_id:kind)[:12]>``.

    Mirrors the claim-id precedent
    (:func:`scitex_clew._claim._model._generate_claim_id`): a stable,
    content-derived hash so re-running the export with unchanged inputs
    reproduces byte-identical ids (no randomness, no autoincrement).
    """
    key = f"{claim_id}:{kind}"
    h = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"hint_{h}"


def _claim_hint_entry(claim, grounded: Optional[bool] = None) -> Optional[Dict]:
    """Map one claim to a hint entry, or ``None`` if it needs no attention."""
    has_exception, has_frozen = _resolve_chain_flags(claim)
    resolved = _resolve_status(claim.status, has_exception, has_frozen, grounded)
    severity = _CLAIM_SEVERITY.get(resolved)
    if severity is None:
        return None
    kind = f"claim-{resolved}"
    return {
        "id": _generate_hint_id(claim.claim_id, kind),
        "kind": kind,
        "severity": severity,
        "message": _CLAIM_MESSAGE[resolved],
        "location": {
            "file": claim.file_path,
            "line": claim.line_number,
            "page": None,
        },
        "claim_id": claim.claim_id,
        "source": "scitex-clew",
    }


def _citation_hint_entry(citation) -> Optional[Dict]:
    """Map one citation node to a hint entry, or ``None`` if it needs no attention."""
    status = citation.status
    severity = _CITATION_SEVERITY.get(status, "advice")
    if severity is None:
        return None
    kind = f"citation-{status}"
    message = _CITATION_MESSAGE.get(status, _CITATION_MESSAGE_FALLBACK)
    return {
        "id": _generate_hint_id(citation.cite_key, kind),
        "kind": kind,
        "severity": severity,
        "message": message,
        "location": {
            "file": citation.manuscript_file,
            "line": citation.line_number,
            "page": None,
        },
        "claim_id": citation.cite_key,
        "source": "scitex-clew",
    }


def export_manuscript_hints(
    path: Optional[Union[str, Path]] = None,
    *,
    read_only: bool = True,
) -> Path:
    """Emit clew's prose-level manuscript hints to ``.scitex/writer/hints.json``.

    Reads clew's claim ledger + ingested citation ledger and emits ONE
    ``hints`` list in scitex-writer's ``manuscript-hints/1`` schema — the
    author-facing "what needs fixing" feed. This is a DIFFERENT, separate
    concern from :func:`export_manuscript_claims` (the per-claim render/
    verification feed) — see the module docstring; do not confuse the two.

    MERGE-BY-SOURCE: if ``hints.json`` already exists with entries from
    other producers (e.g. figrecipe, or scitex-writer's own hints), this
    function replaces ONLY the entries where ``source == "scitex-clew"`` and
    leaves every other entry untouched (verbatim, original relative order).
    A missing or unparsable file is treated as empty and (re)created fresh
    with schema ``manuscript-hints/1``.

    Parameters
    ----------
    path : str | Path, optional
        Output path. Resolution mirrors :func:`export_manuscript_claims`:
        explicit ``path`` > ``$SCITEX_CLEW_HINTS_JSON`` >
        ``<project_root>/.scitex/writer/hints.json`` (the canonical file
        scitex-writer reads). Pass an explicit path for a dedicated file.
    read_only : bool, optional
        ``chmod 0o444`` the file after writing (default True — it is derived).

    Returns
    -------
    Path
        The path written (absolute).
    """
    from .._db import _core as _db_core

    if path is None:
        env_path = os.environ.get("SCITEX_CLEW_HINTS_JSON")
        if env_path:
            path = Path(env_path)
        else:
            path = _db_core._default_hints_json_path(_db_core._find_project_root())
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Registered-source gate (opt-in): same manifest as export_manuscript_claims.
    from .._db import get_db
    from .._sources import is_grounded, load_sources_manifest

    _manifest = load_sources_manifest()
    _gate_active = _manifest is not None and _manifest.active
    _gate_db = get_db()

    def _grounded_for(claim):
        if not _gate_active:
            return None
        return is_grounded(claim, _manifest, _gate_db)

    clew_hints: List[Dict] = []
    for c in list_claims(limit=100_000):
        entry = _claim_hint_entry(c, _grounded_for(c))
        if entry is not None:
            clew_hints.append(entry)

    # Citation ledger optional (no citations ever ingested -> empty, not fatal).
    try:
        from .._citation import list_citations

        for cit in list_citations(limit=100_000):
            entry = _citation_hint_entry(cit)
            if entry is not None:
                clew_hints.append(entry)
    except Exception:  # noqa: BLE001 — citation ledger optional
        pass

    # Deterministic ordering for clew's own slice (same inputs -> same bytes,
    # independent of sqlite row iteration order).
    clew_hints.sort(key=lambda h: h["id"])

    # Merge-by-source: preserve every non-clew entry verbatim (and its
    # relative order); replace clew's slice wholesale.
    existing_payload: Dict = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text())
            if isinstance(loaded, dict):
                existing_payload = loaded
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            existing_payload = {}

    foreign_hints = [
        h
        for h in (existing_payload.get("hints") or [])
        if isinstance(h, dict) and h.get("source") != "scitex-clew"
    ]

    payload = dict(existing_payload)
    payload["schema"] = "manuscript-hints/1"
    payload["generated_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    payload["hints"] = foreign_hints + clew_hints

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
