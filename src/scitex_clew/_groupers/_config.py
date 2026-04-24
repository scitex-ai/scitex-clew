"""Load per-project grouper config from ``.scitex/clew/config.yaml``.

Walks upward from CWD looking for a directory that contains
``.scitex/clew/config.yaml`` (or ``config.json``). Returns the parsed
top-level dict, or ``{}`` if no config found.

Schema::

    grouper:
      type: compose
      steps:
        - {type: pattern, regex: 'P\\d{2}'}
        - {type: auto}

Other top-level keys are preserved for future use (e.g. rendering
defaults, path_mode).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_FILENAMES = ("config.yaml", "config.yml", "config.json")


def _find_config_dir(start: Path | None = None) -> Path | None:
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        probe = parent / ".scitex" / "clew"
        if probe.is_dir():
            for name in CONFIG_FILENAMES:
                if (probe / name).is_file():
                    return probe
    return None


def load_project_config(start: Path | None = None) -> dict[str, Any]:
    """Return the project config dict, or ``{}`` if none found."""
    cfg_dir = _find_config_dir(start)
    if cfg_dir is None:
        return {}

    for name in CONFIG_FILENAMES:
        path = cfg_dir / name
        if not path.is_file():
            continue
        text = path.read_text()
        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError as e:
                raise ImportError(
                    f"PyYAML required to read {path}. Install with `pip install pyyaml`"
                ) from e
            return yaml.safe_load(text) or {}
        return json.loads(text) if text.strip() else {}
    return {}
