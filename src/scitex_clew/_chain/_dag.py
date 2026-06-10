#!/usr/bin/env python3
# Timestamp: "2026-05-05 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_chain/_dag.py
"""DAG topological sort, multi-target DAG verification, and strict-mode
failure attribution (F2).
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .._db import get_db
from ._types import (
    DAGVerification,
    FileVerification,
    RunVerification,
    VerificationStatus,
)
from ._verify_ops import verify_run


def _topological_sort(adjacency: Dict[str, List[str]]) -> List[str]:
    """Topological sort of DAG using Kahn's algorithm.

    Parameters
    ----------
    adjacency : dict
        {child_session: [parent_sessions, ...]}

    Returns
    -------
    list of str
        Session IDs in topological order (roots first)

    Raises
    ------
    ValueError
        If a cycle is detected in the DAG
    """
    # Build in-degree and forward adjacency (parent -> children)
    all_nodes = set()
    forward: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = {}

    for child, parents in adjacency.items():
        all_nodes.add(child)
        for p in parents:
            all_nodes.add(p)
            forward[p].append(child)

    for node in all_nodes:
        in_degree[node] = len(adjacency.get(node, []))

    queue = deque(n for n in all_nodes if in_degree[n] == 0)
    result = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for child in forward[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(result) != len(all_nodes):
        raise ValueError("Cycle detected in DAG")

    return result


def verify_dag(
    targets: List[Union[str, Path]],
) -> DAGVerification:
    """Verify the full DAG for one or more target files.

    Traces back through all sessions that produced the target files,
    collecting the full multi-parent DAG and verifying each session.

    Parameters
    ----------
    targets : list of str or Path
        Target files to trace back to sources

    Returns
    -------
    DAGVerification
        Unified verification result for the entire DAG
    """
    db = get_db()

    # Resolve targets to leaf session IDs
    leaf_sessions = []
    resolved_targets = []
    for target in targets:
        target_str = str(Path(target).resolve())
        resolved_targets.append(target_str)
        sessions = db.find_session_by_file(target_str, role="output")
        if sessions:
            leaf_sessions.append(sessions[0])

    if not leaf_sessions:
        return DAGVerification(
            target_files=resolved_targets,
            runs=[],
            edges=[],
            status=VerificationStatus.UNKNOWN,
            topological_order=[],
        )

    # BFS backward to collect full DAG
    adjacency, all_ids = db.get_dag(leaf_sessions)

    # Topological sort (roots first)
    topo_order = _topological_sort(adjacency)

    # Verify each session exactly once
    verifications: Dict[str, RunVerification] = {}
    for sid in topo_order:
        verifications[sid] = verify_run(sid, propagate=False)

    # Propagate failures forward through the DAG
    failed_sessions: set = set()
    for sid in topo_order:
        parents = adjacency.get(sid, [])
        has_failed_parent = any(p in failed_sessions for p in parents)
        if has_failed_parent or not verifications[sid].is_verified:
            failed_sessions.add(sid)

    # Build edges list
    edges = []
    for child, parents in adjacency.items():
        for p in parents:
            edges.append((p, child))

    # Determine overall status. SUSPECT slots in below MISMATCH / MISSING
    # so a DAG that has any locally-broken run still reports MISMATCH /
    # MISSING (the user has to fix that first), but a DAG whose runs are
    # all locally valid except for an upstream-only failure reports
    # SUSPECT — matching the orange band in ``_viz/_mermaid_nodes.py``.
    run_list = [verifications[sid] for sid in topo_order]
    if all(sid not in failed_sessions for sid in topo_order):
        status = VerificationStatus.VERIFIED
    elif any(
        verifications[sid].status == VerificationStatus.MISMATCH for sid in topo_order
    ):
        status = VerificationStatus.MISMATCH
    elif any(
        verifications[sid].status == VerificationStatus.MISSING for sid in topo_order
    ):
        status = VerificationStatus.MISSING
    elif any(
        verifications[sid].status == VerificationStatus.SUSPECT for sid in topo_order
    ):
        status = VerificationStatus.SUSPECT
    else:
        status = VerificationStatus.UNKNOWN

    return DAGVerification(
        target_files=resolved_targets,
        runs=run_list,
        edges=edges,
        status=status,
        topological_order=topo_order,
    )


# ---------------------------------------------------------------------------
# F2 — Strict-mode DAG verification with failure attribution
# ---------------------------------------------------------------------------


def _file_to_node(fv: FileVerification, sid: str) -> Dict[str, Any]:
    """Convert a FileVerification + owning session to the F2 'node' dict."""
    return {
        "session_id": sid,
        "path": fv.path,
        "role": fv.role,
        "expected_hash": fv.expected_hash,
        "got_hash": fv.current_hash,
        "status": fv.status.value,
    }


def _root_cause_file(failed_files: List[FileVerification]) -> FileVerification:
    """For the upstream-most failed session, prefer the input file that diverged."""
    inputs = [f for f in failed_files if f.role == "input"]
    if inputs:
        return inputs[0]
    return failed_files[0]


def _failed_node_file(failed_files: List[FileVerification]) -> FileVerification:
    """For the downstream-most failed session, prefer the output (the artifact)."""
    outputs = [f for f in failed_files if f.role == "output"]
    if outputs:
        return outputs[0]
    return failed_files[0]


def _resolve_claim_session(claim, db) -> Optional[str]:
    """Best-effort resolve a claim to its source session id."""
    if claim.source_session:
        return claim.source_session
    if claim.source_file:
        sids = db.find_session_by_file(claim.source_file, role="output")
        if sids:
            return sids[0]
    return None


def verify_dag_strict(
    targets: Optional[List[Union[str, Path]]] = None,
    claims: bool = False,
) -> Dict[str, Any]:
    """Verify a DAG and attribute the failure (F2).

    Parameters
    ----------
    targets : list of str or Path, optional
        Target files (mutually exclusive with claims).
    claims : bool, optional
        If True, build the DAG from every registered claim.

    Returns
    -------
    dict
        ::

            {
              "status": "OK" | "FAIL",
              "is_verified": bool,
              "target_files": [...],
              "topological_order": [...],
              "failed_node": {path, role, expected_hash, got_hash, ...} | None,
              "root_cause":  {path, role, expected_hash, got_hash, ...} | None,
              "invalidated_claims": [claim_id, ...],
              "still_valid_claims": [claim_id, ...],
            }
    """
    # Late imports to avoid circulars and to keep zero-cost when unused.
    from .._claim import list_claims, verify_claims_dag

    if claims:
        result = verify_claims_dag()
    else:
        result = verify_dag([str(t) for t in (targets or [])])

    # Map session_id → RunVerification.
    by_sid: Dict[str, RunVerification] = {r.session_id: r for r in result.runs}

    # Sessions whose own file hashes failed (not just propagated upstream failure).
    own_failures: "dict[str, list[FileVerification]]" = {}
    for sid in result.topological_order:
        run = by_sid.get(sid)
        if run is None:
            continue
        files_failed = [
            f
            for f in run.files
            if f.status in (VerificationStatus.MISMATCH, VerificationStatus.MISSING)
        ]
        if files_failed:
            own_failures[sid] = files_failed

    db = get_db()
    all_claims = list_claims(limit=10000)

    if result.is_verified:
        return {
            "status": "OK",
            "is_verified": True,
            "target_files": list(result.target_files),
            "topological_order": list(result.topological_order),
            "failed_node": None,
            "root_cause": None,
            "invalidated_claims": [],
            "still_valid_claims": [c.claim_id for c in all_claims],
        }

    # FAIL path -----------------------------------------------------------
    # Compute blast radius: failed sessions ∪ everything downstream.
    forward: Dict[str, List[str]] = defaultdict(list)
    for parent, child in result.edges:
        forward[parent].append(child)

    invalidated_sessions: set = set(own_failures.keys())
    queue: deque = deque(invalidated_sessions)
    while queue:
        sid = queue.popleft()
        for child in forward.get(sid, []):
            if child not in invalidated_sessions:
                invalidated_sessions.add(child)
                queue.append(child)

    # If the DAG reports failure but we have no own_failures (e.g. UNKNOWN
    # because target's session is missing entirely), fall back to using the
    # mismatched/missing files reported by any failed run.
    if not own_failures:
        for sid in result.topological_order:
            run = by_sid.get(sid)
            if run is None:
                continue
            ff = list(run.mismatched_files) + list(run.missing_files)
            if ff:
                own_failures[sid] = ff
                invalidated_sessions.add(sid)
                break

    root_sid = next(iter(own_failures), None)
    failed_sid = list(own_failures.keys())[-1] if own_failures else None

    failed_node = (
        _file_to_node(_failed_node_file(own_failures[failed_sid]), failed_sid)
        if failed_sid
        else None
    )
    root_cause = (
        _file_to_node(_root_cause_file(own_failures[root_sid]), root_sid)
        if root_sid
        else None
    )

    # Resolve claims against the invalidated session set.
    invalidated_claim_ids: List[str] = []
    still_valid_claim_ids: List[str] = []
    for c in all_claims:
        cs = _resolve_claim_session(c, db)
        if cs is None:
            still_valid_claim_ids.append(c.claim_id)
            continue
        chain = db.get_chain(cs)
        if any(s in invalidated_sessions for s in chain):
            invalidated_claim_ids.append(c.claim_id)
        else:
            still_valid_claim_ids.append(c.claim_id)

    return {
        "status": "FAIL",
        "is_verified": False,
        "target_files": list(result.target_files),
        "topological_order": list(result.topological_order),
        "failed_node": failed_node,
        "root_cause": root_cause,
        "invalidated_claims": invalidated_claim_ids,
        "still_valid_claims": still_valid_claim_ids,
    }


# EOF
