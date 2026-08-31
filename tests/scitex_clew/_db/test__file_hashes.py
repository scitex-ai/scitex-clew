#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for FileHashMixin.find_sessions_by_files (batch N+1 elimination).

Mirrors src/scitex_clew/_db/_file_hashes.py per the project mirror rule.

All tests use a real VerificationDB against the per-test PostgreSQL
schema handed out by the autouse `isolated_store` fixture
(tests/conftest.py) — no mocks (PA-307).
Each test contains exactly one assertion, with # Arrange / # Act / # Assert
markers each on its own line in that order.
"""

from __future__ import annotations

import os

import pytest

from scitex_clew import VerificationDB
from scitex_clew._chain._routes import resolve_file_dag
from scitex_clew._db._file_hashes import _resolve_host


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db():
    return VerificationDB()


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
    def test_single_file_single_producer_returns_correct_mapping(self):
        # Arrange
        db = _make_db()
        _seed(db, "producer_a", outputs=["/data/out.csv"])
        # Act
        result = db.find_sessions_by_files(["/data/out.csv"], role="output")
        # Assert
        assert result == {"/data/out.csv": ["producer_a"]}

    def test_empty_file_list_returns_empty_dict(self):
        # Arrange
        db = _make_db()
        _seed(db, "s1", outputs=["/data/out.csv"])
        # Act
        result = db.find_sessions_by_files([], role="output")
        # Assert
        assert result == {}

    def test_file_with_no_producer_is_absent_from_result(self):
        # Arrange
        db = _make_db()
        _seed(db, "s1", outputs=["/data/out.csv"])
        # Act
        result = db.find_sessions_by_files(["/data/no-such.csv"], role="output")
        # Assert
        assert "/data/no-such.csv" not in result

    def test_multiple_files_returns_mapping_for_each_file(self):
        # Arrange
        db = _make_db()
        _seed(db, "sa", outputs=["/a.csv"])
        _seed(db, "sb", outputs=["/b.csv"])
        # Act
        result = db.find_sessions_by_files(["/a.csv", "/b.csv"], role="output")
        # Assert
        assert set(result.keys()) == {"/a.csv", "/b.csv"}

    def test_multiple_producers_per_file_are_all_returned(self):
        # Arrange
        db = _make_db()
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
    def test_batch_result_matches_individual_calls_for_fixture_set(self):
        """Batch result == union of N individual find_session_by_file calls."""
        # Arrange
        db = _make_db()
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

    def test_batch_newest_first_order_matches_individual_order(self):
        """Newest-first order from batch must equal find_session_by_file order."""
        # Arrange
        db = _make_db()
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

    def _build_multi_session_db(self):
        """3 panels -> composer with a shared read-only CONFIG (no producer)."""
        db = _make_db()
        _seed(db, "panel_a", outputs=["/fig/a.yaml"])
        _seed(db, "panel_b", outputs=["/fig/b.yaml"])
        _seed(db, "panel_c", outputs=["/fig/c.yaml"])
        _seed(
            db,
            "composer",
            inputs=["/fig/a.yaml", "/fig/b.yaml", "/fig/c.yaml", "/cfg/CONFIG.yaml"],
        )
        return db

    def test_multi_session_dag_parents_are_exactly_three_panels(self):
        # Arrange
        db = self._build_multi_session_db()
        # Act
        adjacency, _ = resolve_file_dag(["composer"], db=db)
        # Assert
        assert set(adjacency["composer"]) == {"panel_a", "panel_b", "panel_c"}

    def test_multi_session_dag_all_ids_correct(self):
        # Arrange
        db = self._build_multi_session_db()
        # Act
        _, all_ids = resolve_file_dag(["composer"], db=db)
        # Assert
        assert all_ids == {"composer", "panel_a", "panel_b", "panel_c"}

    def test_multi_session_dag_readonly_config_adds_no_parent(self):
        # Arrange
        db = self._build_multi_session_db()
        # Act
        adjacency, _ = resolve_file_dag(["composer"], db=db)
        # Assert
        assert len(adjacency["composer"]) == 3

    def test_multi_session_dag_panel_sessions_are_roots(self):
        # Arrange
        db = self._build_multi_session_db()
        # Act
        adjacency, _ = resolve_file_dag(["composer"], db=db)
        # Assert
        assert adjacency["panel_a"] == []


# ---------------------------------------------------------------------------
# Edge cases: empty inputs and no-producer inputs
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_session_with_no_inputs_has_no_parents(self):
        # Arrange
        db = _make_db()
        _seed(db, "raw_source", outputs=["/raw.csv"])
        # Act
        adjacency, _ = resolve_file_dag(["raw_source"], db=db)
        # Assert
        assert adjacency["raw_source"] == []

    def test_session_input_with_no_producer_adds_no_parent(self):
        # Arrange
        db = _make_db()
        _seed(db, "consumer", inputs=["/external.csv"])
        # Act
        adjacency, _ = resolve_file_dag(["consumer"], db=db)
        # Assert
        assert adjacency["consumer"] == []

    def test_self_read_does_not_create_self_edge_via_batch(self):
        # Arrange
        db = _make_db()
        _seed(db, "sess", inputs=["/out.csv"], outputs=["/out.csv"])
        # Act
        adjacency, _ = resolve_file_dag(["sess"], db=db)
        # Assert
        assert adjacency["sess"] == []


# ---------------------------------------------------------------------------
# Frozen flag: add_file_hash + get_frozen_files
# ---------------------------------------------------------------------------


class TestFrozenFlag:
    """Tests for the frozen=True flag in add_file_hash and get_frozen_files."""

    def test_add_file_hash_frozen_true_is_stored(self):
        # Arrange
        db = _make_db()
        db.add_run("s_frz", script_path="/script.py")
        db.add_file_hash("s_frz", "/data/huge.npz", "aabbcc", "input", frozen=True)
        # Act
        frozen = db.get_frozen_files("s_frz")
        # Assert
        assert "/data/huge.npz" in frozen

    def test_add_file_hash_frozen_false_not_in_frozen_set(self):
        # Arrange
        db = _make_db()
        db.add_run("s_nfrz", script_path="/script.py")
        db.add_file_hash("s_nfrz", "/data/small.csv", "112233", "input", frozen=False)
        # Act
        frozen = db.get_frozen_files("s_nfrz")
        # Assert
        assert "/data/small.csv" not in frozen

    def test_add_file_hash_default_not_frozen(self):
        # Arrange
        db = _make_db()
        db.add_run("s_def", script_path="/script.py")
        db.add_file_hash("s_def", "/data/normal.csv", "deadbeef", "input")
        # Act
        frozen = db.get_frozen_files("s_def")
        # Assert
        assert "/data/normal.csv" not in frozen

    def test_get_frozen_files_role_filter_only_returns_matching_role(self):
        # Arrange
        db = _make_db()
        db.add_run("s_role", script_path="/script.py")
        db.add_file_hash("s_role", "/data/in.npz", "aa", "input", frozen=True)
        db.add_file_hash("s_role", "/data/out.csv", "bb", "output", frozen=True)
        # Act
        frozen_inputs = db.get_frozen_files("s_role", role="input")
        # Assert
        assert "/data/out.csv" not in frozen_inputs

    def test_get_frozen_files_returns_set_type(self):
        # Arrange
        db = _make_db()
        db.add_run("s_set", script_path="/script.py")
        db.add_file_hash("s_set", "/x.npz", "ff", "input", frozen=True)
        # Act
        result = db.get_frozen_files("s_set")
        # Assert
        assert isinstance(result, set)

    def test_get_frozen_files_empty_session_returns_empty_set(self):
        # Arrange
        db = _make_db()
        db.add_run("s_empty", script_path="/script.py")
        # Act
        frozen = db.get_frozen_files("s_empty")
        # Assert
        assert frozen == set()

    def test_get_file_hashes_still_returns_path_hash_mapping_when_frozen(self):
        # Arrange — frozen flag must NOT break the existing get_file_hashes API.
        db = _make_db()
        db.add_run("s_compat", script_path="/script.py")
        db.add_file_hash("s_compat", "/data/huge.npz", "deadcafe", "input", frozen=True)
        # Act
        hashes = db.get_file_hashes("s_compat", role="input")
        # Assert
        assert hashes["/data/huge.npz"] == "deadcafe"


# ---------------------------------------------------------------------------
# _resolve_host: env-override precedence (real env, save/restore — no mocks)
# ---------------------------------------------------------------------------


class _EnvGuard:
    """Set env keys for the duration of a with-block, then restore verbatim."""

    def __init__(self, **overrides):
        self._overrides = overrides
        self._saved = {}

    def __enter__(self):
        for key, val in self._overrides.items():
            self._saved[key] = os.environ.get(key)
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        return self

    def __exit__(self, *exc):
        for key, prev in self._saved.items():
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev
        return False


class TestResolveHost:
    def test_scitex_clew_host_env_takes_precedence(self):
        # Arrange
        with _EnvGuard(SCITEX_CLEW_HOST="login01", SAC_HOST="compute99"):
            # Act
            host = _resolve_host()
            # Assert
            assert host == "login01"

    def test_sac_host_used_when_clew_host_absent(self):
        # Arrange
        with _EnvGuard(SCITEX_CLEW_HOST=None, SAC_HOST="compute99"):
            # Act
            host = _resolve_host()
            # Assert
            assert host == "compute99"

    def test_falls_back_to_gethostname_when_no_env(self):
        # Arrange
        with _EnvGuard(SCITEX_CLEW_HOST=None, SAC_HOST=None):
            import socket

            expected = socket.gethostname() or None
            # Act
            host = _resolve_host()
            # Assert
            assert host == expected


# ---------------------------------------------------------------------------
# host column: stamped on write, queryable, back-compatible
# ---------------------------------------------------------------------------


class TestHostColumn:
    def test_add_file_hash_stamps_env_host(self):
        # Arrange
        db = _make_db()
        db.add_run("s_h", script_path="/script.py")
        with _EnvGuard(SCITEX_CLEW_HOST="node-A"):
            db.add_file_hash("s_h", "/data/out.csv", "hh01", "output")
        # Act
        hosts = db.hosts_for_hash("hh01")
        # Assert
        assert hosts == ["node-A"]

    def test_add_file_hashes_batch_stamps_env_host(self):
        # Arrange
        db = _make_db()
        db.add_run("s_batch", script_path="/script.py")
        with _EnvGuard(SCITEX_CLEW_HOST="node-B"):
            db.add_file_hashes("s_batch", {"/a.csv": "bh01"}, role="output")
        # Act
        hosts = db.hosts_for_hash("bh01")
        # Assert
        assert hosts == ["node-B"]

    def test_get_file_hashes_still_returns_path_hash_mapping(self):
        # Arrange — host column must not change the get_file_hashes contract.
        db = _make_db()
        db.add_run("s_c", script_path="/script.py")
        db.add_file_hash("s_c", "/data/out.csv", "ch01", "output")
        # Act
        hashes = db.get_file_hashes("s_c", role="output")
        # Assert
        assert hashes == {"/data/out.csv": "ch01"}


# ---------------------------------------------------------------------------
# find_sessions_by_hash / hosts_for_hash: content-addressed lookup (idx_hash)
# ---------------------------------------------------------------------------


class TestContentAddressedLookup:
    def test_finds_session_by_content_regardless_of_path(self):
        # Arrange — same content hash recorded under two DIFFERENT paths.
        db = _make_db()
        db.add_run("s1", script_path="/s1.py")
        db.add_run("s2", script_path="/s2.py")
        db.add_file_hash("s1", "/host_a/out.csv", "SAME", "output")
        db.add_file_hash("s2", "/host_b/out.csv", "SAME", "output")
        # Act
        sessions = db.find_sessions_by_hash("SAME", role="output")
        # Assert
        assert set(sessions) == {"s1", "s2"}

    def test_role_filter_excludes_other_roles(self):
        # Arrange
        db = _make_db()
        db.add_run("s1", script_path="/s1.py")
        db.add_file_hash("s1", "/in.csv", "RH", "input")
        db.add_file_hash("s1", "/out.csv", "RH", "output")
        # Act
        sessions = db.find_sessions_by_hash("RH", role="input")
        # Assert
        assert sessions == ["s1"]

    def test_unknown_hash_returns_empty_list(self):
        # Arrange
        db = _make_db()
        db.add_run("s1", script_path="/s1.py")
        db.add_file_hash("s1", "/out.csv", "KNOWN", "output")
        # Act
        sessions = db.find_sessions_by_hash("MISSING")
        # Assert
        assert sessions == []

    def test_hosts_for_hash_returns_distinct_sorted_hosts(self):
        # Arrange — same content produced on two hosts (+ a duplicate).
        db = _make_db()
        db.add_run("s1", script_path="/s1.py")
        db.add_run("s2", script_path="/s2.py")
        db.add_run("s3", script_path="/s3.py")
        with _EnvGuard(SCITEX_CLEW_HOST="zeta"):
            db.add_file_hash("s1", "/a.csv", "MH", "output")
        with _EnvGuard(SCITEX_CLEW_HOST="alpha"):
            db.add_file_hash("s2", "/b.csv", "MH", "output")
            db.add_file_hash("s3", "/c.csv", "MH", "output")
        # Act
        hosts = db.hosts_for_hash("MH")
        # Assert
        assert hosts == ["alpha", "zeta"]


# EOF
