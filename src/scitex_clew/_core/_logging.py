#!/usr/bin/env python3
"""Logging with optional scitex.logging enhancement.

When scitex is installed, uses scitex.logging (richer formatting).
Otherwise, falls back to stdlib logging.

Set SCITEX_CLEW_DEBUG_MODE=1 to enable DEBUG-level logging.
"""

import os

try:
    # Optional enhancement. scitex_logging does filesystem work at import
    # time (it sets up file handlers under ~/.scitex/logs), so its import can
    # fail with more than ImportError — e.g. OSError when that directory is
    # over its inode/space quota. clew is zero-dependency and the stdlib
    # fallback below is complete, so ANY failure of this optional path must
    # fall back cleanly rather than crash clew's package import.
    import scitex_logging as _logging

    getLogger = _logging.getLogger
except Exception:
    import logging

    getLogger = logging.getLogger

if os.environ.get("SCITEX_CLEW_DEBUG_MODE", "").strip() in ("1", "true", "yes"):
    import logging

    logging.basicConfig(level=logging.DEBUG)
    getLogger("scitex_clew").setLevel(logging.DEBUG)


# EOF
