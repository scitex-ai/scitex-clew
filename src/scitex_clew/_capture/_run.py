#!/usr/bin/env python3
"""Per-session capture state: :class:`RunCapture` (see :mod:`scitex_clew._capture`).

Split out of ``_capture/__init__.py``; the audit hook and the session
lifecycle (``activate`` / ``finish``) stay there and drive this class.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any

from .._core import getLogger
from .._links import absolute, link_entries, merge_link_entries
from ._code import CodeExecCapture
from ._external import ExternalPolicy, external_info
from ._frames import not_a_run_read

logger = getLogger("scitex_clew._capture")

__all__ = ["ENV_VAR", "RunCapture"]

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

_tls = threading.local()


def _signature(path: str) -> tuple[int, int, int] | None:
    """``(size, mtime_ns, inode)`` of ``path``, or None when it cannot be read."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return st.st_size, st.st_mtime_ns, st.st_ino


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


class RunCapture(CodeExecCapture):
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
        #: resolved path -> stat signature of the bytes hashed at open time,
        #: so the stx.io load hook can reuse that hash (see hash_at_open).
        self._read_sigs: dict[str, tuple[int, int, int]] = {}
        #: resolved path -> ``external`` payload of every external input read.
        self.external: dict[str, dict] = {}
        self._external_writes: set[str] = set()
        #: link path -> entry of every in-project symlink traversed to reach
        #: an in-scope file (see :mod:`scitex_clew._links`, #192).
        self.links: dict[str, dict] = {}
        self.code: dict[str, str] = {}
        self.code_changed: list[str] = []
        self.errors: list[str] = []
        self.audit = audit
        self.audit_state = "active" if audit else f"disabled ({ENV_VAR}=0)"
        self._init_code_exec()

    # ----------------------------------------------------------------- filter

    def classify(self, path: str) -> str | None:
        """Resolved path to record for an IN-PROJECT ``path``, else None."""
        decision = self.scope(path)
        if decision is None or decision[1]:
            return None
        return decision[0]

    def scope(
        self, path: str, *, code: bool = False
    ) -> tuple[str, bool, str | None] | None:
        """``(resolved, external, via)`` for ``path``, or None when out of scope.

        ``external`` is True for a data file outside the project root (or
        reached through an in-project symlink whose target lies outside);
        ``via`` is then the in-project path used, else None. ``code=True``
        scopes a source file the run EXECUTED (``.py`` allowed; see
        :mod:`scitex_clew._capture._code`).
        """
        if path.startswith(_SYSTEM_PREFIXES):
            return None
        if not code and path.endswith(_EXCLUDED_SUFFIXES):
            return None
        lexical = os.path.normpath(path)
        lexically_in = _under(lexical, self._root_lexical) or _under(lexical, self.root)
        real = os.path.realpath(path)
        if real == self.root:
            return None
        if not _under(real, self.root):
            if any(_under(real, p) for p in self._exclude):
                return None
            if not self.external_policy.accepts(real, code=code):
                return None
            return real, True, (path if lexically_in else None)
        if real == self.entry_script:
            return None
        if not code and real.endswith(_EXCLUDED_SUFFIXES):
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
        lexical = absolute(str(path))
        real = os.path.realpath(lexical)
        if _under(real, self.root):
            return None
        lexical = os.path.normpath(lexical)
        lexically_in = _under(lexical, self._root_lexical) or _under(lexical, self.root)
        return external_info(real, lexical if lexically_in else None)

    def _decide(self, raw: Any) -> tuple[str, bool, str | None] | None:
        if isinstance(raw, int):
            return None
        if isinstance(raw, bytes):
            raw = os.fsdecode(raw)
        elif not isinstance(raw, str):
            raw = os.fspath(raw)
        key = absolute(raw)
        try:
            return self._decided[key]
        except KeyError:
            # Unnormalised: ``link/..`` must resolve as the kernel does.
            decision = self._decided[key] = self.scope(key)
            if decision is not None:
                self.note_links(key, decision[0])
            return decision

    def note_links(self, path: str, real: str) -> None:
        """Remember the symlinks ``path`` went through to ``real``: in-project
        ones, and pre-existing ones under the temp dir (flagged external)."""
        try:
            entries = link_entries(
                path, self.root, real, outside=self.external_policy.records_link
            )
        except OSError as exc:
            self._fail(f"symlink walk {path}: {type(exc).__name__}: {exc}")
            return
        if entries:
            with self._lock:
                merge_link_entries(self.links, entries)

    # ------------------------------------------------------------- audit side

    def _on_open(self, args: tuple) -> None:
        try:
            if os.getpid() != self.pid:
                return  # forked child: never write through the parent's tracker
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            if flags & _ACCMODE != os.O_WRONLY:
                self._note_code_read(args[0])
            decision = self._decide(args[0])
            if decision is None:
                return
            real, external, via = decision
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
                self._note_write(real)
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
            if dst[1]:
                self._external_writes.add(dst[0])
            else:
                self._note_write(dst[0])
        except Exception as exc:  # noqa: BLE001
            self._fail(f"rename capture: {type(exc).__name__}: {exc}")

    def _record_read(
        self, real: str, *, via: str | None = None, external: bool = False
    ) -> None:
        if not os.path.isfile(real):
            return  # missing (the open will fail) or not a regular file
        if not_a_run_read() is not None:
            return  # a saver's check of its target / clew's own verification
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
            signature = _signature(real)
            digest = self._pending_reads[real] = hash_file(real)
            if signature is not None and signature == _signature(real):
                self._read_sigs[real] = signature
            if external:
                self.external[real] = external_info(real, via)
            self._journal_read(real, digest, signature)
        except Exception as exc:  # noqa: BLE001
            self._fail(f"hash input {real}: {type(exc).__name__}: {exc}")
        finally:
            _tls.busy = False

    def _journal_read(self, real: str, digest: str, signature) -> None:
        """Journal a captured read NOW (it is recorded at close; a kill must
        not lose it — see :mod:`scitex_clew._journal`)."""
        journal = getattr(self.tracker, "_journal", None)
        if journal is not None:
            size = signature[0] if signature is not None else None
            journal.captured_read(real, digest, size, self.external.get(real))

    def _note_write(self, real: str) -> None:
        """Remember a write target (hashed at close); journal it once."""
        if real in self.writes:
            return
        self.writes.add(real)
        journal = getattr(self.tracker, "_journal", None)
        if journal is not None:
            journal.captured_write(real)

    def hash_at_open(self, real: str) -> str | None:
        """The hash taken when ``real`` was opened, if its bytes are unchanged.

        ``stx.io.load`` opens a file (captured here, hashed) and then fires
        clew's load hook, which records the same file: the hook reuses this
        hash instead of reading the file a second time. "Unchanged" is the
        same ``(size, mtime_ns, inode)`` as when it was hashed — the file is
        hashed again whenever that cannot be shown.
        """
        signature = self._read_sigs.get(real)
        if signature is None or signature != _signature(real):
            return None
        return self._pending_reads.get(real)

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
                # Imported through a symlinked dir/file: the import path is
                # what a re-run resolves, so the link is part of the record.
                self.note_links(absolute(str(file)), real)
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
            if self.exec_code:
                try:
                    # Executed-not-imported code (runpy / exec / %run): the
                    # same input edge as an imported project module.
                    self.tracker.record_hashed_inputs(
                        self.exec_code, external=self.external
                    )
                except Exception as exc:  # noqa: BLE001
                    self._fail(f"record exec code: {type(exc).__name__}: {exc}")
            if self._pending_reads:
                try:
                    # stx.io-recorded paths are skipped inside (one edge).
                    self.tracker.record_hashed_inputs(
                        self._pending_reads, external=self.external
                    )
                except Exception as exc:  # noqa: BLE001
                    self._fail(f"record inputs: {type(exc).__name__}: {exc}")
            outputs = self._record_writes(hash_file)
            if self.links:
                self.tracker.note_links(self.links.values())
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
            "exec_code_inputs": sorted(self.exec_code),
            "external_inputs": sorted(self.external),
            "external": self.external_policy.describe(),
            "links": sorted(self.links),
            "errors": list(self.errors),
        }
        if reads_more:
            summary["open_reads_truncated"] = reads_more
        if writes_more:
            summary["open_writes_truncated"] = writes_more
        return summary


# EOF
