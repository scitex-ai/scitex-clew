#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for FileHashMixin.find_sessions_by_files (batch N+1 elimination).

Mirrors src/scitex_clew/_db/_file_hashes.py per the project mirror rule.

All tests use a real temp VerificationDB — no mocks (PA-307).
Each test contains exactly one assertion, with # Arrange / # Act / # Assert
markers each on its own line in that order.
"""

from __future__ import annotations

import pytest

from scitex_clew import VerificationDB
from scitex_clew._chain._routes import resolve_file_dag


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path, name="test.db"):
    return VerificationDB(tmp_path / name)


def _seed(db, session_id, inputs=(), outputs=()):
    """Insert a session with the given input and output file records."""
    db.add_run(session_id=session_id, script_path=f"/scripts/{session_id}.py")
    for fp in inputs:
        db.add_file_hash(session_id, fp, f"h-{fp}", "input")
    for fp in outputs:
        db.add_file_hash(session_id, fp, f"h-{fp}", "output")


# ---------------------------------------------------------------------------
# find_sessions_by_files: basic batch lookup
# ---------------------------------------------------------------------------


class TestFindSessionsByFilesBasic:
    def test_single_file_single_producer_returns_correct_mapping(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "producer_a", outputs=["/data/out.csv"])
        # Act
        result = db.find_sessions_by_files(["/data/out.csv"], role="output")
        # Assert
        assert result == {"/data/out.csv": ["producer_a"]}

    def test_empty_file_list_returns_empty_dict(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "s1", outputs=["/data/out.csv"])
        # Act
        result = db.find_sessions_by_files([], role="output")
        # Assert
        assert result == {}

    def test_file_with_no_producer_is_absent_from_result(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "s1", outputs=["/data/out.csv"])
        # Act
        result = db.find_sessions_by_files(["/data/no-such.csv"], role="output")
        # Assert
        assert "/data/no-such.csv" not in result

    def test_multiple_files_returns_mapping_for_each_file(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "sa", outputs=["/a.csv"])
        _seed(db, "sb", outputs=["/b.csv"])
        # Act
        result = db.find_sessions_by_files(["/a.csv", "/b.csv"], role="output")
        # Assert
        assert set(result.keys()) == {"/a.csv", "/b.csv"}

    def test_multiple_producers_per_file_are_all_returned(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "s_old", outputs=["/shared.csv"])
        _seed(db, "s_new", outputs=["/shared.csv"])
        # Act
        result = db.find_sessions_by_files(["/shared.csv"], role="output")
        # Assert
        assert set(result["/shared.csv"]) == {"s_old", "s_new"}


# ---------------------------------------------------------------------------
# find_sessions_by_files vs N individual find_session_by_file calls
# ---------------------------------------------------------------------------


class TestBatchEquivalenceToIndividualCalls:
    def test_batch_result_matches_individual_calls_for_fixture_set(self, tmp_path):
        """Batch result == union of N individual find_session_by_file calls."""
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "panel_a", outputs=["/fig/a.yaml"])
        _seed(db, "panel_b", outputs=["/fig/b.yaml"])
        _seed(db, "panel_c", outputs=["/fig/c.yaml"])
        file_paths = ["/fig/a.yaml", "/fig/b.yaml", "/fig/c.yaml"]
        individual = {
            fp: db.find_session_by_file(fp, role="output") for fp in file_paths
        }
        # Act
        batch = db.find_sessions_by_files(file_paths, role="output")
        # Assert
        assert batch == individual

    def test_batch_newest_first_order_matches_individual_order(self, tmp_path):
        """Newest-first order from batch must equal find_session_by_file order."""
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "s_old", outputs=["/shared.csv"])
        _seed(db, "s_new", outputs=["/shared.csv"])
        individual_order = db.find_session_by_file("/shared.csv", role="output")
        # Act
        batch = db.find_sessions_by_files(["/shared.csv"], role="output")
        # Assert
        assert batch["/shared.csv"] == individual_order


# ---------------------------------------------------------------------------
# Topology preservation: resolve_file_dag produces identical DAGs
# ---------------------------------------------------------------------------


class TestTopologyPreservation:
    """Multi-session DAG built via the real DB API; topology must be unchanged."""

    def _build_multi_session_db(self, tmp_path):
        """3 panels -> composer with a shared read-only CONFIG (no producer)."""
        db = _make_db(tmp_path)
        _seed(db, "panel_a", outputs=["/fig/a.yaml"])
        _seed(db, "panel_b", outputs=["/fig/b.yaml"])
        _seed(db, "panel_c", outputs=["/fig/c.yaml"])
        _seed(
            db,
            "composer",
            inputs=["/fig/a.yaml", "/fig/b.yaml", "/fig/c.yaml", "/cfg/CONFIG.yaml"],
        )
        return db

    def test_multi_session_dag_parents_are_exactly_three_panels(self, tmp_path):
        # Arrange
        db = self._build_multi_session_db(tmp_path)
        # Act
        adjacency, _ = resolve_file_dag(["composer"], db=db)
        # Assert
        assert set(adjacency["composer"]) == {"panel_a", "panel_b", "panel_c"}

    def test_multi_session_dag_all_ids_correct(self, tmp_path):
        # Arrange
        db = self._build_multi_session_db(tmp_path)
        # Act
        _, all_ids = resolve_file_dag(["composer"], db=db)
        # Assert
        assert all_ids == {"composer", "panel_a", "panel_b", "panel_c"}

    def test_multi_session_dag_readonly_config_adds_no_parent(self, tmp_path):
        # Arrange
        db = self._build_multi_session_db(tmp_path)
        # Act
        adjacency, _ = resolve_file_dag(["composer"], db=db)
        # Assert
        assert len(adjacency["composer"]) == 3

    def test_multi_session_dag_panel_sessions_are_roots(self, tmp_path):
        # Arrange
        db = self._build_multi_session_db(tmp_path)
        # Act
        adjacency, _ = resolve_file_dag(["composer"], db=db)
        # Assert
        assert adjacency["panel_a"] == []


# ---------------------------------------------------------------------------
# Edge cases: empty inputs and no-producer inputs
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_session_with_no_inputs_has_no_parents(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "raw_source", outputs=["/raw.csv"])
        # Act
        adjacency, _ = resolve_file_dag(["raw_source"], db=db)
        # Assert
        assert adjacency["raw_source"] == []

    def test_session_input_with_no_producer_adds_no_parent(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "consumer", inputs=["/external.csv"])
        # Act
        adjacency, _ = resolve_file_dag(["consumer"], db=db)
        # Assert
        assert adjacency["consumer"] == []

    def test_self_read_does_not_create_self_edge_via_batch(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path)
        _seed(db, "sess", inputs=["/out.csv"], outputs=["/out.csv"])
        # Act
        adjacency, _ = resolve_file_dag(["sess"], db=db)
        # Assert
        assert adjacency["sess"] == []


# EOF
