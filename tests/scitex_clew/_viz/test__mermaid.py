#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for render_dag format handling (:mod:`scitex_clew._viz._mermaid`).

Covers the targeted error when a caller mistakenly passes the clew STORE path
(.sqlite/.db) as the render OUTPUT target (reported by paper-scitex-clew
dogfooding: a launcher used the old to_svg(db, out) signature).

Per PA-307 §3: AAA markers + one assertion per test.
"""

from __future__ import annotations

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._hash import hash_file
from scitex_clew._viz._mermaid import render_dag


@pytest.fixture
def one_run_db(tmp_path):
    """Fresh store with one finished run (real files, no mocks)."""
    db_path = tmp_path / "store" / "clew.db"
    db_path.parent.mkdir(parents=True)
    set_db(db_path)
    db = _db_module.get_db()
    raw = tmp_path / "raw.csv"
    raw.write_text("col\n1\n2\n")
    out = tmp_path / "out.csv"
    out.write_text("avg\n1.5\n")
    sid = "2026Y-01M-01D-00h00m00s_Mmd1"
    db.add_run(sid, script_path="/scripts/step.py")
    db.add_file_hash(sid, str(raw.resolve()), hash_file(raw), "input")
    db.add_file_hash(sid, str(out.resolve()), hash_file(out), "output")
    db.finish_run(sid, status="success", combined_hash=f"chash_{sid}")
    yield {"db": db, "sid": sid, "out_file": out}
    _db_module._DB_INSTANCE = None


class TestRenderDagImageFallback:
    """GH #133: .png/.svg must be written even when mmdc is unavailable.

    PATH is narrowed to a directory without mmdc so subprocess raises a
    REAL FileNotFoundError (environment manipulation, not a mock object).
    """

    def test_png_written_via_matplotlib_when_mmdc_unavailable(
        self, one_run_db, tmp_path, monkeypatch
    ):
        pytest.importorskip("matplotlib")
        # Arrange
        monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
        png = tmp_path / "figs" / "dag.png"
        # Act
        result = render_dag(str(png))
        # Assert
        assert result == png and png.exists() and png.stat().st_size > 0, (
            "render_dag must write the REQUESTED .png via the fallback"
        )

    def test_svg_written_via_matplotlib_when_mmdc_unavailable(
        self, one_run_db, tmp_path, monkeypatch
    ):
        pytest.importorskip("matplotlib")
        # Arrange
        monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
        svg = tmp_path / "figs" / "dag.svg"
        # Act
        result = render_dag(str(svg))
        # Assert
        assert result == svg and svg.exists() and svg.stat().st_size > 0, (
            "render_dag must write the REQUESTED .svg via the fallback"
        )

    def test_no_silent_mmd_pathswap_when_mmdc_unavailable(
        self, one_run_db, tmp_path, monkeypatch
    ):
        pytest.importorskip("matplotlib")
        # Arrange
        monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
        png = tmp_path / "figs" / "dag.png"
        # Act
        render_dag(str(png))
        # Assert
        assert not (tmp_path / "figs" / "dag.mmd").exists(), (
            "the old silent .mmd path-swap must be gone"
        )

    def test_raises_runtime_error_when_both_renderers_fail(
        self, one_run_db, tmp_path, monkeypatch
    ):
        pytest.importorskip("matplotlib")
        # Arrange — read-only output dir makes the matplotlib save fail
        # for real (PermissionError), after mmdc is already unreachable.
        monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
        outdir = tmp_path / "ro-figs"
        outdir.mkdir()
        outdir.chmod(0o500)
        png = outdir / "dag.png"
        # Act
        # Assert
        try:
            with pytest.raises(RuntimeError, match="could not produce"):
                render_dag(str(png))
        finally:
            outdir.chmod(0o700)


class TestRenderDagStoreAsTarget:
    def test_sqlite_output_raises_store_not_target(self, tmp_path):
        # Arrange
        out = tmp_path / ".scitex" / "clew" / "db.sqlite"
        # Act
        # Assert
        with pytest.raises(ValueError, match="store, not a render target"):
            render_dag(str(out), claims=True)

    def test_db_output_raises_store_not_target(self, tmp_path):
        # Arrange
        out = tmp_path / "store.db"
        # Act
        # Assert
        with pytest.raises(ValueError, match="store, not a render target"):
            render_dag(str(out), claims=True)

    def test_unknown_ext_still_generic_error(self, tmp_path):
        # Arrange
        out = tmp_path / "dag.xyz"
        # Act
        # Assert
        with pytest.raises(ValueError, match="Unsupported format"):
            render_dag(str(out), claims=True)


# EOF
