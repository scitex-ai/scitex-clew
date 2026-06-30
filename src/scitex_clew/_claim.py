#!/usr/bin/env python3
# Timestamp: "2026-02-09 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/verify/_claim.py
"""Claim layer — link paper assertions to verification chain.

Claims represent specific assertions in manuscripts (statistics, figures,
tables) that can be traced back through the verification chain to source data.

Five claim types:
  - statistic: A numerical result (p-value, effect size, etc.)
  - figure:    A figure reference linked to a recipe/image
  - table:     A table reference linked to source CSV
  - text:      A textual assertion linked to computational output
  - value:     A specific computed value (count, percentage, etc.)
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union

from ._db import get_db

# Canonical claim types
CLAIM_TYPES = ("statistic", "figure", "table", "text", "value")

# ---------------------------------------------------------------------------
# Canonical status-to-hex palette (source of truth for scitex-clew;
# downstream consumers MUST read from exported claims.json).
# Hexes are locked with the live-paper consumer (scitex-writer) — do NOT
# change without a coordinated bump to both packages.
# Introduced in schema v1.1; referenced by legend block added in v1.2.
# Updated in schema v1.3: "partial" renamed to "suspect".
# ---------------------------------------------------------------------------
_CLAIM_PALETTE: Dict[str, str] = {
    "verified": "2da44e",
    "suspect": "d29922",
    "mismatch": "cf222e",
    "missing": "cf222e",
    "registered": "6e7781",
}
_PALETTE_FALLBACK = "6e7781"  # grey — used for any unknown/future status

# ---------------------------------------------------------------------------
# Schema v1.3: 4-state display palette (reader-facing, color-only, no icons).
# Maps the 4 display buckets to accessible hex values.
# ---------------------------------------------------------------------------
_DISPLAY_PALETTE: Dict[str, str] = {
    "verified": "2da44e",
    "suspect": "d29922",
    "unverified": "cf222e",
    "exception": "8250df",
}


def _resolve_display_group(
    status: str, has_exception: bool, has_frozen: bool
) -> str:
    """Resolve the 4-state display bucket for a claim.

    Precedence: unverified > suspect > exception > verified.
    Frozen folds into verified — it never changes the bucket.

    Parameters
    ----------
    status : str
        The claim's internal status (verified, suspect, mismatch, missing, registered).
    has_exception : bool
        True if the claim's provenance chain contains an exception node.
    has_frozen : bool
        True if the claim's provenance chain contains a frozen file.

    Returns
    -------
    str
        One of: "verified", "suspect", "unverified", "exception".
    """
    if status in ("mismatch", "missing", "registered"):
        return "unverified"
    if status == "suspect":
        return "suspect"
    if has_exception:
        return "exception"
    return "verified"  # plain verified; frozen folds in here


# ---------------------------------------------------------------------------
# Back-compat helper: normalise legacy stored "partial" -> "suspect".
# ---------------------------------------------------------------------------
_LEGACY_STATUS_MAP: Dict[str, str] = {
    "partial": "suspect",
}


@dataclass
class Claim:
    """A traceable assertion in a manuscript."""

    claim_id: str
    file_path: str
    line_number: Optional[int]
    claim_type: str
    claim_value: Optional[str]
    source_session: Optional[str]
    source_file: Optional[str]
    source_hash: Optional[str]
    registered_at: Optional[str] = None
    verified_at: Optional[str] = None
    status: str = "registered"

    @property
    def location(self) -> str:
        """Human-readable location string."""
        if self.line_number:
            return f"{self.file_path}:L{self.line_number}"
        return self.file_path

    def to_dict(self) -> Dict:
        return {
            "claim_id": self.claim_id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "claim_type": self.claim_type,
            "claim_value": self.claim_value,
            "source_session": self.source_session,
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "registered_at": self.registered_at,
            "verified_at": self.verified_at,
            "status": self.status,
        }


@dataclass
class ClaimVerification:
    """Per-claim verification outcome (one row of a :class:`VerificationResult`)."""

    claim_id: str
    location: str
    claim_value: Optional[str]
    status: Optional[str]
    source_file: Optional[str]
    source_session: Optional[str]
    source_verified: bool
    chain_verified: bool
    outcome: str  # exit-code NAME: "OK" / "UNVERIFIED" / "HASH_MISMATCH" / ...
    severity: str  # resolved severity for this outcome: error/warning/ignore/ok
    details: List[str]

    @property
    def is_verified(self) -> bool:
        return self.outcome == "OK"

    def to_dict(self) -> Dict:
        return {
            "claim_id": self.claim_id,
            "location": self.location,
            "claim_value": self.claim_value,
            "status": self.status,
            "source_file": self.source_file,
            "source_session": self.source_session,
            "source_verified": self.source_verified,
            "chain_verified": self.chain_verified,
            "outcome": self.outcome,
            "severity": self.severity,
            "details": self.details,
        }


@dataclass
class VerificationResult:
    """Structured result of ``verify_all_claims`` / ``clew verify`` (claim-set mode).

    The single object a harness branches on. ``exit_code`` is the fail-loud
    contract code (see :mod:`scitex_clew._cli._exit_codes`); ``ok`` is the
    DONE-gate. Per-pattern severity (configurable via ``.scitex/clew``) decides
    which fired patterns count as ``errors`` (fail) vs ``warnings`` (tolerated).
    ``.to_dict()`` returns the canonical CLI ``--json`` shape.
    """

    exit_code: int
    exit_name: str
    reason: str
    strict: bool
    total: int
    verified: int
    counts: Dict[str, int]
    claims: List[ClaimVerification]
    severities: Dict[str, str]  # pattern key -> resolved severity (transparency)
    errors: List[str]  # pattern NAMES that fired at ERROR severity
    warnings: List[str]  # pattern NAMES that fired at WARNING severity

    @property
    def ok(self) -> bool:
        """True iff exit_code == 0 — a solver may then legitimately signal DONE."""
        return self.exit_code == 0

    def to_dict(self) -> Dict:
        return {
            "exit_code": self.exit_code,
            "exit_name": self.exit_name,
            "reason": self.reason,
            "strict": self.strict,
            "total": self.total,
            "verified": self.verified,
            "counts": self.counts,
            "severities": self.severities,
            "errors": self.errors,
            "warnings": self.warnings,
            "claims": [c.to_dict() for c in self.claims],
        }


def migrate_add_claims_table(db_path: Path) -> None:
    """Create claims table if not present. Safe to call multiple times."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id TEXT UNIQUE NOT NULL,
                file_path TEXT NOT NULL,
                line_number INTEGER,
                claim_type TEXT NOT NULL,
                claim_value TEXT,
                source_session TEXT,
                source_file TEXT,
                source_hash TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMP,
                status TEXT DEFAULT 'registered'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_claims_file ON claims(file_path)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_claims_source ON claims(source_file)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_claims_session ON claims(source_session)"
        )
        conn.commit()
    finally:
        conn.close()


def _generate_claim_id(
    file_path: str, line_number: Optional[int], claim_type: str
) -> str:
    """Generate a deterministic claim ID."""
    loc = f"{file_path}:L{line_number}" if line_number else file_path
    import hashlib

    h = hashlib.sha256(f"{loc}:{claim_type}".encode()).hexdigest()[:12]
    return f"claim_{h}"


def add_claim(
    file_path: str,
    claim_type: str,
    line_number: Optional[int] = None,
    claim_value: Optional[str] = None,
    source_file: Optional[str] = None,
    source_session: Optional[str] = None,
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

    Returns
    -------
    Claim
        The registered claim object.
    """
    if claim_type not in CLAIM_TYPES:
        raise ValueError(
            f"Invalid claim_type '{claim_type}'. Must be one of: {CLAIM_TYPES}"
        )

    file_path = str(Path(file_path).resolve())
    claim_id = _generate_claim_id(file_path, line_number, claim_type)

    # Compute source hash if source_file exists
    source_hash = None
    if source_file:
        source_file = str(Path(source_file).resolve())
        source_path = Path(source_file)
        if source_path.exists():
            from ._hash import hash_file

            source_hash = hash_file(source_path)

    # Auto-detect source session if not provided
    if source_file and not source_session:
        db = get_db()
        sessions = db.find_session_by_file(source_file, role="output")
        if sessions:
            source_session = sessions[0]

    claim = Claim(
        claim_id=claim_id,
        file_path=file_path,
        line_number=line_number,
        claim_type=claim_type,
        claim_value=claim_value,
        source_session=source_session,
        source_file=source_file,
        source_hash=source_hash,
    )

    # Store in database
    db = get_db()
    _ensure_claims_table(db)
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO claims
                (claim_id, file_path, line_number, claim_type, claim_value,
                 source_session, source_file, source_hash, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'registered')
            """,
            (
                claim.claim_id,
                claim.file_path,
                claim.line_number,
                claim.claim_type,
                claim.claim_value,
                claim.source_session,
                claim.source_file,
                claim.source_hash,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # Auto-export the canonical claims.json so consumers (verifier,
    # scitex-writer, human eyes) can read a stable artifact without
    # talking to sqlite. Default ON; opt out with
    # SCITEX_CLEW_AUTO_EXPORT_CLAIMS=0 if you're streaming thousands of
    # claims and the per-call rewrite cost matters. The cost is O(N×K)
    # where N is total claims in the DB and K is rewrite size — for
    # typical research papers (N < 100, K < 50 KB) it's negligible.
    if os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "1") != "0":
        try:
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


def _resolve_chain_flags(claim: "Claim") -> tuple:
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

    Parameters
    ----------
    claim : Claim
        The claim to inspect.

    Returns
    -------
    tuple of (bool, bool)
        ``(chain_has_exception, chain_has_frozen)``.
    """
    from ._chain._routes import resolve_file_dag

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
    from ._db import _core as _db_core

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

    # Build per-claim dicts with v1.1 enrichment fields appended AFTER all
    # existing fields so the existing field order (and thus byte-positions for
    # streaming parsers) is unchanged.  New fields are purely additive.
    enriched_claims = []
    for c in claims:
        base = c.to_dict()  # all existing fields, byte-identical
        color = _CLAIM_PALETTE.get(c.status, _PALETTE_FALLBACK)
        chain_has_exception, chain_has_frozen = _resolve_chain_flags(c)
        base["color"] = color
        base["chain_has_exception"] = chain_has_exception
        base["chain_has_frozen"] = chain_has_frozen
        # Schema v1.3: display group + display color (4-state, color-only)
        display_group = _resolve_display_group(c.status, chain_has_exception, chain_has_frozen)
        base["display_group"] = display_group
        base["display_color"] = _DISPLAY_PALETTE[display_group]
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

    # Schema v1.3: 4 display states — the reader's legend (color-only, no icons).
    legend_statuses = [
        {
            "status": "verified",
            "color": "2da44e",
            "marker": "wavy-underline",
            "label": "verified — matches its source",
        },
        {
            "status": "suspect",
            "color": "d29922",
            "marker": "wavy-underline",
            "label": "suspect — upstream unverified, possibly contaminated",
        },
        {
            "status": "unverified",
            "color": "cf222e",
            "marker": "wavy-underline",
            "label": "unverified — could not confirm against source",
        },
        {
            "status": "exception",
            "color": "8250df",
            "marker": "wavy-underline",
            "label": "exception — author-declared, outside auto-verification",
        },
    ]

    # Static map: internal status -> display bucket (for plain/no-flag claims).
    display_groups_map: Dict[str, str] = {
        "verified": "verified",
        "suspect": "suspect",
        "mismatch": "unverified",
        "missing": "unverified",
        "registered": "unverified",
    }

    payload = {
        "_note": (
            "AUTO-GENERATED by scitex_clew.export_claims_json() from "
            "db.sqlite. Do NOT edit by hand — re-emit by calling "
            "scitex_clew.export_claims_json() (default-on after every "
            "clew.add_claim()) or by re-running your pipeline."
        ),
        "schema_version": "1.3",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "palette": dict(_CLAIM_PALETTE),
        "display_palette": dict(_DISPLAY_PALETTE),
        "display_groups": display_groups_map,
        "claims_count": claims_count,
        "attestation": {
            "text": "Provenance checked by SciTeX Clew.",
            "tool": "scitex-clew",
            "version": _pkg_version,
            "url": "https://github.com/ywatanabe1989/scitex-clew",
            "color": _CLAIM_PALETTE["verified"],
            "verified_count": verified_count,
            "unverified_count": unverified_count,
        },
        "legend": {
            "statuses": legend_statuses,
            "badge": {
                "template": "{verified} verified · {unverified} unverified",
                "all_clear": "Clew Verified — all {n} claims match source",
            },
        },
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


def list_claims(
    file_path: Optional[str] = None,
    claim_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    *,
    include_superseded: bool = False,
    file_path_prefix: Optional[str] = None,
) -> List[Claim]:
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
    db = get_db()
    _ensure_claims_table(db)

    query = "SELECT * FROM claims WHERE 1=1"
    params = []

    if file_path:
        file_path = str(Path(file_path).resolve())
        query += " AND file_path = ?"
        params.append(file_path)
    if file_path_prefix:
        resolved_prefix = str(Path(file_path_prefix).resolve())
        # Ensure the prefix ends with separator so /foo/bar doesn't match /foo/barbaz
        if not resolved_prefix.endswith("/"):
            resolved_prefix = resolved_prefix + "/"
        query += " AND (file_path LIKE ? OR file_path = ?)"
        params.append(resolved_prefix + "%")
        params.append(resolved_prefix.rstrip("/"))
    if claim_type:
        query += " AND claim_type = ?"
        params.append(claim_type)
    if status:
        query += " AND status = ?"
        params.append(status)
    if not include_superseded:
        # Exclude superseded rows unless the caller explicitly filters by
        # status="superseded" (allow explicit status filter to override).
        if not status:
            query += " AND status != 'superseded'"

    query += " ORDER BY file_path, line_number LIMIT ?"
    params.append(limit)

    conn = sqlite3.connect(str(db.db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query, params).fetchall()
        return [
            Claim(
                claim_id=row["claim_id"],
                file_path=row["file_path"],
                line_number=row["line_number"],
                claim_type=row["claim_type"],
                claim_value=row["claim_value"],
                source_session=row["source_session"],
                source_file=row["source_file"],
                source_hash=row["source_hash"],
                registered_at=row["registered_at"],
                verified_at=row["verified_at"],
                # Back-compat: normalize legacy "partial" -> "suspect"
                status=_LEGACY_STATUS_MAP.get(row["status"], row["status"]),
            )
            for row in rows
        ]
    finally:
        conn.close()


def verify_claim(
    claim_id_or_location: str,
    hash_cache: "Optional[Dict[str, str]]" = None,
    chain_cache: "Optional[Dict[str, object]]" = None,
) -> Dict:
    """Verify a specific claim by checking its source against the verification chain.

    Parameters
    ----------
    claim_id_or_location : str
        Either a claim_id or a location string like "paper.tex:L42".
    hash_cache : dict or None, optional
        Per-pass cache mapping resolved-path -> hash (see
        :func:`scitex_clew._hash.hash_file`). When provided, a source file
        shared by multiple claims is hashed at most once per pass. Pass
        ``None`` (default) to disable caching — direct callers are unaffected.
    chain_cache : dict or None, optional
        Per-pass memo mapping ``str(resolved source_file)`` ->
        :class:`~scitex_clew._chain.ChainVerification`. When provided, the
        full chain walk (``verify_chain``) for a source_file that appears on
        multiple claims is executed at most once per :func:`verify_all_claims`
        pass. Pass ``None`` (default) to disable memoization — direct callers
        are unaffected.

    Returns
    -------
    dict
        Verification result with claim details and chain status.
    """
    db = get_db()
    _ensure_claims_table(db)

    claim = _resolve_claim(claim_id_or_location, db)
    if not claim:
        return {
            "status": "not_found",
            "message": f"No claim found for '{claim_id_or_location}'",
        }

    result = {
        "claim": claim.to_dict(),
        "source_verified": False,
        "chain_verified": False,
        "details": [],
    }

    # Check source file exists and hash matches
    if claim.source_file:
        source_path = Path(claim.source_file)
        if not source_path.exists():
            result["details"].append(f"Source file missing: {claim.source_file}")
            _update_claim_status(claim.claim_id, "missing", db)
            result["claim"]["status"] = "missing"
            return result

        from ._hash import hash_file

        current_hash = hash_file(source_path, hash_cache=hash_cache)
        if (
            claim.source_hash
            and current_hash[: len(claim.source_hash)]
            == claim.source_hash[: len(current_hash)]
        ):
            result["source_verified"] = True
            result["details"].append("Source file hash matches")
        else:
            result["details"].append(
                f"Source hash mismatch: stored={claim.source_hash}, current={current_hash}"
            )
            _update_claim_status(claim.claim_id, "mismatch", db)
            result["claim"]["status"] = "mismatch"
            return result

    # Verify the chain if we have a source file
    if claim.source_file:
        from ._chain import verify_chain

        try:
            # Per-pass chain memo: avoid re-walking the same source chain when
            # multiple claims share one source_file (strict-mode perf).
            chain_key = str(Path(claim.source_file).resolve())
            if chain_cache is not None and chain_key in chain_cache:
                chain = chain_cache[chain_key]
            else:
                chain = verify_chain(claim.source_file)
                if chain_cache is not None:
                    chain_cache[chain_key] = chain
            result["chain_verified"] = chain.is_verified
            if chain.is_verified:
                result["details"].append(f"Chain verified ({len(chain.runs)} runs)")
            else:
                result["details"].append(
                    f"Chain verification failed ({len(chain.failed_runs)} failed runs)"
                )
        except Exception as e:
            result["details"].append(f"Chain verification error: {e}")

    # Update status
    if result["source_verified"] and result["chain_verified"]:
        _update_claim_status(claim.claim_id, "verified", db)
        result["claim"]["status"] = "verified"
    elif result["source_verified"]:
        _update_claim_status(claim.claim_id, "suspect", db)
        result["claim"]["status"] = "suspect"

    return result


def verify_claims_dag(
    file_path: Optional[str] = None,
    claim_type: Optional[str] = None,
) -> DAGVerification:
    """Build a unified DAG from all claims, tracing each back to its source.

    Parameters
    ----------
    file_path : str, optional
        Filter claims by manuscript file path.
    claim_type : str, optional
        Filter claims by type.

    Returns
    -------
    DAGVerification
        Unified verification result covering all claim source chains merged.
    """
    from ._chain import DAGVerification, VerificationStatus
    from ._dag import verify_dag

    claims = list_claims(file_path=file_path, claim_type=claim_type)

    # Collect unique source files from claims
    source_files = []
    for c in claims:
        if c.source_file and c.source_file not in source_files:
            source_files.append(c.source_file)

    if not source_files:
        return DAGVerification(
            target_files=[],
            runs=[],
            edges=[],
            status=VerificationStatus.UNKNOWN,
            topological_order=[],
        )

    return verify_dag(source_files)


def _classify_claim(result: Dict, *, strict: bool) -> int:
    """Classify a single ``verify_claim`` result into an exit code.

    Maps the per-claim verification outcome onto the documented fail-loud
    exit-code contract in :mod:`scitex_clew._cli._exit_codes`. Returns the
    code for *this one claim* (the caller reduces over the whole set).

    Decision tree (per claim):

    * No ``source_file`` linked → ``UNVERIFIED`` (the fabrication case: a
      claim registered against nothing computable — exactly the hand-coded
      ``results.json`` story).
    * Source file gone → ``SOURCE_MISSING``.
    * Stored hash != current hash → ``HASH_MISMATCH``.
    * Source hash matches but the claim was never marked verified
      (``verified_at`` is null AND status is still ``registered``) →
      ``UNVERIFIED``.
    * Source verified:
        * non-strict → ``OK`` (hash match is the bar).
        * strict and chain NOT verified → ``NO_LINEAGE`` (hand-written
          leaf, no ``@stx.session`` provenance upstream).
        * strict and chain verified → ``OK``.
    """
    from ._cli._exit_codes import (
        HASH_MISMATCH,
        NO_LINEAGE,
        OK,
        SOURCE_MISSING,
        UNVERIFIED,
    )

    claim = result.get("claim", {})
    status = claim.get("status")
    source_file = claim.get("source_file")
    verified_at = claim.get("verified_at")

    # No computable source at all — the canonical fabrication case.
    if not source_file:
        return UNVERIFIED

    if status == "missing":
        return SOURCE_MISSING
    if status == "mismatch":
        return HASH_MISMATCH

    if result.get("source_verified"):
        if strict and not result.get("chain_verified"):
            return NO_LINEAGE
        return OK

    # Source linked but neither verified nor explicitly failed: it was
    # never put through a real verification pass (verified_at null).
    if not verified_at:
        return UNVERIFIED

    # Fallback — any other not-verified state is treated as unverified.
    return UNVERIFIED


def verify_all_claims(
    file_path: Optional[str] = None,
    claim_type: Optional[str] = None,
    *,
    strict: bool = False,
    config: Optional[Union[str, Path]] = None,
) -> "VerificationResult":
    """Verify every registered claim and reduce to a fail-loud result.

    This is the reusable core behind ``clew verify`` (claim-set mode). It
    re-verifies each claim (re-hashing its source and, in ``strict`` mode,
    checking upstream ``@stx.session`` lineage), updates each claim's stored
    status as a side effect (via :func:`verify_claim`), and reduces the
    per-claim outcomes to a single :class:`VerificationResult`.

    Parameters
    ----------
    file_path : str, optional
        Restrict to claims registered against this manuscript path.
    claim_type : str, optional
        Restrict to claims of this type.
    strict : bool, optional
        When True, a claim only passes if its source additionally has
        upstream computation lineage (its provenance chain verifies).
        A hand-written leaf (no ``@stx.session`` behind it) fails with
        ``NO_LINEAGE`` even though its hash matches. ``strict`` also promotes
        ``NO_LINEAGE`` to ERROR severity regardless of config. Default False.
    config : str or pathlib.Path, optional
        Explicit ``.scitex/clew`` config file/dir overriding the resolved
        user/project severity map (see :mod:`scitex_clew._core._config`).

    Returns
    -------
    VerificationResult
        Structured outcome. ``result.exit_code == 0`` (``result.ok``) is the
        DONE-gate; any nonzero code means the agent MUST abstain honestly
        instead of claiming success. Per-pattern severity (configurable via
        ``.scitex/clew``) decides which fired patterns are ``errors`` (fail)
        vs ``warnings`` (tolerated). See :mod:`scitex_clew._cli._exit_codes`.
    """
    from ._cli._exit_codes import (
        KEY_BY_CODE,
        NO_CLAIMS,
        OK,
        classify_exit,
        name_of,
        reason_of,
        resolve_severity,
    )

    severities = resolve_severity(explicit=config, strict=strict)
    severity_view = {KEY_BY_CODE[code]: lvl.value for code, lvl in severities.items()}

    claims = list_claims(file_path=file_path, claim_type=claim_type, limit=10_000)

    if not claims:
        exit_code, errors, warnings = classify_exit([NO_CLAIMS], severities)
        return VerificationResult(
            exit_code=exit_code,
            exit_name=name_of(exit_code),
            reason=reason_of(exit_code),
            strict=strict,
            total=0,
            verified=0,
            counts={name_of(NO_CLAIMS): 1},
            claims=[],
            severities=severity_view,
            errors=errors,
            warnings=warnings,
        )

    # Perf B: one hash_cache per pass so a source file shared by N claims is
    # hashed exactly once (O(D) instead of O(C·D)).  The cache is fresh every
    # call to verify_all_claims so a file changed between two independent passes
    # is always re-hashed — no stale entries leak across passes.
    from ._chain._hash_cache import new_hash_cache

    hash_cache = new_hash_cache()
    # Strict-mode chain memo: in strict mode, verify_chain(source_file) walks
    # upstream provenance — O(depth) per unique source.  Claims sharing one
    # source_file would otherwise re-walk the same chain O(C) times.  The memo
    # is keyed by str(resolved source_file) and populated on first encounter so
    # each unique chain is walked at most once per pass.  A fresh dict is
    # created each call so no stale entries leak across independent passes.
    chain_cache: Dict[str, object] = {}

    per_claim: List[ClaimVerification] = []
    per_codes: List[int] = []
    verified = 0
    counts: Dict[str, int] = {}

    for c in claims:
        result = verify_claim(c.claim_id, hash_cache=hash_cache, chain_cache=chain_cache)
        code = _classify_claim(result, strict=strict)
        per_codes.append(code)
        cname = name_of(code)
        counts[cname] = counts.get(cname, 0) + 1
        if code == OK:
            verified += 1

        rclaim = result.get("claim", {})
        sev = "ok" if code == OK else severities[code].value
        per_claim.append(
            ClaimVerification(
                claim_id=c.claim_id,
                location=c.location,
                claim_value=c.claim_value,
                status=rclaim.get("status", c.status),
                source_file=rclaim.get("source_file", c.source_file),
                source_session=rclaim.get("source_session", c.source_session),
                source_verified=result.get("source_verified", False),
                chain_verified=result.get("chain_verified", False),
                outcome=cname,
                severity=sev,
                details=result.get("details", []),
            )
        )

    exit_code, errors, warnings = classify_exit(per_codes, severities)
    return VerificationResult(
        exit_code=exit_code,
        exit_name=name_of(exit_code),
        reason=reason_of(exit_code),
        strict=strict,
        total=len(claims),
        verified=verified,
        counts=counts,
        claims=per_claim,
        severities=severity_view,
        errors=errors,
        warnings=warnings,
    )


def _resolve_claim(identifier: str, db) -> Optional[Claim]:
    """Resolve a claim by ID or location string."""
    conn = sqlite3.connect(str(db.db_path))
    conn.row_factory = sqlite3.Row
    try:
        # Try claim_id first
        row = conn.execute(
            "SELECT * FROM claims WHERE claim_id = ?", (identifier,)
        ).fetchone()

        if not row:
            # Try location format: file.tex:L42
            match = re.match(r"^(.+):L(\d+)$", identifier)
            if match:
                fpath = str(Path(match.group(1)).resolve())
                line = int(match.group(2))
                row = conn.execute(
                    "SELECT * FROM claims WHERE file_path = ? AND line_number = ?",
                    (fpath, line),
                ).fetchone()

        if not row:
            # Try file path only (returns first match)
            fpath = str(Path(identifier).resolve())
            row = conn.execute(
                "SELECT * FROM claims WHERE file_path = ? ORDER BY line_number LIMIT 1",
                (fpath,),
            ).fetchone()

        if row:
            return Claim(
                claim_id=row["claim_id"],
                file_path=row["file_path"],
                line_number=row["line_number"],
                claim_type=row["claim_type"],
                claim_value=row["claim_value"],
                source_session=row["source_session"],
                source_file=row["source_file"],
                source_hash=row["source_hash"],
                registered_at=row["registered_at"],
                verified_at=row["verified_at"],
                # Back-compat: normalize legacy "partial" -> "suspect"
                status=_LEGACY_STATUS_MAP.get(row["status"], row["status"]),
            )
        return None
    finally:
        conn.close()


def _update_claim_status(claim_id: str, status: str, db) -> None:
    """Update claim verification status."""
    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute(
            "UPDATE claims SET status = ?, verified_at = ? WHERE claim_id = ?",
            (status, datetime.now().isoformat(), claim_id),
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_claims_table(db) -> None:
    """Ensure the claims table exists (run migration)."""
    migrate_add_claims_table(db.db_path)


def format_claims(claims: List[Claim], verbose: bool = False) -> str:
    """Format claims list for terminal display."""
    if not claims:
        return "No claims registered."

    lines = []
    status_icons = {
        "registered": "\u25cb",  # ○
        "verified": "\u2713",  # ✓
        "mismatch": "\u2717",  # ✗
        "missing": "?",
        "suspect": "~",
        "superseded": "⊘",  # ⊘
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


def remove_claim(claim_id_or_location: str) -> bool:
    """Hard-delete a claim from the database.

    Permanently removes the claim row identified by ``claim_id_or_location``
    (a claim_id string, a location like ``"paper.tex:L42"``, or a bare file
    path — resolved via the same logic as :func:`verify_claim`).

    After deletion :func:`export_claims_json` is called so the JSON
    artifact stays in sync with the DB.

    Parameters
    ----------
    claim_id_or_location : str
        Claim identifier.  Resolution order:
        1. Exact ``claim_id`` match.
        2. Location string ``"file.tex:L42"``.
        3. File path only (first row).

    Returns
    -------
    bool
        ``True`` if a row was deleted; ``False`` if nothing matched.
    """
    db = get_db()
    _ensure_claims_table(db)

    claim = _resolve_claim(claim_id_or_location, db)
    if claim is None:
        return False

    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute("DELETE FROM claims WHERE claim_id = ?", (claim.claim_id,))
        conn.commit()
    finally:
        conn.close()

    if os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "1") != "0":
        try:
            export_claims_json()
        except Exception as exc:  # noqa: BLE001
            import warnings as _w

            _w.warn(
                f"scitex_clew auto-export of claims.json failed after "
                f"remove_claim: {exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )

    return True


def remove_claims_by_prefix(file_path_prefix: str) -> int:
    """Hard-delete all claims whose file_path starts with ``file_path_prefix``.

    Parameters
    ----------
    file_path_prefix : str
        Path prefix (resolved).  All claims under this root are deleted.

    Returns
    -------
    int
        Number of rows deleted.
    """
    db = get_db()
    _ensure_claims_table(db)

    resolved_prefix = str(Path(file_path_prefix).resolve())
    if not resolved_prefix.endswith("/"):
        resolved_prefix = resolved_prefix + "/"

    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute(
            "DELETE FROM claims WHERE file_path LIKE ? OR file_path = ?",
            (resolved_prefix + "%", resolved_prefix.rstrip("/")),
        )
        conn.commit()
        deleted = conn.execute("SELECT changes()").fetchone()[0]
    finally:
        conn.close()

    if os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "1") != "0":
        try:
            export_claims_json()
        except Exception as exc:  # noqa: BLE001
            import warnings as _w

            _w.warn(
                f"scitex_clew auto-export of claims.json failed after "
                f"remove_claims_by_prefix: {exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )

    return deleted


def supersede_claim(claim_id_or_location: str) -> bool:
    """Soft-retire a claim by setting its status to ``"superseded"``.

    The row is kept in the database (audit trail) but excluded from the
    default :func:`list_claims` view (``include_superseded=False`` is the
    default), from :func:`verify_all_claims`, and from the default
    :func:`export_claims_json` output.

    This allows a user to retire stale/dead claims so that ``clew verify``
    can reach exit 0 without deleting the historical record.

    Parameters
    ----------
    claim_id_or_location : str
        Claim identifier resolved the same way as :func:`remove_claim`.

    Returns
    -------
    bool
        ``True`` if the claim existed and was updated; ``False`` if nothing
        matched.
    """
    db = get_db()
    _ensure_claims_table(db)

    claim = _resolve_claim(claim_id_or_location, db)
    if claim is None:
        return False

    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute(
            "UPDATE claims SET status = 'superseded', verified_at = ? WHERE claim_id = ?",
            (datetime.now().isoformat(), claim.claim_id),
        )
        conn.commit()
    finally:
        conn.close()

    if os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "1") != "0":
        try:
            export_claims_json()
        except Exception as exc:  # noqa: BLE001
            import warnings as _w

            _w.warn(
                f"scitex_clew auto-export of claims.json failed after "
                f"supersede_claim: {exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )

    return True


def supersede_claims_by_prefix(file_path_prefix: str) -> int:
    """Soft-retire all claims whose file_path starts with ``file_path_prefix``.

    Parameters
    ----------
    file_path_prefix : str
        Path prefix (resolved).

    Returns
    -------
    int
        Number of rows updated to status ``"superseded"``.
    """
    db = get_db()
    _ensure_claims_table(db)

    resolved_prefix = str(Path(file_path_prefix).resolve())
    if not resolved_prefix.endswith("/"):
        resolved_prefix = resolved_prefix + "/"

    conn = sqlite3.connect(str(db.db_path))
    try:
        conn.execute(
            "UPDATE claims SET status = 'superseded', verified_at = ? "
            "WHERE file_path LIKE ? OR file_path = ?",
            (
                datetime.now().isoformat(),
                resolved_prefix + "%",
                resolved_prefix.rstrip("/"),
            ),
        )
        conn.commit()
        updated = conn.execute("SELECT changes()").fetchone()[0]
    finally:
        conn.close()

    if os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", "1") != "0":
        try:
            export_claims_json()
        except Exception as exc:  # noqa: BLE001
            import warnings as _w

            _w.warn(
                f"scitex_clew auto-export of claims.json failed after "
                f"supersede_claims_by_prefix: {exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )

    return updated


__all__ = [
    "CLAIM_TYPES",
    "Claim",
    "add_claim",
    "list_claims",
    "verify_claim",
    "verify_claims_dag",
    "format_claims",
    "migrate_add_claims_table",
    "remove_claim",
    "remove_claims_by_prefix",
    "supersede_claim",
    "supersede_claims_by_prefix",
]
