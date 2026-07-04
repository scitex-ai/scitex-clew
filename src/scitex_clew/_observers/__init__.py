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
from typing import Any, Callable, Dict

from scitex_clew._core import getLogger

from ._session import on_session_close, on_session_start

logger = getLogger(__name__)

# Idempotency guards for peer-hook registration. The import-time bootstrap AND
# the entry-point activation path may both invoke register_with_*; keying on the
# peer module's ``id()`` registers exactly ONCE per distinct peer instance — so
# repeat calls against the same instance are no-ops (no double-firing), while a
# genuine two-instance module split still registers each instance that fires.
_registered_io_ids: set = set()
_registered_session_ids: set = set()


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
        # No active session at save time -> nothing to attach the file_hash to.
        # Log it (not a silent bail): a save firing here with no tracker is
        # either a legitimate out-of-session save OR the symptom of a tracker
        # not being live across session-start->save. DEBUG, because out-of-
        # session saves are normal and WARNING would cry wolf on every one.
        logger.debug(
            "clew: on_io_save fired for %s but no active session tracker — "
            "provenance NOT recorded (out-of-session save, or tracker not live)",
            path,
        )
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


_warned_peers: set = set()


def _peer_version(peer_name: str) -> str:
    """Best-effort installed version of a peer package (for the skew hint)."""
    try:
        from importlib.metadata import version

        return version(peer_name.replace("_", "-"))
    except Exception:  # pragma: no cover - version lookup is best-effort
        return "unknown"


def bootstrap_register(register: Callable[[], bool], peer_name: str) -> bool:
    """Invoke a peer-registration callable, surfacing failures (never raises).

    Wraps a zero-arg ``register_with_scitex_*`` call so a silent registration
    failure stops hiding: logs a WARNING — ONCE per peer per process — if
    ``register`` raised or returned ``False``, naming the peer's version as a
    skew hint. It means clew's auto-provenance hooks will not fire for
    ``peer_name`` (which does NOT affect keygen/sign/verify — those are pure
    crypto on the manifest). Returns the result. Used by the import-time
    bootstrap AND the entry-point activation path.
    """
    try:
        ok = register()
    except Exception as exc:  # a broken registrar must never break import
        if peer_name not in _warned_peers:
            _warned_peers.add(peer_name)
            logger.warning(
                "clew observer registration with %s failed (%s: %s) — "
                "auto-provenance hooks will not fire (does not affect "
                "keygen/sign/verify)",
                peer_name,
                type(exc).__name__,
                exc,
            )
        return False
    if not ok:
        if peer_name not in _warned_peers:
            _warned_peers.add(peer_name)
            logger.warning(
                "clew observer registration with %s (v%s) returned False "
                "(peer hook-API unavailable or version skew) — auto-provenance "
                "hooks will not fire (does not affect keygen/sign/verify)",
                peer_name,
                _peer_version(peer_name),
            )
    return bool(ok)


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

    if id(scitex_io) in _registered_io_ids:
        return True  # idempotent: already registered against THIS instance

    try:
        scitex_io.register_post_save_hook(on_io_save)
        scitex_io.register_post_load_hook(on_io_load)
        _registered_io_ids.add(id(scitex_io))
        # Diagnostic (module-identity): logs WHICH scitex_io instance clew
        # registered against, so a "registered True but hooks never fire"
        # symptom (a distinct scitex_io module firing a different hook list)
        # is visible by comparing this id with the firing instance's.
        logger.debug(
            "clew registered io hooks against scitex_io id=%s file=%s",
            id(scitex_io),
            getattr(scitex_io, "__file__", "?"),
        )
        return True
    except Exception as e:
        logger.debug("clew: failed to register hooks with scitex_io: %s", e)
        return False


def register_with_scitex_session() -> bool:
    """Register clew's session hooks with scitex-session's registry if available.

    Mirrors :func:`register_with_scitex_io`: scitex-session OWNS the lifecycle
    hook registry (``register_session_start_hook`` / ``register_session_close_hook``)
    and clew SUBSCRIBES — scitex-session never imports clew, so the seam is
    acyclic. Guarded so an OLD scitex-session without the registry API is a
    silent no-op (same contract as the fallback-import path on the session
    side). Never raises.

    scitex-session fires hooks POSITIONALLY — ``start(session_id, script_path,
    metadata)`` / ``close(status, exit_code)`` — whereas clew's public
    :func:`~scitex_clew.on_session_start` positional order is
    ``(session_id, script_path, parent_session, verbose, metadata)``. So we
    register keyword-mapping ADAPTERS (not the raw callables); a positional
    ``metadata`` never lands in ``parent_session``, and the public hooks stay
    unchanged.

    Returns
    -------
    bool
        True if both hooks were registered. False if scitex-session is not
        installed or its registry API is unavailable.
    """
    try:
        import scitex_session
    except Exception as e:
        logger.debug(
            "clew: scitex_session not importable, skipping session hooks: %s", e
        )
        return False

    reg_start = getattr(scitex_session, "register_session_start_hook", None)
    reg_close = getattr(scitex_session, "register_session_close_hook", None)
    if reg_start is None or reg_close is None:
        logger.debug(
            "clew: scitex_session has no lifecycle-hook registry; skipping"
        )
        return False

    if id(scitex_session) in _registered_session_ids:
        return True  # idempotent: already registered against THIS instance

    def _start_adapter(session_id, script_path=None, metadata=None):
        on_session_start(session_id, script_path=script_path, metadata=metadata)

    def _close_adapter(status="success", exit_code=0):
        on_session_close(status=status, exit_code=exit_code)

    try:
        reg_start(_start_adapter)
        reg_close(_close_adapter)
        return True
    except Exception as e:
        logger.debug("clew: failed to register hooks with scitex_session: %s", e)
        return False


# EOF
