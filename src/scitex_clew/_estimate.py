#!/usr/bin/env python3
# Timestamp: "2026-06-27 (clew-feature-impl)"
# File: src/scitex_clew/_estimate.py
"""Pre-flight compute estimate from historical run data.

Phase 1: runtime + success-rate + output-count only, zero schema change.

Usage
-----
>>> from scitex_clew import estimate
>>> result = estimate("scripts/train.py")
>>> if result.heavy:
...     print(result.hint)

CLI
---
    $ clew estimate scripts/train.py
    $ clew estimate results/fig1.png --json
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

#: p90 duration (seconds) above which the ``heavy`` flag is set.
HEAVY_THRESHOLD_SECONDS: int = 300


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class EstimateResult:
    """Pre-flight estimate for a script or target file.

    Attributes
    ----------
    script_path : str or None
        Resolved script path (None when cold-start).
    match_tier : str
        ``"exact_hash"`` — runs matched by script_hash (script unchanged).
        ``"path_history"`` — fallback: matched by script_path (script may
        have changed since last run).
        ``"unknown"`` — no prior runs at all.
    run_count : int
        Number of completed historical runs used for the estimate.
    p50_seconds : float or None
        Median wall-clock duration in seconds.
    p90_seconds : float or None
        90th-percentile wall-clock duration in seconds.
    success_rate : float or None
        Fraction of completed runs that were successful (0.0–1.0).
    typical_outputs : int or None
        Median number of output files per run.
    heavy : bool
        True when p90_seconds > HEAVY_THRESHOLD_SECONDS.
    hint : str
        Human-readable warning / suggestion string.
    script_changed : bool
        True when match_tier == ``"path_history"`` (script differs from the
        hash-matched version).
    """

    script_path: Optional[str]
    match_tier: str  # "exact_hash" | "path_history" | "unknown"
    run_count: int
    p50_seconds: Optional[float]
    p90_seconds: Optional[float]
    success_rate: Optional[float]
    typical_outputs: Optional[int]
    heavy: bool
    hint: str
    script_changed: bool

    def to_dict(self) -> dict:
        """Serialise to a plain dict (JSON-safe)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_iso(s: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string into a datetime (UTC-naive)."""
    if not s:
        return None
    try:
        # Python 3.7+: fromisoformat handles "YYYY-MM-DDTHH:MM:SS.ffffff"
        # Strip trailing Z if present for compatibility.
        return datetime.fromisoformat(s.rstrip("Z"))
    except (ValueError, TypeError):
        return None


def _duration_seconds(started_at: str, finished_at: str) -> Optional[float]:
    """Return wall-clock seconds for a completed run, or None on parse error."""
    start = _parse_iso(started_at)
    end = _parse_iso(finished_at)
    if start is None or end is None:
        return None
    delta = (end - start).total_seconds()
    return delta if delta >= 0 else None


def _percentile(values: List[float], pct: float) -> float:
    """Return the *pct*-th percentile of a sorted list (linear interpolation)."""
    if not values:
        raise ValueError("Empty sequence")
    n = len(values)
    if n == 1:
        return values[0]
    sorted_vals = sorted(values)
    # Index formula: (pct/100) * (n-1)
    idx = (pct / 100.0) * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return sorted_vals[-1]
    frac = idx - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def _build_cold_start(script_path: Optional[str]) -> EstimateResult:
    """Return a cold-start EstimateResult with no fabricated numbers."""
    return EstimateResult(
        script_path=script_path,
        match_tier="unknown",
        run_count=0,
        p50_seconds=None,
        p90_seconds=None,
        success_rate=None,
        typical_outputs=None,
        heavy=False,
        hint="No prior runs — cannot estimate. Run the script at least once to build history.",
        script_changed=False,
    )


def _build_hint(
    heavy: bool,
    p90: Optional[float],
    match_tier: str,
    success_rate: Optional[float],
) -> str:
    """Compose a human-readable summary hint."""
    parts: List[str] = []

    if match_tier == "path_history":
        parts.append("Script changed since last run — estimate from path history.")

    if heavy and p90 is not None:
        mins = p90 / 60.0
        parts.append(
            f"Long job (~{mins:.0f}m p90); consider a subset run, sbatch, or GPU."
        )
    elif p90 is not None:
        mins = p90 / 60.0
        if mins >= 1:
            parts.append(f"Estimated runtime: ~{mins:.0f}m p90.")
        else:
            parts.append(f"Estimated runtime: ~{p90:.0f}s p90.")

    if success_rate is not None and success_rate < 1.0:
        fail_pct = (1.0 - success_rate) * 100
        parts.append(f"Historical failure rate: {fail_pct:.0f}%.")

    if not parts:
        parts.append("Looks routine — no warnings.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Core estimation logic
# ---------------------------------------------------------------------------


def _query_runs_by_hash(db, script_hash: str) -> List[dict]:
    """Return completed runs whose script_hash matches exactly."""
    with db._connect() as conn:
        rows = conn.execute(
            """
            SELECT session_id, started_at, finished_at, status, exit_code
            FROM runs
            WHERE script_hash = ? AND finished_at IS NOT NULL
            ORDER BY started_at DESC
            """,
            (script_hash,),
        ).fetchall()
    return [dict(r) for r in rows]


def _query_runs_by_path(db, script_path: str) -> List[dict]:
    """Return completed runs whose script_path matches (fallback tier)."""
    with db._connect() as conn:
        rows = conn.execute(
            """
            SELECT session_id, started_at, finished_at, status, exit_code
            FROM runs
            WHERE script_path = ? AND finished_at IS NOT NULL
            ORDER BY started_at DESC
            """,
            (script_path,),
        ).fetchall()
    return [dict(r) for r in rows]


def _count_outputs_for_sessions(db, session_ids: List[str]) -> List[int]:
    """Return a list of output-file counts, one entry per session."""
    counts = []
    for sid in session_ids:
        with db._connect() as conn:
            n = conn.execute(
                """
                SELECT COUNT(*) FROM file_hashes
                WHERE session_id = ? AND role = 'output'
                """,
                (sid,),
            ).fetchone()[0]
        counts.append(n)
    return counts


def _is_successful(run: dict) -> bool:
    """Return True if the run is considered successful."""
    return run.get("status") == "success" or run.get("exit_code") == 0


def _compute_estimate(
    db,
    matched_runs: List[dict],
    match_tier: str,
    script_path: Optional[str],
    heavy_threshold: int,
) -> EstimateResult:
    """Compute statistics from a non-empty list of completed runs."""
    durations: List[float] = []
    successes: int = 0

    for r in matched_runs:
        dur = _duration_seconds(r.get("started_at", ""), r.get("finished_at", ""))
        if dur is not None:
            durations.append(dur)
        if _is_successful(r):
            successes += 1

    p50: Optional[float] = None
    p90: Optional[float] = None
    if durations:
        p50 = _percentile(durations, 50)
        p90 = _percentile(durations, 90)

    n = len(matched_runs)
    success_rate: float = successes / n if n > 0 else None  # type: ignore[assignment]

    # Output count per session
    session_ids = [r["session_id"] for r in matched_runs]
    output_counts = _count_outputs_for_sessions(db, session_ids)
    typical_outputs: Optional[int] = (
        int(statistics.median(output_counts)) if output_counts else None
    )

    heavy = bool(p90 is not None and p90 > heavy_threshold)
    hint = _build_hint(heavy, p90, match_tier, success_rate)

    return EstimateResult(
        script_path=script_path,
        match_tier=match_tier,
        run_count=n,
        p50_seconds=round(p50, 1) if p50 is not None else None,
        p90_seconds=round(p90, 1) if p90 is not None else None,
        success_rate=round(success_rate, 3) if success_rate is not None else None,
        typical_outputs=typical_outputs,
        heavy=heavy,
        hint=hint,
        script_changed=(match_tier == "path_history"),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def estimate(
    script_or_target: str,
    *,
    db=None,
    heavy_threshold: int = HEAVY_THRESHOLD_SECONDS,
) -> EstimateResult:
    """Pre-flight estimate: predict runtime and success likelihood.

    Parameters
    ----------
    script_or_target : str
        Either a path to a Python script **or** a path to a target output
        file that was produced by some script.  If it is a target file,
        the producing script is resolved via the DB's file-hash lookup.
    db : VerificationDB, optional
        Database to query.  Defaults to the global DB instance.
    heavy_threshold : int, optional
        p90 duration (seconds) above which the ``heavy`` flag is set.
        Default: :data:`HEAVY_THRESHOLD_SECONDS` (300 s / 5 min).

    Returns
    -------
    EstimateResult
        Estimation result.  When no prior runs exist, ``match_tier`` is
        ``"unknown"`` and all numeric fields are ``None`` — no numbers are
        fabricated.

    Examples
    --------
    >>> result = estimate("scripts/train.py")
    >>> print(result.hint)
    >>> result = estimate("results/fig1.png")   # resolves producing script
    """
    from ._db import get_db
    from ._hash import hash_file

    if db is None:
        db = get_db()

    arg_path = Path(script_or_target)

    # --- Resolve script path from a target file ---------------------------
    # Heuristic: if the argument looks like a non-.py file that already
    # exists, try to find its producing session via file_hashes.role='output'.
    resolved_script_path: Optional[str] = None

    if arg_path.suffix.lower() != ".py" and arg_path.exists():
        # Try to find a session that produced this file.
        session_ids = db.find_session_by_file(str(arg_path), role="output")
        if session_ids:
            # Use the most recent session's script_path.
            run_info = db.get_run(session_ids[0])
            if run_info:
                resolved_script_path = run_info.get("script_path")
    elif arg_path.suffix.lower() == ".py":
        resolved_script_path = str(arg_path)
    else:
        # Treat as script path regardless (may not exist).
        resolved_script_path = str(arg_path)

    # --- Tier 1: exact script_hash match ----------------------------------
    current_hash: Optional[str] = None
    if resolved_script_path:
        sp = Path(resolved_script_path)
        if sp.exists():
            try:
                current_hash = hash_file(sp)
            except Exception:
                current_hash = None

    exact_runs: List[dict] = []
    if current_hash:
        exact_runs = _query_runs_by_hash(db, current_hash)

    if exact_runs:
        return _compute_estimate(
            db, exact_runs, "exact_hash", resolved_script_path, heavy_threshold
        )

    # --- Tier 2: script_path fallback ------------------------------------
    if resolved_script_path:
        path_runs = _query_runs_by_path(db, resolved_script_path)
        if path_runs:
            return _compute_estimate(
                db, path_runs, "path_history", resolved_script_path, heavy_threshold
            )

    # --- Cold start -------------------------------------------------------
    return _build_cold_start(resolved_script_path)


# EOF
