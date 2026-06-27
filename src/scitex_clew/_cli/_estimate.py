#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI subcommand: ``clew estimate <script_or_target> [--json]``.

Pre-flight compute estimate from historical run data (Phase 1).
"""

from __future__ import annotations

import json

import click

from ._claim import _json_mode


@click.command(
    "estimate",
    epilog=(
        "Examples:\n"
        "  $ clew estimate scripts/train.py\n"
        "  $ clew estimate results/fig1.png\n"
        "  $ clew estimate scripts/train.py --json"
    ),
)
@click.argument("script_or_target")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def estimate(ctx: click.Context, script_or_target: str, as_json: bool) -> None:
    """Pre-flight runtime/success estimate for a script or target file.

    SCRIPT_OR_TARGET can be:

    \b
      - a Python script path  (estimates that script directly)
      - a target output file  (resolved to its producing script via the DB)

    Shows p50/p90 runtime, success rate, typical #outputs, and a heavy-job
    warning when the estimated p90 runtime exceeds 5 minutes.

    Match tiers:

    \b
      exact_hash   — script unchanged since last run (most reliable)
      path_history — script changed; using path-matched history (annotated)
      unknown      — no prior runs; cannot estimate
    """
    from scitex_clew._estimate import estimate as _estimate

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    result = _estimate(script_or_target)

    if _json_mode(ctx):
        click.echo(json.dumps(result.to_dict(), indent=2, default=str))
        return

    # Human-readable output
    _echo_estimate_human(result)


def _echo_estimate_human(result) -> None:
    """Print a compact human summary of an EstimateResult."""
    tier_label = {
        "exact_hash": "exact match (script unchanged)",
        "path_history": "path history (script changed)",
        "unknown": "no prior history",
    }.get(result.match_tier, result.match_tier)

    click.echo(f"Estimate for: {result.script_path or '(unknown)'}")
    click.echo(f"  Match tier    : {tier_label}")
    click.echo(f"  Run count     : {result.run_count}")

    if result.p50_seconds is not None:
        p50_str = _fmt_duration(result.p50_seconds)
        p90_str = _fmt_duration(result.p90_seconds) if result.p90_seconds is not None else "n/a"
        click.echo(f"  Duration p50  : {p50_str}")
        click.echo(f"  Duration p90  : {p90_str}")
    else:
        click.echo("  Duration      : n/a")

    if result.success_rate is not None:
        click.echo(f"  Success rate  : {result.success_rate * 100:.0f}%")
    else:
        click.echo("  Success rate  : n/a")

    if result.typical_outputs is not None:
        click.echo(f"  Typical #outputs: {result.typical_outputs}")
    else:
        click.echo("  Typical #outputs: n/a")

    if result.heavy:
        click.echo(f"  [HEAVY] {result.hint}")
    elif result.match_tier == "unknown":
        click.echo(f"  [INFO] {result.hint}")
    else:
        click.echo(f"  [OK] {result.hint}")


def _fmt_duration(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{minutes:.1f}m"
    hours = minutes / 60.0
    return f"{hours:.1f}h"


# EOF
