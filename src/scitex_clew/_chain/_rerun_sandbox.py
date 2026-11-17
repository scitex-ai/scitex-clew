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
* **``python -c`` runs** (scitex-session >= 0.3.6 records ``entry =
  {"kind": "command", "command", "command_sha256"}`` and no script) are
  replayed as ``python -c <command>`` from a sandbox that mirrors the
  recorded ``cwd`` (symlinked entries, minus the output root), so relative
  reads still resolve and outputs land in the sandbox. Refused, with a reason,
  when only the command's hash was recorded or the text no longer matches it.
* **Notebook runs** (a ``@session`` called in a notebook cell; scitex-session
  >= 0.4.0 records the ``.ipynb`` as the run's script) are replayed by
  executing a sandbox COPY of the notebook headless (``python -m scitex_clew
  execute-notebook``, nbclient) with the kernel in the recorded ``cwd`` — never
  by replaying the kernel's argv. Refused, with what to install, when the
  recorded interpreter lacks nbclient/ipykernel. A ``%run`` script started
  from a notebook replays as the script it is.
* **Clean up.** The sandbox directory is removed and the sandbox run's
  records are hidden from the default view (the store never deletes), so
  they do not show up as MISSING in ``clew status`` afterwards.
"""

from __future__ import annotations

import hashlib
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
    script: Path | None
    out_root: Path
    argv_tail: list[str]
    cwd: Path
    python: str
    outside_outputs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    #: ``python -c`` text to replay instead of a script (``entry.kind == command``).
    command: str | None = None
    #: Why the run cannot be replayed at all (None when it can).
    refusal: str | None = None
    #: True when the script is a notebook replayed with ``execute-notebook``.
    notebook: bool = False

    @property
    def can_sandbox(self) -> bool:
        return not self.outside_outputs and self.refusal is None


def _metadata(run_info: dict) -> dict:
    raw = run_info.get("metadata")
    if not raw:
        return {}
    return json.loads(raw) if isinstance(raw, str) else dict(raw)


def _command_plan(session_id: str, meta: dict, output_paths, python: str) -> SandboxPlan:
    """Plan the replay of a ``python -c`` run (see module doc)."""
    entry = meta.get("entry") or {}
    text = entry.get("command")
    refusal = None
    if not text:
        refusal = (
            "python -c run recorded without its command text (only "
            f"command_sha256={entry.get('command_sha256')}): cannot replay"
        )
    elif entry.get("command_sha256") and (
        hashlib.sha256(text.encode("utf-8")).hexdigest() != entry["command_sha256"]
    ):
        refusal = "python -c command text does not match its recorded sha256"
    cwd = Path(meta["cwd"]) if meta.get("cwd") else None
    if refusal is None and (cwd is None or not cwd.is_dir()):
        refusal = f"python -c run's recorded cwd {cwd} is gone: cannot replay"
    out_root = Path(meta["sdir_out"]) if meta.get("sdir_out") else (
        (cwd or Path.cwd()) / "python_c_out"
    )
    return SandboxPlan(
        session_id=session_id,
        script=None,
        out_root=out_root,
        argv_tail=[],
        cwd=cwd or Path.cwd(),
        python=python,
        outside_outputs=sorted(
            p for p in output_paths if not _is_under(Path(p), out_root)
        ),
        command=text,
        refusal=refusal,
    )


def plan_sandbox(session_id: str, run_info: dict, output_paths) -> SandboxPlan:
    """Plan the replay of ``session_id`` (no side effects)."""
    meta = _metadata(run_info)
    if (meta.get("entry") or {}).get("kind") == "command":
        python = ((meta.get("python") or {}).get("executable")) or sys.executable
        if not Path(python).exists():
            python = sys.executable
        return _command_plan(session_id, meta, output_paths, python)
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
    notebook = script.suffix == ".ipynb"
    refusal = _notebook_executor_missing(python) if notebook else None
    if notebook:
        argv_tail = []  # the kernel's argv is not the notebook's CLI
    return SandboxPlan(
        session_id=session_id,
        script=script,
        out_root=out_root,
        argv_tail=argv_tail,
        cwd=cwd,
        python=python,
        outside_outputs=outside,
        notes=notes,
        refusal=refusal,
        notebook=notebook,
    )


def _notebook_executor_missing(python: str) -> str | None:
    """Why ``python`` cannot execute a notebook headless, or None."""
    probe = subprocess.run(
        [python, "-c", "import nbclient, nbformat, ipykernel"],
        capture_output=True,
        text=True,
    )
    if probe.returncode == 0:
        return None
    return (
        f"notebook replay needs nbclient + nbformat + ipykernel in {python} "
        "(pip install nbclient nbformat ipykernel)"
    )


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


#: Key prefix of an output saved INSIDE the session's own run directory.
RUN_DIR_KEY = "<run-dir>"


def run_dir_of(run_info: dict | None) -> Path | None:
    """The run's final session directory (``sdir_run_final``, scitex-session
    >= 0.3.6), whose name carries the run's own id."""
    final = _metadata(run_info or {}).get("sdir_run_final")
    return Path(final) if final else None


def relative_outputs(
    hashes: dict[str, str], out_root: Path, run_dir: Path | None = None
) -> dict[str, str]:
    """``{relative path under out_root: hash}`` (paths outside are dropped).

    An output inside ``run_dir`` (the session's own ``FINISHED_*/<ID>/`` dir,
    whose name differs for every run) is keyed ``<run-dir>/<path in it>`` so
    the replay's copy is compared with the original's.
    """
    out: dict[str, str] = {}
    root = out_root.resolve()
    run_root = run_dir.resolve() if run_dir is not None else None
    for path, value in hashes.items():
        if run_root is not None:
            try:
                rel = Path(path).resolve().relative_to(run_root)
                out[f"{RUN_DIR_KEY}/{rel}"] = value
                continue
            except ValueError:
                pass
        try:
            out[str(Path(path).resolve().relative_to(root))] = value
        except ValueError:
            continue
    return out


def _mirror_cwd(plan: SandboxPlan, sandbox: Path) -> None:
    """Symlink the recorded cwd's entries into ``sandbox`` (not the out root)."""
    for entry in plan.cwd.iterdir():
        if entry.name == plan.out_root.name:
            continue
        try:
            (sandbox / entry.name).symlink_to(entry)
        except OSError:
            continue


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
    stem = plan.script.stem if plan.script is not None else "command"
    sandbox = Path(tempfile.mkdtemp(prefix=f"clew-rerun-{stem}-"))
    if plan.command is not None:
        _mirror_cwd(plan, sandbox)
        script_copy = None
        cmd = [plan.python, "-c", plan.command]
        run_cwd = sandbox
    elif plan.notebook:
        script_copy = _mirror_script_dir(plan, sandbox)
        cmd = [plan.python, "-m", "scitex_clew", "execute-notebook", str(script_copy),
               "--cwd", str(plan.cwd)]  # fmt: skip
        run_cwd = plan.cwd
    else:
        script_copy = _mirror_script_dir(plan, sandbox)
        cmd = [plan.python, str(script_copy), *plan.argv_tail]
        run_cwd = plan.cwd
    env = dict(os.environ)
    env["SCITEX_SESSION_OUT_DIR"] = str(sandbox)
    env["SCITEX_CLEW_RERUN_OF"] = plan.session_id
    # Record the replay in the SAME project scope this process reads, whatever
    # the recorded cwd resolves to on its own.
    from .._db._scope import PROJECT_SCOPE_ENV

    env[PROJECT_SCOPE_ENV] = db._runs.project
    try:
        proc = subprocess.run(
            cmd,
            cwd=run_cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return SandboxRun(None, sandbox, script_copy, None, {}, timed_out=True)

    new_sid = _find_sandbox_session(db, script_copy, sandbox)
    new_outputs = {}
    if new_sid is not None:
        new_outputs = relative_outputs(
            db.get_file_hashes(new_sid, role="output"),
            sandbox / plan.out_root.name,
            run_dir_of(db.get_run(new_sid)),
        )
    return SandboxRun(
        proc.returncode,
        sandbox,
        script_copy,
        new_sid,
        new_outputs,
        stderr_tail=(proc.stderr or "")[-2_000:],
    )


def _find_sandbox_session(db, script_copy: Path | None, sandbox: Path) -> str | None:
    """The run the replay recorded: its script is the sandbox copy, or (a
    ``python -c`` replay, no script) its recorded cwd is the sandbox.

    The sandbox path is unique per replay, so this cannot pick up another
    run of the same script (the old "newest of the last 5 runs" heuristic
    could).
    """
    wanted = (
        {str(script_copy), str(script_copy.resolve())} if script_copy else set()
    )
    sandbox_real = os.path.realpath(sandbox)
    for run in db.list_runs(limit=100_000):
        if run.get("script_path") in wanted and wanted:
            return run["session_id"]
        if script_copy is None:
            cwd = _metadata(run).get("cwd")
            if cwd and os.path.realpath(cwd) == sandbox_real:
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
