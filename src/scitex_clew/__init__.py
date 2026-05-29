#!/usr/bin/env python3
"""
scitex-clew — Hash-based verification for reproducible science.

Standalone package. Zero dependencies (pure stdlib + sqlite3).
When used with scitex, integration is automatic via @stx.session + stx.io.

Public API::

    import scitex_clew as clew

    # Verification
    clew.status()                      # git-status-like overview
    clew.run(session_id)               # verify one run (hash check)
    clew.chain(target_file)            # trace file → source chain
    clew.dag(targets)                  # verify full DAG
    clew.rerun(target)                 # re-execute & compare (sandbox)
    clew.rerun_dag(targets)            # rerun full DAG in topo order
    clew.rerun_claims()                # rerun all claim-backing sessions
    clew.list_runs(limit=100)          # list tracked runs
    clew.stats()                       # database statistics

    # Claims
    clew.add_claim(...)                # register manuscript assertion
    clew.list_claims(...)              # list registered claims
    clew.verify_claim(...)             # verify a specific claim

    # Stamping
    clew.stamp(...)                    # create temporal proof
    clew.list_stamps(...)              # list stamps
    clew.check_stamp(...)              # verify a stamp

    # Hashing
    clew.hash_file(path)               # SHA256 of a file
    clew.hash_directory(path)          # SHA256 of all files in dir

    # Visualization
    clew.mermaid(...)                  # generate Mermaid DAG diagram

    # Examples
    clew.init_examples(dest)           # scaffold example pipeline

    # Session lifecycle hooks (invoked by @scitex.session)
    clew.on_session_start(session_id)  # open a tracked run
    clew.on_session_close(status=...)  # finalize run + combined hash
"""

from __future__ import annotations

try:
    from importlib.metadata import version as _v, PackageNotFoundError

    try:
        __version__ = _v("scitex-clew")
    except PackageNotFoundError:
        __version__ = "0.0.0+local"
    del _v, PackageNotFoundError
except ImportError:  # pragma: no cover — only on ancient Pythons
    __version__ = "0.0.0+local"

# ---------------------------------------------------------------------------
# Optional decorator from scitex-dev (graceful fallback)
# ---------------------------------------------------------------------------
try:
    from scitex_dev.decorators import supports_return_as as _supports_return_as
except Exception:
    # Broad catch (not just ImportError): scitex-dev may import optional ML
    # libs whose runtime-init can fail with VersionError / RuntimeError.
    # Fall back to a no-op decorator regardless.
    def _supports_return_as(fn):
        return fn


# ---------------------------------------------------------------------------
# Internal imports (hidden from public API, still importable via full path)
# ---------------------------------------------------------------------------
from . import groupers  # public: scitex_clew.groupers
from ._chain import (
    ChainVerification as _ChainVerification,
)
from ._chain import (
    DAGVerification as _DAGVerification,
)
from ._chain import (
    FileVerification as _FileVerification,
)
from ._chain import (
    RunVerification as _RunVerification,
)
from ._chain import (
    VerificationLevel as _VerificationLevel,
)
from ._chain import (
    VerificationStatus as _VerificationStatus,
)
from ._chain import (
    get_status as _get_status,
)
from ._chain import (
    verify_chain as _verify_chain,
)
from ._chain import (
    verify_file as _verify_file,
)
from ._chain import (
    verify_run as _verify_run,
)
from ._claim import (
    Claim as _Claim,
)
from ._claim import (
    add_claim,
    list_claims,
    verify_claim,
)
from ._register_intermediate import register_intermediate
from ._session import on_session_close, on_session_start
from ._claim import (
    format_claims as _format_claims,
)
from ._claim import (
    verify_claims_dag as _verify_claims_dag,
)
from ._dag import verify_dag as _verify_dag
from ._dag import verify_dag_strict as _verify_dag_strict
from ._db import VerificationDB as _VerificationDB
from ._db import get_db as _get_db
from ._db import set_db as _set_db
from ._examples import init_examples
from ._hash import (
    combine_hashes as _combine_hashes,
)
from ._hash import (
    hash_directory,
    hash_file,
)
from ._hash import (
    hash_files as _hash_files,
)
from ._hash import (
    verify_hash as _verify_hash,
)
from ._registry import ClewRegistry as _ClewRegistry
from ._registry import get_registry as _get_registry
from ._rerun import rerun_claims, rerun_dag
from ._rerun import verify_by_rerun as _verify_by_rerun
from ._stamp import Stamp as _Stamp
from ._stamp import check_stamp, list_stamps, stamp
from ._tracker import (
    SessionTracker as _SessionTracker,
)
from ._tracker import (
    get_tracker as _get_tracker,
)
from ._tracker import (
    set_tracker as _set_tracker,
)
from ._tracker import (
    start_tracking as _start_tracking,
)
from ._tracker import (
    stop_tracking as _stop_tracking,
)
from ._visualize import (
    format_chain_verification as _format_chain_verification,
)
from ._visualize import (
    format_list as _format_list,
)
from ._visualize import (
    format_run_detailed as _format_run_detailed,
)
from ._visualize import (
    format_run_verification as _format_run_verification,
)
from ._visualize import (
    format_status as _format_status,
)
from ._visualize import (
    generate_html_dag as _generate_html_dag,
)
from ._visualize import (
    generate_mermaid_dag as _generate_mermaid_dag,
)
from ._visualize import (
    print_verification_summary as _print_verification_summary,
)
from ._visualize import (
    render_dag as _render_dag,
)


# ---------------------------------------------------------------------------
# Public convenience API
# ---------------------------------------------------------------------------
@_supports_return_as
def list_runs(limit: int = 100, status: str = None):
    """List tracked runs."""
    db = _get_db()
    return db.list_runs(status=status, limit=limit)


@_supports_return_as
def status():
    """Get verification status summary (like git status)."""
    return _get_status()


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
        return _verify_by_rerun(session_id)
    return _verify_run(session_id)


@_supports_return_as
def chain(target: str):
    """Verify the dependency chain for a target file."""
    return _verify_chain(target)


@_supports_return_as
def stats():
    """Get database statistics."""
    db = _get_db()
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
        return _verify_dag_strict(targets=targets, claims=claims)
    if claims:
        return _verify_claims_dag()
    return _verify_dag(targets or [])


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
    return _verify_by_rerun(target, timeout=timeout, cleanup=cleanup)


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
    return _generate_mermaid_dag(
        session_id=session_id,
        target_file=target_file,
        target_files=target_files,
        claims=claims,
        grouper=grouper,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Accessible but not in __all__ (for advanced use / backward compat)
# ---------------------------------------------------------------------------
get_db = _get_db
set_db = _set_db
verify_run = _verify_run
verify_chain = _verify_chain
verify_dag = _verify_dag
verify_file = _verify_file
verify_by_rerun = _verify_by_rerun
verify_claims_dag = _verify_claims_dag
get_status = _get_status
generate_mermaid_dag = _generate_mermaid_dag
get_tracker = _get_tracker
set_tracker = _set_tracker
start_tracking = _start_tracking
stop_tracking = _stop_tracking
get_registry = _get_registry
format_claims = _format_claims
format_status = _format_status
format_list = _format_list
format_run_verification = _format_run_verification
format_run_detailed = _format_run_detailed
format_chain_verification = _format_chain_verification
print_verification_summary = _print_verification_summary
generate_html_dag = _generate_html_dag
render_dag = _render_dag
combine_hashes = _combine_hashes
hash_files = _hash_files
verify_hash = _verify_hash
verify_run_from_scratch = _verify_by_rerun

# Class/type names
VerificationDB = _VerificationDB
SessionTracker = _SessionTracker
ClewRegistry = _ClewRegistry
VerificationStatus = _VerificationStatus
VerificationLevel = _VerificationLevel
FileVerification = _FileVerification
RunVerification = _RunVerification
ChainVerification = _ChainVerification
DAGVerification = _DAGVerification
Claim = _Claim
Stamp = _Stamp


# ---------------------------------------------------------------------------
# Public API — only these 19 names show in dir() and tab-completion
# ---------------------------------------------------------------------------
__all__ = [
    "__version__",
    # Verification
    "status",
    "run",
    "chain",
    "dag",
    "rerun",
    "rerun_dag",
    "rerun_claims",
    "list_runs",
    "stats",
    # Claims
    "add_claim",
    "list_claims",
    "verify_claim",
    "register_intermediate",
    # Stamping
    "stamp",
    "list_stamps",
    "check_stamp",
    # Hashing
    "hash_file",
    "hash_directory",
    # Visualization
    "mermaid",
    # Grouping API
    "groupers",
    # Examples
    "init_examples",
    # Session lifecycle hooks
    "on_session_start",
    "on_session_close",
]


# EOF
