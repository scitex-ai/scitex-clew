#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_chain/_verify_ops.py
"""Core file and run verification logic."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

from ._archive_lookup import hash_archived_file
from .._db import get_db
from .._hash import hash_file
from ._types import (
    FileVerification,
    RunVerification,
    VerificationStatus,
)


def verify_file(
    path: Union[str, Path],
    expected_hash: str,
    role: str = "unknown",
    hash_cache: Optional[Dict[str, str]] = None,
    frozen: bool = False,
) -> FileVerification:
    """Verify a single file against expected hash.

    If the loose file is gone but its enclosing session dir was compressed to
    an ancestor ``<dir>.tar.gz`` (``scitex.session`` archive mode), the file
    is read+hashed from inside the archive instead of being reported MISSING.
    This keeps provenance verifiable after the inode-saving compression — the
    archived bytes are byte-identical to the recorded ones.

    Parameters
    ----------
    path : str or Path
        Path to the file
    expected_hash : str
        Expected hash value
    role : str, optional
        Role of the file (input, output, script)
    hash_cache : dict or None, optional
        Per-pass cache (resolved-path -> hash) threaded from the top-level
        verify entry point. When provided, each file is hashed at most once
        within the pass; subsequent references reuse the cached value.
    frozen : bool, optional
        When True, skip re-hashing and trust the recorded hash.  The file's
        *existence* is still checked: a frozen file that is absent on disk is
        still reported MISSING (frozen means "trust the hash without
        re-reading", not "ignore missing files").  Returns a FileVerification
        with ``status=VERIFIED`` and ``frozen=True`` — never silently rendered
        as a normal verified file; callers and renderers must show the 🔒 FROZEN
        marker.

    Returns
    -------
    FileVerification
        Verification result
    """
    path = Path(path)
    path_str = str(path)

    # Frozen short-circuit: trust the recorded hash without re-reading the
    # file.  We still check existence so a genuinely missing frozen file is
    # not silently swallowed — the user needs to know the data is gone even
    # if they opted out of re-hashing.
    if frozen:
        if not path.exists() and hash_archived_file(path) is None:
            return FileVerification(
                path=path_str,
                role=role,
                expected_hash=expected_hash,
                current_hash=None,
                status=VerificationStatus.MISSING,
                frozen=True,
            )
        # File present (or archived): trust the stored hash, no re-read.
        return FileVerification(
            path=path_str,
            role=role,
            expected_hash=expected_hash,
            current_hash=expected_hash,
            status=VerificationStatus.VERIFIED,
            frozen=True,
        )

    if path.exists():
        current_hash = hash_file(path, hash_cache=hash_cache)
    else:
        # Loose file absent — try to read it from an ancestor session archive
        # (transparent .tar.gz support). None means truly gone.
        current_hash = hash_archived_file(path)
        if current_hash is None:
            return FileVerification(
                path=path_str,
                role=role,
                expected_hash=expected_hash,
                current_hash=None,
                status=VerificationStatus.MISSING,
            )

    # Compare only the length of expected_hash
    matches = current_hash[: len(expected_hash)] == expected_hash

    return FileVerification(
        path=path_str,
        role=role,
        expected_hash=expected_hash,
        current_hash=current_hash,
        status=VerificationStatus.VERIFIED if matches else VerificationStatus.MISMATCH,
    )


def _resolve_target(db, target: str) -> str | None:
    """Resolve target (session_id, script path, or artifact path) to session_id."""
    # Try as session_id
    if db.get_run(target):
        return target

    # Resolve to absolute path
    resolved = str(Path(target).resolve())

    # Try as script path
    for run in db.list_runs(limit=100):
        if run.get("script_path") == resolved:
            return run["session_id"]

    # Try as artifact (output) path
    sessions = db.find_session_by_file(resolved, role="output")
    return sessions[0] if sessions else None


def verify_run(
    target: str,
    propagate: bool = True,
    collapse_suspect: bool = False,
    hash_cache: Optional[Dict[str, str]] = None,
) -> RunVerification:
    """Verify a session run by checking all file hashes.

    Parameters
    ----------
    target : str
        Session ID, script path, or artifact path
    propagate : bool
        If True, mark as failed if any upstream input has failed verification.
    collapse_suspect : bool
        Backward-compatibility knob for the original 2-state output:
        when True the new SUSPECT state ("upstream failed but every local
        file verifies on its own") is folded back into MISMATCH, exactly
        matching the pre-SUSPECT behaviour. Default is False so callers
        opting into the 3-state DAG colouring get SUSPECT surfaced
        without further changes.
    hash_cache : dict or None, optional
        Per-pass cache (resolved-path -> hash) threaded from the top-level
        verify entry point. When provided, each file is hashed at most once
        within the pass; subsequent references reuse the cached value.

    Returns
    -------
    RunVerification
        Verification result
    """
    db = get_db()

    # Resolve target to session_id
    session_id = _resolve_target(db, target)
    if not session_id:
        return RunVerification(
            session_id=target,
            script_path=None,
            status=VerificationStatus.UNKNOWN,
            files=[],
            combined_hash_expected=None,
            combined_hash_current=None,
        )

    # Get run info
    run_info = db.get_run(session_id)
    if not run_info:
        return RunVerification(
            session_id=session_id,
            script_path=None,
            status=VerificationStatus.UNKNOWN,
            files=[],
            combined_hash_expected=None,
            combined_hash_current=None,
        )

    # Get all file hashes
    input_hashes = db.get_file_hashes(session_id, role="input")
    output_hashes = db.get_file_hashes(session_id, role="output")

    # Get frozen file sets (additive helper, no change to existing get_file_hashes API)
    frozen_inputs = db.get_frozen_files(session_id, role="input")
    frozen_outputs = db.get_frozen_files(session_id, role="output")

    # Verify each file
    file_verifications = []
    upstream_failed = False

    for path, expected in input_hashes.items():
        fv = verify_file(
            path,
            expected,
            role="input",
            hash_cache=hash_cache,
            frozen=path in frozen_inputs,
        )
        file_verifications.append(fv)

        # Check if upstream session that produced this input has failed
        # A frozen file that verifies (trusted) does NOT trigger upstream_failed.
        if propagate and not fv.is_verified:
            upstream_failed = True

    for path, expected in output_hashes.items():
        file_verifications.append(
            verify_file(
                path,
                expected,
                role="output",
                hash_cache=hash_cache,
                frozen=path in frozen_outputs,
            )
        )

    # Verify script if present
    if run_info.get("script_path") and run_info.get("script_hash"):
        script_verification = verify_file(
            run_info["script_path"],
            run_info["script_hash"],
            role="script",
            hash_cache=hash_cache,
        )
        file_verifications.append(script_verification)

    # Determine overall status.
    #
    # Order matters: a *local* failure (MISMATCH on an output/script, or a
    # MISSING output) is always more severe than upstream propagation —
    # the local failure says "this run's own artifacts are wrong now",
    # which the user must fix regardless of chain state. We check those
    # first. Only when every locally-checkable file passes do we fall back
    # to the upstream-only signal — that becomes SUSPECT (or MISMATCH if
    # the caller opted into the legacy 2-state collapse).
    locally_failed_files = [
        f for f in file_verifications if f.role != "input" and not f.is_verified
    ]
    if locally_failed_files:
        # Pick MISMATCH if any local artifact mismatches; MISSING only when
        # every local failure is "file absent" (matches the original
        # severity preference).
        if any(f.status == VerificationStatus.MISMATCH for f in locally_failed_files):
            status = VerificationStatus.MISMATCH
        elif all(f.status == VerificationStatus.MISSING for f in locally_failed_files):
            status = VerificationStatus.MISSING
        else:
            status = VerificationStatus.UNKNOWN
    elif upstream_failed:
        # Every local file (output / script) verifies cleanly; only the
        # upstream chain is broken. This is the SUSPECT case — surface it
        # so the DAG view can render it in its own colour ("upstream-
        # failed-but-locally-valid"). The collapse_suspect knob folds it
        # back into MISMATCH for callers that still want the legacy
        # 2-state behaviour.
        status = (
            VerificationStatus.MISMATCH
            if collapse_suspect
            else VerificationStatus.SUSPECT
        )
    elif all(f.is_verified for f in file_verifications):
        status = VerificationStatus.VERIFIED
    elif any(f.status == VerificationStatus.MISMATCH for f in file_verifications):
        status = VerificationStatus.MISMATCH
    elif any(f.status == VerificationStatus.MISSING for f in file_verifications):
        status = VerificationStatus.MISSING
    else:
        status = VerificationStatus.UNKNOWN

    return RunVerification(
        session_id=session_id,
        script_path=run_info.get("script_path"),
        status=status,
        files=file_verifications,
        combined_hash_expected=run_info.get("combined_hash"),
        combined_hash_current=None,
        provenance=run_info.get("provenance", "tracked") or "tracked",
        exception_reason=run_info.get("exception_reason"),
    )


# EOF
