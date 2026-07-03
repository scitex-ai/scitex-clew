#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core verification CLI subcommands: status, list-runs, verify, show-stats.

Extracted from ``_verification.py`` to keep each module under 512 lines.
"""

from __future__ import annotations

import json

import click

from ._claim import _json_mode


def _run_status_to_exit_code(result) -> int:
    """Map a single-run RunVerification onto the fail-loud exit-code scheme.

    A verified run -> ``OK`` (0). A locally broken run -> ``HASH_MISMATCH`` /
    ``SOURCE_MISSING``; anything else not-verified (e.g. an unknown / missing
    session) -> ``UNVERIFIED``.
    """
    from .._chain import VerificationStatus
    from ._exit_codes import HASH_MISMATCH, OK, SOURCE_MISSING, UNVERIFIED

    if result.is_verified:
        return OK
    if result.status == VerificationStatus.MISMATCH:
        return HASH_MISMATCH
    if result.status == VerificationStatus.MISSING:
        return SOURCE_MISSING
    return UNVERIFIED


def _echo_verify_all_human(result) -> None:
    """Print a git-status-like human summary of a VerificationResult."""
    from ._exit_codes import OK

    icon = "OK" if result.exit_code == OK else "FAIL"
    mode = " (strict)" if result.strict else ""
    click.echo(
        f"[{icon}] verify claims{mode}: "
        f"{result.verified}/{result.total} verified "
        f"-> {result.exit_name} (exit {result.exit_code})"
    )
    if result.reason:
        click.echo(f"  reason: {result.reason}")
    if result.warnings:
        click.echo(f"  warnings (tolerated): {', '.join(result.warnings)}")
    for c in result.claims:
        cicon = "OK" if c.outcome == "OK" else "!!"
        val = f" = {c.claim_value}" if c.claim_value else ""
        tag = "" if c.severity in ("ok", "error") else f" [{c.severity}]"
        click.echo(f"  [{cicon}] {c.outcome:<14} {c.location}{val}{tag}")


@click.command(
    epilog="Example:\n  $ scitex-clew status\n  $ scitex-clew status --json",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit JSON (also accepted at top level).",
)
@click.pass_context
def status(ctx: click.Context, as_json: bool):
    """Git-status-like overview of verification state."""
    import scitex_clew as clew

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    result = clew.status()
    # status has historically printed indented JSON; preserve that as the
    # default human output and emit pure JSON when --json is set.
    if _json_mode(ctx):
        click.echo(json.dumps(result, default=str))
    else:
        click.echo(json.dumps(result, indent=2, default=str))


@click.command(
    "list-runs",
    epilog=(
        "Example:\n"
        "  $ scitex-clew list-runs\n"
        "  $ scitex-clew list-runs --status success --limit 10 --json"
    ),
)
@click.option("--limit", type=int, default=50, help="Maximum number of runs.")
@click.option(
    "--status",
    "status_filter",
    default=None,
    help="Filter by status (success/failed/running).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def list_runs(ctx: click.Context, limit: int, status_filter, as_json: bool):
    """List tracked runs."""
    import scitex_clew as clew

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    runs = clew.list_runs(limit=limit, status=status_filter)
    if _json_mode(ctx):
        click.echo(
            json.dumps({"count": len(runs), "runs": runs}, indent=2, default=str)
        )
        return

    for r in runs:
        sid = r["session_id"]
        run_status = r.get("status", "?")
        script = r.get("script_path", "")
        click.echo(f"  {run_status:<8} {sid}  {script}")


@click.command(
    epilog=(
        "Example:\n"
        "  $ scitex-clew verify                # verify ALL registered claims\n"
        "  $ scitex-clew verify --strict       # also require @stx.session lineage\n"
        "  $ scitex-clew verify <session_id>   # verify one run, fail loud\n"
        "  $ scitex-clew verify --json"
    ),
)
@click.argument("session_id", required=False, default=None)
@click.option(
    "--strict",
    is_flag=True,
    help=(
        "Claim-set mode only: a claim passes only if its source ALSO has "
        "upstream @stx.session lineage (rejects hand-written leaves)."
    ),
)
@click.option(
    "--config",
    "config",
    type=click.Path(exists=True, dir_okay=True, file_okay=True),
    default=None,
    help=(
        "Claim-set mode only: explicit .scitex/clew config file/dir whose "
        "verify.severity map overrides the resolved user/project config."
    ),
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def verify(ctx: click.Context, session_id, strict: bool, config, as_json: bool):
    """Verify registered claims (no arg) or a specific run (SESSION_ID).

    \b
    FAIL-LOUD EXIT CODES (claim-set mode — the agent contract):
      0   OK              every registered claim is source-verified
      10  UNVERIFIED      claim(s) registered but never verified (fabrication)
      11  SOURCE_MISSING  a claim's source file is gone
      12  HASH_MISMATCH   a claim's source changed since registration
      13  NO_LINEAGE      --strict: source has no @stx.session lineage
      17  UNSOURCED       link-verified but ungrounded (no registered source);
                          only when the source gate is active (a manifest exists)
      20  NO_CLAIMS       no claims registered — nothing to verify

    A solver MUST run ``clew verify [--strict]`` before signalling DONE.
    DONE is legitimate ONLY on exit 0; any nonzero code means the agent
    must abstain honestly (null + reason) instead of claiming success.
    """
    import scitex_clew as clew

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    # ----- Claim-set mode (no SESSION_ID): the DONE-gate ------------------
    if session_id is None:
        result = clew.verify_all_claims(strict=strict, config=config)

        if _json_mode(ctx):
            click.echo(json.dumps(result.to_dict(), indent=2, default=str))
        else:
            _echo_verify_all_human(result)

        ctx.exit(result.exit_code)

    # ----- Single-run mode (SESSION_ID given): fail loud ------------------
    result = clew.run(session_id)
    code = _run_status_to_exit_code(result)

    if _json_mode(ctx):
        payload = {
            "session_id": result.session_id,
            "script_path": result.script_path,
            "status": result.status.value,
            "is_verified": result.is_verified,
            "exit_code": code,
            "files": [
                {
                    "path": f.path,
                    "role": f.role,
                    "status": f.status.value,
                    "expected_hash": f.expected_hash,
                    "current_hash": f.current_hash,
                    "is_verified": f.is_verified,
                    "frozen": getattr(f, "frozen", False),
                }
                for f in result.files
            ],
        }
        click.echo(json.dumps(payload, indent=2, default=str))
        ctx.exit(code)

    icon = "OK" if result.is_verified else "FAIL"
    click.echo(f"[{icon}] {result.session_id} ({result.status.value})")
    if getattr(result, "provenance", "tracked") == "exception":
        reason = getattr(result, "exception_reason", None) or "no reason given"
        click.echo(f"  EXCEPTION (reason: {reason})")
    for f in result.files:
        ficon = "OK" if f.is_verified else "!!"
        if getattr(f, "frozen", False):
            click.echo(
                f"  [{ficon}] {f.role:<6} FROZEN (trusted hash, not re-read): {f.path}"
            )
        else:
            click.echo(f"  [{ficon}] {f.role:<6} {f.path}")
    ctx.exit(code)


@click.command(
    "show-stats",
    epilog=("Example:\n  $ scitex-clew show-stats\n  $ scitex-clew show-stats --json"),
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def stats(ctx: click.Context, as_json: bool):
    """Database statistics."""
    import scitex_clew as clew

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    result = clew.stats()
    if _json_mode(ctx):
        click.echo(json.dumps(result, default=str))
    else:
        click.echo(json.dumps(result, indent=2, default=str))


# EOF
