"""Host paths -> portable bundle paths (never an absolute host path)."""

from __future__ import annotations

import pytest
from scitex_clew._exchange._relpaths import (
    external_name,
    is_portable,
    relative_argv,
    relative_or_none,
)


def test_in_project_path_is_repo_relative_posix(tmp_path):
    # Arrange
    path = tmp_path / "data" / "in.csv"
    # Act
    rel = relative_or_none(path, tmp_path)
    # Assert
    assert rel == "data/in.csv"


def test_outside_path_is_none(tmp_path):
    # Arrange
    root = tmp_path / "proj"
    # Act
    rel = relative_or_none(tmp_path / "elsewhere.csv", root)
    # Assert
    assert rel is None


def test_external_without_via_is_named_by_file_name_only(tmp_path):
    # Arrange
    host_path = "/mnt/lab/shared/raw/eeg.edf"
    # Act
    name = external_name(host_path, None, tmp_path)
    # Assert
    assert name == "<external>/eeg.edf"


def test_external_read_through_project_symlink_keeps_that_path(tmp_path):
    # Arrange
    via = str(tmp_path / "data" / "raw" / "eeg.edf")
    # Act
    name = external_name("/mnt/lab/raw/eeg.edf", via, tmp_path)
    # Assert
    assert name == "data/raw/eeg.edf"


def test_absolute_in_project_argv_becomes_cwd_relative(tmp_path):
    # Arrange
    argv = [
        str(tmp_path / "scripts" / "a.py"),
        "--src",
        str(tmp_path / "data" / "x.csv"),
    ]
    # Act
    got = relative_argv(argv, tmp_path, tmp_path / "scripts")
    # Assert
    assert got == ["a.py", "--src", "../data/x.csv"]


@pytest.mark.parametrize(
    ("rel", "ok"),
    [("data/x.csv", True), ("/etc/passwd", False), ("../x", False),
     ("a/../../x", False), ("C:/x", False), ("a\\b", False)],
)  # fmt: skip
def test_portable_paths_stay_inside_the_root(rel, ok):
    # Arrange
    candidate = rel
    # Act
    got = is_portable(candidate)
    # Assert
    assert got is ok


# EOF
