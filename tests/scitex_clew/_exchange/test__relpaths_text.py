"""Absolute in-project paths inside prose -> project-relative (portable_text)."""

from __future__ import annotations

from pathlib import Path

import pytest
from scitex_clew._exchange._relpaths import portable_text

ROOT = Path("/home/u/proj/x")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("source changed: /home/u/proj/x/data/a.json", "source changed: data/a.json"),
        ("missing /home/u/proj/x/data/a.json.", "missing data/a.json."),
        ("at /home/u/proj/x/paper.tex:L10 here", "at paper.tex:L10 here"),
        ("'/home/u/proj/x/r/out.csv' differs", "'r/out.csv' differs"),
        ("(/home/u/proj/x/a.json, /home/u/proj/x/b.json)", "(a.json, b.json)"),
        ("root /home/u/proj/x is clean", "root . is clean"),
        (
            "value[/n_rows]: claimed 3 vs source 2",
            "value[/n_rows]: claimed 3 vs source 2",
        ),
    ],
)
def test_in_project_tokens_become_relative(text, expected):
    # Arrange
    root = ROOT
    # Act
    out = portable_text(text, root)
    # Assert
    assert out == expected


@pytest.mark.parametrize(
    "text",
    [
        "source changed: /mnt/shared/data/a.json",
        "sibling /home/u/proj/x2/data/a.json differs",
        "see https://example.org/home/u/proj/x/a.json",
        "1/2 of runs and/or ./data/a.json or ~/a.json",
        "pointer /auc not found",
        "",
    ],
)
def test_other_text_is_left_exactly_as_written(text):
    # Arrange
    root = ROOT
    # Act
    out = portable_text(text, root)
    # Assert
    assert out == text


def test_root_spelled_with_spaces_is_rewritten():
    # Arrange
    root = Path("/home/u/My Project")
    # Act
    out = portable_text("source changed: /home/u/My Project/data/a.json", root)
    # Assert
    assert out == "source changed: data/a.json"


def test_none_passes_through():
    # Arrange
    root = ROOT
    # Act
    out = portable_text(None, root)
    # Assert
    assert out is None
