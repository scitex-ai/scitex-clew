"""Pytest fixtures and rootdir marker for this package.

An empty conftest.py at tests/ is the canonical SciTeX
convention (audit-project PS208) — it pins the pytest
rootdir and gives downstream fixtures a home.

Subprocess coverage wiring (skill leaf 05_development_06_subprocess-coverage):
when tests spawn child Python interpreters (subprocess.run([sys.executable, ...]),
jupyter nbconvert --execute, etc.), their coverage data is dropped by default
because pytest-cov sets COVERAGE_FILE to a per-test tmp dir before conftest
loads. We force-set (NOT setdefault — that's a silent no-op) COVERAGE_PROCESS_START
+ COVERAGE_FILE at module import time, then write an idempotent .pth shim into
site-packages so coverage.process_startup() fires in every child interpreter.
"""

from __future__ import annotations

import os
import sysconfig
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Pin coverage data file at the repo root and point process_startup at our
# pyproject so child interpreters configure themselves correctly. Force-set
# (not setdefault) because pytest-cov has already populated COVERAGE_FILE by
# the time this conftest is imported.
os.environ["COVERAGE_PROCESS_START"] = str(_PROJECT_ROOT / "pyproject.toml")
os.environ["COVERAGE_FILE"] = str(_PROJECT_ROOT / ".coverage")


def _ensure_subprocess_coverage_shim() -> None:
    """Drop an idempotent `.pth` file in site-packages that auto-starts
    coverage in every child Python interpreter via
    `coverage.process_startup()`.
    """
    purelib = Path(sysconfig.get_paths()["purelib"])
    pth = purelib / "_scitex_clew_subprocess_coverage.pth"
    shim = (
        "import os, coverage\n"
        "if os.environ.get('COVERAGE_PROCESS_START'):\n"
        "    coverage.process_startup()\n"
    )
    try:
        if not pth.exists() or pth.read_text() != shim:
            pth.write_text(shim)
    except OSError:
        # site-packages may be read-only (e.g. system Python); silently skip —
        # local dev venvs are writable and that's where this matters.
        pass


_ensure_subprocess_coverage_shim()
