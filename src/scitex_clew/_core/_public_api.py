#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Public API registry for scitex_clew.

Extracted from __init__.py to keep that file under the 512-line limit;
lives in ``_core/`` so the package root stays under the PS-108b flat-file
threshold.

Contains:
- _LAZY_ATTRS  — mapping of public name to (submodule, attr) for PEP-562

The canonical ``__all__`` literal and the ``TYPE_CHECKING`` import stubs live
in ``__init__.py`` (PA-101 requires ``__all__`` declared there, and PA-102
requires every ``__all__`` name statically bound there); this module only
provides the lazy-attribute registry.

Internal helper — not part of the public API surface.
"""

from __future__ import annotations

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
    "export_manuscript_claims": ("._claim", "export_manuscript_claims"),
    "export_manuscript_hints": ("._claim", "export_manuscript_hints"),
    "format_claims": ("._claim", "format_claims"),
    "verify_claims_dag": ("._claim", "verify_claims_dag"),
    "remove_claim": ("._claim", "remove_claim"),
    "remove_claims_by_prefix": ("._claim", "remove_claims_by_prefix"),
    "supersede_claim": ("._claim", "supersede_claim"),
    "supersede_claims_by_prefix": ("._claim", "supersede_claims_by_prefix"),
    "Claim": ("._claim", "Claim"),
    "ClaimVerification": ("._claim", "ClaimVerification"),
    "VerificationResult": ("._claim", "VerificationResult"),
    # _citation (citation -> scholar-verified source gate)
    "add_citation": ("._citation", "add_citation"),
    "list_citations": ("._citation", "list_citations"),
    "verify_citations": ("._citation", "verify_citations"),
    "verify_all_citations": ("._citation", "verify_all_citations"),
    "format_citations": ("._citation", "format_citations"),
    "Citation": ("._citation", "Citation"),
    # _sources (registered-source gate)
    "register_source": ("._sources", "register_source"),
    "unregister_source": ("._sources", "unregister_source"),
    "list_sources": ("._sources", "list_sources"),
    "is_grounded": ("._sources", "is_grounded"),
    "is_claim_grounded": ("._sources", "is_claim_grounded"),
    "GROUNDING_REASONS": ("._sources", "GROUNDING_REASONS"),
    "load_sources_manifest": ("._sources", "load_sources_manifest"),
    "resolve_sources_path": ("._sources", "resolve_sources_path"),
    "SourcesManifest": ("._sources", "SourcesManifest"),
    "grounded_claim_ids": ("._grounded", "grounded_claim_ids"),
    # _submission_gate (HARD 1:1 question_id↔claim_id completeness gate)
    "check_submission_completeness": (
        "._submission_gate",
        "check_submission_completeness",
    ),
    "assert_submission_complete": (
        "._submission_gate",
        "assert_submission_complete",
    ),
    "SubmissionCompletenessResult": (
        "._submission_gate",
        "SubmissionCompletenessResult",
    ),
    "SubmissionCompletenessError": (
        "._submission_gate",
        "SubmissionCompletenessError",
    ),
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
    # _chain._dag (re-exported via _chain)
    "verify_dag": ("._chain", "verify_dag"),
    "verify_dag_strict": ("._chain", "verify_dag_strict"),
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
    # _attest._registry
    "ClewRegistry": ("._attest._registry", "ClewRegistry"),
    "get_registry": ("._attest._registry", "get_registry"),
    # _rerun
    "rerun_claims": ("._rerun", "rerun_claims"),
    "rerun_dag": ("._rerun", "rerun_dag"),
    "verify_by_rerun": ("._rerun", "verify_by_rerun"),
    "verify_run_from_scratch": ("._rerun", "verify_by_rerun"),
    # _attest._stamp
    "Stamp": ("._attest._stamp", "Stamp"),
    "check_stamp": ("._attest._stamp", "check_stamp"),
    "list_stamps": ("._attest._stamp", "list_stamps"),
    "stamp": ("._attest._stamp", "stamp"),
    # _tracker
    "SessionTracker": ("._tracker", "SessionTracker"),
    "get_tracker": ("._tracker", "get_tracker"),
    "set_tracker": ("._tracker", "set_tracker"),
    "start_tracking": ("._tracker", "start_tracking"),
    "stop_tracking": ("._tracker", "stop_tracking"),
    "session": ("._tracker", "session"),
    "record_input": ("._tracker", "record_input"),
    "record_output": ("._tracker", "record_output"),
    # _viz
    "generate_mermaid_dag": ("._viz", "generate_mermaid_dag"),
    "generate_html_dag": ("._viz", "generate_html_dag"),
    "render_dag": ("._viz", "render_dag"),
    "format_chain_verification": ("._viz", "format_chain_verification"),
    "format_list": ("._viz", "format_list"),
    "format_run_detailed": ("._viz", "format_run_detailed"),
    "format_run_verification": ("._viz", "format_run_verification"),
    "format_status": ("._viz", "format_status"),
    "print_verification_summary": ("._viz", "print_verification_summary"),
}


# EOF
