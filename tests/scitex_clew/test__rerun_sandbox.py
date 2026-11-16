#!/usr/bin/env python3
"""Sandboxed rerun: replay recorded argv from recorded cwd, never touch originals.

Each test runs a REAL script in a subprocess (recorded through
``clew.session`` with a scitex-session-shaped payload: ``argv`` + ``cwd``),
then re-runs it with :func:`scitex_clew.rerun`. No mocks.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest
import scitex_clew as clew
from scitex_clew._chain import VerificationStatus
from scitex_clew._db import get_db

SCRIPT = textwrap.dedent(
    """
    import os, sys
    from pathlib import Path
    import scitex_clew as clew

    here = Path(__file__)
    out = here.parent / f"{here.stem}_out"
    n = sys.argv[sys.argv.index("--n") + 1] if "--n" in sys.argv else "default"
    meta = {"argv": list(sys.argv), "cwd": os.getcwd()}
    with clew.session(script_path=str(here), metadata=meta) as run:
        data = Path("data.csv")          # relative to the recorded cwd
        run.record_input(data)
        for sub, text in (("fig", n + data.read_text()), ("table", "fixed")):
            (out / sub).mkdir(parents=True, exist_ok=True)
            (out / sub / "result.txt").write_text(text)   # same basename twice
            run.record_output(out / sub / "result.txt")
        if os.environ.get("WRITE_OUTSIDE"):
            outside = here.parent / "outside.txt"
            outside.write_text("abs")
            run.record_output(outside)
    """
)


def _record_original(tmp_path, *args, env_extra=None):
    work = tmp_path / "work"
    work.mkdir()
    (work / "data.csv").write_text("x\n1\n")
    proj = tmp_path / "proj"
    proj.mkdir()
    script = proj / "analysis.py"
    script.write_text(SCRIPT)
    env = dict(os.environ, **(env_extra or {}))
    env["SCITEX_CLEW_PROJECT"] = get_db()._runs.project
    subprocess.run(
        [sys.executable, str(script), *args],
        cwd=work,
        env=env,
        check=True,
        capture_output=True,
        timeout=120,
    )
    sid = next(
        r["session_id"]
        for r in get_db().list_runs(limit=1_000)
        if r["script_path"] == str(script)
    )
    return sid, script


@pytest.fixture
def original(tmp_path):
    return _record_original(tmp_path, "--n", "3")


class TestSandboxedRerun:
    def test_replay_with_recorded_argv_verifies(self, original):
        # Arrange
        sid, _script = original
        # Act
        result = clew.rerun(sid)
        # Assert
        assert result.status == VerificationStatus.VERIFIED

    def test_outputs_are_compared_by_full_relative_path(self, original):
        # Arrange
        sid, _script = original
        # Act
        result = clew.rerun(sid)
        # Assert
        assert sorted(f.path for f in result.files) == [
            "fig/result.txt",
            "table/result.txt",
        ]

    def test_original_outputs_are_never_rewritten(self, original):
        # Arrange
        sid, script = original
        target = script.parent / "analysis_out" / "fig" / "result.txt"
        before = target.stat().st_mtime_ns
        # Act
        clew.rerun(sid)
        # Assert
        assert target.stat().st_mtime_ns == before

    def test_sandbox_run_is_hidden_after_cleanup(self, original):
        # Arrange
        sid, script = original
        # Act
        clew.rerun(sid)
        # Assert
        assert [r["session_id"] for r in get_db().list_runs(limit=1_000)] == [sid]

    def test_changed_output_is_a_mismatch(self, original):
        # Arrange — the script now writes something else for the same argv
        sid, script = original
        script.write_text(SCRIPT.replace("n + data.read_text()", '"changed"'))
        # Act
        result = clew.rerun(sid)
        # Assert
        assert result.status == VerificationStatus.MISMATCH

    def test_failing_replay_is_failed(self, original):
        # Arrange
        sid, script = original
        script.write_text("raise SystemExit(3)\n")
        # Act
        result = clew.rerun(sid)
        # Assert
        assert result.status == VerificationStatus.FAILED


class TestRefusesWhatCannotBeSandboxed:
    def test_outputs_outside_out_root_are_not_rerun(self, tmp_path):
        # Arrange
        sid, script = _record_original(
            tmp_path, "--n", "1", env_extra={"WRITE_OUTSIDE": "1"}
        )
        outside = script.parent / "outside.txt"
        before = outside.stat().st_mtime_ns
        # Act
        result = clew.rerun(sid)
        # Assert
        assert (result.status, outside.stat().st_mtime_ns) == (
            VerificationStatus.UNKNOWN,
            before,
        )


# EOF
