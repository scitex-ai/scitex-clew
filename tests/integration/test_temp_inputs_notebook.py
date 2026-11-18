#!/usr/bin/env python3
"""Temp-dir precision under a REAL Jupyter kernel (no mocks).

A notebook is the noisiest temp-dir user there is: nbconvert writes the
kernel's connection file into the Jupyter runtime dir BEFORE the kernel
starts, the kernel writes its own cell files (``ipykernel_<pid>/…``), and
matplotlib builds a font cache in a fresh config dir. None of that is data.
A scratch file a shell command staged in temp before the kernel started IS.

Here every one of those lives in a PRIVATE ``TMPDIR`` created and removed by
the test, the kernel runs a real scitex-session ``@session`` writing into a
real PostgreSQL schema, and the run must record exactly the staged file as
its only external input.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import scitex_clew as clew
from scitex_clew._chain._notebook import kernel_channel_dir
from scitex_clew._db import get_db

nbformat = pytest.importorskip("nbformat")
pytest.importorskip("nbclient")
pytest.importorskip("nbconvert")
pytest.importorskip("ipykernel")
pytest.importorskip("matplotlib")

_SRC = str(Path(clew.__file__).resolve().parents[1])


def _session_records_notebooks() -> bool:
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
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scitex_session import session, INJECTED
    """
)

MAIN = textwrap.dedent(
    """
    @session(verbose=False)
    def main(CONFIG=INJECTED):
        with open(STAGED) as f:
            n = len(f.read().splitlines())
        fig, ax = plt.subplots()
        ax.plot(range(n))
        ax.set_title("staged rows")
        fig.savefig(str(CONFIG["SDIR_OUT"]) + "/rows.png")
        plt.close(fig)
        return 0
    """
)


@pytest.fixture
def private_tmp(tmp_path):
    path = tmp_path.resolve() / "private-tmp"
    path.mkdir()
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _env(tmpdir: Path) -> dict[str, str]:
    """Explicit allowlist — never the parent's whole environment."""
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", str(tmpdir)),
        "LANG": "C.UTF-8",
        "TMPDIR": str(tmpdir),
        "PYTHONPATH": _SRC,
        "SCITEX_STORE_DSN": os.environ["SCITEX_STORE_DSN"],
        "SCITEX_CLEW_PROJECT": get_db()._runs.project,
        "JUPYTER_RUNTIME_DIR": str(tmpdir / "jupyter-runtime"),
        "MPLCONFIGDIR": str(tmpdir / "mpl"),
    }
    for key in ("COVERAGE_PROCESS_START", "COVERAGE_FILE"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def _execute(notebook: Path, cwd: Path, tmpdir: Path) -> None:
    """Run the notebook headless in a real kernel; raise with stderr on failure.

    The kernel's channels are Unix sockets in a private directory: with
    nbconvert's default tcp, ports picked here and bound later by the kernel
    collide with a concurrently starting kernel ("Address already in use").
    """
    channels = Path(kernel_channel_dir())  # short enough for socket paths
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "nbconvert", "--to", "notebook", "--execute",
             "--KernelManager.transport=ipc", f"--KernelManager.ip={channels / 'kernel'}",
             "--stdout", os.path.relpath(notebook, cwd)],
            cwd=cwd, env=_env(tmpdir), capture_output=True, text=True, timeout=300,
        )  # fmt: skip
    finally:
        shutil.rmtree(channels, ignore_errors=True)
    if proc.returncode != 0:
        stderr = proc.stderr.replace(os.environ["SCITEX_STORE_DSN"], "<dsn>")
        raise RuntimeError(f"nbconvert failed:\n{stderr[-3000:]}")


def test_kernel_and_library_temp_churn_is_not_recorded_but_staged_input_is(
    tmp_path, private_tmp
):
    # Arrange: a project, and a scratch file staged in temp BEFORE the kernel
    project = tmp_path.resolve() / "proj"
    (project / "notebooks").mkdir(parents=True)
    (project / "scripts").mkdir()
    staged = private_tmp / "scratch" / "rows.txt"
    staged.parent.mkdir()
    staged.write_text("a\nb\nc\n")
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        nbformat.v4.new_code_cell(SETUP),
        nbformat.v4.new_code_cell(f"STAGED = {str(staged)!r}"),
        nbformat.v4.new_code_cell(MAIN),
        nbformat.v4.new_code_cell("main()"),
    ]
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}  # fmt: skip
    path = project / "notebooks" / "a.ipynb"
    nbformat.write(nb, str(path))
    # Act
    _execute(path, project, private_tmp)
    # Assert
    (run,) = get_db().list_runs(limit=50)
    external = sorted(
        r["file_path"]
        for r in get_db().get_file_records(run["session_id"])
        if r["role"] == "input" and r["external"]
    )
    assert external == [str(staged)]
