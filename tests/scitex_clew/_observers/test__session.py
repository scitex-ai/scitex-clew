#!/usr/bin/env python3
"""Tests for scitex_clew._observers._session lifecycle hooks (on_session_start/close)."""

from __future__ import annotations

import logging

import pytest

import scitex_clew
import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._observers._session import (
    _warn_if_unrecorded_outputs,
    on_session_close,
    on_session_start,
)
from scitex_clew._tracker import get_tracker, set_tracker


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Inject a fresh temp clew.db and reset global state after each test."""
    db_path = tmp_path / "clew.db"
    set_db(db_path)
    yield
    _db_module._DB_INSTANCE = None
    set_tracker(None)


# ---------------------------------------------------------------------------
# Public API exposure
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_on_session_start_exposed_at_top_level(self):
        # Arrange
        expected = on_session_start
        # Act
        actual = scitex_clew.on_session_start
        # Assert
        assert actual is expected

    def test_on_session_close_exposed_at_top_level(self):
        # Arrange
        expected = on_session_close
        # Act
        actual = scitex_clew.on_session_close
        # Assert
        assert actual is expected

    def test_on_session_start_in_all(self):
        # Arrange
        names = scitex_clew.__all__
        # Act
        present = "on_session_start" in names
        # Assert
        assert present

    def test_on_session_close_in_all(self):
        # Arrange
        names = scitex_clew.__all__
        # Act
        present = "on_session_close" in names
        # Assert
        assert present


# ---------------------------------------------------------------------------
# on_session_start
# ---------------------------------------------------------------------------


class TestOnSessionStart:
    def test_start_opens_tracker(self):
        # Arrange
        set_tracker(None)
        # Act
        on_session_start("sess_hook_001")
        # Assert
        assert get_tracker() is not None

    def test_start_sets_session_id(self):
        # Arrange
        set_tracker(None)
        # Act
        on_session_start("sess_hook_002")
        # Assert
        assert get_tracker().session_id == "sess_hook_002"

    def test_start_opens_run_record_in_db(self):
        # Arrange
        db = _db_module.get_db()
        # Act
        on_session_start("sess_hook_003")
        # Assert
        assert db.get_run("sess_hook_003") is not None

    def test_start_with_script_path_hashes_script(self, tmp_path):
        # Arrange
        script = tmp_path / "run.py"
        script.write_text("print('hello')")
        # Act
        on_session_start("sess_hook_004", script_path=str(script))
        # Assert
        assert get_tracker()._script_hash is not None

    def test_start_does_not_raise_on_normal_args(self):
        # Arrange
        set_tracker(None)
        # Act
        on_session_start("sess_hook_005")
        # Assert
        assert get_tracker().session_id == "sess_hook_005"


# ---------------------------------------------------------------------------
# on_session_close
# ---------------------------------------------------------------------------


class TestOnSessionClose:
    def test_close_clears_tracker(self):
        # Arrange
        on_session_start("sess_hook_010")
        # Act
        on_session_close()
        # Assert
        assert get_tracker() is None

    def test_close_finalizes_run_status(self):
        # Arrange
        on_session_start("sess_hook_011")
        # Act
        on_session_close(status="success")
        # Assert
        assert _db_module.get_db().get_run("sess_hook_011")["status"] == "success"

    def test_close_computes_combined_hash(self):
        # Arrange
        on_session_start("sess_hook_012")
        # Act
        on_session_close()
        # Assert
        assert _db_module.get_db().get_run("sess_hook_012")["combined_hash"]

    def test_close_propagates_status(self):
        # Arrange
        on_session_start("sess_hook_013")
        # Act
        on_session_close(status="failed", exit_code=1)
        # Assert
        assert _db_module.get_db().get_run("sess_hook_013")["status"] == "failed"

    def test_close_with_no_active_session_is_noop(self):
        # Arrange
        set_tracker(None)
        # Act
        on_session_close()
        # Assert
        assert get_tracker() is None


# ---------------------------------------------------------------------------
# start → record → close round trip
# ---------------------------------------------------------------------------


class TestStartCloseRoundTrip:
    def test_full_lifecycle_finalizes_with_success_status(self, tmp_path):
        # Arrange
        data = tmp_path / "data.csv"
        data.write_text("a,b\n1,2")
        out = tmp_path / "result.csv"
        out.write_text("done")
        # Act
        on_session_start("sess_hook_020")
        tracker = get_tracker()
        tracker.record_input(data)
        tracker.record_output(out)
        on_session_close(status="success")
        # Assert
        assert _db_module.get_db().get_run("sess_hook_020")["status"] == "success"

    def test_full_lifecycle_finalizes_with_combined_hash(self, tmp_path):
        # Arrange
        data = tmp_path / "data.csv"
        data.write_text("a,b\n1,2")
        out = tmp_path / "result.csv"
        out.write_text("done")
        # Act
        on_session_start("sess_hook_021")
        tracker = get_tracker()
        tracker.record_input(data)
        tracker.record_output(out)
        on_session_close(status="success")
        # Assert
        assert _db_module.get_db().get_run("sess_hook_021")["combined_hash"]

    def test_combined_hash_reflects_recorded_files(self, tmp_path):
        # Arrange
        data = tmp_path / "data.csv"
        data.write_text("payload")
        on_session_start("sess_hook_022")
        get_tracker().record_input(data)
        on_session_close()
        on_session_start("sess_hook_023")
        on_session_close()
        db = _db_module.get_db()
        # Act
        h_with = db.get_run("sess_hook_022")["combined_hash"]
        h_without = db.get_run("sess_hook_023")["combined_hash"]
        # Assert
        assert h_with != h_without


# ---------------------------------------------------------------------------
# Session-close provenance-completeness WARN (#45)
# ---------------------------------------------------------------------------


class TestUnrecordedOutputsWarn:
    """`_warn_if_unrecorded_outputs`: WARN iff outputs written AND none recorded."""

    def test_warns_when_outputs_written_but_none_recorded(self, tmp_path, caplog):
        # Arrange — output_dir has a file; nothing recorded (the #44 gap).
        outdir = tmp_path / "script_out" / "RUNNING" / "sess-warn-1"
        outdir.mkdir(parents=True)
        (outdir / "result.csv").write_text("x\n1\n")
        on_session_start(
            "sess-warn-1", "/tmp/s.py", metadata={"output_dir": str(outdir)}
        )
        tracker = get_tracker()
        # Act
        with caplog.at_level(logging.WARNING, logger="scitex_clew._observers._session"):
            _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert any("recorded ZERO provenance" in r.getMessage() for r in caplog.records)

    def test_silent_when_output_dir_empty(self, tmp_path, caplog):
        # Arrange — output_dir exists but holds no files.
        outdir = tmp_path / "script_out" / "RUNNING" / "sess-warn-2"
        outdir.mkdir(parents=True)
        on_session_start(
            "sess-warn-2", "/tmp/s.py", metadata={"output_dir": str(outdir)}
        )
        tracker = get_tracker()
        # Act
        with caplog.at_level(logging.WARNING, logger="scitex_clew._observers._session"):
            _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert not any(
            "recorded ZERO provenance" in r.getMessage() for r in caplog.records
        )

    def test_silent_when_no_output_dir_signal(self, tmp_path, caplog):
        # Arrange — no output_dir in metadata (pre-enabler scitex-session).
        on_session_start("sess-warn-3", "/tmp/s.py", metadata={"other": "x"})
        tracker = get_tracker()
        # Act
        with caplog.at_level(logging.WARNING, logger="scitex_clew._observers._session"):
            _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert not any(
            "recorded ZERO provenance" in r.getMessage() for r in caplog.records
        )

    def test_silent_when_outputs_were_recorded(self, tmp_path, caplog):
        # Arrange — the output IS recorded (tracker._outputs non-empty).
        outdir = tmp_path / "script_out" / "RUNNING" / "sess-warn-4"
        outdir.mkdir(parents=True)
        f = outdir / "result.csv"
        f.write_text("x\n1\n")
        on_session_start(
            "sess-warn-4", "/tmp/s.py", metadata={"output_dir": str(outdir)}
        )
        tracker = get_tracker()
        tracker.record_output(f)
        # Act
        with caplog.at_level(logging.WARNING, logger="scitex_clew._observers._session"):
            _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert not any(
            "recorded ZERO provenance" in r.getMessage() for r in caplog.records
        )

    def test_warns_when_dir_moved_to_status_subdir(self, tmp_path, caplog):
        # Arrange — start metadata points at RUNNING/, but the dir "moved" to
        # FINISHED/ by close; the glob-fallback must still find the files.
        running = tmp_path / "script_out" / "RUNNING" / "sess-warn-5"
        moved = tmp_path / "script_out" / "FINISHED" / "sess-warn-5"
        moved.mkdir(parents=True)
        (moved / "result.csv").write_text("x\n1\n")
        on_session_start(
            "sess-warn-5", "/tmp/s.py", metadata={"output_dir": str(running)}
        )
        tracker = get_tracker()
        # Act
        with caplog.at_level(logging.WARNING, logger="scitex_clew._observers._session"):
            _warn_if_unrecorded_outputs(tracker)
        # Assert
        assert any("recorded ZERO provenance" in r.getMessage() for r in caplog.records)


# EOF
