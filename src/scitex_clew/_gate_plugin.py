#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev pre-submission gate plugin — clew source-reachability check.

Registered via the ``scitex_dev.gate.checks`` entry point so
``scitex-dev gate --stage=pre-submission <capsule>`` discovers clew's
provenance gate when scitex-clew is installed. The check reads the capsule's
OWN clew DB (+ its registered-source manifest) and fails a submission whose
claims are not backed by a tracked ``@stx.session`` run reaching a registered
source — the v0.8.0 UNSOURCED rule, packaged as scitex-dev's plugin.

scitex-clew owns the RULE + reading its own DB; scitex-dev owns the
contract/aggregation/CLI and stays clew-agnostic (it passes ``workdir``
verbatim and never looks inside ``.scitex/clew``).

Path portability: claim ``source_file`` paths are absolute-as-recorded; this
gate runs on the capsule in-place at submission time, so they resolve. A
capsule relocated to a different absolute path could mis-resolve — out of
scope for the pre-submission-on-the-capsule use case.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

_CHECK_ID = "clew-source-reachability"
_FIX_HINT = (
    "wrap analysis in @stx.session + register claims to the run's computed "
    "output + resubmit"
)


def provide():
    """Return clew's GateCheck(s) for scitex-dev's pre-submission gate.

    scitex-dev calls this via the ``scitex_dev.gate.checks`` entry point; the
    import of ``scitex_dev.gate`` is lazy so scitex-clew never hard-depends on
    scitex-dev at import time.
    """
    from scitex_dev.gate import GateCheck

    return [
        GateCheck(
            id=_CHECK_ID,
            stage="pre-submission",
            run=_run,
            requires="",
            description=(
                "Fail a submission whose clew claims are not backed by a "
                "tracked @stx.session run reaching a registered source "
                "(no tracked runs, or a backing claim unverified/unsourced)."
            ),
        )
    ]


def _find_clew_db(workdir: Path) -> Optional[Path]:
    """Return the capsule's clew DB (prefer the canonical ``db.sqlite``).

    clew's runtime DB is ``.scitex/clew/runtime/db.sqlite`` (``.sqlite``
    extension), so glob for both ``.sqlite`` and ``.db`` to be robust.
    """
    dbs = sorted(workdir.glob(".scitex/clew/**/*.sqlite"))
    dbs += sorted(workdir.glob(".scitex/clew/**/*.db"))
    for db in dbs:
        if db.name == "db.sqlite":
            return db
    return dbs[0] if dbs else None


def _count_runs(db_path: Path) -> int:
    """Number of recorded runs (0 if the runs table is absent)."""
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _finding(message: str):
    """Build an error-severity provenance Finding with the canonical fix hint."""
    from scitex_dev.gate import Finding

    return Finding(
        check_id=_CHECK_ID,
        kind="provenance",
        message=message,
        severity="error",
        fix_hint=_FIX_HINT,
    )


def _run(workdir, config):
    """Fail a submission whose clew provenance is incomplete.

    Returns a ``GateResult(passed, findings)``: ``passed`` iff the capsule has
    >=1 tracked run AND every clew claim is verified and (when the source gate
    is active) grounded to a registered source.

    A verified-but-ungrounded claim has raw DB status ``verified``; only
    ``is_grounded`` reveals it is unsourced — so this runs clew's real gate
    (manifest + chain-walk), pointed at the capsule's own DB, rather than a
    raw-status read.
    """
    from scitex_dev.gate import GateResult

    from ._claim._register import list_claims
    from ._db import use_db
    from ._sources import is_grounded, load_sources_manifest

    workdir = Path(workdir)
    db_path = _find_clew_db(workdir)

    if db_path is None:
        return GateResult(
            passed=False,
            findings=(
                _finding(
                    "no clew database under the capsule — outputs were not "
                    "tracked by @stx.session, so no claim can reach a source"
                ),
            ),
        )

    findings: List = []

    if _count_runs(db_path) == 0:
        findings.append(
            _finding(
                "clew DB has 0 tracked runs — outputs were saved outside "
                "@stx.session, so their provenance chain reaches no source"
            )
        )

    # Per-claim source-reachability. ``use_db`` scopes clew's global DB to the
    # capsule and restores it on exit; the manifest is loaded explicitly from
    # the capsule so the gate matches THIS capsule's registered sources.
    sources_path = workdir / ".scitex" / "clew" / "sources.json"
    with use_db(db_path) as db:
        # Always pass the capsule's manifest path EXPLICITLY (even if absent) so
        # the gate never falls back to an unrelated cwd-resolved manifest; a
        # missing file loads as None => gate inactive (opt-in), scoped to THIS
        # capsule only.
        manifest = load_sources_manifest(sources_path, root=workdir)
        gate_active = manifest is not None and manifest.active
        for claim in list_claims(limit=100_000):
            ungrounded = gate_active and not is_grounded(claim, manifest, db)
            if claim.status != "verified" or ungrounded:
                reason = (
                    "reaches no registered source (unsourced)"
                    if ungrounded
                    else f"has status '{claim.status}', not verified"
                )
                findings.append(_finding(f"claim {claim.location} {reason}"))

    return GateResult(passed=not findings, findings=tuple(findings))


# EOF
