"""The evidence report on a REAL clew project, validated against the contract.

The report is validated against the vendored, version-pinned contract schema
(``scitex-live-paper.evidence-report`` 1.0.0) with jsonschema; scitex-live-paper
itself is never imported. No mocks: real sessions, a real PostgreSQL store
(one schema and one built project per module, see ``conftest.py``).
"""

from __future__ import annotations

import jsonschema
import pytest
from scitex_clew._evidence_provider import (
    SCHEMA_ID,
    SCHEMA_VERSION,
    EvidenceEntry,
    load_schema,
)

from ._clew_project import EXPECTED_OUTCOMES, EXPECTED_REPORT


def test_report_validates_against_the_vendored_schema(report):
    # Arrange
    validator = jsonschema.Draft202012Validator(load_schema())
    # Act
    errors = [e.message for e in validator.iter_errors(report)]
    # Assert
    assert errors == []


def test_report_header_names_contract_provider_and_root(report, clew_project):
    # Arrange
    keys = ("schema", "schema_version", "project_root")
    # Act
    header = {k: report[k] for k in keys} | {"provider": report["provider"]["name"]}
    # Assert
    assert header == {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "project_root": str(clew_project),
        "provider": "clew",
    }


def test_report_holds_exactly_the_registered_claims(by_id):
    # Arrange: paper.tex line 8 is text, not a registered claim.
    expected = set(EXPECTED_OUTCOMES)
    # Act
    reported = set(by_id)
    # Assert
    assert reported == expected


@pytest.mark.parametrize("claim_id", sorted(EXPECTED_REPORT))
def test_claim_state_reason_and_provider_status(by_id, claim_id):
    # Arrange
    claim = by_id[claim_id]
    # Act
    verdict = (claim["state"], claim["reason"], claim["provider_status"])
    # Assert
    assert verdict == EXPECTED_REPORT[claim_id], claim["details"]


def test_claim_record_fields_are_relative_to_the_project(by_id):
    # Arrange
    claim = by_id["n_rows"]
    # Act
    fields = {
        k: claim[k] for k in ("location", "stated_text", "stated_value", "source")
    }
    # Assert
    assert fields == {
        "location": {"file": "paper/paper.tex", "line": 3, "label": "paper.tex:L3"},
        "stated_text": "n = 3",
        "stated_value": 3,
        "source": {
            "file": "results/results.json",
            "locator": {".": {"pointer": "/n_rows"}},
        },
    }


def test_claim_without_locator_reports_a_null_locator(by_id):
    # Arrange
    claim = by_id["accuracy"]
    # Act
    locator = claim["source"]["locator"]
    # Assert
    assert locator is None


def test_every_claim_carries_clews_details_list(by_id):
    # Arrange
    claims = by_id.values()
    # Act
    types = {type(c["details"]) for c in claims}
    # Assert
    assert types == {list}


# --- scoping, on-demand graphs, out of process -------------------------------


def test_claim_ids_scope_the_report_and_unknown_ids_are_absent(clew_project):
    # Arrange
    wanted = ["auc", "budget", "not-a-claim"]
    # Act
    report = EvidenceEntry.adapter.evidence_report(str(clew_project), wanted, {})
    # Assert
    assert [c["claim_id"] for c in report["claims"]] == ["auc", "budget"]


def test_with_graphs_false_omits_the_graph_key_and_still_validates(clew_project):
    # Arrange
    options = {"with_graphs": False}
    validator = jsonschema.Draft202012Validator(load_schema())
    # Act
    report = EvidenceEntry.adapter.evidence_report(str(clew_project), None, options)
    # Assert
    assert validator.is_valid(report) and all(
        "graph" not in c for c in report["claims"]
    )


def test_evidence_graph_on_demand_matches_the_report_graph(clew_project, by_id):
    # Arrange
    adapter = EvidenceEntry.adapter
    # Act
    graph = adapter.evidence_graph(str(clew_project), "auc", {})
    # Assert
    assert graph == by_id["auc"]["graph"]


def test_evidence_graph_of_an_unregistered_claim_raises(clew_project):
    # Arrange
    adapter = EvidenceEntry.adapter
    # Act
    call = lambda: adapter.evidence_graph(str(clew_project), "not-a-claim", {})
    # Assert
    with pytest.raises(KeyError):
        call()


def test_project_root_must_be_a_directory(tmp_path):
    # Arrange
    absent = tmp_path / "absent"
    # Act
    call = lambda: EvidenceEntry.adapter.evidence_report(str(absent), None, {})
    # Assert
    with pytest.raises(NotADirectoryError):
        call()
