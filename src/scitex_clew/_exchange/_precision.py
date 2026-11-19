#!/usr/bin/env python3
"""A claim's precision as the bundle states it, and recomputing its value.

Nothing here decides what "agrees" means: that is clew's claim check,
:func:`scitex_clew._claim._locator.compare` (declared ``abs_tol``/``rel_tol``,
per locator or claim-level, used verbatim; otherwise the tolerance implied by
the precision the stated value was WRITTEN with, e.g. ``4.23`` -> ±0.005 and
``"p = 0.003"`` -> ±0.0005 via :mod:`scitex_clew._claim._numbers`).

* :func:`precision_of` DESCRIBES that rule for one claim, so a reader of the
  bundle sees the tolerance without running clew. ``basis`` is ``declared``,
  ``implied`` or ``exact`` (a non-numeric value compares verbatim);
  ``fields`` repeats it per located value field.
* :func:`recompute_claim` re-reads each located value and judges it with
  ``compare`` itself, passing the declared claim-level tolerance only when
  ``basis == "declared"`` — so a rerun applies exactly the tolerance clew's
  ``verify`` applies.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = ["precision_of", "recompute_claim"]


def _declared(tolerance: Mapping[str, Any] | None) -> dict[str, float]:
    return {
        k: float(v)
        for k, v in (tolerance or {}).items()
        if k in ("abs_tol", "rel_tol") and v is not None
    }


def _implied(value: Any) -> dict[str, Any]:
    """The written-precision tolerance of ``value`` (clew's implied rule)."""
    from .._claim._locator import implied_abs_tol
    from .._claim._numbers import parse_numbers

    if isinstance(value, bool) or value is None:
        return {"basis": "exact", "abs_tol": None, "rel_tol": None}
    if isinstance(value, (int, float)):
        return {"basis": "implied", "abs_tol": implied_abs_tol(value), "rel_tol": 0.0}
    if isinstance(value, str):
        try:
            float(value.strip())
        except ValueError:
            points = [t for t in parse_numbers(value) if not t.uncertainty]
            if points:
                return {
                    "basis": "implied",
                    "abs_tol": points[0].implied_tol,
                    "rel_tol": 0.0,
                }
            return {"basis": "exact", "abs_tol": None, "rel_tol": None}
        return {"basis": "implied", "abs_tol": implied_abs_tol(value), "rel_tol": 0.0}
    return {"basis": "implied", "abs_tol": None, "rel_tol": None}


def _rule(value: Any, declared: Mapping[str, float]) -> dict[str, Any]:
    if declared:
        return {
            "basis": "declared",
            "abs_tol": declared.get("abs_tol"),
            "rel_tol": declared.get("rel_tol"),
        }
    return _implied(value)


def precision_of(
    stated_value: Any,
    tolerance: Mapping[str, Any] | None,
    source_keys: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """The bundle's ``precision`` object for one claim (see module doc)."""
    from .._claim._locator import WHOLE_VALUE

    claim_level = _declared(tolerance)
    out = _rule(stated_value, claim_level)
    fields = {}
    for field, locator in (source_keys or {}).items():
        if field == WHOLE_VALUE:
            claimed = stated_value
        elif isinstance(stated_value, Mapping) and field in stated_value:
            claimed = stated_value[field]
        else:
            continue
        per = {
            **claim_level,
            **_declared(locator if isinstance(locator, Mapping) else {}),
        }
        fields[field] = _rule(claimed, per)
    if fields:
        out["fields"] = fields
    return out


def recompute_claim(claim: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """Re-read ``claim``'s located value(s) under ``root`` and judge them.

    Returns ``{"status", "recomputed_value", "detail"}``: ``reproduced`` when
    every located field agrees, ``differs`` when one was read and disagrees,
    ``not_checkable`` when the claim has no locator / source or a value cannot
    be read.
    """
    from .._claim._locator import (
        WHOLE_VALUE,
        SourceLocatorError,
        claimed_field,
        compare,
        normalize_source_keys,
        read_source_value,
    )

    source = claim.get("source") or {}
    if not source.get("file") or not source.get("locator"):
        return {"status": "not_checkable", "recomputed_value": None,
                "detail": "the claim has no source locator"}  # fmt: skip
    precision = claim.get("precision") or {}
    tolerance = (
        {
            k: precision[k]
            for k in ("abs_tol", "rel_tol")
            if precision.get(k) is not None
        }
        if precision.get("basis") == "declared"
        else {}
    )
    stated = claim.get("stated_value")
    values: dict[str, Any] = {}
    oks, details = [], []
    try:
        keys = normalize_source_keys(dict(source["locator"]))
        for field, locator in keys.items():
            actual = read_source_value(root / source["file"], locator)
            ok, detail = compare(
                claimed_field(stated, field), actual, locator, tolerance
            )
            values[field] = actual
            oks.append(ok)
            details.append(f"{field}: {detail}")
    except (SourceLocatorError, OSError, ValueError) as exc:
        return {"status": "not_checkable", "recomputed_value": values or None,
                "detail": f"cannot read source value: {exc}"}  # fmt: skip
    recomputed = values[WHOLE_VALUE] if list(values) == [WHOLE_VALUE] else values
    return {
        "status": "reproduced" if all(oks) else "differs",
        "recomputed_value": recomputed,
        "detail": "; ".join(details),
    }


# EOF
