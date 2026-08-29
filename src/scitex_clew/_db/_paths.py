#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project-root resolution for clew's regenerable file artifacts.

clew no longer has a database FILE. Its four stores resolve through
``scitex_dev.store.host_store()`` — the per-host PostgreSQL instance — so
there is nothing here that resolves "where the database lives"; that
question has exactly one answer and the primitive owns it.

What remains is the project-root walk, which is still needed for the one
thing clew genuinely writes to disk: the regenerable ``claims.json``
export artifact.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["_default_claims_json_path", "_find_project_root"]


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
    is regenerable from the store at any time.

    The resolved path is **just the path** — this function does not
    write or read the file. ``scitex_clew.export_claims_json()`` writes
    to it.
    """
    return project_root / ".scitex" / "clew" / "runtime" / "claims.json"


# EOF
