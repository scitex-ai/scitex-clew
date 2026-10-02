"""Ordinary synthetic fixtures for descriptor-rooted project previews."""

import os
from pathlib import Path

import pytest
from scitex_sdk.host import AccessError, ProjectAccess

from scitex_clew._django.services.project_files import (
    MAX_TEXT_BYTES,
    open_project_file,
    read_project_text,
)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    return ProjectAccess("project", "Synthetic project", root)



def test_valid_utf8_text_preserves_content(project):
    # Arrange
    path = project.root / "notes.txt"
    path.write_text("Synthetic preview: α\n", encoding="utf-8")
    # Act
    # Assert
    assert read_project_text(project.root, project.path("notes.txt")) == "Synthetic preview: α\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_readable_file_does_not_require_directory_listing_permissions(project):
    # Arrange
    directory = project.root / "folder"
    directory.mkdir()
    (directory / "notes.txt").write_text("Synthetic search-only directory")
    directory.chmod(0o111)
    project.root.chmod(0o111)
    # Act
    # Assert
    try:
        assert read_project_text(project.root, project.path("folder/notes.txt")) == "Synthetic search-only directory"
    finally:
        project.root.chmod(0o700)
        directory.chmod(0o700)


@pytest.fixture
def image_path(project):
    path = project.root / "plot.png"
    content = b"\x89PNG\r\n\x1a\nsynthetic image bytes"
    path.write_bytes(content)
    return path, content


def test_regular_image_stream_preserves_file_bytes(project, image_path):
    # Arrange
    path, content = image_path
    # Act
    with open_project_file(project.root, project.path("plot.png")) as stream:
        # Assert
        assert stream.read() == content


def test_regular_image_stream_remains_open_inside_response(project, image_path):
    # Arrange
    path, content = image_path
    # Act
    with open_project_file(project.root, project.path("plot.png")) as stream:
        # Assert
        assert not stream.closed


def test_regular_image_stream_closes_after_response(project, image_path):
    # Arrange
    path, content = image_path
    # Act
    with open_project_file(project.root, project.path("plot.png")) as stream:
        pass
    # Assert
    assert stream.closed


@pytest.fixture(params=["missing", "directory", "fifo"])
def invalid_regular_path(project, request):
    path = project.root / "entry"
    if request.param == "directory":
        path.mkdir()
    elif request.param == "fifo":
        os.mkfifo(path)
    return path


def test_only_existing_regular_files_are_accepted(project, invalid_regular_path):
    # Arrange
    path = invalid_regular_path
    # Act
    # Assert
    with pytest.raises(AccessError):
        open_project_file(project.root, path)


def test_invalid_regular_files_preserve_not_found_status(project, invalid_regular_path):
    # Arrange
    path = invalid_regular_path
    # Act
    status = regular_error_status(project, path)
    # Assert
    assert status == 404


def test_text_limit_accepts_exact_boundary(project):
    # Arrange
    path = project.root / "notes.txt"
    path.write_bytes(b"x" * MAX_TEXT_BYTES)
    # Act
    # Assert
    assert len(read_project_text(project.root, path)) == MAX_TEXT_BYTES


@pytest.fixture
def oversized_text(project):
    path = project.root / "notes.txt"
    path.write_bytes(b"x" * MAX_TEXT_BYTES)
    with path.open("ab") as stream:
        stream.write(b"x")
    yield path


def test_text_limit_rejects_oversize_payload(project, oversized_text):
    # Arrange
    path = oversized_text
    # Act
    # Assert
    with pytest.raises(AccessError):
        read_project_text(project.root, path)


def test_text_limit_preserves_oversize_status(project, oversized_text):
    # Arrange
    path = oversized_text
    # Act
    status = text_error_status(project, path)
    # Assert
    assert status == 413


@pytest.fixture(params=[("paper", ".scitex/writer"), ("clew", ".scitex/clew")])
def internal_alias(project, request):
    alias, target = request.param
    directory = project.root / target
    directory.mkdir(parents=True)
    (directory / "notes.txt").write_text("Synthetic internal alias")
    (project.root / alias).symlink_to(target, target_is_directory=True)
    return directory, project.path(f"{alias}/notes.txt")


def test_normalized_internal_alias_preserves_canonical_path(internal_alias):
    # Arrange
    directory, canonical = internal_alias
    # Act
    # Assert
    assert canonical == directory / "notes.txt"


def test_normalized_internal_alias_remains_readable(project, internal_alias):
    # Arrange
    directory, canonical = internal_alias
    # Act
    # Assert
    assert read_project_text(project.root, canonical) == "Synthetic internal alias"


def test_external_alias_is_rejected_by_existing_capability(project, tmp_path):
    # Arrange
    outside = tmp_path / "outside.txt"
    outside.write_text("Synthetic sibling fixture")
    (project.root / "external.txt").symlink_to(outside)
    # Act
    # Assert
    with pytest.raises(AccessError):
        project.path("external.txt")


@pytest.fixture(params=["file", "parent", "root", "root_parent"])
def symlink_open_target(project, tmp_path, request):
    component = request.param
    # Arrange
    directory = project.root / "folder"
    directory.mkdir()
    path = directory / "notes.txt"
    path.write_text("Synthetic regular file")
    # Act
    if component == "file":
        link = directory / "link.txt"
        link.symlink_to(path)
        canonical = link
        root = project.root
    elif component == "parent":
        link = project.root / "alias"
        link.symlink_to(directory, target_is_directory=True)
        canonical = link / "notes.txt"
        root = project.root
    elif component == "root":
        root = tmp_path / "root-alias"
        root.symlink_to(project.root, target_is_directory=True)
        canonical = root / "folder" / "notes.txt"
    else:
        parent = tmp_path / "parent-alias"
        parent.symlink_to(tmp_path, target_is_directory=True)
        root = parent / "project"
        canonical = root / "folder" / "notes.txt"
    return root, canonical


def test_canonical_open_refuses_any_symlink_component(symlink_open_target):
    # Arrange
    root, canonical = symlink_open_target
    # Act
    # Assert
    with pytest.raises(AccessError):
        open_project_file(root, canonical)


@pytest.mark.parametrize("value", ["outside", "parent"])
def test_lexical_path_outside_authorized_root_is_rejected(project, tmp_path, value):
    # Arrange
    path = tmp_path / "sibling.txt" if value == "outside" else project.root / ".." / "sibling.txt"
    # Act
    # Assert
    with pytest.raises(AccessError):
        open_project_file(project.root, path)


def regular_error_status(project, path):
    with pytest.raises(AccessError) as error:
        open_project_file(project.root, path)
    return error.value.status


def text_error_status(project, path):
    with pytest.raises(AccessError) as error:
        read_project_text(project.root, path)
    return error.value.status
