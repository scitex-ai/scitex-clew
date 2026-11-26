#!/usr/bin/env python3
"""A fresh machine records and verifies provenance with NO store configuration.

scitex-dev#1111 / scitex-writer#516: an unset ``SCITEX_STORE_DSN`` used to
resolve to a private fleet hostname, so a researcher who installed from PyPI
got ``StoreTargetError`` from every ``@session`` run and from
``clew verify``. This drives the whole researcher path in a CLEAN
environment — ``env -i`` style: a throwaway ``HOME``, ``PATH`` holding only
this interpreter's bin dir and the system dirs, no ``SCITEX_*`` or ``PG*``
variable — and requires each step to succeed against the per-user local
store that scitex-dev creates on first use:

1. a tiny ``@scitex_session.session`` script loads data and saves a result;
2. a claim on that result is registered;
3. ``clew verify --strict`` exits 0.

Real subprocesses, a real PostgreSQL, no mocks. Skips only where the machine
has no PostgreSQL server binaries at all (the store then fails loudly, which
scitex-dev's own suite pins).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_local = pytest.importorskip(
    "scitex_dev.store._local",
    reason="needs scitex-dev >= 0.67.0 (per-user local store default)",
)
pytest.importorskip("scitex_session")
pytest.importorskip("scitex_io")

if not (_local.pg_bin("initdb") and _local.pg_bin("pg_ctl")):
    pytest.skip(
        "no PostgreSQL server binaries on this machine", allow_module_level=True
    )

ANALYZE = """
import scitex_io, scitex_session
import scitex_clew._observers as observers
observers.register_with_scitex_session()
observers.register_with_scitex_io()

@scitex_session.session
def main():
    rows = scitex_io.load("data/in.csv")
    scitex_io.save({"n_rows": int(len(rows))}, "results/summary.json")
    return 0

main()
"""

CLAIM = """
import glob, json, scitex_clew
source = sorted(glob.glob("**/results/summary.json", recursive=True))[0]
n_rows = json.load(open(source))["n_rows"]
open("paper.tex", "w").write("We analysed \\\\vclaim{n_rows} rows.\\n")
scitex_clew.add_claim(
    "paper.tex", "value", line_number=1, claim_value=str(n_rows),
    source_file=source, claim_id="n_rows", value=n_rows,
    source_keys={".": {"pointer": "/n_rows"}},
)
"""

_STEP_TIMEOUT = 600


def _clean_env(home: Path) -> dict:
    """What ``env -i`` leaves, plus a HOME and a PATH: no SCITEX_*, no PG*."""
    bin_dir = str(Path(sys.executable).parent)
    return {
        "HOME": str(home),
        "PATH": os.pathsep.join([bin_dir, "/usr/bin", "/bin"]),
        "LANG": "C.UTF-8",
    }


def _run(argv: list, *, cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        check=False,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=_STEP_TIMEOUT,
        stdin=subprocess.DEVNULL,
    )


@pytest.fixture
def researcher_path(tmp_path):
    """Run the three steps; record each result; stop the server after."""
    base = tmp_path
    home, project = base / "home", base / "proj"
    (project / "data").mkdir(parents=True)
    (project / "scripts").mkdir()
    home.mkdir()
    (project / "data" / "in.csv").write_text("a,b\n1,2\n3,4\n")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.0.0"\n'
    )
    # A source/editable install of the package under test is correctly
    # ENV_NOT_REPRODUCIBLE under --strict. Accept it as project policy (the
    # same knob the evidence tests use) so this test measures the STORE, not
    # how CI installed clew. The release proof from PyPI runs without it.
    (project / ".scitex" / "clew").mkdir(parents=True)
    (project / ".scitex" / "clew" / "config.yaml").write_text(
        "verify:\n  severity:\n    env_not_reproducible: warning\n"
    )
    (project / "scripts" / "analyze.py").write_text(ANALYZE)
    (project / "scripts" / "claim.py").write_text(CLAIM)
    env = _clean_env(home)
    clew = str(Path(sys.executable).parent / "clew")
    steps = {}
    try:
        steps["session"] = _run(
            [sys.executable, "scripts/analyze.py"], cwd=project, env=env
        )
        steps["claim"] = _run(
            [sys.executable, "scripts/claim.py"], cwd=project, env=env
        )
        steps["verify"] = _run([clew, "verify", "--strict"], cwd=project, env=env)
        yield steps, home
    finally:
        pgdata = home / ".scitex" / "store" / "local" / "pgdata"
        if pgdata.exists():
            subprocess.run(
                [_local.pg_bin("pg_ctl"), "-D", str(pgdata), "-m", "fast", "stop"],
                check=False,
                capture_output=True,
                timeout=120,
            )


_TAIL = 3_000


def _report(steps: dict) -> str:
    return "\n".join(
        f"--- {name}: exit={result.returncode}\n"
        f"{result.stdout[-_TAIL:]}\n{result.stderr[-_TAIL:]}"
        for name, result in steps.items()
    )


def test_a_fresh_machine_records_and_verifies_with_no_configuration(
    researcher_path,
):
    """One observable: every step of the researcher path, as a summary.

    ``provenance_complete`` matters on its own: the old failure printed
    'provenance hook failure(s)' and still exited 0.
    """
    # Arrange
    steps, home = researcher_path
    session_output = steps["session"].stdout + steps["session"].stderr
    # Act
    observed = {
        "session_exit": steps["session"].returncode,
        "provenance_complete": "provenance hook failure" not in session_output,
        "claim_exit": steps["claim"].returncode,
        "verify_strict_exit": steps["verify"].returncode,
        "users_own_store_created": (
            home / ".scitex" / "store" / "local" / "pgdata" / "PG_VERSION"
        ).is_file(),
    }
    # Assert
    assert observed == {
        "session_exit": 0,
        "provenance_complete": True,
        "claim_exit": 0,
        "verify_strict_exit": 0,
        "users_own_store_created": True,
    }, _report(steps)


# EOF
