"""Exporting a REAL project's evidence bundle from the store.

The project (two real ``@session`` runs, three registered claims) is built
once for the package (see ``conftest.py``); the bundle is exported and signed
from the test's own PostgreSQL schema. No mocks.
"""

from __future__ import annotations

import json

import pytest
from scitex_clew._exchange import load_bundle, schema_errors


@pytest.fixture(scope="module")
def doc(signed_bundle):
    return load_bundle(signed_bundle)[0]


@pytest.fixture(scope="module")
def runs_by_script(doc):
    return {r["script"]: r for r in doc["runs"]}


def test_bundle_is_written_where_the_contract_says(signed_bundle, bundle_project):
    # Arrange
    expected = bundle_project / ".scitex" / "clew" / "evidence-bundle.json"
    # Act
    got = signed_bundle
    # Assert
    assert got == expected


def test_bundle_validates_against_its_shipped_schema(doc):
    # Arrange
    name = "evidence-bundle"
    # Act
    errors = schema_errors(doc, name)
    # Assert
    assert errors == []


def test_bundle_names_no_absolute_host_path(signed_bundle, bundle_project):
    # Arrange
    text = signed_bundle.read_text(encoding="utf-8")
    # Act
    leaked = str(bundle_project) in text or str(bundle_project.parent) in text
    # Assert
    assert not leaked


def test_bundle_holds_both_recorded_runs(runs_by_script):
    # Arrange
    expected = {"scripts/stats.py", "scripts/report.py"}
    # Act
    scripts = set(runs_by_script)
    # Assert
    assert scripts == expected


def test_run_files_are_repo_relative_with_sha256(runs_by_script):
    # Arrange
    run = runs_by_script["scripts/stats.py"]
    # Act
    files = (sorted(run["inputs"]), sorted(run["outputs"]))
    # Assert
    assert files == (["data/in.csv"], ["scripts/stats_out/results.json"])


def test_run_replays_from_repo_relative_cwd_and_argv(runs_by_script):
    # Arrange
    run = runs_by_script["scripts/report.py"]
    # Act
    replay = (run["cwd"], run["argv"], run["interpreter"]["name"])
    # Assert
    assert replay == (".", ["scripts/report.py"], "python")


def test_edge_links_the_producer_to_its_consumer(doc, runs_by_script):
    # Arrange
    parent = runs_by_script["scripts/stats.py"]["run_id"]
    child = runs_by_script["scripts/report.py"]["run_id"]
    # Act
    edges = doc["edges"]
    # Assert
    assert edges == [{"parent": parent, "child": child}]


def test_claims_carry_the_four_state_vocabulary(doc):
    # Arrange
    claims = doc["claims"]
    # Act
    states = {c["claim_id"]: c["state"] for c in claims}
    # Assert
    assert states == {
        "n_rows": "supported",
        "mean_x": "supported",
        "double": "supported",
    }


def test_claim_precision_is_implied_by_the_written_value(doc):
    # Arrange
    claim = next(c for c in doc["claims"] if c["claim_id"] == "mean_x")
    # Act
    precision = {k: claim["precision"][k] for k in ("basis", "abs_tol")}
    # Assert
    assert precision == {"basis": "implied", "abs_tol": pytest.approx(0.05)}


def test_claim_names_its_producing_run(doc, runs_by_script):
    # Arrange
    claim = next(c for c in doc["claims"] if c["claim_id"] == "double")
    # Act
    producers = claim["producing_runs"]
    # Assert
    assert producers == [runs_by_script["scripts/report.py"]["run_id"]]


def test_claim_carries_its_minimal_evidence_graph(doc):
    # Arrange
    claim = next(c for c in doc["claims"] if c["claim_id"] == "n_rows")
    # Act
    kinds = sorted({n["kind"] for n in claim["graph"]["nodes"]})
    # Assert
    assert kinds == ["claim", "input", "output", "process"]


def test_bundle_is_signed_with_the_given_key(doc, signing_key):
    # Arrange
    from scitex_clew._exchange import load_signer

    expected = load_signer(signing_key).key_id
    # Act
    key_id = doc["signature"]["key_id"]
    # Assert
    assert key_id == expected


def test_written_json_is_key_sorted_for_stable_diffs(signed_bundle):
    # Arrange
    text = signed_bundle.read_text(encoding="utf-8")
    # Act
    resorted = json.dumps(
        json.loads(text), indent=2, sort_keys=True, ensure_ascii=False
    )
    # Assert
    assert text == resorted + "\n"


# EOF
