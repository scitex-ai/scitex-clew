#!/usr/bin/env python3
"""Logging with optional scitex.logging enhancement.

When scitex is installed, uses scitex.logging (richer formatting).
Otherwise, falls back to stdlib logging.

Set SCITEX_CLEW_DEBUG_MODE=1 to enable DEBUG-level logging.
"""

import os

try:
    import scitex_logging as _logging
    getLogger = _logging.getLogger
except ImportError:
    import logging

    getLogger = logging.getLogger

if os.environ.get("SCITEX_CLEW_DEBUG_MODE", "").strip() in ("1", "true", "yes"):
    import logging

    logging.basicConfig(level=logging.DEBUG)
    getLogger("scitex_clew").setLevel(logging.DEBUG)


# EOF
