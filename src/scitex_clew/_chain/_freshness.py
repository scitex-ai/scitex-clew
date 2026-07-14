#!/usr/bin/env python3
# Timestamp: "2026-06-27 (ywatanabe)"
# File: src/scitex_clew/_chain/_freshness.py
"""Freshness check helpers for the opt-in incremental skip in rerun_dag.

A session is considered fresh (skippable) when:
- ``script_hash`` is recorded (non-NULL) in the ``runs`` table.
- The script file at ``script_path`` still exists and its current SHA-256
  (full digest, comparable prefix-tolerantly against ``script_hash`` — see
  ``_hashes_match``) matches ``script_hash``.
- Every file recorded with ``role='input'`` for the session still exists on
  disk and its current hash matches the recorded value.

Output hashes are deliberately NOT checked here — the purpose of the check is
to decide whether to skip a re-execution, not to validate outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .._db import get_db
from .._hash import hash_file
from ._hash_cache import new_hash_cache
from ._types import RunVerification, VerificationLevel, VerificationStatus


def _hashes_match(current: str, recorded: str) -> bool:
    """Prefix-tolerant hash equality (same convention as ``verify_file``).

    ``hash_file`` now returns the full sha256 digest, but a ``runs``/
    ``file_hashes`` row recorded before clew-fix-truncated-hash-comparison
    may still hold the old 32-char truncated value. Compare over the
    shorter length so freshness detection keeps working for both old and
    new rows instead of degrading to "always stale" for a pre-existing DB.
    """
    if not current or not recorded:
        return False
    n = min(len(current), len(recorded))
    return current[:n] == recorded[:n]


def _is_session_fresh(
    session_id: str,
    hash_cache: Optional[Dict[str, str]] = None,
) -> bool:
    """Return True iff the session's recorded inputs and script are unchanged.

    Freshness definition (EXACT):

    1. ``script_hash`` stored in the ``runs`` table is non-NULL.
    2. The script file at ``script_path`` exists and its current SHA-256
       hash matches ``script_hash`` (prefix-tolerant, see ``_hashes_match``).
    3. Every file recorded with ``role='input'`` for *session_id* still
       exists on disk and its current hash matches the recorded value.

    If any condition fails the session is NOT fresh (return False) and
    ``rerun_dag`` falls through to the normal ``_execute_script`` path.

    Parameters
    ----------
    session_id : str
        Session to evaluate.
    hash_cache : dict or None, optional
        Per-pass cache (resolved-path -> hash) shared across freshness
        checks in a single ``rerun_dag`` call.  When *None* a temporary
        cache is created for this call only.

    Returns
    -------
    bool
        True iff all inputs and the script match their recorded hashes.
    """
    if hash_cache is None:
        hash_cache = new_hash_cache()

    db = get_db()
    run_info = db.get_run(session_id)
    if not run_info:
        return False

    recorded_script_hash = run_info.get("script_hash")
    script_path = run_info.get("script_path")

    # A recorded script_hash is required to establish a freshness baseline
    if not recorded_script_hash:
        return False

    # Script must still be present and unchanged
    if not script_path or not Path(script_path).exists():
        return False

    try:
        current_script_hash = hash_file(script_path, hash_cache=hash_cache)
    except FileNotFoundError:
        return False

    if not _hashes_match(current_script_hash, recorded_script_hash):
        return False

    # Every recorded INPUT file must be present and unchanged
    input_hashes = db.get_file_hashes(session_id, role="input")
    for file_path, recorded_hash in input_hashes.items():
        if not Path(file_path).exists():
            return False
        try:
            current_hash = hash_file(file_path, hash_cache=hash_cache)
        except FileNotFoundError:
            return False
        if not _hashes_match(current_hash, recorded_hash):
            return False

    return True


def _skipped_result(
    session_id: str,
    script_path: Optional[str],
) -> RunVerification:
    """Return a RunVerification that marks the session as skipped-unchanged.

    Uses ``level=VerificationLevel.CACHE`` (not RERUN) so that
    ``is_verified_from_scratch`` returns False, clearly distinguishing a
    freshness-skip from an actual re-execution.  ``status`` is VERIFIED
    because all inputs and the script were confirmed unchanged — the run is
    locally consistent; it was simply not re-executed.
    """
    return RunVerification(
        session_id=session_id,
        script_path=script_path,
        status=VerificationStatus.VERIFIED,
        files=[],
        combined_hash_expected=None,
        combined_hash_current=None,
        level=VerificationLevel.CACHE,
    )


# EOF
