#!/usr/bin/env python3
"""Numbers as a manuscript writes them (:mod:`scitex_clew._claim._numbers`)."""

from __future__ import annotations

import pytest
from scitex_clew._claim._numbers import numeric_leaves, parse_numbers, text_agrees_with


@pytest.mark.parametrize(
    "text, expected",
    [
        ("0.91", [(0.91, 0.005)]),
        ("p = 0.003", [(0.003, 0.0005)]),
        ("12,345", [(12345.0, 0.5)]),
        ("1.2e-3", [(0.0012, 0.00005)]),
        ("1.2 × 10^-3", [(0.0012, 0.00005)]),
        ("1.2x10^-3", [(0.0012, 0.00005)]),
        ("$1.2 \\times 10^{-3}$", [(0.0012, 0.00005)]),
        ("p < 10⁻³", [(0.001, 0.0005)]),
        ("−0.5", [(-0.5, 0.05)]),
        ("S01", []),
    ],
)
def test_parse_value_and_implied_precision(text, expected):
    # Arrange
    want = [pytest.approx(e) for e in expected]
    # Act
    got = [(t.value, t.implied_tol) for t in parse_numbers(text)]
    # Assert
    assert got == want


def test_percent_reads_as_percent_and_fraction():
    # Arrange
    text = "45.3\\%"
    # Act
    (tok,) = parse_numbers(text)
    # Assert
    assert tok.candidates() == [
        pytest.approx((45.3, 0.05)),
        pytest.approx((0.453, 0.0005)),
    ]


def test_number_after_pm_is_an_uncertainty():
    # Arrange
    text = "0.91 ± 0.02"
    # Act
    toks = parse_numbers(text)
    # Assert
    assert [t.uncertainty for t in toks] == [False, True]


def test_range_hyphen_is_not_a_sign():
    # Arrange
    text = "1-2"
    # Act
    got = [t.value for t in parse_numbers(text)]
    # Assert
    assert got == [1.0, 2.0]


def test_uncertainty_never_matches_the_value():
    # Arrange
    text = "0.91 ± 0.02"
    # Act
    hit = text_agrees_with(text, 0.02)
    # Assert
    assert hit is None


def test_declared_tolerance_overrides_written_precision():
    # Arrange
    declared = {"abs_tol": 0.001}
    # Act
    hit = text_agrees_with("0.3", 0.27, declared)
    # Assert
    assert hit is None


def test_numeric_leaves_keep_registered_type():
    # Arrange
    value = {"auc": 0.91, "n": 120, "ok": True, "name": "x"}
    # Act
    leaves = numeric_leaves(value)
    # Assert
    assert leaves == [("/auc", 0.91), ("/n", 120)]


# EOF
