#!/usr/bin/env python3
"""Session-hook correctness against the real scitex-session registry + store.

(a) clew's session hooks register exactly once per scitex_session module, so
    each lifecycle event fires once.
(b) a failing hook is never swallowed: warned, recorded, re-raised.
(c) the unrecorded-outputs warning reads ``sdir_out`` from the start payload,
    counts only files newer than ``started_at`` and skips RUNNING/FINISHED*.
(e) the close hook accepts a metadata payload (capture failures).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime

import pytest
import scitex_clew._observers as obs
import scitex_session
from scitex_clew._db import get_db
from scitex_clew._observers._session import (
    HOOK_FAILURES,
    _warn_if_unrecorded_outputs,
    on_session_close,
    on_session_start,
)
from scitex_clew._tracker import get_tracker, set_tracker
from scitex_session import _hooks

LOGGER = "scitex_clew._observers._session"


@pytest.fixture(autouse=True)
def _clean():
    set_tracker(None)
    HOOK_FAILURES.clear()
    yield
    set_tracker(None)
    HOOK_FAILURES.clear()


def _clew_hooks(registry):
    return [
        h
        for h in registry
        if getattr(h, "__qualname__", "").startswith("register_with_scitex_session.")
    ]


@pytest.fixture
def empty_registry():
    """The real scitex-session registry, emptied for the test and restored."""
    saved_start = list(_hooks._SESSION_START_HOOKS)
    saved_close = list(_hooks._SESSION_CLOSE_HOOKS)
    _hooks._SESSION_START_HOOKS[:] = []
    _hooks._SESSION_CLOSE_HOOKS[:] = []
    obs._registered_session_ids.clear()
    yield _hooks
    _hooks._SESSION_START_HOOKS[:] = saved_start
    _hooks._SESSION_CLOSE_HOOKS[:] = saved_close


# ---------------------------------------------------------------------------
# (a) registered once
# ---------------------------------------------------------------------------


class TestRegistersOnce:
    def test_second_registration_adds_no_second_start_hook(self, empty_registry):
        # Arrange
        obs.register_with_scitex_session()
        # Act
        obs.register_with_scitex_session()
        # Assert
        assert len(_clew_hooks(empty_registry._SESSION_START_HOOKS)) == 1

    def test_second_registration_adds_no_second_close_hook(self, empty_registry):
        # Arrange
        obs.register_with_scitex_session()
        # Act
        obs.register_with_scitex_session()
        # Assert
        assert len(_clew_hooks(empty_registry._SESSION_CLOSE_HOOKS)) == 1

    def test_module_id_is_remembered(self, empty_registry):
        # Arrange
        expected = id(scitex_session)
        # Act
        obs.register_with_scitex_session()
        # Assert
        assert expected in obs._registered_session_ids

    def test_fired_lifecycle_records_payload_argv(self, empty_registry, tmp_path):
        # Arrange
        obs.register_with_scitex_session()
        obs.register_with_scitex_session()
        script = tmp_path / "s.py"
        script.write_text("pass\n")
        # Act
        empty_registry._fire_session_start_hooks(
            "sid-once", str(script), {"argv": [str(script), "--n", "3"]}
        )
        empty_registry._fire_session_close_hooks("success", 0)
        # Assert
        run = get_db().get_run("sid-once")
        assert (run["status"], json.loads(run["metadata"])["argv"][1:]) == (
            "success",
            ["--n", "3"],
        )


# ---------------------------------------------------------------------------
# (b) never swallowed
# ---------------------------------------------------------------------------


class TestFailuresNeverSwallowed:
    def test_start_failure_is_reraised(self):
        # Arrange — metadata must be JSON-serialisable for the run record
        bad = {"x": object()}
        # Act
        call = lambda: on_session_start("sid-bad", "/tmp/x.py", metadata=bad)
        # Assert
        with pytest.raises(TypeError):
            call()

    def test_start_failure_is_recorded(self):
        # Arrange
        bad = {"x": object()}
        # Act
        try:
            on_session_start("sid-bad1", "/tmp/x.py", metadata=bad)
        except TypeError:
            pass
        # Assert
        assert [f["phase"] for f in HOOK_FAILURES] == ["start"]

    def test_start_failure_warns_without_verbose(self, caplog):
        # Arrange
        bad = {"x": object()}
        # Act
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            try:
                on_session_start("sid-bad2", metadata=bad, verbose=False)
            except TypeError:
                pass
        # Assert
        assert any("INCOMPLETE" in r.getMessage() for r in caplog.records)

    def test_capture_errors_in_payload_are_warned(self, caplog):
        # Arrange
        meta = {"capture_errors": [{"field": "git", "error": "no git"}]}
        # Act
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            on_session_start("sid-cap", "/tmp/x.py", metadata=meta)
        # Assert
        assert any("capture error" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# (e) close payload
# ---------------------------------------------------------------------------

FAILURE = {"phase": "start", "hook": "other", "error": "Boom: x"}


class TestCloseMetadata:
    def test_close_payload_is_merged_into_run(self):
        # Arrange
        on_session_start("sid-close", "/tmp/x.py", metadata={"seed": 1})
        # Act
        on_session_close("success", 0, metadata={"hook_failures": [FAILURE]})
        # Assert
        meta = json.loads(get_db().get_run("sid-close")["metadata"])
        assert (meta["seed"], meta["hook_failures"]) == (1, [FAILURE])

    def test_close_payload_failures_are_warned(self, caplog):
        # Arrange
        on_session_start("sid-close2", "/tmp/x.py")
        # Act
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            on_session_close("success", 0, metadata={"hook_failures": [FAILURE]})
        # Assert
        assert any("hook failure" in r.getMessage() for r in caplog.records)

    def test_adapter_accepts_positional_metadata(self, empty_registry):
        # Arrange
        obs.register_with_scitex_session()
        close = _clew_hooks(empty_registry._SESSION_CLOSE_HOOKS)[0]
        on_session_start("sid-adapt", "/tmp/x.py")
        # Act
        close("failed", 1, {"capture_errors": ["e"]})
        # Assert
        run = get_db().get_run("sid-adapt")
        assert (run["status"], json.loads(run["metadata"])["capture_errors"]) == (
            "failed",
            ["e"],
        )


# ---------------------------------------------------------------------------
# (c) unrecorded outputs under sdir_out
# ---------------------------------------------------------------------------


def _start(tmp_path, sid):
    sdir_out = tmp_path / "script_out"
    sdir_out.mkdir(exist_ok=True)
    meta = {
        "sdir_out": str(sdir_out),
        "sdir_run": str(sdir_out / "RUNNING" / sid),
        "started_at": datetime.now().isoformat(),
    }
    on_session_start(sid, str(tmp_path / "s.py"), metadata=meta)
    return sdir_out, get_tracker()


class TestUnrecordedOutputs:
    def test_unrecorded_output_under_sdir_out_is_reported(self, tmp_path):
        # Arrange
        sdir_out, tracker = _start(tmp_path, "sid-u1")
        (sdir_out / "result.csv").write_text("x\n1\n")
        # Act
        missing = _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert missing == [str((sdir_out / "result.csv").resolve())]

    def test_unrecorded_output_is_warned(self, tmp_path, caplog):
        # Arrange
        sdir_out, tracker = _start(tmp_path, "sid-u1w")
        (sdir_out / "result.csv").write_text("x\n1\n")
        # Act
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert any("NOT recorded" in r.getMessage() for r in caplog.records)

    def test_only_the_unrecorded_sibling_is_flagged(self, tmp_path):
        # Arrange
        sdir_out, tracker = _start(tmp_path, "sid-u2")
        ok = sdir_out / "ok.csv"
        ok.write_text("1")
        tracker.record_output(ok)
        (sdir_out / "sub").mkdir()
        (sdir_out / "sub" / "raw_open.json").write_text("{}")
        # Act
        missing = _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert missing == [str((sdir_out / "sub" / "raw_open.json").resolve())]

    def test_running_and_finished_trees_are_skipped(self, tmp_path):
        # Arrange
        sdir_out, tracker = _start(tmp_path, "sid-u3")
        for tree in ("RUNNING/sid-u3", "FINISHED_SUCCESS/old", "FINISHED/x"):
            d = sdir_out / tree
            d.mkdir(parents=True)
            (d / "stdout.log").write_text("log")
        # Act
        missing = _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert missing == []

    def test_files_older_than_started_at_are_ignored(self, tmp_path):
        # Arrange
        sdir_out = tmp_path / "script_out"
        sdir_out.mkdir()
        old = sdir_out / "previous_run.csv"
        old.write_text("1")
        past = time.time() - 3600
        os.utime(old, (past, past))
        _, tracker = _start(tmp_path, "sid-u4")
        # Act
        missing = _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert missing == []

    def test_inert_without_sdir_out(self):
        # Arrange
        on_session_start("sid-u5", "/tmp/s.py", metadata={"other": "x"})
        # Act
        missing = _warn_if_unrecorded_outputs(get_tracker())
        # Assert
        assert missing == []

    def test_session_close_fires_the_warning(self, tmp_path, caplog):
        # Arrange
        sdir_out, _ = _start(tmp_path, "sid-u6")
        # Written by ANOTHER process: in-process writes are now captured by
        # clew's audit hook (scitex_clew._capture), so an unrecorded output
        # is one this interpreter never opened.
        subprocess.run(
            [sys.executable, "-c", "import sys; open(sys.argv[1], 'w').write('x')",
             str(sdir_out / "result.csv")],
            check=True,
        )
        # Act
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            on_session_close("success", 0)
        # Assert
        assert any("NOT recorded" in r.getMessage() for r in caplog.records)


# EOF
