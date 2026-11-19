#!/usr/bin/env python3
"""Pluggable signing for evidence bundles: a Signer/Verifier interface + Ed25519.

The format names an algorithm (``signature.alg``) and carries the raw public
key, so a consumer verifies a bundle with nothing but the bundle. WHICH keys a
consumer trusts is policy, and production key policy is not decided here:
keys are plain files (:func:`generate_private_key_file`), and
``verify_document(..., expected_key_id=...)`` pins one when the caller has
decided.

Signature block (format 1.x)::

    {"alg": "ed25519",
     "key_id": sha256(raw public key).hexdigest()[:16],
     "public_key": base64(raw 32-byte public key),
     "value": base64(signature over canonical_bytes(document))}

Ed25519 needs python-cryptography, an OPTIONAL dependency (the ``[sign]``
extra): clew core stays stdlib-only. It is imported lazily, and a missing
package fails loudly with the install command.
"""

from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ._canonical import SIGNATURE_KEY, canonical_bytes, sha256_bytes

__all__ = [
    "CRYPTO_HINT",
    "ED25519",
    "Ed25519Signer",
    "Ed25519Verifier",
    "Signer",
    "SigningUnavailable",
    "Verifier",
    "generate_private_key_file",
    "key_id_of",
    "load_signer",
    "register_verifier",
    "sign_document",
    "verify_document",
]

ED25519 = "ed25519"

CRYPTO_HINT = (
    "evidence-bundle signing needs the 'cryptography' package: install it with "
    "`pip install 'scitex-clew[sign]'` (or `uv pip install 'scitex-clew[sign]'`)."
)


class SigningUnavailable(RuntimeError):
    """The signing backend for an algorithm is not installed."""


@runtime_checkable
class Signer(Protocol):
    """Anything that can sign bytes under one key."""

    alg: str
    key_id: str
    public_key: bytes  # the raw public key the signature verifies under

    def sign(self, data: bytes) -> bytes: ...


@runtime_checkable
class Verifier(Protocol):
    """Verifies signatures of one algorithm."""

    alg: str

    def verify(self, public_key: bytes, data: bytes, signature: bytes) -> bool: ...


def key_id_of(public_key: bytes) -> str:
    """The format's key id: first 16 hex chars of sha256(raw public key)."""
    return sha256_bytes(public_key)[:16]


def _crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:
        raise SigningUnavailable(CRYPTO_HINT) from exc
    return serialization, ed25519


def _raw_public(public_key_obj) -> bytes:
    serialization, _ = _crypto()
    return public_key_obj.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )


@dataclass
class Ed25519Signer:
    """Ed25519 signer over a private key object from python-cryptography."""

    _private: Any
    alg: str = ED25519

    @property
    def public_key(self) -> bytes:
        return _raw_public(self._private.public_key())

    @property
    def key_id(self) -> str:
        return key_id_of(self.public_key)

    def sign(self, data: bytes) -> bytes:
        return self._private.sign(data)


class Ed25519Verifier:
    """Ed25519 verification of a raw 32-byte public key."""

    alg = ED25519

    def verify(self, public_key: bytes, data: bytes, signature: bytes) -> bool:
        _, ed25519 = _crypto()
        try:
            key = ed25519.Ed25519PublicKey.from_public_bytes(public_key)
            key.verify(signature, data)
        except Exception:  # noqa: BLE001 - any failure is "does not verify"
            return False
        return True


_VERIFIERS: dict[str, Verifier] = {ED25519: Ed25519Verifier()}


def register_verifier(verifier: Verifier) -> None:
    """Make ``verifier`` the one used for signatures with its ``alg``."""
    _VERIFIERS[verifier.alg] = verifier


def generate_private_key_file(path: str | Path) -> Ed25519Signer:
    """Write a NEW Ed25519 private key (PKCS8 PEM, mode 0600) to ``path``.

    Refuses to overwrite an existing file (``FileExistsError``): replacing a
    key silently orphans every bundle signed with it.
    """
    serialization, ed25519 = _crypto()
    private = ed25519.Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    os.chmod(path, 0o600)  # the umask must not widen it
    return Ed25519Signer(private)


def load_signer(path: str | Path) -> Ed25519Signer:
    """The signer for an Ed25519 private key file written by :func:`generate_private_key_file`."""
    serialization, ed25519 = _crypto()
    private = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(private, ed25519.Ed25519PrivateKey):
        raise TypeError(f"{path} is not an Ed25519 private key")
    return Ed25519Signer(private)


def sign_document(document: Mapping[str, Any], signer: Signer) -> dict:
    """A copy of ``document`` carrying ``signer``'s signature block."""
    signature = signer.sign(canonical_bytes(document))
    out = {k: v for k, v in document.items() if k != SIGNATURE_KEY}
    out[SIGNATURE_KEY] = {
        "alg": signer.alg,
        "key_id": signer.key_id,
        "public_key": base64.b64encode(signer.public_key).decode("ascii"),
        "value": base64.b64encode(signature).decode("ascii"),
    }
    return out


def _b64(text: Any) -> bytes | None:
    if not isinstance(text, str):
        return None
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None


def verify_document(
    document: Mapping[str, Any], expected_key_id: str | None = None
) -> dict:
    """Check ``document``'s signature block; never raises for a bad signature.

    Returns ``{"signed", "valid", "alg", "key_id", "reason"}``. ``valid`` is
    ``None`` when the document is unsigned. Raises :class:`SigningUnavailable`
    only when the algorithm's backend is not installed (an unverifiable
    signature must not read as an invalid one, nor as a valid one).
    """
    block = document.get(SIGNATURE_KEY)
    if block is None:
        return {"signed": False, "valid": None, "alg": None, "key_id": None,
                "reason": "the bundle is not signed"}  # fmt: skip
    result = {"signed": True, "valid": False, "alg": None, "key_id": None}
    if not isinstance(block, Mapping):
        return {**result, "reason": "signature is not an object"}
    alg, key_id = block.get("alg"), block.get("key_id")
    result.update(alg=alg, key_id=key_id)
    verifier = _VERIFIERS.get(alg)
    if verifier is None:
        return {**result, "reason": f"unsupported signature algorithm {alg!r}"}
    public_key, value = _b64(block.get("public_key")), _b64(block.get("value"))
    if public_key is None or value is None:
        return {**result, "reason": "public_key / value is not valid base64"}
    if key_id != key_id_of(public_key):
        return {**result, "reason": "key_id does not match the public key"}
    if expected_key_id is not None and key_id != expected_key_id:
        return {
            **result,
            "reason": f"signed by key {key_id}, expected {expected_key_id}",
        }
    if not verifier.verify(public_key, canonical_bytes(document), value):
        return {**result, "reason": "signature does not verify: the bundle "
                "was changed after signing, or signed by another key"}  # fmt: skip
    return {**result, "valid": True, "reason": "signature verifies"}


# EOF
