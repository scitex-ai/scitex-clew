#!/usr/bin/env python3
"""A REAL scitex-session (>= 0.3.7) run from ``scripts/`` of a non-git project.

The bug this guards: clew scoped its store by walking up from the CWD for
``.git``/``pyproject.toml`` only, so a run from ``proj/scripts/`` minted its
project id in ``proj/scripts/.scitex/clew/`` while the session recorded
``proj`` as the project root. clew now adopts the session's recorded root.

A real interpreter, a real ``@scitex_session.session`` script, a real
PostgreSQL store. No mocks.
"""

from __future__ import annotations

import os
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version

import pytest
from scitex_clew._db import get_db, reset_db


def _session_version() -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in version("scitex-session").split(".")[:3])
    except (PackageNotFoundError, ValueError):
        return (0,)


pytestmark = pytest.mark.skipif(
    _session_version() < (0, 3, 7),
    reason="needs scitex-session >= 0.3.7 (records project_root_source)",
)

SCRIPT = """
import scitex_session
import scitex_clew._observers as clew_observers
clew_observers.register_with_scitex_session()

@scitex_session.session
def main():
    return 0

main()
"""


@pytest.fixture
def session_run(tmp_path):
    """Run SCRIPT from ``proj/scripts``; return (project dir, run record)."""
    home = tmp_path.resolve()
    project = home / "proj"
    for sub in ("config", "data", "scripts"):
        (project / sub).mkdir(parents=True)
    (project / "scripts" / "run.py").write_text(SCRIPT)
    env = {k: v for k, v in os.environ.items() if k != "SCITEX_CLEW_PROJECT"}
    env["HOME"] = str(home)
    env.pop("SCITEX_SESSION_PROJECT_ROOT", None)
    proc = subprocess.run(
        [sys.executable, "run.py"],
        cwd=project / "scripts",
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    id_file = project / ".scitex" / "clew" / "project-id"
    saved = os.environ.get("SCITEX_CLEW_PROJECT")
    os.environ["SCITEX_CLEW_PROJECT"] = id_file.read_text().strip()
    reset_db()
    try:
        runs = get_db().list_runs(limit=10)
    finally:
        if saved is None:
            os.environ.pop("SCITEX_CLEW_PROJECT", None)
        else:
            os.environ["SCITEX_CLEW_PROJECT"] = saved
        reset_db()
    return project, runs


def test_session_run_from_scripts_scopes_clew_at_the_project_root(session_run):
    # Arrange
    project, _ = session_run
    # Act
    places = (
        (project / ".scitex" / "clew" / "project-id").is_file(),
        (project / "scripts" / ".scitex").exists(),
    )
    # Assert
    assert places == (True, False)


def test_session_run_records_the_root_and_rule_clew_used(session_run):
    # Arrange
    import json

    project, runs = session_run
    # Act
    meta = runs[0]["metadata"] if runs else None
    meta = json.loads(meta) if isinstance(meta, str) else (meta or {})
    used = meta.get("clew_project_root", {})
    # Assert
    assert (
        used.get("project_root"),
        used.get("project_root_source"),
        used.get("via"),
    ) == (
        str(project),
        "marker",
        "session",
    )


# EOF
