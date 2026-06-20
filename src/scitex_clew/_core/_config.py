#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Layered config resolution for scitex-clew (SciTeX ``.scitex/<pkg>`` convention).

Follows the ecosystem local-state convention used by ``scitex-todo``
(``_paths.py``) and the in-package grouper loader (``_groupers/_config.py``):
the package short name is ``clew`` (``scitex-`` prefix stripped), so config
lives under ``.scitex/clew/``.

Resolution (lowest precedence first; each layer deep-merged over the previous)::

    code defaults  <  user scope  <  project scope  <  explicit

    user scope:     ``$SCITEX_DIR/clew/``      (default ``~/.scitex/clew/``)
    project scope:  ``<git-root>/.scitex/clew/``
    explicit:       a ``--config`` path (file or dir), highest priority

Within ONE scope dir, ``config.yaml`` is the base and every
``config/*.yaml`` / ``config/*.yml`` file is deep-merged on top (sorted by
name). This is the ``{config.yaml, config/}`` shape: a single file for the
simple case, a ``config/`` directory when you want to split settings.

Project keys override user keys *per key* (deep merge), so a project can
tune one setting without restating the rest.

Fail-loud (operator rule: no silent fallbacks):
- Absent config is NOT an error -> ``{}`` (callers apply code defaults).
- Malformed YAML, a non-mapping top level, or an explicit-but-missing
  ``--config`` path RAISES.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

#: Package short name (``scitex-clew`` with the ``scitex-`` prefix stripped).
PKG_SHORT = "clew"

#: Env var that relocates the user-scope root (ecosystem convention).
ENV_DIR = "SCITEX_DIR"

#: Single-file config basenames, in precedence order (``.yaml`` wins).
CONFIG_BASENAMES = ("config.yaml", "config.yml")

#: Sub-directory whose ``*.yaml`` / ``*.yml`` files are merged on top.
CONFIG_SUBDIR = "config"


def _user_root() -> Path:
    """User-scope ``.scitex/clew`` root, honouring ``$SCITEX_DIR``."""
    base = os.environ.get(ENV_DIR)
    root = Path(base).expanduser() if base else Path.home() / ".scitex"
    return root / PKG_SHORT


def _find_git_root(start: Path) -> Optional[Path]:
    """Walk up from ``start`` looking for a ``.git`` entry."""
    cur = start.resolve()
    for parent in (cur, *cur.parents):
        if (parent / ".git").exists():
            return parent
    return None


def _project_root(start: Optional[Path] = None) -> Optional[Path]:
    """Project-scope ``<git-root>/.scitex/clew`` (or ``None`` outside a repo)."""
    git_root = _find_git_root(start or Path.cwd())
    return (git_root / ".scitex" / PKG_SHORT) if git_root else None


def _read_yaml(path: Path) -> Dict[str, Any]:
    """Parse one YAML file into a mapping (fail-loud on bad shape)."""
    try:
        import yaml
    except ImportError as e:  # pragma: no cover - environment-dependent
        raise ImportError(
            f"PyYAML is required to read {path}. Install with `uv pip install pyyaml`."
        ) from e
    text = path.read_text()
    if not text.strip():
        return {}
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"Config {path} must be a YAML mapping at the top level, "
            f"got {type(data).__name__}."
        )
    return data


def _deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``over`` onto ``base`` (``over`` wins per key)."""
    out = dict(base)
    for key, val in over.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _scope_files(scope_dir: Path) -> List[Path]:
    """Ordered config files within one scope: ``config.yaml`` then ``config/*``."""
    files: List[Path] = []
    for name in CONFIG_BASENAMES:
        candidate = scope_dir / name
        if candidate.is_file():
            files.append(candidate)
            break  # config.yaml takes precedence over config.yml
    sub = scope_dir / CONFIG_SUBDIR
    if sub.is_dir():
        nested = [p for ext in ("*.yaml", "*.yml") for p in sub.glob(ext)]
        files.extend(sorted(nested, key=lambda p: p.name))
    return files


def _load_scope(scope_dir: Optional[Path]) -> Dict[str, Any]:
    """Merge ``config.yaml`` + ``config/*.y{,a}ml`` within one scope dir."""
    if scope_dir is None or not scope_dir.is_dir():
        return {}
    merged: Dict[str, Any] = {}
    for path in _scope_files(scope_dir):
        merged = _deep_merge(merged, _read_yaml(path))
    return merged


def load_config(
    *,
    start: Optional[Path] = None,
    explicit: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Resolve the layered clew config dict (user < project < explicit).

    Parameters
    ----------
    start : pathlib.Path, optional
        Directory to resolve the project scope from (default: CWD). The
        project scope is ``<git-root-of-start>/.scitex/clew``.
    explicit : str or pathlib.Path, optional
        A ``--config`` override. A directory is treated like a scope
        (``config.yaml`` + ``config/``); a file is read directly. Must
        exist (a missing explicit path raises).

    Returns
    -------
    dict
        The merged config mapping (``{}`` when nothing is configured).
    """
    cfg: Dict[str, Any] = {}
    cfg = _deep_merge(cfg, _load_scope(_user_root()))
    cfg = _deep_merge(cfg, _load_scope(_project_root(start)))
    if explicit is not None:
        epath = Path(explicit).expanduser()
        if not epath.exists():
            raise FileNotFoundError(f"--config path does not exist: {epath}")
        if epath.is_dir():
            cfg = _deep_merge(cfg, _load_scope(epath))
        else:
            cfg = _deep_merge(cfg, _read_yaml(epath))
    return cfg


__all__ = [
    "PKG_SHORT",
    "ENV_DIR",
    "load_config",
]

# EOF
