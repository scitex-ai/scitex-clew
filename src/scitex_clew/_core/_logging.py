#!/usr/bin/env python3
"""Canonical scitex-logging with a tolerant stdlib fallback.

The package declares scitex-logging as a dependency. If its initialization
fails, package imports retain the existing stdlib logging fallback.

Set SCITEX_CLEW_DEBUG_MODE=1 to enable DEBUG-level logging. The level is
applied through scitex-logging's ``set_level`` (PS-220: package source must
not configure stdlib logging directly), which lowers both the root logger
and its handlers so DEBUG records actually reach the console. In the
degraded stdlib fallback the flag has no effect.
"""

import os

_DEBUG_MODE = os.environ.get("SCITEX_CLEW_DEBUG_MODE", "").strip() in (
    "1",
    "true",
    "yes",
)

try:
    # scitex_logging may initialize file handlers under the canonical
    # $SCITEX_DIR/logging/runtime path (default ~/.scitex/logging/runtime).
    # Its import can fail with more than ImportError — e.g. OSError if it is
    # over its inode/space quota. The existing stdlib fallback below is
    # complete, so a failure during canonical logger initialization must
    # fall back cleanly rather than crash clew's package import.
    import scitex_logging as _logging

    getLogger = _logging.getLogger
    if _DEBUG_MODE:
        _logging.set_level(_logging.DEBUG)
except Exception:
    import logging

    getLogger = logging.getLogger


# EOF
