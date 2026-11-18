"""A claim's level-1 slice as a contract evidence graph, on a REAL project.

No mocks: real sessions, a real PostgreSQL store (one schema and one built
project per module, see ``conftest.py``).
"""

from __future__ import annotations

from ._clew_project import EXPECTED_REPORT, kinds, labelled_edges


def test_session_output_graph_is_input_run_output_claim(by_id):
    # Arrange
    graph = by_id["auc"]["graph"]
    run = kinds(graph)["process"]
    # Act
    edges = labelled_edges(graph)
    # Assert
    assert len(run) == 1 and edges == {
        ("data/input.csv", run[0], "input"),
        (run[0], "results/results.json", "output"),
        ("results/results.json", "auc", "supports"),
    }


def test_graph_file_nodes_carry_their_recorded_hash(by_id):
    # Arrange
    graph = by_id["auc"]["graph"]
    # Act
    files = [n for n in graph["nodes"] if n["kind"] in ("input", "output")]
    # Assert
    assert len(files) == 2 and all(len(n["hash"] or "") == 64 for n in files)


def test_graph_summary_counts_runs_and_files(by_id):
    # Arrange
    graph = by_id["auc"]["graph"]
    # Act
    summary = graph["summary"]
    # Assert
    assert summary == "level-1 slice: 1 run(s), 2 file(s)"


def test_stale_cohort_graph_keeps_its_own_lineage(by_id):
    # Arrange
    graph = by_id["cohort2"]["graph"]
    # Act
    inputs = kinds(graph)["input"]
    # Assert
    assert inputs == ["data/input2.csv"]


def test_hand_written_leaf_graph_is_file_supports_claim(by_id):
    # Arrange
    graph = by_id["calib"]["graph"]
    # Act
    shape = (kinds(graph), labelled_edges(graph))
    # Assert
    assert shape == (
        {"input": ["paper/manual.json"], "claim": ["calib"]},
        {("paper/manual.json", "calib", "supports")},
    )


def test_every_sourced_claim_has_a_graph_with_its_claim_node(by_id):
    # Arrange
    claims = by_id.values()
    # Act
    claim_nodes = {c["claim_id"]: kinds(c["graph"])["claim"] for c in claims}
    # Assert
    assert claim_nodes == {cid: [cid] for cid in EXPECTED_REPORT}
