#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev pre-submission gate plugin — clew source-reachability check.

Registered via the ``scitex_dev.gate.checks`` entry point so
``scitex-dev gate --stage=pre-submission <capsule>`` discovers clew's
provenance gate when scitex-clew is installed. The check reads the host
store (+ the capsule's registered-source manifest) and fails a submission
whose claims are not backed by a tracked ``@stx.session`` run reaching a
registered source — the v0.8.0 UNSOURCED rule, packaged as scitex-dev's
plugin.

Provenance used to live in a per-capsule ``.db`` file that this module
globbed for; since the Postgres migration it lives in the host store, so
the run/claim half of the check is answered by the host running the gate
rather than by the capsule. The manifest half is still per-capsule.

scitex-clew owns the RULE + reading its own store; scitex-dev owns the
contract/aggregation/CLI and stays clew-agnostic (it passes ``workdir``
verbatim and never looks inside ``.scitex/clew``).

Path portability: claim ``source_file`` paths are absolute-as-recorded; this
gate runs on the capsule in-place at submission time, so they resolve. A
capsule relocated to a different absolute path could mis-resolve — out of
scope for the pre-submission-on-the-capsule use case.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

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


def _count_runs(db) -> int:
    """Number of recorded runs in the host store.

    ``VerificationDB``/``Store`` construction creates the ``runs`` table on
    the spot (``CREATE TABLE IF NOT EXISTS``) if it isn't there yet, so a
    never-populated store degrades to 0 rather than raising.
    """
    return len(db.list_runs(limit=100_000))


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


def _claim_ref(claim) -> str:
    """Reference a claim by its STABLE ``claim_id``, with location as a locator.

    A gate finding must name the claim by ``claim_id``, not by ``file:L42``
    alone: the location shifts on every manuscript re-write (insert one
    paragraph and every downstream line number moves), so a consumer
    correlating findings across runs — or joining them back to a submission
    keyed by ``claim_id``/``question_id`` — cannot use it as an identity.
    ``claim_id`` is clew's actual primary key and is stable by construction.

    The location is kept as a parenthesised locator because it is what a
    human needs to actually go fix the thing; dropping it would trade one
    usability problem for another. Identity first, navigation second.
    """
    location = claim.location
    if location and location != claim.claim_id:
        return f"{claim.claim_id} ({location})"
    return claim.claim_id


def _value_failure_reason(code: int) -> str:
    """Human reason for a value-integrity RE-HASH failure (distinct from unsourced).

    ``code`` is a :func:`scitex_clew._claim._verify._classify_claim` outcome for
    ONE re-verified claim (``strict=False``). The message names the concrete
    gate-time re-hash failure — the source changed (hash mismatch), the source
    is gone (missing), or the claim has no re-hashable/verified source — so a
    value failure never reads like the ungrounded ("unsourced") finding.
    """
    from ._cli._exit_codes import HASH_MISMATCH, SOURCE_MISSING

    if code == HASH_MISMATCH:
        return (
            "failed source re-hash at gate time (hash mismatch — the source "
            "file changed since the claim was registered)"
        )
    if code == SOURCE_MISSING:
        return "failed source re-hash at gate time (source file missing)"
    return (
        "is not verified at gate time (no source hashes to its recorded "
        "value — re-hash found nothing to stand behind the claim)"
    )


def _run(workdir, config):
    """Fail a submission whose clew provenance is incomplete.

    Returns a ``GateResult(passed, findings)``: ``passed`` iff the capsule has
    >=1 tracked run AND every clew claim is (a) source RE-HASH-verified at gate
    time AND (b) grounded to a registered source when the source gate is active.

    Value integrity is RE-COMPUTED here, never trusted. Each claim is
    re-verified via :func:`~scitex_clew._claim._verify.verify_claim`, which
    re-hashes the source file at submission time (and, as a side effect,
    corrects the claim's stored status in the capsule DB). A claim whose stored
    status is ``verified`` but whose source has since been edited (hash
    mismatch) or deleted (missing) is REJECTED — the gate does NOT rely on the
    flag the solver's own ``clew verify`` wrote. The value bar is
    ``_classify_claim(result, strict=False) == OK`` — i.e. the source still
    hashes to the recorded value; upstream ``@stx.session`` lineage is
    intentionally NOT required here (it is covered separately by the grounding
    half), so a legitimate raw registered source with a zero-length chain is
    not spuriously rejected.

    A verified-but-ungrounded claim re-hashes fine yet reaches no registered
    source; only ``is_grounded`` reveals it is unsourced, so the explicit
    manifest + chain-walk is kept alongside the per-claim re-hash rather than
    replaced by ``verify_all_claims`` (whose ``load_sources_manifest()`` would
    resolve a manifest from cwd, not the capsule).

    WHAT THIS GATE NO LONGER CHECKS. Before the Postgres migration the gate
    globbed ``<workdir>/.scitex/clew/**/*.db`` and read THAT capsule's own
    provenance, so a capsule submitted from another machine was judged on
    the provenance it carried. Provenance now lives in the host store and a
    capsule carries none, so the run/claim half of this gate is answered by
    the store of the host running the gate. The manifest half is still read
    from the capsule (``<workdir>/.scitex/clew/sources.json``), so which
    sources are registered is still per-capsule.
    """
    from scitex_dev.gate import GateResult

    from ._claim._register import list_claims
    from ._claim._verify import _classify_claim, verify_claim
    from ._cli._exit_codes import OK
    from ._db import get_db
    from ._sources import is_grounded, load_sources_manifest

    workdir = Path(workdir)

    findings: List = []

    # The manifest is loaded explicitly from the capsule so the gate matches
    # THIS capsule's registered sources.
    sources_path = workdir / ".scitex" / "clew" / "sources.json"
    db = get_db()
    if _count_runs(db) == 0:
        findings.append(
            _finding(
                "clew DB has 0 tracked runs — outputs were saved outside "
                "@stx.session, so their provenance chain reaches no source"
            )
        )

    # Always pass the capsule's manifest path EXPLICITLY (even if absent) so
    # the gate never falls back to an unrelated cwd-resolved manifest; a
    # missing file loads as None => gate inactive (opt-in), scoped to THIS
    # capsule only.
    manifest = load_sources_manifest(sources_path, root=workdir)
    gate_active = manifest is not None and manifest.active
    # Per-pass caches so a source shared by several claims is hashed /
    # chain-walked at most once. Created fresh each gate run, so a file
    # edited between two runs is always re-hashed (no stale entry leaks).
    hash_cache: dict = {}
    chain_cache: dict = {}
    for claim in list_claims(limit=100_000):
        # RE-HASH the source at gate time — never trust the stored status
        # flag the solver's own `clew verify` wrote. verify_claim re-computes
        # hash_file on the source; _classify_claim(strict=False) is OK iff
        # the source still hashes to the recorded value (a since-edited or
        # deleted source classifies as HASH_MISMATCH / SOURCE_MISSING).
        result = verify_claim(
            claim.claim_id, hash_cache=hash_cache, chain_cache=chain_cache
        )
        code = _classify_claim(result, strict=False)
        ungrounded = gate_active and not is_grounded(claim, manifest, db)
        # Value failure takes precedence over the grounding failure: a
        # tampered/missing source is reported as such even if it also
        # happens to be ungrounded. Exactly one finding per failing claim.
        if code != OK:
            findings.append(
                _finding(f"claim {_claim_ref(claim)} {_value_failure_reason(code)}")
            )
        elif ungrounded:
            findings.append(
                _finding(
                    f"claim {_claim_ref(claim)} reaches no registered source "
                    "(unsourced)"
                )
            )

    return GateResult(passed=not findings, findings=tuple(findings))


# EOF
