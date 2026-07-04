#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nuanced, fail-loud exit codes for ``clew verify`` (claim-set mode).

Motivation
----------
Clew's value is making fabricated-then-claimed-success catchable. A
solver agent can register Clew claims that point at a hand-written
``results.json`` and then print ``DONE`` — but those claims are
``status="registered"`` with ``verified_at=NULL`` and no ``@stx.session``
computation behind the source. Recording that (lack of) provenance is
not enough on its own; ``clew verify`` must *fail loud* with a distinct,
machine-actionable exit code per outcome so a harness can gate ``DONE``
on it.

The contract
------------
A solver MUST run ``clew verify [--strict]`` before signalling ``DONE``.
``DONE`` is legitimate **only** on exit ``0`` (:data:`OK`). Any nonzero
exit means the agent must emit an honest abstention (``null`` + reason)
per the scitexification honest-grounding rule rather than claim success.

Codes
-----
The codes are spread out (10+) so they never collide with click's usage
error (exit ``2``) or a generic Python traceback (exit ``1``). They are a
stable, documented contract — downstream harnesses branch on the integer.

============  =====  ====================================================
Constant      Code   Meaning
============  =====  ====================================================
OK            0      Every registered claim is source-verified (its value
                     hashes to a recorded source). In ``--strict`` mode,
                     every source additionally has upstream
                     ``@stx.session`` lineage (chain verified).
NO_CLAIMS     20     No claims registered at all. There is nothing to
                     stand behind a ``DONE`` — treat as a hard failure for
                     a task that was supposed to produce verifiable claims.
UNVERIFIED    10     Claims exist but at least one is registered-but-
                     unverified: ``verified_at`` is NULL / no source is
                     linked / it never went through a verification pass.
                     THIS IS THE FABRICATION CASE (hand-coded metrics with
                     no computation behind them).
HASH_MISMATCH 12     At least one claim's source file changed after the
                     claim was registered (stored hash != current hash).
                     The artifact was edited / regenerated out of band.
SOURCE_MISSING 11    At least one claim's source file is gone (deleted or
                     never written).
NO_LINEAGE    13     ``--strict`` only: a claim's source hashes fine but
                     has NO upstream computation lineage — it is a
                     hand-written leaf (e.g. a hand-edited ``results.json``)
                     with no ``@stx.session`` / processing chain. Source
                     integrity is intact but provenance is absent.
CITATION_STUB 14     At least one ``\\cite{}`` key resolves to a scholar
                     STUB (note="Auto-generated stub" / journal="Pending
                     scitex-scholar metadata lookup" / no DOI) — a
                     hallucinated / placeholder reference. THE FLAGSHIP
                     "一発アウト" catch (per-key status ``stub``).
CITATION_UNRESOLVED 15  At least one cited key has no confirmed real
                     source yet — registered but scholar has not resolved
                     it to a DOI-bearing source (per-key status
                     ``unverified``).
CITATION_UNLINKED 16  At least one ``\\cite{}`` key present in the
                     manuscript has no clew citation node at all — never
                     registered by scholar and nothing to judge it against
                     (per-key status ``unknown``).
============  =====  ====================================================

When more than one failure class is present across the claim set, the
single returned code is the highest-severity one per :data:`SEVERITY`
(see :func:`worst_code`). Severity is ordered by "what the agent must fix
first": tampering / missing artifacts (hard integrity failures) outrank
the never-computed fabrication case, which outranks missing lineage,
which outranks the empty set.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple, Union

# --- The documented contract ------------------------------------------------
OK: int = 0
UNVERIFIED: int = 10
SOURCE_MISSING: int = 11
HASH_MISMATCH: int = 12
NO_LINEAGE: int = 13
# Citation gate (``\cite`` -> scholar-verified source). The per-key status
# vocabulary {verified, stub, unverified, unknown} (returned by
# :func:`scitex_clew.verify_citations`) reduces onto these aggregate codes:
#   stub       -> CITATION_STUB        (hallucinated / auto-generated stub)
#   unverified -> CITATION_UNRESOLVED  (cited but no confirmed real source)
#   unknown    -> CITATION_UNLINKED    (cited key with no clew citation node)
CITATION_STUB: int = 14
CITATION_UNRESOLVED: int = 15
CITATION_UNLINKED: int = 16
# Registered-source gate: a claim is link-hash-verified but its provenance
# chain reaches NO registered source (see :mod:`scitex_clew._sources`). The
# gate colour is amber, but it still FAILS the run (colour != exit severity).
# Outranked by the hard integrity failures (mismatch/missing) per the status
# precedence; only fires when the gate is active (a non-empty valid manifest).
UNSOURCED: int = 17
NO_CLAIMS: int = 20

# Human-readable name per code (for summaries / JSON payloads).
NAMES: Dict[int, str] = {
    OK: "OK",
    UNVERIFIED: "UNVERIFIED",
    SOURCE_MISSING: "SOURCE_MISSING",
    HASH_MISMATCH: "HASH_MISMATCH",
    NO_LINEAGE: "NO_LINEAGE",
    CITATION_STUB: "CITATION_STUB",
    CITATION_UNRESOLVED: "CITATION_UNRESOLVED",
    CITATION_UNLINKED: "CITATION_UNLINKED",
    UNSOURCED: "UNSOURCED",
    NO_CLAIMS: "NO_CLAIMS",
}

# One-line reason per code (printed in the human summary; embedded in JSON).
REASONS: Dict[int, str] = {
    OK: "all registered claims are source-verified",
    UNVERIFIED: (
        "claims registered but not verified (verified_at is null / no "
        "computation behind the source) — possible fabrication"
    ),
    SOURCE_MISSING: "a claim's source file is missing",
    HASH_MISMATCH: "a claim's source file changed since registration (hash mismatch)",
    NO_LINEAGE: (
        "a claim's source has no upstream @stx.session lineage "
        "(hand-written leaf) — strict mode"
    ),
    CITATION_STUB: (
        "a cited source is a scholar stub (auto-generated / journal pending "
        "/ no DOI) — a hallucinated or placeholder reference"
    ),
    CITATION_UNRESOLVED: (
        "a cited key has no confirmed real source yet "
        "(registered but not resolved to a DOI-bearing source)"
    ),
    CITATION_UNLINKED: (
        "a cited key has no clew citation node at all "
        "(never registered by scholar)"
    ),
    UNSOURCED: (
        "a claim is link-hash-verified but its provenance chain reaches no "
        "registered source (ungrounded) — register the source or ground the "
        "chain"
    ),
    NO_CLAIMS: "no claims registered — nothing to verify",
}

# Severity ranking: higher wins when several failure classes co-occur.
# Ordered by "what the agent must fix first". Citation failures rank above the
# value-integrity failures: a hallucinated source (CITATION_STUB) is the
# flagship "一発アウト" catch and should be the reported code when it co-occurs.
# UNSOURCED sits just above NO_LINEAGE and below the fabrication/integrity
# failures: a hash-failing OR never-verified claim reports its stronger code,
# never the amber source-gate one. This mirrors the status-colour precedence
# (mismatch/missing outrank unsourced).
SEVERITY: Dict[int, int] = {
    OK: 0,
    NO_CLAIMS: 1,
    NO_LINEAGE: 2,
    UNSOURCED: 3,
    UNVERIFIED: 4,
    SOURCE_MISSING: 5,
    HASH_MISMATCH: 6,
    CITATION_UNLINKED: 7,
    CITATION_UNRESOLVED: 8,
    CITATION_STUB: 9,
}


def worst_code(codes: Iterable[int]) -> int:
    """Return the highest-severity code from ``codes`` (``OK`` if empty)."""
    worst = OK
    for code in codes:
        if SEVERITY.get(code, 0) > SEVERITY.get(worst, 0):
            worst = code
    return worst


def name_of(code: int) -> str:
    """Human-readable name for ``code`` (falls back to ``CODE_<n>``)."""
    return NAMES.get(code, f"CODE_{code}")


def reason_of(code: int) -> str:
    """One-line reason string for ``code`` (empty if unknown)."""
    return REASONS.get(code, "")


# --- Per-pattern severity (configurable — the "linter for provenance" model) -
# The exit codes above say WHAT failed. Severity says how much each failure
# COUNTS: ERROR fails the run (blocks DONE), WARNING is reported but tolerated,
# IGNORE is dropped. The map is tunable per pattern via .scitex/clew/config.yaml
# (see :mod:`scitex_clew._core._config`), so a project can downgrade a pattern without
# touching code — exactly like a linter's per-rule severities.
class Severity(Enum):
    """How a fired verification pattern affects the overall result."""

    ERROR = "error"  # contributes to a nonzero exit; blocks DONE
    WARNING = "warning"  # surfaced but does NOT fail the run
    IGNORE = "ignore"  # suppressed entirely


# Stable lowercase config keys <-> exit codes (the verify.severity schema).
KEY_BY_CODE: Dict[int, str] = {
    UNVERIFIED: "unverified",
    SOURCE_MISSING: "source_missing",
    HASH_MISMATCH: "hash_mismatch",
    NO_LINEAGE: "no_lineage",
    CITATION_STUB: "citation_stub",
    CITATION_UNRESOLVED: "citation_unresolved",
    CITATION_UNLINKED: "citation_unlinked",
    UNSOURCED: "unsourced",
    NO_CLAIMS: "no_claims",
}
CODE_BY_KEY: Dict[str, int] = {key: code for code, key in KEY_BY_CODE.items()}

# Default posture: fail-loud on every integrity/fabrication pattern. NO_LINEAGE
# defaults to WARNING because it only fires under --strict, which itself
# promotes it to ERROR (the flag means "require real computation, fatally").
# All citation patterns default ERROR: a hallucinated / unresolved / unlinked
# citation must block a research-project compile ("一発アウト").
DEFAULT_SEVERITY: Dict[int, Severity] = {
    UNVERIFIED: Severity.ERROR,
    SOURCE_MISSING: Severity.ERROR,
    HASH_MISMATCH: Severity.ERROR,
    NO_LINEAGE: Severity.WARNING,
    CITATION_STUB: Severity.ERROR,
    CITATION_UNRESOLVED: Severity.ERROR,
    CITATION_UNLINKED: Severity.ERROR,
    # The source gate fails the run by default (colour amber, exit non-zero).
    UNSOURCED: Severity.ERROR,
    NO_CLAIMS: Severity.ERROR,
}


def _coerce_severity(value: object, *, key: str, source: str) -> Severity:
    """Parse a config value into a :class:`Severity` (fail-loud)."""
    if isinstance(value, Severity):
        return value
    try:
        return Severity(str(value).strip().lower())
    except ValueError as e:
        raise ValueError(
            f"Invalid severity {value!r} for pattern {key!r} ({source}); "
            f"valid: {[s.value for s in Severity]}"
        ) from e


def _apply_overrides(
    sev: Dict[int, Severity],
    raw: Mapping[str, object],
    *,
    source: str,
) -> Dict[int, Severity]:
    """Overlay a ``{pattern_key: severity}`` mapping (fail-loud on bad keys)."""
    for key, value in dict(raw).items():
        code = CODE_BY_KEY.get(str(key).strip().lower())
        if code is None:
            raise ValueError(
                f"Unknown verify-severity pattern {key!r} ({source}); "
                f"valid keys: {sorted(CODE_BY_KEY)}"
            )
        sev[code] = _coerce_severity(value, key=str(key), source=source)
    return sev


def resolve_severity(
    *,
    overrides: Optional[Mapping[str, object]] = None,
    start: Optional[Path] = None,
    explicit: Optional[Union[str, Path]] = None,
    strict: bool = False,
) -> Dict[int, Severity]:
    """Resolve per-pattern severity: defaults < ``.scitex/clew`` config < overrides.

    ``--strict`` promotes :data:`NO_LINEAGE` to ERROR regardless of config.
    Raises on an unknown pattern key or an invalid severity value.
    """
    sev: Dict[int, Severity] = dict(DEFAULT_SEVERITY)

    from .._core import load_config  # lazy: avoid an import cycle at load time

    cfg = load_config(start=start, explicit=explicit)
    raw = ((cfg.get("verify") or {}).get("severity")) or {}
    if raw:
        sev = _apply_overrides(sev, raw, source="config")
    if overrides:
        sev = _apply_overrides(sev, overrides, source="argument")
    if strict:
        sev[NO_LINEAGE] = Severity.ERROR
    return sev


def classify_exit(
    fired_codes: Iterable[int],
    severities: Mapping[int, Severity],
) -> Tuple[int, List[str], List[str]]:
    """Reduce fired pattern codes to ``(exit_code, error_names, warning_names)``.

    A pattern contributes to the exit code only if its resolved severity is
    ERROR; the returned code is the highest-severity ERROR pattern (see
    :func:`worst_code`). WARNING patterns are surfaced but never fail the run;
    IGNORE patterns are dropped. Returns ``OK`` when no ERROR pattern fired.
    """
    errors: List[int] = []
    warnings: List[int] = []
    for code in fired_codes:
        if code == OK:
            continue
        level = severities.get(code, Severity.ERROR)
        if level == Severity.ERROR:
            errors.append(code)
        elif level == Severity.WARNING:
            warnings.append(code)
        # Severity.IGNORE -> dropped
    exit_code = worst_code(errors) if errors else OK
    return exit_code, [name_of(c) for c in errors], [name_of(c) for c in warnings]


__all__ = [
    "OK",
    "UNVERIFIED",
    "SOURCE_MISSING",
    "HASH_MISMATCH",
    "NO_LINEAGE",
    "CITATION_STUB",
    "CITATION_UNRESOLVED",
    "CITATION_UNLINKED",
    "UNSOURCED",
    "NO_CLAIMS",
    "NAMES",
    "REASONS",
    "SEVERITY",
    "worst_code",
    "name_of",
    "reason_of",
    "Severity",
    "KEY_BY_CODE",
    "CODE_BY_KEY",
    "DEFAULT_SEVERITY",
    "resolve_severity",
    "classify_exit",
]

# EOF
