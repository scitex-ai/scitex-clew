#!/usr/bin/env python3
"""Code a run EXECUTES from a file without importing it.

The module scan (:meth:`RunCapture.record_code`) sees project code that was
imported — a module in ``sys.modules``. Researchers also load code by reading
a file and executing it:

* ``runpy.run_path("helpers.py")``
* ``exec(compile(open(p).read(), p, "exec"))``
* ``spec = importlib.util.spec_from_file_location(name, p)`` +
  ``spec.loader.exec_module(module)`` (often never put in ``sys.modules``)
* IPython / Jupyter ``%run helpers.py``
* ``exec(open(p).read())`` — the code object is named ``"<string>"``

None of these leave a module behind, so the claim's slice lacked the code.
Two audit events (PEP 578) close the gap:

``exec``
    Fired for every executed code object. Its ``co_filename`` names the file
    the code was compiled from in every style above except the last; that
    file is recorded as a code input when it is in scope.

``compile``
    Fired with ``(source, filename)``, also for the implicit compilation of
    ``exec(<str>)``. When ``filename`` is not a file (``"<string>"``), the
    source is matched — by content hash, newline-normalised — against the
    ``.py`` files this run opened for reading. Only an EXACT match records a
    file, so a library compiling generated code (``dataclasses``,
    ``namedtuple``) never matches anything.

Scope: the same project-root / external-input boundary as data files
(:mod:`scitex_clew._capture._external`), with ``.py`` allowed. Library
internals — the interpreter's prefixes, ``site-/dist-packages``, the
directories of imported packages, system trees — are excluded by those rules,
as is the entry script itself. A code file outside the root (a shared lab
helper) is a code input flagged ``external``.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from .._links import absolute

__all__ = ["CodeExecCapture", "source_digest"]


def source_digest(source: Any) -> str | None:
    """Newline-normalised sha256 of Python source text (``None`` if not text).

    ``open(p).read()`` applies universal newlines and the source may carry a
    UTF-8 BOM, so raw file bytes and compiled text are compared after
    decoding and normalising both the same way.
    """
    if isinstance(source, (bytes, bytearray, memoryview)):
        text = bytes(source).decode("utf-8", "replace")
    elif isinstance(source, str):
        text = source
    else:
        return None  # an AST object: no source text to match
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _as_path(raw: Any) -> str | None:
    if isinstance(raw, bytes):
        raw = os.fsdecode(raw)
    elif not isinstance(raw, str):
        try:
            raw = os.fspath(raw)
        except TypeError:
            return None
        if isinstance(raw, bytes):
            raw = os.fsdecode(raw)
    return raw


class CodeExecCapture:
    """Mixin for :class:`~scitex_clew._capture.RunCapture` (see module doc).

    Requires ``scope(path, code=True)``, ``_fail``, ``code``, ``external``
    and ``_tls``-style re-entrancy handled by the caller.
    """

    def _init_code_exec(self) -> None:
        #: ``.py`` paths opened for reading this run (lazily hashed).
        self._code_candidates: set[str] = set()
        #: source digest -> resolved path, of the in-scope candidates hashed.
        self._candidate_digests: dict[str, str] = {}
        self._decided_code: dict[str, tuple[str, bool, str | None] | None] = {}
        #: resolved path -> file hash of code executed from a file.
        self.exec_code: dict[str, str] = {}

    # ----------------------------------------------------------- decisions

    def _decide_code(self, raw: Any) -> tuple[str, bool, str | None] | None:
        path = _as_path(raw)
        if not path or not path.endswith(".py"):
            return None
        key = absolute(path)
        try:
            return self._decided_code[key]
        except KeyError:
            decision = self._decided_code[key] = self.scope(key, code=True)
            if decision is not None:
                self.note_links(key, decision[0])
            return decision

    # --------------------------------------------------------- audit side

    def _note_code_read(self, raw: Any) -> None:
        """An ``open`` of a ``.py`` file for reading: a possible exec source."""
        path = _as_path(raw)
        if path and path.endswith(".py"):
            self._code_candidates.add(absolute(path))

    def _on_exec(self, args: tuple) -> None:
        try:
            filename = getattr(args[0], "co_filename", None) if args else None
            if not filename or filename.startswith("<"):
                return
            decision = self._decide_code(filename)
            if decision is not None:
                self._record_exec_code(*decision)
        except Exception as exc:  # noqa: BLE001 - must never break exec()
            self._fail(f"exec capture: {type(exc).__name__}: {exc}")

    def _on_compile(self, args: tuple) -> None:
        try:
            if len(args) < 2 or not self._code_candidates:
                return
            filename = _as_path(args[1])
            if filename and not filename.startswith("<"):
                return  # compiled from a named file: the exec event covers it
            digest = source_digest(args[0])
            if digest is None:
                return
            path = self._candidate_digests.get(digest)
            if path is None:
                self._hash_new_candidates()
                path = self._candidate_digests.get(digest)
            if path is not None:
                decision = self._decide_code(path)
                if decision is not None:
                    self._record_exec_code(*decision)
        except Exception as exc:  # noqa: BLE001 - must never break compile()
            self._fail(f"compile capture: {type(exc).__name__}: {exc}")

    def _hash_new_candidates(self) -> None:
        pending = self._code_candidates - set(self._candidate_digests.values())
        for path in sorted(pending):
            decision = self._decide_code(path)
            if decision is None:
                self._code_candidates.discard(path)
                continue
            try:
                with open(decision[0], "rb") as f:  # re-entrancy: caller is busy
                    digest = source_digest(f.read())
            except OSError:
                self._code_candidates.discard(path)
                continue
            self._candidate_digests.setdefault(digest, path)

    def _record_exec_code(self, real: str, external: bool, via: str | None) -> None:
        if real in self.exec_code or real in self.code or not os.path.isfile(real):
            return
        from .._hash import hash_file
        from ._external import external_info

        digest = hash_file(real)
        self.exec_code[real] = digest
        self.code[real] = digest
        if external:
            self.external[real] = external_info(real, via)
        # Recorded at close; journaled now so a kill does not lose it.
        journal = getattr(self.tracker, "_journal", None)
        if journal is not None:
            try:
                size = os.path.getsize(real)
            except OSError:
                size = None
            journal.captured_read(real, digest, size, self.external.get(real))


# EOF
