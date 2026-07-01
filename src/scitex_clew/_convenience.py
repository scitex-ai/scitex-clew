#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Eager public convenience wrappers for scitex_clew.

Extracted from ``__init__.py`` to keep that file under the 512-line limit.

These wrappers are defined eagerly (cheap — they're just function objects plus
the :func:`_supports_return_as` decorator). Each body does a function-local
``from .<submodule> import …`` so the heavy submodule is only imported on first
invocation. Python caches the resulting module in ``sys.modules``, so the
local-import overhead on subsequent calls is a dict lookup. Importing this
module itself therefore adds no measurable cold-start cost (audit §10).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Lazy decorator from scitex-dev (audit §10 cold-start)
#
# ``supports_return_as`` adds ``return_as="result"`` support. We MUST apply it
# at function-definition time to preserve that public API behaviour, but
# importing ``scitex_dev.decorators`` eagerly costs ~190ms (it pulls in
# ``scitex_dev._core.types`` + dataclasses + copy). That single import was
# pushing ``import scitex_clew`` over the audit-cli §10 500 ms threshold in CI
# py3.12.
#
# Trick: wrap the decorator. At definition time we just record the function
# unchanged (cheap). The first *call* into any wrapper resolves the real
# decorator from scitex_dev.decorators, applies it, and patches the module
# global so subsequent calls skip the indirection. Net cost at import: zero.
# ---------------------------------------------------------------------------
def _supports_return_as(fn):
    """Defer scitex_dev.decorators.supports_return_as to first call."""

    _decorated = [None]

    def _wrapper(*args, **kwargs):
        if _decorated[0] is None:
            try:
                from scitex_dev.decorators import (
                    supports_return_as as _real,
                )

                _decorated[0] = _real(fn)
            except Exception:
                # scitex-dev may import optional ML libs whose runtime-init
                # can fail with VersionError / RuntimeError; fall back to
                # the bare function, preserving normal call semantics.
                _decorated[0] = fn
        return _decorated[0](*args, **kwargs)

    _wrapper.__wrapped__ = fn
    _wrapper.__name__ = getattr(fn, "__name__", "_wrapper")
    _wrapper.__doc__ = fn.__doc__
    _wrapper.__qualname__ = getattr(fn, "__qualname__", _wrapper.__name__)
    return _wrapper


@_supports_return_as
def list_runs(limit: int = 100, status: str = None):
    """List tracked runs."""
    from ._db import get_db

    db = get_db()
    return db.list_runs(status=status, limit=limit)


@_supports_return_as
def status():
    """Get verification status summary (like git status)."""
    from ._chain import get_status

    return get_status()


@_supports_return_as
def run(session_id: str, from_scratch: bool = False):
    """Verify a specific run.

    Parameters
    ----------
    session_id : str
        Session identifier
    from_scratch : bool, optional
        If True, re-execute the script and verify outputs (slow but thorough).
        If False, only compare hashes (fast).
    """
    if from_scratch:
        from ._rerun import verify_by_rerun

        return verify_by_rerun(session_id)
    from ._chain import verify_run

    return verify_run(session_id)


@_supports_return_as
def chain(target: str):
    """Verify the dependency chain for a target file."""
    from ._chain import verify_chain

    return verify_chain(target)


@_supports_return_as
def stats():
    """Get database statistics."""
    from ._db import get_db

    db = get_db()
    return db.stats()


@_supports_return_as
def dag(targets=None, claims=False, strict=False):
    """Verify the DAG for multiple targets or all claims.

    Parameters
    ----------
    targets : list of str or Path, optional
        Target files to verify (mutually exclusive with ``claims``).
    claims : bool, optional
        If True, build the DAG from every registered claim.
    strict : bool, optional
        If True (F2), return a failure-attribution dict with
        ``failed_node`` / ``root_cause`` / ``invalidated_claims`` /
        ``still_valid_claims`` instead of a ``DAGVerification``.
    """
    if strict:
        from ._dag import verify_dag_strict

        return verify_dag_strict(targets=targets, claims=claims)
    if claims:
        from ._claim import verify_claims_dag

        return verify_claims_dag()
    from ._dag import verify_dag

    return verify_dag(targets or [])


@_supports_return_as
def rerun(target, timeout: int = 300, cleanup: bool = True):
    """Re-execute a session in a sandbox and compare outputs.

    Parameters
    ----------
    target : str or list[str]
        Session ID, script path, or artifact path.
    timeout : int, optional
        Maximum execution time in seconds (default: 300).
    cleanup : bool, optional
        Remove sandbox outputs after verification (default: True).
    """
    from ._rerun import verify_by_rerun

    return verify_by_rerun(target, timeout=timeout, cleanup=cleanup)


@_supports_return_as
def mermaid(
    session_id=None,
    target_file=None,
    target_files=None,
    claims=False,
    grouper=None,
    **kwargs,
):
    """Generate a Mermaid DAG diagram.

    Parameters
    ----------
    session_id : str, optional
        Start from this session.
    target_file : str, optional
        Start from the session that produced this file.
    target_files : list of str, optional
        Multiple target files (multi-target DAG).
    claims : bool, optional
        If True, build DAG from all registered claims.
    grouper : callable | dict | None, optional
        File grouping strategy. Callable or JSON/dict spec (see
        ``scitex_clew.groupers.resolve_spec``). If ``None``, falls back to
        ``.scitex/clew/config.yaml`` (key ``grouper``) if present.
    """
    if grouper is None:
        from ._groupers._config import load_project_config

        grouper = load_project_config().get("grouper")
    from ._visualize import generate_mermaid_dag

    return generate_mermaid_dag(
        session_id=session_id,
        target_file=target_file,
        target_files=target_files,
        claims=claims,
        grouper=grouper,
        **kwargs,
    )


@_supports_return_as
def estimate(script_or_target: str, *, heavy_threshold: int = None):
    """Pre-flight runtime/success estimate for a script or target file.

    Parameters
    ----------
    script_or_target : str
        Path to a Python script or a target output file.  Target files are
        resolved to their producing script via the run DB.
    heavy_threshold : int, optional
        Override the p90 threshold (seconds) above which the ``heavy`` flag
        is set.  Defaults to :data:`scitex_clew.HEAVY_THRESHOLD_SECONDS`.

    Returns
    -------
    EstimateResult
        Estimation result with match_tier, p50/p90 runtime, success rate,
        typical #outputs, heavy flag, and hint text.
    """
    from ._estimate import HEAVY_THRESHOLD_SECONDS, estimate as _estimate

    kwargs = {}
    if heavy_threshold is not None:
        kwargs["heavy_threshold"] = heavy_threshold
    else:
        kwargs["heavy_threshold"] = HEAVY_THRESHOLD_SECONDS
    return _estimate(script_or_target, **kwargs)


__all__ = [
    "list_runs",
    "status",
    "run",
    "chain",
    "stats",
    "dag",
    "rerun",
    "mermaid",
    "estimate",
]

# EOF
