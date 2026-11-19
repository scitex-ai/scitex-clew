"""Failing graph nodes (contract 1.1.0 ``node.failure``) on a REAL project.

The marks come from clew's own verification of each claim: the planted
faults of ``_clew_project`` (a value that differs, a hand-written source
edited after registration, a session input changed after its run) must show
up on exactly the nodes where they were planted, and nowhere else. No mocks:
real sessions, a real PostgreSQL store (see ``conftest.py``).
"""

from __future__ import annotations

import pytest
from scitex_clew._evidence_provider import EvidenceEntry

from ._clew_project import EXPECTED_OUTCOMES

#: claim_id -> {node label: failure kind} the planted faults must produce.
EXPECTED_FAILURES = {
    "auc": {},
    "n_rows": {"results/results.json": "mismatched"},
    "accuracy": {},
    "calib": {},
    "budget": {"paper/edited.json": "changed"},
    "cohort2": {"data/input2.csv": "changed"},
}


def _failing(graph: dict) -> dict[str, str]:
    return {
        n["label"]: n["failure"]["kind"] for n in graph["nodes"] if n.get("failure")
    }


def _failure_of(graph: dict, label: str) -> dict:
    return next(n["failure"] for n in graph["nodes"] if n["label"] == label)


def test_expected_failures_cover_every_registered_claim():
    # Arrange
    expected = set(EXPECTED_OUTCOMES)
    # Act
    covered = set(EXPECTED_FAILURES)
    # Assert
    assert covered == expected


@pytest.mark.parametrize("claim_id", sorted(EXPECTED_FAILURES))
def test_failing_nodes_are_exactly_where_the_fault_was_planted(by_id, claim_id):
    # Arrange
    graph = by_id[claim_id]["graph"]
    # Act
    failing = _failing(graph)
    # Assert
    assert failing == EXPECTED_FAILURES[claim_id]


def test_value_mismatch_detail_names_both_values(by_id):
    # Arrange
    graph = by_id["n_rows"]["graph"]
    # Act
    failure = _failure_of(graph, "results/results.json")
    # Assert
    assert failure == {"kind": "mismatched", "detail": "2 in source vs 3 stated"}


def test_hash_mismatch_detail_says_changed_since_registration(by_id):
    # Arrange
    graph = by_id["budget"]["graph"]
    # Act
    failure = _failure_of(graph, "paper/edited.json")
    # Assert
    assert failure["detail"] == (
        "differs from the hash recorded when the claim was registered"
    )


def test_stale_lineage_detail_names_the_run_that_recorded_the_input(by_id):
    # Arrange
    graph = by_id["cohort2"]["graph"]
    (run,) = [n["label"] for n in graph["nodes"] if n["kind"] == "process"]
    # Act
    failure = _failure_of(graph, "data/input2.csv")
    # Assert
    assert failure["detail"] == f"input differs from what run {run} recorded"


def test_stale_lineage_does_not_blame_the_unchanged_output_or_run(by_id):
    # Arrange
    graph = by_id["cohort2"]["graph"]
    # Act
    blamed_kinds = {n["kind"] for n in graph["nodes"] if n.get("failure")}
    # Assert
    assert blamed_kinds == {"input"}


def test_on_demand_graph_carries_the_same_failing_nodes(clew_project, by_id):
    # Arrange
    adapter = EvidenceEntry.adapter
    # Act
    graphs = {
        cid: adapter.evidence_graph(str(clew_project), cid, {})
        for cid in ("n_rows", "budget", "cohort2")
    }
    # Assert
    assert graphs == {cid: by_id[cid]["graph"] for cid in graphs}
