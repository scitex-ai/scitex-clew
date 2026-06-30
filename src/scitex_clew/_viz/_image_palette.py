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
    "verified": "#2da44e",
    "verified_scratch": "#2da44e",
    "failed": "#cf222e",
    "mismatch": "#cf222e",
    "missing": "#cf222e",
    "suspect": "#d29922",
    "exception": "#8250df",
    "file_ok": "#2da44e",
    "file_rerun": "#2da44e",
    "file_bad": "#cf222e",
    "file_suspect": "#d29922",
    "file_frozen": "#2da44e",  # frozen folds into verified green
    "script": "#87CEEB",
    "unknown": "#F8F8F8",
    "registered": "#F8F8F8",
    "not_found": "#F8F8F8",
}

# Border (edge) colours per status class
NODE_EDGE: dict[str, str] = {
    "verified": "#1a6b32",
    "verified_scratch": "#1a6b32",
    "failed": "#8b1a1a",
    "mismatch": "#8b1a1a",
    "missing": "#8b1a1a",
    "suspect": "#8a5c00",
    "exception": "#4a1c8a",  # darker purple
    "file_ok": "#1a6b32",
    "file_rerun": "#1a6b32",
    "file_bad": "#8b1a1a",
    "file_suspect": "#8a5c00",
    "file_frozen": "#1a6b32",  # frozen folds into verified green
    "script": "#4169E1",
    "unknown": "#6e7781",
    "registered": "#6e7781",
    "not_found": "#6e7781",
}

# Dashed-border statuses (schema v1.3: exception and frozen are solid, not dashed)
_DASHED_STATUSES: frozenset[str] = frozenset()


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
