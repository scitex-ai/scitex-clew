#!/usr/bin/env python3
"""Project-relative paths in the claim exports a reader sees.

``claims.json`` (``export_claims_json``) and the unified render feed
(``export_manuscript_claims``) travel in Live Paper bundles. The store keeps
each path as recorded — usually absolute on the machine that built the paper
(``/home/<user>/proj/<paper>/.worktrees/<agent>/data/x.json``) — which tells a
reader about the authors' host and nothing about the paper. The exports name
in-project files relative to the project root instead, with the rule the
evidence bundle and the slice already use (:func:`_exchange._relpaths.
portable_path`): inside the root -> repo-relative POSIX path; outside it ->
kept absolute and flagged ``<field>_external: true``, never disguised as
part of the project. The store itself is unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .._exchange._relpaths import portable_path

__all__ = ["PATHS_NOTE", "export_root", "portable_fields"]

#: Top-level description of the path convention, written into both exports.
PATHS_NOTE = {
    "relative_to": "project_root",
    "external": (
        "paths outside the project root stay absolute and carry <field>_external: true"
    ),
}


def export_root() -> Path:
    """The project root the exports are relative to (clew's project root)."""
    from .._db import _core as _db_core

    return Path(_db_core._find_project_root()).resolve()


def portable_fields(entry: dict, fields: Iterable[str], root: Path) -> dict:
    """Rewrite ``fields`` of ``entry`` in place; add ``<field>_external``."""
    for name in fields:
        text, external = portable_path(entry.get(name), root)
        entry[name] = text
        entry[f"{name}_external"] = external
    return entry


# EOF
