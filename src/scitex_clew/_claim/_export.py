#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim export — enriched claims.json + provenance-chain flag resolution."""

from __future__ import annotations

import importlib.metadata
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

from .._db import get_db
from ._model import (
    _CLAIM_PALETTE,
    _DISPLAY_GROUPS,
    _DISPLAY_PALETTE,
    _PALETTE_FALLBACK,
    _resolve_display_group,
    _resolve_status,
)


def _resolve_chain_flags(claim) -> tuple:
    """Derive ``chain_has_exception`` and ``chain_has_frozen`` for a claim.

    Walks the provenance DAG reachable from the claim's ``source_session``
    (or the newest producer of ``source_file`` when only that is available)
    using the **existing** :func:`scitex_clew._chain._routes.resolve_file_dag`
    walk — no custom DAG traversal here.

    Rules
    -----
    * ``chain_has_exception``: any run reachable from the starting session has
      ``provenance == 'exception'`` in the ``runs`` table.
    * ``chain_has_frozen``: any ``file_hashes`` row whose ``session_id`` is in
      the resolved session set has ``frozen == 1``.
    * If neither ``source_session`` nor ``source_file`` is present (claim has
      no computable provenance), both flags default to ``False`` — safe.
    * Never re-hashes anything: DB-metadata only, cheap per claim.

    Returns
    -------
    tuple of (bool, bool)
        ``(chain_has_exception, chain_has_frozen)``.
    """
    from .._chain._routes import resolve_file_dag

    db = get_db()

    # Determine the leaf session to start the backward DAG walk.
    session_id = claim.source_session
    if not session_id and claim.source_file:
        sessions = db.find_session_by_file(
            str(Path(claim.source_file).resolve()), role="output"
        )
        if sessions:
            session_id = sessions[0]

    if not session_id:
        # No provenance link at all — safe defaults.
        return False, False

    # Walk the provenance DAG from the leaf session backward.
    _, all_ids = resolve_file_dag([session_id], db=db)

    if not all_ids:
        return False, False

    # Build the IN-clause placeholders for the set of session IDs.
    placeholders = ", ".join("?" * len(all_ids))
    id_list = list(all_ids)

    chain_has_exception = False
    chain_has_frozen = False

    with db._connect() as conn:
        # chain_has_exception: any run has provenance == 'exception'
        row = conn.execute(
            f"SELECT 1 FROM runs WHERE session_id IN ({placeholders})"
            " AND provenance = 'exception' LIMIT 1",
            id_list,
        ).fetchone()
        if row:
            chain_has_exception = True

        # chain_has_frozen: any file_hashes row has frozen == 1
        row2 = conn.execute(
            f"SELECT 1 FROM file_hashes WHERE session_id IN ({placeholders})"
            " AND frozen = 1 LIMIT 1",
            id_list,
        ).fetchone()
        if row2:
            chain_has_frozen = True

    return chain_has_exception, chain_has_frozen


def _resolve_exception_reasons(claim) -> List[tuple]:
    """Return the list of exception nodes in a claim's provenance chain.

    Walks the SAME provenance DAG that :func:`_resolve_chain_flags` walks,
    reusing :func:`scitex_clew._chain._routes.resolve_file_dag` exactly —
    no custom traversal.

    Returns
    -------
    list of (str, str)
        ``[(session_id, reason), ...]`` for every run in the resolved session
        set whose ``provenance == 'exception'``. A NULL/empty ``exception_reason``
        in the DB is replaced by the string ``"no reason given"``.
        Returns an empty list when the claim has no provenance link or there
        are no exception nodes in the chain.
    """
    from .._chain._routes import resolve_file_dag

    db = get_db()

    # Determine the leaf session to start the backward DAG walk.
    session_id = claim.source_session
    if not session_id and claim.source_file:
        sessions = db.find_session_by_file(
            str(Path(claim.source_file).resolve()), role="output"
        )
        if sessions:
            session_id = sessions[0]

    if not session_id:
        return []

    # Walk the provenance DAG from the leaf session backward.
    _, all_ids = resolve_file_dag([session_id], db=db)

    if not all_ids:
        return []

    placeholders = ", ".join("?" * len(all_ids))
    id_list = list(all_ids)

    with db._connect() as conn:
        rows = conn.execute(
            f"SELECT session_id, exception_reason FROM runs"
            f" WHERE session_id IN ({placeholders})"
            f" AND provenance = 'exception'"
            f" ORDER BY session_id",
            id_list,
        ).fetchall()

    result = []
    for row in rows:
        sid = row[0]
        reason = row[1]
        if not reason:
            reason = "no reason given"
        result.append((sid, reason))

    return result


def export_claims_json(
    path: Optional[Union[str, Path]] = None,
    *,
    file_path_filter: Optional[str] = None,
    read_only: bool = True,
    include_superseded: bool = False,
) -> Path:
    """Export every registered claim to a canonical JSON artifact.

    The exported file is the single human-readable + machine-consumable
    view of the claims table in ``db.sqlite``. The DB remains the
    source of truth; this JSON is a regenerable artifact.

    Path resolution (mirrors :func:`scitex_clew._db._core._default_db_path`)::

        1. Explicit ``path`` argument.
        2. ``$SCITEX_CLEW_CLAIMS_JSON`` env var (escape hatch).
        3. ``<project_root>/.scitex/clew/runtime/claims.json``
           (project root = nearest ancestor dir with ``.git`` or
           ``pyproject.toml``; falls back to cwd if none found).

    Parameters
    ----------
    path : str | Path, optional
        Override the resolved path. Useful for tests / one-off dumps.
    file_path_filter : str, optional
        When set, only claims registered against this manuscript file
        path are exported. Default: every claim in the DB.
    read_only : bool, optional
        After writing, ``chmod 0o444`` the file so accidental edits
        fail loudly at the OS layer. Default True (the file IS
        derived). Set False for tests that need to mutate the file.
    include_superseded : bool, optional
        When False (default), superseded claims are excluded from the
        exported JSON — consumers should only see active claims.
        Pass True to include them (audit/debug use).

    Returns
    -------
    Path
        The path the artifact was written to (absolute).

    Examples
    --------
    >>> import scitex_clew as clew
    >>> clew.add_claim("paper.tex", "value", 42, "0.94", source_file="r.csv")
    >>> # claims.json now auto-exported under ./.scitex/clew/runtime/
    >>> clew.export_claims_json()  # idempotent — re-emit on demand
    PosixPath('.../.scitex/clew/runtime/claims.json')
    """
    from .._db import _core as _db_core
    from ._register import list_claims

    if path is None:
        env_path = os.environ.get("SCITEX_CLEW_CLAIMS_JSON")
        if env_path:
            path = Path(env_path)
        else:
            path = _db_core._default_claims_json_path(_db_core._find_project_root())
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    claims = list_claims(
        file_path=file_path_filter,
        limit=10_000,
        include_superseded=include_superseded,
    )

    # Registered-source gate (opt-in): load the manifest ONCE. Absent -> None
    # -> gate inactive (grounded stays None -> zero behavior change). Malformed
    # -> ValueError (fail loud).
    from .._sources import is_grounded, load_sources_manifest

    _manifest = load_sources_manifest()
    _gate_active = _manifest is not None and _manifest.active
    _gate_db = get_db()

    # Build per-claim dicts with v1.1 enrichment fields appended AFTER all
    # existing fields so the existing field order (and thus byte-positions for
    # streaming parsers) is unchanged.  New fields are purely additive.
    enriched_claims = []
    # Accumulate all exception nodes across all claims for top-level dedup list.
    _all_exception_pairs: Dict[str, str] = {}  # session_id -> reason (deduped)
    for c in claims:
        base = c.to_dict()  # all existing fields, byte-identical
        chain_has_exception, chain_has_frozen = _resolve_chain_flags(c)
        # Schema v1.4: registered-source gate. grounded is None when the gate
        # is inactive (no manifest) -> identical to v1.3. When active, False
        # demotes an otherwise-green claim to "unsourced".
        grounded = None
        if _gate_active:
            grounded = is_grounded(c, _manifest, _gate_db)
        # Schema v1.3/1.4: resolved full-8 status via color precedence —
        # mismatch/missing > unsourced > [verified claims only: exception >
        # frozen] > suspect > verified > registered
        resolved_status = _resolve_status(
            c.status, chain_has_exception, chain_has_frozen, grounded
        )
        base["color"] = _CLAIM_PALETTE.get(resolved_status, _PALETTE_FALLBACK)
        base["resolved_status"] = resolved_status
        base["chain_has_exception"] = chain_has_exception
        base["chain_has_frozen"] = chain_has_frozen
        # Schema v1.4 additive: per-claim groundedness (None => gate inactive).
        base["grounded"] = grounded
        # Schema v1.3: display group + display color (color-only)
        display_group = _resolve_display_group(
            c.status, chain_has_exception, chain_has_frozen, grounded
        )
        base["display_group"] = display_group
        base["display_color"] = _DISPLAY_PALETTE[display_group]
        # Schema v1.3 additive: exception_reasons for this claim's chain.
        if chain_has_exception:
            exc_pairs = _resolve_exception_reasons(c)
            base["exception_reasons"] = [reason for _, reason in exc_pairs]
            # Accumulate into the dedup dict.
            for sid, reason in exc_pairs:
                _all_exception_pairs.setdefault(sid, reason)
        else:
            base["exception_reasons"] = []
        enriched_claims.append(base)
    # ---------------------------------------------------------------------------
    # Schema v1.3: attestation + legend blocks (4-state, no subbadges).
    # ---------------------------------------------------------------------------
    try:
        _pkg_version = importlib.metadata.version("scitex-clew")
    except importlib.metadata.PackageNotFoundError:
        _pkg_version = "0.0.0"

    claims_count = len(claims)
    verified_count = sum(1 for c in claims if c.status == "verified")
    unverified_count = claims_count - verified_count
    # Schema v1.4 additive: how many claims the source gate demoted to amber.
    unsourced_count = sum(
        1 for e in enriched_claims if e["resolved_status"] == "unsourced"
    )

    # Schema v1.3: 4 display buckets — the reader's legend (color-only, no icons).
    legend_statuses = [
        {
            "status": "verified",
            "color": _DISPLAY_PALETTE["verified"],
            "marker": "wavy-underline",
            "label": "verified — matches its source",
        },
        {
            "status": "suspect",
            "color": _DISPLAY_PALETTE["suspect"],
            "marker": "wavy-underline",
            "label": (
                "suspect — not confirmed: upstream unverified, never verified, "
                "or reaches no registered source"
            ),
        },
        {
            "status": "failed",
            "color": _DISPLAY_PALETTE["failed"],
            "marker": "wavy-underline",
            "label": "failed — mismatch or missing against source",
        },
        {
            "status": "exception",
            "color": _DISPLAY_PALETTE["exception"],
            "marker": "wavy-underline",
            "label": "exception — auto-verification chain does not connect through this declared node (transparently NOT auto-verified)",
        },
        # Schema v1.4.1 (operator decision): NO separate `unsourced` legend row —
        # it folds into the amber `suspect` bucket above (see _DISPLAY_GROUPS).
    ]

    payload = {
        "_note": (
            "AUTO-GENERATED by scitex_clew.export_claims_json() from "
            "db.sqlite. Do NOT edit by hand — re-emit by calling "
            "scitex_clew.export_claims_json() (default-on after every "
            "clew.add_claim()) or by re-running your pipeline."
        ),
        "schema_version": "1.4",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # Full-8 status palette (author tooling + DAG fidelity).
        "palette": dict(_CLAIM_PALETTE),
        # 4-bucket reader palette (color-only, no icons).
        "display_palette": dict(_DISPLAY_PALETTE),
        # Per-status collapse map: full-7 status -> display bucket.
        "display_groups": dict(_DISPLAY_GROUPS),
        "claims_count": claims_count,
        "attestation": {
            "text": "Provenance checked by SciTeX Clew.",
            "tool": "scitex-clew",
            "version": _pkg_version,
            "url": "https://github.com/ywatanabe1989/scitex-clew",
            "color": _CLAIM_PALETTE["verified"],
            "verified_count": verified_count,
            "unverified_count": unverified_count,
            # Schema v1.4: source-gate demotions (0 when the gate is inactive).
            "unsourced_count": unsourced_count,
        },
        "legend": {
            "statuses": legend_statuses,
            "badge": {
                "template": "{verified} verified · {unverified} unverified",
                "all_clear": "Clew Verified — all {n} claims match source",
            },
        },
        # Schema v1.3 additive: deduped exception nodes across all claims.
        # Stable sort by session_id for determinism.
        "exceptions": [
            {"session_id": sid, "reason": reason}
            for sid, reason in sorted(_all_exception_pairs.items())
        ],
        "claims": enriched_claims,
    }

    # Clear any pre-existing read-only bit before rewriting.
    if path.exists():
        try:
            path.chmod(0o644)
        except OSError:
            pass

    path.write_text(json.dumps(payload, indent=2, default=str))

    if read_only:
        try:
            path.chmod(0o444)
        except OSError:
            # Best-effort — on filesystems that don't support unix
            # perms (e.g. some Windows mounts) this is a no-op.
            pass

    return path


# EOF
