#!/usr/bin/env python3
"""Verify an evidence bundle against a checkout: schema, signature, file hashes.

Store-free and read-only: it reads the bundle and the files under the project
root, nothing else. Every problem is a FINDING in the result, never an
exception — a malformed bundle, a missing file and a bad signature are all
answers, not crashes. ``ok`` is True only when the bundle validates, a
present signature verifies, and every recorded input/output/script hash
matches the file in the project root (a missing file fails too, unless
``allow_missing``). Which tree is "the project root" is decided by
:mod:`._root` and reported — an ambiguous choice raises, it is never guessed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._canonical import sha256_bytes
from ._relpaths import is_portable
from ._root import resolve_bundle_root
from ._schema import SchemaValidatorMissing, schema_errors
from ._signing import SigningUnavailable, verify_document

__all__ = ["load_bundle", "verify_bundle"]


def load_bundle(path: str | Path) -> tuple[Any, bytes]:
    """``(document, raw bytes)`` of the bundle file (raises on unreadable JSON)."""
    raw = Path(path).read_bytes()
    return json.loads(raw.decode("utf-8")), raw


def _expected_files(doc: dict) -> list[dict]:
    """``{path, role, run_id, expected}`` per recorded in-project file, deduped."""
    seen: set[tuple[str, str]] = set()
    out = []
    for run in doc.get("runs") or []:
        if not isinstance(run, dict):
            continue
        items = [("script", run.get("script"), run.get("script_sha256"))]
        items += [("input", p, h) for p, h in (run.get("inputs") or {}).items()]
        items += [("output", p, h) for p, h in (run.get("outputs") or {}).items()]
        for role, rel, digest in items:
            if not rel or not digest or (rel, digest) in seen:
                continue
            seen.add((rel, digest))
            out.append({"path": rel, "role": role, "run_id": run.get("run_id"),
                        "expected": digest})  # fmt: skip
    return out


def _check_file(item: dict, root: Path) -> dict:
    from .._hash import hash_like, hashes_match

    rel = item["path"]
    if not is_portable(rel):
        return {**item, "actual": None, "status": "not_portable"}
    path = root / rel
    if not path.is_file():
        return {**item, "actual": None, "status": "missing"}
    actual = hash_like(path, item["expected"])
    status = "match" if hashes_match(item["expected"], actual) else "mismatch"
    return {**item, "actual": actual, "status": status}


def verify_bundle(
    bundle_path: str | Path,
    project_root: str | Path | None = None,
    *,
    expected_key_id: str | None = None,
    allow_missing: bool = False,
) -> dict:
    """Verify the bundle at ``bundle_path`` against ``project_root`` (see module doc).

    ``project_root=None`` resolves the tree with
    :func:`._root.resolve_bundle_root` (the bundle's own project, which must
    agree with the working directory's; else :class:`ProjectRootAmbiguous`).
    The result always names the tree checked (``project_root``) and the rule
    that chose it (``project_root_source``).
    """
    where = resolve_bundle_root(bundle_path, project_root)
    root = Path(where["project_root"])
    findings: list[dict] = []
    result: dict[str, Any] = {
        "ok": False,
        "bundle": str(bundle_path),
        "bundle_sha256": None,
        "project_root": str(root),
        "project_root_source": where["project_root_source"],
        "bundle_home": where["bundle_home"],
        "schema_valid": False,
        "schema_errors": [],
        "signed": False,
        "signature": None,
        "files": {"checked": 0, "matched": 0, "mismatched": [], "missing": []},
        "findings": findings,
    }
    try:
        doc, raw = load_bundle(bundle_path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        findings.append(
            {"code": "unreadable", "message": f"cannot read the bundle: {exc}"}
        )
        return result
    result["bundle_sha256"] = sha256_bytes(raw)
    if not isinstance(doc, dict):
        findings.append(
            {"code": "not_an_object", "message": "the bundle is not a JSON object"}
        )
        return result

    try:
        result["schema_errors"] = schema_errors(doc, "evidence-bundle")
        result["schema_valid"] = not result["schema_errors"]
        if result["schema_errors"]:
            findings.append({"code": "schema_invalid",
                             "message": f"{len(result['schema_errors'])} schema violation(s)"})  # fmt: skip
    except SchemaValidatorMissing as exc:
        findings.append({"code": "schema_validator_missing", "message": str(exc)})

    try:
        sig = verify_document(doc, expected_key_id=expected_key_id)
    except SigningUnavailable as exc:
        sig = {"signed": True, "valid": None, "reason": str(exc)}
        findings.append({"code": "signature_unverifiable", "message": str(exc)})
    result["signed"], result["signature"] = sig["signed"], sig
    if sig["signed"] and sig["valid"] is False:
        findings.append({"code": "signature_invalid", "message": sig["reason"]})
    if not sig["signed"] and expected_key_id is not None:
        findings.append({"code": "signature_required",
                         "message": f"unsigned, but key {expected_key_id} was expected"})  # fmt: skip

    files = result["files"]
    for item in _expected_files(doc):
        checked = _check_file(item, root)
        files["checked"] += 1
        if checked["status"] == "match":
            files["matched"] += 1
        elif checked["status"] == "missing":
            files["missing"].append(checked)
        else:
            files["mismatched"].append(checked)
            findings.append({"code": f"file_{checked['status']}", "path": item["path"],
                             "message": f"{item['role']} {item['path']}: recorded "
                             f"{item['expected']}, found {checked['actual']}"})  # fmt: skip
    for missing in files["missing"]:
        findings.append({"code": "file_missing", "path": missing["path"],
                         "severity": "warning" if allow_missing else "error",
                         "message": f"{missing['role']} {missing['path']} is not in "
                         "the project root"})  # fmt: skip
    result["ok"] = not [f for f in findings if f.get("severity") != "warning"]
    return result


# EOF
