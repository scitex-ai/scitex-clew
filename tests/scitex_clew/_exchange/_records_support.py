"""Shared helpers for the project-records tests (real stores, no mocks)."""

from __future__ import annotations

import json
import os
import uuid
import warnings
from contextlib import contextmanager
from urllib.parse import quote

from click.testing import CliRunner

from tests.conftest import WRITABLE_DSN, _connect

SRC_SCOPE = "researcher-private"
TGT_SCOPE = "tenant-fixed-scope"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _dsn(schema: str, user: str | None = None, password: str | None = None) -> str:
    """WRITABLE_DSN pointed at ``schema`` (optionally as another login)."""
    import psycopg

    params = psycopg.conninfo.conninfo_to_dict(WRITABLE_DSN)
    if user is not None:
        params["user"], params["password"] = user, password
    params["options"] = f"-csearch_path={schema}"
    netloc = quote(params.pop("user"), safe="")
    password = params.pop("password", None)
    if password:
        netloc += f":{quote(password, safe='')}"
    netloc += f"@{params.pop('host')}:{params.pop('port')}"
    query = "&".join(
        f"{k}={quote(str(v), safe='')}" for k, v in params.items() if k != "dbname"
    )
    return f"postgresql://{netloc}/{params['dbname']}?{query}"


@contextmanager
def _env(**values):
    saved = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _store(dsn: str, scope: str):
    """Point clew at exactly one store and one scope for the block."""
    from scitex_clew._db import reset_db

    with _env(SCITEX_STORE_DSN=dsn, SCITEX_CLEW_PROJECT=scope):
        reset_db()
        try:
            yield
        finally:
            reset_db()


@contextmanager
def _schema():
    name = f"clewrec_{uuid.uuid4().hex[:12]}"
    with _connect() as conn:
        conn.execute(f'CREATE SCHEMA "{name}"')
    try:
        yield name
    finally:
        with _connect() as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')


def _cli(*args, catch: bool = False):
    from scitex_clew._cli._main import main

    return CliRunner().invoke(main, list(args), catch_exceptions=catch)


def _claim_view():
    import scitex_clew as clew

    return sorted(
        (c.claim_id, c.claim_value, c.status, c.source_file, c.source_hash)
        for c in clew.list_claims(limit=10_000)
    )


def _verify_view():
    result = _cli("--json", "verify")
    payload = json.loads(result.output)
    payload.pop("elapsed_s", None)
    return result.exit_code, json.dumps(payload, sort_keys=True, default=str)


def _record_project(root):
    """Two chained runs, a verification, claims (one removed), a citation, a stamp."""
    import scitex_clew as clew
    from scitex_clew._chain import verify_run
    from scitex_clew._db import get_db
    from scitex_clew._tracker import SessionTracker

    script = root / "make.py"
    script.write_text("# make\n")
    raw = root / "raw.csv"
    raw.write_text("x\n1\n2\n")
    results = root / "results.json"
    results.write_text(json.dumps({"auc": 0.8123, "n": 120}))
    first = SessionTracker("S-first", script_path=str(script))
    first.record_input(raw)
    first.record_output(results)
    first.finalize()
    summary = root / "summary.json"
    summary.write_text(json.dumps({"double": 1.6246}))
    second = SessionTracker(
        "S-second", script_path=str(script), parent_session="S-first"
    )
    second.record_input(results)
    second.record_output(summary)
    second.finalize()
    verify_run("S-first")
    db = get_db()
    db.add_parent("S-second", "S-first")
    db.record_verification("S-first", "cache", "verified")
    paper = str(root / "paper.tex")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        clew.add_claim(paper, "value", 1, "0.81", source_file=str(results),
                       claim_id="auc", source_keys={".": "/auc"})  # fmt: skip
        clew.add_claim(paper, "value", 2, "120", source_file=str(results),
                       claim_id="n_subjects", source_keys={".": "/n"})  # fmt: skip
        clew.add_claim(
            paper, "value", 3, "9", source_file=str(results), claim_id="gone"
        )
    clew.remove_claim("gone")
    clew.add_citation("smith2020", manuscript_file=paper, doi="10.1000/x")
    clew.stamp(backend="file", output_dir=str(root / "stamps"))


def build_source(root):
    """Record the project in its own store and export it via the CLI."""
    out = root / "records.json"
    with (
        _env(
            SCITEX_CLEW_AUTO_EXPORT_CLAIMS="0",
            SCITEX_CLEW_JOURNAL_DIR=str(root / "journal"),
        ),
        _schema() as src,
        _store(_dsn(src), SRC_SCOPE),
    ):
        _record_project(root)
        verify, claims = _verify_view(), _claim_view()
        result = _cli("records", "export", "--out", str(out), "--json")
    return {"out": out, "claims": claims, "verify": verify,
            "result": result, "doc": json.loads(out.read_text())}  # fmt: skip


TENANT_OWNER = "scitex_cloud_owner"


@contextmanager
def _tenant_store(names=None):
    """A tenant namespace provisioned by the operator API; yields its login DSN.

    ``names`` limits provisioning to those clew stores (default: all eight),
    as the Hub provisions only the schemas its Clew app reads.
    """
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
        for name, schema in _schemas().items():
            if names is not None and name not in names:
                continue
            provision_tenant_store(admin, schema, scope, owner_role=TENANT_OWNER)
        yield tenant, _dsn(scope.namespace, scope.principal, password)
    finally:
        with _connect() as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{scope.namespace}" CASCADE')
            roles = [scope.principal] + ([TENANT_OWNER] if created_owner else [])
            for role in roles:
                conn.execute(f"DROP OWNED BY {role}")
                conn.execute(f"DROP ROLE {role}")
