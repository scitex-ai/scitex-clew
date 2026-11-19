#!/usr/bin/env python3
"""Build an evidence bundle from the host store, for one project.

Which runs: by default the runs that produced the project AS IT IS ON DISK —
a recorded, successful run is kept when every in-project output it recorded
is present with the recorded hash, and it is the newest such producer of at
least one of them. Superseded history (an older run whose outputs were since
overwritten) is not evidence for this snapshot and is left out;
``all_runs=True`` exports every recorded run instead.

Claims come from clew's evidence-provider report (the same strict verdict,
4-state vocabulary and minimal graph ``clew export-evidence`` emits), plus
the claim's :func:`~._precision.precision_of` and the bundle runs that
produced it. Every path is made repo-relative (:mod:`._relpaths`).
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from ._canonical import sha256_file
from ._precision import precision_of
from ._relpaths import external_name, relative_argv, relative_or_none

__all__ = ["BUNDLE_SCHEMA", "BUNDLE_SCHEMA_VERSION", "build_bundle"]

BUNDLE_SCHEMA = "scitex-clew.evidence-bundle"
BUNDLE_SCHEMA_VERSION = "1.0.0"
_RUN_PAGE = 1_000


def _metadata(run: dict) -> dict:
    raw = run.get("metadata")
    if not raw:
        return {}
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


def _all_runs(db) -> list[dict]:
    runs, offset = [], 0
    while True:
        page = db.list_runs(limit=_RUN_PAGE, offset=offset)
        runs.extend(page)
        if len(page) < _RUN_PAGE:
            return runs
        offset += _RUN_PAGE


def _portable_hash(recorded: str, path: Path) -> str:
    """The recorded hash, upgraded from the legacy 32-char width when the file
    on disk has exactly those bytes."""
    from .._hash import hashes_match

    if len(recorded) == 64 or not path.is_file():
        return recorded
    current = sha256_file(path)
    return current if hashes_match(recorded, current) else recorded


def _files(db, sid: str, root: Path) -> tuple[dict, dict, list]:
    inputs: dict[str, str] = {}
    outputs: dict[str, str] = {}
    external: list[dict] = []
    for rec in db.get_file_records(sid):
        rel = relative_or_none(rec["file_path"], root)
        payload = rec.get("external")
        if isinstance(payload, str):
            payload = json.loads(payload)
        if rec["role"] == "input" and (payload or rel is None):
            via = (payload or {}).get("via")
            name = external_name(rec["file_path"], via, root)
            external.append({"path": name, "sha256": rec["hash"] or None,
                             "size": rec.get("size_bytes")})  # fmt: skip
            continue
        if rel is None:
            continue  # an output outside the project cannot travel with it
        target = outputs if rec["role"] == "output" else inputs
        target[rel] = _portable_hash(rec["hash"], root / rel)
    return inputs, outputs, external


def _interpreter(meta: dict) -> dict:
    python = meta.get("python") or {}
    return {"name": "python", "version": python.get("version")}


def _run_entry(db, run: dict, root: Path) -> dict:
    sid = run["session_id"]
    meta = _metadata(run)
    entry = meta.get("entry") or {}
    cwd_abs = Path(meta["cwd"]) if meta.get("cwd") else root
    cwd_rel = relative_or_none(cwd_abs, root)
    if cwd_rel is None:  # recorded outside the project: replay from the root
        cwd_rel, cwd_abs = ".", root
    command = entry.get("command") if entry.get("kind") == "command" else None
    script = None if command else relative_or_none(run.get("script_path"), root)
    if command is not None:
        argv = ["-c", command, *[str(a) for a in (meta.get("argv") or [])[1:]]]
    elif isinstance(meta.get("argv"), list) and meta["argv"]:
        argv = relative_argv([str(a) for a in meta["argv"]], root, cwd_abs)
    elif script is not None:
        argv = relative_argv([str(root / script)], root, cwd_abs)
    else:
        argv = []
    inputs, outputs, external = _files(db, sid, root)
    run_dir = meta.get("sdir_run_final")
    return {
        "run_id": sid,
        "script": script,
        "script_sha256": run.get("script_hash"),
        "command": command,
        "argv": argv,
        "interpreter": _interpreter(meta),
        "cwd": cwd_rel,
        "inputs": inputs,
        "outputs": outputs,
        "external_inputs": external,
        "run_dir": relative_or_none(run_dir, root) if run_dir else None,
        "status": run.get("status") or "unknown",
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
    }


def _is_current(entry: dict, root: Path) -> bool:
    from .._hash import hashes_match

    if entry["status"] != "success" or not entry["outputs"]:
        return False
    for rel, recorded in entry["outputs"].items():
        path = root / rel
        if not path.is_file() or not hashes_match(recorded, sha256_file(path)):
            return False
    return True


def _select_current(entries: list[dict], root: Path) -> list[dict]:
    """The newest current producer of each output (see module doc)."""
    newest_first = sorted(entries, key=lambda e: e["started_at"] or "", reverse=True)
    claimed: set[str] = set()
    keep = []
    for entry in newest_first:
        if not _is_current(entry, root):
            continue
        fresh = set(entry["outputs"]) - claimed
        if fresh:
            keep.append(entry)
            claimed |= set(entry["outputs"])
    return keep


def _edges(db, entries: list[dict]) -> list[dict]:
    ids = {e["run_id"] for e in entries}
    producer = {}
    for e in sorted(entries, key=lambda e: e["started_at"] or ""):
        for rel, digest in e["outputs"].items():
            producer[(rel, digest)] = e["run_id"]
    pairs = set()
    for e in entries:
        for parent in db.get_parents(e["run_id"]):
            if parent in ids and parent != e["run_id"]:
                pairs.add((parent, e["run_id"]))
        for rel, digest in e["inputs"].items():
            parent = producer.get((rel, digest))
            if parent and parent != e["run_id"]:
                pairs.add((parent, e["run_id"]))
    return [{"parent": p, "child": c} for p, c in sorted(pairs)]


def _portable_graph(graph: dict | None, root: Path) -> dict | None:
    """The evidence graph with any host path label made portable."""
    if not graph:
        return graph
    nodes = []
    for node in graph.get("nodes", []):
        node = dict(node)
        label = node.get("label") or ""
        if node.get("kind") in ("input", "output") and Path(label).is_absolute():
            rel = relative_or_none(label, root)
            node["label"] = rel if rel is not None else external_name(label, None, root)
        nodes.append(node)
    return {**graph, "nodes": nodes}


def _claims(root: Path, entries: list[dict]) -> list[dict]:
    from .._claim import list_claims
    from .._evidence_provider import build_evidence_report

    report = build_evidence_report(root, None, {"with_graphs": True})
    records = {c.claim_id: c for c in list_claims(limit=10_000)}
    by_output: dict[str, list[str]] = {}
    for e in entries:
        for rel in e["outputs"]:
            by_output.setdefault(rel, []).append(e["run_id"])
    claims = []
    for c in report["claims"]:
        record = records.get(c["claim_id"])
        source = dict(c.get("source") or {})
        src_file = source.get("file")
        if src_file and Path(src_file).is_absolute():
            source["file"] = external_name(src_file, None, root)
        claims.append({
            "claim_id": c["claim_id"],
            "claim_type": c.get("claim_type"),
            "location": c["location"],
            "stated_text": c.get("stated_text"),
            "stated_value": c.get("stated_value"),
            "precision": precision_of(
                c.get("stated_value"),
                record.tolerance if record else None,
                source.get("locator"),
            ),
            "source": source,
            "state": c["state"],
            "reason": c["reason"],
            "producing_runs": sorted(by_output.get(src_file or "", [])),
            "graph": _portable_graph(c.get("graph"), root),
        })  # fmt: skip
    return claims


def _clew_version() -> str | None:
    from .. import __version__

    return __version__


def build_bundle(project_root: str | Path, *, all_runs: bool = False) -> dict:
    """The (unsigned) evidence bundle of the clew project at ``project_root``."""
    from .._db import get_db
    from .._db._paths import project_root as project_root_cm

    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"clew project root is not a directory: {root}")
    with project_root_cm(root):
        db = get_db()
        entries = [_run_entry(db, run, root) for run in _all_runs(db)]
        if not all_runs:
            entries = _select_current(entries, root)
        entries.sort(key=lambda e: (e["started_at"] or "", e["run_id"]))
        edges = _edges(db, entries)
        claims = _claims(root, entries)
        project_id = db._runs.project
    return {
        "schema": BUNDLE_SCHEMA,
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "exported_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        "clew_version": _clew_version(),
        "project": {"project_id": project_id, "root_name": root.name},
        "runs": entries,
        "edges": edges,
        "claims": claims,
    }


# EOF
