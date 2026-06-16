#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_chain/_chain_ops.py
"""Chain and status verification operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Union

from .._db import get_db
from ._routes import DEFAULT_MAX_DEPTH, order_roots_first, resolve_file_dag
from ._types import ChainVerification, VerificationStatus
from ._verify_ops import verify_run


def verify_chain(
    target: Union[str, Path],
    *,
    db_factory=get_db,
    verify_run_fn=verify_run,
    max_depth: int = DEFAULT_MAX_DEPTH,
) -> ChainVerification:
    """Verify the dependency chain for a target file.

    Traces back through all sessions that produced this file
    and verifies each one.

    Parameters
    ----------
    target : str or Path
        Target file to trace
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

    # Find session that produced this output
    sessions = db.find_session_by_file(target, role="output")
    if not sessions:
        return ChainVerification(
            target_file=target,
            runs=[],
            status=VerificationStatus.UNKNOWN,
        )

    # Get the most recent session
    session_id = sessions[0]

    # Resolve the chain via file save->load handshakes (bounded + deduped),
    # NOT the legacy parent_session walk (which was cyclic and accreted every
    # historical producer of every shared/config input). The target's producer
    # is the leaf; walk back through the newest producer of each loaded file.
    # See ._routes for the model.
    adjacency, all_ids = resolve_file_dag([session_id], db=db, max_depth=max_depth)

    # Roots-first order (sources -> target), cycle-tolerant.
    chain = order_roots_first(adjacency, all_ids)

    # Verify each run in the chain
    run_verifications = []
    for sid in chain:
        run_verifications.append(verify_run_fn(sid))

    # Determine overall status.
    # Severity preserved: VERIFIED > SUSPECT > MISSING > MISMATCH > UNKNOWN
    # is NOT the order — instead we keep the historical "any-failure-wins"
    # priority and slot SUSPECT in below MISMATCH/MISSING:
    #     MISMATCH > MISSING > SUSPECT > UNKNOWN.
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
    elif any(r.status == VerificationStatus.SUSPECT for r in run_verifications):
        status = VerificationStatus.SUSPECT
    else:
        status = VerificationStatus.UNKNOWN

    return ChainVerification(
        target_file=target,
        runs=run_verifications,
        status=status,
    )


def get_status(
    *,
    db_factory=get_db,
    verify_run_fn=verify_run,
) -> Dict[str, Any]:
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

    for run in runs:
        session_id = run["session_id"]
        verification = verify_run_fn(session_id)

        if verification.is_verified:
            verified.append(session_id)
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
        "mismatched": mismatched,
        "missing": missing,
    }


# EOF
