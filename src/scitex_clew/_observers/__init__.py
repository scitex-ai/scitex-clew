#!/usr/bin/env python3
"""Self-registering scitex-io post-save / post-load hooks (SOC R6).

scitex-clew is the observer; it registers its own hooks with scitex-io so
the umbrella package never has to wire them. Each hook is exception-safe
— it MUST NOT raise (scitex-io would swallow exceptions anyway, but we
also log at DEBUG for diagnostics).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from scitex_clew._logging import getLogger

logger = getLogger(__name__)


def on_io_save(path: Path, obj: Any, kwargs: Dict[str, Any]) -> None:
    """Post-save hook fired by scitex-io after a successful save.

    Ensures the clew DB exists and, if a session tracker is active,
    records the saved file as an output of the current session.

    Parameters
    ----------
    path : Path
        Path that was just saved.
    obj : Any
        The saved object (unused — the umbrella's prior implementation
        didn't use it either).
    kwargs : dict
        Original kwargs passed to ``scitex_io.save``. We honour
        ``track`` (default True) for parity with the umbrella shim.
    """
    try:
        from scitex_clew._db import get_db

        get_db()  # Ensure DB exists
    except Exception as e:
        logger.debug("clew: failed to initialise DB: %s", e)

    track = bool(kwargs.get("track", True)) if isinstance(kwargs, dict) else True
    if not track:
        return

    try:
        from scitex_clew._tracker import get_tracker

        tracker = get_tracker()
    except Exception as e:
        logger.debug("clew: failed to get tracker: %s", e)
        return

    if tracker is None:
        return

    try:
        tracker.record_output(path, track=track)
    except Exception as e:
        logger.debug("clew: failed to record output %s: %s", path, e)


def on_io_load(path: Path, result: Any) -> None:
    """Post-load hook fired by scitex-io after a successful load.

    Ensures the clew DB exists and, if a session tracker is active,
    records the loaded file as an input of the current session.

    Parameters
    ----------
    path : Path
        Path that was just loaded.
    result : Any
        The loaded object (unused).
    """
    try:
        from scitex_clew._db import get_db

        get_db()
    except Exception as e:
        logger.debug("clew: failed to initialise DB: %s", e)

    try:
        from scitex_clew._tracker import get_tracker

        tracker = get_tracker()
    except Exception as e:
        logger.debug("clew: failed to get tracker: %s", e)
        return

    if tracker is None:
        return

    try:
        tracker.record_input(path, track=True)
    except Exception as e:
        logger.debug("clew: failed to record input %s: %s", path, e)


def register_with_scitex_io() -> bool:
    """Register clew's hooks with scitex-io if it is importable.

    Returns
    -------
    bool
        True if both hooks were registered. False if scitex-io is not
        installed or its hook API is unavailable. Never raises.
    """
    try:
        import scitex_io
    except Exception as e:
        logger.debug(
            "clew: scitex_io not importable, skipping hook registration: %s", e
        )
        return False

    try:
        scitex_io.register_post_save_hook(on_io_save)
        scitex_io.register_post_load_hook(on_io_load)
        return True
    except Exception as e:
        logger.debug("clew: failed to register hooks with scitex_io: %s", e)
        return False


# EOF
