#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clew's stores resolve through `host_store()`, against a real Postgres.

These are the tests that would have caught the migration going wrong. They
assert three things the rest of the suite takes for granted:

1. every one of clew's four stores is Postgres-backed, not file-backed;
2. no clew module can construct a DSN of its own — the switch is
   `SCITEX_STORE_DSN`, read by `host_store()`;
3. the per-test schema really isolates: rows written here are invisible to
   the next test.

There are no mocks. `isolated_store` (tests/conftest.py) puts each test in
its own throwaway schema on the writable cluster.
"""

from __future__ import annotations

import os

from scitex_dev.store import Backend

from scitex_clew._attest._stamp import _stamps_store
from scitex_clew._citation._model import citations_store
from scitex_clew._claim._store import _open_store
from scitex_clew._db import VerificationDB, get_db


class TestEveryStoreIsPostgresBacked:
    """No clew store may be file-backed after the migration."""

    def test_runs_store_backend_is_postgres(self):
        # Arrange
        db = VerificationDB()
        # Act
        backend = db._runs.target.backend
        # Assert
        assert backend is Backend.POSTGRES

    def test_file_hashes_store_backend_is_postgres(self):
        # Arrange
        db = VerificationDB()
        # Act
        backend = db._file_hashes.target.backend
        # Assert
        assert backend is Backend.POSTGRES

    def test_verifications_store_backend_is_postgres(self):
        # Arrange
        db = VerificationDB()
        # Act
        backend = db._verifications.target.backend
        # Assert
        assert backend is Backend.POSTGRES

    def test_session_parents_store_backend_is_postgres(self):
        # Arrange
        db = VerificationDB()
        # Act
        backend = db._session_parents.target.backend
        # Assert
        assert backend is Backend.POSTGRES

    def test_claims_store_backend_is_postgres(self):
        # Arrange
        store = _open_store()
        # Act
        backend = store.target.backend
        # Assert
        assert backend is Backend.POSTGRES
        store.close()

    def test_citations_store_backend_is_postgres(self):
        # Arrange
        store = citations_store()
        # Act
        backend = store.target.backend
        # Assert
        assert backend is Backend.POSTGRES
        store.close()

    def test_stamps_store_backend_is_postgres(self):
        # Arrange
        store = _stamps_store()
        # Act
        backend = store.target.backend
        # Assert
        assert backend is Backend.POSTGRES
        store.close()

    def test_no_store_is_file_backed(self):
        # Arrange
        db = VerificationDB()
        stores = [db._runs, db._file_hashes, db._verifications, db._session_parents]
        # Act
        file_backed = [s.target.name for s in stores if s.target.is_file_backed]
        # Assert
        assert file_backed == []


class TestTheOneSwitch:
    """`SCITEX_STORE_DSN` decides which store answers — nothing else does."""

    def test_runs_store_dsn_is_the_env_var_value(self):
        # Arrange
        expected = os.environ["SCITEX_STORE_DSN"]
        # Act
        dsn = VerificationDB()._runs.target.dsn
        # Assert
        assert dsn == expected

    def test_claims_store_dsn_is_the_env_var_value(self):
        # Arrange
        expected = os.environ["SCITEX_STORE_DSN"]
        # Act
        store = _open_store()
        dsn = store.target.dsn
        store.close()
        # Assert
        assert dsn == expected

    def test_the_four_stores_differ_only_by_name(self):
        # Arrange
        db = VerificationDB()
        # Act
        names = sorted(
            s.target.name
            for s in (db._runs, db._file_hashes, db._verifications, db._session_parents)
        )
        # Assert
        assert names == [
            "file_hashes",
            "runs",
            "session_parents",
            "verification_results",
        ]

    def test_every_store_declares_the_clew_package(self):
        # Arrange
        db = VerificationDB()
        # Act
        pkgs = {s.target.pkg for s in (db._runs, db._file_hashes)}
        # Assert
        assert pkgs == {"scitex_clew"}


class TestRoundTripThroughPostgres:
    """A row written through the public API comes back from the database."""

    def test_added_run_is_readable(self):
        # Arrange
        db = get_db()
        # Act
        db.add_run(session_id="pg_round_trip", script_path="/path/script.py")
        stored = db._runs.get(("pg_round_trip",))
        # Assert
        assert stored is not None

    def test_added_run_keeps_its_script_path(self):
        # Arrange
        db = get_db()
        # Act
        db.add_run(session_id="pg_round_trip_2", script_path="/path/script.py")
        stored = db._runs.get(("pg_round_trip_2",))
        # Assert
        assert stored.values["script_path"] == "/path/script.py"

    def test_stats_reports_the_store_not_a_file_path(self):
        # Arrange
        db = get_db()
        # Act
        result = db.stats()
        # Assert
        assert "db_path" not in result

    def test_stats_store_field_names_postgres(self):
        # Arrange
        db = get_db()
        # Act
        result = db.stats()
        # Assert
        assert result["store"].startswith("postgres:")


class TestPerTestSchemaIsolation:
    """The isolation itself is under test — a leak would make everything lie.

    These two tests write the SAME session_id. If the schema were shared,
    the second would see the first's row and the count would be 2.
    """

    def test_first_writer_sees_exactly_its_own_row(self):
        # Arrange
        db = get_db()
        # Act
        db.add_run(session_id="isolation_probe", script_path="/first.py")
        rows = db._runs.rows()
        # Assert
        assert len(rows) == 1

    def test_second_writer_sees_exactly_its_own_row(self):
        # Arrange
        db = get_db()
        # Act
        db.add_run(session_id="isolation_probe", script_path="/second.py")
        rows = db._runs.rows()
        # Assert
        assert len(rows) == 1

    def test_second_writer_sees_its_own_value_not_the_first(self):
        # Arrange
        db = get_db()
        # Act
        db.add_run(session_id="isolation_probe", script_path="/second.py")
        stored = db._runs.get(("isolation_probe",))
        # Assert
        assert stored.values["script_path"] == "/second.py"


# EOF
