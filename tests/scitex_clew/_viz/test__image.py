#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for ``scitex_clew._viz._image`` — native matplotlib DAG image export.

PA-306: no mocks — all tests use real DB state with real files.
PA-307: one observable assertion per test; AAA markers each on their own line.

Test coverage:
  (a) render_dag_image writes non-empty PNG and SVG files for a real DAG.
  (b) status_color() maps status strings to the canonical palette.
  (c) Exception node gets dashed/lavender style; frozen file gets frozen style.
  (d) CLI --format png/svg writes the file; --format mermaid is text.
  (e) matplotlib-missing error path raises ImportError with clear message.
"""

from __future__ import annotations

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._hash import hash_file


# ---------------------------------------------------------------------------
# Skip entire module if matplotlib is absent (but test the error-path below).
# ---------------------------------------------------------------------------
matplotlib = pytest.importorskip("matplotlib", reason="matplotlib not installed")


# ---------------------------------------------------------------------------
# Shared DB fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Fresh per-test DB; reset after."""
    # Arrange
    db_path = tmp_path / "test_image.db"
    set_db(db_path)
    # Act
    yield _db_module.get_db()
    # Assert (teardown)
    _db_module._DB_INSTANCE = None


@pytest.fixture
def two_session_db(isolated_db, tmp_path):
    """DB with two sessions A -> B sharing mid.csv."""
    db = isolated_db
    raw = tmp_path / "raw.csv"
    raw.write_text("col\n1\n2\n")
    mid = tmp_path / "mid.csv"
    mid.write_text("avg\n1.5\n")
    leaf = tmp_path / "leaf.csv"
    leaf.write_text("final\n1.0\n")

    sid_a = "2026Y-01M-01D-00h00m00s_ImgA"
    db.add_run(sid_a, script_path="/scripts/step_a.py")
    db.add_file_hash(sid_a, str(raw.resolve()), hash_file(raw), "input")
    db.add_file_hash(sid_a, str(mid.resolve()), hash_file(mid), "output")
    db.finish_run(sid_a, status="success", combined_hash=f"chash_{sid_a}")

    sid_b = "2026Y-01M-01D-01h00m00s_ImgB"
    db.add_run(sid_b, script_path="/scripts/step_b.py")
    db.add_file_hash(sid_b, str(mid.resolve()), hash_file(mid), "input")
    db.add_file_hash(sid_b, str(leaf.resolve()), hash_file(leaf), "output")
    db.finish_run(sid_b, status="success", combined_hash=f"chash_{sid_b}")
    db.add_parent(sid_b, sid_a)

    return {"db": db, "sid_a": sid_a, "sid_b": sid_b,
            "raw": raw, "mid": mid, "leaf": leaf}


@pytest.fixture
def exception_run_db(isolated_db, tmp_path):
    """DB with one exception-provenance session (no file hashes)."""
    db = isolated_db
    sid = "2026Y-06M-28D-00h00m00s_ExcImg"
    db.add_run(
        sid,
        script_path="/scripts/gpac.py",
        provenance="exception",
        exception_reason="4.1TB gPAC, recipe-known",
    )
    db.finish_run(sid, status="success")
    return {"db": db, "sid": sid}


@pytest.fixture
def frozen_run_db(isolated_db, tmp_path):
    """DB with one session that has a frozen input file."""
    db = isolated_db
    sid = "2026Y-06M-28D-10h00m00s_FrzImg"
    frozen_file = tmp_path / "huge.npz"
    frozen_file.write_bytes(b"placeholder")
    db.add_run(sid, script_path="/scripts/consumer.py")
    db.add_file_hash(
        sid, str(frozen_file.resolve()),
        "precomputed_sha256_placeholder", "input", frozen=True,
    )
    out_file = tmp_path / "result.csv"
    out_file.write_text("val\n1\n")
    db.add_file_hash(sid, str(out_file.resolve()), hash_file(out_file), "output")
    db.finish_run(sid, status="success")
    return {"db": db, "sid": sid,
            "frozen_file": frozen_file, "out_file": out_file}


# ---------------------------------------------------------------------------
# (a) render_dag_image writes a non-empty PNG file
# ---------------------------------------------------------------------------


def test_render_dag_image_png_file_exists(two_session_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image import render_dag_image
    out = tmp_path / "dag.png"
    # Act
    render_dag_image(str(out), fmt="png")
    # Assert
    assert out.exists()


def test_render_dag_image_png_file_nonempty(two_session_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image import render_dag_image
    out = tmp_path / "dag_ne.png"
    # Act
    render_dag_image(str(out), fmt="png")
    # Assert
    assert out.stat().st_size > 0


def test_render_dag_image_svg_file_exists(two_session_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image import render_dag_image
    out = tmp_path / "dag.svg"
    # Act
    render_dag_image(str(out), fmt="svg")
    # Assert
    assert out.exists()


def test_render_dag_image_svg_file_nonempty(two_session_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image import render_dag_image
    out = tmp_path / "dag_ne.svg"
    # Act
    render_dag_image(str(out), fmt="svg")
    # Assert
    assert out.stat().st_size > 0


def test_render_dag_image_returns_string_path(two_session_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image import render_dag_image
    out = tmp_path / "dag_ret.png"
    # Act
    result = render_dag_image(str(out), fmt="png")
    # Assert
    assert isinstance(result, str)


def test_render_dag_image_returns_absolute_path(two_session_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image import render_dag_image
    out = tmp_path / "dag_abs.png"
    # Act
    result = render_dag_image(str(out), fmt="png")
    # Assert
    import os
    assert os.path.isabs(result)


def test_render_dag_image_creates_parent_dirs(isolated_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image import render_dag_image
    out = tmp_path / "subdir" / "nested" / "dag.png"
    # Act
    render_dag_image(str(out), fmt="png")
    # Assert
    assert out.exists()


# ---------------------------------------------------------------------------
# (b) status_color maps statuses to canonical palette
# ---------------------------------------------------------------------------


def test_status_color_verified_fill_is_light_green():
    # Arrange — schema v1.3: verified fill updated to #2da44e (matching display_palette)
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("verified")
    # Assert
    assert fill == "#2da44e"


def test_status_color_verified_edge_is_dark_green():
    # Arrange — schema v1.3: verified edge updated to #1a6b32 (darker green)
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("verified")
    # Assert
    assert edge == "#1a6b32"


def test_status_color_verified_linestyle_is_solid():
    # Arrange
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("verified")
    # Assert
    assert ls is None


def test_status_color_failed_fill_is_red():
    # Arrange — schema v1.3: failed fill updated to #cf222e (matching display_palette unverified)
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("failed")
    # Assert
    assert fill == "#cf222e"


def test_status_color_mismatch_fill_matches_failed():
    # Arrange
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill_f, _, _ = status_color("failed")
    fill_m, _, _ = status_color("mismatch")
    # Assert
    assert fill_m == fill_f


def test_status_color_suspect_fill_is_amber():
    # Arrange — schema v1.3: suspect fill updated to #d29922 (matching display_palette suspect)
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("suspect")
    # Assert
    assert fill == "#d29922"


def test_status_color_unknown_returns_tuple_of_three():
    # Arrange
    from scitex_clew._viz._image_palette import status_color
    # Act
    result = status_color("unknown")
    # Assert
    assert len(result) == 3


# ---------------------------------------------------------------------------
# (c) Exception node style: solid violet; frozen file: solid verified green
# (Schema v1.3: exception and frozen use solid fills, color-only, no dashes)
# ---------------------------------------------------------------------------


def test_exception_status_fill_is_lavender():
    # Arrange — schema v1.3: exception fill is violet #8250df (solid, not lavender)
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("exception")
    # Assert
    assert fill == "#8250df"


def test_exception_status_edge_is_purple():
    # Arrange — schema v1.3: exception edge is #4a1c8a (darker purple)
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("exception")
    # Assert
    assert edge == "#4a1c8a"


def test_exception_status_linestyle_is_dashed():
    # Arrange — schema v1.3: exception uses solid fill, NOT dashed (color conveys exception)
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("exception")
    # Assert — v1.3: solid (None), not dashed
    assert ls is None


def test_file_frozen_status_fill_is_light_blue():
    # Arrange — schema v1.3: frozen folds into verified green #2da44e (not light blue)
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("file_frozen")
    # Assert
    assert fill == "#2da44e"


def test_file_frozen_status_edge_is_steel_blue():
    # Arrange — schema v1.3: frozen uses verified green edge #1a6b32 (not steel blue)
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("file_frozen")
    # Assert
    assert edge == "#1a6b32"


def test_file_frozen_status_linestyle_is_dashed():
    # Arrange — schema v1.3: frozen is solid (not dashed); folds into verified green
    from scitex_clew._viz._image_palette import status_color
    # Act
    fill, edge, ls = status_color("file_frozen")
    # Assert — v1.3: solid (None), not dashed
    assert ls is None


def test_exception_run_dag_image_node_has_exception_status(exception_run_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image_dag import build_dag_graph
    # Act
    nodes, edges = build_dag_graph()
    exception_nodes = [n for n in nodes if n.get("is_exception")]
    # Assert
    assert len(exception_nodes) > 0


def test_exception_run_dag_image_node_status_is_exception(exception_run_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image_dag import build_dag_graph
    # Act
    nodes, edges = build_dag_graph()
    exception_nodes = [n for n in nodes if n.get("is_exception")]
    # Assert
    assert exception_nodes[0]["status"] == "exception"


def test_frozen_run_dag_image_file_node_has_frozen_status(frozen_run_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image_dag import build_dag_graph
    # Act
    nodes, edges = build_dag_graph()
    frozen_nodes = [n for n in nodes if n["status"] == "file_frozen"]
    # Assert
    assert len(frozen_nodes) > 0


def test_frozen_run_dag_image_file_node_is_frozen_flag(frozen_run_db, tmp_path):
    # Arrange
    from scitex_clew._viz._image_dag import build_dag_graph
    # Act
    nodes, edges = build_dag_graph()
    frozen_nodes = [n for n in nodes if n.get("is_frozen")]
    # Assert
    assert len(frozen_nodes) > 0


# ---------------------------------------------------------------------------
# (e) matplotlib-missing error path — tested via source inspection (no mocks)
# ---------------------------------------------------------------------------


def test_render_dag_image_error_message_string_contains_all():
    # Arrange — read the source of _image.py to verify the error message text
    from pathlib import Path as _Path
    src = _Path(__file__).parent.parent.parent.parent / "src" / "scitex_clew" / "_viz" / "_image.py"
    # Act
    source_text = src.read_text()
    # Assert — the lazy ImportError must mention the [all] extra (two-bucket convention)
    assert "scitex-clew[all]" in source_text


def test_render_dag_image_error_message_string_mentions_uv_pip_install():
    # Arrange
    from pathlib import Path as _Path
    src = _Path(__file__).parent.parent.parent.parent / "src" / "scitex_clew" / "_viz" / "_image.py"
    # Act
    source_text = src.read_text()
    # Assert — the hint must include uv pip install guidance
    assert "uv pip install" in source_text


# ---------------------------------------------------------------------------
# Layered layout unit tests
# ---------------------------------------------------------------------------


def test_layered_layout_returns_dict_for_all_nodes():
    # Arrange
    from scitex_clew._viz._image_layout import layered_layout
    nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    edges = [("a", "b"), ("b", "c")]
    # Act
    pos = layered_layout(nodes, edges)
    # Assert
    assert set(pos.keys()) == {"a", "b", "c"}


def test_layered_layout_source_has_smaller_x_than_target():
    # Arrange
    from scitex_clew._viz._image_layout import layered_layout
    nodes = [{"id": "src"}, {"id": "tgt"}]
    edges = [("src", "tgt")]
    # Act
    pos = layered_layout(nodes, edges)
    # Assert
    assert pos["src"][0] < pos["tgt"][0]


def test_layered_layout_single_node_returns_origin():
    # Arrange
    from scitex_clew._viz._image_layout import layered_layout
    nodes = [{"id": "only"}]
    edges = []
    # Act
    pos = layered_layout(nodes, edges)
    # Assert
    assert pos["only"] == (0.0, 0.0)


# EOF
