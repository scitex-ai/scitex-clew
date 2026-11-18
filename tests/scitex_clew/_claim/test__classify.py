#!/usr/bin/env python3
"""Per-claim exit-code classification (``scitex_clew._claim._classify``).

Pure function over the result dict ``verify_claim`` returns; no store needed.
"""

from __future__ import annotations

import pytest

from scitex_clew._claim._classify import _classify_claim
from scitex_clew._cli._exit_codes import (
    EXTERNAL_MISSING,
    HASH_MISMATCH,
    NO_LINEAGE,
    OK,
    SOURCE_MISSING,
    STALE_LINEAGE,
    UNVERIFIED,
    VALUE_MISMATCH,
    VALUE_UNCHECKED,
    VERIFY_ERROR,
)


def _result(**fields) -> dict:
    claim = {"source_file": "/r/out.csv", "status": fields.pop("status", None)}
    return {"claim": claim, **fields}


@pytest.mark.parametrize(
    ("result", "strict", "expected"),
    [
        ({"claim": {"source_file": None}}, False, UNVERIFIED),
        (_result(status="missing"), False, SOURCE_MISSING),
        (_result(value_verified=False), False, VALUE_MISMATCH),
        (_result(status="mismatch"), False, HASH_MISMATCH),
        (_result(value_error="x"), False, VERIFY_ERROR),
        (_result(source_verified=True, chain_verified=True), True, OK),
        (
            _result(source_verified=True, chain_verified=True, value_unchecked=True),
            False,
            VALUE_UNCHECKED,
        ),
        (_result(source_verified=True, chain_status="error"), False, VERIFY_ERROR),
        (
            _result(source_verified=True, chain_status="mismatch", external_only=True),
            False,
            EXTERNAL_MISSING,
        ),
        (_result(source_verified=True, chain_status="mismatch"), False, STALE_LINEAGE),
        (_result(source_verified=True, chain_status="no_lineage"), True, NO_LINEAGE),
        (_result(source_verified=True, chain_status="no_lineage"), False, OK),
        (_result(status="registered"), False, UNVERIFIED),
    ],
)
def test_classify_claim_result_maps_to_exit_code(result, strict, expected):
    # Arrange
    # Act
    code = _classify_claim(result, strict=strict)
    # Assert
    assert code == expected


def test_verify_module_reexports_the_classifier():
    # Arrange
    from scitex_clew._claim import _verify

    # Act
    reexported = _verify._classify_claim
    # Assert
    assert reexported is _classify_claim


# EOF
