#!/usr/bin/env python3
"""clew as a dataset provenance provider (contract ``scitex-dataset.provenance-readers`` 1.1.0).

Coupling is only through scitex-dataset's published, provider-neutral
contract: clew does not import scitex-dataset and scitex-dataset does not
import clew. It discovers :class:`ReadersEntry` through the
``scitex.dataset.provenance`` entry-point group::

    [project.entry-points."scitex.dataset.provenance"]
    clew = "scitex_clew._dataset_readers:ReadersEntry"

The schema of the return value is vendored, version-pinned, as
``provenance-readers.schema.1.0.0.json`` (copied verbatim from
scitex-dataset's ``src/scitex_dataset/project/``); 1.1.0 did not change it.

1.1.0 adds ``store``: the host's routing to the project's OWN record store
(``{"tenant_id", "dsn", "project_scope", "owner_role"}``, the fields of
``scitex_sdk.host.StoreAccess``). A Hub keeps each project's records in a
tenant store; reading the process's ambient store instead finds nothing for
the project, which is how a Hub project showed no readers at all. With
``store`` the query runs in clew's isolated tenant worker (the same one the
Clew app uses), after the tenant catalogue check, never in this process.

Read-only by construction: a project clew has never scoped (no
``.scitex/clew/project-id``) has no records, and it is answered without
opening the store — opening it would MINT a project id, i.e. write into a
project the caller may only read.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

CONTRACT_VERSION = "1.1.0"
PROVIDER_NAME = "clew"
SCHEMA_PATH = Path(__file__).with_name("provenance-readers.schema.1.0.0.json")
_STORE_FIELDS = ("tenant_id", "dsn", "project_scope", "owner_role")

__all__ = [
    "CONTRACT_VERSION",
    "PROVIDER_NAME",
    "SCHEMA_PATH",
    "ReadersEntry",
    "load_schema",
    "readers",
    "records_from_db",
]


def load_schema() -> dict:
    """The vendored provenance-readers JSON Schema (draft 2020-12)."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _display_path(path: str | None, root: Path) -> str | None:
    if not path:
        return None
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        return path


def records_from_db(db, root: Path, paths: Sequence[str]) -> dict[str, list[dict]]:
    """The read records of ``paths`` (project-relative) in an OPEN clew db.

    Newest run first. A path no run read is absent from the result.
    """
    absolute = {str((root / p).resolve()): p for p in paths}
    sessions = db.find_sessions_by_files(list(absolute), role="input")
    out: dict[str, list[dict]] = {}
    runs: dict[str, dict | None] = {}
    for abs_path, session_ids in sessions.items():
        records = []
        for session_id in session_ids:
            if session_id not in runs:
                runs[session_id] = db.get_run(session_id)
            run = runs[session_id]
            if run is None or not run.get("script_path"):
                continue
            records.append(
                {
                    "script": _display_path(run.get("script_path"), root),
                    "run_id": session_id,
                    "started_at": run.get("started_at"),
                    "status": run.get("status"),
                }
            )
        if records:
            out[absolute[abs_path]] = records
    return out


def _routed(root: Path, paths: Sequence[str], store: Mapping) -> dict[str, list[dict]]:
    """Ask the project's tenant store, through clew's isolated worker."""
    missing = [k for k in _STORE_FIELDS if not store.get(k)]
    if missing:
        raise ValueError(f"store routing is missing {', '.join(missing)}")
    from .._django.services.project_store import execute

    context = {k: str(store[k]) for k in _STORE_FIELDS}
    context["root"] = str(root)
    answer = execute(context, "dataset_readers", {"paths": list(paths)})
    if not isinstance(answer, Mapping):
        raise TypeError("the tenant worker returned no readers mapping")
    return dict(answer)


def readers(
    project_root: str, paths: Sequence[str], *, store: Mapping | None = None
) -> dict[str, list[dict]]:
    """Scripts clew recorded as READING each project-relative path.

    ``store`` routes the query to the project's tenant store (contract 1.1);
    without it the process's configured store is read.
    """
    from ._paths import project_scope_exists

    root = Path(project_root).resolve()
    if not paths or not project_scope_exists(root):
        return {}
    if store is not None:
        return _routed(root, paths, store)

    from .._db import get_db
    from .._db._paths import project_root as project_root_cm

    with project_root_cm(root):
        return records_from_db(get_db(), root, paths)


class ReadersEntry:
    """Entry-point object for the ``scitex.dataset.provenance`` group."""

    name = PROVIDER_NAME
    contract_version = CONTRACT_VERSION

    def readers(
        self, project_root: str, paths: Sequence[str], *, store: Mapping | None = None
    ) -> dict[str, list[dict]]:
        return readers(project_root, paths, store=store)


# EOF
