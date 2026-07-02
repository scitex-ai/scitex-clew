#!/usr/bin/env python3
"""Lifecycle hook observers (SOC R6).

scitex-clew is the observer; it owns the hooks that other packages fire
into so the umbrella package never has to wire them:

* **io hooks** (``on_io_save`` / ``on_io_load``) — self-registered with
  scitex-io; exception-safe (they MUST NOT raise).
* **session hooks** (``on_session_start`` / ``on_session_close``) — invoked
  by ``@scitex.session`` to open/finalize a tracked run; see
  :mod:`scitex_clew._observers._session`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from scitex_clew._core import getLogger

from ._session import on_session_close, on_session_start

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
        The saved object. Inspected for the citation-artifact schema marker so
        scitex-scholar can populate the citation ledger by saving a
        ``citation_status.json`` via ``stx.io`` — no scholar→clew import (the
        decoupled seam; see :mod:`scitex_clew._citation._ingest`).
    kwargs : dict
        Original kwargs passed to ``scitex_io.save``. We honour
        ``track`` (default True) for parity with the umbrella shim.
    """
    try:
        from scitex_clew._db import get_db

        get_db()  # Ensure DB exists
    except Exception as e:
        logger.debug("clew: failed to initialise DB: %s", e)

    # Citation-artifact ingestion (the scholar↔clew decoupled seam). Runs
    # BEFORE the track/session gate: citations are a manuscript-level ledger,
    # not session-scoped, so a saved citation_status.json is ingested whether or
    # not a tracker is active or ``track`` was requested.
    try:
        from scitex_clew._citation._ingest import ingest_citations_artifact

        ingest_citations_artifact(obj)
    except Exception as e:
        logger.debug("clew: citation-artifact ingest failed: %s", e)

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
