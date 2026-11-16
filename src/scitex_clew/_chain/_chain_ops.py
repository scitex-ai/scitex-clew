#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_chain/_chain_ops.py
"""Chain and status verification operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

from .._db import get_db
from ._hash_cache import new_hash_cache
from ._routes import (
    DEFAULT_MAX_DEPTH,
    current_hash_or_none,
    order_roots_first,
    resolve_file_dag,
    resolve_producer,
)
from ._types import ChainVerification, VerificationStatus
from ._verify_ops import verify_run


def verify_chain(
    target: str | Path,
    *,
    db_factory=get_db,
    verify_run_fn=verify_run,
    max_depth: int = DEFAULT_MAX_DEPTH,
    minimal: bool = False,
    level: int = 1,
) -> ChainVerification:
    """Verify the dependency chain for a target file.

    Traces back through all sessions that produced this file
    and verifies each one.

    Parameters
    ----------
    target : str or Path
        Target file to trace
    minimal : bool, optional
        Verify only the file-level minimal slice (see
        :mod:`scitex_clew._chain._slice`): runs and files on a path to the
        target. Default False keeps the run-level closure.
    level : int, optional
        Slice level when ``minimal`` (1 path-pruned, 2 declared deps).
    db_factory : callable, optional
        Zero-arg callable returning a verification-DB handle. Defaults
        to the real ``get_db``; tests inject a hand-rolled fake DB via
        this PA-306 §1 DI seam.
    verify_run_fn : callable, optional
        ``(session_id) -> RunVerification``. Defaults to the real
        ``verify_run``; tests inject a canned-result callable here.

    Returns
    -------
    ChainVerification
        Verification result for the entire chain
    """
    db = db_factory()
    target = str(Path(target).resolve())

    # The leaf is the session that produced the bytes now on disk (falling
    # back to the path's newest producer, so a tampered target still reports
    # its mismatch instead of vanishing).
    session_id = resolve_producer(db, target, current_hash_or_none(target))
    if session_id is None:
        return ChainVerification(
            target_file=target,
            runs=[],
            status=VerificationStatus.UNKNOWN,
        )

    slice_ = None
    if minimal:
        from ._slice import build_slice

        slice_ = build_slice([target], level=level, db=db, max_depth=max_depth)
        chain = list(slice_.runs)
    else:
        # Resolve upstream lineage with the ONE resolver (hash-bound
        # save->load handshakes, bounded + deduped). See ._routes.
        adjacency, all_ids = resolve_file_dag([session_id], db=db, max_depth=max_depth)
        # Roots-first order (sources -> target), cycle-tolerant.
        chain = order_roots_first(adjacency, all_ids)

    # Verify each run in the chain, sharing a single hash cache across all
    # sessions so a file referenced by multiple sessions is hashed only once
    # per pass.  ``verify_run_fn`` may be a test-injected stub that ignores
    # the kwarg, so we pass it only when the function is the real verify_run.
    hash_cache = new_hash_cache()
    run_verifications = []
    for sid in chain:
        if verify_run_fn is verify_run:
            run_verifications.append(
                verify_run_fn(
                    sid,
                    hash_cache=hash_cache,
                    slice_files=slice_.run_files(sid) if slice_ else None,
                )
            )
        else:
            run_verifications.append(verify_run_fn(sid))

    # Determine overall status.
    # Severity preserved: VERIFIED > SUSPECT > MISSING > MISMATCH > UNKNOWN
    # is NOT the order — instead we keep the historical "any-failure-wins"
    # priority and slot SUSPECT in below MISMATCH/MISSING:
    #     MISMATCH > MISSING > FAILED > SUSPECT > UNKNOWN.
    # FAILED (a run in the lineage whose execution failed) ranks above
    # SUSPECT: it is the root cause the SUSPECT consumers point at.
    # A chain that has any *locally* broken run reports MISMATCH/MISSING
    # because that needs to be fixed first; a chain whose runs are all
    # locally valid but at least one is SUSPECT (its upstream was broken)
    # reports SUSPECT so the DAG colours that band orange instead of
    # lying green.
    if all(r.is_verified for r in run_verifications):
        status = VerificationStatus.VERIFIED
    elif any(r.status == VerificationStatus.MISMATCH for r in run_verifications):
        status = VerificationStatus.MISMATCH
    elif any(r.status == VerificationStatus.MISSING for r in run_verifications):
        status = VerificationStatus.MISSING
    elif any(r.status == VerificationStatus.FAILED for r in run_verifications):
        status = VerificationStatus.FAILED
    elif any(r.status == VerificationStatus.SUSPECT for r in run_verifications):
        status = VerificationStatus.SUSPECT
    else:
        status = VerificationStatus.UNKNOWN

    return ChainVerification(
        target_file=target,
        runs=run_verifications,
        status=status,
        slice=slice_,
    )


def get_status(
    *,
    db_factory=get_db,
    verify_run_fn=verify_run,
) -> dict[str, Any]:
    """Get verification status for all runs (like git status).

    Parameters
    ----------
    db_factory : callable, optional
        Zero-arg callable returning a verification-DB handle. Defaults
        to the real ``get_db``; tests inject a hand-rolled fake via
        this PA-306 §1 DI seam.
    verify_run_fn : callable, optional
        ``(session_id) -> RunVerification``. Defaults to the real
        ``verify_run``; tests inject a canned-result callable here.

    Returns
    -------
    dict
        Summary of verification status
    """
    db = db_factory()
    runs = db.list_runs(limit=1_000)

    verified = []
    mismatched = []
    missing = []
    failed = []

    # Share a single hash cache across all runs in this status pass so files
    # referenced by multiple sessions are hashed from disk only once.
    hash_cache = new_hash_cache()

    for run in runs:
        session_id = run["session_id"]
        if verify_run_fn is verify_run:
            verification = verify_run_fn(session_id, hash_cache=hash_cache)
        else:
            verification = verify_run_fn(session_id)

        if verification.is_verified:
            verified.append(session_id)
        elif verification.status == VerificationStatus.FAILED:
            # Execution failed: never verified, whatever its files hash to.
            failed.append(session_id)
        elif verification.mismatched_files:
            mismatched.append(
                {
                    "session_id": session_id,
                    "files": [f.path for f in verification.mismatched_files],
                }
            )
        elif verification.missing_files:
            missing.append(
                {
                    "session_id": session_id,
                    "files": [f.path for f in verification.missing_files],
                }
            )

    return {
        "verified_count": len(verified),
        "mismatch_count": len(mismatched),
        "missing_count": len(missing),
        "failed_count": len(failed),
        "mismatched": mismatched,
        "missing": missing,
        "failed": failed,
    }


# EOF
