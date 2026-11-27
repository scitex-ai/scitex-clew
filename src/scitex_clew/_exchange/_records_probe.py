#!/usr/bin/env python3
"""Read-only preflight of the target store before a records import.

WHY
---
Opening a ``Store`` on a table that does not exist issues
``CREATE TABLE IF NOT EXISTS``. On a self-managed store that is what every
clew command does; on a tenant store (``provision_tenant_store``: a login
with no CREATE right) or a managed store (``provision_store_acl``) it fails
— mid-import, after other tables may already be written. A Hub tenant is
provisioned with only the schemas its Clew app reads, so an export carrying
rows for another store (e.g. ``environments``) hit exactly that.

So the import asks the catalogue first, with SELECTs only: which store
objects are missing, and may this login create them? It opens a ``Store``
only for a table that is complete, or that it may legitimately create.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["StoreProbe", "probe_store"]


@dataclass(frozen=True)
class StoreProbe:
    """What the catalogue says about one store, before anything is opened."""

    missing: tuple[str, ...]  #: absent tables / ``table.column`` the Store needs
    may_create: bool  #: this login may create them (self-managed store)

    @property
    def ready(self) -> bool:
        return not self.missing


def _first(row) -> object:
    return row[next(iter(row.keys()))] if hasattr(row, "keys") else row[0]


def probe_store(target, schema) -> StoreProbe:
    """The objects ``Store(target, schema)`` needs that are absent, read-only.

    ``may_create`` is True only when this login holds CREATE on the schema AND
    the database does not declare the managed owner/writer role contract (a
    managed store refuses application DDL even when the login could run it).
    """
    from scitex_dev.store._dialect import get_dialect
    from scitex_dev.store._provision import requires_privileged_provisioning

    dialect = get_dialect(target.backend)
    connection = dialect.connect(target)
    try:
        missing: list[str] = []
        for table in dialect.schema_tables(schema):
            if not connection.execute(dialect.columns_sql(table)).fetchall():
                missing.append(table)
        rows_table = dialect.rows_table(schema)
        if rows_table not in missing:
            present = {
                str(_first(r))
                for r in connection.execute(dialect.columns_sql(rows_table)).fetchall()
            }
            missing += [f"{rows_table}.{f}" for f in schema.fields if f not in present]
        for table, column, _type, _default in dialect.additive_columns(schema):
            if table in missing:
                continue
            present = {
                str(_first(r))
                for r in connection.execute(dialect.columns_sql(table)).fetchall()
            }
            if column not in present:
                missing.append(f"{table}.{column}")
        can_create = bool(
            _first(
                connection.execute(
                    "SELECT has_schema_privilege(current_schema(), 'CREATE')"
                ).fetchone()
            )
        )
        managed = requires_privileged_provisioning(connection)
        return StoreProbe(missing=tuple(missing), may_create=can_create and not managed)
    finally:
        connection.close()


# EOF
