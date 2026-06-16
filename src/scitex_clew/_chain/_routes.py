#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""File-mediated route resolution for the provenance DAG.

Why this exists
---------------
The lineage a reader cares about is the **file-mediated data flow**: session A
*saves* a file ``P`` (output) and session B *loads* that same ``P`` (input).
That save->load handshake is the genuine provenance hop, and the file path is
the waypoint on the route: ``A -> P -> B``.

The legacy resolution walked the ``session_parents`` junction table, which had
accreted *every historical producer of every file a session ever read* —
including shared CONFIG/cache inputs that dozens of unrelated sessions also
produced. A composed figure ended up with ~83 "parents" and the meaningful
``3 panels -> composed`` route was lost; ``chain()`` also hung on the dense
fan-out (and ``get_chain`` followed ``runs.parent_session`` with no cycle
guard).

This module resolves the DAG *at graph-build time* from the file records
clew already stores losslessly (``file_hashes`` with ``role`` input/output).
Recording is untouched. The rules:

* For each session, its parents are the **producers of the files it loaded**.
* A loaded file contributes **its newest producer only** (``find_session_by_file
  (role="output")`` is ordered newest-first) — one parent per input file, not
  every historical producer. This is what collapses 83 -> ~3.
* A file with **no producing session** (a raw source / read-only CONFIG) yields
  **no parent edge** — it stays a plain source input on the session, never a
  cross-session link hub.
* Traversal is bounded (``visited`` dedup + ``max_depth``), so dense or cyclic
  graphs return quickly instead of hanging.

The return shape mirrors ``VerificationDB.get_dag`` so it is a drop-in swap for
the chain / DAG / mermaid resolution paths.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

# A generous default: real provenance chains are shallow, but we never want to
# walk forever on a pathological graph. Callers (chain/dag/mermaid) may lower it.
DEFAULT_MAX_DEPTH = 50


def resolve_file_dag(
    leaf_session_ids: List[str],
    *,
    db,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> Tuple[Dict[str, List[str]], Set[str]]:
    """Resolve the provenance DAG by walking file save->load handshakes.

    Backward BFS from each leaf session: a session's parents are the newest
    producers of the files it loaded. Bounded and deduped.

    Parameters
    ----------
    leaf_session_ids : list of str
        Sessions to start the backward walk from (e.g. the producer of a
        target file).
    db : VerificationDB
        Provides ``get_file_hashes(session_id, role="input")`` and
        ``find_session_by_file(file_path, role="output")``.
    max_depth : int, optional
        Maximum number of save->load hops to walk back. Defaults to
        ``DEFAULT_MAX_DEPTH``.

    Returns
    -------
    tuple of (dict, set)
        - adjacency: ``{child_session: [parent_sessions, ...]}`` (newest
          producer per loaded file; no edge for source/config files).
        - all_ids: every session id in the resolved DAG.
    """
    adjacency: Dict[str, List[str]] = {}
    all_ids: Set[str] = set()
    visited: Set[str] = set()
    # (session_id, depth) so depth is tracked per-node, not globally.
    queue: deque = deque((sid, 0) for sid in leaf_session_ids)

    while queue:
        sid, depth = queue.popleft()
        if sid in visited:
            continue
        visited.add(sid)
        all_ids.add(sid)

        parents = _parents_via_files(db, sid) if depth < max_depth else []
        adjacency[sid] = parents
        for parent in parents:
            all_ids.add(parent)
            if parent not in visited:
                queue.append((parent, depth + 1))

    # Root nodes (sources with no upstream) get an explicit empty parent list.
    for sid in all_ids:
        adjacency.setdefault(sid, [])

    return adjacency, all_ids


def _parents_via_files(db, session_id: str) -> List[str]:
    """Parents of ``session_id`` = newest producer of each file it loaded.

    A loaded file with no producing session (raw source / read-only config)
    contributes no parent. Self-edges (a session that re-reads its own output)
    are skipped. Order follows the session's input-file order, deduped.
    """
    input_files = db.get_file_hashes(session_id, role="input")  # {path: hash}

    parents: List[str] = []
    seen: Set[str] = set()
    for file_path in input_files:
        producers = db.find_session_by_file(file_path, role="output")
        # find_session_by_file is ordered newest-first; the newest producer
        # that is not this session itself is the genuine upstream hop.
        producer = next((p for p in producers if p != session_id), None)
        if producer is not None and producer not in seen:
            seen.add(producer)
            parents.append(producer)
    return parents


def order_roots_first(
    adjacency: Dict[str, List[str]],
    all_ids: Set[str],
) -> List[str]:
    """Order sessions roots-first (parents before children), cycle-tolerant.

    A Kahn topological sort over ``adjacency`` (``{child: [parents]}``). Unlike
    the strict DAG sort, any cyclic remnant is appended in stable id order
    rather than raising — ``chain()`` must never blow up on a pathological
    graph that the resolver already bounded.

    Parameters
    ----------
    adjacency : dict
        ``{child_session: [parent_sessions, ...]}`` from ``resolve_file_dag``.
    all_ids : set
        Every session id in the resolved DAG.

    Returns
    -------
    list of str
        Session ids, roots (sources) first, target(s) last.
    """
    in_degree = {node: len(adjacency.get(node, [])) for node in all_ids}
    children: Dict[str, List[str]] = defaultdict(list)
    for child, parents in adjacency.items():
        for parent in parents:
            children[parent].append(child)

    queue = deque(sorted(n for n in all_ids if in_degree.get(n, 0) == 0))
    order: List[str] = []
    seen: Set[str] = set()
    while queue:
        node = queue.popleft()
        if node in seen:
            continue
        seen.add(node)
        order.append(node)
        for child in children[node]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Cyclic remnants (if any): append deterministically so no session is lost.
    for node in sorted(all_ids):
        if node not in seen:
            order.append(node)
    return order


# EOF
