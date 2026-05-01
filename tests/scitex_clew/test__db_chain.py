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
        _add_run(db, "solo")
        chain = db.get_chain("solo")
        assert chain == ["solo"]

    def test_parent_child_chain(self, db):
        _add_run(db, "parent")
        _add_run(db, "child", parent_session="parent")
        chain = db.get_chain("child")
        assert chain[0] == "child"
        assert chain[1] == "parent"

    def test_three_level_chain(self, db):
        _add_run(db, "gp")
        _add_run(db, "parent", parent_session="gp")
        _add_run(db, "child", parent_session="parent")
        chain = db.get_chain("child")
        assert len(chain) == 3
        assert chain[0] == "child"
        assert chain[-1] == "gp"

    def test_chain_for_nonexistent_session(self, db):
        # Should return a list with just the ID (no DB row found)
        chain = db.get_chain("nonexistent")
        assert chain == ["nonexistent"]

    def test_chain_includes_all_ancestors(self, db):
        for i in range(5):
            parent = f"level_{i - 1}" if i > 0 else None
            _add_run(db, f"level_{i}", parent_session=parent)
        chain = db.get_chain("level_4")
        assert len(chain) == 5


# ---------------------------------------------------------------------------
# get_children
# ---------------------------------------------------------------------------


class TestGetChildren:
    def test_no_children(self, db):
        _add_run(db, "leaf")
        children = db.get_children("leaf")
        assert children == []

    def test_single_child(self, db):
        _add_run(db, "parent")
        _add_run(db, "child", parent_session="parent")
        children = db.get_children("parent")
        assert children == ["child"]

    def test_multiple_children(self, db):
        _add_run(db, "parent")
        _add_run(db, "child_a", parent_session="parent")
        _add_run(db, "child_b", parent_session="parent")
        children = db.get_children("parent")
        assert set(children) == {"child_a", "child_b"}

    def test_nonexistent_parent_returns_empty(self, db):
        children = db.get_children("no_such_parent")
        assert children == []


# ---------------------------------------------------------------------------
# set_parent
# ---------------------------------------------------------------------------


class TestSetParent:
    def test_set_parent_updates_run(self, db):
        _add_run(db, "parent_sp")
        _add_run(db, "child_sp")
        db.set_parent("child_sp", "parent_sp")
        run = db.get_run("child_sp")
        assert run["parent_session"] == "parent_sp"

    def test_set_parent_populates_session_parents_table(self, db):
        _add_run(db, "p1")
        _add_run(db, "c1")
        db.set_parent("c1", "p1")
        parents = db.get_parents("c1")
        assert "p1" in parents

    def test_set_parent_chain_traversal(self, db):
        _add_run(db, "root")
        _add_run(db, "middle")
        _add_run(db, "leaf")
        db.set_parent("middle", "root")
        db.set_parent("leaf", "middle")
        chain = db.get_chain("leaf")
        assert chain == ["leaf", "middle", "root"]


# ---------------------------------------------------------------------------
# add_parent
# ---------------------------------------------------------------------------


class TestAddParent:
    def test_add_parent_inserts_junction(self, db):
        _add_run(db, "p_add")
        _add_run(db, "c_add")
        db.add_parent("c_add", "p_add")
        parents = db.get_parents("c_add")
        assert "p_add" in parents

    def test_add_multiple_parents(self, db):
        _add_run(db, "p1")
        _add_run(db, "p2")
        _add_run(db, "child_multi")
        db.add_parent("child_multi", "p1")
        db.add_parent("child_multi", "p2")
        parents = db.get_parents("child_multi")
        assert set(parents) == {"p1", "p2"}

    def test_add_parent_idempotent(self, db):
        _add_run(db, "pa")
        _add_run(db, "ca")
        db.add_parent("ca", "pa")
        db.add_parent("ca", "pa")  # Should not raise or duplicate
        parents = db.get_parents("ca")
        assert parents.count("pa") == 1

    def test_add_parent_sets_primary_if_null(self, db):
        _add_run(db, "p_primary")
        _add_run(db, "c_primary")
        # No parent initially
        assert db.get_run("c_primary")["parent_session"] is None
        db.add_parent("c_primary", "p_primary")
        run = db.get_run("c_primary")
        assert run["parent_session"] == "p_primary"

    def test_add_parent_does_not_overwrite_existing_primary(self, db):
        _add_run(db, "first_parent")
        _add_run(db, "second_parent")
        _add_run(db, "child_existing", parent_session="first_parent")
        db.add_parent("child_existing", "second_parent")
        run = db.get_run("child_existing")
        # Primary parent should remain the original
        assert run["parent_session"] == "first_parent"


# ---------------------------------------------------------------------------
# get_parents
# ---------------------------------------------------------------------------


class TestGetParents:
    def test_no_parents(self, db):
        _add_run(db, "root_node")
        parents = db.get_parents("root_node")
        assert parents == []

    def test_single_parent(self, db):
        _add_run(db, "p_single")
        _add_run(db, "c_single")
        db.add_parent("c_single", "p_single")
        parents = db.get_parents("c_single")
        assert "p_single" in parents

    def test_multiple_parents(self, db):
        _add_run(db, "p_a")
        _add_run(db, "p_b")
        _add_run(db, "c_multi")
        db.add_parent("c_multi", "p_a")
        db.add_parent("c_multi", "p_b")
        parents = db.get_parents("c_multi")
        assert set(parents) == {"p_a", "p_b"}

    def test_nonexistent_session_returns_empty(self, db):
        parents = db.get_parents("does_not_exist")
        assert parents == []


# ---------------------------------------------------------------------------
# get_dag
# ---------------------------------------------------------------------------


class TestGetDag:
    def test_single_node_dag(self, db):
        _add_run(db, "only_node")
        adjacency, all_ids = db.get_dag(["only_node"])
        assert "only_node" in all_ids
        assert adjacency["only_node"] == []

    def test_linear_chain_dag(self, db):
        _add_run(db, "root_dag")
        _add_run(db, "mid_dag", parent_session="root_dag")
        _add_run(db, "leaf_dag", parent_session="mid_dag")
        adjacency, all_ids = db.get_dag(["leaf_dag"])
        assert all_ids == {"root_dag", "mid_dag", "leaf_dag"}
        assert adjacency["leaf_dag"] == ["mid_dag"]
        assert adjacency["mid_dag"] == ["root_dag"]
        assert adjacency["root_dag"] == []

    def test_multi_parent_dag(self, db):
        _add_run(db, "pa_dag")
        _add_run(db, "pb_dag")
        _add_run(db, "child_dag")
        db.add_parent("child_dag", "pa_dag")
        db.add_parent("child_dag", "pb_dag")
        adjacency, all_ids = db.get_dag(["child_dag"])
        assert "pa_dag" in all_ids
        assert "pb_dag" in all_ids
        assert "child_dag" in all_ids
        assert set(adjacency["child_dag"]) == {"pa_dag", "pb_dag"}

    def test_multiple_leaves(self, db):
        _add_run(db, "shared_root")
        _add_run(db, "leaf_x", parent_session="shared_root")
        _add_run(db, "leaf_y", parent_session="shared_root")
        adjacency, all_ids = db.get_dag(["leaf_x", "leaf_y"])
        assert "shared_root" in all_ids
        assert "leaf_x" in all_ids
        assert "leaf_y" in all_ids

    def test_all_ids_in_adjacency(self, db):
        _add_run(db, "root_all")
        _add_run(db, "child_all", parent_session="root_all")
        adjacency, all_ids = db.get_dag(["child_all"])
        for sid in all_ids:
            assert sid in adjacency

    def test_empty_input_returns_empty(self, db):
        adjacency, all_ids = db.get_dag([])
        assert len(all_ids) == 0

    def test_fallback_to_runs_parent_session(self, db):
        # No explicit add_parent calls; relies on runs.parent_session
        _add_run(db, "root_fb")
        _add_run(db, "child_fb", parent_session="root_fb")
        adjacency, all_ids = db.get_dag(["child_fb"])
        assert "root_fb" in all_ids


# ---------------------------------------------------------------------------
# migrate_session_parents (internal, called by __init__)
# ---------------------------------------------------------------------------


class TestMigrateSessionParents:
    def test_existing_parent_migrated_to_junction(self, tmp_path):
        # Populate the runs table directly via SQLite, then open a fresh
        # VerificationDB — _migrate_session_parents runs at __init__ and
        # should copy the parent_session column into session_parents.
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
        parents = db.get_parents("c_mig")
        assert "p_mig" in parents


# EOF
