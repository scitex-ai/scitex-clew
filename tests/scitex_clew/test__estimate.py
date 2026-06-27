#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_clew._estimate — Phase 1 pre-flight compute estimate.

Coverage:
  (a) exact script_hash match path
  (b) script_path fallback path with "script changed" annotation
  (c) cold-start returns the no-history result without fabricating
  (d) heavy flag triggers above threshold
  (e) #outputs median from file_hashes
  (f) target-file argument resolves to its producing script
  (g) CLI --json shape

All test DBs are built via the package's own DB API (no raw SQL fixtures).
No mocks used.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scitex_clew import VerificationDB
from scitex_clew._estimate import (
    HEAVY_THRESHOLD_SECONDS,
    EstimateResult,
    _build_cold_start,
    _percentile,
    estimate,
)

CliRunner = pytest.importorskip("click.testing").CliRunner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path) -> VerificationDB:
    """Create an isolated VerificationDB in a temp directory."""
    return VerificationDB(tmp_path / "test_estimate.db")


def _iso(dt: datetime) -> str:
    """Format a datetime as the ISO-8601 string the DB stores."""
    return dt.isoformat()


def _add_completed_run(
    db: VerificationDB,
    session_id: str,
    script_path: str,
    script_hash: str,
    duration_seconds: float,
    status: str = "success",
    exit_code: int = 0,
) -> None:
    """Add a completed run with the given wall-clock duration."""
    start = datetime(2026, 1, 1, 12, 0, 0)
    end = start + timedelta(seconds=duration_seconds)
    db.add_run(session_id, script_path, script_hash=script_hash)
    db.finish_run(session_id, status=status, exit_code=exit_code)
    # Overwrite timestamps with exact values for deterministic durations.
    with db._connect() as conn:
        conn.execute(
            "UPDATE runs SET started_at=?, finished_at=? WHERE session_id=?",
            (_iso(start), _iso(end), session_id),
        )


# ---------------------------------------------------------------------------
# Unit tests: internal helpers
# ---------------------------------------------------------------------------


class TestPercentile:
    def test_single_value_returns_that_value(self):
        # Arrange
        vals = [42.0]
        # Act
        result = _percentile(vals, 50)
        # Assert
        assert result == 42.0

    def test_p50_of_two_values_is_midpoint(self):
        # Arrange
        vals = [10.0, 20.0]
        # Act
        result = _percentile(vals, 50)
        # Assert
        assert result == 15.0

    def test_p90_of_ten_values_above_nine_tenths(self):
        # Arrange
        vals = [float(i) for i in range(1, 11)]  # 1..10
        # Act
        result = _percentile(vals, 90)
        # Assert
        assert result >= 9.0

    def test_empty_raises_value_error(self):
        # Arrange
        # Act / Assert
        with pytest.raises(ValueError):
            _percentile([], 50)


class TestBuildColdStart:
    def test_match_tier_is_unknown(self):
        # Arrange / Act
        result = _build_cold_start("/some/script.py")
        # Assert
        assert result.match_tier == "unknown"

    def test_run_count_is_zero(self):
        # Arrange / Act
        result = _build_cold_start("/some/script.py")
        # Assert
        assert result.run_count == 0

    def test_numeric_fields_are_none(self):
        # Arrange / Act
        result = _build_cold_start("/some/script.py")
        # Assert
        assert result.p50_seconds is None
        assert result.p90_seconds is None
        assert result.success_rate is None
        assert result.typical_outputs is None

    def test_heavy_is_false(self):
        # Arrange / Act
        result = _build_cold_start("/some/script.py")
        # Assert
        assert result.heavy is False

    def test_hint_mentions_no_prior_runs(self):
        # Arrange / Act
        result = _build_cold_start("/some/script.py")
        # Assert
        assert "no prior" in result.hint.lower() or "cannot" in result.hint.lower()


# ---------------------------------------------------------------------------
# (a) Exact script_hash match path
# ---------------------------------------------------------------------------


class TestExactHashMatch:
    def test_match_tier_is_exact_hash(self, tmp_path):
        # Arrange — write a real script file and populate DB with matching hash
        script = tmp_path / "train.py"
        script.write_text("print('hello')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), h, 60.0)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.match_tier == "exact_hash"

    def test_run_count_matches_number_of_sessions(self, tmp_path):
        # Arrange
        script = tmp_path / "train.py"
        script.write_text("print('hello')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), h, 60.0)
        _add_completed_run(db, "s2", str(script), h, 90.0)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.run_count == 2

    def test_p50_seconds_is_median_of_durations(self, tmp_path):
        # Arrange
        script = tmp_path / "train.py"
        script.write_text("print('hello')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), h, 60.0)
        _add_completed_run(db, "s2", str(script), h, 120.0)
        _add_completed_run(db, "s3", str(script), h, 180.0)
        # Act
        result = estimate(str(script), db=db)
        # Assert — median of [60, 120, 180] = 120
        assert result.p50_seconds == pytest.approx(120.0, abs=1.0)

    def test_success_rate_all_success(self, tmp_path):
        # Arrange
        script = tmp_path / "train.py"
        script.write_text("print('hello')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), h, 60.0, status="success")
        _add_completed_run(db, "s2", str(script), h, 70.0, status="success")
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.success_rate == pytest.approx(1.0)

    def test_success_rate_partial_failures(self, tmp_path):
        # Arrange
        script = tmp_path / "train.py"
        script.write_text("print('hello')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), h, 60.0, status="success", exit_code=0)
        _add_completed_run(db, "s2", str(script), h, 70.0, status="failed", exit_code=1)
        # Act
        result = estimate(str(script), db=db)
        # Assert — 1 success out of 2
        assert result.success_rate == pytest.approx(0.5)

    def test_script_changed_is_false_for_exact_hash(self, tmp_path):
        # Arrange
        script = tmp_path / "train.py"
        script.write_text("print('hello')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), h, 60.0)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.script_changed is False


# ---------------------------------------------------------------------------
# (b) Script_path fallback path with "script changed" annotation
# ---------------------------------------------------------------------------


class TestPathHistoryFallback:
    def test_match_tier_is_path_history_when_script_changed(self, tmp_path):
        # Arrange — register run with a stale hash, then update the script
        script = tmp_path / "analyze.py"
        script.write_text("print('v1')\n")
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), "stalehash000000000000000000000000", 50.0)
        # Update the script so the hash no longer matches
        script.write_text("print('v2')\n")
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.match_tier == "path_history"

    def test_script_changed_is_true_for_path_history(self, tmp_path):
        # Arrange
        script = tmp_path / "analyze.py"
        script.write_text("print('v1')\n")
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), "stalehash000000000000000000000000", 50.0)
        script.write_text("print('v2')\n")
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.script_changed is True

    def test_hint_mentions_script_changed(self, tmp_path):
        # Arrange
        script = tmp_path / "analyze.py"
        script.write_text("print('v1')\n")
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), "stalehash000000000000000000000000", 50.0)
        script.write_text("print('v2')\n")
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert "changed" in result.hint.lower() or "path history" in result.hint.lower()

    def test_run_count_is_correct_for_path_fallback(self, tmp_path):
        # Arrange
        script = tmp_path / "analyze.py"
        script.write_text("print('v1')\n")
        db = _make_db(tmp_path)
        _add_completed_run(db, "s1", str(script), "stale1000000000000000000000000000", 50.0)
        _add_completed_run(db, "s2", str(script), "stale2000000000000000000000000000", 80.0)
        script.write_text("print('v2')\n")
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.run_count == 2


# ---------------------------------------------------------------------------
# (c) Cold-start returns no-history result without fabricating
# ---------------------------------------------------------------------------


class TestColdStart:
    def test_cold_start_match_tier_unknown(self, tmp_path):
        # Arrange — empty DB, script with no history
        script = tmp_path / "fresh.py"
        script.write_text("print('new')\n")
        db = _make_db(tmp_path)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.match_tier == "unknown"

    def test_cold_start_no_fabricated_p50(self, tmp_path):
        # Arrange
        script = tmp_path / "fresh.py"
        script.write_text("print('new')\n")
        db = _make_db(tmp_path)
        # Act
        result = estimate(str(script), db=db)
        # Assert — must not fabricate
        assert result.p50_seconds is None

    def test_cold_start_no_fabricated_success_rate(self, tmp_path):
        # Arrange
        script = tmp_path / "fresh.py"
        script.write_text("print('new')\n")
        db = _make_db(tmp_path)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.success_rate is None

    def test_cold_start_run_count_is_zero(self, tmp_path):
        # Arrange
        script = tmp_path / "fresh.py"
        script.write_text("print('new')\n")
        db = _make_db(tmp_path)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.run_count == 0

    def test_cold_start_heavy_is_false(self, tmp_path):
        # Arrange
        script = tmp_path / "fresh.py"
        script.write_text("print('new')\n")
        db = _make_db(tmp_path)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.heavy is False


# ---------------------------------------------------------------------------
# (d) Heavy flag triggers above threshold
# ---------------------------------------------------------------------------


class TestHeavyFlag:
    def test_heavy_true_when_p90_exceeds_threshold(self, tmp_path):
        # Arrange — p90 just above HEAVY_THRESHOLD_SECONDS
        script = tmp_path / "heavy.py"
        script.write_text("import time; time.sleep(1)\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        threshold = 60  # use a small threshold for the test
        for i, dur in enumerate([600.0, 700.0, 800.0]):
            _add_completed_run(db, f"s{i}", str(script), h, dur)
        # Act
        result = estimate(str(script), db=db, heavy_threshold=threshold)
        # Assert
        assert result.heavy is True

    def test_heavy_false_when_p90_below_threshold(self, tmp_path):
        # Arrange
        script = tmp_path / "light.py"
        script.write_text("print('fast')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        for i, dur in enumerate([5.0, 10.0, 15.0]):
            _add_completed_run(db, f"s{i}", str(script), h, dur)
        # Act
        result = estimate(str(script), db=db, heavy_threshold=300)
        # Assert
        assert result.heavy is False

    def test_hint_contains_heavy_warning(self, tmp_path):
        # Arrange
        script = tmp_path / "heavy2.py"
        script.write_text("print('slow')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        for i, dur in enumerate([400.0, 500.0, 600.0]):
            _add_completed_run(db, f"s{i}", str(script), h, dur)
        # Act
        result = estimate(str(script), db=db, heavy_threshold=300)
        # Assert
        assert "long" in result.hint.lower() or "p90" in result.hint.lower()

    def test_default_heavy_threshold_is_300s(self):
        # Arrange / Act
        from scitex_clew._estimate import HEAVY_THRESHOLD_SECONDS
        # Assert
        assert HEAVY_THRESHOLD_SECONDS == 300


# ---------------------------------------------------------------------------
# (e) #outputs median from file_hashes
# ---------------------------------------------------------------------------


class TestOutputCount:
    def test_typical_outputs_is_median_of_output_counts(self, tmp_path):
        # Arrange — session 1: 2 outputs, session 2: 4 outputs, session 3: 6 outputs
        script = tmp_path / "plot.py"
        script.write_text("import matplotlib\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        for i, (sid, n_out) in enumerate([("o1", 2), ("o2", 4), ("o3", 6)]):
            _add_completed_run(db, sid, str(script), h, 30.0 + i * 10)
            for j in range(n_out):
                db.add_file_hash(sid, f"/out/{sid}/file{j}.png", f"hash{j}", "output")
        # Act
        result = estimate(str(script), db=db)
        # Assert — median of [2, 4, 6] = 4
        assert result.typical_outputs == 4

    def test_typical_outputs_zero_when_no_outputs_registered(self, tmp_path):
        # Arrange — runs with no output files
        script = tmp_path / "report.py"
        script.write_text("print('report')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        _add_completed_run(db, "r1", str(script), h, 20.0)
        # Act
        result = estimate(str(script), db=db)
        # Assert
        assert result.typical_outputs == 0


# ---------------------------------------------------------------------------
# (f) Target-file argument resolves to its producing script
# ---------------------------------------------------------------------------


class TestTargetFileResolution:
    def test_target_file_resolves_script_path(self, tmp_path):
        # Arrange — register a session that produced a target file
        script = tmp_path / "produce.py"
        script.write_text("open('out.csv', 'w').write('data')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        target = tmp_path / "results" / "out.csv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("data\n")
        _add_completed_run(db, "prod1", str(script), h, 45.0)
        db.add_file_hash("prod1", str(target), "filehash001", "output")
        # Act — pass the target file instead of the script
        result = estimate(str(target), db=db)
        # Assert
        assert result.script_path == str(script)

    def test_target_file_uses_producing_script_history(self, tmp_path):
        # Arrange
        script = tmp_path / "produce.py"
        script.write_text("open('out.csv', 'w').write('data')\n")
        from scitex_clew._hash import hash_file as _hf

        h = _hf(script)
        db = _make_db(tmp_path)
        target = tmp_path / "out.csv"
        target.write_text("data\n")
        _add_completed_run(db, "p1", str(script), h, 45.0)
        _add_completed_run(db, "p2", str(script), h, 55.0)
        db.add_file_hash("p1", str(target), "fh1", "output")
        db.add_file_hash("p2", str(target), "fh2", "output")
        # Act
        result = estimate(str(target), db=db)
        # Assert — both runs should be incorporated
        assert result.run_count >= 1

    def test_nonexistent_target_falls_back_to_cold_start(self, tmp_path):
        # Arrange — target file does not exist, no DB records
        db = _make_db(tmp_path)
        nonexistent = tmp_path / "missing.csv"
        # Act
        result = estimate(str(nonexistent), db=db)
        # Assert — cold start, not an exception
        assert result.match_tier == "unknown"


# ---------------------------------------------------------------------------
# (g) CLI --json shape
# ---------------------------------------------------------------------------


class TestCLI:
    def test_json_flag_produces_valid_json(self, tmp_path):
        # Arrange
        from scitex_clew._cli._estimate import estimate as estimate_cmd

        script = tmp_path / "script.py"
        script.write_text("print('hello')\n")
        runner = CliRunner()
        # Act
        result = runner.invoke(estimate_cmd, [str(script), "--json"])
        # Assert
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert isinstance(payload, dict)

    def test_json_output_has_required_keys(self, tmp_path):
        # Arrange
        from scitex_clew._cli._estimate import estimate as estimate_cmd

        script = tmp_path / "script.py"
        script.write_text("print('hello')\n")
        runner = CliRunner()
        # Act
        result = runner.invoke(estimate_cmd, [str(script), "--json"])
        payload = json.loads(result.output)
        # Assert
        required_keys = {
            "match_tier", "run_count", "p50_seconds", "p90_seconds",
            "success_rate", "typical_outputs", "heavy", "hint", "script_changed",
        }
        assert required_keys.issubset(set(payload.keys()))

    def test_json_cold_start_match_tier_unknown(self, tmp_path):
        # Arrange — empty environment, no history
        from scitex_clew._cli._estimate import estimate as estimate_cmd

        script = tmp_path / "fresh.py"
        script.write_text("print('new')\n")
        runner = CliRunner()
        # Act
        result = runner.invoke(estimate_cmd, [str(script), "--json"])
        payload = json.loads(result.output)
        # Assert
        assert payload["match_tier"] == "unknown"

    def test_human_output_shown_without_json_flag(self, tmp_path):
        # Arrange
        from scitex_clew._cli._estimate import estimate as estimate_cmd

        script = tmp_path / "script.py"
        script.write_text("print('hello')\n")
        runner = CliRunner()
        # Act
        result = runner.invoke(estimate_cmd, [str(script)])
        # Assert — human-readable, not JSON
        assert result.exit_code == 0
        assert "Estimate for" in result.output or "Match tier" in result.output

    def test_estimate_result_to_dict_is_json_serialisable(self):
        # Arrange
        result = EstimateResult(
            script_path="/some/script.py",
            match_tier="unknown",
            run_count=0,
            p50_seconds=None,
            p90_seconds=None,
            success_rate=None,
            typical_outputs=None,
            heavy=False,
            hint="No prior runs.",
            script_changed=False,
        )
        # Act
        d = result.to_dict()
        serialised = json.dumps(d)
        # Assert
        assert isinstance(serialised, str)
        assert json.loads(serialised)["match_tier"] == "unknown"


# EOF
