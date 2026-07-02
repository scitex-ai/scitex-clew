#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""External attestation for scitex-clew — trust anchors outside the local DB.

Groups the two modules that anchor local hashes to external authorities
(PS-108b topical subpackage, moved from the package root):

- ``_stamp``    — temporal proof stamps (file / RFC 3161 TSA / Zenodo backends)
- ``_registry`` — remote Clew Registry client (hash registration via scitex.ai)

The public surface is re-exported here so callers can write
``from scitex_clew._attest import stamp, get_registry`` without reaching
into the private leaf modules.
"""

from __future__ import annotations

from ._registry import DEFAULT_REGISTRY_URL, ClewRegistry, get_registry
from ._stamp import Stamp, check_stamp, list_stamps, stamp

__all__ = [
    "DEFAULT_REGISTRY_URL",
    "ClewRegistry",
    "get_registry",
    "Stamp",
    "check_stamp",
    "list_stamps",
    "stamp",
]

# EOF
