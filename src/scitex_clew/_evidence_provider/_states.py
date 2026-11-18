#!/usr/bin/env python3
"""clew per-claim outcome -> evidence-report state + plain reason.

The four states are the contract's provider-neutral vocabulary
(``scitex-live-paper.evidence-report`` 1.x). The outcome names and codes are
clew's own (:mod:`scitex_clew._cli._exit_codes`); the code reported in
``provider_status`` is read from that module, never restated here.

An outcome this table does not know is reported ``not_supported`` with the raw
name as its reason, never ``supported``: an unknown verdict is not evidence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .._cli import _exit_codes as _codes

__all__ = [
    "NOT_CHECKABLE",
    "NOT_SUPPORTED",
    "NO_EVIDENCE_GRAPH",
    "OUTCOME_STATES",
    "STATES",
    "SUPPORTED",
    "classify_outcome",
    "value_difference",
]

SUPPORTED = "supported"
NOT_SUPPORTED = "not_supported"
NOT_CHECKABLE = "not_checkable"
NO_EVIDENCE_GRAPH = "no_evidence_graph"
STATES = (SUPPORTED, NOT_SUPPORTED, NOT_CHECKABLE, NO_EVIDENCE_GRAPH)

#: clew outcome name -> (state, plain reason).
OUTCOME_STATES: Mapping[str, tuple[str, str]] = {
    "OK": (SUPPORTED, "value and sources check out against the recorded run"),
    "VALUE_MISMATCH": (
        NOT_SUPPORTED,
        "value in source differs from the stated value",
    ),
    "HASH_MISMATCH": (
        NOT_SUPPORTED,
        "source changed after the claim was registered",
    ),
    "STALE_LINEAGE": (
        NOT_SUPPORTED,
        "source changed after the run (an input, script or run changed)",
    ),
    "EXTERNAL_MISSING": (
        NOT_SUPPORTED,
        "an input from outside the project is absent here, so the run "
        "cannot be checked",
    ),
    "ENV_NOT_REPRODUCIBLE": (
        NOT_SUPPORTED,
        "the recorded software environment cannot be reproduced from the record",
    ),
    "SOURCE_MISSING": (NOT_SUPPORTED, "the source file is missing"),
    "VERIFY_ERROR": (NOT_SUPPORTED, "verification could not complete"),
    "UNSOURCED": (NOT_SUPPORTED, "the lineage reaches no registered source"),
    "VALUE_UNCHECKED": (NOT_CHECKABLE, "no locator, value not checked"),
    "NO_LINEAGE": (
        NO_EVIDENCE_GRAPH,
        "no evidence graph: the source has no recorded computation behind it",
    ),
    "UNVERIFIED": (
        NO_EVIDENCE_GRAPH,
        "no evidence graph: no source is linked to the claim",
    ),
}

#: clew's own VALUE_MISMATCH detail: ``value[<field>]: claimed X vs source Y``.
_VALUE_DIFF = re.compile(
    r"value\[[^\]]*\]: claimed (?P<claimed>\S+) vs source (?P<source>\S+)"
)

_CODE_BY_NAME: Mapping[str, int] = {name: code for code, name in _codes.NAMES.items()}


def value_difference(details: Iterable[str]) -> tuple[str, str] | None:
    """``(source value, claimed value)`` from clew's first differing value detail."""
    for detail in details:
        m = _VALUE_DIFF.search(str(detail))
        if m and m["claimed"] != m["source"]:
            return m["source"], m["claimed"]
    return None


def _specific_reason(outcome: str, details: Iterable[str]) -> str | None:
    """A sharper reason read from clew's details (it only rephrases them)."""
    if outcome != "VALUE_MISMATCH":
        return None
    diff = value_difference(details)
    if diff is None:
        return None
    return f"value in source differs: {diff[0]} in source vs {diff[1]} stated"


def classify_outcome(
    outcome: str, details: Iterable[str] = ()
) -> tuple[str, str, dict]:
    """``(state, reason, provider_status)`` for one clew per-claim outcome."""
    status = {"name": outcome, "code": _CODE_BY_NAME.get(outcome)}
    if outcome not in OUTCOME_STATES:
        return NOT_SUPPORTED, f"clew reported {outcome}", status
    state, reason = OUTCOME_STATES[outcome]
    return state, _specific_reason(outcome, details) or reason, status


# EOF
