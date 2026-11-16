#!/usr/bin/env python3
"""Re-execute a recorded run in a SANDBOX output root and compare its outputs.

Contract
--------
* **Replay what was recorded.** The run's recorded ``argv`` (scitex-session's
  start payload) is replayed from the recorded ``cwd`` with the recorded
  Python executable when it still exists. A run recorded without ``argv``
  is replayed as ``python <script>`` (no arguments) and says so in
  :attr:`SandboxPlan.notes`.
* **Never overwrite originals.** The script is COPIED into a fresh
  temporary directory (its siblings are symlinked so local imports keep
  working; its own ``<stem>_out/`` is not), so the caller-anchored
  ``stx.io.save`` writes to ``<sandbox>/<stem>_out/…`` and the session tree
  lands under ``SCITEX_SESSION_OUT_DIR=<sandbox>``. A run whose recorded
  outputs lie OUTSIDE ``<stem>_out/`` (absolute-path saves) cannot be
  sandboxed this way and is refused, not re-run.
* **Compare by full relative path + hash.** Original output
  ``<stem>_out/fig/a.png`` is compared with ``<sandbox>/<stem>_out/fig/a.png``
  only — never with another file that merely shares its basename.
* **Clean up.** The sandbox directory is removed and the sandbox run's
  records are hidden from the default view (the store never deletes), so
  they do not show up as MISSING in ``clew status`` afterwards.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from scitex_dev.store import ANY_REVISION

__all__ = ["SandboxPlan", "plan_sandbox", "relative_outputs", "run_in_sandbox"]


@dataclass
class SandboxPlan:
    """Everything needed to replay one run without touching its originals."""

    session_id: str
    script: Path
    out_root: Path
    argv_tail: list[str]
    cwd: Path
    python: str
    outside_outputs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def can_sandbox(self) -> bool:
        return not self.outside_outputs


def _metadata(run_info: dict) -> dict:
    raw = run_info.get("metadata")
    if not raw:
        return {}
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


def plan_sandbox(session_id: str, run_info: dict, output_paths) -> SandboxPlan:
    """Plan the replay of ``session_id`` (no side effects)."""
    script = Path(run_info["script_path"]).resolve()
    out_root = script.parent / f"{script.stem}_out"
    meta = _metadata(run_info)
    notes: list[str] = []

    argv = meta.get("argv")
    if isinstance(argv, list) and argv:
        argv_tail = [str(a) for a in argv[1:]]
    else:
        argv_tail = []
        notes.append("no recorded argv: replayed without arguments")

    cwd = Path(meta["cwd"]) if meta.get("cwd") else script.parent
    if not cwd.is_dir():
        notes.append(f"recorded cwd {cwd} is gone: replayed from {script.parent}")
        cwd = script.parent

    python = ((meta.get("python") or {}).get("executable")) or sys.executable
    if not Path(python).exists():
        notes.append(f"recorded python {python} is gone: used {sys.executable}")
        python = sys.executable

    outside = sorted(p for p in output_paths if not _is_under(Path(p), out_root))
    return SandboxPlan(
        session_id=session_id,
        script=script,
        out_root=out_root,
        argv_tail=argv_tail,
        cwd=cwd,
        python=python,
        outside_outputs=outside,
        notes=notes,
    )


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def relative_outputs(hashes: dict[str, str], out_root: Path) -> dict[str, str]:
    """``{relative path under out_root: hash}`` (paths outside are dropped)."""
    out: dict[str, str] = {}
    root = out_root.resolve()
    for path, value in hashes.items():
        try:
            out[str(Path(path).resolve().relative_to(root))] = value
        except ValueError:
            continue
    return out


def _mirror_script_dir(plan: SandboxPlan, sandbox: Path) -> Path:
    """Copy the script into ``sandbox``; symlink its siblings (not its _out)."""
    for entry in plan.script.parent.iterdir():
        if entry.name in (plan.script.name, plan.out_root.name):
            continue
        try:
            (sandbox / entry.name).symlink_to(entry)
        except OSError:
            continue
    copy = sandbox / plan.script.name
    shutil.copy2(plan.script, copy)
    return copy


@dataclass
class SandboxRun:
    """Outcome of one sandboxed replay."""

    returncode: int | None
    sandbox: Path
    sandbox_script: Path
    new_session_id: str | None
    new_outputs: dict[str, str]
    stderr_tail: str = ""
    timed_out: bool = False


def run_in_sandbox(plan: SandboxPlan, db, timeout: int) -> SandboxRun:
    """Replay ``plan`` in a fresh sandbox; outputs keyed by relative path."""
    sandbox = Path(tempfile.mkdtemp(prefix=f"clew-rerun-{plan.script.stem}-"))
    script_copy = _mirror_script_dir(plan, sandbox)
    env = dict(os.environ)
    env["SCITEX_SESSION_OUT_DIR"] = str(sandbox)
    env["SCITEX_CLEW_RERUN_OF"] = plan.session_id
    # Record the replay in the SAME project scope this process reads, whatever
    # the recorded cwd resolves to on its own.
    from .._db._scope import PROJECT_SCOPE_ENV

    env[PROJECT_SCOPE_ENV] = db._runs.project
    cmd = [plan.python, str(script_copy), *plan.argv_tail]
    try:
        proc = subprocess.run(
            cmd,
            cwd=plan.cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return SandboxRun(None, sandbox, script_copy, None, {}, timed_out=True)

    new_sid = _find_sandbox_session(db, script_copy)
    new_outputs = {}
    if new_sid is not None:
        new_outputs = relative_outputs(
            db.get_file_hashes(new_sid, role="output"),
            sandbox / plan.out_root.name,
        )
    return SandboxRun(
        proc.returncode,
        sandbox,
        script_copy,
        new_sid,
        new_outputs,
        stderr_tail=(proc.stderr or "")[-2_000:],
    )


def _find_sandbox_session(db, script_copy: Path) -> str | None:
    """The run the replay recorded: the one whose script is the sandbox copy.

    The sandbox path is unique per replay, so this cannot pick up another
    run of the same script (the old "newest of the last 5 runs" heuristic
    could).
    """
    wanted = {str(script_copy), str(script_copy.resolve())}
    for run in db.list_runs(limit=100_000):
        if run.get("script_path") in wanted:
            return run["session_id"]
    return None


def cleanup_sandbox(run: SandboxRun, db) -> None:
    """Remove the sandbox and hide the replay's records from default views."""
    shutil.rmtree(run.sandbox, ignore_errors=True)
    if run.new_session_id is None:
        return
    for rec in db.get_file_records(run.new_session_id):
        db._file_hashes.hide(
            (run.new_session_id, rec["file_path"], rec["role"]),
            expected_revision=ANY_REVISION,
        )
    db._runs.hide((run.new_session_id,), expected_revision=ANY_REVISION)


# EOF
