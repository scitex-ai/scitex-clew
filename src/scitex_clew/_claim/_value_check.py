#!/usr/bin/env python3
"""The value half of claim verification: is the claimed value the source's?

``verify_claim`` checks a claim's source FILE (hash, lineage); this module
checks the claimed VALUE, in three steps, each recorded in
``result["value_checks"]`` / ``result["details"]``:

1. **Text vs registered value** (:func:`text_value_checks`). The manuscript
   shows ``claim_value``; the source check compares the structured
   ``value``. When both are registered they must state the same numbers —
   otherwise a drifted manuscript number verifies against a correct
   registration. Disagreement -> ``VALUE_MISMATCH``.
2. **Located value vs source** (``source_keys``; see
   :mod:`scitex_clew._claim._locator`). Disagreement -> ``VALUE_MISMATCH``;
   an unreadable locator -> ``VERIFY_ERROR``.
3. **No locator**: the value is justified by a unique match in the source
   or reported as unchecked (see :mod:`scitex_clew._claim._justify`) ->
   ``VALUE_UNCHECKED``, a warning by default and an error under
   ``--strict``. Never silent.
"""

from __future__ import annotations

from ._model import AUTHOR_INTERPRETATION

__all__ = ["check_claim_value", "text_value_checks"]


def text_value_checks(claim) -> list[dict]:
    """Does the display text (``claim_value``) state the registered ``value``?

    Rule: when a claim registers BOTH a display string and a structured
    ``value``, every numeric leaf of ``value`` must be written in the text —
    as a number that agrees within the claim's declared tolerance, else
    within the precision the TEXT wrote it with (``"0.25"`` agrees with
    0.2534; ``"25%"`` with 0.253 or 25.3; ``"1.2 × 10^-3"`` with 0.00121).
    Formats: plain, scientific, ``× 10^n`` / LaTeX ``\\times 10^{n}``,
    thousands separators, ``%`` / ``\\%``; a number after ``±`` is an
    uncertainty and never stands for the value. So ``value`` should hold the
    numbers the sentence states; other data belongs in ``metadata``.

    Not compared (returns ``[]``): no structured value, no text, or a text
    that writes no number at all (a label such as ``"AUC"``). A string
    ``value`` must appear in the text verbatim (case-insensitive).
    """
    if claim.value is None or claim.claim_value is None:
        return []
    from ._numbers import numeric_leaves, parse_numbers, text_agrees_with

    text = str(claim.claim_value)
    if isinstance(claim.value, str):
        ok = claim.value.strip().lower() in text.lower()
        verb = "states" if ok else "does not state"
        return [
            {
                "field": "text",
                "ok": ok,
                "error": False,
                "detail": f"claim text {text!r} {verb} the registered value "
                f"{claim.value!r}",
            }
        ]
    if not any(not t.uncertainty for t in parse_numbers(text)):
        return []
    tolerance = claim.tolerance or {}
    how = "declared" if tolerance else "implied by the text's precision"
    checks = []
    for path, number in numeric_leaves(claim.value):
        hit = text_agrees_with(text, number, tolerance)
        if hit is not None:
            detail = (
                f"claim text {text!r} states the registered value {number!r} "
                f"(as {hit.raw}; tolerance {how})"
            )
        else:
            detail = (
                f"claim text {text!r} disagrees with the registered value "
                f"{number!r}: no number written in the text agrees "
                f"(tolerance {how})"
            )
        checks.append(
            {
                "field": "text" if path == "." else f"text{path}",
                "ok": hit is not None,
                "error": False,
                "detail": detail,
            }
        )
    return checks


def _record(result: dict, checks: list[dict]) -> None:
    result["value_checks"] = result.get("value_checks", []) + checks
    result["details"].extend(f"value[{c['field']}]: {c['detail']}" for c in checks)


def check_claim_value(claim, result: dict) -> str | None:
    """Run the value checks for ``claim`` into ``result``.

    Returns the claim status to stop verification with (``"mismatch"`` for a
    contradicted value, ``"suspect"`` for an unreadable locator), or ``None``
    to go on to the lineage check. A value that could only be left unchecked
    sets ``result["value_unchecked"]`` and does not stop.
    """
    text_checks = text_value_checks(claim)
    if text_checks:
        _record(result, text_checks)
        if not all(c["ok"] for c in text_checks):
            result["value_verified"] = False
            return "mismatch"

    if claim.source_keys:
        from ._locator import check_claim_against_source

        checks = check_claim_against_source(
            claim.checked_value,
            claim.source_file,
            claim.source_keys,
            claim.tolerance or {},
        )
        _record(result, checks)
        if any(c["error"] for c in checks):
            # Could not READ a located value: unverifiable, never OK.
            result["value_error"] = "; ".join(c["detail"] for c in checks if c["error"])
            return "suspect"
        result["value_verified"] = all(c["ok"] for c in checks)
        return None if result["value_verified"] else "mismatch"

    if claim.evidence_relation == AUTHOR_INTERPRETATION:
        return None

    from ._justify import justify_by_search, states_a_value

    if not states_a_value(claim):
        return None
    checks = justify_by_search(claim, claim.tolerance or {})
    if not any(c["field"] != "note" for c in checks):
        checks.append(
            {
                "field": ".",
                "ok": False,
                "error": False,
                "unchecked": True,
                "matched_by": "search",
                "locator": None,
                "detail": "value unchecked: the claim states no number or "
                "string clew can search for, and has no source_keys",
            }
        )
    _record(result, checks)
    unchecked = [c["detail"] for c in checks if c.get("unchecked")]
    if unchecked:
        result["value_unchecked"] = unchecked
    return None


# EOF
