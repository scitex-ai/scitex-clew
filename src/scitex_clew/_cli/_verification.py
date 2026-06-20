#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verification CLI subcommands.

Extracted from ``_main.py`` so each module owns one responsibility (mirrors
``_claim`` / ``_hash`` / ``_stamp``). ``_main`` imports these and registers
them on the root group via ``add_command``.

Commands: ``status``, ``list-runs``, ``verify``, ``show-stats``,
``print-mermaid``, ``dag``, ``chain``, ``rerun-dag``, ``rerun-claims``.

Every command respects the top-level ``--json`` flag (F5), stored on
``ctx.obj['json']`` and read via ``_json_mode``.
"""

from __future__ import annotations

import json

import click

from ._claim import _json_mode


# ---------------------------------------------------------------------------
# Shared DAG serialization helpers (used by dag / rerun-dag / rerun-claims)
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
# Verification commands
# ---------------------------------------------------------------------------


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
                }
                for f in result.files
            ],
        }
        click.echo(json.dumps(payload, indent=2, default=str))
        ctx.exit(code)

    icon = "OK" if result.is_verified else "FAIL"
    click.echo(f"[{icon}] {result.session_id} ({result.status.value})")
    for f in result.files:
        ficon = "OK" if f.is_verified else "!!"
        click.echo(f"  [{ficon}] {f.role:<6} {f.path}")
    ctx.exit(code)


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


@click.command(
    "print-mermaid",
    epilog=(
        "Example:\n"
        "  $ scitex-clew print-mermaid > dag.mmd\n"
        "  $ scitex-clew print-mermaid --claims --json"
    ),
)
@click.option("--claims", is_flag=True, help="Build DAG from registered claims.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def mermaid(ctx: click.Context, claims: bool, as_json: bool):
    """Generate Mermaid DAG diagram."""
    import scitex_clew as clew

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    code = clew.mermaid(claims=claims)
    if _json_mode(ctx):
        click.echo(json.dumps({"mermaid": code, "claims": claims}, default=str))
    else:
        click.echo(code)


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
