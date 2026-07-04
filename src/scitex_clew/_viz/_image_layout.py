#!/usr/bin/env python3
# Timestamp: "2026-06-30 (ywatanabe)"
# File: src/scitex_clew/_viz/_image_layout.py
"""Layered DAG layout — no external library required.

Uses a simple topological-sort-based (Kahn's algorithm) layering:
layers flow left-to-right (increasing x), nodes within a layer are
spaced vertically (decreasing y, so top-of-layer is highest y).
"""

from __future__ import annotations


def layered_layout(
    nodes: list[dict],
    edges: list[tuple[str, str]],
    *,
    x_gap: float = 3.0,
    y_gap: float = 1.6,
) -> dict[str, tuple[float, float]]:
    """Assign (x, y) positions for *nodes* given *edges*.

    Parameters
    ----------
    nodes:
        Node dicts with at least ``{"id": str}`` each.
    edges:
        (source_id, target_id) pairs.
    x_gap:
        Horizontal distance between successive layers.
    y_gap:
        Vertical distance between nodes in the same layer.

    Returns
    -------
    dict[str, tuple[float, float]]
        Mapping node-id -> (x, y) centre position.
    """
    node_id_set = {n["id"] for n in nodes}

    # Build successor / predecessor maps
    successors: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    predecessors: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    for src, tgt in edges:
        if src in node_id_set and tgt in node_id_set:
            successors[src].add(tgt)
            predecessors[tgt].add(src)

    # Kahn's algorithm: assign each node to its earliest possible layer
    in_degree = {n["id"]: len(predecessors[n["id"]]) for n in nodes}
    queue: list[str] = [nid for nid, d in in_degree.items() if d == 0]
    layer: dict[str, int] = {}
    while queue:
        nid = queue.pop(0)
        layer[nid] = max(
            (layer[pred] + 1 for pred in predecessors[nid] if pred in layer),
            default=0,
        )
        for succ in successors[nid]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    # Handle cycles: assign remaining to last_layer + 1
    max_layer = max(layer.values(), default=0) if layer else 0
    for n in nodes:
        if n["id"] not in layer:
            layer[n["id"]] = max_layer + 1

    # Group nodes by layer
    layers: dict[int, list[str]] = {}
    for nid, lyr in layer.items():
        layers.setdefault(lyr, []).append(nid)

    # Assign positions
    positions: dict[str, tuple[float, float]] = {}
    for lyr_idx, nids in sorted(layers.items()):
        x = lyr_idx * x_gap
        total_height = (len(nids) - 1) * y_gap
        for j, nid in enumerate(nids):
            y = total_height / 2 - j * y_gap
            positions[nid] = (x, y)

    return positions


# EOF
