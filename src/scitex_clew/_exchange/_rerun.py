#!/usr/bin/env python3
"""Re-execute an evidence bundle's runs, STORE-FREE, and compare.

SECURITY: this EXECUTES THE PROJECT'S CODE (every recorded run's argv). It
adds no sandbox of its own: run it only on code you trust, or inside an
isolated, disposable container — which is how scitex-agentic-journal calls it.

What it does, for the bundle at ``bundle_path`` and the checkout at
``project_root``:

1. Copy the project tree (minus ``.git``) to a fresh temporary directory and
   delete every recorded OUTPUT from the copy, so each one must be produced
   again. Inputs are whatever the snapshot holds. The given project root is
   only read, never written. With ``work_dir`` the replay happens there
   (it must be absent or empty) and is KEPT: the report then gives
   ``work_dir``, each run's ``run_dir`` and each output's ``resolved_path``
   (relative to ``work_dir``), so a verifier outside the sandbox can hash
   exactly the files that were compared.
2. Replay each run in topological order (``edges``; ties by start time) as
   ``<python> <argv...>`` from its recorded ``cwd`` in the copy. The child
   gets an explicit environment — never this process's — with clew capture
   and its journal OFF and ``SCITEX_STORE_DSN`` pointing at no server, so
   nothing can reach a store; HOME / TMPDIR / SCITEX_DIR are inside the
   temporary directory.
3. Compare each recorded output's sha256 with the file the replay wrote (an
   output under the session's own run directory is matched in the replay's
   new run directory).
4. Recompute every claim's value from its source + locator in the copy, with
   the tolerance clew's claim check uses (:mod:`._precision`).

Run statuses: ``reproduced`` (exit 0, every output matches), ``differs``
(exit 0, an output differs or is absent), ``failed`` (non-zero exit or
timeout), ``skipped`` (not replayable: the recorded run did not succeed, a
notebook, no command, an input that is neither in the snapshot nor produced
by an earlier run, or an upstream run that failed/was skipped).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

from ._canonical import sha256_bytes, sha256_file
from ._precision import recompute_claim
from ._relpaths import is_portable
from ._verify import load_bundle

__all__ = [
    "RERUN_SCHEMA",
    "RERUN_SCHEMA_VERSION",
    "rerun_bundle",
    "rerun_env",
    "topological_runs",
]

RERUN_SCHEMA = "scitex-clew.rerun-report"
RERUN_SCHEMA_VERSION = "1.1.0"
#: A DSN no server answers: a stray store access fails loudly instead of
#: reaching the host's store.
NO_STORE_DSN = (
    "postgresql:///clew-bundle-rerun-has-no-store?host=/nonexistent-clew-rerun"
)
_PASS_ENV = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "SYSTEMROOT")
_STDERR_TAIL = 2_000


def rerun_env(work: Path) -> dict[str, str]:
    """The child environment: an explicit allowlist, no store, no capture."""
    env = {k: os.environ[k] for k in _PASS_ENV if k in os.environ}
    for name in ("home", "tmp", "scitex"):
        (work / name).mkdir(exist_ok=True)
    env.update(
        HOME=str(work / "home"),
        TMPDIR=str(work / "tmp"),
        SCITEX_DIR=str(work / "scitex"),
        SCITEX_CLEW_CAPTURE="0",
        SCITEX_CLEW_JOURNAL="0",
        SCITEX_STORE_DSN=NO_STORE_DSN,
        MPLBACKEND="Agg",
        PYTHONDONTWRITEBYTECODE="1",
    )
    return env


def topological_runs(runs: list[dict], edges: list[dict]) -> list[dict]:
    by_id = {r["run_id"]: r for r in runs}
    order_key = {r["run_id"]: (r.get("started_at") or "", r["run_id"]) for r in runs}
    parents: dict[str, set[str]] = {rid: set() for rid in by_id}
    for e in edges:
        if e.get("parent") in by_id and e.get("child") in by_id:
            parents[e["child"]].add(e["parent"])
    done: list[str] = []
    pending = set(by_id)
    while pending:
        ready = sorted(
            (r for r in pending if parents[r] <= set(done)), key=order_key.get
        )
        if not ready:  # a cycle: fall back to start order for the rest
            ready = sorted(pending, key=order_key.get)[:1]
        done.append(ready[0])
        pending.discard(ready[0])
    return [by_id[r] for r in done]


def _prepare_work_dir(work_dir: str | Path) -> Path:
    """``work_dir`` resolved and created; refuse one that already has content."""
    work = Path(work_dir).expanduser().resolve()
    if work.exists() and (not work.is_dir() or any(work.iterdir())):
        raise FileExistsError(f"--work-dir {work} exists and is not an empty directory")
    work.mkdir(parents=True, exist_ok=True)
    return work


def _copy_project(root: Path, dest: Path) -> None:
    shutil.copytree(root, dest, symlinks=True, ignore=shutil.ignore_patterns(".git"))


def _skip_reason(run: dict, tree: Path, produced: set[str], blocked: set[str],
                 parents: set[str]) -> str | None:  # fmt: skip
    if run.get("status") != "success":
        return f"the recorded run's status is {run.get('status')!r}, not 'success'"
    if (run.get("script") or "").endswith(".ipynb"):
        return "notebook runs are not replayed store-free"
    if not run.get("argv"):
        return "the run has no recorded command line"
    if not is_portable(run.get("cwd") or "."):
        return f"cwd {run.get('cwd')!r} is not a repo-relative path"
    upstream = sorted(parents & blocked)
    if upstream:
        return f"upstream run(s) {', '.join(upstream)} failed or were skipped"
    for rel in run.get("inputs") or {}:
        if rel not in produced and not (tree / rel).exists():
            return (
                f"input {rel} is neither in the snapshot nor produced by an earlier run"
            )
    return None


def _run_dirs(tree: Path, run: dict) -> tuple[Path | None, set[str]]:
    rd = run.get("run_dir")
    if not rd or not is_portable(rd):
        return None, set()
    parent = tree / PurePosixPath(rd).parent
    return parent, ({p.name for p in parent.iterdir()} if parent.is_dir() else set())


def _output_path(tree: Path, run: dict, rel: str, new_run_dir: Path | None) -> Path:
    rd = run.get("run_dir")
    if rd and new_run_dir is not None:
        try:
            inside = PurePosixPath(rel).relative_to(PurePosixPath(rd))
        except ValueError:
            pass
        else:
            return new_run_dir / inside
    return tree / rel


def _work_rel(path: Path, work: Path) -> str:
    return path.relative_to(work).as_posix()


def _compare_outputs(
    tree: Path, work: Path, run: dict, new_run_dir: Path | None
) -> list[dict]:
    from .._hash import hashes_match

    out = []
    for rel, expected in sorted((run.get("outputs") or {}).items()):
        path = _output_path(tree, run, rel, new_run_dir)
        actual = sha256_file(path) if path.is_file() else None
        out.append({"path": rel, "resolved_path": _work_rel(path, work),
                    "expected_sha256": expected, "actual_sha256": actual,
                    "match": hashes_match(expected, actual)})  # fmt: skip
    return out


def _replay(
    run: dict, tree: Path, work: Path, python: str, env: dict, timeout: float
) -> dict:
    parent, before = _run_dirs(tree, run)
    cmd = [python, *run["argv"]]
    try:
        proc = subprocess.run(cmd, check=False, cwd=tree / (run.get("cwd") or "."), env=env,
                              capture_output=True, text=True, timeout=timeout)  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        tail = (
            exc.stderr.decode("utf-8", "replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        return {"exit_code": None, "status": "failed",
                "reason": f"timed out after {timeout:g} s", "run_dir": None, "outputs": [],
                "stderr_tail": tail[-_STDERR_TAIL:]}  # fmt: skip
    new_run_dir = None
    if parent is not None and parent.is_dir():
        fresh = sorted(p for p in parent.iterdir() if p.name not in before)
        new_run_dir = fresh[0] if len(fresh) == 1 else None
    outputs = _compare_outputs(tree, work, run, new_run_dir)
    if proc.returncode != 0:
        status, reason = "failed", f"exited {proc.returncode}"
    elif all(o["match"] for o in outputs):
        status, reason = "reproduced", None
    else:
        status = "differs"
        reason = ", ".join(o["path"] for o in outputs if not o["match"]) + " differ(s)"
    run_dir = _work_rel(new_run_dir, work) if new_run_dir is not None else None
    return {"exit_code": proc.returncode, "status": status, "reason": reason,
            "run_dir": run_dir, "outputs": outputs, "stderr_tail": (proc.stderr or "")[-_STDERR_TAIL:]}  # fmt: skip


def _interpreter(python: str, env: dict) -> dict:
    proc = subprocess.run(
        [python, "-c", "import platform; print(platform.python_version())"],
        check=False, env=env, capture_output=True, text=True, timeout=60,
    )  # fmt: skip
    version = proc.stdout.strip() if proc.returncode == 0 else None
    return {"name": "python", "version": version, "executable": python}


def rerun_bundle(
    bundle_path: str | Path,
    project_root: str | Path,
    *,
    timeout: float = 600.0,
    python: str | None = None,
    work_dir: str | Path | None = None,
) -> dict:
    """Re-execute the bundle's runs and recompute its claims (see module doc).

    ``work_dir``: replay into this directory (absent or empty, else
    :class:`FileExistsError`) and KEEP it, so a verifier can hash the
    replayed files the report names (``work_dir`` + ``resolved_path``).
    Without it, a fresh temporary directory is used and removed.
    """
    root = Path(project_root).expanduser().resolve()
    doc, raw = load_bundle(bundle_path)
    python = python or sys.executable
    keep = work_dir is not None
    work = (
        _prepare_work_dir(work_dir)
        if keep
        else Path(tempfile.mkdtemp(prefix="clew-bundle-rerun-")).resolve()
    )
    try:
        tree = work / (root.name or "project")
        _copy_project(root, tree)
        runs = [r for r in doc.get("runs") or [] if isinstance(r, dict)]
        for run in runs:
            for rel in run.get("outputs") or {}:
                if is_portable(rel) and (tree / rel).is_file():
                    (tree / rel).unlink()
        env = rerun_env(work)
        parents_of: dict[str, set[str]] = {}
        for e in doc.get("edges") or []:
            parents_of.setdefault(e.get("child"), set()).add(e.get("parent"))
        produced: set[str] = set()
        blocked: set[str] = set()
        reports = []
        for run in topological_runs(runs, doc.get("edges") or []):
            rid = run["run_id"]
            reason = _skip_reason(
                run, tree, produced, blocked, parents_of.get(rid, set())
            )
            if reason is not None:
                rep = {"exit_code": None, "status": "skipped", "reason": reason,
                       "run_dir": None, "outputs": [], "stderr_tail": ""}  # fmt: skip
            else:
                rep = _replay(run, tree, work, python, env, timeout)
            if rep["status"] in ("failed", "skipped"):
                blocked.add(rid)
            produced |= set(run.get("outputs") or {})
            reports.append({"run_id": rid, **rep})
        claims = []
        for claim in doc.get("claims") or []:
            got = recompute_claim(claim, tree)
            claims.append({
                "claim_id": claim.get("claim_id"),
                "status": got["status"],
                "stated_value": claim.get("stated_value"),
                "recomputed_value": got["recomputed_value"],
                "tolerance": claim.get("precision"),
                "detail": got["detail"],
            })  # fmt: skip
        interpreter = _interpreter(python, env)
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
    return {
        "schema": RERUN_SCHEMA,
        "schema_version": RERUN_SCHEMA_VERSION,
        "bundle_sha256": sha256_bytes(raw),
        "work_dir": str(work) if keep else None,
        "executable": all(r["status"] in ("reproduced", "differs") for r in reports),
        "interpreter": interpreter,
        "runs": reports,
        "claims": claims,
    }


# EOF
