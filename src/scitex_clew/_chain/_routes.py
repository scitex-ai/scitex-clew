#!/usr/bin/env python3
"""The ONE lineage resolver behind every provenance-DAG view.

Model
-----
The lineage a reader cares about is the **file-mediated data flow**: session A
*saves* bytes to ``P`` (output) and session B *loads* those same bytes from
``P`` (input). That save->load handshake is the provenance hop ``A -> P -> B``.

Every view — ``verify_chain``, ``verify_dag``, ``verify_dag_strict``,
``rerun_dag``, the JSON/Mermaid DAG renderers, claim export and the source
gate — resolves parents here, from the file records clew already stores
(``file_hashes`` with ``role`` input/output). The legacy ``session_parents``
junction and ``runs.parent_session`` are NOT consulted for lineage.

Binding rule (content hash + record time, never path alone)
-----------------------------------------------------------
An input row ``(B, P, h_in, t_in)`` is bound to the producer whose OUTPUT row
for the same path has hash ``h_in`` (:func:`scitex_clew._hash.hashes_match`)
and was recorded no later than ``t_in``; among those, the newest wins. So:

* a run that overwrites ``P`` with different bytes AFTER B loaded it is never
  B's parent (its hash differs) — B is not silently re-parented;
* a deterministic re-run that writes byte-identical ``P`` AFTER B loaded it is
  not B's parent either (it was recorded later);
* an input whose bytes match no recorded producer output is left UNBOUND and
  reported in :attr:`LineageResolution.unbound_inputs` with a reason:

  - ``"external"`` — nobody ever recorded ``P`` as an output (a raw source /
    read-only config): a plain source input, never a cross-session link;
  - ``"unmatched"`` — ``P`` has producers, but none recorded these bytes
    before B loaded them (edited out of band, or the producer never ran
    through clew). Flagged, never guessed.

Traversal is bounded (``visited`` dedup + ``max_depth``), so dense or cyclic
graphs return quickly instead of hanging.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .._hash import hashes_match

# A generous default: real provenance chains are shallow, but we never want to
# walk forever on a pathological graph. Callers (chain/dag/mermaid) may lower it.
DEFAULT_MAX_DEPTH = 50

#: Reasons an input is left unbound (see module docstring).
UNBOUND_EXTERNAL = "external"
UNBOUND_UNMATCHED = "unmatched"


@dataclass(frozen=True)
class InputBinding:
    """One resolved save->load edge: ``parent`` produced the bytes ``child`` loaded."""

    child: str
    parent: str
    file_path: str
    hash: str | None


@dataclass(frozen=True)
class UnboundInput:
    """An input with no producer of its exact bytes (see ``reason``)."""

    file_path: str
    hash: str | None
    reason: str


@dataclass
class LineageResolution:
    """Result of :func:`resolve_lineage`.

    ``adjacency`` maps ``{child_session: [parent_sessions, ...]}`` (every
    session in ``all_ids`` has an entry; roots map to ``[]``).
    """

    adjacency: dict[str, list[str]]
    all_ids: set[str]
    bindings: list[InputBinding] = field(default_factory=list)
    unbound_inputs: dict[str, list[UnboundInput]] = field(default_factory=dict)

    def roots_first(self) -> list[str]:
        """Session ids ordered sources-first (see :func:`order_roots_first`)."""
        return order_roots_first(self.adjacency, self.all_ids)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def bind_input(
    producers: Iterable[dict[str, str | None]],
    *,
    consumer_session: str,
    input_hash: str | None,
    input_recorded_at: str | None = None,
) -> str | None:
    """Return the producer session of the exact bytes a consumer loaded.

    Parameters
    ----------
    producers : iterable of dict
        Output records for the input's path, NEWEST-FIRST, each with
        ``session_id`` / ``hash`` / ``recorded_at`` (as returned by
        ``VerificationDB.find_producer_records``).
    consumer_session : str
        The loading session (never its own parent).
    input_hash : str
        Hash the consumer recorded for the input.
    input_recorded_at : str, optional
        When the consumer recorded the input. A producer recorded strictly
        later cannot be the source of these bytes. ``None`` (record time
        unknown, or binding at load time) skips the time gate.

    Returns
    -------
    str or None
        The newest qualifying producer, or ``None`` when no producer recorded
        these bytes before the load.
    """
    t_in = _parse_time(input_recorded_at)
    for rec in producers:
        sid = rec.get("session_id")
        if not sid or sid == consumer_session:
            continue
        if not hashes_match(rec.get("hash"), input_hash):
            continue
        t_out = _parse_time(rec.get("recorded_at"))
        if t_in is not None and t_out is not None and t_out > t_in:
            continue
        return sid
    return None


def _session_bindings(
    db, session_id: str
) -> tuple[list[InputBinding], list[UnboundInput]]:
    """Bind each input of ``session_id`` to the producer of its bytes."""
    inputs = db.get_file_records(session_id, role="input")
    if not inputs:
        return [], []
    producers_by_path = db.find_producer_records([r["file_path"] for r in inputs])

    bindings: list[InputBinding] = []
    unbound: list[UnboundInput] = []
    for rec in inputs:
        path = rec["file_path"]
        producers = [
            p
            for p in producers_by_path.get(path, [])
            if p.get("session_id") != session_id
        ]
        parent = bind_input(
            producers,
            consumer_session=session_id,
            input_hash=rec.get("hash"),
            input_recorded_at=rec.get("recorded_at"),
        )
        if parent is not None:
            bindings.append(InputBinding(session_id, parent, path, rec.get("hash")))
        else:
            reason = UNBOUND_UNMATCHED if producers else UNBOUND_EXTERNAL
            unbound.append(UnboundInput(path, rec.get("hash"), reason))
    return bindings, unbound


def parents_of(db, session_id: str) -> list[str]:
    """Direct, hash-bound parents of one session (input order, deduped)."""
    bindings, _ = _session_bindings(db, session_id)
    return _dedup(b.parent for b in bindings)


def resolve_lineage(
    leaf_session_ids: Iterable[str],
    *,
    db,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> LineageResolution:
    """Resolve the provenance DAG upstream of ``leaf_session_ids``.

    Backward BFS from each leaf; a session's parents are the hash-bound
    producers of the bytes it loaded (see module docstring). Bounded and
    deduped.

    Parameters
    ----------
    leaf_session_ids : iterable of str
        Sessions to start the backward walk from.
    db : VerificationDB
        Provides ``get_file_records`` and ``find_producer_records``.
    max_depth : int, optional
        Maximum number of save->load hops to walk back.
    """
    adjacency: dict[str, list[str]] = {}
    all_ids: set[str] = set()
    visited: set[str] = set()
    all_bindings: list[InputBinding] = []
    unbound_inputs: dict[str, list[UnboundInput]] = {}
    queue: deque = deque((sid, 0) for sid in leaf_session_ids)

    while queue:
        sid, depth = queue.popleft()
        if sid in visited:
            continue
        visited.add(sid)
        all_ids.add(sid)

        if depth < max_depth:
            bindings, unbound = _session_bindings(db, sid)
        else:
            bindings, unbound = [], []
        all_bindings.extend(bindings)
        if unbound:
            unbound_inputs[sid] = unbound
        parents = _dedup(b.parent for b in bindings)
        adjacency[sid] = parents
        for parent in parents:
            all_ids.add(parent)
            if parent not in visited:
                queue.append((parent, depth + 1))

    for sid in all_ids:
        adjacency.setdefault(sid, [])

    return LineageResolution(
        adjacency=adjacency,
        all_ids=all_ids,
        bindings=all_bindings,
        unbound_inputs=unbound_inputs,
    )


def resolve_file_dag(
    leaf_session_ids: list[str],
    *,
    db,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> tuple[dict[str, list[str]], set[str]]:
    """``(adjacency, all_ids)`` view of :func:`resolve_lineage`.

    Kept for callers that only need the graph shape; the return shape mirrors
    the legacy ``VerificationDB.get_dag``.
    """
    lineage = resolve_lineage(leaf_session_ids, db=db, max_depth=max_depth)
    return lineage.adjacency, lineage.all_ids


def resolve_producer(
    db,
    file_path: str,
    content_hash: str | None = None,
) -> str | None:
    """The session that produced ``file_path`` — the leaf of a back-trace.

    With ``content_hash`` (e.g. the file's current bytes, or a claim's
    registered source hash) the newest producer that recorded THOSE bytes is
    returned. Without one — or when no producer recorded those bytes — the
    newest producer of the path is returned, so that verifying it reports the
    divergence instead of hiding the file's history.
    """
    resolved = str(Path(file_path).resolve())
    records = db.find_producer_records([resolved]).get(resolved, [])
    if not records:
        return None
    if content_hash:
        for rec in records:
            if hashes_match(rec.get("hash"), content_hash):
                return rec.get("session_id")
    return records[0].get("session_id")


def current_hash_or_none(file_path: str) -> str | None:
    """Hash of the file's current bytes, or ``None`` when it cannot be read."""
    from .._hash import hash_file

    try:
        return hash_file(file_path)
    except OSError:
        return None


def order_roots_first(
    adjacency: dict[str, list[str]],
    all_ids: set[str],
) -> list[str]:
    """Order sessions roots-first (parents before children), cycle-tolerant.

    A Kahn topological sort over ``adjacency`` (``{child: [parents]}``). Unlike
    the strict DAG sort, any cyclic remnant is appended in stable id order
    rather than raising — ``chain()`` must never blow up on a pathological
    graph that the resolver already bounded.
    """
    in_degree = {node: len(adjacency.get(node, [])) for node in all_ids}
    children: dict[str, list[str]] = defaultdict(list)
    for child, parents in adjacency.items():
        for parent in parents:
            children[parent].append(child)

    queue = deque(sorted(n for n in all_ids if in_degree.get(n, 0) == 0))
    order: list[str] = []
    seen: set[str] = set()
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

    for node in sorted(all_ids):
        if node not in seen:
            order.append(node)
    return order


def _dedup(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


# EOF
