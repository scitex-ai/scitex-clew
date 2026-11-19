"""A claim's precision in the bundle, and recomputing its value with clew's rule.

The tolerance is clew's own claim-check rule (``_claim._locator.compare``):
declared ``abs_tol``/``rel_tol`` verbatim, else implied by the written
precision. Real JSON source files; no mocks.
"""

from __future__ import annotations

import json

import pytest
from scitex_clew._exchange._precision import precision_of, recompute_claim


@pytest.mark.parametrize(
    ("stated", "tolerance", "expected"),
    [
        (0.91, None, {"basis": "implied", "abs_tol": 0.005, "rel_tol": 0.0}),
        (3, None, {"basis": "implied", "abs_tol": 0.5, "rel_tol": 0.0}),
        ("p = 0.003", None, {"basis": "implied", "abs_tol": 0.0005, "rel_tol": 0.0}),
        ("AUC", None, {"basis": "exact", "abs_tol": None, "rel_tol": None}),
        (
            0.91,
            {"abs_tol": 0.1},
            {"basis": "declared", "abs_tol": 0.1, "rel_tol": None},
        ),
    ],
)
def test_claim_level_precision(stated, tolerance, expected):
    # Arrange
    keys = None
    # Act
    got = precision_of(stated, tolerance, keys)
    # Assert
    assert got == pytest.approx(expected)


def test_locator_tolerance_is_the_fields_precision():
    # Arrange
    keys = {".": {"pointer": "/auc", "rel_tol": 0.01}}
    # Act
    got = precision_of(0.91, None, keys)["fields"]["."]
    # Assert
    assert got == {"basis": "declared", "abs_tol": None, "rel_tol": 0.01}


def _claim(stated, pointer="/auc", precision=None):
    return {
        "claim_id": "c",
        "stated_value": stated,
        "precision": precision or precision_of(stated, None, None),
        "source": {"file": "results.json", "locator": {".": {"pointer": pointer}}},
    }


@pytest.fixture
def source_root(tmp_path):
    (tmp_path / "results.json").write_text(json.dumps({"auc": 0.9134}))
    return tmp_path


def test_value_within_written_precision_is_reproduced(source_root):
    # Arrange
    claim = _claim(0.91)
    # Act
    got = recompute_claim(claim, source_root)
    # Assert
    assert (got["status"], got["recomputed_value"]) == ("reproduced", 0.9134)


def test_value_outside_written_precision_differs(source_root):
    # Arrange
    claim = _claim(0.92)
    # Act
    got = recompute_claim(claim, source_root)
    # Assert
    assert got["status"] == "differs"


def test_declared_tolerance_is_applied(source_root):
    # Arrange
    precision = {"basis": "declared", "abs_tol": 0.01, "rel_tol": None}
    claim = _claim(0.92, precision=precision)
    # Act
    got = recompute_claim(claim, source_root)
    # Assert
    assert got["status"] == "reproduced"


def test_unresolvable_locator_is_not_checkable(source_root):
    # Arrange
    claim = _claim(0.91, pointer="/missing")
    # Act
    got = recompute_claim(claim, source_root)
    # Assert
    assert got["status"] == "not_checkable"


def test_claim_without_locator_is_not_checkable(source_root):
    # Arrange
    claim = {
        "claim_id": "c",
        "stated_value": 1,
        "source": {"file": None, "locator": None},
    }
    # Act
    got = recompute_claim(claim, source_root)
    # Assert
    assert got["status"] == "not_checkable"


# EOF
