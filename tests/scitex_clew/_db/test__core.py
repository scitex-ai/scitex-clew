#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/tests/scitex/verify/test__db.py

"""Tests for scitex.clew._db module.

Every test runs against its OWN throwaway PostgreSQL schema, handed to
clew by the autouse `isolated_store` fixture in tests/conftest.py.
`VerificationDB()` takes no argument — there is no database file.
"""

import os

import pytest
from scitex_dev.store import Backend

from scitex_clew import VerificationDB
from scitex_clew._attest._stamp import _stamps_store
from scitex_clew._citation._model import citations_store
from scitex_clew._claim._store import _open_store
from scitex_clew._db import get_db


class TestVerificationDB:
    """Tests for VerificationDB class."""

    @pytest.fixture
    def db(self):
        """Real database for testing (own PostgreSQL schema per test)."""
        return VerificationDB()

    def test_init_creates_database_db_is_not_none(self):
        # Arrange
        # Arrange
        # Arrange
        # Act
        # Act
        db = VerificationDB()
        # Act
        # Assert
        # Assert
        # Assert
        assert db is not None


    def test_init_creates_runs_table(self, db):
        """Initialization must create a Store-backed `runs` table.

        RETARGETED (the 2026-08-28 store migration, final cleanup):
        this used to open the legacy raw-file mirror via `db._connect()`
        and check the table catalogue for a `runs` table. That mirror is gone;
        the equivalent Store-side fact is that a row written through the
        public API round-trips through `self._runs` (the Store instance).
        """
        # Arrange
        # Act
        db.add_run(session_id="init_check_run", script_path="/path/script.py")
        stored = db._runs.get(("init_check_run",))
        # Assert
        assert stored is not None

    def test_init_creates_file_hashes_table(self, db):
        """Initialization must create a Store-backed `file_hashes` table.

        RETARGETED (the 2026-08-28 store migration, final cleanup):
        see `test_init_creates_runs_table` above — same rationale, applied
        to `self._file_hashes`.
        """
        # Arrange
        db.add_run(session_id="init_check_run", script_path="/path/script.py")
        # Act
        db.add_file_hash(
            session_id="init_check_run",
            file_path="/path/to/data.csv",
            hash_value="hash123",
            role="input",
        )
        stored = db._file_hashes.rows()
        # Assert
        assert any(r.values.get("session_id") == "init_check_run" for r in stored)


class TestRunOperations:
    """Tests for run-related database operations."""

    @pytest.fixture
    def db(self):
        """Real database for testing (own PostgreSQL schema per test)."""
        return VerificationDB()

    def test_add_run_run_is_not_none(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(
            session_id="test_session_001",
            script_path="/path/to/script.py",
            script_hash="abc123def456",
        )
        # Act
        # Act
        run = db.get_run("test_session_001")
        # Act
        # Assert
        # Assert
        # Assert
        assert run is not None

    def test_add_run_run_session_id_test_session_001(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(
            session_id="test_session_001",
            script_path="/path/to/script.py",
            script_hash="abc123def456",
        )
        # Act
        # Act
        run = db.get_run("test_session_001")
        # Act
        # Assert
        # Assert
        # Assert
        assert run["session_id"] == "test_session_001"

    def test_add_run_run_script_path_path_to_script_py(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(
            session_id="test_session_001",
            script_path="/path/to/script.py",
            script_hash="abc123def456",
        )
        # Act
        # Act
        run = db.get_run("test_session_001")
        # Act
        # Assert
        # Assert
        # Assert
        assert run["script_path"] == "/path/to/script.py"

    def test_add_run_run_script_hash_abc123def456(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(
            session_id="test_session_001",
            script_path="/path/to/script.py",
            script_hash="abc123def456",
        )
        # Act
        # Act
        run = db.get_run("test_session_001")
        # Act
        # Assert
        # Assert
        # Assert
        assert run["script_hash"] == "abc123def456"


    def test_add_run_with_metadata(self, db):
        """Test adding a run with metadata."""
        # Arrange
        metadata = {"key": "value", "number": 42}
        db.add_run(
            session_id="test_session_002",
            script_path="/path/to/script.py",
            metadata=metadata,
        )

        # Act
        run = db.get_run("test_session_002")
        # Assert
        assert run is not None

    def test_add_run_with_parent(self, db):
        """Test adding a run with parent session."""
        # Arrange
        db.add_run(session_id="parent_001", script_path="/path/parent.py")
        db.add_run(
            session_id="child_001",
            script_path="/path/child.py",
            parent_session="parent_001",
        )

        # Act
        run = db.get_run("child_001")
        # Assert
        assert run["parent_session"] == "parent_001"

    def test_get_run_not_found(self, db):
        """Test getting a non-existent run."""
        # Arrange
        # Act
        result = db.get_run("nonexistent")
        # Assert
        assert result is None

    def test_finish_run_status_run_status_success(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.finish_run("test_session", status="success", exit_code=0)
        # Act
        # Act
        run = db.get_run("test_session")
        # Act
        # Assert
        # Assert
        # Assert
        assert run["status"] == "success"

    def test_finish_run_status_run_exit_code_0(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.finish_run("test_session", status="success", exit_code=0)
        # Act
        # Act
        run = db.get_run("test_session")
        # Act
        # Assert
        # Assert
        # Assert
        assert run["exit_code"] == 0


    def test_list_runs_len_runs_is_3(self, db):
        """Test listing runs."""
        # Arrange
        db.add_run(session_id="session_a", script_path="/path/a.py")
        db.add_run(session_id="session_b", script_path="/path/b.py")
        db.add_run(session_id="session_c", script_path="/path/c.py")

        # Act
        runs = db.list_runs(limit=10)
        # Assert
        assert len(runs) == 3

    def test_list_runs_with_limit(self, db):
        """Test listing runs with limit."""
        # Arrange
        for i in range(5):
            db.add_run(session_id=f"session_{i}", script_path=f"/path/{i}.py")

        # Act
        runs = db.list_runs(limit=3)
        # Assert
        assert len(runs) == 3

    def test_list_runs_with_status_filter(self, db):
        """Test listing runs filtered by status."""
        # Arrange
        db.add_run(session_id="success_1", script_path="/path/a.py")
        db.finish_run("success_1", status="success")
        db.add_run(session_id="failed_1", script_path="/path/b.py")
        db.finish_run("failed_1", status="failed")

        # Act
        success_runs = db.list_runs(status="success")
        # Assert
        assert all(r["status"] == "success" for r in success_runs)


class TestFileHashOperations:
    """Tests for file hash-related database operations."""

    @pytest.fixture
    def db(self):
        """Real database for testing (own PostgreSQL schema per test)."""
        return VerificationDB()

    def test_add_file_hash_path_to_data_csv_in_hashes(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash(
            session_id="test_session",
            file_path="/path/to/data.csv",
            hash_value="hash123",
            role="input",
        )
        # Act
        # Act
        hashes = db.get_file_hashes("test_session")
        # Act
        # Assert
        # Assert
        # Assert
        assert "/path/to/data.csv" in hashes

    def test_add_file_hash_hashes_path_to_data_csv_hash123(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash(
            session_id="test_session",
            file_path="/path/to/data.csv",
            hash_value="hash123",
            role="input",
        )
        # Act
        # Act
        hashes = db.get_file_hashes("test_session")
        # Act
        # Assert
        # Assert
        # Assert
        assert hashes["/path/to/data.csv"] == "hash123"


    def test_add_file_hash_multiple(self, db):
        """Test adding multiple file hashes."""
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash("test_session", "/path/input.csv", "hash1", "input")
        db.add_file_hash("test_session", "/path/output.csv", "hash2", "output")

        # Act
        all_hashes = db.get_file_hashes("test_session")
        # Assert
        assert len(all_hashes) == 2

    def test_get_file_hashes_by_role_len_inputs_is_1(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash("test_session", "/path/input.csv", "hash1", "input")
        db.add_file_hash("test_session", "/path/output.csv", "hash2", "output")
        # Act
        # Act
        inputs = db.get_file_hashes("test_session", role="input")
        # Act
        # Assert
        # Assert
        # Assert
        assert len(inputs) == 1

    def test_get_file_hashes_by_role_path_input_csv_in_inputs(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash("test_session", "/path/input.csv", "hash1", "input")
        db.add_file_hash("test_session", "/path/output.csv", "hash2", "output")
        # Act
        # Act
        inputs = db.get_file_hashes("test_session", role="input")
        # Act
        # Assert
        # Assert
        # Assert
        assert "/path/input.csv" in inputs

    def test_get_file_hashes_by_role_len_outputs_is_1_len_inputs_is_1(self, db):
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash("test_session", "/path/input.csv", "hash1", "input")
        db.add_file_hash("test_session", "/path/output.csv", "hash2", "output")
        # Act
        inputs = db.get_file_hashes("test_session", role="input")
        # Act
        # Assert
        # Assert
        assert len(inputs) == 1

    def test_get_file_hashes_by_role_len_outputs_is_1_path_input_csv_in_inputs(self, db):
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash("test_session", "/path/input.csv", "hash1", "input")
        db.add_file_hash("test_session", "/path/output.csv", "hash2", "output")
        # Act
        inputs = db.get_file_hashes("test_session", role="input")
        # Act
        # Assert
        # Assert
        assert "/path/input.csv" in inputs

    def test_get_file_hashes_by_role_len_outputs_is_1_len_outputs_is_1(self, db):
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash("test_session", "/path/input.csv", "hash1", "input")
        db.add_file_hash("test_session", "/path/output.csv", "hash2", "output")
        # Act
        outputs = db.get_file_hashes("test_session", role="output")
        # Assert
        assert len(outputs) == 1


    def test_get_file_hashes_by_role_path_output_csv_in_outputs_len_inputs_is_1(self, db):
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash("test_session", "/path/input.csv", "hash1", "input")
        db.add_file_hash("test_session", "/path/output.csv", "hash2", "output")
        # Act
        inputs = db.get_file_hashes("test_session", role="input")
        # Act
        # Assert
        # Assert
        assert len(inputs) == 1

    def test_get_file_hashes_by_role_path_output_csv_in_outputs_path_input_csv_in_inputs(self, db):
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash("test_session", "/path/input.csv", "hash1", "input")
        db.add_file_hash("test_session", "/path/output.csv", "hash2", "output")
        # Act
        inputs = db.get_file_hashes("test_session", role="input")
        # Act
        # Assert
        # Assert
        assert "/path/input.csv" in inputs

    def test_get_file_hashes_by_role_path_output_csv_in_outputs_path_output_csv_in_outputs(self, db):
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.add_file_hash("test_session", "/path/input.csv", "hash1", "input")
        db.add_file_hash("test_session", "/path/output.csv", "hash2", "output")
        # Act
        outputs = db.get_file_hashes("test_session", role="output")
        # Assert
        assert "/path/output.csv" in outputs



    def test_find_session_by_file(self, db):
        """Test finding sessions by file path."""
        # Arrange
        db.add_run(session_id="session_1", script_path="/path/script.py")
        db.add_file_hash("session_1", "/shared/data.csv", "hash1", "output")

        db.add_run(session_id="session_2", script_path="/path/script.py")
        db.add_file_hash("session_2", "/shared/data.csv", "hash2", "input")

        # Act
        sessions = db.find_session_by_file("/shared/data.csv", role="output")
        # Assert
        assert "session_1" in sessions


class TestChainOperations:
    """Tests for chain-related database operations."""

    @pytest.fixture
    def db(self):
        """Real database for testing (own PostgreSQL schema per test)."""
        return VerificationDB()

    def test_get_chain_single(self, db):
        """Test getting chain for a single run."""
        # Arrange
        db.add_run(session_id="single", script_path="/path/script.py")

        # Act
        chain = db.get_chain("single")
        # Assert
        assert chain == ["single"]

    def test_get_chain_with_parent_child_in_chain(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="parent", script_path="/path/parent.py")
        db.add_run(
            session_id="child",
            script_path="/path/child.py",
            parent_session="parent",
        )
        # Act
        # Act
        chain = db.get_chain("child")
        # Act
        # Assert
        # Assert
        # Assert
        assert "child" in chain

    def test_get_chain_with_parent_parent_in_chain(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="parent", script_path="/path/parent.py")
        db.add_run(
            session_id="child",
            script_path="/path/child.py",
            parent_session="parent",
        )
        # Act
        # Act
        chain = db.get_chain("child")
        # Act
        # Assert
        # Assert
        # Assert
        assert "parent" in chain


    def test_get_chain_multi_level(self, db):
        """Test getting chain with multiple levels."""
        # Arrange
        db.add_run(session_id="grandparent", script_path="/path/gp.py")
        db.add_run(
            session_id="parent",
            script_path="/path/p.py",
            parent_session="grandparent",
        )
        db.add_run(
            session_id="child",
            script_path="/path/c.py",
            parent_session="parent",
        )

        # Act
        chain = db.get_chain("child")
        # Assert
        assert len(chain) >= 3


class TestVerificationRecords:
    """Tests for verification record operations."""

    @pytest.fixture
    def db(self):
        """Real database for testing (own PostgreSQL schema per test)."""
        return VerificationDB()

    def test_record_verification_verification_is_not_none(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.record_verification(
            session_id="test_session",
            level="cache",
            status="verified",
        )
        # Should not raise
        # Act
        # Act
        verification = db.get_latest_verification("test_session")
        # Act
        # Assert
        # Assert
        # Assert
        assert verification is not None

    def test_record_verification_verification_level_cache(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.record_verification(
            session_id="test_session",
            level="cache",
            status="verified",
        )
        # Should not raise
        # Act
        # Act
        verification = db.get_latest_verification("test_session")
        # Act
        # Assert
        # Assert
        # Assert
        assert verification["level"] == "cache"

    def test_record_verification_verification_status_verified(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.record_verification(
            session_id="test_session",
            level="cache",
            status="verified",
        )
        # Should not raise
        # Act
        # Act
        verification = db.get_latest_verification("test_session")
        # Act
        # Assert
        # Assert
        # Assert
        assert verification["status"] == "verified"


    def test_record_verification_multiple(self, db):
        """Test recording multiple verification results."""
        # Arrange
        import time

        db.add_run(session_id="test_session", script_path="/path/script.py")
        db.record_verification("test_session", "cache", "verified")
        time.sleep(0.01)  # Ensure different timestamp
        db.record_verification("test_session", "rerun", "verified")

        # Act
        verification = db.get_latest_verification("test_session")
        # Latest verification should exist
        # Assert
        assert verification is not None


class TestDatabaseStats:
    """Tests for database statistics."""

    @pytest.fixture
    def db(self):
        """Real database for testing (own PostgreSQL schema per test)."""
        return VerificationDB()

    def test_stats_total_runs_in_stats(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="s1", script_path="/p1.py")
        db.finish_run("s1", status="success")
        db.add_run(session_id="s2", script_path="/p2.py")
        db.finish_run("s2", status="failed")
        # Act
        # Act
        stats = db.stats()
        # Act
        # Assert
        # Assert
        # Assert
        assert "total_runs" in stats

    def test_stats_stats_total_runs_2(self, db):
        # Arrange
        # Arrange
        # Arrange
        db.add_run(session_id="s1", script_path="/p1.py")
        db.finish_run("s1", status="success")
        db.add_run(session_id="s2", script_path="/p2.py")
        db.finish_run("s2", status="failed")
        # Act
        # Act
        stats = db.stats()
        # Act
        # Assert
        # Assert
        # Assert
        assert stats["total_runs"] == 2


    def test_stats_empty_db(self, db):
        """Test stats on empty database."""
        # Arrange
        # Act
        stats = db.stats()
        # Assert
        assert stats["total_runs"] == 0


class TestProvenanceMigration:
    """Tests for `provenance`/`exception_reason` persistence (Store-backed).

    RETARGETED (the 2026-08-28 store migration, final cleanup): this
    class originally exercised the legacy raw-file mirror's idempotent
    `ALTER TABLE runs ADD COLUMN provenance/exception_reason` migration —
    including a scenario that seeded a hand-rolled pre-migration-shaped store
    file directly with raw SQL, then read the migrated mirror table
    back via `db._connect()`. That legacy mirror (and its
    `_migrate_runs_provenance` helper) is deleted — Store schemas carry
    `provenance`/`exception_reason` as first-class fields from creation,
    so there is no additive-ALTER-TABLE step left to test. These tests now
    assert the equivalent real behavior: `provenance`/`exception_reason`
    round-trip through the Store, including across a SECOND
    `VerificationDB()` instance reading the same store (the Store-backed
    replacement for "migration preserves existing rows / is idempotent").
    """

    @pytest.fixture
    def db(self):
        """Real database for testing (own PostgreSQL schema per test)."""
        return VerificationDB()

    def test_provenance_present_on_added_run(self, db):
        # Arrange
        db.add_run("s1", "/path/script.py")
        # Act
        run = db.get_run("s1")
        # Assert
        assert run["provenance"] == "tracked"

    def test_exception_reason_present_on_added_run(self, db):
        # Arrange
        db.add_run(
            "s1", "/path/script.py", provenance="exception", exception_reason="reason"
        )
        # Act
        run = db.get_run("s1")
        # Assert
        assert run["exception_reason"] == "reason"

    def test_reopening_db_is_idempotent_for_provenance(self):
        # Arrange
        db = VerificationDB()
        db.add_run("s1", "/path/script.py")
        # Act — construct a SECOND VerificationDB against the same store;
        # must not raise and must still expose provenance on a fresh add_run.
        db2 = VerificationDB()
        db2.add_run("s2", "/path/script.py")
        run = db2.get_run("s2")
        # Assert
        assert run["provenance"] == "tracked"

    def test_provenance_visible_across_reopened_db_instances(self):
        # Arrange — Store-backed replacement for the old
        # "migration preserves existing rows" premise: confirm a row
        # written by one VerificationDB instance is visible, with its
        # provenance intact, from a SECOND instance reading the same
        # store.
        db1 = VerificationDB()
        db1.add_run("legacy_001", "/old/script.py")
        db1.finish_run("legacy_001", status="success")

        # Act
        db2 = VerificationDB()
        run = db2.get_run("legacy_001")

        # Assert
        assert run["provenance"] == "tracked"

    def test_run_data_preserved_across_reopened_db_instances(self):
        # Arrange — Store-backed replacement for
        # "migration preserves legacy mirror row data": confirm the full
        # row round-trips across a fresh VerificationDB instance reading
        # the same store.
        db1 = VerificationDB()
        db1.add_run("legacy_002", "/old/script.py")

        # Act
        db2 = VerificationDB()
        run = db2.get_run("legacy_002")

        # Assert
        assert run["session_id"] == "legacy_002"


class TestAddRunProvenance:
    """Tests for provenance + exception_reason in add_run."""

    @pytest.fixture
    def db(self):
        """Real database for testing (own PostgreSQL schema per test)."""
        return VerificationDB()

    def test_add_run_defaults_provenance_to_tracked(self, db):
        # Arrange
        db.add_run("default_session", "/path/script.py")
        # Act
        run = db.get_run("default_session")
        # Assert
        assert run["provenance"] == "tracked"

    def test_add_run_defaults_exception_reason_to_null(self, db):
        # Arrange
        db.add_run("default_session", "/path/script.py")
        # Act
        run = db.get_run("default_session")
        # Assert
        assert run["exception_reason"] is None

    def test_add_run_stores_exception_provenance(self, db):
        # Arrange
        db.add_run(
            "exception_session",
            "/path/gpac.py",
            provenance="exception",
            exception_reason="4.1TB gPAC, recipe-known, never re-run",
        )
        # Act
        run = db.get_run("exception_session")
        # Assert
        assert run["provenance"] == "exception"

    def test_add_run_stores_exception_reason(self, db):
        # Arrange
        db.add_run(
            "exception_session",
            "/path/gpac.py",
            provenance="exception",
            exception_reason="4.1TB gPAC, recipe-known, never re-run",
        )
        # Act
        run = db.get_run("exception_session")
        # Assert
        assert run["exception_reason"] == "4.1TB gPAC, recipe-known, never re-run"

    def test_add_run_exception_is_distinct_from_tracked(self, db):
        # Arrange
        db.add_run("tracked_s", "/script.py")
        db.add_run(
            "exception_s",
            "/script.py",
            provenance="exception",
            exception_reason="reason",
        )
        # Act
        tracked = db.get_run("tracked_s")
        exception = db.get_run("exception_s")
        # Assert
        assert tracked["provenance"] != exception["provenance"]


class TestFrozenMigration:
    """Tests for the `frozen` field on file_hashes rows (Store-backed).

    RETARGETED (the 2026-08-28 store migration, final cleanup): this
    class originally exercised the legacy raw-file mirror's idempotent
    `ALTER TABLE file_hashes ADD COLUMN frozen` migration, including a
    hand-rolled pre-migration-shaped store file. That legacy mirror (and
    `_migrate_file_hashes_frozen`) is deleted — Store schemas carry
    `frozen` as a first-class field from creation, so there is no
    additive-ALTER-TABLE step left to test. These tests now assert the
    equivalent real Store-backed behavior instead.
    """

    def test_frozen_defaults_to_false_on_fresh_db(self):
        # Arrange
        db = VerificationDB()
        db.add_run(session_id="s1", script_path="/path/script.py")
        db.add_file_hash("s1", "/data/file.csv", "abc123", "input")
        # Act
        frozen = db.get_frozen_files("s1")
        # Assert
        assert "/data/file.csv" not in frozen

    def test_frozen_true_round_trips(self):
        # Arrange
        db = VerificationDB()
        db.add_run(session_id="s1", script_path="/path/script.py")
        db.add_file_hash("s1", "/data/file.csv", "abc123", "input", frozen=True)
        # Act
        frozen = db.get_frozen_files("s1")
        # Assert
        assert "/data/file.csv" in frozen

    def test_frozen_state_visible_across_reopened_db_instances(self):
        # Arrange — Store-backed replacement for the old
        # "frozen column added to pre-existing DB" premise: confirm a
        # frozen row written by one VerificationDB instance is visible,
        # with `frozen` intact, from a SECOND instance reading the same
        # store.
        db1 = VerificationDB()
        db1.add_run(session_id="s1", script_path="/path/script.py")
        db1.add_file_hash("s1", "/data/file.csv", "abc123", "input", frozen=True)

        # Act
        db2 = VerificationDB()
        frozen = db2.get_frozen_files("s1")

        # Assert
        assert "/data/file.csv" in frozen

    def test_non_frozen_rows_default_zero_across_reopened_db_instances(self):
        # Arrange — Store-backed replacement for
        # "existing rows default frozen zero": confirm a non-frozen row
        # stays non-frozen across a fresh VerificationDB instance.
        db1 = VerificationDB()
        db1.add_run(session_id="s1", script_path="/path/script.py")
        db1.add_file_hash("s1", "/data/file.csv", "abc123", "input")

        # Act
        db2 = VerificationDB()
        frozen = db2.get_frozen_files("s1")

        # Assert
        assert "/data/file.csv" not in frozen



# ---------------------------------------------------------------------------
# Store resolution — the tests that would have caught the Postgres migration
# going wrong. They live here rather than in their own module because the
# store construction they exercise is `_core.VerificationDB.__init__`; the
# claims/citations/stamps openers are pulled in so the assertion covers
# EVERY store clew opens, not just the four this module builds.
# ---------------------------------------------------------------------------
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
        """Every store is on PostgreSQL, so none of them is a file.

        This used to read ``target.is_file_backed``. scitex-dev removed
        that attribute along with the SQLite backend, and a test that
        raises AttributeError is a broken test, not a kept promise.

        Asking about ``backend`` instead states the same guarantee
        against an attribute both the old and new primitive expose, so
        this fails for the right reason — a store on some other engine —
        under either version, rather than passing because the thing it
        asked about stopped existing.
        """
        # Arrange
        db = VerificationDB()
        stores = [db._runs, db._file_hashes, db._verifications, db._session_parents]
        # Act
        off_postgres = [
            s.target.name for s in stores if s.target.backend is not Backend.POSTGRES
        ]
        # Assert
        assert off_postgres == []


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
