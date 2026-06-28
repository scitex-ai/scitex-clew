#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/tests/scitex/verify/test__db.py

"""Tests for scitex.clew._db module."""

import pytest

from scitex_clew import VerificationDB


class TestVerificationDB:
    """Tests for VerificationDB class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_verification.db"
        return VerificationDB(db_path)

    def test_init_creates_database_db_path_exists(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        # Act
        # Act
        db = VerificationDB(db_path)
        # Act
        # Assert
        # Assert
        # Assert
        assert db_path.exists()

    def test_init_creates_database_db_is_not_none(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        # Act
        # Act
        db = VerificationDB(db_path)
        # Act
        # Assert
        # Assert
        # Assert
        assert db is not None


    def test_init_creates_runs_table(self, db):
        """Initialization must create the `runs` table."""
        # Arrange
        # Act
        with db._connect() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
            ).fetchone()
        # Assert
        assert result is not None

    def test_init_creates_file_hashes_table(self, db):
        """Initialization must create the `file_hashes` table."""
        # Arrange
        # Act
        with db._connect() as conn:
            result = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='file_hashes'"
            ).fetchone()
        # Assert
        assert result is not None


class TestRunOperations:
    """Tests for run-related database operations."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_verification.db"
        return VerificationDB(db_path)

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
    def db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_verification.db"
        return VerificationDB(db_path)

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
    def db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_verification.db"
        return VerificationDB(db_path)

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
    def db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_verification.db"
        return VerificationDB(db_path)

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
    def db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_verification.db"
        return VerificationDB(db_path)

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
    """Tests for the Phase-3 provenance migration (idempotent ALTER TABLE)."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_provenance.db"
        return VerificationDB(db_path)

    def test_migration_adds_provenance_column_to_fresh_db(self, db):
        # Arrange
        # Act
        with db._connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        # Assert
        assert "provenance" in cols

    def test_migration_adds_exception_reason_column_to_fresh_db(self, db):
        # Arrange
        # Act
        with db._connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        # Assert
        assert "exception_reason" in cols

    def test_migration_is_idempotent_for_provenance(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test_idem.db"
        db = VerificationDB(db_path)
        # Act — call migration a second time directly; must not raise
        db._migrate_runs_provenance()
        with db._connect() as conn:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        # Assert
        assert "provenance" in cols

    def test_migration_preserves_existing_rows_as_tracked(self, tmp_path):
        # Arrange — insert a row WITHOUT provenance (simulate pre-existing DB
        # by creating the DB, inserting a row via raw SQL without the new cols,
        # then running the migration manually).
        import sqlite3

        db_path = tmp_path / "legacy.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE runs (session_id TEXT PRIMARY KEY, script_path TEXT, "
            "script_hash TEXT, started_at TIMESTAMP, finished_at TIMESTAMP, "
            "status TEXT, exit_code INTEGER, parent_session TEXT, "
            "combined_hash TEXT, metadata TEXT)"
        )
        conn.execute(
            "INSERT INTO runs (session_id, script_path, status) "
            "VALUES ('legacy_001', '/old/script.py', 'success')"
        )
        conn.commit()
        conn.close()
        db = VerificationDB(db_path)
        # Act
        run = db.get_run("legacy_001")
        # Assert
        assert run["provenance"] == "tracked"

    def test_migration_preserves_existing_rows_data(self, tmp_path):
        # Arrange — same legacy DB as above; verify original data is intact.
        import sqlite3

        db_path = tmp_path / "legacy2.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE runs (session_id TEXT PRIMARY KEY, script_path TEXT, "
            "script_hash TEXT, started_at TIMESTAMP, finished_at TIMESTAMP, "
            "status TEXT, exit_code INTEGER, parent_session TEXT, "
            "combined_hash TEXT, metadata TEXT)"
        )
        conn.execute(
            "INSERT INTO runs (session_id, script_path, status) "
            "VALUES ('legacy_002', '/old/script.py', 'success')"
        )
        conn.commit()
        conn.close()
        db = VerificationDB(db_path)
        # Act
        run = db.get_run("legacy_002")
        # Assert
        assert run["session_id"] == "legacy_002"


class TestAddRunProvenance:
    """Tests for provenance + exception_reason in add_run."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test_addrun_prov.db"
        return VerificationDB(db_path)

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


# EOF
