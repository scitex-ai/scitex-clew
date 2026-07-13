#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-claim grounding verdict — thin public wrapper around ``is_grounded``.

``is_grounded`` (see :mod:`._gate`) is the pure, reusable chain-walk primitive
behind the aggregate verify/export gate: it collapses a claim's provenance
status to a single bool. That is exactly right for ``verify_all_claims``
(which only needs a pass/fail bit to decide an exit code), but WRONG for a
live inline editor (scitex-writer's SSOT paper editor) that needs to tell a
human apart:

* "nothing registered yet" (amber, fine — compose-phase convenience) from
* "a manifest exists and this claim fails it" (red, a real problem)

Collapsing those two into the same ``False`` would misreport a claim's
actual provenance status — the exact bug class this whole feature exists to
prevent. :func:`is_claim_grounded` is the richer, per-claim verdict: the SAME
``grounded`` bool (guaranteed to agree with :func:`~._gate.is_grounded`
bit-for-bit on the same claim/manifest/db whenever a manifest is present —
see the HARD invariant tested in
``tests/scitex_clew/_sources/test__grounding_api.py``), plus a precise
``reason`` + actionable ``fix_hint`` + the matched anchor (if any).

Locked design: agreed with scitex-writer + scitex-dev on 2026-07-08
(scitex-writer ADR 0001 §4 "Inline engine", status Accepted). Tracked by
scitex-todo card ``clew-per-claim-grounding-api``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

from .._claim._model import _ensure_claims_table, _resolve_claim
from .._db._core import VerificationDB, _default_db_path
from ._gate import _hash_consistent, collect_chain_files, is_grounded
from ._manifest import SourcesManifest, _resolve_sources_tier3, load_sources_manifest

# ---------------------------------------------------------------------------
# Reason enum — a stable, importable constant. A plain tuple (mirrors
# ``scitex_clew._claim.CLAIM_TYPES``, not an ``Enum`` class like ``Severity``
# — the reason is a descriptive classification field, not a config-coerced
# value). Downstream consumers (scitex-dev's future ``provenance_verdict``)
# should import this rather than hardcode the strings.
# ---------------------------------------------------------------------------
GROUNDING_REASONS = (
    "grounded",
    "no_chain_match",
    "no_manifest",
    "manifest_untrusted",
    "claim_not_found",
)

_FIX_HINTS: Dict[str, str] = {
    "grounded": "",
    "no_chain_match": (
        "register a source for this claim's input chain "
        "(clew register-source ...)"
    ),
    "no_manifest": (
        "no sources manifest found under this workdir — provenance gate is "
        "inactive (compose-phase convenience, not an error)"
    ),
    "manifest_untrusted": (
        "sources manifest exists but failed signature/trust verification — "
        "re-sign it (clew sign) or check for tampering"
    ),
    "claim_not_found": (
        "no claim matches this location — check the claim_id or file:line"
    ),
}


def _verdict(
    *,
    grounded: bool,
    claim_id: str,
    matched_source: Optional[Dict[str, str]],
    reason: str,
) -> Dict:
    """Build the canonical ``GroundingVerdict`` dict."""
    return {
        "grounded": grounded,
        "claim_id": claim_id,
        "matched_source": matched_source,
        "reason": reason,
        "fix_hint": _FIX_HINTS[reason],
    }


def _resolve_db_path_for_workdir(root: Path) -> Path:
    """Resolve the clew DB path for an explicit ``root`` (not cwd).

    Mirrors :func:`scitex_clew._db._core.resolve_db_path`'s tier2/tier3
    precedence exactly (the ``SCITEX_CLEW_DB_PATH`` env var escape hatch,
    then the canonical ``runtime/clew.db`` layout + migration via
    :func:`~scitex_clew._db._core._default_db_path`), swapping only the
    tier-3 "which directory is the project root" step from a cwd
    upward-walk to the explicit ``root`` the caller already resolved from
    ``workdir`` — the same "workdir IS the project root" convention already
    established by :mod:`scitex_clew._gate_plugin` (scitex-dev's
    pre-submission gate), the one existing precedent for an explicit-workdir
    resolution in this codebase.
    """
    env_path = os.environ.get("SCITEX_CLEW_DB_PATH")
    if env_path:
        return Path(env_path)
    return _default_db_path(root)


def _resolve_sources_path_for_workdir(root: Path) -> Path:
    """Resolve the sources manifest path for an explicit ``root`` (not cwd).

    Mirrors :func:`scitex_clew._sources._manifest.resolve_sources_path`'s
    tier2/tier3 precedence exactly, reusing the SAME tier-3 helper
    (:func:`~scitex_clew._sources._manifest._resolve_sources_tier3`) with
    ``root`` instead of a cwd-derived project root.
    """
    env_path = os.environ.get("SCITEX_CLEW_SOURCES")
    if env_path:
        return Path(env_path)
    path, _label = _resolve_sources_tier3(root / ".scitex" / "clew")
    return path


def _find_matched_entry(claim, manifest: SourcesManifest, db):
    """Return the first VALID manifest entry that grounds ``claim`` (else ``None``).

    Mirrors :func:`~._gate.is_grounded`'s own chain-walk EXACTLY (same
    ``collect_chain_files`` candidates, same ``anchor_paths``, same
    ``_hash_consistent`` comparison) so the returned entry is always the one
    ``is_grounded`` itself would have matched — never a second, drifting
    implementation of the walk.
    """
    anchor_paths = manifest.anchor_paths()
    if not anchor_paths:
        return None
    for abspath, fhash in collect_chain_files(claim, db):
        if abspath in anchor_paths:
            for entry in manifest.valid_entries:
                if str(entry.abspath) == abspath and _hash_consistent(
                    fhash, entry.sha256
                ):
                    return entry
    return None


def is_claim_grounded(claim_location: str, *, workdir: str = ".") -> Dict:
    """Per-claim grounding verdict for a live inline editor.

    Resolves ``claim_location`` (a bare ``claim_id`` OR a ``file.tex:L42``
    location — reusing :func:`scitex_clew._claim._model._resolve_claim`, the
    SAME resolution ``verify_claim`` uses) against the clew DB + registered-
    source manifest found under ``workdir``, and returns a richer verdict
    than :func:`~._gate.is_grounded`'s bare bool.

    This function OWNS opening the sources manifest and the clew DB
    internally (via ``workdir``) — callers must never construct a
    ``SourcesManifest`` or a DB handle directly.

    Parameters
    ----------
    claim_location : str
        A claim_id or a ``file.tex:L42``-style location.
    workdir : str, optional
        Directory the clew DB + sources manifest are resolved under
        (default ``"."`` — the current working directory, byte-identical to
        every other clew call that resolves implicitly from cwd since
        ``Path(".").resolve()`` is the cwd).

    Returns
    -------
    dict
        The ``GroundingVerdict``::

            {
                "grounded": bool,        # see Notes — never disagrees with
                                         # the aggregate gate
                "claim_id": str,
                "matched_source": {"path": str, "sha256": str} | None,
                "reason": str,           # one of GROUNDING_REASONS
                "fix_hint": str,
            }

    Notes
    -----
    ``grounded`` NEVER disagrees with the aggregate ``verify_all_claims`` /
    ``export_claims_json`` gate on the same claim: when a manifest is
    present, ``grounded`` is the LITERAL return value of
    :func:`~._gate.is_grounded` (including its defensive-True when the
    manifest has no valid anchors at all — reason folds to ``"grounded"``,
    there is no separate reason for that edge case); when no manifest exists
    at all, the aggregate gate is INACTIVE (it never demotes a claim), so
    ``grounded=True`` here too — reason ``"no_manifest"`` carries the
    "amber, not a failure" nuance the bool alone cannot express.
    """
    root = Path(workdir).resolve()
    db_path = _resolve_db_path_for_workdir(root)
    db = VerificationDB(db_path=db_path)
    _ensure_claims_table(db)

    claim = _resolve_claim(claim_location, db)
    if claim is None:
        return _verdict(
            grounded=False,
            claim_id=claim_location,
            matched_source=None,
            reason="claim_not_found",
        )

    sources_path = _resolve_sources_path_for_workdir(root)
    manifest = load_sources_manifest(sources_path, root=root)
    if manifest is None:
        return _verdict(
            grounded=True,
            claim_id=claim.claim_id,
            matched_source=None,
            reason="no_manifest",
        )

    grounded = is_grounded(claim, manifest, db)
    if not grounded:
        reason = "manifest_untrusted" if not manifest.trusted else "no_chain_match"
        matched_source = None
    else:
        reason = "grounded"
        entry = _find_matched_entry(claim, manifest, db)
        matched_source = (
            {"path": entry.path, "sha256": entry.sha256}
            if entry is not None
            else None
        )

    return _verdict(
        grounded=grounded,
        claim_id=claim.claim_id,
        matched_source=matched_source,
        reason=reason,
    )


# EOF
