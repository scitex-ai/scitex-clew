#!/usr/bin/env python3
"""``clew execute-notebook``: a real notebook in a real kernel (no mocks).

The kernel must run in ``--cwd`` (not the notebook's directory), see the
notebook named in ``$SCITEX_NOTEBOOK_PATH``, and leave the file untouched.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

nbformat = pytest.importorskip("nbformat")
pytest.importorskip("nbclient")
pytest.importorskip("ipykernel")

CELL = "import os\nopen('seen.txt', 'w').write(os.environ['SCITEX_NOTEBOOK_PATH'])\n"


@pytest.fixture
def executed(tmp_path):
    """Execute a one-cell notebook in nb/ with the kernel cwd in work/."""
    nb_dir, work = tmp_path / "nb", tmp_path / "work"
    nb_dir.mkdir()
    work.mkdir()
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell(CELL)]
    path = nb_dir / "a.ipynb"
    nbformat.write(nb, str(path))
    before = path.read_bytes()
    proc = subprocess.run(
        [sys.executable, "-m", "scitex_clew", "execute-notebook", str(path), "--cwd", str(work)],
        capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    return {"proc": proc, "path": path, "work": work, "before": before}


def test_execute_notebook_exits_zero(executed):
    # Arrange
    proc = executed["proc"]
    # Act
    code = proc.returncode
    # Assert
    assert code == 0, proc.stderr[-2000:]


def test_execute_notebook_runs_the_kernel_in_cwd_and_names_the_notebook(executed):
    # Arrange
    seen = executed["work"] / "seen.txt"
    # Act
    named = seen.read_text()
    # Assert
    assert named == str(executed["path"].resolve())


def test_execute_notebook_leaves_the_file_untouched(executed):
    # Arrange
    path = executed["path"]
    # Act
    after = path.read_bytes()
    # Assert
    assert after == executed["before"]
