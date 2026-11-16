#!/usr/bin/env python3
"""Claim-value-vs-source: re-read a claim's number from the file that produced it.

A hash says the source FILE has not changed since registration. It does not
say the number typed into the manuscript is the number IN that file — a claim
registered as ``0.91`` against a JSON that says ``0.81`` hashes perfectly.
A claim may therefore record WHERE inside its source each value field lives
(a *locator*); verification re-reads that location and compares it to the
claim's value within a tolerance.

The shape is the one scitex-writer registers (scitex-writer PR #502), so a
writer claim needs no translation layer.

``source_keys``
---------------
Maps a field of the claim's structured ``value`` dict — or ``"."`` for a claim
whose value is a bare scalar — to a locator dict::

    # structured sources (.json / .yaml / .yml) — RFC 6901 JSON Pointer
    {"pointer": "/results/0/auc"}

    # tabular sources (.csv / .tsv) — one cell
    {"row": 3, "column": "auc"}                 # 0-based data row
    {"row": {"subject": "S01"}, "column": 2}    # row selected by column values;
                                                # must match EXACTLY one row

    # optional on either form — overrides the claim-level tolerance
    {"pointer": "/auc", "abs_tol": 0.001, "rel_tol": 0.0}

A bare string is shorthand for ``{"pointer": <string>}``.

The claimed value of field ``"."`` is the claim's structured ``value`` when
given, else its display string ``claim_value``.

Tolerance
---------
Declared tolerances (``abs_tol`` / ``rel_tol``, per locator or claim-level
``tolerance``) are used verbatim. When NOTHING is declared, the tolerance is
implied by the precision the claim value was WRITTEN with: ``4.23`` asserts
"the source rounds to 4.23", i.e. ±0.005. Strings and booleans compare
exactly.
"""

from __future__ import annotations

import csv
import json
import math
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

STRUCTURED_SUFFIXES = (".json", ".yaml", ".yml")
TABULAR_SUFFIXES = (".csv", ".tsv")
WHOLE_VALUE = "."

__all__ = [
    "WHOLE_VALUE",
    "SourceLocatorError",
    "check_claim_against_source",
    "compare",
    "implied_abs_tol",
    "normalize_locator",
    "normalize_source_keys",
    "normalize_tolerance",
    "read_source_value",
]


class SourceLocatorError(ValueError):
    """A locator is malformed or does not resolve inside its source file."""


# ---------------------------------------------------------------------------
# Normalisation / validation (fail loud at registration)
# ---------------------------------------------------------------------------


def _check_tol(key: str, val: Any) -> None:
    if isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:
        raise SourceLocatorError(f"{key} must be a non-negative number, got {val!r}")


def normalize_locator(locator: Any) -> dict[str, Any]:
    """Return the canonical dict form of ``locator`` or raise loudly."""
    if isinstance(locator, str):
        locator = {"pointer": locator}
    if not isinstance(locator, dict):
        raise SourceLocatorError(
            f"source locator must be a JSON-Pointer string or a dict, got "
            f"{type(locator).__name__}: {locator!r}"
        )
    allowed = {"pointer", "row", "column", "abs_tol", "rel_tol"}
    unknown = set(locator) - allowed
    if unknown:
        raise SourceLocatorError(
            f"unknown locator key(s) {sorted(unknown)}; allowed: {sorted(allowed)}"
        )
    has_pointer = "pointer" in locator
    has_cell = "row" in locator or "column" in locator
    if has_pointer == has_cell:
        raise SourceLocatorError(
            "a locator needs EITHER 'pointer' (json/yaml) OR 'row'+'column' "
            f"(csv/tsv): {locator!r}"
        )
    if has_pointer:
        ptr = locator["pointer"]
        if not isinstance(ptr, str) or not (ptr == "" or ptr.startswith("/")):
            raise SourceLocatorError(
                f"'pointer' must be an RFC 6901 JSON Pointer ('' or '/a/0/b'): {ptr!r}"
            )
    else:
        if "row" not in locator or "column" not in locator:
            raise SourceLocatorError(
                f"a tabular locator needs both 'row' and 'column': {locator!r}"
            )
        row = locator["row"]
        if not (
            (isinstance(row, int) and not isinstance(row, bool))
            or (isinstance(row, dict) and row)
        ):
            raise SourceLocatorError(
                f"'row' must be a 0-based int or a non-empty {{column: value}} "
                f"selector: {row!r}"
            )
    for key in ("abs_tol", "rel_tol"):
        if key in locator:
            _check_tol(key, locator[key])
    return dict(locator)


def normalize_tolerance(tolerance: dict[str, Any] | None) -> dict[str, float]:
    """Claim-level tolerance: ``{"abs_tol": x, "rel_tol": y}`` (either optional)."""
    if tolerance is None:
        return {}
    if not isinstance(tolerance, dict):
        raise SourceLocatorError(f"tolerance must be a dict, got {tolerance!r}")
    unknown = set(tolerance) - {"abs_tol", "rel_tol"}
    if unknown:
        raise SourceLocatorError(
            f"unknown tolerance key(s) {sorted(unknown)}; allowed: abs_tol, rel_tol"
        )
    for key, val in tolerance.items():
        _check_tol(key, val)
    return {k: float(v) for k, v in tolerance.items()}


def normalize_source_keys(source_keys: dict[str, Any] | None) -> dict[str, dict]:
    """``{field: locator}`` with every locator normalised."""
    if source_keys is None:
        return {}
    if not isinstance(source_keys, dict):
        raise SourceLocatorError(
            f"source_keys must map value-field -> locator, got {source_keys!r}"
        )
    return {str(f): normalize_locator(loc) for f, loc in source_keys.items()}


# ---------------------------------------------------------------------------
# Reading a located value
# ---------------------------------------------------------------------------


def _resolve_pointer(doc: Any, pointer: str) -> Any:
    if pointer == "":
        return doc
    node = doc
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if token not in node:
                raise SourceLocatorError(f"pointer {pointer!r}: no key {token!r}")
            node = node[token]
        elif isinstance(node, list):
            if not token.isdigit() or int(token) >= len(node):
                raise SourceLocatorError(
                    f"pointer {pointer!r}: {token!r} is not an index of a "
                    f"{len(node)}-element list"
                )
            node = node[int(token)]
        else:
            raise SourceLocatorError(
                f"pointer {pointer!r}: cannot descend into {type(node).__name__} "
                f"at {token!r}"
            )
    return node


def _load_structured(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as e:  # clew core is stdlib-only
        raise SourceLocatorError(
            f"reading {path.name} needs PyYAML (pip install pyyaml)"
        ) from e
    return yaml.safe_load(text)


def _read_cell(path: Path, locator: dict[str, Any]) -> str:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh, delimiter=delimiter))
    if not rows:
        raise SourceLocatorError(f"{path.name} is empty")
    header, data = rows[0], rows[1:]
    column = locator["column"]
    if isinstance(column, int) and not isinstance(column, bool):
        col_idx = column
        if not 0 <= col_idx < len(header):
            raise SourceLocatorError(f"column index {column} out of range")
    else:
        if column not in header:
            raise SourceLocatorError(f"no column {column!r} in {header}")
        col_idx = header.index(column)

    row = locator["row"]
    if isinstance(row, int):
        if not 0 <= row < len(data):
            raise SourceLocatorError(f"row {row} out of range ({len(data)} rows)")
        record = data[row]
    else:
        for key in row:
            if key not in header:
                raise SourceLocatorError(f"row selector column {key!r} not in {header}")
        hits = [
            r for r in data if all(r[header.index(k)] == str(v) for k, v in row.items())
        ]
        if len(hits) != 1:
            raise SourceLocatorError(
                f"row selector {row!r} matched {len(hits)} rows (need exactly 1)"
            )
        record = hits[0]
    return record[col_idx]


def read_source_value(source_file: str | Path, locator: dict[str, Any]) -> Any:
    """Return the value at ``locator`` inside ``source_file`` (raise loudly)."""
    source_file = Path(source_file)
    if not source_file.is_file():
        raise SourceLocatorError(f"source file does not exist: {source_file}")
    suffix = source_file.suffix.lower()
    if "pointer" in locator:
        if suffix not in STRUCTURED_SUFFIXES:
            raise SourceLocatorError(
                f"a 'pointer' locator needs a {STRUCTURED_SUFFIXES} source, "
                f"got {source_file.name}"
            )
        return _resolve_pointer(_load_structured(source_file), locator["pointer"])
    if suffix not in TABULAR_SUFFIXES:
        raise SourceLocatorError(
            f"a 'row'/'column' locator needs a {TABULAR_SUFFIXES} source, "
            f"got {source_file.name}"
        )
    return _read_cell(source_file, locator)


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def implied_abs_tol(claimed: Any) -> float:
    """Half a unit in the last WRITTEN place of ``claimed`` (4.23 -> 0.005)."""
    try:
        exponent = Decimal(str(claimed).strip()).as_tuple().exponent
    except (InvalidOperation, ValueError):
        return 0.0
    if not isinstance(exponent, int):
        return 0.0
    return 0.5 * 10.0**exponent


def claimed_field(value: Any, field: str) -> Any:
    if field == WHOLE_VALUE:
        return value
    if not isinstance(value, dict) or field not in value:
        raise SourceLocatorError(
            f"source_keys names field {field!r}, but the claim value has no such "
            f"field (fields: {sorted(value) if isinstance(value, dict) else '-'}; "
            f"use {WHOLE_VALUE!r} for a scalar claim value)"
        )
    return value[field]


def compare(
    claimed: Any, actual: Any, locator: dict[str, Any], tolerance: dict[str, float]
) -> tuple[bool, str]:
    """``(ok, explanation)`` for one field."""
    c_num, a_num = _as_number(claimed), _as_number(actual)
    if c_num is None or a_num is None:
        ok = str(claimed).strip() == str(actual).strip()
        return ok, f"claimed {claimed!r} vs source {actual!r} (exact match)"
    declared = {k: locator.get(k, tolerance.get(k)) for k in ("abs_tol", "rel_tol")}
    if declared["abs_tol"] is None and declared["rel_tol"] is None:
        abs_tol, rel_tol, how = implied_abs_tol(claimed), 0.0, "implied by precision"
    else:
        abs_tol = declared["abs_tol"] or 0.0
        rel_tol = declared["rel_tol"] or 0.0
        how = "declared"
    # float slack on the comparison itself so 4.235 vs 4.23 (±0.005) passes
    ok = math.isclose(c_num, a_num, rel_tol=rel_tol, abs_tol=abs_tol + 1e-12)
    return ok, (
        f"claimed {claimed!r} vs source {actual!r} "
        f"(|diff|={abs(c_num - a_num):.6g}; abs_tol={abs_tol:g}, "
        f"rel_tol={rel_tol:g}, {how})"
    )


def check_claim_against_source(
    value: Any,
    source_file: str | None,
    source_keys: dict[str, dict],
    tolerance: dict[str, float],
) -> list[dict[str, Any]]:
    """One ``{"field", "ok", "error", "detail"}`` per located field (never raises).

    ``error`` is True when the value could not be READ (unresolvable locator,
    missing field, unreadable file) — distinct from a value that was read and
    disagrees.
    """
    results = []
    for field, locator in source_keys.items():
        error = False
        try:
            if not source_file:
                raise SourceLocatorError("claim has source_keys but no source_file")
            claimed = claimed_field(value, field)
            actual = read_source_value(Path(source_file), locator)
            ok, detail = compare(claimed, actual, locator, tolerance)
        except (SourceLocatorError, OSError, ValueError) as exc:
            ok, error, detail = False, True, f"cannot read source value: {exc}"
        results.append({"field": field, "ok": ok, "error": error, "detail": detail})
    return results


# EOF
