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
    typical_output_bytes : int or None
        Median total output size in bytes per run (Phase 2).  ``None`` when
        no ``size_bytes`` data is recorded (older runs / NULL rows).
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
    typical_output_bytes: Optional[int]
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
        typical_output_bytes=None,
        heavy=False,
        hint="No prior runs — cannot estimate. Run the script at least once to build history.",
        script_changed=False,
    )


def _fmt_bytes(n: int) -> str:
    """Format *n* bytes as a human-readable string (e.g. '~120 MB')."""
    for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= threshold:
            return f"~{n / threshold:.0f} {unit}"
    return f"~{n} B"


def _build_hint(
    heavy: bool,
    p90: Optional[float],
    match_tier: str,
    success_rate: Optional[float],
    typical_output_bytes: Optional[int] = None,
    reuse_hints: Optional[List[str]] = None,
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

    if typical_output_bytes is not None:
        parts.append(f"Typical output volume: {_fmt_bytes(typical_output_bytes)}.")

    if success_rate is not None and success_rate < 1.0:
        fail_pct = (1.0 - success_rate) * 100
        parts.append(f"Historical failure rate: {fail_pct:.0f}%.")

    if reuse_hints:
        parts.extend(reuse_hints)

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


def _output_bytes_for_sessions(db, session_ids: List[str]) -> List[Optional[int]]:
    """Return per-session total output bytes (None when all size_bytes are NULL)."""
    results: List[Optional[int]] = []
    for sid in session_ids:
        with db._connect() as conn:
            rows = conn.execute(
                """
                SELECT size_bytes FROM file_hashes
                WHERE session_id = ? AND role = 'output'
                """,
                (sid,),
            ).fetchall()
        sizes = [r[0] for r in rows if r[0] is not None]
        results.append(sum(sizes) if sizes else None)
    return results


def _typical_output_bytes(db, session_ids: List[str]) -> Optional[int]:
    """Median total output bytes across sessions; None if no size data exists."""
    per_session = _output_bytes_for_sessions(db, session_ids)
    known = [v for v in per_session if v is not None]
    if not known:
        return None
    return int(statistics.median(known))


def _cached_intermediate_hints(
    db,
    session_ids: List[str],
    hash_cache: "Optional[dict]" = None,
) -> List[str]:
    """Return hints when recorded inputs exist as FRESH outputs of prior sessions.

    A "fresh" artifact is one whose on-disk content hashes to the same value
    the producer session originally recorded.  PATH equality alone is not
    sufficient: a later run may have overwritten the file (stale artifact).
    Only artifacts that pass the freshness check get a reuse hint.

    Parameters
    ----------
    db : VerificationDB
        Database to query.
    session_ids : list of str
        Session IDs to check for cached-intermediate candidates.
    hash_cache : dict or None, optional
        Per-pass hash cache (see :func:`scitex_clew._hash.hash_file`).
        When provided, each unique file path is hashed at most once per
        call.  Pass ``None`` to disable caching.
    """
    from ._hash import hash_file

    hints: List[str] = []
    seen: set = set()
    for sid in session_ids:
        with db._connect() as conn:
            rows = conn.execute(
                """
                SELECT fh.file_path, r.session_id AS producer_session
                FROM file_hashes fh
                JOIN file_hashes fh2
                    ON fh2.file_path = fh.file_path AND fh2.role = 'output'
                JOIN runs r ON r.session_id = fh2.session_id
                WHERE fh.session_id = ? AND fh.role = 'input'
                  AND fh2.session_id != ?
                ORDER BY r.started_at DESC
                LIMIT 5
                """,
                (sid, sid),
            ).fetchall()
        for row in rows:
            key = (row["file_path"], row["producer_session"])
            if key in seen:
                continue
            seen.add(key)

            # --- Freshness check -------------------------------------------
            # Retrieve the hash the producer session recorded for this output.
            producer_hashes = db.get_file_hashes(
                row["producer_session"], role="output"
            )
            recorded_hash = producer_hashes.get(row["file_path"])

            # If the artifact is missing or the stored hash is unavailable,
            # we cannot vouch for freshness — skip the hint silently.
            from pathlib import Path as _Path
            artifact = _Path(row["file_path"])
            if recorded_hash is None or not artifact.exists():
                continue

            try:
                current_hash = hash_file(artifact, hash_cache=hash_cache)
            except Exception:
                continue

            # Compare truncated hashes (hash_file returns first 32 chars of
            # sha256 hex; the DB may store the same or a full hex — align by
            # comparing the shorter prefix of each).
            min_len = min(len(recorded_hash), len(current_hash))
            if recorded_hash[:min_len] != current_hash[:min_len]:
                # Artifact has changed on disk since the producer session —
                # do NOT suggest reuse of a stale intermediate.
                continue

            hints.append(
                f"Input '{row['file_path']}' already produced by session "
                f"{row['producer_session']} — consider reusing the cached intermediate."
            )
    return hints


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
    from ._chain._hash_cache import new_hash_cache

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

    # Output count and volume per session
    session_ids = [r["session_id"] for r in matched_runs]
    output_counts = _count_outputs_for_sessions(db, session_ids)
    typical_outputs: Optional[int] = (
        int(statistics.median(output_counts)) if output_counts else None
    )
    typ_bytes = _typical_output_bytes(db, session_ids)
    # Per-pass hash cache so each unique artifact is hashed at most once when
    # checking freshness across multiple candidate sessions.
    hint_hash_cache = new_hash_cache()
    reuse_hints = _cached_intermediate_hints(db, session_ids, hash_cache=hint_hash_cache)

    heavy = bool(p90 is not None and p90 > heavy_threshold)
    hint = _build_hint(
        heavy,
        p90,
        match_tier,
        success_rate,
        typical_output_bytes=typ_bytes,
        reuse_hints=reuse_hints,
    )

    return EstimateResult(
        script_path=script_path,
        match_tier=match_tier,
        run_count=n,
        p50_seconds=round(p50, 1) if p50 is not None else None,
        p90_seconds=round(p90, 1) if p90 is not None else None,
        success_rate=round(success_rate, 3) if success_rate is not None else None,
        typical_outputs=typical_outputs,
        typical_output_bytes=typ_bytes,
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
