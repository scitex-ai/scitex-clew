"""Project records move between two real stores through a file (no mocks).

Throwaway PostgreSQL schemas stand in for the stores — the source (a
researcher's private store) and targets (a tenant store with a fixed project
scope). Each phase points ``SCITEX_STORE_DSN`` at ONE of them only, so a
target never connects to the source: the JSON file is all that travels. The
managed-store scenario provisions the target with a NOLOGIN owner role and a
DML-only login (``scitex_dev.store.provision_store_acl``) and imports as that
login. The source project (``source`` fixture, conftest) is built once per
module; each scenario runs once; each test asserts one fact.
"""

from __future__ import annotations

import json
import uuid
import warnings
from contextlib import contextmanager

import pytest

from tests.conftest import _connect

from ._records_support import (
    SRC_SCOPE,
    TGT_SCOPE,
    _claim_view,
    _cli,
    _dsn,
    _env,
    _schema,
    _store,
    _verify_view,
)


@contextmanager
def _target(source, scope=TGT_SCOPE):
    with (
        _env(SCITEX_CLEW_AUTO_EXPORT_CLAIMS="0"),
        _schema() as tgt,
        _store(_dsn(tgt), scope),
    ):
        yield str(source["out"])


@pytest.fixture(scope="module")
def round_trip(source):
    """Imported under an explicit --project-scope while another scope is current."""
    with _target(source, scope="unrelated-default") as path:
        result = _cli("records", "import", path, "--project-scope", TGT_SCOPE, "--json")
        with _env(SCITEX_CLEW_PROJECT=TGT_SCOPE):
            verify, claims = _verify_view(), _claim_view()
        with _env(SCITEX_CLEW_PROJECT="unrelated-default"):
            default_claims = _claim_view()
    return {"result": result, "report": json.loads(result.output), "claims": claims,
            "verify": verify, "default_claims": default_claims}  # fmt: skip


@pytest.fixture(scope="module")
def default_scope(source):
    with _target(source) as path:
        report = json.loads(_cli("records", "import", path, "--json").output)
        claims = _claim_view()
    return {"report": report, "claims": claims}


@pytest.fixture(scope="module")
def reimport(source):
    """Import twice, then change a claim on the target and import a third time."""
    import scitex_clew as clew

    with _target(source) as path:
        first = json.loads(_cli("records", "import", path, "--json").output)
        second = json.loads(_cli("records", "import", path, "--json").output)
        recount = json.loads(
            _cli("records", "export", "--out", "-", "--dry-run", "--json").output
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            clew.add_claim("x.tex", "value", 9, "0.99", claim_id="auc")
        third = json.loads(_cli("records", "import", path, "--json").output)
        claims = _claim_view()
    return {"first": first, "second": second, "recount": recount,
            "third": third, "claims": claims}  # fmt: skip


@pytest.fixture(scope="module")
def dry_run(source):
    with _target(source) as path:
        report = json.loads(
            _cli("records", "import", path, "--dry-run", "--json").output
        )
        claims = _claim_view()
    return {"report": report, "claims": claims}


@pytest.fixture
def tampered(source, tmp_path):
    doc = json.loads(source["out"].read_text())
    doc["tables"]["claims"]["rows"][0]["values"]["claim_value"] = "0.99"
    path = tmp_path / "records.json"
    path.write_text(json.dumps(doc))
    with _target(source):
        result = _cli("records", "import", str(path), catch=True)
        claims = _claim_view()
    return {"result": result, "claims": claims}


@pytest.fixture(scope="module")
def conflict(source):
    """A write-once field differs from the target's: the import is refused."""
    from scitex_clew._exchange._records import (
        RecordsImportConflict,
        import_records,
        records_checksum,
    )

    doc = json.loads(json.dumps(source["doc"]))
    with _target(source):
        import_records(doc)
        doc["tables"]["session_parents"]["rows"][0]["values"]["recorded_at"] = "1999"
        doc["tables"]["claims"]["rows"][0]["values"]["claim_value"] = "changed"
        doc["payload_sha256"] = records_checksum(doc)
        try:
            import_records(doc)
            error = None
        except RecordsImportConflict as exc:
            error = exc
        claims = _claim_view()
    return {"error": error, "claims": claims}


@contextmanager
def _managed_schema():
    """A schema under the managed contract: NOLOGIN owner + DML-only login."""
    from scitex_dev.store import StoreTarget
    from scitex_dev.store._provision import DEFAULT_OWNER_ROLE, DEFAULT_WRITER_ROLE

    name = f"clewrec_{uuid.uuid4().hex[:12]}"
    login, password = f"clewrec_login_{uuid.uuid4().hex[:8]}", uuid.uuid4().hex
    created = []
    with _connect() as conn:
        for role in (DEFAULT_OWNER_ROLE, DEFAULT_WRITER_ROLE):
            found = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,))
            if found.fetchone() is None:
                conn.execute(f"CREATE ROLE {role} NOLOGIN")
                created.append(role)
        conn.execute(
            f"CREATE ROLE {login} LOGIN PASSWORD '{password}' IN ROLE {DEFAULT_WRITER_ROLE}"
        )
        conn.execute(f'CREATE SCHEMA "{name}"')
        conn.execute(f'GRANT USAGE, CREATE ON SCHEMA "{name}" TO {DEFAULT_OWNER_ROLE}')
        conn.execute(f'GRANT USAGE ON SCHEMA "{name}" TO {DEFAULT_WRITER_ROLE}')
    try:
        yield (
            name,
            _dsn(name, login, password),
            StoreTarget.postgres(_dsn(name), pkg="scitex_clew"),
            login,
        )
    finally:
        with _connect() as conn:
            conn.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')
            for role in (login, *created):
                conn.execute(f"DROP OWNED BY {role}")
                conn.execute(f"DROP ROLE {role}")


def _owners(admin, schemas):
    from scitex_dev.store import inspect_store_acl

    return {t: o for s in schemas for t, o in inspect_store_acl(admin, s).table_owners}


@pytest.fixture(scope="module")
def managed(source):
    from scitex_dev.store import StoreProvisionError, provision_store_acl

    from scitex_clew._exchange._records import _schemas

    schemas = list(_schemas().values())
    with (
        _env(SCITEX_CLEW_AUTO_EXPORT_CLAIMS="0"),
        _managed_schema() as (name, login_dsn, admin, login),
    ):
        with _store(login_dsn, TGT_SCOPE):
            try:
                _cli("records", "import", str(source["out"]))
                unprovisioned = None
            except StoreProvisionError as exc:
                unprovisioned = exc
        for schema in schemas:
            provision_store_acl(admin, schema)
        before = _owners(admin, schemas)
        with _connect() as conn:
            can_create = conn.execute(
                "SELECT has_schema_privilege(%s, %s, 'CREATE')", (login, name)
            ).fetchone()[0]
        with _store(login_dsn, TGT_SCOPE):
            result = _cli("records", "import", str(source["out"]), "--json")
            verify, claims = _verify_view(), _claim_view()
        after = _owners(admin, schemas)
    return {"unprovisioned": unprovisioned, "before": before, "after": after,
            "can_create": can_create, "result": result, "claims": claims,
            "verify": verify}  # fmt: skip


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
def test_record_tables_are_every_clew_store_schema():
    # Arrange
    from scitex_clew._exchange._records import RECORD_TABLES, _schemas

    # Act
    names = tuple(_schemas())
    # Assert
    assert names == RECORD_TABLES


def test_export_exits_zero(source):
    # Arrange
    result = source["result"]
    # Act
    code = result.exit_code
    # Assert
    assert code == 0, result.output


def test_export_names_its_schema_id(source):
    # Arrange
    doc = source["doc"]
    # Act
    schema = (doc["schema"], doc["schema_version"])
    # Assert
    assert schema == ("scitex-clew.project-records", "1.0.0")


def test_export_records_the_source_scope(source):
    # Arrange
    doc = source["doc"]
    # Act
    src = doc["source"]
    # Assert
    assert src == {"project": SRC_SCOPE}


def test_export_fills_every_table_the_project_wrote(source):
    # Arrange
    counts = source["doc"]["counts"]
    # Act
    filled = {name for name, n in counts.items() if n}
    # Assert
    assert filled == {"runs", "file_hashes", "verification_results",
                      "session_parents", "claims", "citations", "stamps"}  # fmt: skip


def test_export_keeps_the_removed_claim_as_hidden(source):
    # Arrange
    rows = source["doc"]["tables"]["claims"]["rows"]
    # Act
    hidden = [r["values"]["claim_id"] for r in rows if r["hidden"]]
    # Assert
    assert hidden == ["gone"]


def test_export_rows_carry_no_project_field(source):
    # Arrange
    tables = source["doc"]["tables"].values()
    # Act
    leaked = [r for t in tables for r in t["rows"] if "project" in r["values"]]
    # Assert
    assert leaked == []


def test_export_carries_no_dsn(source):
    # Arrange
    text = source["out"].read_text()
    # Act
    leaked = "postgresql://" in text or "search_path" in text
    # Assert
    assert leaked is False


# ---------------------------------------------------------------------------
# round trip into a second store + scope rewrite
# ---------------------------------------------------------------------------
def test_import_exits_zero(round_trip):
    # Arrange
    result = round_trip["result"]
    # Act
    code = result.exit_code
    # Assert
    assert code == 0, result.output


def test_import_reports_the_rewritten_scope(round_trip):
    # Arrange
    report = round_trip["report"]
    # Act
    scopes = (report["source_project"], report["target_project"])
    # Assert
    assert scopes == (SRC_SCOPE, TGT_SCOPE)


def test_claims_on_target_scope_match_the_source(round_trip, source):
    # Arrange
    expected = source["claims"]
    # Act
    actual = round_trip["claims"]
    # Assert
    assert actual == expected


def test_clew_verify_on_target_scope_matches_the_source(round_trip, source):
    # Arrange
    expected = source["verify"]
    # Act
    actual = round_trip["verify"]
    # Assert
    assert actual == expected


def test_import_leaves_the_current_scope_untouched(round_trip):
    # Arrange
    claims = round_trip["default_claims"]
    # Act
    count = len(claims)
    # Assert
    assert count == 0


def test_import_defaults_to_the_current_scope(default_scope):
    # Arrange
    report = default_scope["report"]
    # Act
    target = report["target_project"]
    # Assert
    assert target == TGT_SCOPE


def test_import_into_default_scope_reproduces_claims(default_scope, source):
    # Arrange
    expected = source["claims"]
    # Act
    actual = default_scope["claims"]
    # Assert
    assert actual == expected


# ---------------------------------------------------------------------------
# idempotency
# ---------------------------------------------------------------------------
def test_first_import_creates_every_row(reimport):
    # Arrange
    tables = reimport["first"]["tables"].values()
    # Act
    created = all(t["created"] == t["rows"] for t in tables)
    # Assert
    assert created is True


def test_reimport_leaves_every_row_unchanged(reimport):
    # Arrange
    tables = reimport["second"]["tables"].values()
    # Act
    unchanged = all(t["unchanged"] == t["rows"] for t in tables)
    # Assert
    assert unchanged is True


def test_reimport_adds_no_duplicates(reimport, source):
    # Arrange
    expected = source["doc"]["counts"]
    # Act
    actual = reimport["recount"]["counts"]
    # Assert
    assert actual == expected


def test_changed_record_is_reported_updated(reimport):
    # Arrange
    claims = reimport["third"]["tables"]["claims"]
    # Act
    updated = claims["updated"]
    # Assert
    assert updated == 1


def test_changed_record_is_replaced_by_the_document(reimport, source):
    # Arrange
    expected = source["claims"]
    # Act
    actual = reimport["claims"]
    # Assert
    assert actual == expected


def test_dry_run_reports_what_it_would_create(dry_run):
    # Arrange
    claims = dry_run["report"]["tables"]["claims"]
    # Act
    created = claims["created"]
    # Assert
    assert created == 3


def test_dry_run_writes_nothing(dry_run):
    # Arrange
    claims = dry_run["claims"]
    # Act
    count = len(claims)
    # Assert
    assert count == 0


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------
def test_tampered_document_exits_one(tampered):
    # Arrange
    result = tampered["result"]
    # Act
    code = result.exit_code
    # Assert
    assert code == 1


def test_tampered_document_names_the_checksum(tampered):
    # Arrange
    result = tampered["result"]
    # Act
    output = result.output
    # Assert
    assert "payload_sha256 mismatch" in output


def test_tampered_document_writes_nothing(tampered):
    # Arrange
    claims = tampered["claims"]
    # Act
    count = len(claims)
    # Assert
    assert count == 0


def test_unsupported_schema_version_is_refused(source, tmp_path):
    # Arrange
    from scitex_clew._exchange._records import (
        RecordsDocumentError,
        load_records,
        records_checksum,
    )

    doc = json.loads(source["out"].read_text())
    doc["schema_version"] = "2.0.0"
    doc["payload_sha256"] = records_checksum(doc)
    path = tmp_path / "records.json"
    path.write_text(json.dumps(doc))
    # Act
    refuse = pytest.raises(RecordsDocumentError, match="schema_version")
    # Assert
    with refuse:
        load_records(path)


def test_write_once_conflict_is_refused(conflict):
    # Arrange
    error = conflict["error"]
    # Act
    message = str(error)
    # Assert
    assert "recorded_at" in message


def test_write_once_conflict_writes_nothing_else(conflict, source):
    # Arrange
    expected = source["claims"]
    # Act
    actual = conflict["claims"]
    # Assert
    assert actual == expected


# ---------------------------------------------------------------------------
# managed store: NOLOGIN owner + DML-only login
# ---------------------------------------------------------------------------
def test_unprovisioned_managed_store_refuses_instead_of_ddl(managed):
    # Arrange
    from scitex_dev.store import StoreProvisionError

    # Act
    error = managed["unprovisioned"]
    # Assert
    assert isinstance(error, StoreProvisionError)


def test_managed_login_has_no_create_privilege(managed):
    # Arrange
    can_create = managed["can_create"]
    # Act
    granted = bool(can_create)
    # Assert
    assert granted is False


def test_import_as_dml_only_login_exits_zero(managed):
    # Arrange
    result = managed["result"]
    # Act
    code = result.exit_code
    # Assert
    assert code == 0, result.output


def test_import_as_dml_only_login_reproduces_claims(managed, source):
    # Arrange
    expected = source["claims"]
    # Act
    actual = managed["claims"]
    # Assert
    assert actual == expected


def test_import_as_dml_only_login_reproduces_verify(managed, source):
    # Arrange
    expected = source["verify"]
    # Act
    actual = managed["verify"]
    # Assert
    assert actual == expected


def test_import_as_dml_only_login_changes_no_table_owner(managed):
    # Arrange
    before = managed["before"]
    # Act
    after = managed["after"]
    # Assert
    assert after == before


def test_managed_tables_stay_owned_by_the_nologin_owner(managed):
    # Arrange
    owners = set(managed["after"].values())
    # Act
    expected = {"scitex_store_owner"}
    # Assert
    assert owners == expected
