#!/usr/bin/env python3
"""Which directory is "the project" — clew's standalone resolver.

ONE CONCEPT, TWO IMPLEMENTATIONS, ONE SET OF TEST VECTORS
---------------------------------------------------------
scitex-session (>= 0.3.7) decides the project root of every ``@session``
run and records it in the start metadata clew receives
(``project_root`` / ``project_root_source`` / ``project_root_marker``).
Inside a session clew uses THAT value (see
:func:`scitex_clew._db._paths.project_root_info`). This module is the same
rule for when no session is active (the ``clew`` CLI, the Python API from
a notebook or a plain script). clew stays stdlib-only, so it cannot import
the session's resolver; it re-implements it instead, and the two are held
together by a shared conformance table:

    tests/scitex_clew/conformance/project-root-vectors.json      (clew)
    tests/scitex_session/conformance/project-root-vectors.json   (session)

(byte-identical)

A change to the detection rule MUST update this module, scitex-session's
``_lifecycle/_project_root.py`` AND the vector file in BOTH repositories.

Detection order (first match wins; the rule is reported as ``source``):

1. ``argument`` — an explicit root (``scitex_clew.project_root(...)`` /
   ``project_root=`` kwarg).
2. ``env`` — ``$SCITEX_SESSION_PROJECT_ROOT``. The same variable the
   session reads, deliberately: a clew-only override would let the two
   disagree, which is the drift this module exists to prevent.
   An explicit root must be an existing directory (else ``ValueError``).
3. ``git`` — the git work-tree root (``git rev-parse --show-toplevel``, the
   same discovery the session uses) unless it is at or above the search
   ceiling (a dotfiles repository at ``$HOME`` is not a research project).
4. ``marker`` — the nearest ancestor of the start directory (itself
   included) holding a :data:`PROJECT_MARKERS` entry.
5. ``cwd`` — the working directory, when it is a proper ancestor of the
   script's directory.
6. ``script_dir`` — the script's own directory, with a WARNING.

Without a script (the standalone case) the start is the working directory
and the last resort is the working directory itself (``cwd``, no warning).

The upward search stays strictly below ``$HOME`` (for starts under it) and
below ``/``, and does not cross a mount point. ``.scitex/`` is NOT a
marker: clew itself creates ``<cwd>/.scitex/clew/`` wherever it runs, so a
run from ``scripts/`` would otherwise pin every later root to ``scripts/``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from ._logging import getLogger

logger = getLogger(__name__)

__all__ = [
    "PROJECT_MARKERS",
    "PROJECT_ROOT_ENV",
    "git_toplevel",
    "resolve_project_root",
]

#: The session's variable, read by both implementations (see module docstring).
PROJECT_ROOT_ENV = "SCITEX_SESSION_PROJECT_ROOT"

#: Entries marking a directory as a project root, in reporting order. A tuple
#: means "all of these directories exist" (SciTeX research layout).
PROJECT_MARKERS: tuple[Any, ...] = (
    ".git",
    ".hg",
    ".svn",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "scitex/.scitex-structure-version",
    ("scripts", "config"),
)

_GIT_TIMEOUT_S = 10


def git_toplevel(where: Path, git: str | None = None) -> Path | None:
    """The git work-tree root holding ``where``, or ``None`` outside one.

    Uses the git binary itself (as scitex-session does) so both
    implementations see the same repository — ``.git`` files of worktrees
    and submodules, ``GIT_*`` discovery settings included. No git on PATH
    means no git root, exactly as in the session.
    """
    git = git if git is not None else shutil.which("git")
    if git is None:
        return None
    try:
        res = subprocess.run(
            [git, "-C", str(where), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("clew: git root lookup in %s failed (%s)", where, exc)
        return None
    top = res.stdout.strip()
    if res.returncode != 0 or not top:
        return None
    return Path(top).resolve()


def resolve_project_root(
    script: os.PathLike | None = None,
    *,
    explicit: os.PathLike | None = None,
    cwd: os.PathLike | None = None,
    environ: Mapping[str, str] | None = None,
    git: str | None = None,
) -> dict[str, Any]:
    """Resolve the project root (see module docstring for the order).

    Returns ``{"project_root": str, "project_root_source": str,
    "project_root_marker": str or None}`` — the same keys scitex-session
    records in its run metadata.

    Raises
    ------
    ValueError
        If an explicit root (argument or ``$SCITEX_SESSION_PROJECT_ROOT``)
        is not an existing directory.
    """
    environ = os.environ if environ is None else environ
    cwd_path = Path(cwd if cwd is not None else os.getcwd()).resolve()
    script_path = Path(script).resolve() if script is not None else None
    start = script_path.parent if script_path is not None else cwd_path

    if explicit is not None and str(explicit) != "":
        return _explicit(explicit, "argument", "project_root argument", start)
    from_env = (environ.get(PROJECT_ROOT_ENV) or "").strip()
    if from_env:
        return _explicit(from_env, "env", f"${PROJECT_ROOT_ENV}", start)

    ceiling = _ceiling(start, environ)

    git_root = git_toplevel(start, git)
    if git_root is not None and _strictly_below(git_root, ceiling):
        return _result(git_root, "git")

    for directory in _candidates(start, ceiling):
        marker = _marker_in(directory)
        if marker is not None:
            return _result(directory, "marker", marker)

    if script_path is None:
        return _result(cwd_path, "cwd")
    if (
        cwd_path != start
        and _is_ancestor(cwd_path, start)
        and _strictly_below(cwd_path, ceiling)
    ):
        return _result(cwd_path, "cwd")

    logger.warning(
        "clew: no project root found for %s (no git repository, no project "
        "marker such as pyproject.toml or config/ + scripts/ in its "
        "ancestors, and the working directory %s does not contain it); using "
        "the script's directory %s. Set $%s, add a marker at the project "
        "directory, or run from it.",
        script_path,
        cwd_path,
        start,
        PROJECT_ROOT_ENV,
    )
    return _result(start, "script_dir")


def _result(root: Path, source: str, marker: str | None = None) -> dict[str, Any]:
    return {
        "project_root": str(root),
        "project_root_source": source,
        "project_root_marker": marker,
    }


def _explicit(value: Any, source: str, what: str, start: Path) -> dict[str, Any]:
    path = Path(os.path.expanduser(str(value))).resolve()
    if not path.is_dir():
        raise ValueError(f"{what} {str(value)!r} is not an existing directory")
    if not _is_ancestor(path, start):
        logger.warning(
            "clew: %s %s does not contain %s; files beside it are outside the project",
            what,
            path,
            start,
        )
    return _result(path, source)


def _home(environ: Mapping[str, str]) -> Path | None:
    home = environ.get("HOME") or os.path.expanduser("~")
    if not home or home == "~":
        return None
    return Path(home).resolve()


def _ceiling(start: Path, environ: Mapping[str, str]) -> Path:
    """The directory the upward search must stay strictly below."""
    home = _home(environ)
    if home is not None and home != Path(home.anchor) and _is_ancestor(home, start):
        return home
    return Path(start.anchor)


def _candidates(start: Path, ceiling: Path) -> Iterator[Path]:
    """``start`` and its ancestors strictly below ``ceiling``, same filesystem."""
    if not _strictly_below(start, ceiling):
        return
    try:
        device = start.stat().st_dev
    except OSError:
        return
    current = start
    while _strictly_below(current, ceiling):
        yield current
        parent = current.parent
        try:
            if parent.stat().st_dev != device:
                return  # mount point: the parent is another filesystem
        except OSError:
            return
        current = parent


def _marker_in(directory: Path) -> str | None:
    for marker in PROJECT_MARKERS:
        if isinstance(marker, tuple):
            if all((directory / name).is_dir() for name in marker):
                return " + ".join(f"{name}/" for name in marker)
        elif os.path.lexists(directory / marker):
            return marker
    return None


def _is_ancestor(ancestor: Path, path: Path) -> bool:
    return ancestor == path or ancestor in path.parents


def _strictly_below(path: Path, ceiling: Path) -> bool:
    return path != ceiling and ceiling in path.parents


# EOF
