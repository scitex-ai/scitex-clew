#!/usr/bin/env python3
"""The level-1/2 backward walk of a provenance slice (see :mod:`._slice`).

Split out of :mod:`._slice` (512-line limit). :func:`walk_demanded` walks back
from the target FILES: a run is kept only because one of its outputs is
demanded, and each demanded output is credited to its originating producer
(:mod:`._readback`), so a run that merely read a file back and rewrote it with
the same bytes never pulls in a second producer of those bytes.
"""

from __future__ import annotations

from collections import defaultdict, deque

from ._readback import originating_producer
from ._routes import _session_bindings

LEVEL_PATH_PRUNED = 1  # re-exported by ._slice (single definition)

__all__ = ["RunIndex", "walk_demanded"]


class RunIndex:
    """Lazily loaded file records + input bindings per run."""

    def __init__(self, db):
        self.db = db
        self._records: dict[str, list[dict]] = {}
        self._bindings: dict[str, dict[str, str]] = {}
        # Built once per run: the walk asks for a run's inputs once per
        # DEMANDED output, so rebuilding them made a run with many demanded
        # outputs cost outputs x inputs.
        self._inputs: dict[str, dict[str, str | None]] = {}
        self._outputs: dict[str, dict[str, dict]] = {}

    def records(self, sid: str, role: str) -> list[dict]:
        if sid not in self._records:
            self._records[sid] = self.db.get_file_records(sid)
        return [r for r in self._records[sid] if r.get("role") == role]

    def inputs(self, sid: str) -> dict[str, str | None]:
        """``{path: hash}`` of the run's inputs (shared; do not mutate)."""
        if sid not in self._inputs:
            self._inputs[sid] = {
                r["file_path"]: r.get("hash") for r in self.records(sid, "input")
            }
        return self._inputs[sid]

    def outputs(self, sid: str) -> dict[str, dict]:
        """``{path: record}`` of the run's outputs (shared; do not mutate)."""
        if sid not in self._outputs:
            self._outputs[sid] = {
                r["file_path"]: r for r in self.records(sid, "output")
            }
        return self._outputs[sid]

    def external(self, sid: str) -> dict[str, dict]:
        """``{path: external payload}`` of the run's outside-the-project inputs."""
        return {
            r["file_path"]: r["external"]
            for r in self.records(sid, "input")
            if r.get("external")
        }

    def parent_of(self, sid: str, input_path: str) -> str | None:
        if sid not in self._bindings:
            bindings, _unbound = _session_bindings(self.db, sid)
            self._bindings[sid] = {b.file_path: b.parent for b in bindings}
        return self._bindings[sid].get(input_path)


def walk_demanded(index, seeds, level, max_depth):
    """Walk back from ``seeds`` (``(producer, path)``) keeping demanded files.

    Returns ``(kept_in, kept_out, parents, fallback, unrecorded)``: per run,
    the kept inputs / outputs, the kept parent runs, the level-2 fallback
    reasons and the declared-but-unrecorded inputs.
    """
    kept_in: dict[str, set[str]] = defaultdict(set)
    kept_out: dict[str, set[str]] = defaultdict(set)
    parents: dict[str, list[str]] = defaultdict(list)
    fallback: dict[str, str] = {}
    unrecorded: dict[str, set[str]] = defaultdict(set)

    queue: deque = deque(
        (originating_producer(index, sid, path), path, 0) for sid, path in seeds
    )
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
            parent = originating_producer(index, parent, inp)
            if parent == sid:
                continue
            if parent not in parents[sid]:
                parents[sid].append(parent)
            if depth < max_depth:
                queue.append((parent, inp, depth + 1))
    return kept_in, kept_out, parents, fallback, unrecorded


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


# EOF
