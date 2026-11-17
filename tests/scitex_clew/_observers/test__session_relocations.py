#!/usr/bin/env python3
"""The scitex-session >= 0.3.6 close payload, applied by clew's session hooks.

``relocations`` (run dir moved RUNNING/<ID> -> FINISHED_*/<ID> before the
close hooks fire), ``entry.kind == "command"`` (``python -c`` runs) and the
refreshed ``packages`` / ``unresolved_imports``. Real files, real directory
moves, the real hooks and a real PostgreSQL store. No mocks.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid

import pytest
from scitex_clew._chain._rerun_sandbox import (
    RUN_DIR_KEY,
    plan_sandbox,
    relative_outputs,
)
from scitex_clew._chain._slice import build_slice
from scitex_clew._chain._verify_ops import verify_run
from scitex_clew._db import get_db
from scitex_clew._hash import hash_file
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._rerun import verify_by_rerun
from scitex_clew._tracker import get_tracker, set_tracker

LOGGER = "scitex_clew._observers._session"


@pytest.fixture(autouse=True)
def _clean():
    set_tracker(None)
    yield
    set_tracker(None)


@pytest.fixture
def run_dirs(tmp_path):
    """A session output root with a RUNNING/<ID> run dir and its final home."""
    out = tmp_path.resolve() / "proj" / "script_out"
    running = out / "RUNNING" / "ID-1"
    running.mkdir(parents=True)
    final = out / "FINISHED_SUCCESS" / "ID-1"
    (out.parent / "script.py").write_text("print(1)\n")
    return out.parent, running, final


def _start(project, **meta):
    sid = f"reloc_{uuid.uuid4().hex[:10]}"
    on_session_start(
        sid,
        script_path=str(project / "script.py"),
        metadata={"project_root": str(project), **meta},
    )
    return sid


def _outputs(sid):
    return get_db().get_file_hashes(sid, role="output")


def _move(running, final):
    final.parent.mkdir(parents=True, exist_ok=True)
    os.rename(running, final)


class TestRelocations:
    def test_run_dir_output_is_recorded_at_its_final_path(self, run_dirs):
        # Arrange
        project, running, final = run_dirs
        sid = _start(project, sdir_run=str(running))
        (running / "fig.json").write_text("{}")
        get_tracker().record_output(running / "fig.json")
        _move(running, final)
        # Act
        on_session_close(
            metadata={"relocations": [{"from": str(running), "to": str(final)}]}
        )
        # Assert
        assert _outputs(sid) == {str(final / "fig.json"): hash_file(final / "fig.json")}

    def test_relocated_run_verifies(self, run_dirs):
        # Arrange
        project, running, final = run_dirs
        sid = _start(project, sdir_run=str(running))
        (running / "fig.json").write_text("{}")
        get_tracker().record_output(running / "fig.json")
        _move(running, final)
        # Act
        on_session_close(
            metadata={"relocations": [{"from": str(running), "to": str(final)}]}
        )
        # Assert
        assert verify_run(sid).is_verified

    def test_output_outside_the_moved_dir_is_untouched(self, run_dirs):
        # Arrange
        project, running, final = run_dirs
        other = project / "script_out" / "table.csv"
        other.write_text("a\n1\n")
        sid = _start(project, sdir_run=str(running))
        get_tracker().record_output(other)
        _move(running, final)
        # Act
        on_session_close(
            metadata={"relocations": [{"from": str(running), "to": str(final)}]}
        )
        # Assert
        assert list(_outputs(sid)) == [str(other.resolve())]

    def test_declared_derived_from_is_rewritten(self, run_dirs):
        # Arrange
        project, running, final = run_dirs
        sid = _start(project, sdir_run=str(running))
        (running / "mid.csv").write_text("x\n")
        (running / "fig.json").write_text("{}")
        tracker = get_tracker()
        tracker.record_output(running / "mid.csv")
        tracker.record_output(running / "fig.json", derived_from=[running / "mid.csv"])
        _move(running, final)
        # Act
        on_session_close(
            metadata={"relocations": [{"from": str(running), "to": str(final)}]}
        )
        # Assert
        rows = {r["file_path"]: r for r in get_db().get_file_records(sid)}
        assert rows[str(final / "fig.json")]["derived_from"] == [str(final / "mid.csv")]

    def test_output_absent_at_its_new_path_is_warned(self, run_dirs, caplog):
        # Arrange
        project, running, final = run_dirs
        _start(project, sdir_run=str(running))
        (running / "fig.json").write_text("{}")
        get_tracker().record_output(running / "fig.json")
        final.mkdir(parents=True)  # moved somewhere else; final stays empty
        # Act
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            on_session_close(
                metadata={"relocations": [{"from": str(running), "to": str(final)}]}
            )
        # Assert
        assert "are not at their new path" in caplog.text

    def test_malformed_relocation_is_warned_not_applied(self, run_dirs, caplog):
        # Arrange
        project, running, _final = run_dirs
        sid = _start(project, sdir_run=str(running))
        (running / "fig.json").write_text("{}")
        get_tracker().record_output(running / "fig.json")
        # Act
        with caplog.at_level(logging.WARNING, logger=LOGGER):
            on_session_close(metadata={"relocations": [{"from": str(running)}]})
        # Assert
        assert (
            "malformed relocation" in caplog.text,
            list(_outputs(sid)),
        ) == (True, [str(running / "fig.json")])


class TestCommandEntryRerun:
    def _command_run(self, project, entry):
        sid = f"cmd_{uuid.uuid4().hex[:10]}"
        out = project / "python_c_out"
        out.mkdir(parents=True)
        (out / "r.json").write_text("{}")
        get_db().add_run(
            session_id=sid,
            script_path="",
            metadata={
                "entry": entry,
                "cwd": str(project),
                "sdir_out": str(out),
                "argv": ["-c"],
            },
        )
        get_db().add_file_hash(
            sid, str(out / "r.json"), hash_file(out / "r.json"), "output"
        )
        return sid

    def test_command_entry_plans_a_python_c_replay(self, tmp_path):
        # Arrange
        text = "print('hi')"
        sid = self._command_run(
            tmp_path,
            {
                "kind": "command",
                "command": text,
                "command_sha256": hashlib.sha256(text.encode()).hexdigest(),
            },
        )
        run = get_db().get_run(sid)
        # Act
        plan = plan_sandbox(sid, run, get_db().get_file_hashes(sid, role="output"))
        # Assert
        assert (plan.command, plan.script, plan.refusal, plan.out_root.name) == (
            text,
            None,
            None,
            "python_c_out",
        )

    def test_command_recorded_only_by_hash_is_refused_loudly(self, tmp_path, caplog):
        # Arrange
        sid = self._command_run(
            tmp_path, {"kind": "command", "command_sha256": "ab" * 32}
        )
        # Act
        with caplog.at_level(logging.WARNING, logger="scitex_clew._rerun"):
            result = verify_by_rerun(sid)
        # Assert
        assert (result.status.value, "without its command text" in caplog.text) == (
            "unknown",
            True,
        )

    def test_command_text_not_matching_its_hash_is_refused(self, tmp_path):
        # Arrange
        sid = self._command_run(
            tmp_path,
            {"kind": "command", "command": "print(2)", "command_sha256": "00" * 32},
        )
        run = get_db().get_run(sid)
        # Act
        plan = plan_sandbox(sid, run, get_db().get_file_hashes(sid, role="output"))
        # Assert
        assert (
            plan.refusal == "python -c command text does not match its recorded sha256"
        )


class TestRunDirOutputKeys:
    def test_run_dir_outputs_are_keyed_by_path_inside_the_run_dir(self, tmp_path):
        # Arrange
        out = tmp_path / "x_out"
        run_dir = out / "FINISHED_SUCCESS" / "ID-9"
        run_dir.mkdir(parents=True)
        hashes = {str(run_dir / "a.json"): "h1", str(out / "b.json"): "h2"}
        # Act
        keyed = relative_outputs(hashes, out, run_dir)
        # Assert
        assert keyed == {f"{RUN_DIR_KEY}/a.json": "h1", "b.json": "h2"}


class TestSliceRequirements:
    def _run(self, project, packages, unresolved=None, name="r.json"):
        sid = _start(project)
        out = project / name
        out.write_text(json.dumps({"sid": sid}))
        get_tracker().record_output(out)
        metadata = {"packages": packages} if packages is not None else {}
        if unresolved is not None:
            metadata["unresolved_imports"] = unresolved
        on_session_close(metadata=metadata)
        return sid, out

    def test_slice_lists_packages_and_unresolved_imports(self, tmp_path):
        # Arrange
        project = tmp_path / "proj"
        project.mkdir()
        (project / "script.py").write_text("print(1)\n")
        _sid, out = self._run(
            project, {"numpy": "2.1.0"}, {"labtools": str(tmp_path / "labtools")}
        )
        # Act
        env = build_slice([out]).requirements()
        # Assert
        assert (env["packages"], env["unresolved_imports"]) == (
            {"numpy": "2.1.0"},
            {"labtools": str(tmp_path / "labtools")},
        )

    def test_run_without_package_record_is_listed(self, tmp_path):
        # Arrange
        project = tmp_path / "proj"
        project.mkdir()
        (project / "script.py").write_text("print(1)\n")
        sid, out = self._run(project, None)
        # Act
        env = build_slice([out]).requirements()
        # Assert
        assert env["runs_without_environment"] == [sid]

    def test_version_conflict_across_runs_is_reported(self, tmp_path):
        # Arrange: run B consumes run A's output; they recorded different numpy
        project = tmp_path / "proj"
        project.mkdir()
        (project / "script.py").write_text("print(1)\n")
        _a, first = self._run(project, {"numpy": "1.26.4"}, name="a.json")
        sid_b = _start(project)
        get_tracker().record_input(first)
        second = project / "b.json"
        second.write_text("{}")
        get_tracker().record_output(second)
        on_session_close(metadata={"packages": {"numpy": "2.1.0"}})
        # Act
        env = build_slice([second]).requirements()
        # Assert
        assert env["conflicts"] == {"numpy": ["1.26.4", "2.1.0"]}
