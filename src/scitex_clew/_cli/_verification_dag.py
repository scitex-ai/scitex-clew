#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DAG-related CLI subcommands: dag, chain, rerun-dag, rerun-claims.

Extracted from ``_verification.py`` to keep each module under 512 lines.
"""

from __future__ import annotations

import json

import click

from ._claim import _json_mode


# ---------------------------------------------------------------------------
# Shared DAG serialization helpers
# ---------------------------------------------------------------------------


def _dag_payload(result) -> dict:
    """Serialize a DAGVerification to the canonical CLI/MCP JSON shape."""
    return {
        "target_files": result.target_files,
        "status": result.status.value,
        "is_verified": result.is_verified,
        "num_runs": len(result.runs),
        "num_edges": len(result.edges),
        "topological_order": result.topological_order,
        "runs": [
            {
                "session_id": r.session_id,
                "script_path": r.script_path,
                "status": r.status.value,
                "is_verified": r.is_verified,
            }
            for r in result.runs
        ],
        "edges": [{"parent": p, "child": c} for p, c in result.edges],
    }


def _echo_dag_human(result, label: str = "DAG") -> None:
    """Print a one-line-per-run human summary of a DAGVerification."""
    icon = "OK" if result.is_verified else "FAIL"
    click.echo(
        f"[{icon}] {label} status={result.status.value} "
        f"runs={len(result.runs)} edges={len(result.edges)}"
    )
    for r in result.runs:
        ficon = "OK" if r.is_verified else "!!"
        click.echo(
            f"  [{ficon}] {r.session_id} ({r.status.value})  {r.script_path or ''}"
        )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--target",
    "targets",
    multiple=True,
    help="Target file(s). Repeat for multiple targets.",
)
@click.option(
    "--claims",
    is_flag=True,
    help="Build DAG from all registered claims (instead of explicit targets).",
)
@click.option(
    "--strict",
    is_flag=True,
    help="On hash mismatch, return failure-attribution payload (F2).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def dag(
    ctx: click.Context,
    targets,
    claims: bool,
    strict: bool,
    as_json: bool,
):
    """Verify the DAG for one or more targets (or every claim).

    \b
    Examples:
      clew dag --target results/foo.csv --json
      clew dag --claims --strict --json
    """
    from scitex_clew._claim import verify_claims_dag
    from scitex_clew._dag import verify_dag, verify_dag_strict

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    # F2: strict mode → failure-attribution dict (always JSON-shaped).
    if strict:
        payload = verify_dag_strict(
            targets=list(targets) or None,
            claims=claims,
        )
        # Compact JSON when --json explicit, else indent=2 for readability.
        indent = None if _json_mode(ctx) else 2
        click.echo(json.dumps(payload, indent=indent, default=str))
        return

    # Non-strict: existing DAGVerification surface.
    if claims:
        result = verify_claims_dag()
    else:
        result = verify_dag(list(targets))

    payload = _dag_payload(result)

    if _json_mode(ctx):
        click.echo(json.dumps(payload, indent=2, default=str))
        return

    _echo_dag_human(result, label="DAG")


@click.command(
    epilog=(
        "Example:\n"
        "  $ scitex-clew chain results/fig1.png\n"
        "  $ scitex-clew chain results/fig1.png --json"
    ),
)
@click.argument("target_file")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def chain(ctx: click.Context, target_file: str, as_json: bool):
    """Verify the provenance chain that produced a target file.

    Walks backwards through every upstream session that contributed to
    TARGET_FILE and re-hashes each one.
    """
    from pathlib import Path

    import scitex_clew as clew

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    path = Path(target_file)
    if not path.exists():
        payload = {
            "error": f"File not found: {target_file}",
            "target_file": target_file,
        }
        if _json_mode(ctx):
            click.echo(json.dumps(payload, indent=2, default=str))
        else:
            click.echo(f"ERROR: file not found: {target_file}", err=True)
        ctx.exit(1)

    result = clew.chain(str(path.resolve()))

    payload = {
        "target_file": result.target_file,
        "status": result.status.value,
        "is_verified": result.is_verified,
        "chain_length": len(result.runs),
        "failed_runs_count": len(result.failed_runs),
        "runs": [
            {
                "session_id": r.session_id,
                "script_path": r.script_path,
                "status": r.status.value,
                "is_verified": r.is_verified,
                "mismatched_files": [f.path for f in r.mismatched_files],
                "missing_files": [f.path for f in r.missing_files],
            }
            for r in result.runs
        ],
    }

    if _json_mode(ctx):
        click.echo(json.dumps(payload, indent=2, default=str))
        return

    icon = "OK" if result.is_verified else "FAIL"
    click.echo(
        f"[{icon}] chain target={result.target_file} "
        f"status={result.status.value} length={len(result.runs)}"
    )
    for r in result.runs:
        ficon = "OK" if r.is_verified else "!!"
        click.echo(
            f"  [{ficon}] {r.session_id} ({r.status.value})  {r.script_path or ''}"
        )


@click.command(
    "rerun-dag",
    epilog=(
        "Example:\n"
        "  $ scitex-clew rerun-dag\n"
        "  $ scitex-clew rerun-dag --target results/fig1.png --timeout 600 --json"
    ),
)
@click.option(
    "--target",
    "targets",
    multiple=True,
    help="Target file(s). Repeat for multiple. Omit to rerun the whole DAG.",
)
@click.option(
    "--timeout",
    type=int,
    default=300,
    help="Maximum execution time per session in seconds (default: 300).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def rerun_dag(ctx: click.Context, targets, timeout: int, as_json: bool):
    """Re-execute the DAG in a sandbox and compare outputs (slow, thorough).

    Originals are never overwritten.
    """
    import scitex_clew as clew

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    result = clew.rerun_dag(list(targets) or None, timeout=timeout)
    payload = _dag_payload(result)

    if _json_mode(ctx):
        click.echo(json.dumps(payload, indent=2, default=str))
        return

    _echo_dag_human(result, label="rerun-dag")


@click.command(
    "rerun-claims",
    epilog=(
        "Example:\n"
        "  $ scitex-clew rerun-claims\n"
        "  $ scitex-clew rerun-claims --type statistic --json"
    ),
)
@click.option(
    "--file-path", "file_path", default=None, help="Filter claims by manuscript path."
)
@click.option(
    "--type",
    "claim_type",
    default=None,
    type=click.Choice(["statistic", "figure", "table", "text", "value"]),
    help="Filter claims by type.",
)
@click.option(
    "--timeout",
    type=int,
    default=300,
    help="Maximum execution time per session in seconds (default: 300).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def rerun_claims(
    ctx: click.Context,
    file_path,
    claim_type,
    timeout: int,
    as_json: bool,
):
    """Re-execute every claim-backing session in a sandbox and compare.

    \b
    Example:
      clew rerun-claims --type statistic --json
    """
    import scitex_clew as clew

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    result = clew.rerun_claims(
        file_path=file_path, claim_type=claim_type, timeout=timeout
    )
    payload = _dag_payload(result)

    if _json_mode(ctx):
        click.echo(json.dumps(payload, indent=2, default=str))
        return

    _echo_dag_human(result, label="rerun-claims")


# EOF
