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


def test_valid_utf8_text(project):
    path = project.root / "notes.txt"
    path.write_text("Synthetic preview: α\n", encoding="utf-8")
    assert read_project_text(project.root, project.path("notes.txt")) == "Synthetic preview: α\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_readable_file_does_not_require_directory_listing_permissions(project):
    directory = project.root / "folder"
    directory.mkdir()
    (directory / "notes.txt").write_text("Synthetic search-only directory")
    directory.chmod(0o111)
    project.root.chmod(0o111)
    try:
        assert read_project_text(project.root, project.path("folder/notes.txt")) == "Synthetic search-only directory"
    finally:
        project.root.chmod(0o700)
        directory.chmod(0o700)


def test_regular_image_stream_stays_open_for_response(project):
    path = project.root / "plot.png"
    content = b"\x89PNG\r\n\x1a\nsynthetic image bytes"
    path.write_bytes(content)
    with open_project_file(project.root, project.path("plot.png")) as stream:
        assert stream.read() == content
        assert not stream.closed
    assert stream.closed


@pytest.mark.parametrize("kind", ["missing", "directory", "fifo"])
def test_only_existing_regular_files_are_accepted(project, kind):
    path = project.root / "entry"
    if kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    with pytest.raises(AccessError) as error:
        open_project_file(project.root, path)
    assert error.value.status == 404


def test_text_limit_accepts_boundary_and_rejects_oversize(project):
    path = project.root / "notes.txt"
    path.write_bytes(b"x" * MAX_TEXT_BYTES)
    assert len(read_project_text(project.root, path)) == MAX_TEXT_BYTES
    with path.open("ab") as stream:
        stream.write(b"x")
    with pytest.raises(AccessError) as error:
        read_project_text(project.root, path)
    assert error.value.status == 413


@pytest.mark.parametrize("alias,target", [("paper", ".scitex/writer"), ("clew", ".scitex/clew")])
def test_normalized_internal_alias_remains_readable(project, alias, target):
    directory = project.root / target
    directory.mkdir(parents=True)
    (directory / "notes.txt").write_text("Synthetic internal alias")
    (project.root / alias).symlink_to(target, target_is_directory=True)
    canonical = project.path(f"{alias}/notes.txt")
    assert canonical == directory / "notes.txt"
    assert read_project_text(project.root, canonical) == "Synthetic internal alias"


def test_external_alias_is_rejected_by_existing_capability(project, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("Synthetic sibling fixture")
    (project.root / "external.txt").symlink_to(outside)
    with pytest.raises(AccessError):
        project.path("external.txt")


@pytest.mark.parametrize("component", ["file", "parent", "root", "root_parent"])
def test_canonical_open_refuses_any_symlink_component(project, tmp_path, component):
    directory = project.root / "folder"
    directory.mkdir()
    path = directory / "notes.txt"
    path.write_text("Synthetic regular file")
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
    with pytest.raises(AccessError):
        open_project_file(root, canonical)


@pytest.mark.parametrize("value", ["outside", "parent"])
def test_lexical_path_outside_authorized_root_is_rejected(project, tmp_path, value):
    path = tmp_path / "sibling.txt" if value == "outside" else project.root / ".." / "sibling.txt"
    with pytest.raises(AccessError):
        open_project_file(project.root, path)
