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
# Public API registry (lazy map + __all__) — extracted to keep this file
# under the 512-line limit while preserving the full public surface.
# ---------------------------------------------------------------------------
from ._public_api import _LAZY_ATTRS, __all__  # noqa: E402, F401


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
