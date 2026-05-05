#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim CLI subcommands — `clew claim {add,list,verify}`.

Mirrors the Python API in ``scitex_clew._claim`` one-for-one. Each command
respects the top-level ``--json`` flag (set on ``ctx.obj['json']``) and
emits human-readable text by default.
"""

from __future__ import annotations

import json as _json

import click


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json_mode(ctx: click.Context) -> bool:
    """Return True if the user requested JSON output (--json at any level)."""
    if ctx.obj and ctx.obj.get("json"):
        return True
    # Walk parents to find a --json flag set somewhere.
    parent = ctx.parent
    while parent is not None:
        if parent.obj and parent.obj.get("json"):
            return True
        parent = parent.parent
    return False


def _emit(ctx: click.Context, payload, human_text: str) -> None:
    """Emit ``payload`` as JSON or ``human_text`` depending on output mode."""
    if _json_mode(ctx):
        click.echo(_json.dumps(payload, indent=2, default=str))
    else:
        click.echo(human_text)


# ---------------------------------------------------------------------------
# `clew claim` group
# ---------------------------------------------------------------------------


@click.group("claim")
def claim() -> None:
    """Manuscript-claim operations (add / list / verify)."""


@claim.command("add")
@click.option(
    "--file-path",
    "file_path",
    required=True,
    help="Path to the manuscript file (e.g., paper.tex).",
)
@click.option(
    "--type",
    "claim_type",
    required=True,
    type=click.Choice(["statistic", "figure", "table", "text", "value"]),
    help="Claim type.",
)
@click.option(
    "--line-number",
    "line_number",
    type=int,
    default=None,
    help="Line number in the manuscript.",
)
@click.option(
    "--value",
    "claim_value",
    default=None,
    help="The asserted value (e.g., 'p = 0.003').",
)
@click.option(
    "--source-file",
    "source_file",
    default=None,
    help="Path to the source file that produced this claim.",
)
@click.option(
    "--source-session",
    "source_session",
    default=None,
    help="Session ID that produced the source.",
)
@click.pass_context
def claim_add(
    ctx: click.Context,
    file_path: str,
    claim_type: str,
    line_number,
    claim_value,
    source_file,
    source_session,
) -> None:
    """Register a claim linking a manuscript assertion to the verification chain."""
    from scitex_clew import add_claim

    try:
        c = add_claim(
            file_path=file_path,
            claim_type=claim_type,
            line_number=line_number,
            claim_value=claim_value,
            source_file=source_file,
            source_session=source_session,
        )
    except ValueError as exc:
        msg = {"error": str(exc), "claim": None}
        if _json_mode(ctx):
            click.echo(_json.dumps(msg, indent=2))
        else:
            click.echo(f"ERROR: {exc}", err=True)
        ctx.exit(1)

    payload = c.to_dict()
    human = (
        f"[ADDED] claim {c.claim_id}\n"
        f"  type:     {c.claim_type}\n"
        f"  location: {c.location}\n"
        f"  value:    {c.claim_value or '(none)'}\n"
        f"  source:   {c.source_file or '(none)'}"
    )
    _emit(ctx, payload, human)


@claim.command("list")
@click.option(
    "--file-path", "file_path", default=None, help="Filter by manuscript path."
)
@click.option(
    "--type",
    "claim_type",
    default=None,
    type=click.Choice(["statistic", "figure", "table", "text", "value"]),
    help="Filter by claim type.",
)
@click.option(
    "--status",
    "status",
    default=None,
    help="Filter by verification status (registered/verified/mismatch/missing/partial).",
)
@click.option("--limit", type=int, default=100, help="Maximum claims to list.")
@click.pass_context
def claim_list(
    ctx: click.Context,
    file_path,
    claim_type,
    status,
    limit: int,
) -> None:
    """List registered claims with optional filters."""
    from scitex_clew import list_claims
    from scitex_clew._claim import format_claims

    claims = list_claims(
        file_path=file_path, claim_type=claim_type, status=status, limit=limit
    )

    payload = {
        "count": len(claims),
        "claims": [c.to_dict() for c in claims],
    }
    human = format_claims(claims, verbose=False) or "No claims registered."
    _emit(ctx, payload, human)


@claim.command("verify")
@click.argument("claim_id_or_location")
@click.pass_context
def claim_verify(ctx: click.Context, claim_id_or_location: str) -> None:
    """Verify a specific claim (by claim_id or 'file.tex:L42')."""
    from scitex_clew import verify_claim

    result = verify_claim(claim_id_or_location)

    if result.get("status") == "not_found":
        if _json_mode(ctx):
            click.echo(_json.dumps(result, indent=2, default=str))
        else:
            click.echo(f"ERROR: {result.get('message', 'claim not found')}", err=True)
        ctx.exit(1)

    if _json_mode(ctx):
        click.echo(_json.dumps(result, indent=2, default=str))
    else:
        c = result.get("claim", {})
        click.echo(f"claim_id:        {c.get('claim_id')}")
        click.echo(f"status:          {c.get('status')}")
        click.echo(f"source_verified: {result.get('source_verified')}")
        click.echo(f"chain_verified:  {result.get('chain_verified')}")
        for d in result.get("details", []):
            click.echo(f"  - {d}")


# EOF
