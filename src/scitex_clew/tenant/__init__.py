#!/usr/bin/env python3
"""Clew's records in a host's per-tenant private store — the public surface.

A host (the SciTeX Hub) gives every project owner a private PostgreSQL
namespace and opens Clew's records there through an unprivileged tenant login
(``scitex_dev.store.TenantScope``). Which stores Clew keeps, and which project
scope a project's records carry, are Clew's decisions, so they are published
here instead of being re-typed by the host:

* :func:`tenant_schemas` — the stores the hosted Clew app reads. The request
  worker checks exactly these before answering, so a host that provisions
  this tuple provisions what the worker needs.
* :func:`provision_tenant` — create those stores in a tenant namespace through
  a separate migration connection. Idempotent: a store that is already
  provisioned and passes the worker's catalogue check is left alone.
* :func:`project_scope_for` — the scope a project's records carry: the id
  persisted at ``<root>/.scitex/clew/project-id``, the same file a Clew run
  inside that project reads, minted once if absent.

Creating the tenant LOGIN (and its password) is the host's job, as it is in
``scitex_dev.store``: Clew never creates credentials.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from scitex_dev.store import Schema, StoreTarget, TenantScope

__all__ = [
    "TenantProvisionError",
    "project_scope_for",
    "provision_tenant",
    "tenant_schemas",
]


class TenantProvisionError(RuntimeError):
    """A tenant store exists but does not pass the worker's catalogue check."""


def tenant_schemas() -> tuple[Schema, ...]:
    """The stores the hosted Clew app reads, in the order it checks them."""
    from .._claim._store import _CLAIMS_SCHEMA
    from .._db._schema import (
        FILE_HASHES_SCHEMA,
        RUNS_SCHEMA,
        SESSION_PARENTS_SCHEMA,
        VERIFICATION_RESULTS_SCHEMA,
    )

    return (
        RUNS_SCHEMA,
        FILE_HASHES_SCHEMA,
        VERIFICATION_RESULTS_SCHEMA,
        SESSION_PARENTS_SCHEMA,
        _CLAIMS_SCHEMA,
    )


def _ready(tenant_dsn: str, schema: Schema, scope: TenantScope, owner_role: str):
    """The worker's own check, run as the tenant login."""
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        from .._django._optional import gui_dependency_error

        gui_dependency_error(exc)
    from scitex_dev.store import inspect_tenant_store

    with psycopg.connect(tenant_dsn) as connection:
        return inspect_tenant_store(connection, schema, scope, owner_role=owner_role)


def provision_tenant(
    migration_target: StoreTarget,
    tenant_dsn: str,
    scope: TenantScope,
    *,
    owner_role: str = "scitex_cloud_owner",
) -> tuple[str, ...]:
    """Provision every :func:`tenant_schemas` store for ``scope``; idempotent.

    Parameters
    ----------
    migration_target : scitex_dev.store.StoreTarget
        The separate administration connection. Request processes never hold it.
    tenant_dsn : str
        The tenant login's DSN, used only to confirm an existing store with the
        worker's catalogue check.
    scope : scitex_dev.store.TenantScope
        The tenant. Its LOGIN must already exist, unprivileged.
    owner_role : str
        The NOLOGIN, NOBYPASSRLS owner of tenant namespaces.

    Returns
    -------
    tuple of str
        Names of the stores created by this call (empty when all existed).

    Raises
    ------
    TenantProvisionError
        A store already exists but fails the catalogue check (for example its
        row-level security was weakened). Nothing is repaired automatically.
    scitex_dev.store.StoreProvisionError
        The tenant login or owner role is missing or privileged.
    """
    from scitex_dev.store import StoreProvisionError, provision_tenant_store

    created = []
    for schema in tenant_schemas():
        try:
            provision_tenant_store(
                migration_target, schema, scope, owner_role=owner_role
            )
        except StoreProvisionError as refused:
            # Refused: either the store is already there (a repeat call), or
            # the login/owner/namespace is wrong. Only the worker's own check,
            # as the tenant, may tell those apart; a login that cannot even
            # connect is the original refusal.
            try:
                status = _ready(tenant_dsn, schema, scope, owner_role)
            except Exception:  # noqa: BLE001 - re-raise the cause, not this
                raise refused from None
            if status.ready:
                continue
            raise TenantProvisionError(
                f"store {schema.name!r} of tenant {scope.tenant_id} was refused "
                f"({refused}) and fails the worker's check: "
                f"{'; '.join(status.issues)}"
            ) from refused
        created.append(schema.name)
    return tuple(created)


def project_scope_for(project_root: str | Path, *, create: bool = True) -> str | None:
    """The Clew project scope of the project at ``project_root``.

    Reads ``<root>/.scitex/clew/project-id``, the id every Clew run inside the
    project uses. When it is absent and ``create`` is true, mints it there
    exactly once (the same race-safe mint a run performs), so records written
    later by runs in that project land in the scope the host reads.

    Returns ``None`` only when the id is absent and ``create`` is false.

    Raises
    ------
    OSError
        The id could not be persisted. A host must not fall back to a
        path-derived scope: it would silently split the project's records.
    """
    from .._db._scope import _mint_project_id, _read_project_id, project_id_path

    path = project_id_path(Path(project_root))
    persisted = _read_project_id(path)
    if persisted or not create:
        return persisted
    minted = _mint_project_id(path)
    if minted is None:
        raise OSError(f"could not persist the Clew project id at {path}")
    return minted


# EOF
