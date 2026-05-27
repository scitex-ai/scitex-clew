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


@claim.command(
    "add",
    epilog=(
        "Example:\n"
        "  $ scitex-clew claim add --file-path paper.tex --type statistic --value 'p=0.003'\n"
        "  $ scitex-clew claim add --file-path paper.tex --type figure --line-number 42 --dry-run"
    ),
)
@click.option(
    "--file-path",
    "file_path",
    required=True,
    help="Path to the manuscript file (e.g., paper.tex).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate inputs and print the claim that would be added; do not write.",
)
@click.option(
    "-y",
    "--yes",
    "yes",
    is_flag=True,
    help="Confirmation flag retained for §2 audit-cli compliance (no-op for `claim add`).",
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
    dry_run: bool,
    yes: bool,
) -> None:
    """Register a claim linking a manuscript assertion to the verification chain."""
    from scitex_clew import add_claim

    del yes  # accepted for §2 compliance
    if dry_run:
        preview = {
            "file_path": file_path,
            "claim_type": claim_type,
            "line_number": line_number,
            "claim_value": claim_value,
            "source_file": source_file,
            "source_session": source_session,
        }
        if _json_mode(ctx):
            click.echo(_json.dumps({"dry_run": True, "claim": preview}, indent=2))
        else:
            click.echo("DRY RUN — would add claim:")
            for k, v in preview.items():
                click.echo(f"  {k}: {v if v is not None else '(none)'}")
        return

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


@claim.command(
    "list",
    epilog=(
        "Example:\n"
        "  $ scitex-clew claim list\n"
        "  $ scitex-clew claim list --file-path paper.tex --type statistic --json"
    ),
)
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
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit JSON (also accepted at top level).",
)
@click.pass_context
def claim_list(
    ctx: click.Context,
    file_path,
    claim_type,
    status,
    limit: int,
    as_json: bool,
) -> None:
    """List registered claims with optional filters."""
    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True
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


@claim.command(
    "verify",
    epilog=(
        "Example:\n"
        "  $ scitex-clew claim verify <claim_id>\n"
        "  $ scitex-clew claim verify paper.tex:L42 --json"
    ),
)
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


@claim.command(
    "register-intermediate",
    epilog=(
        "Example:\n"
        "  $ scitex-clew claim register-intermediate --name n_sig_pathways \\\n"
        "        --value 42 --supports chronic_r2_min_pvals --supports reactome_v2024"
    ),
)
@click.option(
    "--name",
    required=True,
    help="Descriptive identifier for the intermediate (e.g. 'n_sig_pathways').",
)
@click.option(
    "--value",
    "value",
    required=True,
    help="The computed value (stored as its repr for hashing).",
)
@click.option(
    "--supports",
    "supports",
    multiple=True,
    help="Upstream claim/session id this value depends on. Repeat for multiple.",
)
@click.option(
    "--session-id",
    "session_id",
    default=None,
    help="Session ID this value belongs to (defaults to $SCITEX_SESSION_ID).",
)
@click.option(
    "--type",
    "claim_type",
    default="value",
    type=click.Choice(["statistic", "figure", "table", "text", "value"]),
    help="Claim type (default: value).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate inputs and print the claim that would be registered; do not write.",
)
@click.option(
    "-y",
    "--yes",
    "yes",
    is_flag=True,
    help="Confirmation flag retained for §2 audit-cli compliance (no-op here).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit JSON (also accepted at top level).",
)
@click.pass_context
def claim_register_intermediate(
    ctx: click.Context,
    name: str,
    value: str,
    supports,
    session_id,
    claim_type: str,
    dry_run: bool,
    yes: bool,
    as_json: bool,
) -> None:
    """Register a computed intermediate value as a claim in the DAG."""
    from scitex_clew import register_intermediate

    del yes  # accepted for §2 compliance
    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    if dry_run:
        preview = {
            "name": name,
            "value": value,
            "supports": list(supports),
            "session_id": session_id,
            "claim_type": claim_type,
        }
        if _json_mode(ctx):
            click.echo(_json.dumps({"dry_run": True, "claim": preview}, indent=2))
        else:
            click.echo("DRY RUN — would register intermediate:")
            for k, v in preview.items():
                click.echo(f"  {k}: {v if v not in (None, []) else '(none)'}")
        return

    try:
        c = register_intermediate(
            name=name,
            value=value,
            supports=list(supports) or None,
            session_id=session_id,
            claim_type=claim_type,
        )
    except ValueError as exc:
        if _json_mode(ctx):
            click.echo(_json.dumps({"error": str(exc), "claim": None}, indent=2))
        else:
            click.echo(f"ERROR: {exc}", err=True)
        ctx.exit(1)

    payload = c.to_dict()
    human = (
        f"[REGISTERED] intermediate '{name}' as claim {c.claim_id}\n"
        f"  type:     {c.claim_type}\n"
        f"  supports: {', '.join(supports) if supports else '(none)'}\n"
        f"  session:  {session_id or '$SCITEX_SESSION_ID'}"
    )
    _emit(ctx, payload, human)


# EOF
