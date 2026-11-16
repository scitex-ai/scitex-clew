#!/usr/bin/env python3
"""Locator normalisation and comparison (:mod:`scitex_clew._claim._locator`).

Pure functions — no store needed.
"""

from __future__ import annotations

import pytest
from scitex_clew._claim._locator import (
    SourceLocatorError,
    compare,
    implied_abs_tol,
    normalize_locator,
)


class TestLocator:
    def test_per_locator_tolerance_overrides_claim_level(self):
        # Arrange
        locator = {"pointer": "/x", "abs_tol": 0.0}
        # Act
        ok, _ = compare("0.81", 0.8123, locator, {"abs_tol": 0.1})
        # Assert
        assert not ok

    def test_implied_tolerance_is_half_the_last_written_place(self):
        # Arrange
        written = "4.23"
        # Act
        tol = implied_abs_tol(written)
        # Assert
        assert tol == pytest.approx(0.005)

    def test_malformed_locator_is_rejected(self):
        # Arrange
        bad = {"pointer": "no-leading-slash"}
        # Act
        call = lambda: normalize_locator(bad)
        # Assert
        with pytest.raises(SourceLocatorError):
            call()


# EOF
