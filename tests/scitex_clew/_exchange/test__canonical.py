"""The frozen signable byte form of a bundle."""

from __future__ import annotations

import json

from scitex_clew._exchange import canonical_bytes


def test_canonical_bytes_are_the_contract_serialisation():
    # Arrange
    doc = {"b": "é", "a": [1, 2.5], "signature": {"value": "x"}}
    expected = json.dumps(
        {"a": [1, 2.5], "b": "é"}, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")  # fmt: skip
    # Act
    got = canonical_bytes(doc)
    # Assert
    assert got == expected


def test_key_order_does_not_change_the_bytes():
    # Arrange
    a, b = {"x": 1, "y": {"p": 1, "q": 2}}, {"y": {"q": 2, "p": 1}, "x": 1}
    # Act
    same = canonical_bytes(a) == canonical_bytes(b)
    # Assert
    assert same


# EOF
