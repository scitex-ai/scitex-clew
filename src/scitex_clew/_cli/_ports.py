#!/usr/bin/env python3
"""Ecosystem-boundary ports — guarded imports of peer privates (PS-183).

`scitex_dev._cli._completion` is a private surface with no public
equivalent in `scitex_dev.cli`. Reaching it from `_main` at top level
is the a2 ecosystem-boundary smell (ADR-0003), so the reach lives
HERE, behind a guarded import: if the peer ever moves it, the CLI
boots without shell completion instead of crashing at import time.
"""

from __future__ import annotations

from typing import Callable

try:
    from scitex_dev._cli._completion import attach_shell_completion
except ImportError:  # peer moved its privates — CLI works, minus completion
    attach_shell_completion: Callable | None = None  # type: ignore[no-redef]

__all__ = ["attach_shell_completion"]

# EOF
