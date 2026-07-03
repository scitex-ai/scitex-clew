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
    clew.estimate(script_or_target)    # pre-flight runtime/success estimate

    # Claims
    clew.add_claim(...)                # register manuscript assertion
    clew.list_claims(...)              # list registered claims
    clew.verify_claim(...)             # verify a specific claim
    clew.verify_all_claims(...)        # verify every claim -> fail-loud code

    # Citations (\\cite -> scholar-verified source gate)
    clew.add_citation(...)             # register (push) a scholar-resolved cite
    clew.list_citations(...)           # list registered citation nodes
    clew.verify_citations(entries)     # per-key {status,doi,source_id,link,reason}
    clew.verify_all_citations(entries) # fail-loud VerificationResult (same-run)

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

Implementation note (audit-all §10 cold-start)::

    This module uses the PEP 562 ``__getattr__`` lazy-import pattern. All
    submodules and re-exports below ``__version__`` are loaded on first
    access only, so ``import scitex_clew`` stays well under the 500ms
    cold-start threshold. The public attribute names listed above (and in
    ``__all__``) resolve exactly as before — no caller-visible change.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Eager: __version__ (cheap, stdlib only)
# ---------------------------------------------------------------------------
try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _v

    try:
        __version__ = _v("scitex-clew")
    except PackageNotFoundError:
        __version__ = "0.0.0+local"
    del _v, PackageNotFoundError
except ImportError:  # pragma: no cover — only on ancient Pythons
    __version__ = "0.0.0+local"


# ---------------------------------------------------------------------------
# Public API registry (lazy map) — extracted to keep this file under the
# 512-line limit while preserving the full public surface. Lives in
# ``_core/`` (a subpackage, not a flat root module, per PS-108b).
# ``__all__`` itself is declared as a literal below (PA-101 requires it
# in __init__.py).
# ---------------------------------------------------------------------------
from ._core._public_api import _LAZY_ATTRS  # noqa: E402, F401

# Public API — only these names show in dir() and tab-completion. Result
# dataclasses (e.g. EstimateResult) stay lazy-only via _LAZY_ATTRS, matching
# the convention for the other verification result types.
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
    # Claims
    "add_claim",
    "list_claims",
    "verify_claim",
    "verify_all_claims",
    "export_claims_json",
    "export_manuscript_claims",
    "register_intermediate",
    "remove_claim",
    "supersede_claim",
    # Citations (\cite -> scholar-verified source gate)
    "add_citation",
    "list_citations",
    "verify_citations",
    "verify_all_citations",
    # Registered-source gate (chain-walk grounding -> unsourced verdict)
    "register_source",
    "unregister_source",
    "list_sources",
    "is_grounded",
    "load_sources_manifest",
    "resolve_sources_path",
    "SourcesManifest",
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

# Static binding of every lazily-exported public name (PA-102 requires each
# __all__ entry to be imported/defined in __init__.py). These run only under
# type-checking, so they add zero cold-start cost; runtime resolution still
# goes through __getattr__ + _LAZY_ATTRS below.
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
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
        verify_dag,
        verify_dag_strict,
        verify_file,
        verify_run,
    )
    from ._claim import (  # noqa: F401
        Claim,
        ClaimVerification,
        VerificationResult,
        add_claim,
        export_claims_json,
        export_manuscript_claims,
        format_claims,
        list_claims,
        remove_claim,
        remove_claims_by_prefix,
        supersede_claim,
        supersede_claims_by_prefix,
        verify_all_claims,
        verify_claim,
        verify_claims_dag,
    )
    from ._citation import (  # noqa: F401
        Citation,
        add_citation,
        format_citations,
        list_citations,
        verify_all_citations,
        verify_citations,
    )
    from ._sources import (  # noqa: F401
        SourcesManifest,
        is_grounded,
        list_sources,
        load_sources_manifest,
        register_source,
        resolve_sources_path,
        unregister_source,
    )
    from ._attest._registry import ClewRegistry, get_registry  # noqa: F401
    from ._attest._stamp import (  # noqa: F401
        Stamp,
        check_stamp,
        list_stamps,
        stamp,
    )
    from ._cli._exit_codes import Severity  # noqa: F401
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
    from ._rerun import rerun_claims, rerun_dag, verify_by_rerun  # noqa: F401
    from ._tracker import (  # noqa: F401
        SessionTracker,
        get_tracker,
        set_tracker,
        start_tracking,
        stop_tracking,
    )
    from ._viz import (  # noqa: F401
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


# NOTE: Underscore-prefixed aliases (``_get_db`` / ``_verify_run`` / …) are
# deliberately NOT in ``_LAZY_ATTRS``. PEP 562 ``__getattr__`` is only fired
# for ``getattr(module, name)``-style lookups, not for unqualified name
# resolution inside this module's own function bodies. The convenience
# wrappers below therefore do a function-local ``from .<sub> import …``
# at first call instead — which is the canonical lazy-import idiom and
# keeps cold-start free of those submodule imports.


def __getattr__(name: str):
    """PEP 562 lazy attribute resolver.

    Resolves any name in :data:`_LAZY_ATTRS` by importing the backing
    submodule on demand and caching the result in module globals so future
    accesses are direct dict lookups.
    """
    spec = _LAZY_ATTRS.get(name)
    if spec is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_path, attr = spec
    from importlib import import_module

    mod = import_module(module_path, __name__)
    value = mod if attr is None else getattr(mod, attr)
    globals()[name] = value
    return value


def __dir__() -> "list[str]":
    return sorted({*globals().keys(), *_LAZY_ATTRS.keys()})


# ---------------------------------------------------------------------------
# Public convenience API
#
# The eager convenience wrappers (cheap function objects with function-local
# lazy imports) live in ``_core/_convenience.py`` (a subpackage, not a flat
# root module, per PS-108b) to keep this file under the 512-line limit.
# Importing that module adds no measurable cold-start cost — it only defines
# functions. Re-binding them here preserves the public API and PA-102 static
# binding.
# ---------------------------------------------------------------------------
from ._core._convenience import (  # noqa: E402
    chain,
    dag,
    estimate,
    list_runs,
    mermaid,
    rerun,
    run,
    stats,
    status,
)

# ---------------------------------------------------------------------------
# SOC R6: self-register clew's observer hooks with peer packages (scitex-io
# post-save/load, scitex-session lifecycle) WITHOUT those packages importing
# clew — the acyclic observer seam. clew SUBSCRIBES; the peer owns the registry.
#
# Audit §10 cold-start: the legacy eager ``from ._observers import …``
# pulled in _logging + _session + _tracker + _db (>125 ms). We defer
# registration until the peer package is actually imported, via a tiny
# ``sys.meta_path`` finder (constant-time string check per import). Handles both
# landing orders (peer-first via sys.modules check, or clew-first via finder).
# ---------------------------------------------------------------------------
def _bootstrap_pkg_hooks(module_name: str, register_attr: str) -> None:
    import sys

    def _register_now() -> None:
        try:
            from . import _observers

            getattr(_observers, register_attr)()
        except Exception:
            pass

    if module_name in sys.modules:
        _register_now()
        return

    class _F:
        def find_spec(self, fullname, path, target=None):
            if fullname != module_name:
                return None
            try:
                sys.meta_path.remove(self)
            except ValueError:
                pass
            for finder in list(sys.meta_path):
                spec = finder.find_spec(fullname, path, target)
                if spec is None:
                    continue
                orig = spec.loader

                class _L:
                    def create_module(self, s):
                        cm = getattr(orig, "create_module", None)
                        return cm(s) if cm else None

                    def exec_module(self, m):
                        orig.exec_module(m)
                        _register_now()

                spec.loader = _L()
                return spec
            return None

    sys.meta_path.insert(0, _F())


_bootstrap_pkg_hooks("scitex_io", "register_with_scitex_io")
_bootstrap_pkg_hooks("scitex_session", "register_with_scitex_session")
del _bootstrap_pkg_hooks


# EOF
