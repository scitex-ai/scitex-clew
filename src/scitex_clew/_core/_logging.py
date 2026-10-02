#!/usr/bin/env python3
"""Canonical scitex-logging with a tolerant stdlib fallback.

The package declares scitex-logging as a dependency. If its initialization
fails, package imports retain the existing stdlib logging fallback.

Set SCITEX_CLEW_DEBUG_MODE=1 to enable DEBUG-level logging.
"""

import os

try:
    # scitex_logging may initialize file handlers under the canonical
    # $SCITEX_DIR/logging/runtime path (default ~/.scitex/logging/runtime).
    # Its import can fail with more than ImportError — e.g. OSError if it is
    # over its inode/space quota. The existing stdlib fallback below is
    # complete, so a failure during canonical logger initialization must
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
