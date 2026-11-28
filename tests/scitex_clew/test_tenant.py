"""The public tenant surface a Cloud host uses to give a project its store.

Real PostgreSQL (the suite's writable DSN), real operator API, no mocks: a
tenant LOGIN is created the way a host creates it, then provisioned through
:func:`scitex_clew.tenant.provision_tenant`, then read by the hosted Clew
app's own request worker.
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager

import pytest

from tests.conftest import WRITABLE_DSN, _connect
from tests.scitex_clew._exchange._records_support import TENANT_OWNER, _dsn


@contextmanager
def _tenant_login():
    """An unprivileged tenant LOGIN (and the owner role), as a host creates them."""
    from scitex_dev.store import TenantScope

    scope, password = TenantScope(uuid.uuid4()), uuid.uuid4().hex
    created_owner = False
    with _connect() as conn:
        if (
            conn.execute(
                "SELECT 1 FROM pg_roles WHERE rolname=%s", (TENANT_OWNER,)
            ).fetchone()
            is None
        ):
            conn.execute(f"CREATE ROLE {TENANT_OWNER} NOLOGIN NOBYPASSRLS")
            created_owner = True
        conn.execute(f"CREATE ROLE {scope.principal} LOGIN PASSWORD '{password}'")
    try:
        yield scope, _dsn(scope.namespace, scope.principal, password)
    finally:
        with _connect() as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{scope.namespace}" CASCADE')
            roles = [scope.principal] + ([TENANT_OWNER] if created_owner else [])
            for role in roles:
                conn.execute(f"DROP OWNED BY {role}")
                conn.execute(f"DROP ROLE {role}")


def _admin():
    from scitex_dev.store import StoreTarget

    return StoreTarget.postgres(WRITABLE_DSN, pkg="scitex_clew")


@pytest.fixture(scope="module")
def provisioned():
    """Provision twice, then let the request worker read the result."""
    from scitex_clew._db import reset_db
    from scitex_clew._django.services.worker import execute
    from scitex_clew.tenant import provision_tenant

    with _tenant_login() as (scope, dsn):
        first = provision_tenant(_admin(), dsn, scope, owner_role=TENANT_OWNER)
        second = provision_tenant(_admin(), dsn, scope, owner_role=TENANT_OWNER)
        payload = {
            "dsn": dsn,
            "project_scope": "tenant-provision-scope",
            "root": os.getcwd(),
            "tenant_id": str(scope.tenant_id),
            "owner_role": TENANT_OWNER,
            "operation": "stats",
            "parameters": {},
        }
        cwd = os.getcwd()
        saved = {
            k: os.environ.get(k) for k in ("SCITEX_STORE_DSN", "SCITEX_CLEW_PROJECT")
        }
        try:
            reset_db()
            stats = execute(payload)
        finally:
            os.chdir(cwd)
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            reset_db()
        yield {"first": first, "second": second, "stats": stats}


def test_tenant_schemas_names_the_five_stores_the_worker_reads():
    # Arrange
    from scitex_clew.tenant import tenant_schemas

    # Act
    names = [schema.name for schema in tenant_schemas()]
    # Assert
    assert names == [
        "runs",
        "file_hashes",
        "verification_results",
        "session_parents",
        "claims",
    ]


def test_first_provisioning_creates_every_tenant_store(provisioned):
    # Arrange
    from scitex_clew.tenant import tenant_schemas

    # Act
    created = provisioned["first"]
    # Assert
    assert created == tuple(schema.name for schema in tenant_schemas())


def test_repeat_provisioning_creates_nothing(provisioned):
    # Arrange
    second = provisioned["second"]
    # Act
    created = len(second)
    # Assert
    assert created == 0


def test_the_request_worker_reads_a_provisioned_tenant(provisioned):
    # Arrange
    stats = provisioned["stats"]
    # Act
    backend = stats.get("backend")
    # Assert
    assert backend == "postgresql"


def test_provisioning_refuses_a_missing_tenant_login():
    # Arrange
    from scitex_clew.tenant import provision_tenant
    from scitex_dev.store import StoreProvisionError, TenantScope

    scope = TenantScope(uuid.uuid4())
    dsn = _dsn(scope.namespace, scope.principal, "no-such-login")
    # Act
    attempt = lambda: provision_tenant(_admin(), dsn, scope, owner_role=TENANT_OWNER)
    # Assert
    with pytest.raises(StoreProvisionError):
        attempt()


def test_project_scope_is_minted_into_the_project(tmp_path):
    # Arrange
    from scitex_clew.tenant import project_scope_for

    # Act
    scope = project_scope_for(tmp_path)
    # Assert
    assert (tmp_path / ".scitex/clew/project-id").read_text().strip() == scope


def test_project_scope_reuses_the_persisted_id(tmp_path):
    # Arrange
    from scitex_clew.tenant import project_scope_for

    first = project_scope_for(tmp_path)
    # Act
    again = project_scope_for(tmp_path)
    # Assert
    assert again == first


def test_project_scope_reads_an_id_a_run_already_wrote(tmp_path):
    # Arrange
    from scitex_clew.tenant import project_scope_for

    (tmp_path / ".scitex/clew").mkdir(parents=True)
    (tmp_path / ".scitex/clew/project-id").write_text("clew-existing\n")
    # Act
    scope = project_scope_for(tmp_path)
    # Assert
    assert scope == "clew-existing"


def test_project_scope_without_create_does_not_mint(tmp_path):
    # Arrange
    from scitex_clew.tenant import project_scope_for

    # Act
    scope = project_scope_for(tmp_path, create=False)
    # Assert
    assert scope is None
