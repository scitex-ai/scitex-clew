#!/usr/bin/env python3
"""Per-claim exit-code classification (split out of :mod:`._verify`, 512-line limit)."""

from __future__ import annotations


def _classify_claim(result: dict, *, strict: bool) -> int:
    """Classify a single ``verify_claim`` result into an exit code.

    Maps the per-claim verification outcome onto the documented fail-loud
    exit-code contract in :mod:`scitex_clew._cli._exit_codes`. Returns the
    code for *this one claim* (the caller reduces over the whole set).

    Decision tree (per claim):

    * No ``source_file`` linked → ``UNVERIFIED`` (the fabrication case: a
      claim registered against nothing computable — exactly the hand-coded
      ``results.json`` story).
    * Source file gone → ``SOURCE_MISSING``.
    * the claim text does not state its registered structured ``value``, or
      a value at one of its ``source_keys`` disagrees with the claimed value
      → ``VALUE_MISMATCH``; a locator could not be read → ``VERIFY_ERROR``.
    * Stored hash != current hash → ``HASH_MISMATCH``.
    * The lineage walk raised → ``VERIFY_ERROR`` (never ``OK``).
    * Source hash matches but the claim was never marked verified
      (``verified_at`` is null AND status is still ``registered``) →
      ``UNVERIFIED``.
    * Source verified:
        * a recorded lineage exists but does not verify (an upstream input,
          output or script changed, or a run in it failed) →
          ``STALE_LINEAGE`` in BOTH modes: the claim's value may no longer
          follow from its inputs, so it is not verified.
        * the lineage's ONLY failures are inputs read from outside the
          project that are absent on this machine → ``EXTERNAL_MISSING``
          (unverifiable here, not stale).
        * no lineage at all, non-strict → ``OK`` (hash match is the bar).
        * no lineage at all, strict → ``NO_LINEAGE`` (hand-written leaf,
          no ``@stx.session`` provenance upstream).
        * lineage verified → ``OK``.
        * where either of the two would be ``OK`` but the claim states a value
          that has no ``source_keys`` and that a search of the source could
          not justify → ``VALUE_UNCHECKED`` (warning; error under --strict).
    """
    from .._cli._exit_codes import (
        EXTERNAL_MISSING,
        HASH_MISMATCH,
        NO_LINEAGE,
        OK,
        SOURCE_MISSING,
        STALE_LINEAGE,
        UNVERIFIED,
        VALUE_MISMATCH,
        VALUE_UNCHECKED,
        VERIFY_ERROR,
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
    if result.get("value_verified") is False:
        return VALUE_MISMATCH
    if status == "mismatch":
        return HASH_MISMATCH
    if "value_error" in result:
        return VERIFY_ERROR

    if result.get("source_verified"):
        # A stated value nothing checked: the weakest failure, reported only
        # where the claim would otherwise pass.
        ok = VALUE_UNCHECKED if result.get("value_unchecked") else OK
        if result.get("chain_verified"):
            return ok
        chain_status = result.get("chain_status")
        if chain_status == "error":
            return VERIFY_ERROR
        if result.get("external_only"):
            return EXTERNAL_MISSING
        if chain_status is not None and chain_status != "no_lineage":
            return STALE_LINEAGE
        return NO_LINEAGE if strict else ok

    # Source linked but neither verified nor explicitly failed: it was
    # never put through a real verification pass (verified_at null).
    if not verified_at:
        return UNVERIFIED

    # Fallback — any other not-verified state is treated as unverified.
    return UNVERIFIED


# EOF
