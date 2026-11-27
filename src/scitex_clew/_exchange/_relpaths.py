#!/usr/bin/env python3
"""Host paths -> the bundle's portable paths.

A bundle never carries an absolute host path. In-project paths become
repo-relative POSIX paths; a path outside the project root is EXTERNAL and
is named only by what the run saw of it (the in-project path it was read
through, else its file name), never by where it lives on the authors' host.
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

__all__ = [
    "external_name",
    "is_portable",
    "portable_path",
    "portable_text",
    "relative_argv",
    "relative_or_none",
]

#: Prefix of the portable name of an external file read by absolute path.
EXTERNAL_PREFIX = "<external>/"


def relative_or_none(path: str | os.PathLike | None, root: Path) -> str | None:
    """``path`` as a repo-relative POSIX path, or ``None`` when outside ``root``.

    Lexical first (a symlink INSIDE the project is named by its in-project
    path), then by resolution (the same file reached through another spelling).
    """
    if not path:
        return None
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    for candidate in (Path(os.path.normpath(p)), p.resolve()):
        try:
            rel = candidate.relative_to(root)
        except ValueError:
            continue
        return rel.as_posix() or "."
    return None


def portable_path(
    path: str | os.PathLike | None, root: Path
) -> tuple[str | None, bool]:
    """``(text, external)`` for a recorded path in an export a reader sees.

    Inside ``root``: the repo-relative POSIX path, ``external=False``. Outside
    it: the path exactly as recorded (absolute), ``external=True`` — a shared
    dataset or a sibling project's file is named where it really is, never
    disguised as part of this project. ``None`` / empty passes through.
    """
    if not path:
        return (None if path is None else str(path)), False
    rel = relative_or_none(path, root)
    if rel is not None:
        return rel, False
    return str(path), True


#: Characters that end a path token inside prose (whitespace, quotes,
#: brackets, separators). ``:`` ends it too, so ``paper.tex:L10`` keeps its
#: line suffix and ``scheme://`` URLs never start a token.
_STOP = r"\s'\"`,;:()\[\]{}<>|"
#: A token may not start right after a word, path or URL character: ``1/2``,
#: ``and/or``, ``./x``, ``~/x`` and ``https://x`` are not absolute paths.
_LEFT = r"(?<![\w/.~:\-])"


def _path_tokens(root: Path) -> re.Pattern[str]:
    """Absolute POSIX path tokens in prose: the root spelled verbatim (it may
    hold spaces) or any ``/``-rooted run of non-stop characters."""
    char = f"[^{_STOP}]"
    return re.compile(
        rf"{_LEFT}{re.escape(root.as_posix())}(?:/{char}*)?(?!{char})"
        rf"|{_LEFT}/{char}+"
    )


def portable_text(text: str | None, root: Path) -> str | None:
    """``text`` with each absolute in-project path token made project-relative.

    The :func:`portable_path` rule applied to prose (a verify detail such as
    ``source changed: /home/u/proj/data/a.json``): a token inside ``root``
    becomes its repo-relative path (``data/a.json``; the root itself
    ``.``), a token outside it is left exactly as written, and every other
    character is untouched. A sentence-ending ``.`` is not part of a path.
    """
    if not text:
        return text

    def swap(match: re.Match[str]) -> str:
        token = match.group(0)
        core = token.rstrip(".")
        rel, external = portable_path(core, root)
        if external or not core:
            return token
        return rel + token[len(core) :]

    return _path_tokens(root).sub(swap, text)


def external_name(path: str, via: str | None, root: Path) -> str:
    """Portable name of an external input: its in-project ``via`` path, else
    ``<external>/<file name>``."""
    rel = relative_or_none(via, root) if via else None
    if rel is not None:
        return rel
    return EXTERNAL_PREFIX + Path(path).name


def relative_argv(argv: list[str], root: Path, cwd: Path) -> list[str]:
    """Recorded ``argv`` with in-project absolute paths made relative to ``cwd``.

    ``cwd`` is where the run is replayed from, so a path argument relative to
    it names the same file in any copy of the project. Arguments that are not
    absolute in-project paths are kept verbatim.
    """
    out = []
    for arg in argv:
        text = str(arg)
        if os.path.isabs(text) and relative_or_none(text, root) is not None:
            out.append(Path(os.path.relpath(os.path.normpath(text), cwd)).as_posix())
        else:
            out.append(text)
    return out


def is_portable(rel: str) -> bool:
    """True iff ``rel`` is a repo-relative POSIX path that stays inside the root."""
    if (
        not rel
        or "\\" in rel
        or rel.startswith("/")
        or (len(rel) > 1 and rel[1] == ":")
    ):
        return False
    return ".." not in PurePosixPath(rel).parts


# EOF
