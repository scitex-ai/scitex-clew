#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ed25519 signing for source/exception manifests (the ``clew sign`` trust layer).

A manifest is signed over its CANONICAL form — pretty-printed JSON of the
manifest MINUS its ``signature`` field, with ``sort_keys=True`` and
``ensure_ascii=False`` and no trailing newline. Signing this exact form means
the on-disk pretty-JSON (minus its signature) IS the signed byte string, so the
human reviews exactly what is attested. Any byte change to the manifest breaks
the signature, and re-signing needs the private key — which the human holds
off-tree, never the agent/solver. So an unsigned or edited manifest cannot be
forged: "without the key it can't be run/edited".

python-cryptography is an OPTIONAL dependency (the ``[all]`` extra); the bare
zero-dependency install can neither sign nor verify (nor ENFORCE signing, which
is correct — enforcement is opt-in, activated by a committed ``signing.pub``).
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional, Tuple

_CRYPTO_HINT = (
    "clew signing requires the 'cryptography' package — install it with "
    "`pip install scitex-clew[all]` (or `uv pip install scitex-clew[all]`)."
)


def _load_crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
    except ImportError as exc:  # pragma: no cover - exercised only without [all]
        raise RuntimeError(_CRYPTO_HINT) from exc
    return serialization, Ed25519PrivateKey


def canonical_bytes(manifest: Dict[str, Any]) -> bytes:
    """The FROZEN signable form: pretty-JSON of the manifest MINUS ``signature``.

    ``json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)`` with no
    trailing newline. Deterministic (``sort_keys``) and stable across producers,
    so the same manifest content always yields the same signed bytes.
    """
    payload = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(
        payload, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")


def generate_keypair() -> Tuple[bytes, bytes]:
    """Generate a fresh Ed25519 keypair; return ``(private_pem, public_pem)``.

    The private PEM is PKCS8/unencrypted (the human protects it with filesystem
    permissions and by keeping it off-tree); the public PEM is what gets
    committed as ``signing.pub``.
    """
    serialization, Ed25519PrivateKey = _load_crypto()
    private = Ed25519PrivateKey.generate()
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def sign_manifest(manifest: Dict[str, Any], private_pem: bytes) -> Dict[str, str]:
    """Sign the manifest's canonical bytes; return the ``{"algo","sig"}`` dict.

    The caller assigns the result to ``manifest["signature"]`` and writes the
    manifest back (in the same canonical serialization).
    """
    serialization, _ = _load_crypto()
    private = serialization.load_pem_private_key(private_pem, password=None)
    sig = private.sign(canonical_bytes(manifest))
    return {"algo": "ed25519", "sig": base64.b64encode(sig).decode("ascii")}


def verify_manifest(manifest: Dict[str, Any], public_pem: bytes) -> bool:
    """Return ``True`` iff ``manifest['signature']`` verifies against ``public_pem``.

    Fails safe: returns ``False`` on a missing/malformed signature, a bad key, or
    any verification error (an unverifiable manifest is 'not verified'). NEVER
    raises for a verification failure — only :func:`canonical_bytes` /
    dependency loading may raise.
    """
    serialization, _ = _load_crypto()
    signature = manifest.get("signature")
    if not isinstance(signature, dict) or signature.get("algo") != "ed25519":
        return False
    sig_b64 = signature.get("sig")
    if not isinstance(sig_b64, str):
        return False
    try:
        public = serialization.load_pem_public_key(public_pem)
        public.verify(base64.b64decode(sig_b64), canonical_bytes(manifest))
        return True
    except Exception:
        return False


def is_signed(manifest: Dict[str, Any]) -> bool:
    """True iff the manifest carries a well-formed ed25519 signature block.

    Does NOT verify it — just checks the shape (used to decide whether to
    consult a signature at all).
    """
    sig = manifest.get("signature")
    return (
        isinstance(sig, dict)
        and sig.get("algo") == "ed25519"
        and isinstance(sig.get("sig"), str)
    )
