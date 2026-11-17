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
import threading
from pathlib import Path
from typing import Any

from .._core import getLogger
from ._external import ExternalPolicy, external_info

logger = getLogger(__name__)

__all__ = [
    "ENV_VAR",
    "RunCapture",
    "activate",
    "active_capture",
    "audit_capture_enabled",
    "finish",
]

#: Set to ``0`` / ``false`` / ``no`` / ``off`` to disable the ``open`` capture.
ENV_VAR = "SCITEX_CLEW_AUDIT_CAPTURE"
_FALSY = {"0", "false", "no", "off"}

#: Directory names under the project root that never hold run inputs/outputs.
_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".scitex",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".ipynb_checkpoints",
        "site-packages",
        "dist-packages",
    }
)
_EXCLUDED_SUFFIXES = (".py", ".pyc", ".pyo")
_SYSTEM_PREFIXES = ("/proc/", "/dev/", "/sys/")
_MAX_LISTED = 1_000

_ACCMODE = getattr(os, "O_ACCMODE", 3)

_PROBE_EVENT = "scitex_clew.capture.probe"

_tls = threading.local()
_ACTIVE: RunCapture | None = None
#: None = not attempted; True = installed; str = why installation failed.
_INSTALL_STATE: bool | str | None = None


def audit_capture_enabled() -> bool:
    """False when :data:`ENV_VAR` opts out of the ``open`` capture."""
    return os.environ.get(ENV_VAR, "1").strip().lower() not in _FALSY


def active_capture() -> RunCapture | None:
    """The capture of the currently active session, if any."""
    return _ACTIVE


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def _audit_hook(event: str, args: tuple) -> None:
    # Hot path: runs for EVERY audit event in the process. Keep it minimal.
    if event != "open" and event != "os.rename":
        if event == _PROBE_EVENT:
            args[0].append(True)
        return
    capture = _ACTIVE
    if capture is None or not capture.audit or getattr(_tls, "busy", False):
        return
    if event == "open":
        capture._on_open(args)
    else:
        capture._on_rename(args)


#: Modules whose frames mean "a ``scitex_io.save`` is in progress".
_STX_IO_SAVE_MODULES = ("scitex_io._save",)


def _inside_stx_io_save() -> bool:
    """True when the current open() happens inside ``scitex_io.save``.

    A saver may read its own target before overwriting it (the CSV saver
    compares with the existing file to skip identical writes). That read is
    not a data dependency of the run — recording it would bind the run to
    whichever earlier run produced the old bytes, an invented edge. The
    save's real effect is reported by scitex-io's post-save hook. Only walked
    for the first read of an in-scope path, so the cost is off the hot path.
    """
    frame = sys._getframe(2)
    while frame is not None:
        name = frame.f_globals.get("__name__", "")
        if name.startswith(_STX_IO_SAVE_MODULES):
            return True
        frame = frame.f_back
    return False


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


class RunCapture:
    """File-access and code capture for ONE tracked session (see module doc)."""

    def __init__(
        self,
        tracker,
        project_root: str | Path,
        *,
        entry_script: str | Path | None = None,
        exclude: list[str | Path] | None = None,
        audit: bool = True,
    ):
        self.tracker = tracker
        self.root = os.path.realpath(str(project_root))
        self._root_lexical = os.path.abspath(str(project_root))
        self.entry_script = (
            os.path.realpath(str(entry_script)) if entry_script else None
        )
        self._exclude = [os.path.realpath(str(p)) for p in (exclude or [])]
        self.external_policy = ExternalPolicy(self.root)
        self._prefixes = {
            os.path.realpath(p)
            for p in {sys.prefix, sys.exec_prefix, sys.base_prefix}
            if p and _under(os.path.realpath(p), self.root)
        }
        self.pid = os.getpid()
        self._lock = threading.Lock()
        self._decided: dict[str, tuple[str, bool, str | None] | None] = {}
        self.reads: list[str] = []
        self._read_set: set[str] = set()
        self.writes: set[str] = set()
        self._pending_reads: dict[str, str] = {}
        #: resolved path -> ``external`` payload of every external input read.
        self.external: dict[str, dict] = {}
        self._external_writes: set[str] = set()
        self.code: dict[str, str] = {}
        self.code_changed: list[str] = []
        self.errors: list[str] = []
        self.audit = audit
        self.audit_state = "active" if audit else f"disabled ({ENV_VAR}=0)"

    # ----------------------------------------------------------------- filter

    def classify(self, path: str) -> str | None:
        """Resolved path to record for an IN-PROJECT ``path``, else None."""
        decision = self.scope(path)
        if decision is None or decision[1]:
            return None
        return decision[0]

    def scope(self, path: str) -> tuple[str, bool, str | None] | None:
        """``(resolved, external, via)`` for ``path``, or None when out of scope.

        ``external`` is True for a data file outside the project root (or
        reached through an in-project symlink whose target lies outside);
        ``via`` is then the in-project path used, else None.
        """
        if path.startswith(_SYSTEM_PREFIXES) or path.endswith(_EXCLUDED_SUFFIXES):
            return None
        lexically_in = _under(path, self._root_lexical) or _under(path, self.root)
        real = os.path.realpath(path)
        if real == self.root:
            return None
        if not _under(real, self.root):
            if any(_under(real, p) for p in self._exclude):
                return None
            if not self.external_policy.accepts(real):
                return None
            return real, True, (path if lexically_in else None)
        if real.endswith(_EXCLUDED_SUFFIXES) or real == self.entry_script:
            return None
        parts = real[len(self.root) + 1 :].split(os.sep)
        for i, part in enumerate(parts[:-1]):
            if part in _EXCLUDED_DIRS:
                return None
            # Session bookkeeping: <script>_out/RUNNING/... , <script>_out/FINISHED*/...
            if (part == "RUNNING" or part.startswith("FINISHED")) and i > 0:
                if parts[i - 1].endswith("_out"):
                    return None
        if any(_under(real, p) for p in self._prefixes):
            return None
        if any(_under(real, p) for p in self._exclude):
            return None
        return real, False, None

    def external_for(self, path: str | Path) -> dict | None:
        """``external`` payload for an EXPLICITLY recorded input, else None.

        For ``stx.io.load`` / ``record_input``: the load is intentional, so
        only the boundary applies (no precision filter) — a file whose real
        location is outside the project root is external.
        """
        lexical = os.path.abspath(str(path))
        real = os.path.realpath(lexical)
        if _under(real, self.root):
            return None
        lexically_in = _under(lexical, self._root_lexical) or _under(lexical, self.root)
        return external_info(real, lexical if lexically_in else None)

    def _decide(self, raw: Any) -> tuple[str, bool, str | None] | None:
        if isinstance(raw, int):
            return None
        if isinstance(raw, bytes):
            raw = os.fsdecode(raw)
        elif not isinstance(raw, str):
            raw = os.fspath(raw)
        key = raw if os.path.isabs(raw) else os.path.abspath(raw)
        try:
            return self._decided[key]
        except KeyError:
            decision = self._decided[key] = self.scope(os.path.normpath(key))
            return decision

    # ------------------------------------------------------------- audit side

    def _on_open(self, args: tuple) -> None:
        try:
            if os.getpid() != self.pid:
                return  # forked child: never write through the parent's tracker
            decision = self._decide(args[0])
            if decision is None:
                return
            real, external, via = decision
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            access = flags & _ACCMODE
            if external:
                if access != os.O_WRONLY and real not in self._read_set:
                    if real not in self._external_writes:
                        self._record_read(real, via=via, external=True)
                if access != os.O_RDONLY:
                    self._external_writes.add(real)
                return
            if access != os.O_WRONLY and real not in self._read_set:
                if real not in self.writes:
                    self._record_read(real)
            if access != os.O_RDONLY:
                self.writes.add(real)
        except Exception as exc:  # noqa: BLE001 - must never break the user's open()
            self._fail(f"open capture: {type(exc).__name__}: {exc}")

    def _on_rename(self, args: tuple) -> None:
        try:
            if os.getpid() != self.pid or len(args) < 2:
                return
            src, dst = self._decide(args[0]), self._decide(args[1])
            if src is None or dst is None:
                return
            if src[0] not in self.writes and src[0] not in self._external_writes:
                return
            (self._external_writes if dst[1] else self.writes).add(dst[0])
        except Exception as exc:  # noqa: BLE001
            self._fail(f"rename capture: {type(exc).__name__}: {exc}")

    def _record_read(
        self, real: str, *, via: str | None = None, external: bool = False
    ) -> None:
        if not os.path.isfile(real):
            return  # missing (the open will fail) or not a regular file
        if _inside_stx_io_save():
            return  # the saver's own check of its target, not a data input
        with self._lock:
            if real in self._read_set:
                return
            self._read_set.add(real)
            self.reads.append(real)
        # Hash NOW (the bytes about to be read); the store write is batched
        # at close so the user's open() never waits on a store round-trip.
        from .._hash import hash_file

        _tls.busy = True
        try:
            self._pending_reads[real] = hash_file(real)
            if external:
                self.external[real] = external_info(real, via)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"hash input {real}: {type(exc).__name__}: {exc}")
        finally:
            _tls.busy = False

    def _fail(self, message: str) -> None:
        if not self.errors:
            logger.warning(
                "clew: file-access capture failed for session %s (%s) — this "
                "run's provenance is INCOMPLETE; see metadata['capture']['errors']",
                getattr(self.tracker, "session_id", "?"),
                message,
            )
        self.errors.append(message)

    # -------------------------------------------------------------- code side

    def local_modules(self) -> dict[str, str]:
        """``{module_name: resolved_file}`` of imported project-local modules."""
        found: dict[str, str] = {}
        for name, module in list(sys.modules.items()):
            # ``__dict__``, not getattr: a module-level ``__getattr__`` (lazy /
            # deprecated-alias modules) must not fire for a provenance scan.
            try:
                file = vars(module).get("__file__")
            except TypeError:
                continue
            if not file or not str(file).endswith(".py"):
                continue
            real = os.path.realpath(file)
            if real == self.entry_script or not _under(real, self.root):
                continue
            parts = real[len(self.root) + 1 :].split(os.sep)
            if any(p in _EXCLUDED_DIRS for p in parts[:-1]):
                continue
            if any(_under(real, p) for p in self._prefixes):
                continue
            if os.path.isfile(real):
                found[name] = real
        return found

    def record_code(self) -> None:
        """Record every imported project-local module not yet recorded."""
        from .._hash import hash_file

        _tls.busy = True
        try:
            found: dict[str, str] = {}
            for real in sorted(set(self.local_modules().values())):
                if real in self.code:
                    continue
                try:
                    found[real] = hash_file(real)
                except Exception as exc:  # noqa: BLE001
                    self._fail(f"hash code {real}: {type(exc).__name__}: {exc}")
            if found:
                try:
                    self.tracker.record_hashed_inputs(found)
                except Exception as exc:  # noqa: BLE001
                    self._fail(f"record code: {type(exc).__name__}: {exc}")
                else:
                    self.code.update(found)
        finally:
            _tls.busy = False

    def _check_code_unchanged(self) -> None:
        from .._hash import hash_file

        for real, digest in sorted(self.code.items()):
            try:
                now = hash_file(real)
            except FileNotFoundError:
                now = None
            if now != digest:
                self.code_changed.append(real)
        if self.code_changed:
            logger.warning(
                "clew: session %s — %d imported project module(s) changed on disk "
                "during the run; the recorded input hash is the version imported "
                "at start, which is no longer what is on disk: %s",
                self.tracker.session_id,
                len(self.code_changed),
                self.code_changed[:10],
            )

    # ------------------------------------------------------------------ close

    def flush(self) -> dict[str, Any]:
        """Record captured writes + late imports; return the metadata summary."""
        from .._hash import hash_file

        _tls.busy = True
        try:
            self._check_code_unchanged()
            self.record_code()
            if self._pending_reads:
                try:
                    # stx.io-recorded paths are skipped inside (one edge).
                    self.tracker.record_hashed_inputs(
                        self._pending_reads, external=self.external
                    )
                except Exception as exc:  # noqa: BLE001
                    self._fail(f"record inputs: {type(exc).__name__}: {exc}")
            outputs = self._record_writes(hash_file)
        finally:
            _tls.busy = False
        return self.summary(outputs)

    def _record_writes(self, hash_file) -> list[str]:
        recorded = self.tracker._outputs
        outputs: list[str] = []
        with self.tracker._db._file_hashes.batch():
            for real in sorted(self.writes):
                if not os.path.isfile(real):
                    continue  # temp file removed / renamed away
                try:
                    if real in recorded and recorded[real] == hash_file(real):
                        outputs.append(real)  # stx.io.save already recorded it
                        continue
                    if self.tracker.record_output(real):
                        outputs.append(real)
                except Exception as exc:  # noqa: BLE001
                    self._fail(f"record output {real}: {type(exc).__name__}: {exc}")
        return outputs

    def summary(self, outputs: list[str] | None = None) -> dict[str, Any]:
        def listed(items):
            items = list(items)
            return items[:_MAX_LISTED], max(0, len(items) - _MAX_LISTED)

        reads, reads_more = listed(self.reads)
        writes, writes_more = listed(outputs if outputs is not None else [])
        summary: dict[str, Any] = {
            "audit": self.audit_state,
            "project_root": self.root,
            "code_inputs": sorted(self.code),
            "code_changed": list(self.code_changed),
            "open_reads": reads,
            "open_writes": writes,
            "external_inputs": sorted(self.external),
            "external": self.external_policy.describe(),
            "errors": list(self.errors),
        }
        if reads_more:
            summary["open_reads_truncated"] = reads_more
        if writes_more:
            summary["open_writes_truncated"] = writes_more
        return summary


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
