#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for file-mediated route resolution (``_chain/_routes.py``).

The resolver walks file save->load handshakes instead of the legacy
``session_parents`` junction, so a session's parents are the *newest producer
of each file it loaded* — read-only sources/config (no producer) add no edge,
and the walk is bounded against cycles and depth.

These use a hand-rolled in-memory fake DB (no mocks): it implements exactly the
two read methods the resolver calls, over plain dicts.
"""

from __future__ import annotations

from scitex_clew._chain._routes import resolve_file_dag


class FakeDB:
    """Minimal stand-in exposing the reads ``resolve_file_dag`` needs.

    Parameters
    ----------
    outputs : dict
        ``{session_id: [output_file_path, ...]}`` — newest-inserted session
        last, so producer lookups can return newest-first.
    inputs : dict
        ``{session_id: [input_file_path, ...]}``.
    """

    def __init__(self, outputs, inputs):
        self._outputs = outputs
        self._inputs = inputs

    def get_file_hashes(self, session_id, role=None):
        src = self._outputs if role == "output" else self._inputs
        return {path: "hash-of-" + path for path in src.get(session_id, [])}

    def find_session_by_file(self, file_path, role=None):
        # Producers of file_path, newest-first (mirrors the real DESC order).
        producers = [sid for sid, files in self._outputs.items() if file_path in files]
        return list(reversed(producers))

    def find_sessions_by_files(self, file_paths, role=None):
        """Batch variant: return {file_path: [session_id, ...]} newest-first."""
        result = {}
        for fp in file_paths:
            producers = [
                sid for sid, files in self._outputs.items() if fp in files
            ]
            if producers:
                result[fp] = list(reversed(producers))
        return result


# ---------------------------------------------------------------------------
# fig01 scenario: 3 panels + composer + a shared read-only CONFIG
# ---------------------------------------------------------------------------


def _fig01_db():
    outputs = {
        "panel_a": ["fig01a.yaml"],
        "panel_b": ["fig01b.yaml"],
        "panel_c": ["fig01c.yaml"],
        "composer": ["fig01_cohort.yaml"],
    }
    inputs = {
        # composer loads the 3 panels + a shared CONFIG produced by nobody
        "composer": ["fig01a.yaml", "fig01b.yaml", "fig01c.yaml", "CONFIG.yaml"],
    }
    return FakeDB(outputs, inputs)


class TestFig01Route:
    def test_composer_parents_are_exactly_the_three_panels(self):
        # Arrange
        db = _fig01_db()
        # Act
        adjacency, _ = resolve_file_dag(["composer"], db=db)
        # Assert
        assert set(adjacency["composer"]) == {"panel_a", "panel_b", "panel_c"}

    def test_readonly_config_adds_no_parent(self):
        # Arrange
        db = _fig01_db()
        # Act
        adjacency, _ = resolve_file_dag(["composer"], db=db)
        # Assert
        assert len(adjacency["composer"]) == 3

    def test_all_ids_contains_only_route_sessions(self):
        # Arrange
        db = _fig01_db()
        # Act
        _, all_ids = resolve_file_dag(["composer"], db=db)
        # Assert
        assert all_ids == {"composer", "panel_a", "panel_b", "panel_c"}

    def test_panel_sessions_are_roots(self):
        # Arrange
        db = _fig01_db()
        # Act
        adjacency, _ = resolve_file_dag(["composer"], db=db)
        # Assert
        assert adjacency["panel_a"] == []


# ---------------------------------------------------------------------------
# newest-producer-only: a shared file re-produced over time links once
# ---------------------------------------------------------------------------


class TestNewestProducerOnly:
    def test_shared_input_links_only_newest_producer(self):
        # Arrange — shared.yaml produced by s_old then (newer) s_new
        db = FakeDB(
            outputs={"s_old": ["shared.yaml"], "s_new": ["shared.yaml"]},
            inputs={"consumer": ["shared.yaml"]},
        )
        # Act
        adjacency, _ = resolve_file_dag(["consumer"], db=db)
        # Assert
        assert adjacency["consumer"] == ["s_new"]


# ---------------------------------------------------------------------------
# bounded traversal: cycles and depth never hang
# ---------------------------------------------------------------------------


class TestBoundedTraversal:
    def test_mutual_file_cycle_terminates(self):
        # Arrange — A reads B's output and B reads A's output (a file cycle)
        db = FakeDB(
            outputs={"A": ["fa"], "B": ["fb"]},
            inputs={"A": ["fb"], "B": ["fa"]},
        )
        # Act
        _, all_ids = resolve_file_dag(["A"], db=db)
        # Assert
        assert all_ids == {"A", "B"}

    def test_max_depth_limits_walk(self):
        # Arrange — linear chain s0 <- s1 <- s2 <- s3 (each loads prev output)
        outputs = {f"s{i}": [f"f{i}"] for i in range(4)}
        inputs = {f"s{i}": [f"f{i - 1}"] for i in range(1, 4)}
        db = FakeDB(outputs, inputs)
        # Act — from the leaf s3, allow only 2 hops back
        _, all_ids = resolve_file_dag(["s3"], db=db, max_depth=2)
        # Assert — s3 + 2 hops (s2, s1); s0 is beyond the bound
        assert all_ids == {"s3", "s2", "s1"}


# ---------------------------------------------------------------------------
# unknown / empty inputs
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_leaf_with_no_inputs_has_no_parents(self):
        # Arrange — a raw source session that loaded nothing
        db = FakeDB(outputs={"raw": ["raw.csv"]}, inputs={})
        # Act
        adjacency, _ = resolve_file_dag(["raw"], db=db)
        # Assert
        assert adjacency["raw"] == []

    def test_self_read_does_not_create_self_edge(self):
        # Arrange — a session that re-reads its own output
        db = FakeDB(outputs={"s": ["f"]}, inputs={"s": ["f"]})
        # Act
        adjacency, _ = resolve_file_dag(["s"], db=db)
        # Assert
        assert adjacency["s"] == []


# EOF
