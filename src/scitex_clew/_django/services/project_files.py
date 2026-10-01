"""Descriptor-rooted preview reads; this is not an OS filesystem sandbox.

The caller supplies the authorized root and SDK-normalized canonical path.
Internal project aliases can normalize to an in-project target. No symlink
is followed while opening that target, and text reads have a byte bound.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path
from typing import BinaryIO

try:
    from scitex_sdk.host import AccessError, CapabilityUnavailable
except ModuleNotFoundError as exc:
    from scitex_clew._django._optional import gui_dependency_error

    gui_dependency_error(exc)

MAX_TEXT_BYTES = 4 * 1024 * 1024


def open_project_file(root: Path, path: Path) -> BinaryIO:
    """Open a regular file below an authorized root without following links.

    The returned stream owns its descriptor. A streaming response may keep it
    after the directory descriptors close; callers must otherwise close it.
    Unsupported platforms fail closed instead of using a pathname fallback.
    """
    if (
        os.name != "posix"
        or os.open not in os.supports_dir_fd
        or not all(
            hasattr(os, name)
            for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC", "O_NONBLOCK")
        )
    ):
        raise CapabilityUnavailable("Safe project file reads are unavailable")
    root, path = Path(root), Path(path)
    if not root.is_absolute() or ".." in root.parts:
        raise CapabilityUnavailable("Project root is not canonical")
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise AccessError("File must be inside this project") from exc
    if ".." in relative.parts:
        raise AccessError("File must be inside this project")
    if not relative.parts:
        raise AccessError("File not found", 404)

    # Linux O_PATH preserves ordinary file-read behavior in search-only
    # directories without asking for directory-listing permission.
    directories = (
        getattr(os, "O_PATH", os.O_RDONLY)
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
        | os.O_CLOEXEC
    )
    directory_fd = None
    file_fd = None
    try:
        # Walk the canonical root too: O_NOFOLLOW on the final root component
        # alone would still follow a replacement link in one of its parents.
        directory_fd = os.open(root.anchor, directories)
        for component in (*root.parts[1:], *relative.parts[:-1]):
            child_fd = os.open(component, directories, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
        file_fd = os.open(
            relative.name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
        if not stat.S_ISREG(os.fstat(file_fd).st_mode):
            raise AccessError("File not found", 404)
        stream = os.fdopen(file_fd, "rb")
        file_fd = None
        return stream
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            raise AccessError("File not found", 404) from exc
        raise AccessError("File cannot be previewed") from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)


def read_project_text(root: Path, path: Path) -> str:
    """Read at most the existing preview limit, including a growth check."""
    with open_project_file(root, path) as stream:
        if os.fstat(stream.fileno()).st_size > MAX_TEXT_BYTES:
            raise AccessError("File is too large to preview", 413)
        content = stream.read(MAX_TEXT_BYTES + 1)
        if len(content) > MAX_TEXT_BYTES:
            raise AccessError("File is too large to preview", 413)
        return content.decode("utf-8")
