#!/usr/bin/env python3
"""Move one project's clew records between stores, through a file.

WHY
---
A researcher's records live in one store (a private PostgreSQL) and must
reach another (a Cloud tenant store whose Clew app reads a fixed project
scope) WITHOUT the target ever connecting to the source. The evidence bundle
(:mod:`._export`) is a store-free REVIEW format: it keeps what a third party
needs to check a checkout, not the rows clew's own read paths query. This
module keeps the rows themselves.

FORMAT (``scitex-clew.project-records`` 1.0.0)
----------------------------------------------
A JSON document::

    {"schema": "scitex-clew.project-records", "schema_version": "1.0.0",
     "clew_version": ..., "exported_at": ..., "source": {"project": SCOPE},
     "counts": {TABLE: N}, "tables": {TABLE: {"rows": [
         {"values": {FIELD: VALUE, ...}, "hidden": BOOL}, ...]}},
     "payload_sha256": HEX}

* Every table of every clew store the verify / slice / claims / Clew-app read
  paths use (:data:`RECORD_TABLES`) — all of them, so an imported project
  answers exactly as the source did.
* ``values`` omit the ``project`` field: the scope is not a property of a
  record but of where it is filed, and import rewrites it.
* ``hidden`` carries soft-deletion (a removed claim) instead of dropping it.
* ``payload_sha256`` is the SHA-256 of the canonical JSON (sorted keys, no
  whitespace, UTF-8) of the whole document without that key. Import refuses
  a document whose checksum does not match.
* Values only: no DSN, no host, no credentials.

IMPORT SEMANTICS (idempotent)
-----------------------------
Per record, keyed by its identity fields under the TARGET scope:

* absent                    -> created;
* present, identical        -> unchanged (SKIPPED — nothing is written, so a
                               re-import adds no oplog entries);
* present, different        -> updated: the document's values REPLACE the
                               record's (every field, including NULLs);
* a different value in a write-once (IMMUTABLE) field -> the whole import is
  REFUSED before anything is written (two different histories for one key
  is a contradiction to resolve by hand, not to merge).

Writes go through ``scitex_dev.store.Store`` on existing tables, which issues
DML only — so a store provisioned by an admin (a NOLOGIN owner role plus a
DML-only login, ``provision_store_acl``) accepts an import from its login
role. A table that does not exist there makes ``Store()`` refuse with
``StoreProvisionError``; the import never attempts DDL to work around it.
"""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ._canonical import sha256_bytes

__all__ = [
    "RECORDS_SCHEMA",
    "RECORDS_SCHEMA_VERSION",
    "RECORD_TABLES",
    "RecordsDocumentError",
    "RecordsImportConflict",
    "build_records",
    "import_records",
    "load_records",
    "records_checksum",
    "write_records",
]

RECORDS_SCHEMA = "scitex-clew.project-records"
RECORDS_SCHEMA_VERSION = "1.0.0"
CHECKSUM_KEY = "payload_sha256"


class RecordsDocumentError(ValueError):
    """The file is not an intact project-records document this clew reads."""


class RecordsImportConflict(RuntimeError):
    """A write-once field differs between the document and the target store."""


def _schemas() -> dict:
    """Every clew store schema, by store name, in a stable order."""
    from .._attest._stamp import STAMPS_SCHEMA
    from .._citation._model import CITATIONS_SCHEMA
    from .._claim._store import _CLAIMS_SCHEMA
    from .._db._schema import (
        ENVIRONMENTS_SCHEMA,
        FILE_HASHES_SCHEMA,
        RUNS_SCHEMA,
        SESSION_PARENTS_SCHEMA,
        VERIFICATION_RESULTS_SCHEMA,
    )

    return {
        "runs": RUNS_SCHEMA,
        "file_hashes": FILE_HASHES_SCHEMA,
        "verification_results": VERIFICATION_RESULTS_SCHEMA,
        "session_parents": SESSION_PARENTS_SCHEMA,
        "environments": ENVIRONMENTS_SCHEMA,
        "claims": _CLAIMS_SCHEMA,
        "citations": CITATIONS_SCHEMA,
        "stamps": STAMPS_SCHEMA,
    }


#: The tables a project-records document carries — every clew store.
RECORD_TABLES: tuple[str, ...] = (
    "runs",
    "file_hashes",
    "verification_results",
    "session_parents",
    "environments",
    "claims",
    "citations",
    "stamps",
)


def _record_fields(schema) -> list[str]:
    """The fields a document row carries: all but the scope and hide flag."""
    from .._db._scope import PROJECT_FIELD

    return [
        name
        for name in schema.fields
        if name != PROJECT_FIELD and name != schema.hide_flag_field
    ]


def _identity(schema, values: Mapping[str, Any]) -> tuple:
    """The record key under a scoped store (identity minus ``project``)."""
    from .._db._scope import PROJECT_FIELD

    return tuple(values[n] for n in schema.identity_fields if n != PROJECT_FIELD)


def _target(name: str):
    from scitex_dev.store import host_store

    return host_store(pkg="scitex_clew", name=name)


def _open(name: str, schema, project: str):
    """One clew store, scoped to ``project`` (the same seam clew writes through)."""
    from scitex_dev.store import Store, WriterPolicy

    from .._db._schema import resolve_node_id
    from .._db._scope import ProjectScopedStore

    store = Store(
        _target(name),
        schema,
        node=resolve_node_id(),
        writer_policy=WriterPolicy.MULTI_WRITER,
    )
    return ProjectScopedStore(store, project=project)


def _clew_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("scitex-clew")
    except Exception:  # noqa: BLE001 - an unknown version is recorded as null
        return None


def records_checksum(document: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON of ``document`` without its checksum."""
    payload = {k: v for k, v in document.items() if k != CHECKSUM_KEY}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_bytes(raw.encode("utf-8"))


def _export_row(row, fields: list[str]) -> dict:
    values = {name: row.values.get(name) for name in fields}
    return {"values": values, "hidden": bool(row.hidden)}


def build_records(project: str | None = None) -> dict:
    """Every record of ``project`` (default: the current scope), as a document."""
    from .._db._scope import resolve_project_scope

    scope = project or resolve_project_scope()
    tables: dict[str, dict] = {}
    for name, schema in _schemas().items():
        fields = _record_fields(schema)
        store = _open(name, schema, scope)
        try:
            rows = [_export_row(r, fields) for r in store.rows(include_hidden=True)]
        finally:
            store.close()
        rows.sort(key=lambda r: json.dumps(_identity(schema, r["values"]), default=str))
        tables[name] = {"rows": rows}
    document = {
        "schema": RECORDS_SCHEMA,
        "schema_version": RECORDS_SCHEMA_VERSION,
        "clew_version": _clew_version(),
        "exported_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        "source": {"project": scope},
        "counts": {name: len(t["rows"]) for name, t in tables.items()},
        "tables": tables,
    }
    document[CHECKSUM_KEY] = records_checksum(document)
    return document


def write_records(document: Mapping[str, Any], path: str | Path) -> Path:
    """Write ``document`` as pretty, key-sorted UTF-8 JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def _validate(document: Any) -> None:
    """Refuse anything but an intact document whose tables this clew knows."""
    if not isinstance(document, dict):
        raise RecordsDocumentError("not a JSON object")
    if document.get("schema") != RECORDS_SCHEMA:
        raise RecordsDocumentError(
            f"schema is {document.get('schema')!r}, expected {RECORDS_SCHEMA!r}"
        )
    if document.get("schema_version") != RECORDS_SCHEMA_VERSION:
        raise RecordsDocumentError(
            f"schema_version {document.get('schema_version')!r} is not supported "
            f"by this clew (reads {RECORDS_SCHEMA_VERSION}); upgrade scitex-clew"
        )
    stated = document.get(CHECKSUM_KEY)
    actual = records_checksum(document)
    if stated != actual:
        raise RecordsDocumentError(
            f"{CHECKSUM_KEY} mismatch (stated {stated!r}, computed {actual!r}): "
            "the file was altered or truncated after export"
        )
    tables = document.get("tables")
    if not isinstance(tables, dict):
        raise RecordsDocumentError("'tables' is missing or not an object")
    schemas = _schemas()
    unknown = sorted(set(tables) - set(schemas))
    if unknown:
        raise RecordsDocumentError(f"unknown table(s) {unknown}; upgrade scitex-clew")
    for name, table in tables.items():
        rows = table.get("rows") if isinstance(table, dict) else None
        if not isinstance(rows, list):
            raise RecordsDocumentError(f"table {name!r} has no 'rows' list")
        fields = set(_record_fields(schemas[name]))
        for row in rows:
            values = row.get("values") if isinstance(row, dict) else None
            if not isinstance(values, dict):
                raise RecordsDocumentError(f"table {name!r}: a row has no 'values'")
            extra = sorted(set(values) - fields)
            if extra:
                raise RecordsDocumentError(
                    f"table {name!r}: field(s) {extra} unknown to this clew's "
                    "schema; upgrade scitex-clew"
                )


def load_records(path: str | Path) -> dict:
    """Read and validate a project-records document (schema + checksum)."""
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RecordsDocumentError(f"not valid JSON: {exc}") from exc
    _validate(document)
    return document


def _incoming(schema, row: Mapping[str, Any]) -> tuple[dict, bool]:
    """The full replacement values for one document row (absent -> None)."""
    values = row["values"]
    return {n: values.get(n) for n in _record_fields(schema)}, bool(row.get("hidden"))


def _classify(schema, existing, values: dict, hidden: bool) -> tuple[str, list]:
    """``created`` / ``unchanged`` / ``updated``, plus write-once conflicts."""
    from scitex_dev.store import MergeRule

    if existing is None:
        return "created", []
    current = {n: existing.values.get(n) for n in values}
    if current == values and bool(existing.hidden) == hidden:
        return "unchanged", []
    conflicts = [
        n
        for n, v in values.items()
        if schema.fields[n].merge is MergeRule.IMMUTABLE
        and n not in schema.identity_fields
        and current[n] is not None
        and current[n] != v
    ]
    return "updated", conflicts


def _plan_table(name: str, schema, rows: list, project: str):
    """Classify every row against the target; returns (store, plan).

    Opening the store is what any clew command does: on a self-managed store
    with no clew tables yet, ``Store()`` creates them (empty); a managed or
    tenant store is never altered (``Store()`` refuses instead).
    """
    store = _open(name, schema, project)
    plan = []
    for row in rows:
        values, hidden = _incoming(schema, row)
        existing = store.get(_identity(schema, values), include_hidden=True)
        action, conflicts = _classify(schema, existing, values, hidden)
        if conflicts:
            store.close()
            raise RecordsImportConflict(
                f"table {name!r} record {_identity(schema, values)!r}: write-once "
                f"field(s) {conflicts} differ from the target store's values. "
                "Nothing was imported."
            )
        plan.append((action, values, hidden, existing))
    return store, plan


def _apply(name: str, store, plan: list) -> None:
    from scitex_dev.store import ANY_REVISION

    with store.batch():
        for action, values, hidden, existing in plan:
            if action == "unchanged":
                continue
            result = store.put(values, expected_revision=ANY_REVISION)
            if result.conflicts:
                raise RecordsImportConflict(
                    f"table {name!r}: the store kept its own value for "
                    f"{[c.field for c in result.conflicts]} — rolled back"
                )
            was_hidden = bool(existing.hidden) if existing is not None else False
            if hidden != was_hidden:
                key = _identity(store.schema, values)
                verb = store.hide if hidden else store.unhide
                verb(key, expected_revision=ANY_REVISION)


def import_records(
    document: Mapping[str, Any],
    *,
    project: str | None = None,
    dry_run: bool = False,
    rebase: list[tuple[str, str]] | None = None,
) -> dict:
    """Write a validated document's records into the current store.

    ``project`` is the TARGET scope (default: the current resolved scope);
    every record is filed under it. Returns per-table counts. Every table is
    planned (and checked for write-once conflicts) before any is written.

    ``rebase`` (from :func:`._rebase.parse_rebase`) moves the source
    checkout's paths to the target's before anything is planned; the report's
    ``paths`` says how many moved and which stayed external.
    """
    from .._db._scope import resolve_project_scope
    from ._rebase import rebase_tables

    _validate(document)
    scope = project or resolve_project_scope()
    schemas = _schemas()
    tables, paths = rebase_tables(document["tables"], list(rebase or []))
    planned = []
    try:
        for name, table in tables.items():
            planned.append(
                (
                    name,
                    *_plan_table(name, schemas[name], table["rows"], scope),
                )
            )
        report = {}
        for name, store, plan in planned:
            counts = {"rows": len(plan), "created": 0, "updated": 0, "unchanged": 0}
            for action, *_rest in plan:
                counts[action] += 1
            report[name] = counts
            if not dry_run:
                _apply(name, store, plan)
    finally:
        for _name, store, _plan in planned:
            store.close()
    return {
        "schema": RECORDS_SCHEMA,
        "schema_version": RECORDS_SCHEMA_VERSION,
        "source_project": (document.get("source") or {}).get("project"),
        "target_project": scope,
        "dry_run": dry_run,
        "tables": report,
        "paths": paths,
    }


# EOF
