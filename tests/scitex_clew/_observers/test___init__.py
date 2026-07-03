#!/usr/bin/env python3
"""Tests for scitex_clew._observers hook self-registration (SOC R6).

Covers the io seam (post-save/load) and the scitex-session lifecycle-hook
registry seam. Both are the acyclic observer pattern: the peer package owns the
registry, clew subscribes, the peer never imports clew.
"""

from __future__ import annotations

import logging
import sys
import types

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import get_db, set_db
from scitex_clew._observers import (
    bootstrap_register,
    on_io_load,
    on_io_save,
    register_with_scitex_io,
    register_with_scitex_session,
)
from scitex_clew._tracker import set_tracker


@pytest.fixture(autouse=True)
def isolated_state(tmp_path):
    """Fresh DB and no active tracker for each test."""
    db_path = tmp_path / "hooks_test.db"
    set_db(db_path)
    set_tracker(None)
    import scitex_clew._observers as _obs

    _obs._registered_io_ids.clear()
    _obs._registered_session_ids.clear()
    yield
    _db_module._DB_INSTANCE = None
    set_tracker(None)
    _obs._registered_io_ids.clear()
    _obs._registered_session_ids.clear()


# --- io seam ----------------------------------------------------------------


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
    pytest.importorskip("scitex_io")
    # Act
    ok = register_with_scitex_io()
    # Assert
    assert ok is True


@pytest.fixture
def fake_scitex_io():
    """A real synthetic scitex_io module capturing hook registrations (PA-306).

    Not a mock — a real module installed in sys.modules; its register_* append
    to lists so a test can count registrations.
    """
    save_hooks: list = []
    load_hooks: list = []
    mod = types.ModuleType("scitex_io")
    mod.register_post_save_hook = lambda fn: save_hooks.append(fn)
    mod.register_post_load_hook = lambda fn: load_hooks.append(fn)
    prev = sys.modules.get("scitex_io")
    sys.modules["scitex_io"] = mod
    try:
        yield {"save": save_hooks, "load": load_hooks}
    finally:
        if prev is not None:
            sys.modules["scitex_io"] = prev
        else:
            sys.modules.pop("scitex_io", None)


def test_register_with_scitex_io_is_idempotent(fake_scitex_io):
    # Arrange — register once against this instance.
    register_with_scitex_io()
    # Act — a second call must NOT double-register the same instance.
    register_with_scitex_io()
    # Assert
    assert len(fake_scitex_io["save"]) == 1


# --- scitex-session lifecycle-hook registry seam ----------------------------


@pytest.fixture
def fake_scitex_session():
    """A real synthetic scitex_session module exposing the hook registry.

    PA-306: not a mock — a real module object we install in sys.modules and
    remove afterwards; its register_* capture the callables clew subscribes.
    """
    captured: dict = {}
    mod = types.ModuleType("scitex_session")
    mod.register_session_start_hook = lambda fn: captured.__setitem__("start", fn)
    mod.register_session_close_hook = lambda fn: captured.__setitem__("close", fn)
    prev = sys.modules.get("scitex_session")
    sys.modules["scitex_session"] = mod
    try:
        yield captured
    finally:
        if prev is not None:
            sys.modules["scitex_session"] = prev
        else:
            sys.modules.pop("scitex_session", None)


def test_register_with_scitex_session_returns_true(fake_scitex_session):
    # Arrange
    # Act
    ok = register_with_scitex_session()
    # Assert
    assert ok is True


def test_register_with_scitex_session_captures_start_hook(fake_scitex_session):
    # Arrange
    register_with_scitex_session()
    captured_start = fake_scitex_session.get("start")
    # Act
    # Assert
    assert callable(captured_start)


def test_bare_module_without_registry_returns_false():
    # Arrange — a scitex_session without the registry API (guarded no-op).
    mod = types.ModuleType("scitex_session")
    prev = sys.modules.get("scitex_session")
    sys.modules["scitex_session"] = mod
    try:
        # Act
        ok = register_with_scitex_session()
        # Assert
        assert ok is False
    finally:
        if prev is not None:
            sys.modules["scitex_session"] = prev
        else:
            sys.modules.pop("scitex_session", None)


def test_start_adapter_does_not_leak_metadata_into_parent(fake_scitex_session):
    # Arrange — session fires POSITIONALLY: (session_id, script_path, metadata).
    register_with_scitex_session()
    start = fake_scitex_session["start"]
    # Act
    start("sess-adapter-1", "/tmp/script.py", {"notebook_path": "nb.ipynb"})
    # Assert — metadata must NOT land in parent_session (the adapter's whole job).
    assert get_db().get_run("sess-adapter-1")["parent_session"] is None


def test_start_adapter_records_metadata(fake_scitex_session):
    # Arrange
    register_with_scitex_session()
    start = fake_scitex_session["start"]
    # Act
    start("sess-adapter-2", "/tmp/script.py", {"notebook_path": "nb.ipynb"})
    # Assert
    assert "notebook_path" in (get_db().get_run("sess-adapter-2")["metadata"] or "")


def test_close_adapter_finalizes_run(fake_scitex_session):
    # Arrange
    register_with_scitex_session()
    fake_scitex_session["start"]("sess-adapter-3", "/tmp/script.py", None)
    # Act
    fake_scitex_session["close"]("success", 0)
    # Assert
    assert get_db().get_run("sess-adapter-3")["status"] == "success"


# --- bootstrap_register (un-swallowed registration outcome) -----------------


def test_bootstrap_register_returns_true_when_registrar_succeeds():
    # Arrange
    # Act
    result = bootstrap_register(lambda: True, "scitex_io")
    # Assert
    assert result is True


def test_bootstrap_register_returns_false_when_registrar_returns_false():
    # Arrange
    # Act
    result = bootstrap_register(lambda: False, "scitex_io")
    # Assert
    assert result is False


def test_bootstrap_register_returns_false_when_registrar_raises():
    # Arrange
    def _boom():
        raise ValueError("no register_post_save_hook")

    # Act
    result = bootstrap_register(_boom, "scitex_io")
    # Assert
    assert result is False


def test_bootstrap_register_warns_when_registrar_returns_false(caplog):
    # Arrange
    # Act
    with caplog.at_level(logging.WARNING, logger="scitex_clew._observers"):
        bootstrap_register(lambda: False, "scitex_io")
    # Assert
    assert any("returned False" in r.getMessage() for r in caplog.records)


# EOF
