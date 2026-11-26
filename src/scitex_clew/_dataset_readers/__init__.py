#!/usr/bin/env python3
"""clew as a dataset provenance provider (contract ``scitex-dataset.provenance-readers`` 1.0.0).

Coupling is only through scitex-dataset's published, provider-neutral
contract: clew does not import scitex-dataset and scitex-dataset does not
import clew. It discovers :class:`ReadersEntry` through the
``scitex.dataset.provenance`` entry-point group::

    [project.entry-points."scitex.dataset.provenance"]
    clew = "scitex_clew._dataset_readers:ReadersEntry"

The schema of the return value is vendored, version-pinned, as
``provenance-readers.schema.1.0.0.json`` (copied verbatim from
scitex-dataset's ``src/scitex_dataset/project/``). Bump it only together
with :data:`CONTRACT_VERSION`.

Read-only by construction: a project clew has never scoped (no
``.scitex/clew/project-id``) has no records, and it is answered without
opening the store — opening it would MINT a project id, i.e. write into a
project the caller may only read.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

CONTRACT_VERSION = "1.0.0"
PROVIDER_NAME = "clew"
SCHEMA_PATH = Path(__file__).with_name(
    f"provenance-readers.schema.{CONTRACT_VERSION}.json"
)

__all__ = [
    "CONTRACT_VERSION",
    "PROVIDER_NAME",
    "SCHEMA_PATH",
    "ReadersEntry",
    "load_schema",
    "readers",
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


def readers(project_root: str, paths: Sequence[str]) -> dict[str, list[dict]]:
    """Scripts clew recorded as READING each project-relative path.

    Newest run first. A path no run read is absent from the result.
    """
    from ._paths import project_scope_exists

    root = Path(project_root).resolve()
    if not paths or not project_scope_exists(root):
        return {}

    from .._db import get_db
    from .._db._paths import project_root as project_root_cm

    absolute = {str((root / p).resolve()): p for p in paths}
    with project_root_cm(root):
        db = get_db()
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


class ReadersEntry:
    """Entry-point object for the ``scitex.dataset.provenance`` group."""

    name = PROVIDER_NAME
    contract_version = CONTRACT_VERSION

    def readers(self, project_root: str, paths: Sequence[str]) -> dict[str, list[dict]]:
        return readers(project_root, paths)


# EOF
