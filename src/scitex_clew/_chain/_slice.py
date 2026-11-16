#!/usr/bin/env python3
"""File-level minimal provenance slice: only what lies on a path to the target.

Clew records, per run, the files it LOADED (inputs) and SAVED (outputs), and
binds each input to the run that produced those exact bytes (see
:mod:`._routes`). The *run-level closure* of a target — every ancestor run
with all of its inputs and outputs — is what the back-trace views showed
until now. It over-approximates: a sibling output nobody downstream used, and
any input loaded by an off-path run, both appear.

A slice is a bipartite graph of **file nodes** and **run nodes** with
``file -> run`` (input) and ``run -> file`` (output) edges. Three levels,
each a subset of the previous one:

Level 0 — run-level closure (the historical view)
    Every run reachable backwards from the target's producer through
    hash-bound save->load handshakes, with ALL of each run's recorded inputs
    and outputs.

Level 1 — path-pruned (sound from recorded data alone; the default)
    Walk backwards from the target FILE, not from its run. A run is kept only
    because one of its outputs is demanded (the target, or an input of a kept
    run); only demanded outputs are kept, so sibling outputs and every run
    that merely consumed them are dropped. Inside a kept run Clew cannot see
    which input produced which output without instrumentation, so ALL inputs
    of a kept run are kept — an input that was loaded but unused still
    appears if it was loaded by a run on the path. Level 1 is therefore exact
    at file granularity *between* runs and conservative *within* a run.

Level 2 — declared per-output dependencies (opt-in, trusts the writer)
    A writing tool may declare, per output, the files it was derived from
    (``record_output(path, derived_from=[...])``, i.e. the ``derived_from``
    column of an output row). For a kept output with a declaration, only the
    declared inputs (and, transitively, declared intermediate outputs of the
    same run) are kept. An output WITHOUT a declaration falls back to level 1
    for its run (reported in :attr:`ProvenanceSlice.fallback_runs`); a
    declared path that the run never recorded as an input is reported in
    :attr:`ProvenanceSlice.unrecorded_declarations`, never silently added.
    Level 2 is only as correct as the declarations: verification defaults to
    level 1.

Verification over a slice checks only the slice's files (a changed sibling
output no longer marks the target's lineage stale).
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from ._routes import (
    DEFAULT_MAX_DEPTH,
    _session_bindings,
    current_hash_or_none,
    order_roots_first,
    resolve_lineage,
    resolve_producer,
)

LEVEL_RUN_CLOSURE = 0
LEVEL_PATH_PRUNED = 1
LEVEL_DECLARED = 2
LEVELS = (LEVEL_RUN_CLOSURE, LEVEL_PATH_PRUNED, LEVEL_DECLARED)

__all__ = [
    "LEVELS",
    "LEVEL_DECLARED",
    "LEVEL_PATH_PRUNED",
    "LEVEL_RUN_CLOSURE",
    "ProvenanceSlice",
    "SliceEdge",
    "build_slice",
    "compare_levels",
    "resolve_slice_target",
]


def run_node(session_id: str) -> str:
    return f"run:{session_id}"


def file_node(path: str) -> str:
    return f"file:{path}"


@dataclass(frozen=True)
class SliceEdge:
    """``file:<p> -> run:<sid>`` (``kind="input"``) or ``run -> file`` (output)."""

    source: str
    target: str
    kind: str


@dataclass
class ProvenanceSlice:
    """The provenance sub-graph that a set of target files rests on."""

    targets: list[str]
    level: int
    runs: list[str]
    run_inputs: dict[str, list[str]]
    run_outputs: dict[str, list[str]]
    file_hashes: dict[str, str | None]
    parents: dict[str, list[str]]
    unproduced_targets: list[str] = field(default_factory=list)
    dropped_inputs: dict[str, list[str]] = field(default_factory=dict)
    dropped_outputs: dict[str, list[str]] = field(default_factory=dict)
    fallback_runs: dict[str, str] = field(default_factory=dict)
    unrecorded_declarations: dict[str, list[str]] = field(default_factory=dict)

    @property
    def files(self) -> list[str]:
        return sorted(self.file_hashes)

    @property
    def edges(self) -> list[SliceEdge]:
        out: list[SliceEdge] = []
        for sid in self.runs:
            for path in self.run_inputs.get(sid, []):
                out.append(SliceEdge(file_node(path), run_node(sid), "input"))
            for path in self.run_outputs.get(sid, []):
                out.append(SliceEdge(run_node(sid), file_node(path), "output"))
        return out

    @property
    def run_edges(self) -> list[tuple[str, str]]:
        """``(parent_sid, child_sid)`` pairs, the shape DAGVerification uses."""
        return [(p, c) for c in self.runs for p in self.parents.get(c, [])]

    def run_files(self, session_id: str) -> dict[str, set[str]]:
        """``{"input": {...}, "output": {...}}`` kept for one run."""
        return {
            "input": set(self.run_inputs.get(session_id, [])),
            "output": set(self.run_outputs.get(session_id, [])),
        }

    def counts(self) -> dict[str, int]:
        runs, files, edges = len(self.runs), len(self.file_hashes), len(self.edges)
        return {"runs": runs, "files": files, "nodes": runs + files, "edges": edges}

    def to_dict(self) -> dict:
        return {
            "targets": list(self.targets),
            "level": self.level,
            "counts": self.counts(),
            "runs": list(self.runs),
            "files": [{"path": p, "hash": self.file_hashes[p]} for p in self.files],
            "edges": [
                {"source": e.source, "target": e.target, "kind": e.kind}
                for e in self.edges
            ],
            "unproduced_targets": list(self.unproduced_targets),
            "dropped_inputs": self.dropped_inputs,
            "dropped_outputs": self.dropped_outputs,
            "fallback_runs": self.fallback_runs,
            "unrecorded_declarations": self.unrecorded_declarations,
        }


# ---------------------------------------------------------------------------
# Target resolution (file path or claim)
# ---------------------------------------------------------------------------

_LOCATION = re.compile(r"^(.+):L(\d+)$")


def resolve_slice_target(target: str | Path) -> tuple[str, str | None]:
    """``(resolved_path, content_hash)`` for a target file or claim.

    A claim id (or ``paper.tex:L42`` location) resolves to its source file and
    the hash the claim was registered against; anything else is a file path,
    hashed as it is on disk now.
    """
    text = str(target)
    if not Path(text).exists() or _LOCATION.match(text):
        claim = _lookup_claim(text)
        if claim is not None:
            if not claim.source_file:
                raise ValueError(f"claim {claim.claim_id} has no source_file to slice")
            return str(Path(claim.source_file).resolve()), claim.source_hash
    resolved = str(Path(text).resolve())
    return resolved, current_hash_or_none(resolved)


def _lookup_claim(text: str):
    from .._claim._model import _resolve_claim

    try:
        return _resolve_claim(text, None)
    except Exception:  # noqa: BLE001 - not a claim; treated as a file path
        return None


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class _RunIndex:
    """Lazily loaded file records + input bindings per run."""

    def __init__(self, db):
        self.db = db
        self._records: dict[str, list[dict]] = {}
        self._bindings: dict[str, dict[str, str]] = {}

    def records(self, sid: str, role: str) -> list[dict]:
        if sid not in self._records:
            self._records[sid] = self.db.get_file_records(sid)
        return [r for r in self._records[sid] if r.get("role") == role]

    def inputs(self, sid: str) -> dict[str, str | None]:
        return {r["file_path"]: r.get("hash") for r in self.records(sid, "input")}

    def outputs(self, sid: str) -> dict[str, dict]:
        return {r["file_path"]: r for r in self.records(sid, "output")}

    def parent_of(self, sid: str, input_path: str) -> str | None:
        if sid not in self._bindings:
            bindings, _unbound = _session_bindings(self.db, sid)
            self._bindings[sid] = {b.file_path: b.parent for b in bindings}
        return self._bindings[sid].get(input_path)


def build_slice(
    targets: Iterable[str | Path],
    *,
    level: int = LEVEL_PATH_PRUNED,
    db=None,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> ProvenanceSlice:
    """Build the provenance slice of ``targets`` at ``level`` (see module doc).

    Parameters
    ----------
    targets : iterable of str or Path
        Target files, or claim ids / ``file.tex:L42`` locations (resolved to
        the claim's source file and registered hash).
    level : int
        0 (run-level closure), 1 (path-pruned, default) or 2 (declared
        per-output dependencies, falling back to 1 per run).
    db : VerificationDB, optional
        Defaults to the global DB.
    max_depth : int
        Maximum save->load hops walked back.
    """
    if level not in LEVELS:
        raise ValueError(f"slice level must be one of {LEVELS}, got {level!r}")
    if db is None:
        from .._db import get_db

        db = get_db()

    index = _RunIndex(db)
    resolved_targets: list[str] = []
    seeds: list[tuple[str, str]] = []
    unproduced: list[str] = []
    for target in targets:
        path, content_hash = resolve_slice_target(target)
        resolved_targets.append(path)
        producer = resolve_producer(db, path, content_hash)
        if producer is None:
            unproduced.append(path)
        else:
            seeds.append((producer, path))

    kept_in: dict[str, set[str]] = defaultdict(set)
    kept_out: dict[str, set[str]] = defaultdict(set)
    parents: dict[str, list[str]] = defaultdict(list)
    fallback: dict[str, str] = {}
    unrecorded: dict[str, set[str]] = defaultdict(set)

    if level == LEVEL_RUN_CLOSURE:
        lineage = resolve_lineage([sid for sid, _ in seeds], db=db, max_depth=max_depth)
        for sid in lineage.all_ids:
            kept_in[sid] = set(index.inputs(sid))
            kept_out[sid] = set(index.outputs(sid))
            parents[sid] = list(lineage.adjacency.get(sid, []))
    else:
        queue: deque = deque((sid, path, 0) for sid, path in seeds)
        seen: set[tuple[str, str]] = set()
        while queue:
            sid, out_path, depth = queue.popleft()
            if (sid, out_path) in seen:
                continue
            seen.add((sid, out_path))
            kept_out[sid].add(out_path)
            needed = _inputs_needed(
                index, sid, out_path, level, kept_out, fallback, unrecorded
            )
            for inp in needed:
                if inp in kept_in[sid]:
                    continue
                kept_in[sid].add(inp)
                parent = index.parent_of(sid, inp)
                if parent is None:
                    continue
                if parent not in parents[sid]:
                    parents[sid].append(parent)
                if depth < max_depth:
                    queue.append((parent, inp, depth + 1))

    run_ids = set(kept_out) | set(kept_in)
    order = order_roots_first({s: parents.get(s, []) for s in run_ids}, run_ids)

    file_hashes: dict[str, str | None] = {
        p: current_hash_or_none(p) for p in unproduced
    }
    dropped_in: dict[str, list[str]] = {}
    dropped_out: dict[str, list[str]] = {}
    for sid in order:
        ins, outs = index.inputs(sid), index.outputs(sid)
        for p in kept_in[sid]:
            file_hashes.setdefault(p, ins.get(p))
        for p in kept_out[sid]:
            file_hashes[p] = outs[p].get("hash") if p in outs else file_hashes.get(p)
        if level != LEVEL_RUN_CLOSURE:
            d_in = sorted(set(ins) - kept_in[sid])
            d_out = sorted(set(outs) - kept_out[sid])
            if d_in:
                dropped_in[sid] = d_in
            if d_out:
                dropped_out[sid] = d_out

    return ProvenanceSlice(
        targets=resolved_targets,
        level=level,
        runs=order,
        run_inputs={s: sorted(kept_in[s]) for s in order},
        run_outputs={s: sorted(kept_out[s]) for s in order},
        file_hashes=file_hashes,
        parents={s: list(parents.get(s, [])) for s in order},
        unproduced_targets=unproduced,
        dropped_inputs=dropped_in,
        dropped_outputs=dropped_out,
        fallback_runs=fallback,
        unrecorded_declarations={s: sorted(v) for s, v in unrecorded.items() if v},
    )


def _inputs_needed(index, sid, out_path, level, kept_out, fallback, unrecorded):
    """Inputs of ``sid`` that the demanded output ``out_path`` rests on."""
    inputs = index.inputs(sid)
    if level == LEVEL_PATH_PRUNED:
        return list(inputs)
    outputs = index.outputs(sid)
    needed: list[str] = []
    stack, visited = [out_path], set()
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        declared = (outputs.get(current) or {}).get("derived_from")
        if declared is None:
            fallback.setdefault(
                sid, f"output {current} has no derived_from declaration"
            )
            return list(inputs)
        for dep in declared:
            if dep in inputs:
                needed.append(dep)
            elif dep in outputs:
                kept_out[sid].add(dep)  # declared intermediate of the same run
                stack.append(dep)
            else:
                unrecorded[sid].add(dep)
    return needed


def compare_levels(
    targets: Iterable[str | Path], *, db=None
) -> dict[int, dict[str, int]]:
    """Node/edge counts of the slice at every level (for E2-style reporting)."""
    targets = list(targets)
    return {lvl: build_slice(targets, level=lvl, db=db).counts() for lvl in LEVELS}


# EOF
