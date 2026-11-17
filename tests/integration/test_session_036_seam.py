#!/usr/bin/env python3
"""End to end with a REAL scitex-session >= 0.3.6 ``python -c`` run.

A real interpreter runs an ``@scitex_session.session`` function given as
``python -c`` text. It reads project data, saves one result under the session
output root and one inside its own run dir, and closes. scitex-session 0.3.6
moves ``RUNNING/<ID>`` to ``FINISHED_SUCCESS/<ID>`` before the close hooks and
sends ``relocations``, ``entry`` (kind ``command``) and ``packages``. clew must:

* record the run-dir output at its FINAL path (cache verify passes);
* replay the run from ``entry.command`` (rerun verify passes);
* list the run's packages in the slice requirements.

Real subprocesses, real distributions, a real PostgreSQL store. No mocks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version

import pytest
from scitex_clew._chain._slice import build_slice
from scitex_clew._chain._verify_ops import verify_run
from scitex_clew._db import get_db
from scitex_clew._rerun import verify_by_rerun


def _session_version() -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in version("scitex-session").split(".")[:3])
    except (PackageNotFoundError, ValueError):
        return (0,)


pytestmark = pytest.mark.skipif(
    _session_version() < (0, 3, 6),
    reason="needs scitex-session >= 0.3.6 (relocations / entry / packages)",
)

COMMAND = """
import scitex_io, scitex_session
import scitex_clew._observers as clew_observers
clew_observers.register_with_scitex_session()
clew_observers.register_with_scitex_io()

@scitex_session.session
def main():
    rows = open("data/in.csv").read().splitlines()
    scitex_io.save({"n": len(rows)}, str(CONFIG["SDIR_OUT"]) + "/result.json")
    scitex_io.save({"n": len(rows)}, str(CONFIG["SDIR_RUN"]) + "/run_copy.json")
    return 0

main()
"""


@pytest.fixture
def command_run(tmp_path):
    """Run COMMAND as a real ``python -c`` session; return (sid, project)."""
    project = tmp_path.resolve() / "proj"
    (project / "data").mkdir(parents=True)
    (project / "data" / "in.csv").write_text("a,b\n1,2\n")
    env = dict(os.environ)
    env["SCITEX_CLEW_PROJECT"] = get_db()._runs.project
    proc = subprocess.run(
        [sys.executable, "-c", COMMAND],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    runs = [
        r
        for r in get_db().list_runs(limit=50)
        if (json.loads(r["metadata"] or "{}").get("entry") or {}).get("kind")
        == "command"
    ]
    return runs[0]["session_id"], project


def test_run_dir_output_is_recorded_at_its_final_path(command_run):
    # Arrange
    sid, project = command_run
    # Act
    outputs = get_db().get_file_hashes(sid, role="output")
    # Assert
    assert sorted(
        os.path.relpath(p, project / "python_c_out").split(os.sep)[0] for p in outputs
    ) == ["FINISHED_SUCCESS", "result.json"]


def test_relocated_command_run_cache_verifies(command_run):
    # Arrange
    sid, _project = command_run
    # Act
    result = verify_run(sid)
    # Assert
    assert result.is_verified


def test_command_run_is_replayed_and_verifies(command_run):
    # Arrange
    sid, _project = command_run
    # Act
    result = verify_by_rerun(sid, timeout=180)
    # Assert
    assert (result.status.value, sorted(f.path for f in result.files)) == (
        "verified",
        ["<run-dir>/run_copy.json", "result.json"],
    )


def test_slice_lists_the_session_packages(command_run):
    # Arrange
    _sid, project = command_run
    # Act
    env = build_slice([project / "python_c_out" / "result.json"]).requirements()
    # Assert
    assert env["packages"].get("scitex-session") == version("scitex-session")
