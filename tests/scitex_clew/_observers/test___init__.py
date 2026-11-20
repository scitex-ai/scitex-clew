#!/usr/bin/env python3
"""Tests for scitex_clew._observers hook self-registration (SOC R6).

Covers the io seam (post-save/load) and the scitex-session lifecycle-hook
registry seam. Both are the acyclic observer pattern: the peer package owns the
registry, clew subscribes, the peer never imports clew.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import types

import pytest
from scitex_clew._db._paths import project_root

from scitex_clew._chain._slice import build_slice
from scitex_clew._db import get_db
from scitex_clew._observers import (
    bootstrap_register,
    on_io_load,
    on_io_save,
    register_with_scitex_io,
    register_with_scitex_session,
)
from scitex_clew._tracker import set_tracker, start_tracking, stop_tracking


@pytest.fixture(autouse=True)
def _one_clew_project_scope(tmp_path):
    """Session hooks and the reads in these tests share ONE clew project scope.

    clew scopes a session's records to the session's project root, so a read
    from the test process's cwd would look in another project. An explicit
    ``project_root`` block wins over both (scoping itself is tested in
    ``tests/scitex_clew/_core/test__project_root.py``).
    """
    with project_root(tmp_path.resolve()):
        yield


@pytest.fixture(autouse=True)
def isolated_state():
    """No active tracker and a clean observer registry for each test."""
    set_tracker(None)
    import scitex_clew._observers as _obs

    _obs._registered_io_ids.clear()
    _obs._registered_session_ids.clear()
    _obs._warned_peers.clear()
    _obs._warned_io_failures.clear()
    yield
    set_tracker(None)
    _obs._registered_io_ids.clear()
    _obs._registered_session_ids.clear()
    _obs._warned_peers.clear()
    _obs._warned_io_failures.clear()


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


def test_on_io_save_logs_debug_when_no_tracker(tmp_path, caplog):
    # Arrange
    path = tmp_path / "out.csv"
    set_tracker(None)
    # Act
    with caplog.at_level(logging.DEBUG, logger="scitex_clew._observers"):
        on_io_save(path, obj=None, kwargs={"track": True})
    # Assert
    assert any(
        "no active session tracker" in r.getMessage() for r in caplog.records
    )


# --- a store failure in the io seam is LOUD, never a DEBUG line --------------
# A store that refuses writes (unreachable host, StoreProvisionError under
# managed roles, a dropped connection) must not leave a run looking complete.


@pytest.fixture
def unreachable_store():
    """THE store resolves to a real Postgres endpoint that refuses connections.

    Port 9 (discard) on loopback: nothing listens, so libpq fails immediately
    with a genuine connection error — no mock, no network beyond loopback.
    """
    from scitex_clew._db import reset_db

    previous = os.environ.get("SCITEX_STORE_DSN")
    os.environ["SCITEX_STORE_DSN"] = (
        "postgresql://nobody@127.0.0.1:9/none?connect_timeout=2"
    )
    reset_db()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SCITEX_STORE_DSN", None)
        else:
            os.environ["SCITEX_STORE_DSN"] = previous
        reset_db()


def _io_warnings(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and "provenance was NOT recorded" in r.getMessage()
    ]


def test_on_io_save_warns_when_store_is_unreachable(tmp_path, caplog, unreachable_store):
    # Arrange
    path = tmp_path / "out.csv"
    path.write_text("x\n1\n")
    # Act
    with caplog.at_level(logging.WARNING, logger="scitex_clew._observers"):
        on_io_save(path, obj=None, kwargs={"track": True})
    # Assert
    assert any(str(path) in m for m in _io_warnings(caplog))


def test_on_io_save_warning_names_the_store_error(tmp_path, caplog, unreachable_store):
    # Arrange
    path = tmp_path / "out.csv"
    path.write_text("x\n1\n")
    # Act
    with caplog.at_level(logging.WARNING, logger="scitex_clew._observers"):
        on_io_save(path, obj=None, kwargs={"track": True})
    # Assert
    assert any("127.0.0.1" in m for m in _io_warnings(caplog))


def test_repeated_identical_store_failure_warns_once(tmp_path, caplog, unreachable_store):
    # Arrange
    paths = [tmp_path / f"out{i}.csv" for i in range(3)]
    for p in paths:
        p.write_text("x\n1\n")
    # Act
    with caplog.at_level(logging.WARNING, logger="scitex_clew._observers"):
        for p in paths:
            on_io_save(p, obj=None, kwargs={"track": True})
    # Assert
    assert len(_io_warnings(caplog)) == 1


def test_on_io_load_warns_when_store_is_unreachable(tmp_path, caplog, unreachable_store):
    # Arrange
    path = tmp_path / "in.csv"
    path.write_text("x\n1\n")
    # Act
    with caplog.at_level(logging.WARNING, logger="scitex_clew._observers"):
        on_io_load(path, result=None)
    # Assert
    assert any(str(path) in m for m in _io_warnings(caplog))


@pytest.fixture
def unreadable_output(tmp_path):
    """A saved file clew cannot hash (mode 000): recording it really fails."""
    path = tmp_path / "out.csv"
    path.write_text("x\n1\n")
    path.chmod(0)
    if os.access(path, os.R_OK):  # root ignores the mode
        pytest.skip("running as a user that can read a mode-000 file")
    try:
        yield path
    finally:
        path.chmod(0o644)


def test_in_session_record_failure_is_appended_to_hook_failures(unreadable_output):
    # Arrange — a live session; recording this output raises.
    from scitex_clew._observers._session import HOOK_FAILURES

    start_tracking("sess-io-fail-1", script_path=None)
    before = len(HOOK_FAILURES)
    # Act
    on_io_save(unreadable_output, obj=None, kwargs={"track": True})
    # Assert
    new = HOOK_FAILURES[before:]
    assert [(f["phase"], f["session_id"], f["path"]) for f in new] == [
        ("io-save", "sess-io-fail-1", str(unreadable_output))
    ]


def test_in_session_record_failure_warns_session_incomplete(unreadable_output, caplog):
    # Arrange
    start_tracking("sess-io-fail-2", script_path=None)
    # Act
    with caplog.at_level(logging.WARNING, logger="scitex_clew._observers"):
        on_io_save(unreadable_output, obj=None, kwargs={"track": True})
    # Assert
    assert any(
        "session sess-io-fail-2 is INCOMPLETE" in m for m in _io_warnings(caplog)
    )


def test_in_session_record_failure_is_attached_to_the_run(unreadable_output):
    # Arrange
    start_tracking("sess-io-fail-3", script_path=None)
    # Act
    on_io_save(unreadable_output, obj=None, kwargs={"track": True})
    # Assert
    metadata = get_db().get_run("sess-io-fail-3")["metadata"] or ""
    assert "io-save" in metadata and "PermissionError" in metadata


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


# --- derived_from through the io seam (level-2 slice) ------------------------
# The io-hook seam honours ``derived_from`` — real store, real files.
#
# Toy: step 1 writes used.csv and unused.csv; step 2 loads BOTH and saves
# result.json. Each file event goes through ``on_io_load`` / ``on_io_save``
# with exactly the payload scitex-io sends (``kwargs["derived_from"]`` is a
# list of realpaths, present only when the caller declared it).
#
# * declared ``[used.csv]`` -> ``slice(level=2)`` drops unused.csv (and the
#   level-1 slice keeps it, because step 2 read it);
# * nothing declared -> level 2 equals level 1 (no invented edges);
# * the same bytes recorded twice (a figure tool records its image, then the
#   ``stx.io.save`` that called it fires its hook) keep the declaration.


@pytest.fixture(autouse=True)
def _no_claims_export():
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    yield
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _toy(tmp_path, declared):
    """Run the two-step toy through the io hooks; return result.json's path."""
    used, unused = tmp_path / "used.csv", tmp_path / "unused.csv"
    result = tmp_path / "result.json"
    script = tmp_path / "step.py"
    script.write_text("# step\n")

    start_tracking("step1", script_path=str(script))
    for path, rows in ((used, "x\n1\n2\n"), (unused, "x\n9\n")):
        path.write_text(rows)
        on_io_save(path, None, {"track": True})
    stop_tracking()

    start_tracking("step2", script_path=str(script))
    on_io_load(used, None)
    on_io_load(unused, None)
    result.write_text(json.dumps({"n": 2}))
    kwargs = {"track": True}
    if declared is not None:
        kwargs["derived_from"] = [str(p) for p in declared(used, unused)]
    on_io_save(result, {"n": 2}, kwargs)
    stop_tracking()
    return result, unused


def _names(sl):
    return sorted(os.path.basename(p) for p in sl.files)


def test_level1_keeps_the_input_the_run_read_but_did_not_use(tmp_path):
    # Arrange
    result, _ = _toy(tmp_path, declared=lambda used, unused: [used])
    # Act
    sl = build_slice([result], level=1)
    # Assert
    assert _names(sl) == ["result.json", "unused.csv", "used.csv"]


def test_level2_drops_the_undeclared_input(tmp_path):
    # Arrange
    result, _ = _toy(tmp_path, declared=lambda used, unused: [used])
    # Act
    sl = build_slice([result], level=2)
    # Assert
    assert _names(sl) == ["result.json", "used.csv"]


def test_level2_reports_the_dropped_input(tmp_path):
    # Arrange
    result, unused = _toy(tmp_path, declared=lambda used, unused: [used])
    # Act
    sl = build_slice([result], level=2)
    # Assert
    assert sl.dropped_inputs.get("step2") == [str(unused.resolve())]


def test_without_declaration_level2_equals_level1(tmp_path):
    # Arrange
    result, _ = _toy(tmp_path, declared=None)
    # Act
    counts = [build_slice([result], level=lvl).counts() for lvl in (1, 2)]
    # Assert
    assert counts[0] == counts[1]


def test_without_declaration_level2_keeps_every_input(tmp_path):
    # Arrange
    result, _ = _toy(tmp_path, declared=None)
    # Act
    sl = build_slice([result], level=2)
    # Assert
    assert _names(sl) == ["result.json", "unused.csv", "used.csv"]


def _double_record(tmp_path, first, second):
    """Record result.json twice (same bytes) with two payloads; slice level 2."""
    used, unused = tmp_path / "used.csv", tmp_path / "unused.csv"
    used.write_text("x\n1\n")
    unused.write_text("x\n9\n")
    result = tmp_path / "result.json"
    start_tracking("both", script_path=None)
    on_io_load(used, None)
    on_io_load(unused, None)
    result.write_text("{}")
    paths = {"used": str(used), "unused": str(unused)}
    for decl in (first, second):
        kwargs = {"track": True}
        if decl is not None:
            kwargs["derived_from"] = [paths[n] for n in decl]
        on_io_save(result, None, kwargs)
    stop_tracking()
    return _names(build_slice([result], level=2))


def test_undeclared_rerecord_of_same_bytes_keeps_declaration(tmp_path):
    # Arrange
    first, second = ["used"], None
    # Act
    names = _double_record(tmp_path, first, second)
    # Assert
    assert names == ["result.json", "used.csv"]


def test_second_declaration_of_same_bytes_is_unioned(tmp_path):
    # Arrange
    first, second = ["used"], ["unused"]
    # Act
    names = _double_record(tmp_path, first, second)
    # Assert
    assert names == ["result.json", "unused.csv", "used.csv"]


def test_rewritten_bytes_drop_the_old_declaration(tmp_path):
    # Arrange: declared write, then NEW bytes written without a declaration
    used, unused = tmp_path / "used.csv", tmp_path / "unused.csv"
    used.write_text("x\n1\n")
    unused.write_text("x\n9\n")
    result = tmp_path / "result.json"
    start_tracking("rewrite", script_path=None)
    on_io_load(used, None)
    on_io_load(unused, None)
    result.write_text("{}")
    on_io_save(result, None, {"track": True, "derived_from": [str(used)]})
    result.write_text('{"changed": 1}')
    on_io_save(result, None, {"track": True})
    stop_tracking()
    # Act
    sl = build_slice([result], level=2)
    # Assert
    assert _names(sl) == ["result.json", "unused.csv", "used.csv"]
