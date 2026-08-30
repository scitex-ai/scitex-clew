#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project scoping for clew's stores — resolved in ONE place.

WHY THIS EXISTS
---------------
Before the Postgres migration each project had its OWN database file, and
that file did the scoping: ``claim_id`` and ``cite_key`` are chosen by the
author, so two manuscripts could both hold a claim called
``acute_n_sig_pathways`` or both cite ``smith2020`` and never meet.

One host database collapses that. Without a project component in the
record IDENTITY, those two rows are the SAME row, and
``MergeRule.LAST_WRITER_WINS`` picks a winner silently — one manuscript's
provenance overwriting another's, with nothing raising. In a provenance
system that is the least acceptable place for silent data loss.

So the project becomes part of the identity tuple, exactly as
``host_store()`` is the one place that answers "which store". This module
is the one place that answers "which project", and
:class:`ProjectScopedStore` is the one place that applies it — reads and
writes go through the same resolution, so a lookup cannot miss a row it
just wrote.

WHAT THE SCOPE VALUE IS
-----------------------
A minted id PERSISTED INSIDE THE PROJECT, at
``<project_root>/.scitex/clew/project-id``. Resolution, in one place:

1. ``$SCITEX_CLEW_PROJECT`` if set — an explicit override wins outright,
   matching ``host_store()``'s treatment of ``SCITEX_STORE_DSN``.
2. Otherwise the persisted id, if the file is there.
3. Otherwise mint one, write it, and use it.

WHY NOT THE PROJECT PATH. Deriving the scope from the absolute path is the
obvious move and it is wrong here. clew exists to keep a chain-verified
provenance DAG, and a path-derived scope truncates that chain the moment
somebody renames a directory — silently, in the one way this package is
supposed to prevent. The old design never had that failure: the store FILE
lived inside the project, so it travelled with the directory and a ``mv``
kept everything. An id file restores exactly that property. Telling
operators to set ``$SCITEX_CLEW_PROJECT`` first is not a fix, because
whoever moves the directory finds out afterwards.

WHY THE FILE IS NOT COMMITTED. On mint, a sibling ``.gitignore`` is written
naming it (only when no ``.gitignore`` is already there). Two reasons.
First, it matches what the old layout did: the store lived under
``.scitex/clew/runtime/``, which is gitignored, so a fresh clone started an
empty chain rather than adopting another checkout's. Second, a committed id
would be inherited by every fork and template-copy of a paper, handing two
unrelated manuscripts the SAME provenance scope — reintroducing the
collision class this module exists to close, in a way that looks
deliberate.

WHEN THE OVERRIDE AND THE FILE DISAGREE, the override wins, the file is
left untouched, and a warning is logged. Refusing outright was the
alternative and it is worse here: it would make clew unusable in any
project that has an id whenever the variable happens to be set — including
CI that pins a scope on purpose — and an override that cannot override is
not one. The write is suppressed so a one-off override can never silently
re-stamp the project's identity.

DEGRADED CASE: if the id cannot be written (a read-only checkout), the
scope falls back to the project path and warns. A move then loses history
exactly as it would have before this change — no worse, and noisy instead
of silent.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._paths import _find_project_root

logger = logging.getLogger(__name__)

__all__ = [
    "PROJECT_FIELD",
    "PROJECT_ID_FILENAME",
    "PROJECT_SCOPE_ENV",
    "ProjectScopedStore",
    "project_id_path",
    "resolve_project_scope",
]

#: The identity column carrying the scope. Declared FIRST in every scoped
#: schema, because a positional key is matched against
#: ``schema.identity_fields`` in DECLARATION ORDER.
PROJECT_FIELD: str = "project"

#: Explicit override. Lets two checkouts share one logical project, or CI
#: pin a scope. Wins outright, and never rewrites the persisted id.
PROJECT_SCOPE_ENV: str = "SCITEX_CLEW_PROJECT"

#: The persisted id, inside clew's own per-project directory. NOT under
#: ``runtime/``: that directory is documented as regenerable and safe to
#: delete, and this file is neither — losing it severs the chain.
PROJECT_ID_FILENAME: str = "project-id"

#: Written beside the id on mint, so the id is not committed. See the
#: module docstring for why a shared id is worse than a fresh one.
_GITIGNORE_BODY = (
    "# clew's per-project provenance id. Not committed: a fork or\n"
    "# template-copy that inherited it would silently share another\n"
    "# manuscript's provenance scope.\n"
    f"{PROJECT_ID_FILENAME}\n"
)

#: One warning per process, not one per store construction.
_warned: set = set()


def _warn_once(key: str, message: str) -> None:
    if key not in _warned:
        _warned.add(key)
        logger.warning(message)


def project_id_path(project_root: "Path | None" = None) -> Path:
    """Where this project's id lives."""
    root = project_root if project_root is not None else _find_project_root()
    return Path(root) / ".scitex" / "clew" / PROJECT_ID_FILENAME


def _read_project_id(path: Path) -> "str | None":
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _mint_project_id(path: Path) -> "str | None":
    """Create the id exactly once, even against a concurrent writer.

    ``O_CREAT | O_EXCL`` is what makes this safe: two processes starting in
    a fresh project both try to create, exactly one wins, and the loser
    reads the winner's value rather than overwriting it with its own. A
    write-then-rename would let the loser silently re-stamp the project.
    """
    minted = f"clew-{uuid.uuid4().hex}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return _read_project_id(path)
    except OSError:
        return None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(minted + "\n")
    except OSError:
        return None
    _write_sibling_gitignore(path.parent)
    return minted


def _write_sibling_gitignore(directory: Path) -> None:
    """Keep the id out of git — best effort, never fatal.

    Left alone when a ``.gitignore`` is already there: silently editing a
    file the project owns is worse than the id being committed, and the
    module docstring says what to do about it.
    """
    ignore = directory / ".gitignore"
    try:
        if not ignore.exists():
            ignore.write_text(_GITIGNORE_BODY, encoding="utf-8")
    except OSError:
        pass


def resolve_project_scope() -> str:
    """The project these records belong to. The ONLY definition of it."""
    override = os.environ.get(PROJECT_SCOPE_ENV)
    override = override.strip() if override else ""
    root = _find_project_root().resolve()
    path = project_id_path(root)

    if override:
        persisted = _read_project_id(path)
        if persisted and persisted != override:
            _warn_once(
                f"override:{path}",
                f"clew: {PROJECT_SCOPE_ENV}={override!r} overrides the id "
                f"persisted at {path} ({persisted!r}). Records written now "
                "belong to the override's scope, not this project's. The "
                "persisted id is left untouched.",
            )
        return override

    persisted = _read_project_id(path)
    if persisted:
        return persisted

    minted = _mint_project_id(path)
    if minted:
        return minted

    _warn_once(
        f"unwritable:{path}",
        f"clew: could not persist a project id at {path}, so this "
        "project's scope falls back to its absolute path. Provenance "
        "written now becomes invisible if the directory is ever moved. "
        f"Set {PROJECT_SCOPE_ENV} to a stable value to pin it.",
    )
    return str(root)


class ProjectScopedStore:
    """A ``Store`` whose records are confined to one project.

    Wraps rather than subclasses so there is exactly one seam: every read
    filters on the scope and every write stamps it, using the SAME
    ``resolve_project_scope()`` call. Call sites are unchanged — they never
    mention the project, which is the point. A scope threaded by hand
    through ~200 call sites is a scope that will be forgotten at one of
    them, and the forgotten one is silent.

    The scope is captured at construction, so a store opened before the
    environment changes keeps answering for the project it was opened for.
    """

    def __init__(self, store, project: "str | None" = None) -> None:
        self._store = store
        self._project = project if project is not None else resolve_project_scope()

    # -- introspection ----------------------------------------------------
    @property
    def project(self) -> str:
        return self._project

    @property
    def target(self):
        return self._store.target

    @property
    def schema(self):
        return self._store.schema

    def __repr__(self) -> str:
        return (
            f"ProjectScopedStore(project={self._project!r}, "
            f"store={self._store!r})"
        )

    # -- key handling -----------------------------------------------------
    def _key(self, key: "Mapping[str, Any] | Sequence[Any] | str"):
        """Prepend the scope to a positional key, or add it to a mapping.

        A bare string is a single-component key, not a sequence of
        characters — matching ``record_key_from``'s own rule.
        """
        if isinstance(key, Mapping):
            return {PROJECT_FIELD: self._project, **key}
        if isinstance(key, str):
            key = (key,)
        return (self._project, *tuple(key))

    def _values(self, values: Mapping[str, Any]) -> dict:
        return {PROJECT_FIELD: self._project, **dict(values)}

    # -- reads ------------------------------------------------------------
    def rows(self, *, include_hidden: bool = False) -> list:
        return [
            row
            for row in self._store.rows(include_hidden=include_hidden)
            if row.values.get(PROJECT_FIELD) == self._project
        ]

    def get(self, key, *, include_hidden: bool = False):
        return self._store.get(self._key(key), include_hidden=include_hidden)

    def is_hidden(self, key):
        return self._store.is_hidden(self._key(key))

    # -- writes -----------------------------------------------------------
    def put(self, values: Mapping[str, Any], **kwargs):
        return self._store.put(self._values(values), **kwargs)

    def hide(self, key, **kwargs):
        return self._store.hide(self._key(key), **kwargs)

    def unhide(self, key, **kwargs):
        return self._store.unhide(self._key(key), **kwargs)

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> "ProjectScopedStore":
        self._store.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self._store.__exit__(*exc)


# EOF
