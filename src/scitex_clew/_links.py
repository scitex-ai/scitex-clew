#!/usr/bin/env python3
"""Symlinks a run went THROUGH to reach its files (#192).

A script opens ``alias/x.csv`` where ``alias -> data`` (or ``cfg -> ../config``,
or ``raw -> /mnt/shared/raw``, or a chain ``a -> b -> data``). Every recorded
file is keyed by its RESOLVED path (``data/x.csv``), which is what is hashed and
verified — but a re-run of the slice opens the LINK path, so a slice holding
only the target fails with FileNotFoundError (or silently reads nothing).

This module records the path indirection itself: every symlink traversed while
resolving a path the run used, whose link file lives INSIDE the project root
(links elsewhere — ``/home -> /mnt/home`` on some hosts — are the machine's,
not the project's). One entry per link::

    {"link": <absolute location of the link file>,
     "target": <os.readlink() text, verbatim>,
     "resolved": <realpath(link) when recorded>,
     "in_project": <the link's target lies inside the project root>,
     "recreate": <what to point a recreated link at>,
     "kind": "dir" | "file",
     "files": [<resolved recorded files reached through this link>]}

``recreate`` keeps a relative target verbatim when it stays in the project (the
slice preserves the layout, and a chain ``a -> b -> data`` stays a chain), turns
an absolute in-project target into the equivalent relative one (the slice may be
materialized under another root), and points an external target at its
resolved absolute path (it cannot be bundled; the slice lists the file as
required-but-not-bundled at that path).

The entries travel in the run's metadata (``metadata["links"]``, written at
finalize), so no store schema changes. Slices carry the links that reach a
kept file (:mod:`scitex_clew._chain._slice_links`) and ``verify`` re-checks
that each link still exists and still resolves to the recorded target.
"""

from __future__ import annotations

import os

__all__ = [
    "MAX_HOPS",
    "absolute",
    "link_entries",
    "merge_link_entries",
    "symlink_hops",
]

#: Same bound as the kernel's ELOOP (40): a loop records at most this many hops.
MAX_HOPS = 40


def _under(path: str, root: str) -> bool:
    root = root.rstrip(os.sep) or os.sep
    return path == root or path.startswith(root + os.sep) or root == os.sep


def absolute(path: str) -> str:
    """``path`` made absolute WITHOUT lexical normalisation.

    :func:`os.path.abspath` collapses ``link/..`` lexically, which is not what
    the kernel does when ``link`` is a symlink (``..`` climbs from the link's
    target). Paths a run used are kept as given until :func:`os.path.realpath`
    resolves them component by component.
    """
    path = os.fspath(path)
    return path if os.path.isabs(path) else os.path.join(os.getcwd(), path)


def symlink_hops(path: str) -> list[tuple[str, str]]:
    """Every symlink traversed resolving ``path``: ``[(link, readlink text)]``.

    Mirrors the kernel's (and :func:`os.path.realpath`'s) component-wise walk:
    each link location is the place the link file really is (earlier links on
    the way already followed), and a ``..`` after a link climbs from the link's
    TARGET, not lexically. Chains yield one hop per link, in traversal order.
    """
    path = absolute(path)
    pending = [p for p in path.split(os.sep) if p][::-1]
    current = os.sep
    hops: list[tuple[str, str]] = []
    while pending:
        name = pending.pop()
        if name == ".":
            continue
        if name == "..":
            current = os.path.dirname(current)
            continue
        candidate = os.path.join(current, name)
        if not os.path.islink(candidate):
            current = candidate
            continue
        if len(hops) >= MAX_HOPS:
            break  # a loop: the open itself fails with ELOOP
        try:
            target = os.readlink(candidate)
        except OSError:
            current = candidate
            continue
        hops.append((candidate, target))
        if os.path.isabs(target):
            current = os.sep
        pending.extend(reversed([p for p in target.split(os.sep) if p]))
    return hops


def _target_location(link: str, target: str) -> str:
    """Absolute location the link names: its target's directory resolved, the
    last component kept (so a link to another link stays a link to it)."""
    target_abs = os.path.normpath(os.path.join(os.path.dirname(link), target))
    parent = os.path.realpath(os.path.dirname(target_abs))
    return os.path.join(parent, os.path.basename(target_abs))


def link_entries(path: str, root: str, file_real: str | None = None) -> list[dict]:
    """The in-project symlinks on ``path`` as metadata entries (see module doc).

    ``root`` is the RESOLVED project root; ``file_real`` the recorded file
    (default ``realpath(path)``). Empty when ``path`` traverses no link.
    """
    path = absolute(path)
    real = file_real or os.path.realpath(path)
    if path == real:
        return []  # the common case: no link (and no ``..``) on the way
    root = os.path.realpath(root)
    entries = []
    for link, target in symlink_hops(path):
        if not _under(link, root) or link == root:
            continue
        location = _target_location(link, target)
        in_project = _under(location, root)
        resolved = os.path.realpath(link)
        if not in_project:
            recreate = resolved
        elif os.path.isabs(target):
            recreate = os.path.relpath(location, os.path.dirname(link))
        else:
            recreate = target
        entries.append(
            {
                "link": link,
                "target": target,
                "resolved": resolved,
                "in_project": in_project,
                "recreate": recreate,
                "kind": "dir" if os.path.isdir(link) else "file",
                "files": [real],
            }
        )
    return entries


def merge_link_entries(into: dict[str, dict], entries: list[dict]) -> None:
    """Fold ``entries`` into ``into`` (keyed by link path; files unioned)."""
    for entry in entries:
        known = into.get(entry["link"])
        if known is None:
            into[entry["link"]] = {**entry, "files": list(entry["files"])}
            continue
        for f in entry["files"]:
            if f not in known["files"]:
                known["files"].append(f)


# EOF
