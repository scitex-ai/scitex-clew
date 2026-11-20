"""Build a REAL small clew project for the evidence-bundle tests.

No mocks: two real ``@session`` analyses (scitex-session + scitex-io, recorded
by clew into the module's own PostgreSQL schema) run in child interpreters,
and real claims are registered through ``scitex_clew.add_claim``.

* ``scripts/stats.py`` reads ``data/in.csv`` and saves
  ``scripts/stats_out/results.json`` (``n``, ``mean``);
* ``scripts/report.py`` reads that and saves
  ``scripts/report_out/summary.json`` (``double_mean``) — a parent -> child
  edge.

=========  ==========================================  =========
claim id   source + locator                            stated
=========  ==========================================  =========
n_rows     results.json ``/n``                         ``n = 3``
mean_x     results.json ``/mean``                      ``2.0``
double     summary.json ``/double_mean``               ``4.0``
=========  ==========================================  =========
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

STATS = textwrap.dedent(
    """
    import scitex_io as sio
    from scitex_session import session


    @session(verbose=False)
    def main():
        df = sio.load("data/in.csv")
        sio.save({"n": int(len(df)), "mean": float(df["x"].mean())}, "results.json")
        return 0


    if __name__ == "__main__":
        main()
    """
)

REPORT = textwrap.dedent(
    """
    import scitex_io as sio
    from scitex_session import session


    @session(verbose=False)
    def main():
        res = sio.load("scripts/stats_out/results.json")
        sio.save({"double_mean": res["mean"] * 2}, "summary.json")
        return 0


    if __name__ == "__main__":
        main()
    """
)

PAPER = "We analysed n = 3 recordings.\nThe mean was 2.0.\nDoubled, 4.0.\n"

#: Env variables a child interpreter genuinely needs (never os.environ whole).
_KEEP_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")

_REGISTER = r"""
import json, sys
import scitex_clew as clew
root, specs = sys.argv[1], json.loads(sys.argv[2])
for spec in specs:
    clew.add_claim(project_root=root, **spec)
"""


def child_env(journal_dir: Path) -> dict[str, str]:
    """A scrubbed environment: the essentials, the test store, the journal."""
    from scitex_clew._journal import JOURNAL_DIR_ENV

    env = {k: os.environ[k] for k in _KEEP_ENV if k in os.environ}
    env["SCITEX_STORE_DSN"] = os.environ["SCITEX_STORE_DSN"]
    env[JOURNAL_DIR_ENV] = str(journal_dir)
    env["SCITEX_CLEW_WARN_NO_LINEAGE"] = "0"
    return env


def run_checked(argv: list[str], cwd: Path, env: dict[str, str]) -> str:
    proc = subprocess.run(
        argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=900, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{argv!r} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
        )
    return proc.stdout


def _spec(line: int, claim_id: str, text: str, source: Path, value, pointer: str):
    return {
        "file_path": "paper/paper.tex",
        "claim_type": "value",
        "line_number": line,
        "claim_id": claim_id,
        "claim_value": text,
        "source_file": str(source),
        "value": value,
        "source_keys": {".": {"pointer": pointer}},
    }


def build_project(dest: Path, journal_dir: Path) -> Path:
    """Materialise the project under *dest*, run both analyses, register claims."""
    root = (dest / "bundle-project").resolve()
    (root / "scripts").mkdir(parents=True)
    (root / "data").mkdir()
    (root / "paper").mkdir()
    (root / ".git").mkdir()  # project-root marker for clew's root walk
    (root / "data" / "in.csv").write_text("x\n1\n2\n3\n")
    (root / "scripts" / "stats.py").write_text(STATS)
    (root / "scripts" / "report.py").write_text(REPORT)
    (root / "paper" / "paper.tex").write_text(PAPER)
    # An editable dev install is ENV_NOT_REPRODUCIBLE under strict verify;
    # accept it as policy so the claims' states do not depend on HOW the
    # test interpreter installed clew (same knob as the evidence tests).
    (root / ".scitex" / "clew").mkdir(parents=True)
    (root / ".scitex" / "clew" / "config.yaml").write_text(
        "verify:\n  severity:\n    env_not_reproducible: warning\n"
    )
    env = child_env(journal_dir)
    for script in ("scripts/stats.py", "scripts/report.py"):
        run_checked([sys.executable, script], root, env)
    results = root / "scripts" / "stats_out" / "results.json"
    summary = root / "scripts" / "report_out" / "summary.json"
    specs = [
        _spec(1, "n_rows", "n = 3", results, 3, "/n"),
        _spec(2, "mean_x", "2.0", results, 2.0, "/mean"),
        _spec(3, "double", "4.0", summary, 4.0, "/double_mean"),
    ]
    run_checked(
        [sys.executable, "-c", _REGISTER, str(root), json.dumps(specs)], root, env
    )
    return root


# EOF
