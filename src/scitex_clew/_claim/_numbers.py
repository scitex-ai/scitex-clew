#!/usr/bin/env python3
"""Numbers as a manuscript writes them, and whether one agrees with a value.

A claim's display text (``claim_value``) is what the reader sees: ``"0.91"``,
``"p = 0.003"``, ``"45.3%"``, ``"1.2 × 10^-3"``, ``"12,345"``,
``"0.91 ± 0.02"``, ``"$0.91 \\pm 0.02$"``. Verification compares numbers, so
the text is parsed into :class:`WrittenNumber` tokens, each carrying the
precision it was written with:

* ``0.91`` -> 0.91, implied ±0.005 (half a unit in the last written place);
* ``1.2e-3`` / ``1.2 × 10^-3`` / ``1.2 \\times 10^{-3}`` -> 0.0012, ±0.00005;
* ``12,345`` -> 12345 (comma groups of exactly three digits are thousands
  separators), ±0.5;
* ``45.3%`` / ``45.3\\%`` -> 45.3 *percent*: it agrees with 45.3 or with
  0.453 (the two ways a proportion is stored);
* the number right after ``±`` / ``\\pm`` / ``+/-`` is an *uncertainty*.

A token agrees with a value when ``|token - value| <= tolerance``. The
tolerance is the claim's DECLARED ``abs_tol`` / ``rel_tol`` when it has one,
else the token's implied precision — the rounding the text asserts.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = [
    "WrittenNumber",
    "agrees",
    "numeric_leaves",
    "parse_numbers",
    "text_agrees_with",
]


@dataclass(frozen=True)
class WrittenNumber:
    """One number as written in a text."""

    raw: str
    value: float
    #: Half a unit in the last written place (in ``value``'s scale).
    implied_tol: float
    percent: bool = False
    #: Written right after a ``±``: an uncertainty, not a point value.
    uncertainty: bool = False

    def candidates(self) -> list[tuple[float, float]]:
        """``(value, implied_tol)`` readings: a percent also reads as a fraction."""
        out = [(self.value, self.implied_tol)]
        if self.percent:
            out.append((self.value / 100.0, self.implied_tol / 100.0))
        return out


_SUPERSCRIPT = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")

# Token: sign? mantissa (thousands-grouped or plain, optional decimals)
# exponent? (e-notation or "x 10^n") percent?
_TOKEN = re.compile(
    r"""
    (?<![\w.])                                  # not inside an identifier/number
    (?P<sign>[-+](?=[\d.]))?
    (?:
      10\s*\^\s*(?P<pow>[-+]?\d+)              # a bare power of ten: 10^-3
    |
      (?P<mant>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)
      (?:[eE](?P<exp>[-+]?\d+))?
      (?:\s*(?:×|\*|x|X)\s*10\s*\^\s*(?P<exp10>[-+]?\d+))?
    )
    (?P<pct>\s*%)?
    """,
    re.VERBOSE,
)
_PM = re.compile(r"(?:±|\+/-|\+-)\s*$")


def _normalize(text: str) -> str:
    t = text.replace("−", "-").replace("–", "-").replace("\u2009", "")
    t = t.replace("\u202f", "").replace("\u00a0", " ")
    t = re.sub(r"\\num\{([^}]*)\}", r"\1", t)
    t = t.replace("\\%", "%").replace("\\pm", "±").replace("\\times", "×")
    t = t.replace("\\cdot", "×").replace("$", " ")
    t = re.sub(r"\^\{\s*([-+]?\d+)\s*\}", r"^\1", t)
    # Unicode superscript exponents: 10⁻³ -> 10^-3
    t = re.sub(
        r"10([⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+)",
        lambda m: "10^" + m.group(1).translate(_SUPERSCRIPT),
        t,
    )
    return t


def parse_numbers(text: Any) -> list[WrittenNumber]:
    """Every number written in ``text``, in order (``[]`` for non-text)."""
    if text is None or isinstance(text, bool):
        return []
    if isinstance(text, (int, float)):
        text = repr(text)
    if not isinstance(text, str):
        return []
    norm = _normalize(text)
    out: list[WrittenNumber] = []
    for m in _TOKEN.finditer(norm):
        if m.group("pow") is not None:
            # "10^-3": one significant figure at that power.
            dec, exp_digits, exponent = Decimal(1), 0, int(m.group("pow"))
        else:
            try:
                dec = Decimal(m.group("mant").replace(",", ""))
            except InvalidOperation:
                continue
            exp_digits = dec.as_tuple().exponent
            exponent = int(m.group("exp") or 0) + int(m.group("exp10") or 0)
        sign = -1.0 if m.group("sign") == "-" else 1.0
        scale = 10.0**exponent
        value = sign * float(dec) * scale
        implied = 0.5 * 10.0 ** (exp_digits if isinstance(exp_digits, int) else 0)
        out.append(
            WrittenNumber(
                raw=m.group(0).strip(),
                value=value,
                implied_tol=implied * scale,
                percent=bool(m.group("pct")),
                uncertainty=bool(_PM.search(norm[: m.start()])),
            )
        )
    return out


def agrees(
    number: float,
    written_value: float,
    implied_tol: float,
    tolerance: Mapping[str, float] | None,
) -> bool:
    """``number`` agrees with a written value within the claim's tolerance.

    A declared ``abs_tol`` / ``rel_tol`` is used verbatim; otherwise the
    written value's own precision (``implied_tol``) is the tolerance.
    """
    tol = dict(tolerance or {})
    if tol.get("abs_tol") is None and tol.get("rel_tol") is None:
        abs_tol, rel_tol = implied_tol, 0.0
    else:
        abs_tol, rel_tol = tol.get("abs_tol") or 0.0, tol.get("rel_tol") or 0.0
    # float slack so 4.235 vs 4.23 (±0.005) passes despite binary rounding
    slack = 1e-12 * max(1.0, abs(number), abs(written_value))
    return math.isclose(number, written_value, rel_tol=rel_tol, abs_tol=abs_tol + slack)


def text_agrees_with(
    text: Any, number: float, tolerance: Mapping[str, float] | None = None
) -> WrittenNumber | None:
    """The first point number written in ``text`` that agrees with ``number``.

    Uncertainties (after ``±``) are not point values and never match.
    """
    for tok in parse_numbers(text):
        if tok.uncertainty:
            continue
        for value, implied in tok.candidates():
            if agrees(number, value, implied, tolerance):
                return tok
    return None


def numeric_leaves(value: Any, prefix: str = "") -> list[tuple[str, int | float]]:
    """``(path, number)`` for every numeric leaf of a structured claim value.

    A bare scalar yields ``[(".", x)]``; a dict/list yields JSON-Pointer-like
    paths. Booleans and strings are not numeric leaves. Numbers keep their
    type so the precision they were registered with stays readable
    (``120`` is ±0.5, ``120.0`` ±0.05).
    """
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return []
        return [(prefix or ".", value)]
    if isinstance(value, dict):
        out: list[tuple[str, int | float]] = []
        for k, v in value.items():
            out.extend(numeric_leaves(v, f"{prefix}/{k}"))
        return out
    if isinstance(value, (list, tuple)):
        out = []
        for i, v in enumerate(value):
            out.extend(numeric_leaves(v, f"{prefix}/{i}"))
        return out
    return []


# EOF
