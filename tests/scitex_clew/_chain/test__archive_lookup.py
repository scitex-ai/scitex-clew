#!/usr/bin/env python3
# Timestamp: "2026-06-18 (ywatanabe)"
# File: tests/scitex_clew/_chain/test__archive_lookup.py
"""Tests for archive-aware verification (compressed-session support).

These tests build real ``.tar.gz`` archives the same way
``scitex_session.archive_session_dir`` does (``arcname=<dirname>``, loose dir
removed) and assert that clew's verification path can read tracked files back
out of the archive, so provenance survives the inode-saving compression.

No mocks: real files, real tarfiles, real hashing.
"""

from __future__ import annotations

import hashlib
import shutil
import tarfile
from pathlib import Path

import pytest

from scitex_clew._chain._archive_lookup import (
    archived_member_exists,
    find_in_ancestor_archive,
    hash_archive_members,
    hash_archived_file,
    resolve_directory_archive,
)
from scitex_clew._chain._types import VerificationStatus
from scitex_clew._chain._verify_ops import verify_file
from scitex_clew._hash import hash_directory

_FILES = {
    "result.csv": b"a,b\n1,2\n",
    "params.json": b'{"k": 1}',
    "sub/signal.npy": b"\x93NUMPY-fake-bytes",
}


def _sha32(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _write_session_archive(src_dir: Path) -> Path:
    """Archive ``src_dir`` as ``<dir>.tar.gz`` (arcname=<dirname>); remove source.

    Mirrors ``scitex_session.archive_session_dir(..., remove_src=True)``.
    """
    archive = src_dir.with_name(src_dir.name + ".tar.gz")
    with tarfile.open(archive, mode="w:gz") as tf:
        tf.add(str(src_dir), arcname=src_dir.name)
    shutil.rmtree(src_dir)
    return archive


@pytest.fixture
def loose_session_dir(tmp_path):
    """A loose 'session output' dir with a few files (not yet archived)."""
    d = tmp_path / "2025Y-11M-12D-09h57m48s_NLRB-run"
    (d / "sub").mkdir(parents=True)
    for rel, content in _FILES.items():
        (d / rel).write_bytes(content)
    return d


@pytest.fixture
def archived_session(loose_session_dir):
    """Archive the loose dir (arcname=<dirname>) and remove the source.

    Mirrors ``scitex_session.archive_session_dir(..., remove_src=True)``.
    Returns the loose dir Path (now gone) — recorded paths still point at it.
    """
    src = loose_session_dir
    _write_session_archive(src)
    return src  # the (now-removed) recorded dir path


# ── find_in_ancestor_archive ──


def test_find_in_ancestor_archive_top_level_file_returns_expected_member(
    archived_session,
):
    # Arrange
    recorded = archived_session / "result.csv"
    # Act
    located = find_in_ancestor_archive(recorded)
    # Assert
    assert located[1] == f"{archived_session.name}/result.csv"


def test_find_in_ancestor_archive_top_level_file_points_at_sibling_archive(
    archived_session,
):
    # Arrange
    recorded = archived_session / "result.csv"
    expected_archive = archived_session.with_name(archived_session.name + ".tar.gz")
    # Act
    located = find_in_ancestor_archive(recorded)
    # Assert
    assert located[0] == expected_archive


def test_find_in_ancestor_archive_nested_file_returns_nested_member(
    archived_session,
):
    # Arrange
    recorded = archived_session / "sub" / "signal.npy"
    # Act
    located = find_in_ancestor_archive(recorded)
    # Assert
    assert located[1] == f"{archived_session.name}/sub/signal.npy"


def test_find_in_ancestor_archive_no_archive_returns_none(tmp_path):
    # Arrange
    missing = tmp_path / "nope" / "x.csv"
    # Act
    located = find_in_ancestor_archive(missing)
    # Assert
    assert located is None


def test_find_in_ancestor_archive_root_path_returns_none_without_raising():
    # Arrange
    root = "/"
    # Act
    located = find_in_ancestor_archive(root)
    # Assert
    assert located is None


def test_find_in_ancestor_archive_absolute_missing_file_returns_none():
    # Arrange
    missing = "/nonexistent_file_xyz.csv"
    # Act
    located = find_in_ancestor_archive(missing)
    # Assert
    assert located is None


# ── hash_archived_file ──


def test_hash_archived_file_matches_original_hash(archived_session):
    # Arrange
    recorded = archived_session / "result.csv"
    # Act
    got = hash_archived_file(recorded)
    # Assert
    assert got == _sha32(_FILES["result.csv"])


def test_hash_archived_file_absent_returns_none(tmp_path):
    # Arrange
    missing = tmp_path / "gone.csv"
    # Act
    got = hash_archived_file(missing)
    # Assert
    assert got is None


# ── verify_file (archive-aware) ──


def test_verify_file_archived_file_with_correct_hash_is_verified(archived_session):
    # Arrange
    recorded = archived_session / "result.csv"
    # Act
    fv = verify_file(recorded, _sha32(_FILES["result.csv"]), role="output")
    # Assert
    assert fv.status == VerificationStatus.VERIFIED


def test_verify_file_archived_file_wrong_hash_is_mismatch(archived_session):
    # Arrange
    recorded = archived_session / "result.csv"
    # Act
    fv = verify_file(recorded, "deadbeef" * 4, role="output")
    # Assert
    assert fv.status == VerificationStatus.MISMATCH


def test_verify_file_no_file_and_no_archive_is_missing(tmp_path):
    # Arrange
    ghost = tmp_path / "ghost.csv"
    # Act
    fv = verify_file(ghost, "abc123", role="output")
    # Assert
    assert fv.status == VerificationStatus.MISSING


def test_verify_file_loose_file_present_is_verified(tmp_path):
    # Arrange
    p = tmp_path / "live.csv"
    p.write_bytes(b"hello")
    # Act
    fv = verify_file(p, _sha32(b"hello"), role="output")
    # Assert
    assert fv.status == VerificationStatus.VERIFIED


# ── hash_directory (archive-aware) ──


def test_hash_directory_on_targz_returns_stripped_relpaths(archived_session):
    # Arrange
    archive = archived_session.with_name(archived_session.name + ".tar.gz")
    # Act
    result = hash_directory(archive)
    # Assert
    assert result["sub/signal.npy"] == _sha32(_FILES["sub/signal.npy"])


def test_hash_directory_on_removed_dir_uses_sibling_archive(archived_session):
    # Arrange
    removed_dir = archived_session  # dir is gone; sibling .tar.gz exists
    # Act
    result = hash_directory(removed_dir)
    # Assert
    assert result["result.csv"] == _sha32(_FILES["result.csv"])


def test_hash_directory_missing_dir_without_archive_raises(tmp_path):
    # Arrange
    missing = tmp_path / "does_not_exist"
    # Act
    call = lambda: hash_directory(missing)
    # Assert
    with pytest.raises(NotADirectoryError):
        call()


def test_hash_directory_loose_dir_hashes_members(loose_session_dir):
    # Arrange
    d = loose_session_dir  # not archived
    # Act
    result = hash_directory(d)
    # Assert
    assert result["result.csv"] == _sha32(_FILES["result.csv"])


# ── resolve_directory_archive ──


def test_resolve_directory_archive_for_archive_file_returns_itself(archived_session):
    # Arrange
    archive = archived_session.with_name(archived_session.name + ".tar.gz")
    # Act
    resolved = resolve_directory_archive(archive)
    # Assert
    assert resolved == archive


def test_resolve_directory_archive_for_dir_path_returns_sibling(archived_session):
    # Arrange
    archive = archived_session.with_name(archived_session.name + ".tar.gz")
    # Act
    resolved = resolve_directory_archive(archived_session)
    # Assert
    assert resolved == archive


def test_resolve_directory_archive_for_live_dir_returns_none(loose_session_dir):
    # Arrange
    d = loose_session_dir  # not archived
    # Act
    resolved = resolve_directory_archive(d)
    # Assert
    assert resolved is None


# ── hash_archive_members ──


def test_hash_archive_members_pattern_filter_selects_only_matching(archived_session):
    # Arrange
    archive = archived_session.with_name(archived_session.name + ".tar.gz")
    # Act
    only_csv = hash_archive_members(archive, pattern="*.csv")
    # Assert
    assert set(only_csv) == {"result.csv"}


def test_archived_member_exists_true_for_archived_file(archived_session):
    # Arrange
    recorded = archived_session / "params.json"
    # Act
    exists = archived_member_exists(recorded)
    # Assert
    assert exists is True


def test_archived_member_exists_false_for_unknown_file(tmp_path):
    # Arrange
    unknown = tmp_path / "nope.json"
    # Act
    exists = archived_member_exists(unknown)
    # Assert
    assert exists is False


# EOF
