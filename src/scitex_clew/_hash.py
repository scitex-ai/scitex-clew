#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/verify/_hash.py
"""File and directory hashing utilities for verification."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict, Optional, Union


def hash_file(
    path: Union[str, Path],
    algorithm: str = "sha256",
    chunk_size: int = 8192,
    hash_cache: Optional[Dict[str, str]] = None,
) -> str:
    """
    Compute hash of a file.

    Parameters
    ----------
    path : str or Path
        Path to the file to hash
    algorithm : str, optional
        Hash algorithm (default: sha256)
    chunk_size : int, optional
        Size of chunks to read (default: 8192)
    hash_cache : dict or None, optional
        Per-pass cache mapping resolved-path -> hash. When provided, the
        resolved path is looked up first; on a miss the file is hashed and
        the result is stored so subsequent calls within the same pass reuse
        the cached value. Pass ``None`` (default) to disable caching —
        direct calls to ``hash_file`` are unaffected.

    Returns
    -------
    str
        Hexadecimal hash string (first 32 characters)

    Examples
    --------
    >>> hash_file("data.csv")
    'a1b2c3d4e5f6...'
    """
    path = Path(path)

    # Per-pass cache: key is the resolved absolute path so that symlinks and
    # relative references to the same inode share one entry.
    # Cache check comes BEFORE the existence check so a cached hash is returned
    # even if the file has been moved/deleted since the first hash in this pass.
    cache_key = str(path.resolve())
    if hash_cache is not None and cache_key in hash_cache:
        return hash_cache[cache_key]

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    hasher = hashlib.new(algorithm)
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)

    result = hasher.hexdigest()[:32]

    if hash_cache is not None:
        hash_cache[cache_key] = result

    return result


def hash_directory(
    path: Union[str, Path],
    pattern: str = "*",
    recursive: bool = True,
    algorithm: str = "sha256",
) -> Dict[str, str]:
    """
    Compute hashes for all files in a directory.

    Parameters
    ----------
    path : str or Path
        Directory path
    pattern : str, optional
        Glob pattern for files (default: "*")
    recursive : bool, optional
        Whether to search recursively (default: True)
    algorithm : str, optional
        Hash algorithm (default: sha256)

    Returns
    -------
    dict
        Mapping of relative paths to hashes

    Examples
    --------
    >>> hash_directory("./data/")
    {'input.csv': 'a1b2...', 'config.yaml': 'c3d4...'}

    Notes
    -----
    Transparently accepts a compressed session archive: if ``path`` is a
    ``<dir>.tar.gz`` file (or a directory whose ``<dir>.tar.gz`` sibling
    exists because it was archived away), the members are hashed in place and
    returned with the same ``{relpath: hash}`` shape a loose dir would yield.
    """
    path = Path(path)

    if not path.is_dir():
        # Maybe the dir was compressed to a session archive — hash its members
        # rather than failing. Keeps ``hash_directory`` usable post-compression.
        from ._chain._archive_lookup import (
            hash_archive_members,
            resolve_directory_archive,
        )

        archive = resolve_directory_archive(path)
        if archive is not None:
            return hash_archive_members(archive, pattern=pattern, algorithm=algorithm)
        raise NotADirectoryError(f"Not a directory: {path}")

    glob_method = path.rglob if recursive else path.glob
    hashes = {}

    for file_path in glob_method(pattern):
        if file_path.is_file():
            rel_path = str(file_path.relative_to(path))
            hashes[rel_path] = hash_file(file_path, algorithm=algorithm)

    return hashes


def hash_files(
    paths: list[Union[str, Path]],
    algorithm: str = "sha256",
) -> Dict[str, str]:
    """
    Compute hashes for a list of files.

    Parameters
    ----------
    paths : list of str or Path
        List of file paths
    algorithm : str, optional
        Hash algorithm (default: sha256)

    Returns
    -------
    dict
        Mapping of paths to hashes
    """
    hashes = {}
    for path in paths:
        path = Path(path)
        if path.exists() and path.is_file():
            hashes[str(path)] = hash_file(path, algorithm=algorithm)
    return hashes


def combine_hashes(hashes: Dict[str, str], algorithm: str = "sha256") -> str:
    """
    Combine multiple hashes into a single hash.

    Creates a deterministic combined hash from a dictionary of hashes.

    Parameters
    ----------
    hashes : dict
        Mapping of names to hashes
    algorithm : str, optional
        Hash algorithm (default: sha256)

    Returns
    -------
    str
        Combined hash (first 32 characters)

    Examples
    --------
    >>> hashes = {'input.csv': 'a1b2...', 'script.py': 'c3d4...'}
    >>> combine_hashes(hashes)
    'e5f6g7h8...'
    """
    hasher = hashlib.new(algorithm)

    # Sort by key for deterministic ordering
    for key in sorted(hashes.keys()):
        hasher.update(f"{key}:{hashes[key]}".encode())

    return hasher.hexdigest()[:32]


def verify_hash(
    path: Union[str, Path],
    expected_hash: str,
    algorithm: str = "sha256",
) -> bool:
    """
    Verify that a file matches an expected hash.

    Parameters
    ----------
    path : str or Path
        Path to the file
    expected_hash : str
        Expected hash value
    algorithm : str, optional
        Hash algorithm (default: sha256)

    Returns
    -------
    bool
        True if hash matches, False otherwise
    """
    try:
        actual_hash = hash_file(path, algorithm=algorithm)
        # Compare only the length of expected_hash (may be truncated)
        return actual_hash[: len(expected_hash)] == expected_hash
    except FileNotFoundError:
        return False


# EOF
