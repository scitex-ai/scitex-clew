"""Ed25519 signing of evidence bundles through the pluggable Signer/Verifier API.

Real keys (python-cryptography), real files; no mocks.
"""

from __future__ import annotations

import base64
import stat

import pytest
from scitex_clew._exchange import (
    Signer,
    Verifier,
    generate_private_key_file,
    key_id_of,
    load_signer,
    register_verifier,
    sign_document,
    verify_document,
)
from scitex_clew._exchange._signing import Ed25519Verifier

DOC = {"schema": "scitex-clew.evidence-bundle", "runs": [], "claims": [{"v": 0.91}]}


@pytest.fixture
def signer(tmp_path):
    return generate_private_key_file(tmp_path / "k.pem")


def test_key_file_is_private_to_its_owner(tmp_path):
    # Arrange
    path = tmp_path / "k.pem"
    # Act
    generate_private_key_file(path)
    # Assert
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_existing_key_file_is_never_overwritten(tmp_path):
    # Arrange
    path = tmp_path / "k.pem"
    generate_private_key_file(path)

    # Act
    def regenerate():
        generate_private_key_file(path)

    # Assert
    with pytest.raises(FileExistsError):
        regenerate()


def test_loaded_signer_has_the_generated_key_id(tmp_path):
    # Arrange
    made = generate_private_key_file(tmp_path / "k.pem")
    # Act
    loaded = load_signer(tmp_path / "k.pem")
    # Assert
    assert loaded.key_id == made.key_id


def test_key_id_is_sha256_prefix_of_raw_public_key(signer):
    # Arrange
    import hashlib

    expected = hashlib.sha256(signer.public_key).hexdigest()[:16]
    # Act
    key_id = key_id_of(signer.public_key)
    # Assert
    assert key_id == expected


def test_ed25519_signer_satisfies_the_signer_protocol(signer):
    # Arrange
    candidate = signer
    # Act
    ok = isinstance(candidate, Signer)
    # Assert
    assert ok


def test_ed25519_verifier_satisfies_the_verifier_protocol():
    # Arrange
    candidate = Ed25519Verifier()
    # Act
    ok = isinstance(candidate, Verifier)
    # Assert
    assert ok


def test_signature_block_carries_alg_key_and_raw_public_key(signer):
    # Arrange
    signed = sign_document(DOC, signer)
    # Act
    block = signed["signature"]
    # Assert
    assert (block["alg"], block["key_id"], base64.b64decode(block["public_key"])) == (
        "ed25519",
        signer.key_id,
        signer.public_key,
    )


def test_signed_document_verifies(signer):
    # Arrange
    signed = sign_document(DOC, signer)
    # Act
    result = verify_document(signed)
    # Assert
    assert result["valid"] is True


def test_changed_content_breaks_the_signature(signer):
    # Arrange
    signed = sign_document(DOC, signer)
    signed["claims"] = [{"v": 0.92}]
    # Act
    result = verify_document(signed)
    # Assert
    assert result["valid"] is False


def test_changed_signature_value_does_not_verify(signer):
    # Arrange
    signed = sign_document(DOC, signer)
    raw = bytearray(base64.b64decode(signed["signature"]["value"]))
    raw[0] ^= 0xFF
    signed["signature"]["value"] = base64.b64encode(bytes(raw)).decode()
    # Act
    result = verify_document(signed)
    # Assert
    assert result["valid"] is False


def test_key_id_not_matching_public_key_is_rejected(signer):
    # Arrange
    signed = sign_document(DOC, signer)
    signed["signature"]["key_id"] = "0" * 16
    # Act
    result = verify_document(signed)
    # Assert
    assert result["reason"] == "key_id does not match the public key"


def test_signature_by_unexpected_key_is_rejected(signer):
    # Arrange
    signed = sign_document(DOC, signer)
    # Act
    result = verify_document(signed, expected_key_id="f" * 16)
    # Assert
    assert result["valid"] is False


def test_unsigned_document_reports_signed_false():
    # Arrange
    unsigned = dict(DOC)
    # Act
    result = verify_document(unsigned)
    # Assert
    assert (result["signed"], result["valid"]) == (False, None)


def test_unknown_algorithm_is_not_valid(signer):
    # Arrange
    signed = sign_document(DOC, signer)
    signed["signature"]["alg"] = "rot13"
    # Act
    result = verify_document(signed)
    # Assert
    assert result["reason"] == "unsupported signature algorithm 'rot13'"


class _AcceptEverything:
    """A real (if useless) Verifier plugin, to show the registry is pluggable."""

    alg = "test-accept-all"

    def verify(self, public_key: bytes, data: bytes, signature: bytes) -> bool:
        return True


def test_registered_verifier_handles_its_algorithm(signer):
    # Arrange
    register_verifier(_AcceptEverything())
    signed = sign_document(DOC, signer)
    signed["signature"]["alg"] = "test-accept-all"
    # Act
    result = verify_document(signed)
    # Assert
    assert result["valid"] is True


# EOF
