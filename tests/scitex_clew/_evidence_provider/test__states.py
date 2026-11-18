"""clew per-claim outcome -> contract state, reason and provider_status."""

from __future__ import annotations

import pytest
from scitex_clew._evidence_provider import OUTCOME_STATES, classify_outcome

#: The full outcome table: name -> (state, reason, code).
OUTCOME_TABLE = {
    "OK": ("supported", "value and sources check out against the recorded run", 0),
    "VALUE_MISMATCH": (
        "not_supported",
        "value in source differs from the stated value",
        21,
    ),
    "HASH_MISMATCH": (
        "not_supported",
        "source changed after the claim was registered",
        12,
    ),
    "STALE_LINEAGE": (
        "not_supported",
        "source changed after the run (an input, script or run changed)",
        18,
    ),
    "EXTERNAL_MISSING": (
        "not_supported",
        "an input from outside the project is absent here, so the run cannot "
        "be checked",
        22,
    ),
    "ENV_NOT_REPRODUCIBLE": (
        "not_supported",
        "the recorded software environment cannot be reproduced from the record",
        23,
    ),
    "SOURCE_MISSING": ("not_supported", "the source file is missing", 11),
    "VERIFY_ERROR": ("not_supported", "verification could not complete", 19),
    "UNSOURCED": ("not_supported", "the lineage reaches no registered source", 17),
    "VALUE_UNCHECKED": ("not_checkable", "no locator, value not checked", 24),
    "NO_LINEAGE": (
        "no_evidence_graph",
        "no evidence graph: the source has no recorded computation behind it",
        13,
    ),
    "UNVERIFIED": (
        "no_evidence_graph",
        "no evidence graph: no source is linked to the claim",
        10,
    ),
}


@pytest.mark.parametrize("outcome", sorted(OUTCOME_TABLE))
def test_outcome_maps_to_state_reason_and_clew_code(outcome):
    # Arrange
    state, reason, code = OUTCOME_TABLE[outcome]
    # Act
    result = classify_outcome(outcome, [])
    # Assert
    assert result == (state, reason, {"name": outcome, "code": code})


def test_value_mismatch_reason_is_read_from_clews_detail():
    # Arrange
    details = ["value[.]: claimed 3 vs source 2"]
    # Act
    _state, reason, _status = classify_outcome("VALUE_MISMATCH", details)
    # Assert
    assert reason == "value in source differs: 2 in source vs 3 stated"


def test_only_ok_maps_to_supported():
    # Arrange
    table = OUTCOME_STATES
    # Act
    supported = [name for name, (state, _) in table.items() if state == "supported"]
    # Assert
    assert supported == ["OK"]


def test_unknown_outcome_is_never_supported():
    # Arrange
    outcome = "SOMETHING_NEW"
    # Act
    result = classify_outcome(outcome)
    # Assert
    assert result == (
        "not_supported",
        "clew reported SOMETHING_NEW",
        {"name": "SOMETHING_NEW", "code": None},
    )


def test_value_mismatch_without_parsable_detail_uses_the_generic_reason():
    # Arrange
    details = ["unrelated detail"]
    # Act
    _state, reason, _status = classify_outcome("VALUE_MISMATCH", details)
    # Assert
    assert reason == "value in source differs from the stated value"
