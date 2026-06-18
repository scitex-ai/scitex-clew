#!/usr/bin/env python3
# Timestamp: "2026-06-18 (ywatanabe)"
# File: src/scitex_clew/_archive_lookup.py
"""Transparent lookup of tracked files inside compressed session archives.

Why this exists
---------------
``scitex.session`` can collapse a finished run directory into a single
``<dir>.tar.gz`` (1 inode instead of N) — see
``scitex_session._lifecycle._archive``. This is a large inode/quota win on
shared HPC filesystems where a single PAC run emits ~6 loose files.

Clew records the **absolute path** of every tracked artifact at save time
(e.g. ``/scratch/run_out/result.csv``). Once the enclosing directory is
archived and the loose copy removed, those paths no longer ``exists()`` — so
``verify_file`` would report every artifact as ``MISSING`` even though the
bytes are intact and byte-identical inside the ``.tar.gz``. That is a silent
false-negative for the provenance/reproducibility layer.

This module bridges the gap **without** any DB migration or re-recording: it
maps a recorded path to the member of an ancestor ``<dir>.tar.gz`` and reads
that member in place (streaming, no full extraction). Recording is untouched;
only the verification read path gains an archive-aware fallback.

Mapping rule
------------
``scitex_session.archive_session_dir`` writes the archive as
``<parent>/<dirname>.tar.gz`` with ``arcname=<dirname>`` — i.e. the dir name
is preserved as the archive's top-level entry. So for a recorded file

    /a/b/<dirname>/sub/file.csv

the archive is ``/a/b/<dirname>.tar.gz`` and the member is
``<dirname>/sub/file.csv``. We try each ancestor directory of the recorded
path (deepest first) so a file is found whichever level was compressed.
``.tar.gz`` / ``.tar.xz`` / ``.tar`` are all supported (the formats
``archive_session_dir`` can emit).
"""

from __future__ import annotations

import fnmatch
import hashlib
import tarfile
from pathlib import Path
from typing import Dict, Optional, Tuple

# Suffixes scitex-session's archive_session_dir can produce, longest first so
# ".tar.gz" wins over a hypothetical ".gz".
_ARCHIVE_SUFFIXES = (".tar.gz", ".tar.xz", ".tar")

# Bound the ancestor walk: real session dirs are shallow, but we never want to
# probe the whole path to root on every missing file.
_MAX_ANCESTOR_DEPTH = 8


def find_in_ancestor_archive(
    path: "str | Path",
) -> Optional[Tuple[Path, str]]:
    """Locate a (now-missing) recorded file inside an ancestor ``.tar.gz``.

    Parameters
    ----------
    path : str or Path
        The absolute path clew recorded for a tracked artifact. It need not
        exist on disk (that is the whole point — it was archived away).

    Returns
    -------
    tuple of (Path, str) or None
        ``(archive_path, member_name)`` if an ancestor ``<dir>.tar.gz``
        (or ``.tar`` / ``.tar.xz``) contains the file, else ``None``.

    Notes
    -----
    This only resolves the *location*; it does not open the archive. Use
    :func:`hash_archived_file` to read+hash the member.
    """
    p = Path(path)
    parts = p.parts
    n = len(parts)
    if n < 2:
        return None

    # Walk ancestor dirs deepest-first: index i splits parts into
    # ancestor = parts[:i] (candidate archived dir) and rel = parts[i:].
    lowest = max(1, n - _MAX_ANCESTOR_DEPTH)
    for i in range(n - 1, lowest - 1, -1):
        ancestor = Path(*parts[:i])
        # Skip the filesystem root / drive anchor (empty name): there is no
        # "<root>.tar.gz", and ``with_name`` would raise on it.
        if not ancestor.name:
            continue
        rel = Path(*parts[i:])
        for suffix in _ARCHIVE_SUFFIXES:
            archive = ancestor.with_name(ancestor.name + suffix)
            if archive.is_file():
                member = f"{ancestor.name}/{rel.as_posix()}"
                if _member_exists(archive, member):
                    return archive, member
    return None


def archived_member_exists(path: "str | Path") -> bool:
    """True if ``path`` (missing on disk) is recoverable from an ancestor archive."""
    return find_in_ancestor_archive(path) is not None


def resolve_directory_archive(path: "str | Path") -> Optional[Path]:
    """Resolve a directory-ish ``path`` to a session archive file, if any.

    Accepts either the archive itself (``foo.tar.gz``) or a directory path
    whose compressed sibling exists (``foo/`` -> ``foo.tar.gz``). Returns the
    archive ``Path`` or ``None`` when neither applies (e.g. a live directory,
    which the caller should walk normally).
    """
    p = Path(path)
    name = p.name
    for suffix in _ARCHIVE_SUFFIXES:
        if name.endswith(suffix) and p.is_file():
            return p
    for suffix in _ARCHIVE_SUFFIXES:
        sibling = p.with_name(p.name + suffix)
        if sibling.is_file():
            return sibling
    return None


def hash_archive_members(
    archive: "str | Path",
    pattern: str = "*",
    algorithm: str = "sha256",
    chunk_size: int = 8_192,
) -> Dict[str, str]:
    """Hash every regular-file member of a tar archive.

    Returns a ``{relpath: hash}`` mapping mirroring
    :func:`scitex_clew._hash.hash_directory`. The leading top-level dir that
    ``archive_session_dir`` adds (``arcname=<dirname>``) is stripped so the
    keys match what a loose-dir hash would have produced. ``pattern`` is
    matched (``fnmatch``) against those stripped relpaths.
    """
    archive = Path(archive)
    out: Dict[str, str] = {}
    with tarfile.open(archive, mode="r:*") as tf:
        members = tf.getmembers()
        # Strip a single shared top-level dir component if present (the
        # arcname wrapper), so keys read like loose-dir relpaths.
        top = _common_top(members)
        for m in members:
            if not m.isfile():
                continue
            rel = m.name
            if top and (rel == top or rel.startswith(top + "/")):
                rel = rel[len(top) + 1 :]
            if not rel:
                continue
            if not fnmatch.fnmatch(rel, pattern):
                continue
            extracted = tf.extractfile(m)
            if extracted is None:
                continue
            hasher = hashlib.new(algorithm)
            with extracted:
                while chunk := extracted.read(chunk_size):
                    hasher.update(chunk)
            out[rel] = hasher.hexdigest()[:32]
    return out


def _common_top(members) -> Optional[str]:
    """Return the single shared top-level path component, or None."""
    tops = set()
    for m in members:
        first = m.name.split("/", 1)[0]
        tops.add(first)
        if len(tops) > 1:
            return None
    return next(iter(tops)) if tops else None


def hash_archived_file(
    path: "str | Path",
    algorithm: str = "sha256",
    chunk_size: int = 8_192,
) -> Optional[str]:
    """Hash a recorded file by reading it from an ancestor ``.tar.gz`` member.

    Streams the member (no full extraction) and returns the same truncated
    digest shape as :func:`scitex_clew._hash.hash_file` (first 32 hex chars),
    so a value produced here is directly comparable to a stored hash.

    Returns
    -------
    str or None
        The hex digest, or ``None`` if the file is not found in any ancestor
        archive (caller should then treat it as genuinely missing).
    """
    located = find_in_ancestor_archive(path)
    if located is None:
        return None
    archive, member = located
    return _hash_member(archive, member, algorithm=algorithm, chunk_size=chunk_size)


# ── internals ──


def _member_exists(archive: Path, member: str) -> bool:
    """Cheap membership check for ``member`` inside ``archive``."""
    try:
        with tarfile.open(archive, mode="r:*") as tf:
            try:
                tf.getmember(member)
                return True
            except KeyError:
                return False
    except (tarfile.TarError, OSError):
        return False


def _hash_member(
    archive: Path,
    member: str,
    algorithm: str = "sha256",
    chunk_size: int = 8_192,
) -> Optional[str]:
    try:
        with tarfile.open(archive, mode="r:*") as tf:
            try:
                extracted = tf.extractfile(member)
            except KeyError:
                return None
            if extracted is None:  # a directory or special member
                return None
            hasher = hashlib.new(algorithm)
            with extracted:
                while chunk := extracted.read(chunk_size):
                    hasher.update(chunk)
            return hasher.hexdigest()[:32]
    except (tarfile.TarError, OSError):
        return None


__all__ = [
    "archived_member_exists",
    "find_in_ancestor_archive",
    "hash_archive_members",
    "hash_archived_file",
    "resolve_directory_archive",
]

# EOF
