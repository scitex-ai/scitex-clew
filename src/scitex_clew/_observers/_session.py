#!/usr/bin/env python3
"""Session lifecycle hooks for scitex-clew.

These thin wrappers are invoked by ``@scitex.session`` (or any equivalent
session manager) at the start and end of a run. They delegate to the
``scitex_clew._tracker`` machinery so that a run record is opened on start
and finalized (with a combined hash) on close.

Failure policy
--------------
A provenance hook that fails is NEVER swallowed. It is logged as a WARNING,
recorded (in :data:`HOOK_FAILURES` for this process and, when the run record
exists, in the run's ``metadata["hook_failures"]``), and re-raised so the
session manager can record it too (scitex-session isolates a raising hook and
stores it in ``CONFIGS/CONFIG.yaml::_HOOK_FAILURES``). An incomplete
provenance record is therefore always visible, never silent.

Payload (scitex-session >= the capture-completeness release)
------------------------------------------------------------
The start hook's ``metadata`` carries ``argv``, ``args``, ``seed``, ``cwd``,
``python``, ``git``, ``packages``, ``local_modules``, ``sdir_run``,
``sdir_out``, ``started_at`` and ``capture_errors``. It is stored verbatim as
the run's metadata; :mod:`scitex_clew._rerun` replays ``argv`` from ``cwd``
and the close-time completeness check reads ``sdir_out``. A non-empty
``capture_errors`` is surfaced as a WARNING at start. The close hook accepts
an optional ``metadata`` dict (e.g. ``{"hook_failures": [...]}``) that is
merged into the run record.

They import only scitex-clew internals; no scitex-io dependency is needed.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .._core import getLogger
from .._tracker import get_tracker, start_tracking, stop_tracking

logger = getLogger(__name__)

#: Every clew session-hook failure in this process:
#: ``{"phase", "session_id", "error"}``. Never cleared by clew itself.
HOOK_FAILURES: list[dict[str, str]] = []


def _record_hook_failure(phase: str, session_id: str | None, exc: BaseException):
    failure = {
        "phase": phase,
        "session_id": session_id or "",
        "error": f"{type(exc).__name__}: {exc}",
    }
    HOOK_FAILURES.append(failure)
    logger.warning(
        "clew: session-%s hook failed for %s (%s) — provenance for this "
        "session is INCOMPLETE",
        phase,
        session_id or "<unknown session>",
        failure["error"],
    )
    if session_id:
        try:
            from .._db import get_db

            get_db().merge_run_metadata(session_id, {"hook_failures": [failure]})
        except Exception as record_exc:  # the warning above already fired
            logger.warning(
                "clew: could not attach the hook failure to run %s (%s)",
                session_id,
                record_exc,
            )
    return failure


def on_session_start(
    session_id: str,
    script_path: str | None = None,
    parent_session: str | None = None,
    verbose: bool = False,
    metadata: dict | None = None,
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
        Kept for signature compatibility; failures are warned regardless.
    metadata : dict, optional
        Re-run metadata from the session manager (see module docstring).

    Raises
    ------
    Exception
        Whatever opening the run record raised — after it was warned and
        recorded (see module docstring).
    """
    try:
        start_tracking(
            session_id=session_id,
            script_path=script_path,
            parent_session=parent_session,
            metadata=metadata,
        )
    except Exception as e:
        _record_hook_failure("start", session_id, e)
        raise
    _activate_capture(get_tracker(), script_path, metadata)
    capture_errors = (
        (metadata or {}).get("capture_errors") if isinstance(metadata, dict) else None
    )
    if capture_errors:
        logger.warning(
            "clew: session %s started with %d provenance capture error(s) "
            "(re-run context is incomplete): %s",
            session_id,
            len(capture_errors),
            capture_errors,
        )


def on_session_close(
    status: str = "success",
    exit_code: int = 0,
    verbose: bool = False,
    register: bool | None = None,
    metadata: dict | None = None,
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
        Kept for signature compatibility; failures are warned regardless.
    register : bool, optional
        If True, register session hashes with remote Clew Registry.
        If None, checks SCITEX_AUTO_REGISTER environment variable.
    metadata : dict, optional
        Close-time payload (e.g. ``{"hook_failures": [...]}`` /
        ``{"capture_errors": [...]}``) merged into the run's metadata.

    Raises
    ------
    Exception
        Whatever finalizing the run raised — after it was warned and recorded.
    """
    tracker = get_tracker()
    session_id = tracker.session_id if tracker is not None else None
    try:
        _apply_relocations(tracker, metadata)
        _finish_capture(tracker)
        if metadata and session_id:
            tracker._db.merge_run_metadata(session_id, dict(metadata))
            failures = metadata.get("hook_failures") or []
            if failures:
                logger.warning(
                    "clew: session %s closed with %d provenance hook failure(s): %s",
                    session_id,
                    len(failures),
                    failures,
                )
        if status == "success":
            # Provenance-completeness check (#45): a succeeded session whose
            # output root holds files it never recorded. A failed session's
            # incomplete recording is expected, so only check success.
            _warn_if_unrecorded_outputs(tracker)
        stop_tracking(status=status, exit_code=exit_code)
    except Exception as e:
        _record_hook_failure("close", session_id, e)
        raise
    if _should_auto_register(register) and session_id is not None:
        _auto_register_session(session_id)


def _apply_relocations(tracker, metadata) -> int:
    """Re-key recorded paths the session manager MOVED before closing.

    scitex-session >= 0.3.6 moves ``RUNNING/<ID>`` to ``FINISHED_*/<ID>``
    before firing close hooks and reports each move in ``metadata
    ["relocations"]`` as ``{"from", "to", "archive"?}`` (real paths). Without
    this, outputs saved into the run dir stay recorded at a path that no
    longer exists and verify as MISSING. Applied before the run is finalized,
    so the combined hash covers the final paths. When ``archive`` is set the
    directory becomes ``<to>.tar.gz`` later; ``verify`` already reads files
    through such an archive. An output that is at neither place is warned
    about, never silently dropped. Claims whose source (or manuscript) path
    lies under a moved directory — registered DURING the session against its
    run dir — are rewritten too (#191, :mod:`scitex_clew._claim._relocate`).
    Returns the number of file rows and claims changed.
    """
    if tracker is None or not isinstance(metadata, dict):
        return 0
    from .._claim._relocate import relocate_claim_paths
    from .._db._relocate import relocated

    changed = 0
    claims_moved: list[str] = []
    for item in metadata.get("relocations") or []:
        old = item.get("from") if isinstance(item, dict) else None
        new = item.get("to") if isinstance(item, dict) else None
        if not old or not new:
            logger.warning(
                "clew: session %s — malformed relocation %r ignored; paths under "
                "it stay recorded at their pre-move location",
                tracker.session_id,
                item,
            )
            continue
        moved = [p for p in tracker._outputs if relocated(p, old, new) is not None]
        changed += tracker.relocate(old, new)
        claims_moved += relocate_claim_paths(
            old, new, session_id=tracker.session_id, outputs=tracker._outputs
        )
        absent = [
            p
            for p in (relocated(m, old, new) for m in moved)
            if not os.path.isfile(p) and not item.get("archive")
        ]
        if absent:
            logger.warning(
                "clew: session %s — %d output(s) relocated %s -> %s are not at "
                "their new path: %s",
                tracker.session_id,
                len(absent),
                old,
                new,
                absent[:10],
            )
    if claims_moved:
        # claims.json carries source paths: re-emit it at the final paths.
        from .._claim._mutate import _auto_export

        _auto_export("relocating claims of session " + tracker.session_id)
    return changed + len(claims_moved)


def _activate_capture(tracker, script_path, metadata) -> None:
    """Start file-access + imported-code capture (:mod:`scitex_clew._capture`).

    A capture failure must not abort the session; it is warned and recorded
    on the run (``metadata["capture"]``) instead — loud, never silent.
    """
    if tracker is None:
        return
    from .. import _capture

    try:
        _capture.activate(tracker, script_path=script_path, metadata=metadata)
    except Exception as exc:  # noqa: BLE001 - warned + recorded below
        error = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "clew: could not start file-access capture for session %s (%s) — "
            "files read/written outside stx.io will NOT be recorded",
            tracker.session_id,
            error,
        )
        tracker._db.merge_run_metadata(
            tracker.session_id, {"capture": {"audit": "failed", "errors": [error]}}
        )


def _finish_capture(tracker) -> None:
    """Flush captured writes/late imports and attach the capture summary."""
    if tracker is None:
        return
    from .. import _capture

    summary = _capture.finish(tracker)
    if summary is not None:
        tracker._db.merge_run_metadata(tracker.session_id, {"capture": summary})


#: Session-manager trees under ``sdir_out`` that hold logs/configs, not outputs.
_SESSION_TREES = ("RUNNING",)
_SESSION_TREE_PREFIX = "FINISHED"


def _is_session_tree(rel_parts) -> bool:
    if not rel_parts:
        return False
    head = rel_parts[0]
    return head in _SESSION_TREES or head.startswith(_SESSION_TREE_PREFIX)


def unrecorded_outputs(
    sdir_out: str | Path,
    started_at: str | None,
    recorded: set,
) -> list[str]:
    """Files under ``sdir_out`` written since ``started_at`` and not recorded.

    ``RUNNING/`` and ``FINISHED*/`` (the session manager's log/config trees)
    are skipped; only files whose mtime is at or after ``started_at`` count,
    so earlier runs' outputs in the shared ``<script>_out/`` are ignored.
    """
    root = Path(sdir_out)
    if not root.is_dir():
        return []
    since = None
    if started_at:
        try:
            since = datetime.fromisoformat(started_at).timestamp()
        except ValueError:
            since = None
    found: list[str] = []
    for path in root.rglob("*"):
        try:
            rel = path.relative_to(root).parts
        except ValueError:
            continue
        if _is_session_tree(rel) or not path.is_file():
            continue
        if since is not None and path.stat().st_mtime < since:
            continue
        resolved = str(path.resolve())
        if resolved not in recorded:
            found.append(resolved)
    return sorted(found)


def _warn_if_unrecorded_outputs(tracker) -> list[str]:
    """WARN when the session wrote outputs that clew never recorded.

    The INDEPENDENT signal is the session's output root ``sdir_out`` (sent in
    the start metadata by scitex-session): every file written there since
    ``started_at`` — outside the ``RUNNING/`` / ``FINISHED*/`` log trees —
    that is not among the tracker's recorded outputs is an unrecorded output
    (the #44 gap: a save that bypassed ``on_io_save``). Silently inert when the
    metadata has no ``sdir_out`` (an older session manager). Returns the
    unrecorded paths.
    """
    if tracker is None:
        return []
    run = tracker._db.get_run(tracker.session_id)
    if not run:
        return []
    meta = run.get("metadata")
    if isinstance(meta, str):
        meta = json.loads(meta) if meta else {}
    meta = meta or {}
    sdir_out = meta.get("sdir_out")
    if not sdir_out:
        return []
    started_at = meta.get("started_at") or run.get("started_at")
    missing = unrecorded_outputs(
        sdir_out, started_at, set(getattr(tracker, "_outputs", {}) or {})
    )
    if missing:
        logger.warning(
            "clew: session %s wrote %d output file(s) under %s that were NOT "
            "recorded as provenance (saved outside a live tracker / not via "
            "stx.io.save): %s. The submission gate will treat them as UNSOURCED.",
            tracker.session_id,
            len(missing),
            sdir_out,
            missing[:10],
        )
    return missing


# ── Registry helpers ──


def _should_auto_register(register: bool | None) -> bool:
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
        logger.warning(
            "clew: failed to auto-register session %s with the registry: %s",
            session_id,
            e,
        )


# EOF
