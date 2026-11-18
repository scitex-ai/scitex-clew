#!/usr/bin/env python3
"""Where a claim's evidence broke: contract 1.1.0 ``node.failure`` marks.

Read from clew's own verification of the claim, never inferred from the
graph's shape:

* ``SOURCE_MISSING`` -> the source file node is ``missing``;
* ``HASH_MISMATCH`` -> the source file node is ``changed`` (its bytes differ
  from the hash recorded when the claim was registered);
* ``VALUE_MISMATCH`` -> the source file node is ``mismatched`` when a located
  value disagrees, else the claim node (its text does not state its
  registered value);
* ``STALE_LINEAGE`` / ``EXTERNAL_MISSING`` -> the claim's minimal chain is
  re-verified (:func:`~scitex_clew._chain.verify_chain`, ``minimal=True``,
  the same slice the graph shows) and every file whose status is
  ``MISMATCH`` is ``changed``, every ``MISSING`` one ``missing``; a run whose
  recorded execution failed is a ``failed`` process node. A recorded file
  the graph does not draw (pruned from the slice) is reported on its run's
  process node, naming the file.

Every other outcome marks nothing: either nothing broke (``OK``), or what
failed is not a node (no locator, no lineage, the environment).
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from pathlib import Path

from ._graph import relative_to_root
from ._states import value_difference

__all__ = ["CHAIN_OUTCOMES", "mark_failures"]

#: Outcomes whose failure lives in the recorded chain, not the source alone.
CHAIN_OUTCOMES = frozenset({"STALE_LINEAGE", "EXTERNAL_MISSING"})


def _chain_failures(source_file: str, root: Path) -> list[tuple[str, str, dict]]:
    """``[(where, key, failure)]`` from clew's verify of the minimal chain.

    ``where`` is ``"file"`` (key: the path relative to ``root``) or ``"run"``
    (key: the session id).
    """
    from .._chain import verify_chain
    from .._chain._types import VerificationStatus as VS

    chain = verify_chain(source_file, minimal=True)
    out: list[tuple[str, str, dict]] = []
    for run in chain.runs:
        sid = str(run.session_id)
        if run.status == VS.FAILED:
            reason = run.exception_reason or "its recorded execution failed"
            out.append(
                ("run", sid, {"kind": "failed", "detail": f"run {sid}: {reason}"})
            )
        for f in run.files:
            if f.status == VS.MISMATCH:
                kind = "changed"
                detail = f"{f.role} differs from what run {sid} recorded"
            elif f.status == VS.MISSING:
                kind = "missing"
                where = "outside the project, " if f.external else ""
                detail = f"{f.role} recorded by run {sid} is absent ({where}here)"
            else:
                continue
            rel = relative_to_root(f.path, root)
            out.append(("file", rel, {"kind": kind, "detail": detail, "_run": sid}))
    return out


def _source_failure(outcome: str, reason: str, details: Iterable[str]):
    """``(on, failure)`` for an outcome that breaks at the source or claim."""
    if outcome == "SOURCE_MISSING":
        return "source", {"kind": "missing", "detail": "the source file is missing"}
    if outcome == "HASH_MISMATCH":
        return "source", {
            "kind": "changed",
            "detail": "differs from the hash recorded when the claim was registered",
        }
    if outcome == "VALUE_MISMATCH":
        diff = value_difference(details)
        if diff is not None:
            source, claimed = diff
            return "source", {
                "kind": "mismatched",
                "detail": f"{source} in source vs {claimed} stated",
            }
        return "claim", {"kind": "mismatched", "detail": reason}
    return None, None


def mark_failures(
    graph: dict,
    *,
    outcome: str,
    reason: str,
    details: Iterable[str],
    source_file: str | None,
    root: Path,
) -> dict:
    """A copy of ``graph`` whose broken nodes carry ``failure``.

    Must run inside the claim's :func:`project_root` block when ``outcome``
    is a chain outcome (it re-verifies the chain from the store).
    """
    graph = copy.deepcopy(graph)
    by_label = {n["label"]: n for n in graph["nodes"] if n["kind"] != "process"}
    runs = {n["label"]: n for n in graph["nodes"] if n["kind"] == "process"}
    claim = next((n for n in graph["nodes"] if n["kind"] == "claim"), None)
    source_label = relative_to_root(source_file, root) if source_file else None

    on, failure = _source_failure(outcome, reason, list(details))
    if on == "source" and source_label in by_label:
        by_label[source_label]["failure"] = failure
    elif on == "claim" and claim is not None:
        claim["failure"] = failure

    if outcome in CHAIN_OUTCOMES and source_file:
        for where, key, fail in _chain_failures(source_file, root):
            run_sid = fail.pop("_run", None)
            node = by_label.get(key) if where == "file" else runs.get(key)
            if node is None and where == "file" and run_sid in runs:
                # Recorded by the run but pruned from the drawn slice: say so
                # on the run, naming the file.
                node = runs[run_sid]
                fail = {**fail, "detail": f"{key}: {fail['detail']}"}
            if node is not None and "failure" not in node:
                node["failure"] = fail
    return graph


# EOF
