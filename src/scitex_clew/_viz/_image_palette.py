#!/usr/bin/env python3
# Timestamp: "2026-06-30 (ywatanabe)"
# File: src/scitex_clew/_viz/_image_palette.py
"""Colour palette and style helpers for DAG image export.

Canonical light-theme hexes mirror the mermaid classDefs in _mermaid_nodes.py.
All functions are pure (no matplotlib state).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical node fill colours per status class
# ---------------------------------------------------------------------------

NODE_FILL: dict[str, str] = {
    "verified": "#90EE90",
    "verified_scratch": "#90EE90",
    "failed": "#FFB6C1",
    "mismatch": "#FFB6C1",
    "missing": "#FFB6C1",
    "suspect": "#FFD580",
    "partial": "#FFD580",
    "exception": "#E6E6FA",
    "file_ok": "#90EE90",
    "file_rerun": "#90EE90",
    "file_bad": "#FFB6C1",
    "file_suspect": "#FFD580",
    "file_frozen": "#E0F0FF",
    "script": "#87CEEB",
    "unknown": "#F8F8F8",
    "registered": "#F8F8F8",
    "not_found": "#F8F8F8",
}

# Border (edge) colours per status class
NODE_EDGE: dict[str, str] = {
    "verified": "#228B22",
    "verified_scratch": "#228B22",
    "failed": "#DC143C",
    "mismatch": "#DC143C",
    "missing": "#DC143C",
    "suspect": "#FF8C00",
    "partial": "#FF8C00",
    "exception": "#8A2BE2",  # purple dashed
    "file_ok": "#228B22",
    "file_rerun": "#228B22",
    "file_bad": "#DC143C",
    "file_suspect": "#FF8C00",
    "file_frozen": "#4682B4",  # steel-blue dashed
    "script": "#4169E1",
    "unknown": "#6e7781",
    "registered": "#6e7781",
    "not_found": "#6e7781",
}

# Dashed-border statuses
_DASHED_STATUSES: frozenset[str] = frozenset({"exception", "file_frozen"})


def status_color(status: str) -> tuple[str, str, str | None]:
    """Return (fill_hex, edge_hex, linestyle) for a node status string.

    ``linestyle`` is ``None`` for solid borders, ``"--"`` for dashed
    (exception and file_frozen nodes match mermaid ``stroke-dasharray:6 4``).

    Pure function — no matplotlib state, safe to call before any import.
    """
    fill = NODE_FILL.get(status, NODE_FILL["unknown"])
    edge = NODE_EDGE.get(status, NODE_EDGE["unknown"])
    linestyle: str | None = "--" if status in _DASHED_STATUSES else None
    return fill, edge, linestyle


# EOF
