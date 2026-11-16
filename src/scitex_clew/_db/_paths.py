#!/usr/bin/env python3
"""Project-root resolution for clew's regenerable file artifacts.

clew no longer has a database FILE. Its four stores resolve through
``scitex_dev.store.host_store()`` — the per-host PostgreSQL instance — so
there is nothing here that resolves "where the database lives"; that
question has exactly one answer and the primitive owns it.

What remains is the project-root walk, which is still needed for the two
things clew genuinely writes to disk: the regenerable ``claims.json``
export artifact, and the manuscript-hints feed clew merges into.
"""

from __future__ import annotations

import functools
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

__all__ = [
    "_default_claims_json_path",
    "_default_hints_json_path",
    "_find_project_root",
    "project_root",
    "project_root_override",
    "with_project_root",
]


#: Explicit project root for the current context (see :func:`project_root`).
_PROJECT_ROOT_OVERRIDE: ContextVar = ContextVar("clew_project_root", default=None)


def project_root_override() -> Path | None:
    """The root set by an enclosing :func:`project_root` block, else None."""
    return _PROJECT_ROOT_OVERRIDE.get()


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


def _find_project_root() -> Path:
    """Walk up from cwd to find the project root (contains .git or pyproject.toml).

    An explicit root set via :func:`project_root` wins.
    """
    override = _PROJECT_ROOT_OVERRIDE.get()
    if override is not None:
        return override
    current = Path.cwd()
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
