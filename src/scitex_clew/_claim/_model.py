#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim model — dataclasses, status palette, table + low-level DB helpers.

Split out of the former single-file ``_claim.py`` (over the 512-line limit).
This is the leaf module: it imports nothing else inside the ``_claim`` package,
so the register/export/verify/mutate modules can all depend on it without an
import cycle.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .._db import get_db

# Canonical claim types
CLAIM_TYPES = ("statistic", "figure", "table", "text", "value")

# ---------------------------------------------------------------------------
# Canonical status-to-hex palette (source of truth for scitex-clew;
# downstream consumers MUST read from exported claims.json).
# Hexes are locked with the live-paper consumer (scitex-writer) — do NOT
# change without a coordinated bump to both packages.
# Introduced in schema v1.1; referenced by legend block added in v1.2.
# Schema v1.3 (color-only taxonomy): "partial" renamed to "suspect";
# full-7 statuses, each a distinct CUD-accessible hue (bare 6-hex, no '#').
# Schema v1.4 (registered-source gate): adds the 8th status "unsourced" — an
# amber (#b26a00) for a claim whose provenance reaches NO registered source.
# The hue clears the CUD delta-E floor (CIE76 >= 12) of the locked 7 across
# normal/protan/deutan/tritan (see tests/scitex_clew/_claim/test__model.py).
# ---------------------------------------------------------------------------
_CLAIM_PALETTE: Dict[str, str] = {
    "verified": "2da44e",  # green
    "suspect": "d29922",  # amber
    "mismatch": "cf222e",  # red
    "missing": "a40e26",  # dark red (distinct from mismatch)
    "registered": "6e7781",  # grey
    "exception": "8250df",  # violet
    "frozen": "0072b2",  # blue (CUD/Okabe-Ito)
    "unsourced": "b26a00",  # burnt amber — ungrounded (no registered source)
}
_PALETTE_FALLBACK = "6e7781"  # grey — used for any unknown/future status

# ---------------------------------------------------------------------------
# Schema v1.3: 4-bucket display palette (reader-facing, color-only, no icons).
# Maps the 4 display buckets to accessible hex values.
# ---------------------------------------------------------------------------
_DISPLAY_PALETTE: Dict[str, str] = {
    "verified": "2da44e",
    "suspect": "d29922",
    "failed": "cf222e",
    "exception": "8250df",
    # Schema v1.4.1 (operator decision): the registered-source gate does NOT
    # get its own reader bucket — `unsourced` FOLDS into `suspect` (amber
    # "questionable"). See _DISPLAY_GROUPS below. The full-8 status palette
    # (_CLAIM_PALETTE) keeps `unsourced`=b26a00 distinct for author/DAG.
}

# ---------------------------------------------------------------------------
# Schema v1.3: per-status display_group — collapses the full-7 taxonomy to
# the MINIMAL 4-bucket reader set. registered folds into suspect (amber:
# "not confirmed"), mismatch+missing fold into failed (red), frozen folds
# into verified (green). clew still EMITS full-7 (author tooling + DAG
# fidelity); readers see only the 4 buckets.
# ---------------------------------------------------------------------------
_DISPLAY_GROUPS: Dict[str, str] = {
    "verified": "verified",
    "suspect": "suspect",
    "mismatch": "failed",
    "missing": "failed",
    "registered": "suspect",
    "exception": "exception",
    "frozen": "verified",
    # Schema v1.4.1 (operator decision): unsourced FOLDS into `suspect` (amber
    # "questionable") at the reader level — "no verified source" reads as the
    # single amber questionable state. The full-8 STATUS + _CLAIM_PALETTE keep
    # `unsourced` (b26a00) distinct for author tooling + DAG fidelity; only the
    # 4-bucket reader display + legend fold.
    "unsourced": "suspect",
}


def _resolve_status(
    status: str,
    has_exception: bool,
    has_frozen: bool,
    grounded: Optional[bool] = None,
) -> str:
    """Resolve a claim to its single full-8 status (color precedence).

    Precedence (schema v1.4, operator-approved):
    ``mismatch/missing > unsourced > [verified claims only: exception >
    frozen] > suspect > verified > registered``.

    Chain-provenance overrides (exception violet / frozen blue) apply ONLY
    to claims that have PASSED verification (``status == "verified"``). A
    never-verified (``registered``) or chain-broken (``suspect``) claim is
    NEVER promoted by its chain flags — a frozen or declared-exception
    chain must not green/violet a claim whose value was never checked
    (false-green is the cardinal sin). Failure dominance is absolute:
    ``mismatch``/``missing`` always win.

    Registered-source gate (schema v1.4)
    ------------------------------------
    ``grounded`` is the OPT-IN gate signal:

    * ``None`` (default) — the gate is INACTIVE (no manifest). Behavior is
      IDENTICAL to schema v1.3: zero change for existing DAGs / tests.
    * ``True`` — the claim's chain reaches a registered source; resolution
      falls through to the existing full-7 logic.
    * ``False`` — the gate is active and the claim reaches NO registered
      source. It resolves to ``"unsourced"`` (amber), DEMOTING what would
      otherwise be ``verified`` / ``suspect`` / ``registered``. Hash failures
      (``mismatch`` / ``missing``) still outrank ``unsourced`` — a red claim
      stays red. This is the whole point: being link-hash-verified does NOT
      exempt a claim from the source gate.

    Parameters
    ----------
    status : str
        The claim's stored status (verified, suspect, mismatch, missing,
        registered; legacy "partial" is normalized to "suspect" upstream).
    has_exception : bool
        True if the claim's provenance chain contains an exception node.
    has_frozen : bool
        True if the claim's provenance chain contains a frozen file.
    grounded : bool or None, optional
        Registered-source gate signal (see above). ``None`` keeps the gate
        inactive (opt-in).

    Returns
    -------
    str
        One of the full-8 statuses: "verified", "suspect", "mismatch",
        "missing", "registered", "exception", "frozen", "unsourced".
    """
    if status in ("mismatch", "missing"):
        return status
    # Gate active + ungrounded: demote to unsourced (outranks a would-be
    # verified/suspect/registered green; outranked only by mismatch/missing).
    if grounded is False:
        return "unsourced"
    if status == "verified":
        if has_exception:
            return "exception"
        if has_frozen:
            return "frozen"
        return "verified"
    if status == "suspect":
        return "suspect"
    return "registered"


def _resolve_display_group(
    status: str,
    has_exception: bool,
    has_frozen: bool,
    grounded: Optional[bool] = None,
) -> str:
    """Resolve the reader display group for a claim.

    Composes :func:`_resolve_status` (full-8 precedence) with the
    per-status ``_DISPLAY_GROUPS`` collapse map.

    Returns
    -------
    str
        One of: "verified", "suspect", "failed", "exception". (``unsourced``
        folds into ``suspect`` per the operator's reader-treatment decision;
        the full-8 STATUS from :func:`_resolve_status` still keeps ``unsourced``
        distinct for author tooling + DAG fidelity.)
    """
    return _DISPLAY_GROUPS[
        _resolve_status(status, has_exception, has_frozen, grounded)
    ]


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
    file_path: str,
    line_number: Optional[int],
    claim_type: str,
    claim_value: Optional[str] = None,
) -> str:
    """Generate a deterministic claim ID.

    ``claim_value`` is folded into the hash so two DISTINCT assertions sharing
    the same ``(file_path, line_number, claim_type)`` — e.g. several numbers on
    one line, or many claims registered with ``line_number=None`` — get DISTINCT
    ids instead of collapsing under ``INSERT OR REPLACE``. Re-registering the
    SAME ``(location, type, value)`` stays idempotent (same id → overwrite),
    which is the desired dedup. Callers that need a stable, human-meaningful id
    (e.g. a figure save-path) should pass ``add_claim(..., claim_id=...)``
    instead of relying on this hash.
    """
    loc = f"{file_path}:L{line_number}" if line_number else file_path
    import hashlib

    key = f"{loc}:{claim_type}:{claim_value if claim_value is not None else ''}"
    h = hashlib.sha256(key.encode()).hexdigest()[:12]
    return f"claim_{h}"


def _ensure_claims_table(db) -> None:
    """Ensure the claims table exists (run migration)."""
    migrate_add_claims_table(db.db_path)


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


# EOF
