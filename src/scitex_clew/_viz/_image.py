#!/usr/bin/env python3
# Timestamp: "2026-06-30 (ywatanabe)"
# File: src/scitex_clew/_viz/_image.py
"""Native matplotlib DAG image export for scitex-clew.

Public entry-point: ``render_dag_image(output_path, ...)``

matplotlib is imported LAZILY (inside the function body) so that
``import scitex_clew`` cold-start is NOT affected.  All heavy logic is
factored into sibling helpers:

  _image_palette.py  — colour/style constants + status_color()
  _image_dag.py      — DAG data builder
  _image_layout.py   — layered layout algorithm
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal


def render_dag_image(
    output_path: str | Path,
    *,
    targets: list[str] | None = None,
    claims: bool = False,
    max_depth: int = 10,
    show_files: bool = True,
    grouper: Any | None = None,
    fmt: Literal["png", "svg"] = "png",
) -> str:
    """Render the provenance DAG to a static PNG or SVG image.

    Uses matplotlib (Agg backend, headless) — no mmdc, no graphviz dot, no
    external web service, no headless Chrome.  matplotlib is imported lazily
    so the function is safe to import without matplotlib installed; the error
    surfaces only on first call.

    Parameters
    ----------
    output_path:
        Destination file.  The ``fmt`` parameter controls the format; the
        file extension is matched to ``fmt`` for clarity but not enforced.
    targets:
        Restrict the DAG to the upstream cone of these target files.
    claims:
        Build DAG from registered claims (default: False).
    max_depth:
        Maximum chain traversal depth.
    show_files:
        Include file nodes in the image (default: True).
    grouper:
        Optional grouper callable/spec (passed through to the DAG builder).
    fmt:
        ``"png"`` or ``"svg"``.

    Returns
    -------
    str
        Absolute path to the written image file.

    Raises
    ------
    ImportError
        When matplotlib is not installed.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # set before pyplot import — headless, no display
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        from matplotlib.patches import FancyBboxPatch
    except ImportError as exc:
        raise ImportError(
            "DAG image export needs matplotlib — uv pip install 'scitex-clew[all]'"
        ) from exc

    from ._image_dag import build_dag_graph
    from ._image_layout import layered_layout
    from ._image_palette import NODE_EDGE, NODE_FILL, status_color

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    nodes, edges = build_dag_graph(
        targets=targets,
        claims=claims,
        max_depth=max_depth,
        show_files=show_files,
        grouper=grouper,
    )

    if not nodes:
        fig, ax = plt.subplots(figsize=(4, 2))
        ax.text(0.5, 0.5, "No runs found", ha="center", va="center",
                fontsize=12, color="#6e7781")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(str(output_path), format=fmt, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(output_path.resolve())

    positions = layered_layout(nodes, edges)

    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    x_range = max(xs) - min(xs) if xs else 1.0
    y_range = max(ys) - min(ys) if ys else 1.0

    fig_w = max(6.0, x_range * 2.5 + 4.0)
    fig_h = max(4.0, y_range * 2.0 + 3.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    ax.set_aspect("equal")
    ax.axis("off")

    # Draw edges first (nodes will be drawn on top)
    for src_id, tgt_id in edges:
        if src_id not in positions or tgt_id not in positions:
            continue
        x0, y0 = positions[src_id]
        x1, y1 = positions[tgt_id]
        ax.annotate(
            "",
            xy=(x1, y1),
            xytext=(x0, y0),
            arrowprops=dict(
                arrowstyle="-|>",
                color="#555555",
                lw=1.2,
                mutation_scale=12,
            ),
        )

    box_w, box_h = 2.2, 0.9
    for node in nodes:
        nid = node["id"]
        if nid not in positions:
            continue
        cx, cy = positions[nid]
        fill_hex, edge_hex, linestyle = status_color(node["status"])

        patch = FancyBboxPatch(
            (cx - box_w / 2, cy - box_h / 2),
            box_w,
            box_h,
            boxstyle="round,pad=0.1",
            facecolor=fill_hex,
            edgecolor=edge_hex,
            linewidth=2.0,
            zorder=2,
        )
        if linestyle:
            patch.set_linestyle(linestyle)
        ax.add_patch(patch)

        label = node["label"]
        font_size = 6.5 if "\n" in label else 7.5
        ax.text(cx, cy, label, ha="center", va="center",
                fontsize=font_size, fontfamily="monospace",
                zorder=3, color="#111111")

    # Legend
    legend_items = [
        mpatches.Patch(facecolor=NODE_FILL["verified"],
                       edgecolor=NODE_EDGE["verified"], label="verified"),
        mpatches.Patch(facecolor=NODE_FILL["failed"],
                       edgecolor=NODE_EDGE["failed"], label="failed/mismatch"),
        mpatches.Patch(facecolor=NODE_FILL["suspect"],
                       edgecolor=NODE_EDGE["suspect"], label="suspect (upstream)"),
        mpatches.Patch(facecolor=NODE_FILL["exception"],
                       edgecolor=NODE_EDGE["exception"],
                       label="exception (declared)"),
        mpatches.Patch(facecolor=NODE_FILL["file_frozen"],
                       edgecolor=NODE_EDGE["file_frozen"],
                       label="frozen file (trusted hash)"),
    ]
    ax.legend(handles=legend_items, loc="lower right",
              fontsize=6, framealpha=0.85, ncol=1)

    ax.set_xlim(min(xs) - box_w, max(xs) + box_w)
    ax.set_ylim(min(ys) - box_h * 2, max(ys) + box_h * 2)

    fig.tight_layout(pad=0.5)
    fig.savefig(str(output_path), format=fmt, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(output_path.resolve())


# EOF
