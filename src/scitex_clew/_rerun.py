#!/usr/bin/env python3
# Timestamp: "2026-06-27 (ywatanabe)"
# File: src/scitex_clew/_rerun.py
"""Rerun verification - re-execute scripts and compare outputs."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Dict

from ._chain import (
    DAGVerification,
    FileVerification,
    RunVerification,
    VerificationLevel,
    VerificationStatus,
)
from ._core import getLogger
from ._db import get_db
from ._hash import hashes_match

logger = getLogger(__name__)

# _chain._freshness and _chain._hash_cache are imported lazily inside rerun_dag
# so they do not add to the cold-start cost of `import scitex_clew`.


def verify_by_rerun(
    target: str | list[str],
    timeout: int = 300,
    cleanup: bool = True,
) -> RunVerification | list[RunVerification]:
    """Verify session(s) by re-executing scripts and comparing outputs.

    Parameters
    ----------
    target : str or list[str]
        Session ID, script path, or artifact path.
        - run_id: directly use this run
        - script path: latest run that executed this script
        - artifact path: latest run which produced this file
    timeout : int, optional
        Maximum execution time in seconds (default: 300)
    cleanup : bool, optional
        Whether to remove the new session's output directory after verification

    Returns
    -------
    RunVerification or list[RunVerification]
        Single result if single target, list if multiple targets
    """
    if isinstance(target, list):
        return [_verify_single(t, timeout, cleanup) for t in target]
    return _verify_single(target, timeout, cleanup)


def _verify_single(
    target: str,
    timeout: int = 300,
    cleanup: bool = True,
) -> RunVerification:
    """Verify a single target by replaying it in a sandbox.

    See :mod:`scitex_clew._chain._rerun_sandbox` for the contract: the
    recorded ``argv`` is replayed from the recorded ``cwd`` into a sandbox
    output root (originals are never overwritten), and outputs are compared
    by full path relative to ``<script>_out/`` plus hash.
    """
    from ._chain._rerun_sandbox import (
        cleanup_sandbox,
        plan_sandbox,
        relative_outputs,
        run_dir_of,
        run_in_sandbox,
    )

    db = get_db()

    # Resolve target to session_id
    session_id = _resolve_to_session_id(db, target)
    if not session_id:
        return _unknown_result(target, None)

    # Get original run info
    run_info = db.get_run(session_id)
    if not run_info:
        return _unknown_result(session_id, None)

    script_path = run_info.get("script_path")
    is_command = _entry_kind(run_info) == "command"
    if not is_command and (not script_path or not Path(script_path).exists()):
        return RunVerification(
            session_id=session_id,
            script_path=script_path,
            status=VerificationStatus.MISSING,
            files=[],
            combined_hash_expected=None,
            combined_hash_current=None,
            level=VerificationLevel.RERUN,
        )

    # Get expected output hashes from original session
    original_hashes = db.get_file_hashes(session_id, role="output")
    if not original_hashes:
        return _unknown_result(session_id, script_path)

    plan = plan_sandbox(session_id, run_info, original_hashes)
    if plan.refusal is not None:
        logger.warning("clew rerun: %s not re-run — %s", session_id, plan.refusal)
        return _unknown_result(session_id, script_path)
    if not plan.can_sandbox:
        # Outputs saved outside <stem>_out/ would be overwritten in place by a
        # replay: refuse rather than touch the originals.
        logger.warning(
            "clew rerun: %s not re-run — %d output(s) outside %s cannot be "
            "sandboxed: %s",
            session_id,
            len(plan.outside_outputs),
            plan.out_root,
            plan.outside_outputs[:5],
        )
        return dataclasses.replace(
            _unknown_result(session_id, script_path),
            files=[
                FileVerification(
                    p, "output", original_hashes[p], None, VerificationStatus.UNKNOWN
                )
                for p in plan.outside_outputs
            ],
        )
    for note in plan.notes:
        logger.warning("clew rerun %s: %s", session_id, note)

    replay = run_in_sandbox(plan, db, timeout)
    try:
        if replay.timed_out:
            return _unknown_result(session_id, script_path)
        if replay.returncode != 0:
            logger.warning(
                "clew rerun: replay of %s exited %s: %s",
                session_id,
                replay.returncode,
                replay.stderr_tail,
            )
            status = VerificationStatus.FAILED
            file_verifications = []
        elif replay.new_session_id is None:
            logger.warning(
                "clew rerun: replay of %s recorded no run (is the script "
                "tracked by @stx.session / clew.session?)",
                session_id,
            )
            return _unknown_result(session_id, script_path)
        else:
            file_verifications = _compare_hashes(
                relative_outputs(
                    original_hashes, plan.out_root, run_dir_of(run_info)
                ),
                replay.new_outputs,
            )
            status = _determine_status(file_verifications)
    finally:
        if cleanup:
            cleanup_sandbox(replay, db)

    # Record verification result in database for original session
    db.record_verification(
        session_id=session_id,
        level=VerificationLevel.RERUN.value,
        status=status.value,
    )

    return RunVerification(
        session_id=session_id,
        script_path=script_path,
        status=status,
        files=file_verifications,
        combined_hash_expected=run_info.get("combined_hash"),
        combined_hash_current=None,
        level=VerificationLevel.RERUN,
    )


def _entry_kind(run_info: dict) -> str | None:
    """``metadata.entry.kind`` (scitex-session >= 0.3.6), e.g. ``command``."""
    raw = run_info.get("metadata")
    try:
        meta = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        return None
    return (meta.get("entry") or {}).get("kind")


def _resolve_to_session_id(db, target: str) -> str | None:
    """Resolve target to session_id.

    Accepts:
        - run_id: directly use this run
        - script path: latest run that executed this script
        - artifact path: latest run which produced this file
    """
    # Try as run_id
    if db.get_run(target):
        return target

    # Always resolve to absolute path
    resolved = str(Path(target).resolve())

    # Try as script path
    for run in db.list_runs(limit=100):
        if run.get("script_path") == resolved:
            return run["session_id"]

    # Try as artifact (output) path: the producer of the bytes on disk now.
    from ._chain._routes import current_hash_or_none, resolve_producer

    return resolve_producer(db, resolved, current_hash_or_none(resolved))


def _unknown_result(session_id: str, script_path: str) -> RunVerification:
    """Create an unknown verification result."""
    return RunVerification(
        session_id=session_id,
        script_path=script_path,
        status=VerificationStatus.UNKNOWN,
        files=[],
        combined_hash_expected=None,
        combined_hash_current=None,
        level=VerificationLevel.RERUN,
    )


def _compare_hashes(
    original_hashes: dict[str, str], new_hashes: dict[str, str]
) -> list:
    """Compare outputs keyed by path RELATIVE to the output root.

    Both dicts map ``relative/path -> hash`` (see
    :func:`scitex_clew._chain._rerun_sandbox.relative_outputs`). A file is
    matched only by its full relative path, never by basename.
    """
    verifications = []
    for rel_path, expected_hash in original_hashes.items():
        current_hash = new_hashes.get(rel_path)
        if current_hash is None:
            status = VerificationStatus.MISSING
        elif hashes_match(expected_hash, current_hash):
            status = VerificationStatus.VERIFIED
        else:
            status = VerificationStatus.MISMATCH
        verifications.append(
            FileVerification(
                path=rel_path,
                role="output",
                expected_hash=expected_hash,
                current_hash=current_hash,
                status=status,
            )
        )
    return verifications


def _determine_status(file_verifications: list) -> VerificationStatus:
    """Determine overall verification status from file verifications."""
    if all(f.is_verified for f in file_verifications):
        return VerificationStatus.VERIFIED
    if any(f.status == VerificationStatus.MISMATCH for f in file_verifications):
        return VerificationStatus.MISMATCH
    return VerificationStatus.UNKNOWN


def rerun_dag(
    targets: list[str] | None = None,
    timeout: int = 300,
    cleanup: bool = True,
    skip_unchanged: bool = False,
) -> DAGVerification:
    """Rerun-verify an entire DAG in topological order.

    Each session is re-executed against its ORIGINAL stored inputs then
    compared to its original outputs.  When ``skip_unchanged=True`` a
    freshness check short-circuits the subprocess for unchanged sessions.

    Parameters
    ----------
    targets : list of str, optional
        Target output files.  If None all recorded outputs are used.
    timeout : int, optional
        Max execution time per session in seconds (default: 300).
    cleanup : bool, optional
        Remove sandbox output directories after each rerun.
    skip_unchanged : bool, optional
        OPT-IN incremental skip (default: False).  When True, each session
        is tested for freshness BEFORE the expensive subprocess launch.
        A session is fresh when: (1) script_hash is recorded; (2) script
        file exists and matches script_hash; (3) every recorded INPUT file
        exists and its hash matches the recorded value.  Fresh sessions are
        marked status=VERIFIED / level=CACHE so ``is_verified_from_scratch``
        is False — clearly distinct from an actual re-execution.  Non-fresh
        sessions fall through to the normal ``_execute_script`` path.
        Default is False: behavior is byte-identical to the original.

    Returns
    -------
    DAGVerification
        Unified verification result for the entire DAG.
    """
    from ._chain import DAGVerification
    from ._chain._dag import _topological_sort

    db = get_db()

    # If no targets, collect all output files from all runs
    if targets is None:
        targets = []
        for run in db.list_runs(limit=10_000):
            hashes = db.get_file_hashes(run["session_id"], role="output")
            targets.extend(hashes.keys())

    from ._chain._routes import (
        current_hash_or_none,
        resolve_file_dag,
        resolve_producer,
    )

    # Resolve targets to leaf session IDs (producer of the bytes on disk)
    resolved_targets = []
    leaf_sessions = []
    for target in targets:
        target_str = str(Path(target).resolve())
        resolved_targets.append(target_str)
        leaf = resolve_producer(db, target_str, current_hash_or_none(target_str))
        if leaf is not None and leaf not in leaf_sessions:
            leaf_sessions.append(leaf)

    if not leaf_sessions:
        return DAGVerification(
            target_files=resolved_targets,
            runs=[],
            edges=[],
            status=VerificationStatus.UNKNOWN,
            topological_order=[],
        )

    # The ONE lineage resolver (hash-bound save->load handshakes) — the same
    # DAG verify_dag / verify_chain / the renderers walk.
    adjacency, _all_ids = resolve_file_dag(leaf_sessions, db=db)

    # Topological sort (roots first)
    topo_order = _topological_sort(adjacency)

    # Lazy-import freshness helpers and hash cache only when opt-in is active
    # so they do not add to the cold-start cost of `import scitex_clew`.
    if skip_unchanged:
        from ._chain._freshness import _is_session_fresh, _skipped_result
        from ._chain._hash_cache import new_hash_cache

        hash_cache = new_hash_cache()
    else:
        hash_cache = None

    # Rerun each session in topological order
    verifications = {}
    for sid in topo_order:
        if skip_unchanged and _is_session_fresh(sid, hash_cache=hash_cache):
            run_info = db.get_run(sid)
            verifications[sid] = _skipped_result(
                sid, run_info.get("script_path") if run_info else None
            )
        else:
            verifications[sid] = verify_by_rerun(sid, timeout, cleanup)

    # Propagate failures forward through the DAG
    failed_sessions: set = set()
    for sid in topo_order:
        parents = adjacency.get(sid, [])
        has_failed_parent = any(p in failed_sessions for p in parents)
        if has_failed_parent or not verifications[sid].is_verified:
            failed_sessions.add(sid)

    # Build edges list
    edges = []
    for child, parents in adjacency.items():
        for p in parents:
            edges.append((p, child))

    # Determine overall status
    run_list = [verifications[sid] for sid in topo_order]

    if all(sid not in failed_sessions for sid in topo_order):
        status = VerificationStatus.VERIFIED
    elif any(
        verifications[sid].status == VerificationStatus.MISMATCH for sid in topo_order
    ):
        status = VerificationStatus.MISMATCH
    elif any(
        verifications[sid].status == VerificationStatus.MISSING for sid in topo_order
    ):
        status = VerificationStatus.MISSING
    elif any(
        verifications[sid].status == VerificationStatus.FAILED for sid in topo_order
    ):
        status = VerificationStatus.FAILED
    else:
        status = VerificationStatus.UNKNOWN

    return DAGVerification(
        target_files=resolved_targets,
        runs=run_list,
        edges=edges,
        status=status,
        topological_order=topo_order,
    )


def rerun_claims(
    file_path: str | None = None,
    claim_type: str | None = None,
    timeout: int = 300,
    cleanup: bool = True,
) -> DAGVerification:
    """Rerun-verify all sessions that produced files referenced by claims.

    Parameters
    ----------
    file_path : str, optional
        Filter claims by manuscript file path.
    claim_type : str, optional
        Filter claims by type (statistic, figure, table, text, value).
    timeout : int, optional
        Maximum execution time per session in seconds (default: 300).
    cleanup : bool, optional
        Whether to remove sandbox output directories after each rerun.

    Returns
    -------
    DAGVerification
        Unified verification result for the upstream DAG.
    """
    from ._claim import list_claims

    claims = list_claims(file_path=file_path, claim_type=claim_type)

    # Collect unique source files from matching claims
    source_files = []
    seen = set()
    for claim in claims:
        sf = claim.source_file
        if sf and sf not in seen:
            seen.add(sf)
            source_files.append(sf)

    return rerun_dag(source_files or None, timeout, cleanup)


# Backward compatibility alias
verify_run_from_scratch = verify_by_rerun


# EOF
