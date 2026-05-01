#!/usr/bin/env python3
"""Tests for scitex_clew._tracker module."""

from __future__ import annotations

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db
from scitex_clew._tracker import (
    SessionTracker,
    get_tracker,
    set_tracker,
    start_tracking,
    stop_tracking,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Inject a fresh temp DB and reset global state after each test."""
    db_path = tmp_path / "tracker_test.db"
    set_db(db_path)
    yield
    _db_module._DB_INSTANCE = None
    set_tracker(None)


# ---------------------------------------------------------------------------
# SessionTracker construction
# ---------------------------------------------------------------------------


class TestSessionTrackerInit:
    def test_basic_construction(self, tmp_path):
        tracker = SessionTracker("sess_001")
        assert tracker.session_id == "sess_001"
        assert tracker.script_path is None
        assert tracker.parent_session is None
        assert tracker._finalized is False

    def test_construction_with_script_path(self, tmp_path):
        script = tmp_path / "script.py"
        script.write_text("print('hello')")
        tracker = SessionTracker("sess_002", script_path=str(script))
        assert tracker._script_hash is not None

    def test_construction_with_nonexistent_script(self):
        tracker = SessionTracker("sess_003", script_path="/nonexistent/script.py")
        assert tracker._script_hash is None

    def test_construction_with_parent_session(self, tmp_path):
        db = _db_module.get_db()
        db.add_run("parent_session", "/path/parent.py")
        tracker = SessionTracker("sess_004", parent_session="parent_session")
        assert tracker.parent_session == "parent_session"
        assert "parent_session" in tracker._parent_sessions

    def test_construction_with_metadata(self):
        tracker = SessionTracker(
            "sess_005", metadata={"notebook": "nb.ipynb", "cell": 3}
        )
        assert tracker.session_id == "sess_005"

    def test_inputs_initially_empty(self):
        tracker = SessionTracker("sess_006")
        assert tracker.inputs == {}

    def test_outputs_initially_empty(self):
        tracker = SessionTracker("sess_007")
        assert tracker.outputs == {}


# ---------------------------------------------------------------------------
# record_input
# ---------------------------------------------------------------------------


class TestRecordInput:
    def test_record_existing_file(self, tmp_path):
        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b\n1,2")
        tracker = SessionTracker("sess_010")
        result = tracker.record_input(data_file)
        assert result is not None
        assert len(result) > 0

    def test_record_nonexistent_file_returns_none(self, tmp_path):
        tracker = SessionTracker("sess_011")
        result = tracker.record_input(tmp_path / "missing.csv")
        assert result is None

    def test_record_input_track_false_returns_none(self, tmp_path):
        data_file = tmp_path / "data.csv"
        data_file.write_text("x")
        tracker = SessionTracker("sess_012")
        result = tracker.record_input(data_file, track=False)
        assert result is None

    def test_record_input_after_finalize_returns_none(self, tmp_path):
        data_file = tmp_path / "data.csv"
        data_file.write_text("x")
        tracker = SessionTracker("sess_013")
        tracker.finalize()
        result = tracker.record_input(data_file)
        assert result is None

    def test_record_input_stored_in_inputs(self, tmp_path):
        data_file = tmp_path / "data.csv"
        data_file.write_text("hello")
        tracker = SessionTracker("sess_014")
        tracker.record_input(data_file)
        assert len(tracker.inputs) == 1

    def test_record_input_deduplication(self, tmp_path):
        data_file = tmp_path / "data.csv"
        data_file.write_text("hello")
        tracker = SessionTracker("sess_015")
        tracker.record_input(data_file)
        tracker.record_input(data_file)
        assert len(tracker.inputs) == 1

    def test_record_input_auto_links_producer_session(self, tmp_path):
        data_file = tmp_path / "shared.csv"
        data_file.write_text("produced data")

        # Producer session
        db = _db_module.get_db()
        db.add_run("producer_sess", "/path/producer.py")
        abs_path = str(data_file.resolve())
        db.add_file_hash("producer_sess", abs_path, "fakehash", "output")

        # Consumer records this file as input
        tracker = SessionTracker("consumer_sess")
        tracker.record_input(data_file)

        # Parent should be auto-linked
        assert "producer_sess" in tracker._parent_sessions


# ---------------------------------------------------------------------------
# record_output
# ---------------------------------------------------------------------------


class TestRecordOutput:
    def test_record_existing_file(self, tmp_path):
        out_file = tmp_path / "result.csv"
        out_file.write_text("result")
        tracker = SessionTracker("sess_020")
        result = tracker.record_output(out_file)
        assert result is not None

    def test_record_nonexistent_file_returns_none(self, tmp_path):
        tracker = SessionTracker("sess_021")
        result = tracker.record_output(tmp_path / "missing_out.csv")
        assert result is None

    def test_record_output_track_false_returns_none(self, tmp_path):
        out_file = tmp_path / "result.csv"
        out_file.write_text("result")
        tracker = SessionTracker("sess_022")
        result = tracker.record_output(out_file, track=False)
        assert result is None

    def test_record_output_after_finalize_returns_none(self, tmp_path):
        out_file = tmp_path / "result.csv"
        out_file.write_text("result")
        tracker = SessionTracker("sess_023")
        tracker.finalize()
        result = tracker.record_output(out_file)
        assert result is None

    def test_record_output_stored_in_outputs(self, tmp_path):
        out_file = tmp_path / "result.csv"
        out_file.write_text("result data")
        tracker = SessionTracker("sess_024")
        tracker.record_output(out_file)
        assert len(tracker.outputs) == 1


# ---------------------------------------------------------------------------
# record_inputs / record_outputs (batch)
# ---------------------------------------------------------------------------


class TestBatchRecording:
    def test_record_inputs_multiple(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"input_{i}.csv"
            f.write_text(f"data{i}")
            files.append(f)

        tracker = SessionTracker("sess_030")
        result = tracker.record_inputs(files)
        assert len(result) == 3

    def test_record_outputs_multiple(self, tmp_path):
        files = []
        for i in range(2):
            f = tmp_path / f"output_{i}.csv"
            f.write_text(f"out{i}")
            files.append(f)

        tracker = SessionTracker("sess_031")
        result = tracker.record_outputs(files)
        assert len(result) == 2

    def test_record_inputs_skips_missing(self, tmp_path):
        existing = tmp_path / "exists.csv"
        existing.write_text("data")
        missing = tmp_path / "missing.csv"

        tracker = SessionTracker("sess_032")
        result = tracker.record_inputs([existing, missing])
        assert len(result) == 1


# ---------------------------------------------------------------------------
# combined_hash
# ---------------------------------------------------------------------------


class TestCombinedHash:
    def test_combined_hash_returns_string(self, tmp_path):
        tracker = SessionTracker("sess_040")
        h = tracker.combined_hash
        assert isinstance(h, str)
        assert len(h) > 0

    def test_combined_hash_changes_with_inputs(self, tmp_path):
        f = tmp_path / "f.csv"
        f.write_text("content")

        tracker1 = SessionTracker("sess_041")
        h1 = tracker1.combined_hash

        tracker2 = SessionTracker("sess_042")
        tracker2.record_input(f)
        h2 = tracker2.combined_hash

        assert h1 != h2

    def test_combined_hash_with_script(self, tmp_path):
        script = tmp_path / "run.py"
        script.write_text("print('hello')")
        tracker = SessionTracker("sess_043", script_path=str(script))
        h = tracker.combined_hash
        assert isinstance(h, str)


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------


class TestFinalize:
    def test_finalize_marks_finalized(self):
        tracker = SessionTracker("sess_050")
        assert not tracker._finalized
        tracker.finalize()
        assert tracker._finalized

    def test_finalize_returns_summary(self):
        tracker = SessionTracker("sess_051")
        summary = tracker.finalize()
        assert isinstance(summary, dict)
        assert "session_id" in summary

    def test_finalize_twice_returns_same_summary(self):
        tracker = SessionTracker("sess_052")
        s1 = tracker.finalize()
        s2 = tracker.finalize()
        assert s1["session_id"] == s2["session_id"]

    def test_finalize_with_status(self):
        tracker = SessionTracker("sess_053")
        summary = tracker.finalize(status="failed", exit_code=1)
        assert summary["session_id"] == "sess_053"

    def test_finalize_updates_database(self):
        tracker = SessionTracker("sess_054")
        tracker.finalize(status="success")
        db = _db_module.get_db()
        run = db.get_run("sess_054")
        assert run is not None
        assert run["status"] == "success"


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_structure(self):
        tracker = SessionTracker("sess_060")
        s = tracker.summary()
        assert "session_id" in s
        assert "script_path" in s
        assert "script_hash" in s
        assert "parent_session" in s
        assert "inputs" in s
        assert "outputs" in s
        assert "combined_hash" in s
        assert "finalized" in s

    def test_summary_finalized_flag(self):
        tracker = SessionTracker("sess_061")
        assert not tracker.summary()["finalized"]
        tracker.finalize()
        assert tracker.summary()["finalized"]


# ---------------------------------------------------------------------------
# get_tracker / set_tracker
# ---------------------------------------------------------------------------


class TestGetSetTracker:
    def test_get_tracker_initially_none(self):
        set_tracker(None)
        assert get_tracker() is None

    def test_set_and_get_tracker(self):
        tracker = SessionTracker("sess_070")
        set_tracker(tracker)
        assert get_tracker() is tracker

    def test_set_tracker_none(self):
        tracker = SessionTracker("sess_071")
        set_tracker(tracker)
        set_tracker(None)
        assert get_tracker() is None


# ---------------------------------------------------------------------------
# start_tracking / stop_tracking
# ---------------------------------------------------------------------------


class TestStartStopTracking:
    def test_start_tracking_returns_tracker(self):
        tracker = start_tracking("sess_080")
        assert isinstance(tracker, SessionTracker)
        assert tracker.session_id == "sess_080"

    def test_start_tracking_sets_global(self):
        tracker = start_tracking("sess_081")
        assert get_tracker() is tracker

    def test_stop_tracking_returns_summary(self):
        start_tracking("sess_082")
        result = stop_tracking()
        assert result is not None
        assert "session_id" in result

    def test_stop_tracking_clears_global(self):
        start_tracking("sess_083")
        stop_tracking()
        assert get_tracker() is None

    def test_stop_tracking_with_no_tracker_returns_none(self):
        set_tracker(None)
        result = stop_tracking()
        assert result is None

    def test_stop_tracking_with_status(self):
        start_tracking("sess_084")
        result = stop_tracking(status="failed", exit_code=1)
        assert result is not None

    def test_start_tracking_with_parent(self):
        db = _db_module.get_db()
        db.add_run("parent_track_sess", "/path/parent.py")
        tracker = start_tracking("sess_085", parent_session="parent_track_sess")
        assert tracker.parent_session == "parent_track_sess"


# EOF
