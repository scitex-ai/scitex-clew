#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Public API registry for scitex_clew.

Extracted from __init__.py to keep that file under the 512-line limit.

Contains:
- _LAZY_ATTRS  — mapping of public name to (submodule, attr) for PEP-562
- __all__      — canonical public export list
- TYPE_CHECKING stubs for IDEs / mypy

Internal helper — not part of the public API surface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# ---------------------------------------------------------------------------
# Lazy attribute map: public_name -> (submodule_relative_path, attr_or_None)
#
# attr_or_None=None means re-export the submodule itself.
# Each entry is resolved on first attribute access via __getattr__ below,
# then cached in module globals so subsequent accesses are free.
# ---------------------------------------------------------------------------
_LAZY_ATTRS: "dict[str, tuple[str, str | None]]" = {
    # ----- Submodule re-export -----
    "groupers": (".groupers", None),
    # ----- Public names re-exported from submodules -----
    # _chain
    "verify_run": ("._chain", "verify_run"),
    "verify_chain": ("._chain", "verify_chain"),
    "verify_file": ("._chain", "verify_file"),
    "get_status": ("._chain", "get_status"),
    "VerificationStatus": ("._chain", "VerificationStatus"),
    "VerificationLevel": ("._chain", "VerificationLevel"),
    "FileVerification": ("._chain", "FileVerification"),
    "RunVerification": ("._chain", "RunVerification"),
    "ChainVerification": ("._chain", "ChainVerification"),
    "DAGVerification": ("._chain", "DAGVerification"),
    # _claim
    "add_claim": ("._claim", "add_claim"),
    "list_claims": ("._claim", "list_claims"),
    "verify_claim": ("._claim", "verify_claim"),
    "verify_all_claims": ("._claim", "verify_all_claims"),
    "export_claims_json": ("._claim", "export_claims_json"),
    "format_claims": ("._claim", "format_claims"),
    "verify_claims_dag": ("._claim", "verify_claims_dag"),
    "Claim": ("._claim", "Claim"),
    "ClaimVerification": ("._claim", "ClaimVerification"),
    "VerificationResult": ("._claim", "VerificationResult"),
    # _cli._exit_codes (configurable verify severity)
    "Severity": ("._cli._exit_codes", "Severity"),
    # _estimate (Phase 1: pre-flight compute estimate)
    "estimate": ("._estimate", "estimate"),
    "EstimateResult": ("._estimate", "EstimateResult"),
    "HEAVY_THRESHOLD_SECONDS": ("._estimate", "HEAVY_THRESHOLD_SECONDS"),
    # _register_intermediate
    "register_intermediate": ("._register_intermediate", "register_intermediate"),
    # _observers (session hooks)
    "on_session_start": ("._observers", "on_session_start"),
    "on_session_close": ("._observers", "on_session_close"),
    # _dag
    "verify_dag": ("._dag", "verify_dag"),
    "verify_dag_strict": ("._dag", "verify_dag_strict"),
    # _db
    "VerificationDB": ("._db", "VerificationDB"),
    "get_db": ("._db", "get_db"),
    "set_db": ("._db", "set_db"),
    # _examples
    "init_examples": ("._examples", "init_examples"),
    # _hash
    "hash_directory": ("._hash", "hash_directory"),
    "hash_file": ("._hash", "hash_file"),
    "hash_files": ("._hash", "hash_files"),
    "combine_hashes": ("._hash", "combine_hashes"),
    "verify_hash": ("._hash", "verify_hash"),
    # _registry
    "ClewRegistry": ("._registry", "ClewRegistry"),
    "get_registry": ("._registry", "get_registry"),
    # _rerun
    "rerun_claims": ("._rerun", "rerun_claims"),
    "rerun_dag": ("._rerun", "rerun_dag"),
    "verify_by_rerun": ("._rerun", "verify_by_rerun"),
    "verify_run_from_scratch": ("._rerun", "verify_by_rerun"),
    # _stamp
    "Stamp": ("._stamp", "Stamp"),
    "check_stamp": ("._stamp", "check_stamp"),
    "list_stamps": ("._stamp", "list_stamps"),
    "stamp": ("._stamp", "stamp"),
    # _tracker
    "SessionTracker": ("._tracker", "SessionTracker"),
    "get_tracker": ("._tracker", "get_tracker"),
    "set_tracker": ("._tracker", "set_tracker"),
    "start_tracking": ("._tracker", "start_tracking"),
    "stop_tracking": ("._tracker", "stop_tracking"),
    # _visualize
    "generate_mermaid_dag": ("._visualize", "generate_mermaid_dag"),
    "generate_html_dag": ("._visualize", "generate_html_dag"),
    "render_dag": ("._visualize", "render_dag"),
    "format_chain_verification": ("._visualize", "format_chain_verification"),
    "format_list": ("._visualize", "format_list"),
    "format_run_detailed": ("._visualize", "format_run_detailed"),
    "format_run_verification": ("._visualize", "format_run_verification"),
    "format_status": ("._visualize", "format_status"),
    "print_verification_summary": ("._visualize", "print_verification_summary"),
}

# ---------------------------------------------------------------------------
# Public API — only these names show in dir() and tab-completion.
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
    # Pre-flight estimate (Phase 1)
    "estimate",
    "EstimateResult",
    # Claims
    "add_claim",
    "list_claims",
    "verify_claim",
    "verify_all_claims",
    "export_claims_json",
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


if TYPE_CHECKING:
    # Re-state for type checkers / IDEs. These statements never execute at
    # runtime, so they don't affect cold-start cost.
    from . import groupers  # noqa: F401
    from ._chain import (  # noqa: F401
        ChainVerification,
        DAGVerification,
        FileVerification,
        RunVerification,
        VerificationLevel,
        VerificationStatus,
        get_status,
        verify_chain,
        verify_file,
        verify_run,
    )
    from ._claim import (  # noqa: F401
        Claim,
        ClaimVerification,
        VerificationResult,
        add_claim,
        export_claims_json,
        format_claims,
        list_claims,
        verify_all_claims,
        verify_claim,
        verify_claims_dag,
    )
    from ._cli._exit_codes import Severity  # noqa: F401
    from ._dag import verify_dag, verify_dag_strict  # noqa: F401
    from ._db import VerificationDB, get_db, set_db  # noqa: F401
    from ._estimate import (  # noqa: F401
        HEAVY_THRESHOLD_SECONDS,
        EstimateResult,
        estimate,
    )
    from ._examples import init_examples  # noqa: F401
    from ._hash import (  # noqa: F401
        combine_hashes,
        hash_directory,
        hash_file,
        hash_files,
        verify_hash,
    )
    from ._observers import on_session_close, on_session_start  # noqa: F401
    from ._register_intermediate import register_intermediate  # noqa: F401
    from ._registry import ClewRegistry, get_registry  # noqa: F401
    from ._rerun import rerun_claims, rerun_dag, verify_by_rerun  # noqa: F401
    from ._stamp import Stamp, check_stamp, list_stamps, stamp  # noqa: F401
    from ._tracker import (  # noqa: F401
        SessionTracker,
        get_tracker,
        set_tracker,
        start_tracking,
        stop_tracking,
    )
    from ._visualize import (  # noqa: F401
        format_chain_verification,
        format_list,
        format_run_detailed,
        format_run_verification,
        format_status,
        generate_html_dag,
        generate_mermaid_dag,
        print_verification_summary,
        render_dag,
    )


# EOF
