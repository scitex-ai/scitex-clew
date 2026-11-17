#!/usr/bin/env python3
"""Claim registration + listing — add_claim, list_claims, format_claims."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from scitex_dev.store import ANY_REVISION

from .._db import get_db
from .._db._paths import with_project_root
from ._model import (
    CLAIM_TYPES,
    Claim,
    _file_path_matches_prefix,
    _generate_claim_id,
    _row_to_claim,
)
from ._store import _open_store


def add_claim(
    file_path: str,
    claim_type: str,
    line_number: int | None = None,
    claim_value: str | None = None,
    source_file: str | None = None,
    source_session: str | None = None,
    *,
    claim_id: str | None = None,
    value=None,
    source_keys: dict | None = None,
    tolerance: dict | None = None,
    metadata: dict | None = None,
    project_root: str | Path | None = None,
) -> Claim:
    """Register a claim linking a manuscript assertion to the verification chain.

    Parameters
    ----------
    file_path : str
        Path to the manuscript file (e.g., paper.tex).
    claim_type : str
        One of: statistic, figure, table, text, value.
    line_number : int, optional
        Line number in the manuscript.
    claim_value : str, optional
        The asserted value (e.g., "p = 0.003").
    source_file : str, optional
        Path to the source file that produced this claim.
    source_session : str, optional
        Session ID that produced the source.
    claim_id : str, optional
        Explicit, stable claim id used VERBATIM as the primary key (keyword-
        only). Supply this when the caller owns a meaningful identity — e.g. a
        figure's image save-path, or a semantic key per manuscript number — so
        the id never collapses and downstream ``\\clew*{id}`` render macros can
        join on it deterministically. When omitted, the id is DERIVED from
        ``(file_path, line_number, claim_type, claim_value)`` — folding the
        value in so two distinct numbers on one line no longer collapse. Re-
        registering the same explicit id (or the same derived tuple) overwrites
        idempotently.
    value : scalar or dict, optional
        Structured claimed value (keyword-only), e.g. ``0.91`` or
        ``{"auc": 0.91, "n": 120}``. ``claim_value`` stays the display string;
        when ``value`` is omitted the display string is the checked value.
    source_keys : dict, optional
        ``{field | ".": locator}`` — where each value field lives inside
        ``source_file``: ``{"pointer": "/test/auc"}`` (RFC 6901, json/yaml) or
        ``{"row": 3 | {"col": "v"}, "column": "auc" | 2}`` (csv/tsv), each
        optionally with ``abs_tol`` / ``rel_tol``. Verification then compares
        the claimed value with the value read there (``VALUE_MISMATCH`` on
        disagreement). Same shape as scitex-writer's ``source_keys``; see
        :mod:`scitex_clew._claim._locator`. Validated here.
    tolerance : dict, optional
        Claim-level ``{"abs_tol", "rel_tol"}``. Without any declared tolerance
        the precision the value was written with is used (0.91 -> ±0.005).
    metadata : dict, optional
        Free-form JSON-serialisable caller data, stored verbatim.
    project_root : str or Path, optional
        Register into this project's scope (and resolve relative paths
        against it) without ``chdir``. Default: resolved from the cwd.

    Returns
    -------
    Claim
        The registered claim object.
    """
    if claim_type not in CLAIM_TYPES:
        raise ValueError(
            f"Invalid claim_type '{claim_type}'. Must be one of: {CLAIM_TYPES}"
        )

    from ._locator import normalize_source_keys, normalize_tolerance

    if source_keys is not None and not source_file:
        raise ValueError("source_keys needs a source_file to locate into")
    source_keys = normalize_source_keys(source_keys) or None
    tolerance = normalize_tolerance(tolerance) or None
    for name, obj in (("value", value), ("metadata", metadata)):
        try:
            json.dumps(obj)
        except (TypeError, ValueError) as e:
            raise ValueError(f"{name} must be JSON-serialisable: {e}") from e

    if project_root is not None:
        root = Path(project_root)
        file_path = str(root / file_path)  # absolute paths are kept as-is
        if source_file:
            source_file = str(root / source_file)
        from .._db._paths import project_root as _project_root

        with _project_root(root):
            return _register(
                file_path,
                claim_type,
                line_number,
                claim_value,
                source_file,
                source_session,
                claim_id,
                value,
                source_keys,
                tolerance,
                metadata,
            )
    return _register(
        file_path,
        claim_type,
        line_number,
        claim_value,
        source_file,
        source_session,
        claim_id,
        value,
        source_keys,
        tolerance,
        metadata,
    )


def _warn_external_dependencies(claim_id: str, source_file: str) -> None:
    """WARN when the claim's lineage reads files from outside the project.

    Such inputs (shared datasets, a sibling project's outputs, symlink
    targets) are part of the claim's minimal slice but can never be bundled
    with it — whoever re-runs or verifies the claim must have them at the
    recorded paths. Saying so at registration is the point where the author
    can still act (copy the data in, or document where it lives).
    """
    import warnings as _w

    from .._chain._slice import build_slice

    try:
        required = build_slice([source_file]).required_external()
    except Exception as exc:  # noqa: BLE001 - reported, never silently skipped
        _w.warn(
            f"clew.add_claim: could not check claim {claim_id} for inputs "
            f"outside the project ({type(exc).__name__}: {exc})",
            RuntimeWarning,
            stacklevel=3,
        )
        return
    if not required:
        return
    paths = [item["path"] for item in required]
    more = f", ... (+{len(paths) - 5})" if len(paths) > 5 else ""
    _w.warn(
        f"clew.add_claim: claim {claim_id} depends on {len(paths)} file(s) "
        f"outside the project: {', '.join(paths[:5])}{more} — the slice "
        f"cannot bundle them",
        RuntimeWarning,
        stacklevel=3,
    )


def _register(
    file_path,
    claim_type,
    line_number,
    claim_value,
    source_file,
    source_session,
    claim_id,
    value,
    source_keys,
    tolerance,
    metadata,
) -> Claim:
    """add_claim's body, run inside the caller's project scope."""
    file_path = str(Path(file_path).resolve())
    if claim_id is not None:
        resolved_id = str(claim_id).strip()
        if not resolved_id:
            raise ValueError("claim_id, when given, must be a non-empty string")
    else:
        resolved_id = _generate_claim_id(
            file_path, line_number, claim_type, claim_value
        )

    # Compute source hash if source_file exists
    source_hash = None
    if source_file:
        source_file = str(Path(source_file).resolve())
        source_path = Path(source_file)
        if source_path.exists():
            from .._hash import hash_file

            source_hash = hash_file(source_path)

    # Auto-detect source session if not provided
    if source_file and not source_session:
        db = get_db()
        from .._chain._routes import resolve_producer

        # The producer of the exact bytes being claimed (content hash), not
        # merely whoever last wrote this path.
        source_session = resolve_producer(db, source_file, source_hash)

    # Warn LOUD, at the point the mistake was made, when a source_file was
    # given but no owning @stx.session run produced it. Without this the claim
    # registers silently as NO_LINEAGE and the mistake only surfaces much later
    # at `clew verify --strict`. Default ON; opt out with
    # SCITEX_CLEW_WARN_NO_LINEAGE=0 (matches the auto-export opt-out style).
    if (
        source_file
        and not source_session
        and os.environ.get("SCITEX_CLEW_WARN_NO_LINEAGE", "1") != "0"
    ):
        import warnings as _w

        _w.warn(
            f"clew.add_claim: source_file '{source_file}' has no owning "
            f"@stx.session run — was it written with stx.io.save() INSIDE an "
            f"@stx.session (not raw open()/json.dump())? This claim will be "
            f"registered as NO_LINEAGE and rejected by `clew verify --strict`.",
            RuntimeWarning,
            stacklevel=2,
        )
    if source_file and source_session:
        _warn_external_dependencies(resolved_id, source_file)

    claim = Claim(
        claim_id=resolved_id,
        file_path=file_path,
        line_number=line_number,
        claim_type=claim_type,
        claim_value=claim_value,
        source_session=source_session,
        source_file=source_file,
        source_hash=source_hash,
        value=value,
        source_keys=source_keys,
        tolerance=tolerance,
        metadata=metadata,
    )

    # Store in database. ANY_REVISION preserves the old ``INSERT OR REPLACE``
    # idempotent-overwrite semantics — re-registering the same claim_id (same
    # derived (location, type, value) tuple, or the same explicit id) just
    # overwrites. ``INSERT OR REPLACE`` is a DELETE+INSERT, so every
    # re-registration used to also RESET registered_at (to the column's
    # CURRENT_TIMESTAMP default) and verified_at (to NULL) even though
    # neither was named in that SQL's column list — a Store.put() is a
    # PARTIAL update instead (omitted fields are left alone), so both are
    # passed explicitly here to keep that same reset-on-overwrite behavior.
    db = get_db()
    store = _open_store()
    try:
        store.put(
            {
                "claim_id": claim.claim_id,
                "file_path": claim.file_path,
                "line_number": claim.line_number,
                "claim_type": claim.claim_type,
                "claim_value": claim.claim_value,
                "source_session": claim.source_session,
                "source_file": claim.source_file,
                "source_hash": claim.source_hash,
                **{
                    name: (json.dumps(obj) if obj is not None else None)
                    for name, obj in (
                        ("value", value),
                        ("source_keys", source_keys),
                        ("tolerance", tolerance),
                        ("metadata", metadata),
                    )
                },
                "status": "registered",
                "registered_at": datetime.now().isoformat(),
                "verified_at": None,
            },
            expected_revision=ANY_REVISION,
        )
        # Re-registering a REMOVED claim brings it back: remove_claim hides
        # the row (a Store never deletes) and put() alone leaves it hidden.
        key = {"claim_id": claim.claim_id}
        if store.is_hidden(key):
            store.unhide(key, expected_revision=ANY_REVISION)
    finally:
        store.close()

    # Auto-export the canonical claims.json so consumers (verifier,
    # scitex-writer, human eyes) can read a stable artifact without
    # talking to the store. Default ON; opt out with
    # SCITEX_CLEW_AUTO_EXPORT_CLAIMS=0 if you're streaming thousands of
    # claims and the per-call rewrite cost matters. The cost is O(N×K)
    # where N is total claims in the DB and K is rewrite size — for
    # typical research papers (N < 100, K < 50 KB) it's negligible.
    if os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "1") != "0":
        try:
            from ._export import export_claims_json

            export_claims_json()
        except Exception as exc:  # noqa: BLE001
            # Auto-export is a convenience layer — must not break the
            # add_claim primary path if e.g. the runtime/ dir is
            # read-only on this host. Log and continue. The user can
            # call export_claims_json() explicitly to surface failures.
            import warnings as _w

            _w.warn(
                f"scitex_clew auto-export of claims.json failed "
                f"(set SCITEX_CLEW_AUTO_EXPORT_CLAIMS=0 to silence): "
                f"{exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )

    return claim


@with_project_root
def list_claims(
    file_path: str | None = None,
    claim_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    *,
    include_superseded: bool = False,
    file_path_prefix: str | None = None,
) -> list[Claim]:
    """List registered claims with optional filters.

    Parameters
    ----------
    file_path : str, optional
        Filter by manuscript file path (exact match).
    claim_type : str, optional
        Filter by claim type.
    status : str, optional
        Filter by verification status.
    limit : int
        Maximum number of claims to return.
    include_superseded : bool, optional
        When False (default), excludes claims with status ``"superseded"``
        so they do not pollute the active-claim view or fail-loud gate.
        Pass True to see the full audit trail including superseded rows.
    file_path_prefix : str, optional
        Prefix-match on file_path (resolved).  Only claims whose
        ``file_path`` starts with this prefix are returned.  If both
        ``file_path`` and ``file_path_prefix`` are given, both filters
        apply (intersection).

    Returns
    -------
    list of Claim
    """
    resolved_file_path = str(Path(file_path).resolve()) if file_path else None
    resolved_prefix = None
    if file_path_prefix:
        resolved_prefix = str(Path(file_path_prefix).resolve())
        # Ensure the prefix ends with separator so /foo/bar doesn't match /foo/barbaz
        if not resolved_prefix.endswith("/"):
            resolved_prefix = resolved_prefix + "/"

    store = _open_store()
    try:
        rows = store.rows()
    finally:
        store.close()

    # Filter comparisons run against the RAW stored status (never the
    # legacy-normalized one — the old ``WHERE status = ?`` compared against
    # the raw column too, so a caller filtering status="suspect" never
    # matched a legacy "partial" row; normalization only happens when
    # building the returned Claim, via ``_row_to_claim``).
    matched = []
    for row in rows:
        v = row.values
        if resolved_file_path is not None and v["file_path"] != resolved_file_path:
            continue
        if resolved_prefix is not None and not _file_path_matches_prefix(
            v["file_path"], resolved_prefix
        ):
            continue
        if claim_type and v["claim_type"] != claim_type:
            continue
        row_status = v["status"]
        if status and row_status != status:
            continue
        if not include_superseded and not status and row_status == "superseded":
            continue
        matched.append(row)

    # ORDER BY file_path, line_number — NULL line_number sorts first
    # in ascending order, mirrored here as a (is_not_none, value) key.
    matched.sort(
        key=lambda r: (
            r.values["file_path"] or "",
            (0, 0) if r.values["line_number"] is None else (1, r.values["line_number"]),
        )
    )
    return [_row_to_claim(r) for r in matched[:limit]]


def format_claims(claims: list[Claim], verbose: bool = False) -> str:
    """Format claims list for terminal display."""
    if not claims:
        return "No claims registered."

    lines = []
    # Schema v1.3: ASCII-ish markers only — no ⊘/🔒 status glyphs.
    status_icons = {
        "registered": "○",  # ○
        "verified": "✓",  # ✓
        "mismatch": "✗",  # ✗
        "missing": "?",
        "suspect": "~",
        "superseded": "-",
    }

    for c in claims:
        icon = status_icons.get(c.status, "?")
        loc = c.location
        val = f" = {c.claim_value}" if c.claim_value else ""
        lines.append(f"  {icon} [{c.claim_type}] {loc}{val}")
        if verbose and c.source_file:
            src = Path(c.source_file).name
            lines.append(
                f"      source: {src} (session: {c.source_session or 'unknown'})"
            )

    return "\n".join(lines)


# EOF
