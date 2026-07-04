#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``grounded_claim_ids`` — the claim_ids whose claims are verified AND grounded.

A GENERIC provenance primitive for consumers that need the set of claims backed
by real, source-reaching provenance, keyed by their external ``claim_id``. The
motivating consumer is a cohort submission-completeness check that diffs a
submission's ids against the grounded ids (missing = submission − grounded;
orphan = grounded − submission) — but clew stays generic: it knows nothing about
the consumer's id semantics (question_ids etc.), it only reports which claim_ids
have grounded provenance.

"Grounded" here reuses the gate's exact rule: a claim is included iff its DB
status is ``verified`` AND — when the source gate is active — ``is_grounded``
(its chain reaches a registered, and if signing is enforced a valid, source).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union


def grounded_claim_ids(
    workdir: Optional[Union[str, Path]] = None,
    *,
    db_path: Optional[Union[str, Path]] = None,
    sources_path: Optional[Union[str, Path]] = None,
) -> List[str]:
    """Return the SORTED, de-duplicated claim_ids that are verified AND grounded.

    The returned ids are the claims' ``claim_id`` column values. NOTE: ``add_claim``
    auto-generates a ``claim_<hex>`` id when none is passed, so every claim has an
    id — in a flow where the consumer sets an explicit ``claim_id`` on every claim
    (e.g. one per submission answer), the returned ids ARE those consumer keys with
    no auto-generated noise; a claim added WITHOUT an explicit id appears under its
    auto id.

    Parameters
    ----------
    workdir : str | Path, optional
        Capsule/project dir. When given (and ``db_path`` is not), the clew DB is
        located under ``<workdir>/.scitex/clew/**`` and the sources manifest at
        ``<workdir>/.scitex/clew/sources.json`` (unless ``sources_path`` is set).
    db_path : str | Path, optional
        Explicit clew DB path (overrides the workdir DB search).
    sources_path : str | Path, optional
        Explicit sources manifest path.

    Returns
    -------
    list of str
        Sorted unique grounded claim_ids (empty if no DB / no grounded claims).
    """
    from ._claim._register import list_claims
    from ._db import use_db
    from ._gate_plugin import _find_clew_db
    from ._sources import is_grounded, load_sources_manifest

    wd = Path(workdir) if workdir is not None else None

    if db_path is not None:
        resolved_db: Optional[Path] = Path(db_path)
    elif wd is not None:
        resolved_db = _find_clew_db(wd)
    else:
        resolved_db = None
    if resolved_db is None:
        return []

    if sources_path is not None:
        src: Optional[Path] = Path(sources_path)
    elif wd is not None:
        src = wd / ".scitex" / "clew" / "sources.json"
    else:
        src = None

    out = set()
    with use_db(resolved_db) as db:
        manifest = load_sources_manifest(src, root=wd)
        gate_active = manifest is not None and manifest.active
        for claim in list_claims(limit=100_000):
            cid = getattr(claim, "claim_id", None)
            if not cid:
                continue
            if claim.status != "verified":
                continue
            if gate_active and not is_grounded(claim, manifest, db):
                continue
            out.add(str(cid))
    return sorted(out)
