#!/usr/bin/env python3
"""Rewrite a records document's paths from the source checkout to the target's.

clew records absolute paths: where the script ran, where each file was read
or written, where a claim's manuscript and source live. Records exported on
one machine name that machine's checkout. A target that checks every path
against ITS project root (the Hub Clew app refuses anything outside it) needs
those paths moved to its own root, so ``clew records import --rebase
SRC_ROOT=DST_ROOT`` rewrites them before the records are written.

A path is rewritten when it IS a source root or lies under one (component
boundary: ``/a/proj`` covers ``/a/proj/x`` but not ``/a/project``). The most
specific (longest) matching root wins. An absolute path under no source root
is left exactly as it is and reported as EXTERNAL — a shared dataset or a
sibling project's output is not this checkout's to move, and silently
pointing it somewhere else would forge provenance.

Fields rewritten (scalar paths):
  runs.script_path, file_hashes.file_path, claims.file_path,
  claims.source_file, citations.manuscript_file.
Fields rewritten inside their JSON text (every string that is a path under a
source root; nothing else in them is touched):
  runs.metadata, file_hashes.derived_from, file_hashes.external.
Not rewritten: identities that are not paths (``claim_id`` stays what it was,
even when it was derived from the old location) and free-form caller data
(``claims.metadata``, stamp metadata).
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from typing import Any

__all__ = ["JSON_PATH_FIELDS", "PATH_FIELDS", "parse_rebase", "rebase_tables"]

#: Scalar path-valued fields, per table.
PATH_FIELDS: dict[str, tuple[str, ...]] = {
    "runs": ("script_path",),
    "file_hashes": ("file_path",),
    "claims": ("file_path", "source_file"),
    "citations": ("manuscript_file",),
}

#: TEXT fields holding JSON whose string leaves may be paths.
JSON_PATH_FIELDS: dict[str, tuple[str, ...]] = {
    "runs": ("metadata",),
    "file_hashes": ("derived_from", "external"),
}

#: How many external paths a report names (the count is always complete).
_EXTERNAL_SAMPLE = 20


def _normalise(root: str) -> str:
    stripped = root.rstrip("/")
    return stripped or "/"


def parse_rebase(specs: Iterable[str]) -> list[tuple[str, str]]:
    """``["SRC=DST", ...]`` -> ``[(src, dst), ...]``, most specific first.

    Both sides must be absolute POSIX paths; a source root may appear once.
    """
    rules: dict[str, str] = {}
    for spec in specs:
        src, sep, dst = spec.partition("=")
        if not sep or not src.startswith("/") or not dst.startswith("/"):
            raise ValueError(
                f"--rebase {spec!r}: expected SRC_ROOT=DST_ROOT with both roots absolute"
            )
        src, dst = _normalise(src), _normalise(dst)
        if src in rules and rules[src] != dst:
            raise ValueError(f"--rebase: source root {src!r} is mapped twice")
        rules[src] = dst
    return sorted(rules.items(), key=lambda rule: len(rule[0]), reverse=True)


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _rewrite(path: str, rules: list[tuple[str, str]]) -> str | None:
    """The rebased path, or ``None`` when no source root covers ``path``."""
    for src, dst in rules:
        if _under(path, src):
            rest = path[len(src) :].lstrip("/") if src != "/" else path.lstrip("/")
            return dst if not rest else f"{dst.rstrip('/')}/{rest}"
    return None


def _rewrite_tree(obj: Any, rules: list[tuple[str, str]]) -> tuple[Any, int]:
    """Rebase every string leaf of a JSON value that a source root covers."""
    if isinstance(obj, str):
        new = _rewrite(obj, rules) if obj.startswith("/") else None
        return (new, 1) if new is not None and new != obj else (obj, 0)
    if isinstance(obj, list):
        pairs = [_rewrite_tree(item, rules) for item in obj]
        return [p[0] for p in pairs], sum(p[1] for p in pairs)
    if isinstance(obj, dict):
        out, total = {}, 0
        for key, value in obj.items():
            out[key], n = _rewrite_tree(value, rules)
            total += n
        return out, total
    return obj, 0


def _rebase_json_text(text: Any, rules) -> tuple[Any, int]:
    if not isinstance(text, str):
        return text, 0
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, 0
    rebased, n = _rewrite_tree(parsed, rules)
    return (json.dumps(rebased), n) if n else (text, 0)


def rebase_tables(
    tables: Mapping[str, Any], rules: list[tuple[str, str]]
) -> tuple[dict, dict]:
    """A rebased deep copy of ``tables``, and a report of what moved.

    The report: ``rules``, ``rewritten`` (scalar paths moved),
    ``rewritten_in_json`` (paths moved inside JSON fields), ``external``
    (absolute scalar paths under no source root, left as they were),
    ``external_by_field`` and up to 20 ``external_examples``.
    """
    out = copy.deepcopy(dict(tables))
    report: dict[str, Any] = {
        "rules": [{"from": s, "to": d} for s, d in rules],
        "rewritten": 0,
        "rewritten_in_json": 0,
        "external": 0,
        "external_by_field": {},
        "external_examples": [],
    }
    if not rules:
        return out, report
    examples: set[str] = set()
    for name, table in out.items():
        for row in table.get("rows", []):
            values = row["values"]
            for field in PATH_FIELDS.get(name, ()):
                path = values.get(field)
                if not isinstance(path, str) or not path.startswith("/"):
                    continue
                new = _rewrite(path, rules)
                if new is None:
                    key = f"{name}.{field}"
                    report["external"] += 1
                    report["external_by_field"][key] = (
                        report["external_by_field"].get(key, 0) + 1
                    )
                    examples.add(path)
                elif new != path:
                    values[field] = new
                    report["rewritten"] += 1
            for field in JSON_PATH_FIELDS.get(name, ()):
                values[field], n = _rebase_json_text(values.get(field), rules)
                report["rewritten_in_json"] += n
    report["external_examples"] = sorted(examples)[:_EXTERNAL_SAMPLE]
    return out, report


# EOF
