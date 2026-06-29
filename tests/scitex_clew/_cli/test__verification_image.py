#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for ``print-mermaid --format png|svg`` image export via CLI.

Isolated from test__verification.py to keep both files under 512 lines.

PA-306: no mocks — all tests use real DB state with real files.
PA-307: one observable assertion per test; AAA markers each on their own line.
"""

from __future__ import annotations

import pytest

CliRunner = pytest.importorskip("click.testing").CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli._main import main
from scitex_clew._db import set_db
from scitex_clew._hash import hash_file


# ---------------------------------------------------------------------------
# Shared fixtures (minimal; mirror two_session_db from test__verification.py)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Fresh per-test DB; reset after."""
    # Arrange
    db_path = tmp_path / "test_img_cli.db"
    set_db(db_path)
    # Act
    yield _db_module.get_db()
    # Assert (teardown)
    _db_module._DB_INSTANCE = None


@pytest.fixture
def runner():
    """CliRunner with mix_stderr=False."""
    return CliRunner()


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

    sid_a = "2026Y-01M-01D-00h00m00s_ICliA"
    db.add_run(sid_a, script_path="/scripts/step_a.py")
    db.add_file_hash(sid_a, str(raw.resolve()), hash_file(raw), "input")
    db.add_file_hash(sid_a, str(mid.resolve()), hash_file(mid), "output")
    db.finish_run(sid_a, status="success", combined_hash=f"chash_{sid_a}")

    sid_b = "2026Y-01M-01D-01h00m00s_ICliB"
    db.add_run(sid_b, script_path="/scripts/step_b.py")
    db.add_file_hash(sid_b, str(mid.resolve()), hash_file(mid), "input")
    db.add_file_hash(sid_b, str(leaf.resolve()), hash_file(leaf), "output")
    db.finish_run(sid_b, status="success", combined_hash=f"chash_{sid_b}")
    db.add_parent(sid_b, sid_a)

    return {"db": db, "sid_a": sid_a, "sid_b": sid_b,
            "raw": raw, "mid": mid, "leaf": leaf}


# ---------------------------------------------------------------------------
# matplotlib availability guard
# ---------------------------------------------------------------------------

_matplotlib_available = True
try:
    import matplotlib  # noqa: F401
except ImportError:
    _matplotlib_available = False

_skip_no_mpl = pytest.mark.skipif(
    not _matplotlib_available,
    reason="matplotlib not installed; install scitex-clew[viz]",
)

# ---------------------------------------------------------------------------
# (d) CLI --format png writes file; --format mermaid (default) emits text
# ---------------------------------------------------------------------------


@_skip_no_mpl
def test_print_mermaid_format_png_exit_code_zero(runner, two_session_db, tmp_path):
    # Arrange
    out = str(tmp_path / "dag.png")
    # Act
    result = runner.invoke(main, ["print-mermaid", "--format", "png", "--output", out])
    # Assert
    assert result.exit_code == 0


@_skip_no_mpl
def test_print_mermaid_format_png_output_file_exists(runner, two_session_db, tmp_path):
    # Arrange
    out = tmp_path / "dag2.png"
    # Act
    runner.invoke(main, ["print-mermaid", "--format", "png", "--output", str(out)])
    # Assert
    assert out.exists()


@_skip_no_mpl
def test_print_mermaid_format_png_output_file_nonempty(runner, two_session_db, tmp_path):
    # Arrange
    out = tmp_path / "dag3.png"
    # Act
    runner.invoke(main, ["print-mermaid", "--format", "png", "--output", str(out)])
    # Assert
    assert out.stat().st_size > 0


@_skip_no_mpl
def test_print_mermaid_format_svg_exit_code_zero(runner, two_session_db, tmp_path):
    # Arrange
    out = str(tmp_path / "dag.svg")
    # Act
    result = runner.invoke(main, ["print-mermaid", "--format", "svg", "--output", out])
    # Assert
    assert result.exit_code == 0


@_skip_no_mpl
def test_print_mermaid_format_svg_output_file_nonempty(runner, two_session_db, tmp_path):
    # Arrange
    out = tmp_path / "dag2.svg"
    # Act
    runner.invoke(main, ["print-mermaid", "--format", "svg", "--output", str(out)])
    # Assert
    assert out.stat().st_size > 0


@_skip_no_mpl
def test_print_mermaid_format_png_default_output_path_reports_png(runner, two_session_db, tmp_path):
    # Arrange — omit --output; default path ./clew_dag.png must appear in stdout
    import os
    orig = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Act
        result = runner.invoke(main, ["print-mermaid", "--format", "png"])
        # Assert
        assert ".png" in result.output
    finally:
        os.chdir(orig)


def test_print_mermaid_default_format_mermaid_emits_text(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid"])
    # Assert
    assert "graph" in result.output


def test_print_mermaid_explicit_format_mermaid_identical_to_default(runner, two_session_db):
    # Arrange
    # Act
    result_default = runner.invoke(main, ["print-mermaid"])
    result_explicit = runner.invoke(main, ["print-mermaid", "--format", "mermaid"])
    # Assert
    assert result_default.output == result_explicit.output


def test_help_shows_format_option(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--help"])
    # Assert
    assert "--format" in result.output


def test_help_shows_output_option(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--help"])
    # Assert
    assert "--output" in result.output


# EOF
