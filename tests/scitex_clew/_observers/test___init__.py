#!/usr/bin/env python3
"""Tests for scitex_clew._observers io hooks (SOC R6 self-registration)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("scitex_io")

import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._observers import (
    on_io_load,
    on_io_save,
    register_with_scitex_io,
)
from scitex_clew._tracker import set_tracker


@pytest.fixture(autouse=True)
def isolated_state(tmp_path):
    """Fresh DB and no active tracker for each test."""
    db_path = tmp_path / "io_hooks_test.db"
    set_db(db_path)
    set_tracker(None)
    yield
    _db_module._DB_INSTANCE = None
    set_tracker(None)


def test_on_io_save_returns_none_without_raising(tmp_path):
    # Arrange
    path = tmp_path / "out.csv"

    # Act
    result = on_io_save(path, obj=None, kwargs={})

    # Assert
    assert result is None


def test_on_io_save_no_tracker_does_not_raise(tmp_path):
    # Arrange
    path = tmp_path / "out.csv"
    set_tracker(None)

    # Act
    result = on_io_save(path, obj={"x": 1}, kwargs={"track": True})

    # Assert
    assert result is None


def test_on_io_load_returns_none_without_raising(tmp_path):
    # Arrange
    path = tmp_path / "in.csv"

    # Act
    result = on_io_load(path, result=None)

    # Assert
    assert result is None


def test_register_with_scitex_io_returns_true_when_importable():
    # Arrange
    import scitex_io  # noqa: F401  — proves importability

    # Act
    ok = register_with_scitex_io()

    # Assert
    assert ok is True


# EOF
