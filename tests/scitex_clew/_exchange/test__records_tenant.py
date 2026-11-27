"""Import into a tenant store exactly as the Hub Clew app's worker reads it.

The target is provisioned by the operator API (``provision_tenant_store``:
a NOLOGIN owner, an unprivileged tenant LOGIN, FORCE row-level security, no
DDL rights for the login). The import runs AS that login, into a checkout at
a DIFFERENT root than the source's, with ``--rebase``; the real worker
(:func:`scitex_clew._django.services.worker.execute`) then reads it with its
own project root and its outside-the-project check. No mocks.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from contextlib import contextmanager

import pytest

from tests.conftest import WRITABLE_DSN, _connect

from ._records_support import TGT_SCOPE, _cli, _dsn, _env, _store, _verify_view

TENANT_OWNER = "scitex_cloud_owner"


@contextmanager
def _tenant_store():
    """A tenant namespace provisioned by the operator API; yields its login DSN."""
    from scitex_dev.store import StoreTarget, TenantScope, provision_tenant_store

    from scitex_clew._exchange._records import _schemas

    tenant = uuid.uuid4()
    scope, password = TenantScope(tenant), uuid.uuid4().hex
    created_owner = False
    with _connect() as conn:
        found = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (TENANT_OWNER,))
        if found.fetchone() is None:
            conn.execute(f"CREATE ROLE {TENANT_OWNER} NOLOGIN NOBYPASSRLS")
            created_owner = True
        conn.execute(f"CREATE ROLE {scope.principal} LOGIN PASSWORD '{password}'")
    admin = StoreTarget.postgres(WRITABLE_DSN, pkg="scitex_clew")
    try:
        for schema in _schemas().values():
            provision_tenant_store(admin, schema, scope, owner_role=TENANT_OWNER)
        yield tenant, _dsn(scope.namespace, scope.principal, password)
    finally:
        with _connect() as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{scope.namespace}" CASCADE')
            roles = [scope.principal] + ([TENANT_OWNER] if created_owner else [])
            for role in roles:
                conn.execute(f"DROP OWNED BY {role}")
                conn.execute(f"DROP ROLE {role}")


def _worker(tenant, dsn, root, operation):
    """The Hub Clew app's real read worker, as it runs per request."""
    from scitex_clew._db import reset_db
    from scitex_clew._django.services.worker import OutsideProject, execute

    payload = {"dsn": dsn, "project_scope": TGT_SCOPE, "root": str(root),
               "tenant_id": str(tenant), "owner_role": TENANT_OWNER,
               "operation": operation, "parameters": {}}  # fmt: skip
    cwd = os.getcwd()
    try:
        with _env(SCITEX_STORE_DSN=dsn, SCITEX_CLEW_PROJECT=TGT_SCOPE):
            reset_db()
            return execute(payload)
    except OutsideProject as exc:
        return exc
    finally:
        os.chdir(cwd)
        reset_db()


@contextmanager
def _cwd(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


@pytest.fixture(scope="module")
def tenant(source, tmp_path_factory):
    """Rebased import as the tenant login; and an un-rebased one for contrast."""
    src_root = source["out"].parent.resolve()
    dst_root = tmp_path_factory.mktemp("records-dst").resolve() / "checkout"
    shutil.copytree(src_root, dst_root)
    rebase = f"{src_root}={dst_root}"
    out = {"dst_root": dst_root}
    with _env(SCITEX_CLEW_AUTO_EXPORT_CLAIMS="0"):
        with _tenant_store() as (tenant_id, dsn):
            with _store(dsn, TGT_SCOPE):
                result = _cli(
                    "records",
                    "import",
                    str(source["out"]),
                    "--json",
                    "--rebase",
                    rebase,
                )
            out["result"] = result
            out["report"] = json.loads(result.output)
            out["status"] = _worker(tenant_id, dsn, dst_root, "status")
            out["claims"] = _worker(tenant_id, dsn, dst_root, "claims")
            with _store(dsn, TGT_SCOPE), _cwd(dst_root):
                out["verify_code"] = _verify_view()[0]
        with _tenant_store() as (tenant_id, dsn):
            with _store(dsn, TGT_SCOPE):
                _cli("records", "import", str(source["out"]))
            out["unrebased_status"] = _worker(tenant_id, dsn, dst_root, "status")
    return out


def test_tenant_import_exits_zero(tenant):
    # Arrange
    result = tenant["result"]
    # Act
    code = result.exit_code
    # Assert
    assert code == 0, result.output


def test_tenant_import_rebases_paths(tenant):
    # Arrange
    paths = tenant["report"]["paths"]
    # Act
    moved = paths["rewritten"]
    # Assert
    assert moved > 0, paths


def test_tenant_import_finds_no_external_paths(tenant):
    # Arrange
    paths = tenant["report"]["paths"]
    # Act
    external = paths["external"]
    # Assert
    assert external == 0, paths


def test_worker_accepts_rebased_records_inside_its_root(tenant):
    # Arrange
    status = tenant["status"]
    # Act
    refused = isinstance(status, Exception)
    # Assert
    assert refused is False, status


def test_worker_lists_the_imported_claims(tenant, source):
    # Arrange
    expected = sorted(c[0] for c in source["claims"])
    # Act
    actual = sorted(c["claim_id"] for c in tenant["claims"]["claims"])
    # Assert
    assert actual == expected


def test_worker_claims_point_into_the_target_root(tenant):
    # Arrange
    root = str(tenant["dst_root"])
    claims = tenant["claims"]["claims"]
    # Act
    outside = [c["file_path"] for c in claims if not c["file_path"].startswith(root)]
    # Assert
    assert outside == []


def test_clew_verify_at_the_target_root_matches_the_source(tenant, source):
    # Arrange
    expected = source["verify"][0]
    # Act
    actual = tenant["verify_code"]
    # Assert
    assert actual == expected


def test_worker_refuses_unrebased_records(tenant):
    # Arrange
    from scitex_clew._django.services.worker import OutsideProject

    # Act
    status = tenant["unrebased_status"]
    # Assert
    assert isinstance(status, OutsideProject)
