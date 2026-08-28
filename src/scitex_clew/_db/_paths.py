#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Path resolution for clew's store file — extracted from `_core.py`.

Pure path-resolution helpers with no `scitex_dev.store` / sqlite3
dependency of their own (the WAL-safe rename they call into still uses
raw sqlite3 — see `_migrate_rename.py`, a deliberate exception documented
there). Split out of `_core.py` only to keep that file under the
project's 512-line limit; no behavior changed by the split.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import Optional, Union

from ._migrate_rename import wal_safe_rename


def _find_project_root() -> Path:
    """Walk up from cwd to find the project root (contains .git or pyproject.toml)."""
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
    is regenerable from the DB at any time, so it lives there alongside
    ``clew.db``.

    The resolved path is **just the path** — this function does not
    write or read the file. ``scitex_clew.export_claims_json()`` writes
    to it.
    """
    return project_root / ".scitex" / "clew" / "runtime" / "claims.json"


def _default_db_path(project_root: Path) -> Path:
    """Resolve the default database path under ``runtime/``.

    Returns ``<project_root>/.scitex/clew/runtime/clew.db`` per the
    fleet-wide ``.scitex/<pkg>/runtime/<pkg>.db`` convention (clew is a
    reference implementation). The ``.db`` extension is also required for
    scitex-io interop — its load dispatch registers ``.db`` → SQLite3 but
    has no handler for ``.sqlite``.

    Transparent auto-rename migration: if the canonical ``clew.db`` does
    not yet exist but a predecessor does, rename the predecessor to
    ``clew.db`` on first access (WAL-safe — see
    ``_migrate_rename.wal_safe_rename``) and emit a one-time deprecation
    warning. Predecessors are checked in order:

    1. ``<root>/.scitex/clew/runtime/db.sqlite`` (the previous default)
    2. ``<root>/.scitex/clew/db.sqlite`` (legacy flat location)
    """
    new = project_root / ".scitex" / "clew" / "runtime" / "clew.db"
    if new.exists():
        return new

    predecessors = [
        project_root / ".scitex" / "clew" / "runtime" / "db.sqlite",
        project_root / ".scitex" / "clew" / "db.sqlite",
    ]
    for old in predecessors:
        if old.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            wal_safe_rename(old, new)
            warnings.warn(
                f"Renamed database from {old} to {new}. "
                "The legacy 'db.sqlite' name is deprecated and will be "
                "removed in a future version. Set SCITEX_CLEW_DB_PATH to "
                "suppress.",
                DeprecationWarning,
                stacklevel=2,
            )
            break
    return new


def resolve_db_path(
    db_path: Optional[Union[str, Path]] = None,
) -> "tuple[Path, str]":
    """Resolve the store path via the three-tier precedence.

    Parameters
    ----------
    db_path : str or Path, optional
        Explicit store path (tier 1). When ``None``, falls through to the
        ``SCITEX_CLEW_DB_PATH`` environment variable (tier 2) and finally
        the project-root walk from the current working directory (tier 3).

    Returns
    -------
    tuple of (Path, str)
        The resolved path and a human-readable label of the tier that
        produced it. This function only resolves — it neither creates
        nor requires the file; read-side callers (e.g. ``render_dag``)
        use the label to fail loud when the store is missing.
    """
    if db_path is not None:
        return Path(db_path), "explicit db_path argument"
    env_path = os.environ.get("SCITEX_CLEW_DB_PATH")
    if env_path:
        return Path(env_path), "SCITEX_CLEW_DB_PATH environment variable"
    return (
        _default_db_path(_find_project_root()),
        "project-root walk from the current working directory",
    )


# EOF
