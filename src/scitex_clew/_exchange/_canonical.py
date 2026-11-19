#!/usr/bin/env python3
"""Canonical bytes and file digests of the evidence-bundle exchange format.

The signed byte string is FROZEN by the format (1.x)::

    json.dumps(doc_without_signature, sort_keys=True,
               separators=(",", ":"), ensure_ascii=False).encode("utf-8")

``doc_without_signature`` is the whole document with its top-level
``signature`` key removed. Any producer or consumer, in any language, that
serialises the same JSON value this way gets the same bytes.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = ["SIGNATURE_KEY", "canonical_bytes", "sha256_bytes", "sha256_file"]

#: The one top-level key excluded from the signed bytes.
SIGNATURE_KEY = "signature"


def canonical_bytes(document: Mapping[str, Any]) -> bytes:
    """The signable form of ``document``: canonical JSON minus ``signature``."""
    payload = {k: v for k, v in document.items() if k != SIGNATURE_KEY}
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hex SHA-256 of a file's bytes, streamed."""
    hasher = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            hasher.update(chunk)
    return hasher.hexdigest()


# EOF
