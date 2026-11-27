"""Build a REAL small clew project for the evidence-provider tests.

No mocks: a real ``@session`` analysis (scitex-session + scitex-io, recorded
by clew into the test's own PostgreSQL schema) runs twice, real claims are
registered through ``scitex_clew.add_claim``, then the faults the tests
expect are planted. Every child process gets a scrubbed environment carrying
only what it needs plus the test store DSN.

=========  ==========================================  =================
claim id   how it is registered                        clew outcome
=========  ==========================================  =================
auc        session output, ``source_keys`` /auc        OK
n_rows     session output, locator, text says 3 (is 2) VALUE_MISMATCH
accuracy   session output, NO locator                  VALUE_UNCHECKED
calib      hand-written json (no session), locator     NO_LINEAGE
budget     hand-written json, edited after register    HASH_MISMATCH
cohort2    session output whose input changed later    STALE_LINEAGE
=========  ==========================================  =================

``paper.tex`` line 8 ("42 degrees") is deliberately NOT registered: text that
is not a registered claim must never appear in the report.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "clew-project"

#: claim_id -> clew outcome the project is built to produce.
EXPECTED_OUTCOMES = {
    "auc": "OK",
    "n_rows": "VALUE_MISMATCH",
    "accuracy": "VALUE_UNCHECKED",
    "calib": "NO_LINEAGE",
    "budget": "HASH_MISMATCH",
    "cohort2": "STALE_LINEAGE",
}

#: claim_id -> (state, reason, provider_status) the adapter must report.
EXPECTED_REPORT = {
    "auc": (
        "supported",
        "value and sources check out against the recorded run",
        {"name": "OK", "code": 0},
    ),
    "n_rows": (
        "not_supported",
        "value in source differs: 2 in source vs 3 stated",
        {"name": "VALUE_MISMATCH", "code": 21},
    ),
    "accuracy": (
        "not_checkable",
        "no locator, value not checked",
        {"name": "VALUE_UNCHECKED", "code": 24},
    ),
    "calib": (
        "no_evidence_graph",
        "no evidence graph: the source has no recorded computation behind it",
        {"name": "NO_LINEAGE", "code": 13},
    ),
    "budget": (
        "not_supported",
        "source changed after the claim was registered",
        {"name": "HASH_MISMATCH", "code": 12},
    ),
    "cohort2": (
        "not_supported",
        "source changed after the run (an input, script or run changed)",
        {"name": "STALE_LINEAGE", "code": 18},
    ),
}


def kinds(graph: dict) -> dict[str, list[str]]:
    """``{node kind: [labels]}`` of a contract graph."""
    out: dict[str, list[str]] = {}
    for node in graph["nodes"]:
        out.setdefault(node["kind"], []).append(node["label"])
    return out


def labelled_edges(graph: dict) -> set[tuple[str, str, str]]:
    """``{(source label, target label, kind)}`` of a contract graph."""
    label = {n["id"]: n["label"] for n in graph["nodes"]}
    return {(label[e["source"]], label[e["target"]], e["kind"]) for e in graph["edges"]}


#: Environment variables a child interpreter genuinely needs.
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
        argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=300
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{argv!r} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}"
        )
    return proc.stdout


def _spec(line, claim_id, text, source, value, pointer=None) -> dict:
    spec = dict(
        file_path="paper/paper.tex",
        claim_type="value",
        line_number=line,
        claim_id=claim_id,
        claim_value=text,
        source_file=str(source),
        value=value,
    )
    if pointer:
        spec["source_keys"] = {".": {"pointer": pointer}}
    return spec


def build_project(dest: Path, journal_dir: Path) -> Path:
    """Materialise the project under *dest*, run it, register, plant faults."""
    root = (dest / "clew-project").resolve()
    shutil.copytree(FIXTURE, root)
    (root / "data").mkdir()
    (root / "data" / "input.csv").write_text("x,y\n1,2\n3,4\n")
    (root / "data" / "input2.csv").write_text("x,y\n10,1\n20,1\n30,1\n")
    (root / ".git").mkdir()  # project-root marker for clew's root walk
    # Environment policy, set explicitly so the outcomes do not depend on HOW
    # the test interpreter installed its packages. In a dev/CI checkout
    # scitex-clew is an editable install, which strict verify rightly calls
    # ENV_NOT_REPRODUCIBLE; from a wheel it is reproducible. The documented
    # knob (resolve_severity: "a project may accept, say, an editable sibling
    # checkout as policy") makes it a warning, so `auc` is OK either way. The
    # ENV_NOT_REPRODUCIBLE -> not_supported mapping is tested on its own.
    (root / ".scitex" / "clew").mkdir(parents=True)
    (root / ".scitex" / "clew" / "config.yaml").write_text(
        "verify:\n  severity:\n    env_not_reproducible: warning\n"
    )
    env = child_env(journal_dir)
    py = sys.executable
    results = root / "results" / "results.json"
    results2 = root / "results" / "results2.json"
    for src, dst in (("data/input.csv", results), ("data/input2.csv", results2)):
        run_checked(
            [py, "scripts/compute.py", "--src", src, "--dst", str(dst)], root, env
        )

    specs = [
        _spec(2, "auc", "AUC = 0.91", results, 0.91, "/auc"),
        _spec(3, "n_rows", "n = 3", results, 3, "/n_rows"),
        _spec(4, "accuracy", "0.77", results, 0.77),
        _spec(5, "calib", "k = 5", root / "paper" / "manual.json", 5, "/k"),
        _spec(
            6, "budget", "100 GPU-hours", root / "paper" / "edited.json", 100, "/budget"
        ),
        _spec(7, "cohort2", "60 units", results2, 60, "/sum_x"),
    ]
    run_checked([py, "-c", _REGISTER, str(root), json.dumps(specs)], root, env)

    # Plant the faults AFTER registration.
    (root / "paper" / "edited.json").write_text('{"budget": 250}\n')
    (root / "data" / "input2.csv").write_text("x,y\n10,1\n20,1\n31,1\n")
    return root


def add_external_claim(root: Path, journal_dir: Path) -> Path:
    """Register claim ``ext`` whose source is a file OUTSIDE ``root``.

    The source is a hand-written JSON beside the project (a shared file), so
    the evidence report must keep its path absolute and flag it external.
    Returns that source path.
    """
    shared = root.parent / "shared"
    shared.mkdir()
    source = shared / "external.json"
    source.write_text('{"k": 5}\n')
    spec = _spec(5, "ext", "k = 5", source, 5, "/k")
    run_checked(
        [sys.executable, "-c", _REGISTER, str(root), json.dumps([spec])],
        root,
        child_env(journal_dir),
    )
    return source
