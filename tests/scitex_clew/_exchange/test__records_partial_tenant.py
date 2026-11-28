"""Import into a tenant provisioned like the Hub's: only the Clew app's 5 stores.

The Hub provisions a tenant with the schemas its Clew worker reads (runs,
file_hashes, verification_results, session_parents, claims). The source
project also holds a citation and a stamp, and no environments rows. Without
a preflight, opening the citations store attempted ``CREATE TABLE`` as the
tenant login and failed mid-import. Real PostgreSQL, no mocks.
"""

from __future__ import annotations

import json

import pytest

from tests.conftest import _connect

from ._records_support import TGT_SCOPE, _claim_view, _cli, _env, _store, _tenant_store

#: The stores the Hub's Clew worker reads (``_django/services/worker.py``).
HUB_STORES = (
    "runs",
    "file_hashes",
    "verification_results",
    "session_parents",
    "claims",
)
SKIPS = ("--skip-table", "citations", "--skip-table", "stamps")


def _table_count(dsn_schema: str) -> int:
    with _connect() as conn:
        found = conn.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = %s", (dsn_schema,)
        ).fetchone()
    return int(found[0])


def _run(source, *flags):
    """Import into a fresh 5-store tenant; return result, claims and table counts."""
    from scitex_dev.store import TenantScope

    with _env(SCITEX_CLEW_AUTO_EXPORT_CLAIMS="0"):
        with _tenant_store(HUB_STORES) as (tenant_id, dsn):
            namespace = TenantScope(tenant_id).namespace
            before = _table_count(namespace)
            with _store(dsn, TGT_SCOPE):
                result = _cli(
                    "records", "import", str(source["out"]), *flags, catch=True
                )
                claims = _claim_view()
            after = _table_count(namespace)
    return {"result": result, "claims": claims, "before": before, "after": after}


@pytest.fixture(scope="module")
def refused(source):
    return _run(source)


@pytest.fixture(scope="module")
def refused_dry(source):
    return _run(source, "--dry-run")


@pytest.fixture(scope="module")
def skipped(source):
    return _run(source, "--json", *SKIPS)


@pytest.fixture(scope="module")
def skipped_dry(source):
    return _run(source, "--json", "--dry-run", *SKIPS)


def test_source_has_rows_for_unprovisioned_tables(source):
    # Arrange
    counts = source["doc"]["counts"]
    # Act
    rows = (counts["citations"], counts["stamps"], counts["environments"])
    # Assert
    assert rows == (1, 1, 0)


def test_unprovisioned_tables_refuse_the_import(refused):
    # Arrange
    result = refused["result"]
    # Act
    code = result.exit_code
    # Assert
    assert code == 1, result.output


def test_refusal_names_every_unprovisioned_table_with_rows(refused):
    # Arrange
    output = refused["result"].output
    # Act
    named = ("'citations'" in output, "'stamps'" in output, "environments" in output)
    # Assert
    assert named == (True, True, False), output


def test_refusal_suggests_skip_table(refused):
    # Arrange
    output = refused["result"].output
    # Act
    hint = "--skip-table citations --skip-table stamps" in output
    # Assert
    assert hint is True, output


def test_refusal_writes_nothing(refused):
    # Arrange
    claims = refused["claims"]
    # Act
    count = len(claims)
    # Assert
    assert count == 0


def test_refusal_attempts_no_ddl(refused):
    # Arrange
    before, after = refused["before"], refused["after"]
    # Act
    created = after - before
    # Assert
    assert created == 0


def test_dry_run_refuses_the_same_way(refused_dry):
    # Arrange
    result = refused_dry["result"]
    # Act
    code = result.exit_code
    # Assert
    assert code == 1, result.output


def test_dry_run_attempts_no_ddl(refused_dry):
    # Arrange
    before, after = refused_dry["before"], refused_dry["after"]
    # Act
    created = after - before
    # Assert
    assert created == 0


def test_skipping_the_unprovisioned_tables_imports_the_rest(skipped):
    # Arrange
    result = skipped["result"]
    # Act
    code = result.exit_code
    # Assert
    assert code == 0, result.output


def test_skipped_import_reproduces_the_claims(skipped, source):
    # Arrange
    expected = source["claims"]
    # Act
    actual = skipped["claims"]
    # Assert
    assert actual == expected


def test_report_lists_skipped_tables_with_their_rows(skipped):
    # Arrange
    report = json.loads(skipped["result"].output)
    # Act
    skips = report["skipped"]
    # Assert
    assert skips == {
        "environments": {"rows": 0, "reason": "empty"},
        "citations": {"rows": 1, "reason": "--skip-table"},
        "stamps": {"rows": 1, "reason": "--skip-table"},
    }


def test_skipped_import_creates_no_table(skipped):
    # Arrange
    before, after = skipped["before"], skipped["after"]
    # Act
    created = after - before
    # Assert
    assert created == 0


def test_skipped_dry_run_writes_nothing(skipped_dry):
    # Arrange
    claims = skipped_dry["claims"]
    # Act
    count = len(claims)
    # Assert
    assert count == 0


def test_skipped_dry_run_reports_what_it_would_create(skipped_dry):
    # Arrange
    report = json.loads(skipped_dry["result"].output)
    # Act
    created = report["tables"]["claims"]["created"]
    # Assert
    assert created == 3


def test_unknown_skip_table_is_a_usage_error(source):
    # Arrange
    args = ("records", "import", str(source["out"]), "--skip-table", "nope")
    # Act
    result = _cli(*args, catch=True)
    # Assert
    assert result.exit_code == 2, result.output
