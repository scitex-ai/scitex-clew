#!/usr/bin/env python3
"""Session lifecycle hooks for scitex-clew.

These thin wrappers are invoked by ``@scitex.session`` (or any equivalent
session manager) at the start and end of a run. They delegate to the
``scitex_clew._tracker`` machinery so that a run record is opened on start
and finalized (with a combined hash) on close.

They import only scitex-clew internals; no scitex-io dependency is needed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .._core import getLogger
from .._tracker import get_tracker, start_tracking, stop_tracking

logger = getLogger(__name__)


def on_session_start(
    session_id: str,
    script_path: Optional[str] = None,
    parent_session: Optional[str] = None,
    verbose: bool = False,
    metadata: Optional[dict] = None,
) -> None:
    """
    Hook called when a session starts.

    Parameters
    ----------
    session_id : str
        Unique session identifier
    script_path : str, optional
        Path to the script being run
    parent_session : str, optional
        Parent session ID for chain tracking
    verbose : bool, optional
        Whether to log status messages
    metadata : dict, optional
        Additional metadata (e.g. notebook_path, cell_index)
    """
    try:
        start_tracking(
            session_id=session_id,
            script_path=script_path,
            parent_session=parent_session,
            metadata=metadata,
        )
    except Exception as e:
        if verbose:
            logger.warning(f"Could not start verification tracking: {e}")


def on_session_close(
    status: str = "success",
    exit_code: int = 0,
    verbose: bool = False,
    register: Optional[bool] = None,
) -> None:
    """
    Hook called when a session closes.

    Parameters
    ----------
    status : str, optional
        Final status (success, failed, error)
    exit_code : int, optional
        Exit code of the script
    verbose : bool, optional
        Whether to log status messages
    register : bool, optional
        If True, register session hashes with remote Clew Registry.
        If None, checks SCITEX_AUTO_REGISTER environment variable.
    """
    try:
        tracker = get_tracker()
        if status == "success":
            # Provenance-completeness check (#45): a succeeded session that wrote
            # outputs but recorded ZERO provenance is the #44-class gap. A failed
            # session's incomplete recording is expected, so only check success.
            _warn_if_unrecorded_outputs(tracker)
        stop_tracking(status=status, exit_code=exit_code)
        if _should_auto_register(register) and tracker is not None:
            _auto_register_session(tracker.session_id)
    except Exception as e:
        if verbose:
            logger.warning(f"Could not stop verification tracking: {e}")


def _warn_if_unrecorded_outputs(tracker) -> None:
    """WARN if the session wrote outputs but recorded ZERO output provenance.

    The provenance-completeness citizen (#45). The INDEPENDENT saves signal is
    the session OUTPUT DIR (passed via ``metadata["output_dir"]`` and populated
    by the save itself) — so it fires precisely when clew's ``on_io_save`` did
    NOT record (the #44 gap: ``@stx.session`` + ``stx.io.save`` but empty
    file_hashes), which an on_io_save-derived counter is blind to. Predicate:

        output_dir has >=1 file  AND  tracker recorded 0 outputs  ->  WARN

    False-positive-free: a read-only / zero-output session has an empty/absent
    output dir and stays silent. DEFENSIVE: silently skips when ``output_dir`` is
    absent from metadata (a pre-enabler scitex-session, or any caller that does
    not send it), so it is inert-safe until that signal exists and lights up the
    moment it does. Never raises.
    """
    try:
        if tracker is None:
            return
        if len(getattr(tracker, "_outputs", {}) or {}) > 0:
            return  # provenance WAS recorded -> no gap
        run = tracker._db.get_run(tracker.session_id)
        if not run:
            return
        meta = run.get("metadata")
        if isinstance(meta, str):
            meta = json.loads(meta) if meta else {}
        output_dir = (meta or {}).get("output_dir")
        if not output_dir:
            return  # no independent saves signal yet -> skip
        out = Path(output_dir)
        if out.is_dir():
            dirs = [out]
        else:
            # The RUNNING output dir may have MOVED to <base>/<final-status>/<id>
            # by the time this close-hook fires (the RUNNING->FINISHED rename);
            # resolve by globbing sibling status subdirs for the same session-id
            # leaf. Best-effort + inert-safe (no match -> skip), so the check is
            # robust regardless of close-hook-vs-move ordering.
            base = out.parent.parent
            dirs = (
                [d for d in base.glob(f"*/{out.name}") if d.is_dir()]
                if base.is_dir()
                else []
            )
        if not dirs:
            return
        file_count = sum(
            1 for d in dirs for p in d.rglob("*") if p.is_file()
        )
        if file_count == 0:
            return  # session wrote nothing -> no gap
        logger.warning(
            "clew: session %s wrote %d output file(s) under %s but recorded ZERO "
            "provenance — outputs were saved outside a live @stx.session tracker "
            "(wrap saves in @stx.session, or check the scitex-io observer wiring). "
            "The submission gate will treat these outputs as UNSOURCED.",
            tracker.session_id,
            file_count,
            output_dir,
        )
    except Exception as e:  # completeness is a nicety — never break close
        logger.debug("clew: session-close completeness check skipped: %s", e)


# ── Registry helpers ──


def _should_auto_register(register: Optional[bool]) -> bool:
    """Check whether auto-registration is enabled."""
    if register is not None:
        return register

    return os.environ.get("SCITEX_AUTO_REGISTER", "").lower() in (
        "1",
        "true",
        "yes",
    )


def _auto_register_session(session_id: str) -> None:
    """Register session hashes with remote Clew Registry (fire-and-forget)."""
    try:
        from .._attest._registry import get_registry

        get_registry().register_session(session_id)
    except Exception as e:
        logger.debug("clew: failed to auto-register session %s: %s", session_id, e)


# EOF
