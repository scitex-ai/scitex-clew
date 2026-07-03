#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registered-source manifest WRITER — the human-run, sanctioned write path.

Only this module (and its ``clew register-source`` CLI wrapper) writes the
manifest. Verify/export never write it. Registration is idempotent: re-
registering a path updates its pinned hash.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional, Union

from .._db._core import _find_project_root
from ._manifest import (
    SOURCES_SCHEMA,
    full_sha256,
    load_sources_manifest,
    resolve_sources_path,
)


def _write_manifest_dict(path: Path, sources: List[dict], signature) -> None:
    """Serialize the manifest dict to ``path`` (creates parents)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SOURCES_SCHEMA,
        "sources": sources,
        "signature": signature,
    }
    path.write_text(json.dumps(payload, indent=2))


def _load_raw(path: Path) -> dict:
    """Read the raw manifest dict from ``path`` (empty skeleton if absent)."""
    if not path.exists():
        return {"schema": SOURCES_SCHEMA, "sources": [], "signature": None}
    return json.loads(path.read_text())


def _relpath(file_path: Union[str, Path], root: Path) -> str:
    """Best-effort relative path of ``file_path`` from ``root``."""
    ap = Path(file_path).resolve()
    try:
        return str(ap.relative_to(root))
    except ValueError:
        # Outside the project root — store the path as-is (still resolvable).
        return str(ap)


def register_source(
    files: Union[str, Path, List[Union[str, Path]]],
    *,
    sources_path: Optional[Union[str, Path]] = None,
    root: Optional[Union[str, Path]] = None,
) -> Path:
    """Register one or more files as trusted sources (idempotent).

    Computes each file's full sha256 and appends/updates a ``{path, sha256}``
    entry in the manifest, creating it at the tier-3 path if absent. Re-
    registering a path updates its hash (idempotent).

    Parameters
    ----------
    files : str | Path | list
        File(s) to register. Each must exist (its content is hashed now).
    sources_path : str | Path, optional
        Explicit manifest path (else tier-2 env / tier-3 default).
    root : str | Path, optional
        Project root that relpaths are stored against (default: cwd walk).

    Returns
    -------
    Path
        The manifest path written to (absolute).
    """
    if isinstance(files, (str, Path)):
        files = [files]
    resolved, _tier = resolve_sources_path(sources_path)
    resolved = Path(resolved).resolve()
    root_path = Path(root).resolve() if root is not None else _find_project_root()

    raw = _load_raw(resolved)
    sources = raw.get("sources") or []
    by_path = {str(e["path"]): e for e in sources if isinstance(e, dict)}

    for f in files:
        fp = Path(f)
        if not fp.exists():
            raise FileNotFoundError(
                f"Cannot register a source that does not exist: {fp}"
            )
        rel = _relpath(fp, root_path)
        by_path[rel] = {"path": rel, "sha256": full_sha256(fp)}

    ordered = [by_path[k] for k in sorted(by_path)]
    _write_manifest_dict(resolved, ordered, raw.get("signature"))
    return resolved


def unregister_source(
    files: Union[str, Path, List[Union[str, Path]]],
    *,
    sources_path: Optional[Union[str, Path]] = None,
    root: Optional[Union[str, Path]] = None,
) -> Path:
    """Remove one or more registered sources (idempotent; no-op if absent)."""
    if isinstance(files, (str, Path)):
        files = [files]
    resolved, _tier = resolve_sources_path(sources_path)
    resolved = Path(resolved).resolve()
    root_path = Path(root).resolve() if root is not None else _find_project_root()

    raw = _load_raw(resolved)
    sources = raw.get("sources") or []
    drop = {_relpath(f, root_path) for f in files}
    kept = [
        e
        for e in sources
        if isinstance(e, dict) and str(e.get("path")) not in drop
    ]
    _write_manifest_dict(resolved, kept, raw.get("signature"))
    return resolved


def list_sources(
    *,
    sources_path: Optional[Union[str, Path]] = None,
    root: Optional[Union[str, Path]] = None,
) -> List[dict]:
    """Return the manifest entries with a per-entry validity check.

    Each dict carries ``path``, ``sha256``, ``abspath``, ``valid`` (bool), and
    ``reason`` (``OK`` / ``TAMPERED`` / ``MISSING``). Returns ``[]`` when no
    manifest exists.
    """
    manifest = load_sources_manifest(sources_path, root=root)
    if manifest is None:
        return []
    return [e.to_dict() for e in manifest.entries]


# EOF
