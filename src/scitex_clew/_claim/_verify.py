#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim verification — verify_claim, verify_all_claims, verify_claims_dag."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union

from .._db import get_db
from ._model import (
    ClaimVerification,
    VerificationResult,
    _ensure_claims_table,
    _resolve_claim,
    _update_claim_status,
)
from ._register import list_claims


def verify_claim(
    claim_id_or_location: str,
    hash_cache: "Optional[Dict[str, str]]" = None,
    chain_cache: "Optional[Dict[str, object]]" = None,
) -> Dict:
    """Verify a specific claim by checking its source against the verification chain.

    Parameters
    ----------
    claim_id_or_location : str
        Either a claim_id or a location string like "paper.tex:L42".
    hash_cache : dict or None, optional
        Per-pass cache mapping resolved-path -> hash (see
        :func:`scitex_clew._hash.hash_file`). When provided, a source file
        shared by multiple claims is hashed at most once per pass. Pass
        ``None`` (default) to disable caching — direct callers are unaffected.
    chain_cache : dict or None, optional
        Per-pass memo mapping ``str(resolved source_file)`` ->
        :class:`~scitex_clew._chain.ChainVerification`. When provided, the
        full chain walk (``verify_chain``) for a source_file that appears on
        multiple claims is executed at most once per :func:`verify_all_claims`
        pass. Pass ``None`` (default) to disable memoization — direct callers
        are unaffected.

    Returns
    -------
    dict
        Verification result with claim details and chain status.
    """
    db = get_db()
    _ensure_claims_table(db)

    claim = _resolve_claim(claim_id_or_location, db)
    if not claim:
        return {
            "status": "not_found",
            "message": f"No claim found for '{claim_id_or_location}'",
        }

    result = {
        "claim": claim.to_dict(),
        "source_verified": False,
        "chain_verified": False,
        "details": [],
    }

    # Check source file exists and hash matches
    if claim.source_file:
        source_path = Path(claim.source_file)
        if not source_path.exists():
            result["details"].append(f"Source file missing: {claim.source_file}")
            _update_claim_status(claim.claim_id, "missing", db)
            result["claim"]["status"] = "missing"
            return result

        from .._hash import hash_file

        current_hash = hash_file(source_path, hash_cache=hash_cache)
        if (
            claim.source_hash
            and current_hash[: len(claim.source_hash)]
            == claim.source_hash[: len(current_hash)]
        ):
            result["source_verified"] = True
            result["details"].append("Source file hash matches")
        else:
            result["details"].append(
                f"Source hash mismatch: stored={claim.source_hash}, current={current_hash}"
            )
            _update_claim_status(claim.claim_id, "mismatch", db)
            result["claim"]["status"] = "mismatch"
            return result

    # Verify the chain if we have a source file
    if claim.source_file:
        from .._chain import verify_chain

        try:
            # Per-pass chain memo: avoid re-walking the same source chain when
            # multiple claims share one source_file (strict-mode perf).
            chain_key = str(Path(claim.source_file).resolve())
            if chain_cache is not None and chain_key in chain_cache:
                chain = chain_cache[chain_key]
            else:
                chain = verify_chain(claim.source_file)
                if chain_cache is not None:
                    chain_cache[chain_key] = chain
            result["chain_verified"] = chain.is_verified
            if chain.is_verified:
                result["details"].append(f"Chain verified ({len(chain.runs)} runs)")
            else:
                result["details"].append(
                    f"Chain verification failed ({len(chain.failed_runs)} failed runs)"
                )
        except Exception as e:
            result["details"].append(f"Chain verification error: {e}")

    # Update status
    if result["source_verified"] and result["chain_verified"]:
        _update_claim_status(claim.claim_id, "verified", db)
        result["claim"]["status"] = "verified"
    elif result["source_verified"]:
        _update_claim_status(claim.claim_id, "suspect", db)
        result["claim"]["status"] = "suspect"

    return result


def verify_claims_dag(
    file_path: Optional[str] = None,
    claim_type: Optional[str] = None,
):
    """Build a unified DAG from all claims, tracing each back to its source.

    Parameters
    ----------
    file_path : str, optional
        Filter claims by manuscript file path.
    claim_type : str, optional
        Filter claims by type.

    Returns
    -------
    DAGVerification
        Unified verification result covering all claim source chains merged.
    """
    from .._chain import DAGVerification, VerificationStatus
    from .._dag import verify_dag

    claims = list_claims(file_path=file_path, claim_type=claim_type)

    # Collect unique source files from claims
    source_files = []
    for c in claims:
        if c.source_file and c.source_file not in source_files:
            source_files.append(c.source_file)

    if not source_files:
        return DAGVerification(
            target_files=[],
            runs=[],
            edges=[],
            status=VerificationStatus.UNKNOWN,
            topological_order=[],
        )

    return verify_dag(source_files)


def _classify_claim(result: Dict, *, strict: bool) -> int:
    """Classify a single ``verify_claim`` result into an exit code.

    Maps the per-claim verification outcome onto the documented fail-loud
    exit-code contract in :mod:`scitex_clew._cli._exit_codes`. Returns the
    code for *this one claim* (the caller reduces over the whole set).

    Decision tree (per claim):

    * No ``source_file`` linked → ``UNVERIFIED`` (the fabrication case: a
      claim registered against nothing computable — exactly the hand-coded
      ``results.json`` story).
    * Source file gone → ``SOURCE_MISSING``.
    * Stored hash != current hash → ``HASH_MISMATCH``.
    * Source hash matches but the claim was never marked verified
      (``verified_at`` is null AND status is still ``registered``) →
      ``UNVERIFIED``.
    * Source verified:
        * non-strict → ``OK`` (hash match is the bar).
        * strict and chain NOT verified → ``NO_LINEAGE`` (hand-written
          leaf, no ``@stx.session`` provenance upstream).
        * strict and chain verified → ``OK``.
    """
    from .._cli._exit_codes import (
        HASH_MISMATCH,
        NO_LINEAGE,
        OK,
        SOURCE_MISSING,
        UNVERIFIED,
    )

    claim = result.get("claim", {})
    status = claim.get("status")
    source_file = claim.get("source_file")
    verified_at = claim.get("verified_at")

    # No computable source at all — the canonical fabrication case.
    if not source_file:
        return UNVERIFIED

    if status == "missing":
        return SOURCE_MISSING
    if status == "mismatch":
        return HASH_MISMATCH

    if result.get("source_verified"):
        if strict and not result.get("chain_verified"):
            return NO_LINEAGE
        return OK

    # Source linked but neither verified nor explicitly failed: it was
    # never put through a real verification pass (verified_at null).
    if not verified_at:
        return UNVERIFIED

    # Fallback — any other not-verified state is treated as unverified.
    return UNVERIFIED


def verify_all_claims(
    file_path: Optional[str] = None,
    claim_type: Optional[str] = None,
    *,
    strict: bool = False,
    config: Optional[Union[str, Path]] = None,
) -> "VerificationResult":
    """Verify every registered claim and reduce to a fail-loud result.

    This is the reusable core behind ``clew verify`` (claim-set mode). It
    re-verifies each claim (re-hashing its source and, in ``strict`` mode,
    checking upstream ``@stx.session`` lineage), updates each claim's stored
    status as a side effect (via :func:`verify_claim`), and reduces the
    per-claim outcomes to a single :class:`VerificationResult`.

    Parameters
    ----------
    file_path : str, optional
        Restrict to claims registered against this manuscript path.
    claim_type : str, optional
        Restrict to claims of this type.
    strict : bool, optional
        When True, a claim only passes if its source additionally has
        upstream computation lineage (its provenance chain verifies).
        A hand-written leaf (no ``@stx.session`` behind it) fails with
        ``NO_LINEAGE`` even though its hash matches. ``strict`` also promotes
        ``NO_LINEAGE`` to ERROR severity regardless of config. Default False.
    config : str or pathlib.Path, optional
        Explicit ``.scitex/clew`` config file/dir overriding the resolved
        user/project severity map (see :mod:`scitex_clew._core._config`).

    Returns
    -------
    VerificationResult
        Structured outcome. ``result.exit_code == 0`` (``result.ok``) is the
        DONE-gate; any nonzero code means the agent MUST abstain honestly
        instead of claiming success. Per-pattern severity (configurable via
        ``.scitex/clew``) decides which fired patterns are ``errors`` (fail)
        vs ``warnings`` (tolerated). See :mod:`scitex_clew._cli._exit_codes`.
    """
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
    severity_view = {KEY_BY_CODE[code]: lvl.value for code, lvl in severities.items()}

    claims = list_claims(file_path=file_path, claim_type=claim_type, limit=10_000)

    if not claims:
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

    # Perf B: one hash_cache per pass so a source file shared by N claims is
    # hashed exactly once (O(D) instead of O(C·D)).  The cache is fresh every
    # call to verify_all_claims so a file changed between two independent passes
    # is always re-hashed — no stale entries leak across passes.
    from .._chain._hash_cache import new_hash_cache

    hash_cache = new_hash_cache()
    # Strict-mode chain memo: in strict mode, verify_chain(source_file) walks
    # upstream provenance — O(depth) per unique source.  Claims sharing one
    # source_file would otherwise re-walk the same chain O(C) times.  The memo
    # is keyed by str(resolved source_file) and populated on first encounter so
    # each unique chain is walked at most once per pass.  A fresh dict is
    # created each call so no stale entries leak across independent passes.
    chain_cache: Dict[str, object] = {}

    per_claim: List[ClaimVerification] = []
    per_codes: List[int] = []
    verified = 0
    counts: Dict[str, int] = {}

    for c in claims:
        result = verify_claim(c.claim_id, hash_cache=hash_cache, chain_cache=chain_cache)
        code = _classify_claim(result, strict=strict)
        per_codes.append(code)
        cname = name_of(code)
        counts[cname] = counts.get(cname, 0) + 1
        if code == OK:
            verified += 1

        rclaim = result.get("claim", {})
        sev = "ok" if code == OK else severities[code].value
        per_claim.append(
            ClaimVerification(
                claim_id=c.claim_id,
                location=c.location,
                claim_value=c.claim_value,
                status=rclaim.get("status", c.status),
                source_file=rclaim.get("source_file", c.source_file),
                source_session=rclaim.get("source_session", c.source_session),
                source_verified=result.get("source_verified", False),
                chain_verified=result.get("chain_verified", False),
                outcome=cname,
                severity=sev,
                details=result.get("details", []),
            )
        )

    exit_code, errors, warnings = classify_exit(per_codes, severities)
    return VerificationResult(
        exit_code=exit_code,
        exit_name=name_of(exit_code),
        reason=reason_of(exit_code),
        strict=strict,
        total=len(claims),
        verified=verified,
        counts=counts,
        claims=per_claim,
        severities=severity_view,
        errors=errors,
        warnings=warnings,
    )


# EOF
