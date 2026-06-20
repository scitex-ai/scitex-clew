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
    clew.verify_all_claims(...)        # verify every claim -> fail-loud code

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

from typing import TYPE_CHECKING

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
# Lazy decorator from scitex-dev (audit §10 cold-start)
#
# ``supports_return_as`` adds ``return_as="result"`` support. We MUST apply
# it at function-definition time to preserve that public API behaviour, but
# importing ``scitex_dev.decorators`` eagerly costs ~190ms (it pulls in
# ``scitex_dev._core.types`` + dataclasses + copy). That single import was
# pushing ``import scitex_clew`` over the audit-cli §10 500 ms threshold in
# CI py3.12.
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

# NOTE: Underscore-prefixed aliases (``_get_db`` / ``_verify_run`` / …) are
# deliberately NOT in ``_LAZY_ATTRS``. PEP 562 ``__getattr__`` is only fired
# for ``getattr(module, name)``-style lookups, not for unqualified name
# resolution inside this module's own function bodies. The convenience
# wrappers below therefore do a function-local ``from .<sub> import …``
# at first call instead — which is the canonical lazy-import idiom and
# keeps cold-start free of those submodule imports.


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
# These wrappers are defined eagerly (cheap — they're just function objects
# plus the decorator). Each body does a function-local
# ``from .<submodule> import …`` so the heavy submodule is only imported on
# first invocation. Python caches the resulting module in ``sys.modules``,
# so the local-import overhead on subsequent calls is a dict lookup.
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Public API — only these names show in dir() and tab-completion.
#
# Star-import (``from scitex_clew import *``) honours ``__all__``: every
# name listed here is either defined directly above (the convenience
# wrappers) or resolved lazily by ``__getattr__`` below.
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


# ---------------------------------------------------------------------------
# SOC R6: self-register post-save / post-load hooks with scitex-io.
#
# Audit §10 cold-start: the legacy eager ``from ._observers import …``
# pulled in _logging + _session + _tracker + _db (>125 ms). We now defer
# registration until ``scitex_io`` is actually imported, via a tiny
# ``sys.meta_path`` finder (constant-time string check per import).
# ---------------------------------------------------------------------------
def _bootstrap_io_hooks() -> None:
    import sys

    def _register_now() -> None:
        try:
            from ._observers import register_with_scitex_io

            register_with_scitex_io()
        except Exception:
            pass

    if "scitex_io" in sys.modules:
        _register_now()
        return

    class _F:
        def find_spec(self, fullname, path, target=None):
            if fullname != "scitex_io":
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


_bootstrap_io_hooks()
del _bootstrap_io_hooks


# EOF
