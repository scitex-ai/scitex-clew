#!/usr/bin/env python3
"""Which checkout a bundle is checked against — never silently the wrong one.

``clew bundle verify`` / ``rerun`` compare a bundle with the files of ONE
project tree. Before this module the tree was simply the working directory
(``--project-root`` defaulted to ``.``), whatever the bundle's own location:
verifying ``<worktree>/.scitex/clew/evidence-bundle.json`` from the main
checkout hashed the MAIN checkout's files, and a stale bundle reported OK
because the main checkout still held the old outputs. A false OK.

The rule now (no explicit root given):

* the bundle's HOME — the project it belongs to:
  ``<R>/.scitex/clew/<file>`` → ``R`` (where ``clew bundle export`` writes);
  otherwise the git WORK TREE holding the bundle (``git rev-parse
  --show-toplevel``: a linked worktree is its own tree, never the shared
  ``--git-common-dir``); otherwise none (a loose bundle file, e.g. a
  download);
* HERE — the project the working directory is in (the standard resolver,
  :func:`scitex_clew._core._project_root.resolve_project_root`);
* home and here agree → that tree; no home → here; they DISAGREE →
  :class:`ProjectRootAmbiguous`. Two candidate trees are never resolved by
  guessing: the caller names one with ``--project-root``.

The chosen root and the rule that chose it are always reported.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .._core._project_root import (
    _ceiling,
    _strictly_below,
    git_toplevel,
    resolve_project_root,
)

__all__ = ["ProjectRootAmbiguous", "bundle_home", "resolve_bundle_root"]


class ProjectRootAmbiguous(ValueError):
    """The bundle belongs to one project tree and the working directory to another."""


def bundle_home(bundle_path: str | os.PathLike) -> tuple[Path, str] | None:
    """``(root, rule)`` of the project the bundle file lives in, or ``None``.

    ``rule`` is ``bundle_location`` (``<root>/.scitex/clew/<file>``) or
    ``bundle_git`` (the git work tree holding the file, below the same
    ``$HOME`` ceiling the project-root resolver uses).
    """
    path = Path(bundle_path).expanduser().resolve()
    parent = path.parent
    if parent.name == "clew" and parent.parent.name == ".scitex":
        return parent.parent.parent, "bundle_location"
    if not parent.is_dir():
        return None
    top = git_toplevel(parent)
    if top is not None and _strictly_below(top, _ceiling(parent, os.environ)):
        return top, "bundle_git"
    return None


def resolve_bundle_root(
    bundle_path: str | os.PathLike,
    project_root: str | os.PathLike | None = None,
    *,
    cwd: str | os.PathLike | None = None,
) -> dict[str, Any]:
    """The tree to check ``bundle_path`` against (see module docstring).

    Returns ``{"project_root", "project_root_source", "bundle_home"}``;
    ``bundle_home`` is the bundle's own project (or ``None``), reported so an
    explicit root that differs from it is visible.

    Raises
    ------
    ProjectRootAmbiguous
        No explicit root, and the bundle's project differs from the
        working directory's.
    ValueError
        An explicit root is not an existing directory.
    """
    home = bundle_home(bundle_path)
    home_str = str(home[0]) if home else None
    if project_root is not None and str(project_root) != "":
        root = Path(project_root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"--project-root {str(project_root)!r} is not a directory")
        return {"project_root": str(root), "project_root_source": "argument",
                "bundle_home": home_str}  # fmt: skip
    here = resolve_project_root(None, cwd=cwd)
    here_root = Path(here["project_root"])
    if home is None:
        return {"project_root": str(here_root),
                "project_root_source": f"cwd:{here['project_root_source']}",
                "bundle_home": None}  # fmt: skip
    home_root, rule = home
    if home_root == here_root:
        return {"project_root": str(home_root), "project_root_source": rule,
                "bundle_home": home_str}  # fmt: skip
    raise ProjectRootAmbiguous(
        f"ambiguous project root: the bundle {Path(bundle_path)} belongs to "
        f"{home_root} ({rule}) but the working directory is in {here_root} "
        f"({here['project_root_source']}). Refusing to guess which tree to "
        "check; pass --project-root explicitly."
    )


# EOF
