#!/usr/bin/env python3
"""Justify a claimed value that has no locator by searching its source.

A claim that states a value but declares no ``source_keys`` used to be
"verified" on its source file's hash alone: the claimed number was never
compared with anything, and nothing said so. This module closes that gap
without asking the author for a locator first.

Rule
----
1. **What is checked.** A claim *states a value* when it has a structured
   ``value``, or when it is a ``value`` / ``statistic`` claim whose display
   text (``claim_value``) writes at least one number. Each numeric leaf of
   ``value`` (else each point number written in the text; uncertainties
   after ``±`` are reported, not required) is one *claimed number*. A string
   ``value`` is one claimed string.
2. **Where it is searched.** The claim's ``source_file``, when it is a
   structured source clew can read without guessing: JSON / YAML (every
   numeric leaf, and every string leaf that is a plain number), CSV / TSV
   (every data cell), and NumPy ``.npy`` (every element of an array of at
   most :data:`MAX_NPY_ELEMENTS`; needs numpy, which clew core does not).
3. **What counts as a match.** A source value within the claim's tolerance:
   the DECLARED ``abs_tol`` / ``rel_tol`` when the claim has one, else the
   precision the claimed number was written with (``0.25`` -> ±0.005,
   ``25%`` -> ±0.5 percent points, also read as the fraction 0.25 ±0.005).
4. **Justified** iff EVERY claimed number matches EXACTLY ONE location in
   the source. The location found is recorded (``locator`` in the check,
   ``matched_by: "search"``), so the report says where the value was taken
   from and what to pin as ``source_keys``.
5. **Unchecked** otherwise — no match (the value is not in the source as
   written: it may be derived, or wrong), several matches (the search
   cannot tell which location the claim means, so it proves nothing), or
   an unsearchable source. Unchecked is NOT a mismatch: without a locator
   clew cannot prove the value wrong, only that it did not verify it. It is
   reported as ``VALUE_UNCHECKED`` (exit 24): a warning by default, an error
   under ``--strict`` — never silent.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from ._locator import STRUCTURED_SUFFIXES, TABULAR_SUFFIXES, implied_abs_tol
from ._numbers import agrees, numeric_leaves, parse_numbers

__all__ = [
    "MAX_NPY_ELEMENTS",
    "Unsearchable",
    "claimed_numbers",
    "justify_by_search",
    "states_a_value",
]

#: Arrays larger than this are not searched (a coincidental match among
#: millions of elements proves nothing, and the read is not free).
MAX_NPY_ELEMENTS = 100_000
NPY_SUFFIXES = (".npy",)
VALUE_CLAIM_TYPES = ("value", "statistic")


class Unsearchable(ValueError):
    """The source cannot be searched for values (format / size / reader)."""


# ---------------------------------------------------------------------------
# What the claim states
# ---------------------------------------------------------------------------


def states_a_value(claim) -> bool:
    """Whether ``claim`` asserts a value that verification must check."""
    if claim.value is not None:
        return True
    if claim.claim_type not in VALUE_CLAIM_TYPES:
        return False
    return any(not t.uncertainty for t in parse_numbers(claim.claim_value))


def claimed_numbers(claim) -> tuple[list[dict], list[str]]:
    """``(items, notes)``: every claimed number/string, with its own tolerance.

    Each item is ``{"field", "kind": "number"|"string", "readings":
    [(value, implied_tol), ...], "shown"}``. ``notes`` lists what is
    deliberately not required (uncertainties).
    """
    items: list[dict] = []
    notes: list[str] = []
    if claim.value is not None:
        if isinstance(claim.value, str):
            items.append(
                {
                    "field": ".",
                    "kind": "string",
                    "readings": [(claim.value.strip(), 0.0)],
                    "shown": claim.value,
                }
            )
            return items, notes
        for path, number in numeric_leaves(claim.value):
            items.append(
                {
                    "field": path,
                    "kind": "number",
                    "readings": [(number, implied_abs_tol(repr(number)))],
                    "shown": repr(number),
                }
            )
        return items, notes
    for i, tok in enumerate(parse_numbers(claim.claim_value)):
        if tok.uncertainty:
            notes.append(f"uncertainty ±{tok.raw} not checked")
            continue
        if tok.bound:
            # "p < 0.001" names no point value to look for: searching the
            # source for 0.001 would test the wrong number.
            notes.append(f"bound {tok.raw} not searched (no point value)")
            continue
        items.append(
            {
                "field": f"text#{i}",
                "kind": "number",
                "readings": tok.candidates(),
                "shown": tok.raw,
            }
        )
    return items, notes


# ---------------------------------------------------------------------------
# What the source holds
# ---------------------------------------------------------------------------


def _walk(node: Any, pointer: str) -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for k, v in node.items():
            token = str(k).replace("~", "~0").replace("/", "~1")
            yield from _walk(v, f"{pointer}/{token}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{pointer}/{i}")
    else:
        yield pointer, node


def _scalar(raw: Any) -> Any:
    """A source leaf as a number when it is one, else a stripped string."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        text = raw.strip()
        try:
            return float(text)
        except ValueError:
            return text
    return None


def source_leaves(source_file: str | Path) -> list[tuple[dict, Any]]:
    """``(locator, value)`` for every scalar in a searchable source."""
    path = Path(source_file)
    suffix = path.suffix.lower()
    if suffix in STRUCTURED_SUFFIXES:
        from ._locator import _load_structured

        doc = _load_structured(path)
        return [({"pointer": p}, _scalar(v)) for p, v in _walk(doc, "")]
    if suffix in TABULAR_SUFFIXES:
        delimiter = "\t" if suffix == ".tsv" else ","
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh, delimiter=delimiter))
        if not rows:
            return []
        header, data = rows[0], rows[1:]
        out = []
        for r, record in enumerate(data):
            for c, cell in enumerate(record):
                column = header[c] if c < len(header) else c
                out.append(({"row": r, "column": column}, _scalar(cell)))
        return out
    if suffix in NPY_SUFFIXES:
        try:
            import numpy as np
        except ImportError as exc:  # clew core is stdlib-only
            raise Unsearchable(f"searching {path.name} needs numpy") from exc
        arr = np.load(path, allow_pickle=False)
        if arr.size > MAX_NPY_ELEMENTS:
            raise Unsearchable(
                f"{path.name} holds {arr.size} elements (> {MAX_NPY_ELEMENTS}); "
                f"too many to search without a locator"
            )
        if arr.dtype.kind not in "biuf":
            raise Unsearchable(f"{path.name} is not a numeric array ({arr.dtype})")
        if arr.ndim == 0:
            return [({"index": []}, _scalar(arr.item()))]
        return [
            ({"index": list(idx)}, _scalar(arr[idx].item()))
            for idx in np.ndindex(arr.shape)
        ]
    raise Unsearchable(
        f"{path.name}: not a searchable structured source "
        f"({', '.join(STRUCTURED_SUFFIXES + TABULAR_SUFFIXES + NPY_SUFFIXES)})"
    )


def _describe(locator: dict) -> str:
    if "pointer" in locator:
        return locator["pointer"] or "/"
    if "index" in locator:
        return f"[{', '.join(str(i) for i in locator['index'])}]"
    return f"row {locator['row']}, column {locator['column']!r}"


# ---------------------------------------------------------------------------
# The search
# ---------------------------------------------------------------------------


def justify_by_search(
    claim, tolerance: Mapping[str, float] | None = None
) -> list[dict[str, Any]]:
    """One check per claimed number: matched uniquely in the source, or not.

    Each check is ``{"field", "ok", "error": False, "unchecked",
    "matched_by": "search", "locator", "detail"}``; ``unchecked`` is True
    when the number could not be justified (see the module rule).
    """
    items, notes = claimed_numbers(claim)
    name = Path(claim.source_file).name
    try:
        leaves = source_leaves(claim.source_file)
    except (Unsearchable, OSError, ValueError, json.JSONDecodeError) as exc:
        why = str(exc) if isinstance(exc, Unsearchable) else f"unreadable: {exc}"
        return [
            {
                "field": item["field"],
                "ok": False,
                "error": False,
                "unchecked": True,
                "matched_by": "search",
                "locator": None,
                "detail": f"value {item['shown']} unchecked: no source_keys and {why}",
            }
            for item in items
        ]

    checks: list[dict[str, Any]] = []
    for item in items:
        hits = []
        for locator, actual in leaves:
            if actual is None:
                continue
            if item["kind"] == "string":
                if isinstance(actual, str) and actual == item["readings"][0][0]:
                    hits.append(locator)
                continue
            if isinstance(actual, str):
                continue
            if any(
                agrees(actual, value, implied, tolerance)
                for value, implied in item["readings"]
            ):
                hits.append(locator)
        if len(hits) == 1:
            where = _describe(hits[0])
            checks.append(
                {
                    "field": item["field"],
                    "ok": True,
                    "error": False,
                    "unchecked": False,
                    "matched_by": "search",
                    "locator": hits[0],
                    "detail": (
                        f"value {item['shown']} found at {where} in {name} "
                        f"(unique match by search; pin it with source_keys)"
                    ),
                }
            )
            continue
        why = (
            f"not found in {name}"
            if not hits
            else f"ambiguous: {len(hits)} locations in {name} match "
            f"({', '.join(_describe(h) for h in hits[:3])}"
            f"{', ...' if len(hits) > 3 else ''})"
        )
        checks.append(
            {
                "field": item["field"],
                "ok": False,
                "error": False,
                "unchecked": True,
                "matched_by": "search",
                "locator": None,
                "detail": (
                    f"value {item['shown']} unchecked: no source_keys and {why} "
                    f"— declare source_keys to verify it"
                ),
            }
        )
    for note in notes:
        checks.append(
            {
                "field": "note",
                "ok": True,
                "error": False,
                "unchecked": False,
                "matched_by": "search",
                "locator": None,
                "detail": note,
            }
        )
    return checks


# EOF
