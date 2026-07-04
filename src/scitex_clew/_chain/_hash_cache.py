#!/usr/bin/env python3
"""Per-pass hash cache for verification.

A single verification pass shares one :data:`HashCache` (resolved-path -> hash)
so a file referenced by multiple sessions is read from disk and hashed at most
once per pass — the dominant cost when outputs are large arrays/figures.

The cache is created fresh at each top-level verify entry point (never a
module-global or a mutable default argument), so a file changed between two
independent passes is always re-hashed and any tampering is detected.
"""

from __future__ import annotations

from typing import Dict

#: Maps ``str(Path(p).resolve())`` -> truncated SHA-256 hash for one pass.
HashCache = Dict[str, str]


def new_hash_cache() -> "HashCache":
    """Return a fresh, empty per-pass hash cache."""
    return {}
