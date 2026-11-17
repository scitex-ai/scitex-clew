#!/usr/bin/env python3
"""Project-root resolution for clew's on-disk state.

clew no longer has a database FILE. Its four stores resolve through
``scitex_dev.store.host_store()`` — the per-host PostgreSQL instance — so
there is nothing here that resolves "where the database lives"; that
question has exactly one answer and the primitive owns it.

What remains is the project root, which decides where clew's on-disk state
lives (``.scitex/clew/project-id`` — hence the store scope — the
regenerable ``claims.json`` export, the manuscript-hints feed) and which
project-scope config applies. Inside a scitex-session run it is the root
the session recorded; otherwise the shared rule in
:mod:`scitex_clew._core._project_root`.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .._core._project_root import resolve_project_root

__all__ = [
    "_default_claims_json_path",
    "_default_hints_json_path",
    "_find_project_root",
    "clear_session_project_root",
    "project_root",
    "project_root_info",
    "project_root_override",
    "set_session_project_root",
    "with_project_root",
]


#: Explicit project root for the current context (see :func:`project_root`).
_PROJECT_ROOT_OVERRIDE: ContextVar = ContextVar("clew_project_root", default=None)

#: The root recorded by the active scitex-session run (set by
#: ``on_session_start``, cleared by ``on_session_close``). Process-wide, like
#: the session itself and clew's tracker.
_SESSION_ROOT: dict | None = None


def set_session_project_root(metadata: dict | None, script_path=None) -> dict:
    """Adopt the active session's project root (single source of truth).

    scitex-session >= 0.3.7 records ``project_root`` (+ ``_source`` /
    ``_marker``) in the start metadata. An older session manager sends no
    root; clew then resolves one with the SAME rule from the session's
    script, so the run is still scoped the way the session would scope it.
    Returns the adopted info.
    """
    global _SESSION_ROOT
    meta = metadata if isinstance(metadata, dict) else {}
    root = meta.get("project_root")
    if root:
        info = {
            "project_root": str(Path(root).resolve()),
            "project_root_source": meta.get("project_root_source") or "session",
            "project_root_marker": meta.get("project_root_marker"),
        }
    else:
        info = resolve_project_root(script_path, cwd=meta.get("cwd"))
    _SESSION_ROOT = {**info, "via": "session"}
    return dict(_SESSION_ROOT)


def clear_session_project_root() -> None:
    """Forget the session's root once the session has closed."""
    global _SESSION_ROOT
    _SESSION_ROOT = None


def project_root_override() -> Path | None:
    """The root set by a :func:`project_root` block or the active session."""
    override = _PROJECT_ROOT_OVERRIDE.get()
    if override is not None:
        return override
    if _SESSION_ROOT is not None:
        return Path(_SESSION_ROOT["project_root"])
    return None


@contextmanager
def project_root(root: str | Path | None):
    """Run clew calls against ``root``'s project without ``chdir``.

    Inside the block, the project scope (claims, runs, the per-project id and
    claims.json export location) resolves from ``root`` instead of the
    current working directory. ``None`` is a no-op. Context-local, so it is
    safe across threads / asyncio tasks (unlike ``os.chdir``).
    """
    if root is None:
        yield None
        return
    token = _PROJECT_ROOT_OVERRIDE.set(Path(root).resolve())
    try:
        yield _PROJECT_ROOT_OVERRIDE.get()
    finally:
        _PROJECT_ROOT_OVERRIDE.reset(token)


def with_project_root(fn):
    """Give ``fn`` an optional ``project_root=`` kwarg (see :func:`project_root`)."""

    @functools.wraps(fn)
    def wrapper(*args, project_root: str | Path | None = None, **kwargs):
        with _project_root_cm(project_root):
            return fn(*args, **kwargs)

    return wrapper


_project_root_cm = project_root


def project_root_info(start: str | Path | None = None) -> dict:
    """The project root clew uses here, and WHICH RULE chose it.

    Order: an explicit :func:`project_root` block > the active
    scitex-session's recorded root > the standalone rule of
    :mod:`scitex_clew._core._project_root`, resolved from ``start``
    (default: the working directory).

    Returns ``project_root``, ``project_root_source`` (the rule:
    ``argument`` / ``env`` / ``git`` / ``marker`` / ``cwd`` /
    ``script_dir``), ``project_root_marker`` and ``via`` (``argument`` /
    ``session`` / ``detected``).
    """
    override = _PROJECT_ROOT_OVERRIDE.get()
    if override is not None:
        return {
            "project_root": str(override),
            "project_root_source": "argument",
            "project_root_marker": None,
            "via": "argument",
        }
    if _SESSION_ROOT is not None:
        return dict(_SESSION_ROOT)
    return {**resolve_project_root(None, cwd=start), "via": "detected"}


def _find_project_root() -> Path:
    """The project root for the store scope, claims.json, hints and config.

    See :func:`project_root_info` for the order.
    """
    return Path(project_root_info()["project_root"])


def _legacy_project_root(cwd: str | Path | None = None) -> Path:
    """Where clew <= 0.24.3 put ``.scitex/clew/`` — for migration warnings ONLY.

    The old walk: nearest ancestor of cwd holding ``.git`` or
    ``pyproject.toml`` (no ``$HOME`` ceiling), else cwd itself.
    """
    current = Path(cwd if cwd is not None else Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return current


def _default_claims_json_path(project_root: Path) -> Path:
    """Resolve the default canonical claims.json artifact path.

    Returns ``<project_root>/.scitex/clew/runtime/claims.json`` per the
    ecosystem local-state-directories convention. The runtime/ subdir
    is the canonical home for regenerable per-host outputs — claims.json
    is regenerable from the store at any time.

    The resolved path is **just the path** — this function does not
    write or read the file. ``scitex_clew.export_claims_json()`` writes
    to it.
    """
    return project_root / ".scitex" / "clew" / "runtime" / "claims.json"


def _default_hints_json_path(project_root: Path) -> Path:
    """Resolve the default canonical manuscript-hints artifact path.

    Returns ``<project_root>/.scitex/writer/hints.json`` — this is
    scitex-writer's namespace (NOT ``.scitex/clew/``), because the artifact
    is writer's manuscript-hints FEED (schema ``manuscript-hints/1``); clew
    is one of several producers that MERGE-BY-SOURCE into it. See
    :func:`scitex_clew._claim._hints.export_manuscript_hints`.

    The resolved path is **just the path** — this function does not write or
    read the file.
    """
    return project_root / ".scitex" / "writer" / "hints.json"


# EOF
