#!/usr/bin/env python3
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

WHERE ``<project_root>`` IS comes from :func:`._paths.project_root_info`:
inside a scitex-session run, the root the session recorded; otherwise the
shared rule of :mod:`scitex_clew._core._project_root`. clew <= 0.24.3
walked up from cwd for ``.git``/``pyproject.toml`` only, so a non-git
project used from ``scripts/`` got its id in ``scripts/.scitex/clew/``. Such
a stale id (one the old rule would use, at a directory INSIDE the new root)
is MIGRATED BY HAND, never automatically: when the new root has
no id, the old one stays in use (history is not split) and a warning gives
the exact ``mv`` command; when both hold different ids, a warning names
both.

DEGRADED CASE: if the id cannot be written (a read-only checkout), the
scope falls back to the project path and warns. A move then loses history
exactly as it would have before this change — no worse, and noisy instead
of silent.
"""

from __future__ import annotations

import os
import shlex
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .._core._logging import getLogger
from ._deferred import DeferredWritesMixin
from ._paths import _find_project_root, _legacy_project_root, project_root_info

logger = getLogger(__name__)

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


def project_id_path(project_root: Path | None = None) -> Path:
    """Where this project's id lives."""
    root = project_root if project_root is not None else _find_project_root()
    return Path(root) / ".scitex" / "clew" / PROJECT_ID_FILENAME


def _read_project_id(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _mint_project_id(path: Path) -> str | None:
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


def _legacy_id_path(root: Path, via: str) -> Path | None:
    """A project id clew <= 0.24.3 left where the OLD root rule pointed.

    The old rule walked up from cwd to the first ``.git``/``pyproject.toml``
    with no ``$HOME`` ceiling, else used cwd — so a non-git project run from
    ``scripts/`` minted its id in ``scripts/.scitex/clew/``. Only meaningful
    when the root was detected or came from the session; an explicit
    ``project_root(...)`` is not compared against cwd.
    """
    if via == "argument":
        return None
    legacy = _legacy_project_root()
    # Only a location INSIDE the project (``proj/scripts``, ``repo/pkg``) can
    # hold this project's old id. Anything else — an unrelated repository
    # the run happened to start from, a stray ``~/pyproject.toml`` — holds
    # ANOTHER scope, and adopting it would merge two projects' provenance.
    if legacy == root or root not in legacy.parents:
        return None
    path = project_id_path(legacy)
    return path if _read_project_id(path) else None


def _move_command(legacy_dir: Path, new_dir: Path) -> str:
    """The exact shell command that moves clew's state to the new root."""
    q = shlex.quote
    if not new_dir.exists():
        return f"mkdir -p {q(str(new_dir.parent))} && mv {q(str(legacy_dir))} {q(str(new_dir))}"
    return (
        f"mv -n {q(str(legacy_dir / PROJECT_ID_FILENAME))} "
        f"{q(str(new_dir / PROJECT_ID_FILENAME))}"
    )


def _warn_legacy(legacy: Path, path: Path, info: dict, persisted: str | None) -> None:
    legacy_id = _read_project_id(legacy)
    rule = info.get("project_root_source")
    marker = info.get("project_root_marker")
    why = f"{rule} ({marker})" if marker else f"{rule}"
    if persisted is None:
        _warn_once(
            f"legacy:{legacy}",
            f"clew: MIGRATION NEEDED — this project's provenance id "
            f"{legacy_id!r} is at {legacy}, a location older clew chose "
            f"from the working directory. The project root is now "
            f"{info['project_root']} (rule: {why}, via "
            f"{info.get('via')}). clew keeps using the old id for now so "
            "no history is split, and has NOT moved anything. Move it:\n\n"
            f"    {_move_command(legacy.parent, path.parent)}\n",
        )
    elif persisted != legacy_id:
        _warn_once(
            f"legacy-split:{legacy}",
            f"clew: TWO provenance ids for one project — {persisted!r} at "
            f"{path} (in use; project root via rule {why}) and "
            f"{legacy_id!r} at {legacy} (left by older clew). Records under "
            "the old id are not visible here. Nothing was moved. To make the "
            "old id this project's, replace the new one:\n\n"
            f"    mv -f {shlex.quote(str(legacy))} {shlex.quote(str(path))}\n",
        )


def resolve_project_scope() -> str:
    """The project these records belong to. The ONLY definition of it."""
    override = os.environ.get(PROJECT_SCOPE_ENV)
    override = override.strip() if override else ""
    info = project_root_info()
    root = Path(info["project_root"]).resolve()
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
    legacy = _legacy_id_path(root, info.get("via", "detected"))
    if legacy is not None:
        _warn_legacy(legacy, path, info, persisted)
        if persisted is None:
            return _read_project_id(legacy)
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


class ProjectScopedStore(DeferredWritesMixin):
    """A ``Store`` whose records are confined to one project.

    Wraps rather than subclasses so there is exactly one seam: every read
    filters on the scope and every write stamps it, using the SAME
    ``resolve_project_scope()`` call. Call sites are unchanged — they never
    mention the project, which is the point. A scope threaded by hand
    through ~200 call sites is a scope that will be forgotten at one of
    them, and the forgotten one is silent.

    The scope is captured at construction, so a store opened before the
    environment changes keeps answering for the project it was opened for.

    Writes may be QUEUED (:meth:`defer_put`, see :mod:`._deferred`); every
    other access flushes the queue first, so this process never reads past
    a queued write.
    """

    def __init__(self, store, project: str | None = None) -> None:
        self._store = store
        self._project = project if project is not None else resolve_project_scope()
        self._init_deferred()

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
        return f"ProjectScopedStore(project={self._project!r}, store={self._store!r})"

    # -- key handling -----------------------------------------------------
    def _key(self, key: Mapping[str, Any] | Sequence[Any] | str):
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
        """Every row of THIS project — the project filter runs in SQL.

        One host database holds every project on the machine; filtering the
        scope client-side decoded every other project's rows too, so a read
        here cost O(all projects' records), not O(this project's).
        """
        from scitex_dev.store import Query

        query = Query().with_hidden() if include_hidden else Query()
        return self.search(query)

    def search(self, query):
        """This project's rows matching ``query`` — filtered in SQL, not Python.

        :meth:`rows` returns the WHOLE project; a per-file lookup through it
        costs O(project) per call. Use this for point queries (e.g. "output
        rows for these paths", "this session's rows").
        """
        from scitex_dev.store import eq

        self.flush()
        return self._store.search(query.where(eq(PROJECT_FIELD, self._project)))

    def batch(self):
        """One durable transaction for many writes (``Store.batch``).

        Journal ``flushed`` markers for rows written inside it are appended
        only when the outermost batch commits (see :mod:`._deferred`).
        """
        self.flush()
        return self._tracked_batch()

    def get(self, key, *, include_hidden: bool = False):
        self.flush()
        return self._store.get(self._key(key), include_hidden=include_hidden)

    def is_hidden(self, key):
        self.flush()
        return self._store.is_hidden(self._key(key))

    # -- writes -----------------------------------------------------------
    def put(self, values: Mapping[str, Any], **kwargs):
        self.flush()
        return self._store.put(self._values(values), **kwargs)

    def hide(self, key, **kwargs):
        self.flush()
        return self._store.hide(self._key(key), **kwargs)

    def unhide(self, key, **kwargs):
        self.flush()
        return self._store.unhide(self._key(key), **kwargs)

    # -- lifecycle --------------------------------------------------------
    def close(self) -> None:
        """Write any queued rows, then close (a close never drops records)."""
        try:
            self.flush()
        finally:
            self._store.close()

    def __enter__(self) -> ProjectScopedStore:
        self._store.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        try:
            self.flush()
        finally:
            self._store.__exit__(*exc)


# EOF
