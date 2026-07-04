#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the Ed25519 manifest signing core (scitex_clew._sources._signing).

Real cryptography (no mocks) — a real keypair, real sign/verify. Skipped when
the optional 'cryptography' dependency (the [all] extra) is absent.
"""

import json

import pytest

pytest.importorskip("cryptography")

from scitex_clew._sources._signing import (  # noqa: E402
    canonical_bytes,
    generate_keypair,
    is_signed,
    sign_manifest,
    verify_manifest,
)


def _manifest():
    return {
        "schema": "sources-1.0",
        "sources": [{"path": "data/cars2.csv", "sha256": "abc123"}],
        "signature": None,
    }


def test_canonical_bytes_is_frozen_form():
    # Arrange
    manifest = _manifest()
    # Act
    result = canonical_bytes(manifest)
    # Assert — pretty-JSON, sort_keys, ensure_ascii, MINUS signature, no newline.
    expected = json.dumps(
        {"schema": manifest["schema"], "sources": manifest["sources"]},
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    assert result == expected


def test_canonical_bytes_ignores_signature_value():
    # Arrange
    unsigned = _manifest()
    signed = {**unsigned, "signature": {"algo": "ed25519", "sig": "ZZZZ"}}
    # Act
    same = canonical_bytes(unsigned) == canonical_bytes(signed)
    # Assert — the signature field must not affect the signed bytes.
    assert same is True


def test_sign_then_verify_roundtrip_returns_true():
    # Arrange
    private_pem, public_pem = generate_keypair()
    manifest = _manifest()
    # Act
    manifest["signature"] = sign_manifest(manifest, private_pem)
    # Assert
    assert verify_manifest(manifest, public_pem) is True


def test_verify_fails_when_manifest_tampered():
    # Arrange
    private_pem, public_pem = generate_keypair()
    manifest = _manifest()
    manifest["signature"] = sign_manifest(manifest, private_pem)
    manifest["sources"][0]["sha256"] = "tampered"
    # Act
    ok = verify_manifest(manifest, public_pem)
    # Assert
    assert ok is False


def test_verify_fails_with_wrong_public_key():
    # Arrange
    private_pem, _ = generate_keypair()
    _, other_public_pem = generate_keypair()
    manifest = _manifest()
    manifest["signature"] = sign_manifest(manifest, private_pem)
    # Act
    ok = verify_manifest(manifest, other_public_pem)
    # Assert
    assert ok is False


def test_verify_fails_when_signature_missing():
    # Arrange
    _, public_pem = generate_keypair()
    manifest = _manifest()  # signature is None
    # Act
    ok = verify_manifest(manifest, public_pem)
    # Assert
    assert ok is False


def test_is_signed_true_for_signed_manifest():
    # Arrange
    private_pem, _ = generate_keypair()
    manifest = _manifest()
    manifest["signature"] = sign_manifest(manifest, private_pem)
    # Act
    signed = is_signed(manifest)
    # Assert
    assert signed is True


def test_is_signed_false_for_unsigned_manifest():
    # Arrange
    manifest = _manifest()
    # Act
    signed = is_signed(manifest)
    # Assert
    assert signed is False
