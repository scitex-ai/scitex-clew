#!/usr/bin/env python3
"""Notebook-produced claims end to end (scitex-clew#199).

Real notebooks, executed headless by real Jupyter kernels (``python -m
nbconvert --execute``), with a REAL scitex-session >= 0.4.0 ``@session``
called inside a cell or a ``%run`` project script, writing into a REAL
PostgreSQL store (each test its own schema). No mocks. clew must:

* record an in-cell session's notebook in ONE role — the run's ``script``,
  exactly as a ``.py`` entry script — never also as an ``input`` (data);
* identify it by its code cells (``ipynb-code-v1:``), so re-executing the
  notebook (new outputs saved into the file) does not stale it, while editing
  a code cell does;
* record a ``%run`` script as the run's ``script`` only, and the driving
  notebook as a code input;
* list the code a notebook run executes in its slice;
* carry an explicit re-execution recipe (run the notebook, not the kernel's
  argv), and replay a notebook run in a sandbox (``clew rerun``);
* refuse a notebook replay, saying what to install, when the interpreter has
  no notebook executor.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import textwrap
import venv
from pathlib import Path

import pytest
from scitex_clew._chain._notebook import (
    NOTEBOOK_CODE_PREFIX,
    hash_notebook_code,
    kernel_channel_dir,
)
from scitex_clew._chain._rerun_sandbox import _notebook_executor_missing
from scitex_clew._chain._slice import build_slice
from scitex_clew._chain._verify_ops import verify_run
from scitex_clew._db import get_db
from scitex_clew._rerun import verify_by_rerun

nbformat = pytest.importorskip("nbformat")
pytest.importorskip("nbclient")
pytest.importorskip("nbconvert")
pytest.importorskip("ipykernel")


def _session_records_notebooks() -> bool:
    """scitex-session >= 0.4.0 resolves and records the kernel's notebook."""
    try:
        return (
            importlib.util.find_spec("scitex_session._lifecycle._notebook") is not None
        )
    except ModuleNotFoundError:
        return False


pytestmark = pytest.mark.skipif(
    not _session_records_notebooks(),
    reason="needs scitex-session >= 0.4.0 (notebook entry)",
)

SETUP = textwrap.dedent(
    """
    import scitex_io as sio
    import scitex_clew as clew
    from scitex_session import session, INJECTED
    """
)

MAIN = textwrap.dedent(
    """
    @session(verbose=False)
    def main(CONFIG=INJECTED):
        rows = sio.load("../data/x.csv")
        sio.save({"n": len(rows)}, str(CONFIG["SDIR_OUT"]) + "/result.json")
        return 0
    """
)

COMPUTE = textwrap.dedent(
    """
    import scitex_io as sio
    import scitex_clew as clew
    from scitex_session import session, INJECTED

    @session(verbose=False)
    def main(CONFIG=INJECTED):
        rows = sio.load("../data/x.csv")
        sio.save({"n": len(rows)}, str(CONFIG["SDIR_OUT"]) + "/result.json")
        return 0

    if __name__ == "__main__":
        main()
    """
)


def _notebook(path: Path, *cells: str) -> Path:
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell(c) for c in cells]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}  # fmt: skip
    nbformat.write(nb, str(path))
    return path


def _env() -> dict[str, str]:
    """Explicit allowlist — never the parent's whole environment."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ["HOME"],
        "LANG": "C.UTF-8",
        "SCITEX_CLEW_PROJECT": get_db()._runs.project,
    }
    for key in ("PYTHONPATH", "SCITEX_STORE_DSN", "TMPDIR",
                "COVERAGE_PROCESS_START", "COVERAGE_FILE"):  # fmt: skip
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def _nbconvert(nb: Path, cwd: Path, *extra: str) -> None:
    # The kernel's channels are Unix sockets in a private directory: with
    # nbconvert's default tcp, ports picked here and bound later by the kernel
    # collide with a concurrently starting kernel ("Address already in use").
    channels = Path(kernel_channel_dir())  # short enough for socket paths
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute",
             "--KernelManager.transport=ipc", f"--KernelManager.ip={channels / 'kernel'}",
             *extra, os.path.relpath(nb, cwd)],
            cwd=cwd, env=_env(), capture_output=True, text=True, timeout=300,
        )  # fmt: skip
    finally:
        shutil.rmtree(channels, ignore_errors=True)
    assert proc.returncode == 0, proc.stderr[-3000:]


def _python(script: Path, cwd: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=cwd, env=_env(), capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    assert proc.returncode == 0, proc.stderr[-3000:]


def _project(tmp_path: Path) -> Path:
    project = tmp_path.resolve() / "proj"
    for d in ("config", "data", "notebooks", "scripts"):
        (project / d).mkdir(parents=True)
    (project / "data" / "x.csv").write_text("id,value\n1,1.5\n2,2.5\n")
    (project / "scripts" / "compute.py").write_text(COMPUTE)
    return project


def _only_run() -> dict:
    (run,) = get_db().list_runs(limit=50)
    return run


@pytest.fixture
def cell_run(tmp_path):
    """``@session`` called in a cell; returns (run, notebook, project)."""
    project = _project(tmp_path)
    nb = _notebook(project / "notebooks" / "a.ipynb", SETUP, MAIN, "main()")
    _nbconvert(nb, project, "--stdout")
    return _only_run(), nb, project


@pytest.fixture
def run_script_run(tmp_path):
    """A notebook that ``%run``s a project @session script."""
    project = _project(tmp_path)
    nb = _notebook(project / "notebooks" / "driver.ipynb", "%run ../scripts/compute.py")
    _nbconvert(nb, project, "--stdout")
    return _only_run(), nb, project


@pytest.fixture
def script_run(tmp_path):
    """The same @session code run as a plain ``.py`` entry script."""
    project = _project(tmp_path)
    script = project / "scripts" / "compute.py"
    _python(script, project / "scripts")
    return _only_run(), script, project


def _roles(run: dict, path: Path) -> set[str]:
    """Every role ``path`` is recorded under in ``run`` (script/input/output)."""
    roles = {"script"} if run["script_path"] == str(path) else set()
    records = get_db().get_file_records(run["session_id"])
    return roles | {r["role"] for r in records if r["file_path"] == str(path)}


def _result(run: dict) -> str:
    meta = json.loads(run["metadata"])
    return str(Path(meta["sdir_out"]) / "result.json")


# ---------------------------------------------------------------------------
# In-cell session
# ---------------------------------------------------------------------------


def test_cell_run_script_is_the_notebook_with_its_code_hash(cell_run):
    # Arrange
    run, nb, _project = cell_run
    # Act
    recorded = (run["script_path"], run["script_hash"])
    # Assert
    assert recorded == (str(nb), hash_notebook_code(nb))


def test_py_script_run_records_its_script_as_script_only(script_run):
    # Arrange
    run, script, _project = script_run
    # Act
    roles = _roles(run, script)
    # Assert
    assert roles == {"script"}


def test_cell_run_records_the_notebook_as_script_only_like_a_py_script(cell_run):
    # Arrange
    run, nb, _project = cell_run
    # Act
    roles = _roles(run, nb)
    # Assert
    assert roles == {"script"}


def test_cell_run_slice_lists_the_notebook_with_its_code_hash(cell_run):
    # Arrange
    run, nb, _project = cell_run
    # Act
    files = {
        f["path"]: f["hash"] for f in build_slice([_result(run)]).to_dict()["files"]
    }
    # Assert
    assert files.get(str(nb), "").startswith(NOTEBOOK_CODE_PREFIX)


def test_cell_run_slice_inputs_are_in_the_project(cell_run):
    # Arrange
    run, _nb, _project = cell_run
    # Act
    external = build_slice([_result(run)]).to_dict()["required_not_bundled"]
    # Assert
    assert external == []


def test_cell_run_slice_carries_a_notebook_rerun_recipe(cell_run):
    # Arrange
    run, nb, _project = cell_run
    # Act
    recipe = build_slice([_result(run)]).to_dict()["reruns"][run["session_id"]]
    # Assert
    assert (recipe["kind"], recipe["argv"][:4], recipe["cwd"]) == (
        "notebook", ["-m", "scitex_clew", "execute-notebook", str(nb)], str(nb.parent),
    )  # fmt: skip


def test_cell_run_verifies(cell_run):
    # Arrange
    run, _nb, _project = cell_run
    # Act
    result = verify_run(run["session_id"])
    # Assert
    assert result.is_verified


def test_cell_run_still_verifies_after_the_notebook_is_executed_in_place(cell_run):
    # Arrange: saving new outputs/execution counts into the .ipynb
    run, nb, project = cell_run
    _nbconvert(nb, project, "--inplace")
    # Act
    result = verify_run(run["session_id"])
    # Assert
    assert result.is_verified


def test_cell_run_is_stale_after_a_code_cell_is_edited(cell_run):
    # Arrange
    run, nb, _project = cell_run
    edited = nbformat.read(str(nb), as_version=4)
    edited.cells[1].source += "\n# edited"
    nbformat.write(edited, str(nb))
    # Act
    result = verify_run(run["session_id"])
    # Assert
    assert result.is_verified is False


def test_cell_run_is_replayed_by_running_the_notebook_and_verifies(cell_run):
    # Arrange
    run, _nb, _project = cell_run
    # Act
    result = verify_by_rerun(run["session_id"], timeout=300)
    # Assert
    assert (result.status.value, [f.path for f in result.files]) == (
        "verified", ["result.json"],
    )  # fmt: skip


# ---------------------------------------------------------------------------
# %run from a notebook
# ---------------------------------------------------------------------------


def test_run_script_records_the_script_as_script_only(run_script_run):
    # Arrange
    run, _nb, project = run_script_run
    # Act
    roles = _roles(run, project / "scripts" / "compute.py")
    # Assert
    assert roles == {"script"}


def test_run_script_records_the_driving_notebook_as_a_code_input(run_script_run):
    # Arrange
    run, nb, _project = run_script_run
    # Act
    roles = _roles(run, nb)
    # Assert
    assert roles == {"input"}


def test_run_script_slice_lists_notebook_and_script(run_script_run):
    # Arrange
    run, nb, project = run_script_run
    # Act
    files = {f["path"] for f in build_slice([_result(run)]).to_dict()["files"]}
    # Assert
    assert {str(nb), str(project / "scripts" / "compute.py")} <= files


def test_run_script_recipe_runs_the_driver_notebook(run_script_run):
    # Arrange
    run, nb, _project = run_script_run
    # Act
    recipe = build_slice([_result(run)]).to_dict()["reruns"][run["session_id"]]
    # Assert
    assert (recipe["path"], recipe["invocation"]) == (str(nb), "run")


def test_run_script_run_verifies(run_script_run):
    # Arrange
    run, _nb, _project = run_script_run
    # Act
    result = verify_run(run["session_id"])
    # Assert
    assert result.is_verified


# ---------------------------------------------------------------------------
# No executor: a clear refusal, not a crash
# ---------------------------------------------------------------------------


def test_notebook_replay_without_nbclient_is_refused_with_install_hint(tmp_path):
    # Arrange: a real interpreter with no third-party packages
    bare = tmp_path / "bare"
    venv.EnvBuilder(with_pip=False).create(bare)
    python = str(bare / "bin" / "python")
    # Act
    reason = _notebook_executor_missing(python)
    # Assert
    assert "pip install nbclient nbformat ipykernel" in (reason or "")
