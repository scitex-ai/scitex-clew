#!/usr/bin/env python3
"""Unconscious capture: file access + imported project code, for a session's life.

``stx.io.load`` / ``stx.io.save`` fire clew's io hooks, so data read or written
through scitex-io is recorded as run inputs/outputs. Two classes of real
dependencies are invisible to those hooks:

1. **Files opened by anything else** — a third-party loader
   (``pandas.read_csv``, ``numpy.load``), the ``open()`` builtin, or a library
   writing a file. A re-run of the run's slice then lacks the data.
2. **Imported project-local code** — helper modules the entry script imports.
   scitex-session hashes them into the run *metadata*, but they were not DAG
   inputs, so a claim's slice lacked the code it was computed with.

This module closes both, for the life of a session (activated by
:func:`~scitex_clew._observers._session.on_session_start`, flushed by
``on_session_close``):

* An **audit hook** (:func:`sys.addaudithook`, PEP 578) on the ``open`` event
  — fired by ``open()``/``io.open``/``os.open`` and therefore by every
  pure-Python loader — records files **under the project root only**. The
  event's ``flags`` give the access mode (``O_RDONLY`` / ``O_WRONLY`` /
  ``O_RDWR``), which is uniform across ``open()`` and ``os.open``:

  - a *read* is hashed at open time (the bytes about to be read) and recorded
    as a run input at session close, in one store transaction
    (:meth:`SessionTracker.record_hashed_inputs`), keyed by the same resolved
    path the ``stx.io.load`` hook uses — a file also loaded through ``stx.io``
    is one edge, never two;
  - a *write* is remembered and hashed at session close (a file may be written
    many times; the last bytes are the output), then recorded through
    :meth:`SessionTracker.record_output` unless the tracker already holds the
    same bytes for it (the ``stx.io.save`` hook);
  - ``os.rename`` / ``os.replace`` of a written temp file carries the write
    over to the destination (atomic-save pattern).

  Reads OUTSIDE the root — a shared dataset, a download, a sibling
  project's output, or a symlink inside the project whose target lies
  outside it — are recorded as **external inputs** (an ``input`` row whose
  ``external`` column carries the in-project path used, size and mtime;
  ``file_path`` is the resolved target). Interpreter, library, system, temp
  and tool-state reads are excluded by :mod:`scitex_clew._capture._external`,
  which documents the full exclusion list and the include/exclude knobs.
  Writes outside the root are not outputs (see that module).

  Excluded even under the root: the session's own bookkeeping trees
  (``<script>_out/RUNNING|FINISHED*``), ``.git``, ``__pycache__``, Python
  sources/bytecode (code is captured by module import, below; ``.py`` opens
  are ``linecache``/tracebacks, not data), the running interpreter's prefix
  (an in-project venv) and ``site-/dist-packages``, ``.scitex`` tool state,
  tool caches, and ``/proc`` ``/dev`` ``/sys``. A file this run wrote and then
  read back is an intermediate, not an input; a read made INSIDE
  ``scitex_io.save`` (a saver checking its own target) is not an input.

* **Imported project-local modules** (``__file__`` under the root, not
  installed, not the entry script) are recorded as run inputs at session start
  — role ``input``, the edge every consumer (``clew.slice``, ``chain``,
  ``verify``, rerun staging) already follows; a ``.py`` input classifies as
  node class ``source``. Modules imported later in the run are recorded at
  close. A module whose file changed on disk during the run is warned about
  and listed (``capture.code_changed``); the recorded hash is the imported one.

* **Executed-not-imported project code** — ``runpy.run_path``,
  ``exec(compile(open(p).read(), p, "exec"))``, ``exec(open(p).read())``,
  ``spec_from_file_location`` + ``exec_module`` and ``%run`` — is recorded the
  same way, from the ``exec`` / ``compile`` audit events
  (:mod:`scitex_clew._capture._code`; ``capture.exec_code_inputs``).

Precision and loudness
----------------------
Nothing is inferred — only files the process actually opened. Outside the
project root only regular data files pass the external-input policy; a run
that depends on any is WARNED about at close (a slice cannot bundle them). The hook is installed once per process
(audit hooks cannot be removed) and is inert unless a session is active, in a
forked child (pid check), or re-entered by clew's own hashing/DB I/O. If the
hook cannot be installed, or recording a captured file fails, clew WARNS and
continues — the loss is also written to the run's ``metadata["capture"]``.

Opt out (performance-sensitive runs): ``SCITEX_CLEW_AUDIT_CAPTURE=0`` disables
the ``open`` capture (a WARNING says the run's provenance relies on stx.io
alone). ``SCITEX_CLEW_EXTERNAL_CAPTURE=0`` disables only the external-input
recording. Code-module capture is cheap and always on.

Not seen: files opened by C/C++ code that bypasses Python's ``open`` (e.g.
HDF5 via ``h5py``, some ``pyarrow`` readers), memory maps of already-open
descriptors, and work done in spawned (non-forked) subprocesses. Read those
through ``stx.io.load`` (or ``clew.record_input``) to record them.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .._core import getLogger
from ._run import _FALSY, ENV_VAR, RunCapture, _tls

logger = getLogger(__name__)

__all__ = [
    "ENV_VAR",
    "RunCapture",
    "activate",
    "active_capture",
    "audit_capture_enabled",
    "finish",
]

_PROBE_EVENT = "scitex_clew.capture.probe"

_ACTIVE: RunCapture | None = None
#: None = not attempted; True = installed; str = why installation failed.
_INSTALL_STATE: bool | str | None = None


def audit_capture_enabled() -> bool:
    """False when :data:`ENV_VAR` opts out of the ``open`` capture."""
    return os.environ.get(ENV_VAR, "1").strip().lower() not in _FALSY


def active_capture() -> RunCapture | None:
    """The capture of the currently active session, if any."""
    return _ACTIVE


_CODE_EVENTS = {"exec": "_on_exec", "compile": "_on_compile"}


def _audit_hook(event: str, args: tuple) -> None:
    # Hot path: runs for EVERY audit event in the process. Keep it minimal.
    if event != "open" and event != "os.rename" and event not in _CODE_EVENTS:
        if event == _PROBE_EVENT:
            args[0].append(True)
        return
    capture = _ACTIVE
    if capture is None or not capture.audit or getattr(_tls, "busy", False):
        return
    if event == "open":
        capture._on_open(args)
    elif event == "os.rename":
        capture._on_rename(args)
    elif os.getpid() == capture.pid:
        # exec/compile handlers hash files: their own opens are not the run's.
        _tls.busy = True
        try:
            getattr(capture, _CODE_EVENTS[event])(args)
        finally:
            _tls.busy = False


def _install_hook() -> bool | str:
    """Install the process-wide audit hook once; return True or the failure."""
    global _INSTALL_STATE
    if _INSTALL_STATE is None:
        try:
            sys.addaudithook(_audit_hook)
            # An existing hook that raises RuntimeError on "sys.addaudithook"
            # makes CPython SKIP the new hook and SUPPRESS the error — so a
            # returned call proves nothing. Fire a probe event and require
            # that our hook saw it.
            seen: list = []
            sys.audit(_PROBE_EVENT, seen)
            if not seen:
                raise RuntimeError(
                    "sys.addaudithook was refused by an existing audit hook"
                )
            _INSTALL_STATE = True
        except Exception as exc:  # noqa: BLE001 - surfaced below + in metadata
            _INSTALL_STATE = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "clew: could not install the file-access audit hook (%s) — files "
                "read/written outside stx.io will NOT be recorded as provenance "
                "in this process",
                _INSTALL_STATE,
            )
    return _INSTALL_STATE


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def _project_root(metadata: dict | None, script_path: str | None) -> str | None:
    """scitex-session's ``project_root`` (>=0.3.5), else git root, else script dir."""
    meta = metadata if isinstance(metadata, dict) else {}
    root = meta.get("project_root")
    if root:
        return str(root)
    git = meta.get("git")
    if isinstance(git, dict) and git.get("root"):
        return str(git["root"])
    if script_path:
        return str(Path(script_path).resolve().parent)
    return None


def activate(
    tracker,
    *,
    script_path: str | None = None,
    metadata: dict | None = None,
) -> RunCapture | None:
    """Start capture for ``tracker``'s session; returns the capture (or None).

    Never raises: a failure is warned and recorded on the run.
    """
    global _ACTIVE
    _ACTIVE = None
    root = _project_root(metadata, script_path)
    if root is None:
        logger.warning(
            "clew: session %s has no project root (no script path / git root) — "
            "file-access and imported-code capture are OFF for it",
            tracker.session_id,
        )
        return None
    meta = metadata if isinstance(metadata, dict) else {}
    exclude = [p for p in (meta.get("sdir_run"),) if p]
    audit = audit_capture_enabled()
    capture = RunCapture(
        tracker, root, entry_script=script_path, exclude=exclude, audit=audit
    )
    capture.record_code()
    if not audit:
        logger.warning(
            "clew: %s=0 — files read/written outside stx.io are NOT recorded for "
            "session %s (provenance relies on stx.io hooks alone)",
            ENV_VAR,
            tracker.session_id,
        )
    else:
        state = _install_hook()
        if state is not True:
            capture.audit = False
            capture.audit_state = f"unavailable ({state})"
    _ACTIVE = capture
    return capture


def finish(tracker) -> dict[str, Any] | None:
    """Stop capture for ``tracker``'s session; flush and return the summary."""
    global _ACTIVE
    capture = _ACTIVE
    if capture is None or capture.tracker is not tracker:
        return None
    try:
        return capture.flush()
    finally:
        _ACTIVE = None


# EOF
