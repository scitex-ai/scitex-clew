#!/usr/bin/env python3
"""Tests for scitex_clew._db_chain module (ChainMixin via VerificationDB)."""

from __future__ import annotations

import pytest

from scitex_clew._db import VerificationDB


@pytest.fixture
def db(tmp_path):
    """Fresh isolated DB for each test."""
    return VerificationDB(tmp_path / "chain_test.db")


def _add_run(db, session_id, script_path="/path/script.py", parent_session=None):
    db.add_run(
        session_id=session_id,
        script_path=script_path,
        parent_session=parent_session,
    )


# ---------------------------------------------------------------------------
# get_chain
# ---------------------------------------------------------------------------


class TestGetChain:
    def test_single_run_chain_is_itself(self, db):
        # Arrange
        # Arrange
        _add_run(db, "solo")
        # Act
        # Act
        chain = db.get_chain("solo")
        # Assert
        # Assert
        assert chain == ["solo"]

    def test_parent_child_chain_chain_0_child(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "parent")
        _add_run(db, "child", parent_session="parent")
        # Act
        # Act
        chain = db.get_chain("child")
        # Act
        # Assert
        # Assert
        # Assert
        assert chain[0] == "child"

    def test_parent_child_chain_chain_1_parent(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "parent")
        _add_run(db, "child", parent_session="parent")
        # Act
        # Act
        chain = db.get_chain("child")
        # Act
        # Assert
        # Assert
        # Assert
        assert chain[1] == "parent"


    def test_three_level_chain_len_chain_is_3(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "gp")
        _add_run(db, "parent", parent_session="gp")
        _add_run(db, "child", parent_session="parent")
        # Act
        # Act
        chain = db.get_chain("child")
        # Act
        # Assert
        # Assert
        # Assert
        assert len(chain) == 3

    def test_three_level_chain_chain_0_child(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "gp")
        _add_run(db, "parent", parent_session="gp")
        _add_run(db, "child", parent_session="parent")
        # Act
        # Act
        chain = db.get_chain("child")
        # Act
        # Assert
        # Assert
        # Assert
        assert chain[0] == "child"

    def test_three_level_chain_chain_1_gp(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "gp")
        _add_run(db, "parent", parent_session="gp")
        _add_run(db, "child", parent_session="parent")
        # Act
        # Act
        chain = db.get_chain("child")
        # Act
        # Assert
        # Assert
        # Assert
        assert chain[-1] == "gp"


    def test_chain_for_nonexistent_session(self, db):
        # Should return a list with just the ID (no DB row found)
        # Arrange
        # Act
        # Arrange
        # Act
        chain = db.get_chain("nonexistent")
        # Assert
        # Assert
        assert chain == ["nonexistent"]

    def test_chain_includes_all_ancestors(self, db):
        # Arrange
        # Arrange
        for i in range(5):
            parent = f"level_{i - 1}" if i > 0 else None
            _add_run(db, f"level_{i}", parent_session=parent)
        # Act
        # Act
        chain = db.get_chain("level_4")
        # Assert
        # Assert
        assert len(chain) == 5


# ---------------------------------------------------------------------------
# get_children
# ---------------------------------------------------------------------------


class TestGetChildren:
    def test_no_children_children_equals_case(self, db):
        # Arrange
        # Arrange
        _add_run(db, "leaf")
        # Act
        # Act
        children = db.get_children("leaf")
        # Assert
        # Assert
        assert children == []

    def test_single_child_children_equals_child(self, db):
        # Arrange
        # Arrange
        _add_run(db, "parent")
        _add_run(db, "child", parent_session="parent")
        # Act
        # Act
        children = db.get_children("parent")
        # Assert
        # Assert
        assert children == ["child"]

    def test_multiple_children_set_children_child_a_child_b(self, db):
        # Arrange
        # Arrange
        _add_run(db, "parent")
        _add_run(db, "child_a", parent_session="parent")
        _add_run(db, "child_b", parent_session="parent")
        # Act
        # Act
        children = db.get_children("parent")
        # Assert
        # Assert
        assert set(children) == {"child_a", "child_b"}

    def test_nonexistent_parent_returns_empty(self, db):
        # Arrange
        # Act
        # Arrange
        # Act
        children = db.get_children("no_such_parent")
        # Assert
        # Assert
        assert children == []


# ---------------------------------------------------------------------------
# set_parent
# ---------------------------------------------------------------------------


class TestSetParent:
    def test_set_parent_updates_run(self, db):
        # Arrange
        # Arrange
        _add_run(db, "parent_sp")
        _add_run(db, "child_sp")
        db.set_parent("child_sp", "parent_sp")
        # Act
        # Act
        run = db.get_run("child_sp")
        # Assert
        # Assert
        assert run["parent_session"] == "parent_sp"

    def test_set_parent_populates_session_parents_table(self, db):
        # Arrange
        # Arrange
        _add_run(db, "p1")
        _add_run(db, "c1")
        db.set_parent("c1", "p1")
        # Act
        # Act
        parents = db.get_parents("c1")
        # Assert
        # Assert
        assert "p1" in parents

    def test_set_parent_chain_traversal(self, db):
        # Arrange
        # Arrange
        _add_run(db, "root")
        _add_run(db, "middle")
        _add_run(db, "leaf")
        db.set_parent("middle", "root")
        db.set_parent("leaf", "middle")
        # Act
        # Act
        chain = db.get_chain("leaf")
        # Assert
        # Assert
        assert chain == ["leaf", "middle", "root"]


# ---------------------------------------------------------------------------
# add_parent
# ---------------------------------------------------------------------------


class TestAddParent:
    def test_add_parent_inserts_junction(self, db):
        # Arrange
        # Arrange
        _add_run(db, "p_add")
        _add_run(db, "c_add")
        db.add_parent("c_add", "p_add")
        # Act
        # Act
        parents = db.get_parents("c_add")
        # Assert
        # Assert
        assert "p_add" in parents

    def test_add_multiple_parents(self, db):
        # Arrange
        # Arrange
        _add_run(db, "p1")
        _add_run(db, "p2")
        _add_run(db, "child_multi")
        db.add_parent("child_multi", "p1")
        db.add_parent("child_multi", "p2")
        # Act
        # Act
        parents = db.get_parents("child_multi")
        # Assert
        # Assert
        assert set(parents) == {"p1", "p2"}

    def test_add_parent_idempotent(self, db):
        # Arrange
        # Arrange
        _add_run(db, "pa")
        _add_run(db, "ca")
        db.add_parent("ca", "pa")
        db.add_parent("ca", "pa")  # Should not raise or duplicate
        # Act
        # Act
        parents = db.get_parents("ca")
        # Assert
        # Assert
        assert parents.count("pa") == 1

    def test_add_parent_sets_primary_if_null_db_get_run_c_primary_parent_session_is_none(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "p_primary")
        # Act
        # Act
        _add_run(db, "c_primary")
        # Act
        # Assert
        # Assert
        # Assert
        assert db.get_run("c_primary")["parent_session"] is None

    def test_add_parent_sets_primary_if_null_run_parent_session_p_primary_db_get_run_c_primary_parent_session_is_none(self, db):
        # Arrange
        # Arrange
        _add_run(db, "p_primary")
        # Act
        _add_run(db, "c_primary")
        # Act
        # Assert
        # Assert
        assert db.get_run("c_primary")["parent_session"] is None

    def test_add_parent_sets_primary_if_null_run_parent_session_p_primary_run_parent_session_p_primary(self, db):
        # Arrange
        # Arrange
        _add_run(db, "p_primary")
        # Act
        _add_run(db, "c_primary")
        # No parent initially
        # Assert
        assert db.get_run("c_primary")["parent_session"] is None
        db.add_parent("c_primary", "p_primary")
        run = db.get_run("c_primary")
        # Act
        # Assert
        assert run["parent_session"] == "p_primary"



    def test_add_parent_does_not_overwrite_existing_primary(self, db):
        # Arrange
        # Arrange
        _add_run(db, "first_parent")
        _add_run(db, "second_parent")
        _add_run(db, "child_existing", parent_session="first_parent")
        db.add_parent("child_existing", "second_parent")
        # Act
        # Act
        run = db.get_run("child_existing")
        # Primary parent should remain the original
        # Assert
        # Assert
        assert run["parent_session"] == "first_parent"


# ---------------------------------------------------------------------------
# get_parents
# ---------------------------------------------------------------------------


class TestGetParents:
    def test_no_parents_parents_equals_case(self, db):
        # Arrange
        # Arrange
        _add_run(db, "root_node")
        # Act
        # Act
        parents = db.get_parents("root_node")
        # Assert
        # Assert
        assert parents == []

    def test_single_parent_p_single_in_parents(self, db):
        # Arrange
        # Arrange
        _add_run(db, "p_single")
        _add_run(db, "c_single")
        db.add_parent("c_single", "p_single")
        # Act
        # Act
        parents = db.get_parents("c_single")
        # Assert
        # Assert
        assert "p_single" in parents

    def test_multiple_parents_set_parents_p_a_p_b(self, db):
        # Arrange
        # Arrange
        _add_run(db, "p_a")
        _add_run(db, "p_b")
        _add_run(db, "c_multi")
        db.add_parent("c_multi", "p_a")
        db.add_parent("c_multi", "p_b")
        # Act
        # Act
        parents = db.get_parents("c_multi")
        # Assert
        # Assert
        assert set(parents) == {"p_a", "p_b"}

    def test_nonexistent_session_returns_empty(self, db):
        # Arrange
        # Act
        # Arrange
        # Act
        parents = db.get_parents("does_not_exist")
        # Assert
        # Assert
        assert parents == []


# ---------------------------------------------------------------------------
# get_dag
# ---------------------------------------------------------------------------


class TestGetDag:
    def test_single_node_dag_only_node_in_all_ids(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "only_node")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["only_node"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "only_node" in all_ids

    def test_single_node_dag_adjacency_only_node(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "only_node")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["only_node"])
        # Act
        # Assert
        # Assert
        # Assert
        assert adjacency["only_node"] == []


    def test_linear_chain_dag_all_ids_equals_root_dag_mid_dag_leaf_dag(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "root_dag")
        _add_run(db, "mid_dag", parent_session="root_dag")
        _add_run(db, "leaf_dag", parent_session="mid_dag")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["leaf_dag"])
        # Act
        # Assert
        # Assert
        # Assert
        assert all_ids == {"root_dag", "mid_dag", "leaf_dag"}

    def test_linear_chain_dag_adjacency_leaf_dag_mid_dag(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "root_dag")
        _add_run(db, "mid_dag", parent_session="root_dag")
        _add_run(db, "leaf_dag", parent_session="mid_dag")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["leaf_dag"])
        # Act
        # Assert
        # Assert
        # Assert
        assert adjacency["leaf_dag"] == ["mid_dag"]

    def test_linear_chain_dag_adjacency_mid_dag_root_dag(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "root_dag")
        _add_run(db, "mid_dag", parent_session="root_dag")
        _add_run(db, "leaf_dag", parent_session="mid_dag")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["leaf_dag"])
        # Act
        # Assert
        # Assert
        # Assert
        assert adjacency["mid_dag"] == ["root_dag"]

    def test_linear_chain_dag_adjacency_root_dag(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "root_dag")
        _add_run(db, "mid_dag", parent_session="root_dag")
        _add_run(db, "leaf_dag", parent_session="mid_dag")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["leaf_dag"])
        # Act
        # Assert
        # Assert
        # Assert
        assert adjacency["root_dag"] == []


    def test_multi_parent_dag_pa_dag_in_all_ids(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "pa_dag")
        _add_run(db, "pb_dag")
        _add_run(db, "child_dag")
        db.add_parent("child_dag", "pa_dag")
        db.add_parent("child_dag", "pb_dag")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["child_dag"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "pa_dag" in all_ids

    def test_multi_parent_dag_pb_dag_in_all_ids(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "pa_dag")
        _add_run(db, "pb_dag")
        _add_run(db, "child_dag")
        db.add_parent("child_dag", "pa_dag")
        db.add_parent("child_dag", "pb_dag")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["child_dag"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "pb_dag" in all_ids

    def test_multi_parent_dag_child_dag_in_all_ids(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "pa_dag")
        _add_run(db, "pb_dag")
        _add_run(db, "child_dag")
        db.add_parent("child_dag", "pa_dag")
        db.add_parent("child_dag", "pb_dag")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["child_dag"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "child_dag" in all_ids

    def test_multi_parent_dag_set_adjacency_child_dag_pa_dag_pb_dag(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "pa_dag")
        _add_run(db, "pb_dag")
        _add_run(db, "child_dag")
        db.add_parent("child_dag", "pa_dag")
        db.add_parent("child_dag", "pb_dag")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["child_dag"])
        # Act
        # Assert
        # Assert
        # Assert
        assert set(adjacency["child_dag"]) == {"pa_dag", "pb_dag"}


    def test_multiple_leaves_shared_root_in_all_ids(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "shared_root")
        _add_run(db, "leaf_x", parent_session="shared_root")
        _add_run(db, "leaf_y", parent_session="shared_root")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["leaf_x", "leaf_y"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "shared_root" in all_ids

    def test_multiple_leaves_leaf_x_in_all_ids(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "shared_root")
        _add_run(db, "leaf_x", parent_session="shared_root")
        _add_run(db, "leaf_y", parent_session="shared_root")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["leaf_x", "leaf_y"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "leaf_x" in all_ids

    def test_multiple_leaves_leaf_y_in_all_ids(self, db):
        # Arrange
        # Arrange
        # Arrange
        _add_run(db, "shared_root")
        _add_run(db, "leaf_x", parent_session="shared_root")
        _add_run(db, "leaf_y", parent_session="shared_root")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["leaf_x", "leaf_y"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "leaf_y" in all_ids


    def test_all_ids_in_adjacency(self, db):
        # Arrange
        # Arrange
        _add_run(db, "root_all")
        _add_run(db, "child_all", parent_session="root_all")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["child_all"])
        # Assert
        # Assert
        assert all(sid in adjacency for sid in all_ids)

    def test_empty_input_returns_empty(self, db):
        # Arrange
        # Act
        # Arrange
        # Act
        adjacency, all_ids = db.get_dag([])
        # Assert
        # Assert
        assert len(all_ids) == 0

    def test_fallback_to_runs_parent_session(self, db):
        # No explicit add_parent calls; relies on runs.parent_session
        # Arrange
        # Arrange
        _add_run(db, "root_fb")
        _add_run(db, "child_fb", parent_session="root_fb")
        # Act
        # Act
        adjacency, all_ids = db.get_dag(["child_fb"])
        # Assert
        # Assert
        assert "root_fb" in all_ids


# ---------------------------------------------------------------------------
# migrate_session_parents (internal, called by __init__)
# ---------------------------------------------------------------------------


class TestMigrateSessionParents:
    def test_existing_parent_migrated_to_junction(self, tmp_path):
        # Populate the runs table directly via SQLite, then open a fresh
        # VerificationDB — _migrate_session_parents runs at __init__ and
        # should copy the parent_session column into session_parents.
        # Arrange
        # Arrange
        import sqlite3

        db_path = tmp_path / "migrate_mig.db"

        # Seed with a raw DB that has data in runs but NOT in session_parents
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE runs (
                session_id TEXT PRIMARY KEY,
                script_path TEXT,
                script_hash TEXT,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                status TEXT,
                exit_code INTEGER,
                parent_session TEXT,
                combined_hash TEXT,
                metadata TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE file_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                file_path TEXT,
                hash TEXT,
                role TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, file_path, role)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE verification_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                verified_at TIMESTAMP,
                level TEXT,
                status TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE session_parents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                parent_session TEXT NOT NULL,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_id, parent_session)
            )
            """
        )
        conn.execute(
            "INSERT INTO runs (session_id, script_path, parent_session) "
            "VALUES ('p_mig', '/path/p.py', NULL)"
        )
        conn.execute(
            "INSERT INTO runs (session_id, script_path, parent_session) "
            "VALUES ('c_mig', '/path/c.py', 'p_mig')"
        )
        conn.commit()
        conn.close()

        # Now open VerificationDB — _migrate_session_parents should fire
        db = VerificationDB(db_path)
        # Act
        # Act
        parents = db.get_parents("c_mig")
        # Assert
        # Assert
        assert "p_mig" in parents


# EOF
