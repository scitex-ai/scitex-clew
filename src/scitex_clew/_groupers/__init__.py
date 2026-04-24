"""File-grouping API for DAG visualization.

Groupers collapse many related file nodes into a single visual group while
preserving every underlying hash. Every group carries a Merkle root so
group-level verification is cryptographically meaningful.

Public API::

    from scitex_clew.groupers import (
        FileEntry, Group,
        identity, drop_all_files,
        pattern_grouper, directory_grouper, session_bundle_grouper,
        auto, compose,
        resolve_spec, load_project_config,
    )

Spec form (JSON/YAML, works in CLI/MCP/file config)::

    {"type": "compose", "steps": [
        {"type": "pattern", "regex": "P\\d{2}"},
        {"type": "directory", "depth": 2},
        {"type": "auto"}
    ]}
"""
from ._base import FileEntry, Group, GroupOrEntry
from ._builtins import (
    auto,
    compose,
    directory_grouper,
    drop_all_files,
    identity,
    pattern_grouper,
    session_bundle_grouper,
)
from ._config import load_project_config
from ._spec import register_grouper, resolve_spec

__all__ = [
    "FileEntry",
    "Group",
    "GroupOrEntry",
    "auto",
    "compose",
    "directory_grouper",
    "drop_all_files",
    "identity",
    "pattern_grouper",
    "session_bundle_grouper",
    "load_project_config",
    "register_grouper",
    "resolve_spec",
]
