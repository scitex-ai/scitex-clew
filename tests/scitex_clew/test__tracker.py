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
    def test_basic_construction_tracker_session_id_equals_sess_001(self, tmp_path):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker("sess_001")
        # Act
        # Assert
        # Assert
        # Assert
        assert tracker.session_id == "sess_001"

    def test_basic_construction_tracker_script_path_is_none(self, tmp_path):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker("sess_001")
        # Act
        # Assert
        # Assert
        # Assert
        assert tracker.script_path is None

    def test_basic_construction_tracker_parent_session_is_none(self, tmp_path):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker("sess_001")
        # Act
        # Assert
        # Assert
        # Assert
        assert tracker.parent_session is None

    def test_basic_construction_tracker_finalized_is_false(self, tmp_path):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker("sess_001")
        # Act
        # Assert
        # Assert
        # Assert
        assert tracker._finalized is False


    def test_construction_with_script_path(self, tmp_path):
        # Arrange
        # Arrange
        script = tmp_path / "script.py"
        script.write_text("print('hello')")
        # Act
        # Act
        tracker = SessionTracker("sess_002", script_path=str(script))
        # Assert
        # Assert
        assert tracker._script_hash is not None

    def test_construction_with_nonexistent_script(self):
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker("sess_003", script_path="/nonexistent/script.py")
        # Assert
        # Assert
        assert tracker._script_hash is None

    def test_construction_with_parent_session_tracker_parent_session_equals_parent_session(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        db = _db_module.get_db()
        db.add_run("parent_session", "/path/parent.py")
        # Act
        # Act
        tracker = SessionTracker("sess_004", parent_session="parent_session")
        # Act
        # Assert
        # Assert
        # Assert
        assert tracker.parent_session == "parent_session"

    def test_construction_with_parent_session_parent_session_in_tracker_parent_sessions(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        db = _db_module.get_db()
        db.add_run("parent_session", "/path/parent.py")
        # Act
        # Act
        tracker = SessionTracker("sess_004", parent_session="parent_session")
        # Act
        # Assert
        # Assert
        # Assert
        assert "parent_session" in tracker._parent_sessions


    def test_construction_with_metadata(self):
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker(
            "sess_005", metadata={"notebook": "nb.ipynb", "cell": 3}
        )
        # Assert
        # Assert
        assert tracker.session_id == "sess_005"

    def test_inputs_initially_empty(self):
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker("sess_006")
        # Assert
        # Assert
        assert tracker.inputs == {}

    def test_outputs_initially_empty(self):
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker("sess_007")
        # Assert
        # Assert
        assert tracker.outputs == {}


# ---------------------------------------------------------------------------
# record_input
# ---------------------------------------------------------------------------


class TestRecordInput:
    def test_record_existing_file_result_is_not_none(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b\n1,2")
        tracker = SessionTracker("sess_010")
        # Act
        # Act
        result = tracker.record_input(data_file)
        # Act
        # Assert
        # Assert
        # Assert
        assert result is not None

    def test_record_existing_file_len_result_0(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        data_file = tmp_path / "data.csv"
        data_file.write_text("a,b\n1,2")
        tracker = SessionTracker("sess_010")
        # Act
        # Act
        result = tracker.record_input(data_file)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) > 0


    def test_record_nonexistent_file_returns_none(self, tmp_path):
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_011")
        # Act
        # Act
        result = tracker.record_input(tmp_path / "missing.csv")
        # Assert
        # Assert
        assert result is None

    def test_record_input_track_false_returns_none(self, tmp_path):
        # Arrange
        # Arrange
        data_file = tmp_path / "data.csv"
        data_file.write_text("x")
        tracker = SessionTracker("sess_012")
        # Act
        # Act
        result = tracker.record_input(data_file, track=False)
        # Assert
        # Assert
        assert result is None

    def test_record_input_after_finalize_returns_none(self, tmp_path):
        # Arrange
        # Arrange
        data_file = tmp_path / "data.csv"
        data_file.write_text("x")
        tracker = SessionTracker("sess_013")
        tracker.finalize()
        # Act
        # Act
        result = tracker.record_input(data_file)
        # Assert
        # Assert
        assert result is None

    def test_record_input_stored_in_inputs(self, tmp_path):
        # Arrange
        # Arrange
        data_file = tmp_path / "data.csv"
        data_file.write_text("hello")
        tracker = SessionTracker("sess_014")
        # Act
        # Act
        tracker.record_input(data_file)
        # Assert
        # Assert
        assert len(tracker.inputs) == 1

    def test_record_input_deduplication(self, tmp_path):
        # Arrange
        # Arrange
        data_file = tmp_path / "data.csv"
        data_file.write_text("hello")
        tracker = SessionTracker("sess_015")
        tracker.record_input(data_file)
        # Act
        # Act
        tracker.record_input(data_file)
        # Assert
        # Assert
        assert len(tracker.inputs) == 1

    def test_record_input_auto_links_producer_session(self, tmp_path):
        # Arrange
        # Arrange
        data_file = tmp_path / "shared.csv"
        data_file.write_text("produced data")

        # Producer session
        db = _db_module.get_db()
        db.add_run("producer_sess", "/path/producer.py")
        abs_path = str(data_file.resolve())
        db.add_file_hash("producer_sess", abs_path, "fakehash", "output")

        # Consumer records this file as input
        tracker = SessionTracker("consumer_sess")
        # Act
        # Act
        tracker.record_input(data_file)

        # Parent should be auto-linked
        # Assert
        # Assert
        assert "producer_sess" in tracker._parent_sessions


# ---------------------------------------------------------------------------
# record_output
# ---------------------------------------------------------------------------


class TestRecordOutput:
    def test_record_existing_file(self, tmp_path):
        # Arrange
        # Arrange
        out_file = tmp_path / "result.csv"
        out_file.write_text("result")
        tracker = SessionTracker("sess_020")
        # Act
        # Act
        result = tracker.record_output(out_file)
        # Assert
        # Assert
        assert result is not None

    def test_record_nonexistent_file_returns_none(self, tmp_path):
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_021")
        # Act
        # Act
        result = tracker.record_output(tmp_path / "missing_out.csv")
        # Assert
        # Assert
        assert result is None

    def test_record_output_track_false_returns_none(self, tmp_path):
        # Arrange
        # Arrange
        out_file = tmp_path / "result.csv"
        out_file.write_text("result")
        tracker = SessionTracker("sess_022")
        # Act
        # Act
        result = tracker.record_output(out_file, track=False)
        # Assert
        # Assert
        assert result is None

    def test_record_output_after_finalize_returns_none(self, tmp_path):
        # Arrange
        # Arrange
        out_file = tmp_path / "result.csv"
        out_file.write_text("result")
        tracker = SessionTracker("sess_023")
        tracker.finalize()
        # Act
        # Act
        result = tracker.record_output(out_file)
        # Assert
        # Assert
        assert result is None

    def test_record_output_stored_in_outputs(self, tmp_path):
        # Arrange
        # Arrange
        out_file = tmp_path / "result.csv"
        out_file.write_text("result data")
        tracker = SessionTracker("sess_024")
        # Act
        # Act
        tracker.record_output(out_file)
        # Assert
        # Assert
        assert len(tracker.outputs) == 1


# ---------------------------------------------------------------------------
# record_inputs / record_outputs (batch)
# ---------------------------------------------------------------------------


class TestBatchRecording:
    def test_record_inputs_multiple(self, tmp_path):
        # Arrange
        # Arrange
        files = []
        for i in range(3):
            f = tmp_path / f"input_{i}.csv"
            f.write_text(f"data{i}")
            files.append(f)

        tracker = SessionTracker("sess_030")
        # Act
        # Act
        result = tracker.record_inputs(files)
        # Assert
        # Assert
        assert len(result) == 3

    def test_record_outputs_multiple(self, tmp_path):
        # Arrange
        # Arrange
        files = []
        for i in range(2):
            f = tmp_path / f"output_{i}.csv"
            f.write_text(f"out{i}")
            files.append(f)

        tracker = SessionTracker("sess_031")
        # Act
        # Act
        result = tracker.record_outputs(files)
        # Assert
        # Assert
        assert len(result) == 2

    def test_record_inputs_skips_missing(self, tmp_path):
        # Arrange
        # Arrange
        existing = tmp_path / "exists.csv"
        existing.write_text("data")
        missing = tmp_path / "missing.csv"

        tracker = SessionTracker("sess_032")
        # Act
        # Act
        result = tracker.record_inputs([existing, missing])
        # Assert
        # Assert
        assert len(result) == 1


# ---------------------------------------------------------------------------
# combined_hash
# ---------------------------------------------------------------------------


class TestCombinedHash:
    def test_combined_hash_returns_string_h_is_str(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_040")
        # Act
        # Act
        h = tracker.combined_hash
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(h, str)

    def test_combined_hash_returns_string_len_h_0(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_040")
        # Act
        # Act
        h = tracker.combined_hash
        # Act
        # Assert
        # Assert
        # Assert
        assert len(h) > 0


    def test_combined_hash_changes_with_inputs(self, tmp_path):
        # Arrange
        # Arrange
        f = tmp_path / "f.csv"
        f.write_text("content")

        tracker1 = SessionTracker("sess_041")
        h1 = tracker1.combined_hash

        tracker2 = SessionTracker("sess_042")
        tracker2.record_input(f)
        # Act
        # Act
        h2 = tracker2.combined_hash

        # Assert
        # Assert
        assert h1 != h2

    def test_combined_hash_with_script(self, tmp_path):
        # Arrange
        # Arrange
        script = tmp_path / "run.py"
        script.write_text("print('hello')")
        tracker = SessionTracker("sess_043", script_path=str(script))
        # Act
        # Act
        h = tracker.combined_hash
        # Assert
        # Assert
        assert isinstance(h, str)


# ---------------------------------------------------------------------------
# finalize
# ---------------------------------------------------------------------------


class TestFinalize:
    def test_finalize_marks_finalized_not_tracker_finalized(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker("sess_050")
        # Act
        # Assert
        # Assert
        # Assert
        assert not tracker._finalized

    def test_finalize_marks_finalized_tracker_finalized_not_tracker_finalized(self):
        # Arrange
        # Arrange
        # Act
        tracker = SessionTracker("sess_050")
        # Act
        # Assert
        # Assert
        assert not tracker._finalized

    def test_finalize_marks_finalized_tracker_finalized_tracker_finalized(self):
        # Arrange
        tracker = SessionTracker("sess_050")
        # Act
        tracker.finalize()
        # Assert
        assert tracker._finalized



    def test_finalize_returns_summary_summary_is_dict(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_051")
        # Act
        # Act
        summary = tracker.finalize()
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(summary, dict)

    def test_finalize_returns_summary_session_id_in_summary(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_051")
        # Act
        # Act
        summary = tracker.finalize()
        # Act
        # Assert
        # Assert
        # Assert
        assert "session_id" in summary


    def test_finalize_twice_returns_same_summary(self):
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_052")
        s1 = tracker.finalize()
        # Act
        # Act
        s2 = tracker.finalize()
        # Assert
        # Assert
        assert s1["session_id"] == s2["session_id"]

    def test_finalize_with_status(self):
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_053")
        # Act
        # Act
        summary = tracker.finalize(status="failed", exit_code=1)
        # Assert
        # Assert
        assert summary["session_id"] == "sess_053"

    def test_finalize_updates_database_run_is_not_none(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_054")
        tracker.finalize(status="success")
        db = _db_module.get_db()
        # Act
        # Act
        run = db.get_run("sess_054")
        # Act
        # Assert
        # Assert
        # Assert
        assert run is not None

    def test_finalize_updates_database_run_status_success(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_054")
        tracker.finalize(status="success")
        db = _db_module.get_db()
        # Act
        # Act
        run = db.get_run("sess_054")
        # Act
        # Assert
        # Assert
        # Assert
        assert run["status"] == "success"



# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_structure_session_id_in_s(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_060")
        # Act
        # Act
        s = tracker.summary()
        # Act
        # Assert
        # Assert
        # Assert
        assert "session_id" in s

    def test_summary_structure_script_path_in_s(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_060")
        # Act
        # Act
        s = tracker.summary()
        # Act
        # Assert
        # Assert
        # Assert
        assert "script_path" in s

    def test_summary_structure_script_hash_in_s(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_060")
        # Act
        # Act
        s = tracker.summary()
        # Act
        # Assert
        # Assert
        # Assert
        assert "script_hash" in s

    def test_summary_structure_parent_session_in_s(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_060")
        # Act
        # Act
        s = tracker.summary()
        # Act
        # Assert
        # Assert
        # Assert
        assert "parent_session" in s

    def test_summary_structure_inputs_in_s(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_060")
        # Act
        # Act
        s = tracker.summary()
        # Act
        # Assert
        # Assert
        # Assert
        assert "inputs" in s

    def test_summary_structure_outputs_in_s(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_060")
        # Act
        # Act
        s = tracker.summary()
        # Act
        # Assert
        # Assert
        # Assert
        assert "outputs" in s

    def test_summary_structure_combined_hash_in_s(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_060")
        # Act
        # Act
        s = tracker.summary()
        # Act
        # Assert
        # Assert
        # Assert
        assert "combined_hash" in s

    def test_summary_structure_finalized_in_s(self):
        # Arrange
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_060")
        # Act
        # Act
        s = tracker.summary()
        # Act
        # Assert
        # Assert
        # Assert
        assert "finalized" in s


    def test_summary_finalized_flag_not_tracker_summary_finalized(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = SessionTracker("sess_061")
        # Act
        # Assert
        # Assert
        # Assert
        assert not tracker.summary()["finalized"]

    def test_summary_finalized_flag_tracker_summary_finalized_not_tracker_summary_finalized(self):
        # Arrange
        # Arrange
        # Act
        tracker = SessionTracker("sess_061")
        # Act
        # Assert
        # Assert
        assert not tracker.summary()["finalized"]

    def test_summary_finalized_flag_tracker_summary_finalized_tracker_summary_finalized(self):
        # Arrange
        tracker = SessionTracker("sess_061")
        # Act
        tracker.finalize()
        # Assert
        assert tracker.summary()["finalized"]




# ---------------------------------------------------------------------------
# get_tracker / set_tracker
# ---------------------------------------------------------------------------


class TestGetSetTracker:
    def test_get_tracker_initially_none(self):
        # Arrange
        # Act
        # Arrange
        # Act
        set_tracker(None)
        # Assert
        # Assert
        assert get_tracker() is None

    def test_set_and_get_tracker(self):
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_070")
        # Act
        # Act
        set_tracker(tracker)
        # Assert
        # Assert
        assert get_tracker() is tracker

    def test_set_tracker_none(self):
        # Arrange
        # Arrange
        tracker = SessionTracker("sess_071")
        set_tracker(tracker)
        # Act
        # Act
        set_tracker(None)
        # Assert
        # Assert
        assert get_tracker() is None


# ---------------------------------------------------------------------------
# start_tracking / stop_tracking
# ---------------------------------------------------------------------------


class TestStartStopTracking:
    def test_start_tracking_returns_tracker_tracker_is_sessiontracker(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = start_tracking("sess_080")
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(tracker, SessionTracker)

    def test_start_tracking_returns_tracker_tracker_session_id_equals_sess_080(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = start_tracking("sess_080")
        # Act
        # Assert
        # Assert
        # Assert
        assert tracker.session_id == "sess_080"


    def test_start_tracking_sets_global(self):
        # Arrange
        # Act
        # Arrange
        # Act
        tracker = start_tracking("sess_081")
        # Assert
        # Assert
        assert get_tracker() is tracker

    def test_stop_tracking_returns_summary_result_is_not_none(self):
        # Arrange
        # Arrange
        # Arrange
        start_tracking("sess_082")
        # Act
        # Act
        result = stop_tracking()
        # Act
        # Assert
        # Assert
        # Assert
        assert result is not None

    def test_stop_tracking_returns_summary_session_id_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        start_tracking("sess_082")
        # Act
        # Act
        result = stop_tracking()
        # Act
        # Assert
        # Assert
        # Assert
        assert "session_id" in result


    def test_stop_tracking_clears_global(self):
        # Arrange
        # Arrange
        start_tracking("sess_083")
        # Act
        # Act
        stop_tracking()
        # Assert
        # Assert
        assert get_tracker() is None

    def test_stop_tracking_with_no_tracker_returns_none(self):
        # Arrange
        # Arrange
        set_tracker(None)
        # Act
        # Act
        result = stop_tracking()
        # Assert
        # Assert
        assert result is None

    def test_stop_tracking_with_status(self):
        # Arrange
        # Arrange
        start_tracking("sess_084")
        # Act
        # Act
        result = stop_tracking(status="failed", exit_code=1)
        # Assert
        # Assert
        assert result is not None

    def test_start_tracking_with_parent(self):
        # Arrange
        # Arrange
        db = _db_module.get_db()
        db.add_run("parent_track_sess", "/path/parent.py")
        # Act
        # Act
        tracker = start_tracking("sess_085", parent_session="parent_track_sess")
        # Assert
        # Assert
        assert tracker.parent_session == "parent_track_sess"


# EOF
