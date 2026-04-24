"""Public alias for :mod:`scitex_clew._groupers`.

Allows ``from scitex_clew.groupers import ...`` without exposing the
underscore-prefixed internal module.
"""
from ._groupers import (
    FileEntry,
    Group,
    GroupOrEntry,
    auto,
    compose,
    directory_grouper,
    drop_all_files,
    identity,
    load_project_config,
    pattern_grouper,
    register_grouper,
    resolve_spec,
    session_bundle_grouper,
)

__all__ = [
    "FileEntry",
    "Group",
    "GroupOrEntry",
    "auto",
    "compose",
    "directory_grouper",
    "drop_all_files",
    "identity",
    "load_project_config",
    "pattern_grouper",
    "register_grouper",
    "resolve_spec",
    "session_bundle_grouper",
]
