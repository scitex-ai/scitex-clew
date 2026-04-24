"""Built-in file groupers.

A grouper is ``Callable[[List[FileEntry]], List[GroupOrEntry]]`` — it takes
all files for one session (both roles) and returns a mixed list of
ungrouped entries and groups. Renderers treat both uniformly.

Design rules:
- Grouping never crosses session boundaries (the caller splits by session).
- Grouping never hides files — a group carries every member hash.
- Roles don't mix inside a group (``identity`` for role='input' + 'output').
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from collections.abc import Callable

from ._base import FileEntry, Group, GroupOrEntry

Grouper = Callable[[list[FileEntry]], list[GroupOrEntry]]


def identity() -> Grouper:
    """No grouping — every file stays its own node."""

    def _g(entries: list[FileEntry]) -> list[GroupOrEntry]:
        return list(entries)

    return _g


def drop_all_files() -> Grouper:
    """Render no file nodes at all — scripts-only DAG."""

    def _g(entries: list[FileEntry]) -> list[GroupOrEntry]:
        return []

    return _g


def pattern_grouper(regex: str, placeholder: str = "{X}") -> Grouper:
    """Collapse files whose names agree after replacing ``regex`` with ``placeholder``.

    Example: ``pattern_grouper(r"P\\d{2}")`` groups ``P01_effect.png``,
    ``P02_effect.png``, ..., ``P15_effect.png`` into one node labeled
    ``P{X}_effect.png (×15)``.
    """
    pat = re.compile(regex)

    def _g(entries: list[FileEntry]) -> list[GroupOrEntry]:
        buckets: dict = defaultdict(list)
        singles: list[FileEntry] = []
        for e in entries:
            name = os.path.basename(e.path)
            normalized = pat.sub(placeholder, name)
            if normalized == name:
                singles.append(e)
            else:
                buckets[(e.role, normalized)].append(e)

        out: list[GroupOrEntry] = list(singles)
        for (role, norm), members in buckets.items():
            if len(members) < 2:
                out.extend(members)
                continue
            out.append(
                Group(
                    members=sorted(members, key=lambda m: m.path),
                    label=f"{norm} (×{len(members)})",
                    kind=f"pattern:{regex}",
                )
            )
        return out

    return _g


def directory_grouper(min_size: int = 10, depth: int = 1) -> Grouper:
    """Collapse ≥``min_size`` files sharing the same parent directory.

    ``depth`` controls how many trailing path components to keep as the
    group label (default 1 = just the basename of the dir).
    """

    def _g(entries: list[FileEntry]) -> list[GroupOrEntry]:
        buckets: dict = defaultdict(list)
        for e in entries:
            parent = os.path.dirname(e.path)
            buckets[(e.role, parent)].append(e)

        out: list[GroupOrEntry] = []
        for (role, parent), members in buckets.items():
            if len(members) < min_size:
                out.extend(members)
                continue
            parts = parent.rstrip("/").split("/")
            label_dir = "/".join(parts[-depth:]) if parts else parent
            out.append(
                Group(
                    members=sorted(members, key=lambda m: m.path),
                    label=f"{label_dir}/ (×{len(members)})",
                    kind="directory",
                )
            )
        return out

    return _g


def session_bundle_grouper(max_files: int = 3) -> Grouper:
    """If a session has ≤``max_files`` per role, keep them; otherwise bundle.

    Useful as the outermost wrapper to ensure even ungroupable per-session
    dumps don't flood the diagram.
    """

    def _g(entries: list[FileEntry]) -> list[GroupOrEntry]:
        by_role: dict = defaultdict(list)
        for e in entries:
            by_role[e.role].append(e)

        out: list[GroupOrEntry] = []
        for role, members in by_role.items():
            if len(members) <= max_files:
                out.extend(members)
                continue
            out.append(
                Group(
                    members=sorted(members, key=lambda m: m.path),
                    label=f"{role} bundle (×{len(members)})",
                    kind="session_bundle",
                )
            )
        return out

    return _g


def auto(
    pattern_regexes=(r"P\d+", r"\d{4}-\d{2}-\d{2}", r"fold_\d+"),
    directory_min: int = 10,
    bundle_max: int = 3,
) -> Grouper:
    """Sensible default: try patterns → directory bundle → per-session bundle."""
    steps = [pattern_grouper(r) for r in pattern_regexes]
    steps.append(directory_grouper(min_size=directory_min))
    steps.append(session_bundle_grouper(max_files=bundle_max))
    return compose(*steps)


def compose(*groupers: Grouper) -> Grouper:
    """Apply groupers in order; each operates on the previous output's
    still-ungrouped entries while preserving already-formed groups.
    """

    def _g(entries: list[FileEntry]) -> list[GroupOrEntry]:
        current: list[GroupOrEntry] = list(entries)
        for g in groupers:
            ungrouped = [x for x in current if isinstance(x, FileEntry)]
            already = [x for x in current if not isinstance(x, FileEntry)]
            current = already + g(ungrouped)
        return current

    return _g
