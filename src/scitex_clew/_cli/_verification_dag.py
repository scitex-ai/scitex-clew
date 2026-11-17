#!/usr/bin/env python3
"""DAG-related CLI subcommands: dag, chain, rerun-dag, rerun-claims.

Extracted from ``_verification.py`` to keep each module under 512 lines.
"""

from __future__ import annotations

import json

import click
from scitex_dev.ecosystem import SpecCommand, SpecGroup

from ._claim import _json_mode
from ._help_specs import CLI_HELP

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
        **_slice_payload(getattr(result, "slice", None)),
    }


def _slice_payload(slice_) -> dict:
    """``{"slice": {...}}`` when the result was verified over a minimal slice."""
    if slice_ is None:
        return {}
    return {"slice": {"level": slice_.level, "counts": slice_.counts()}}


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
        if getattr(r, "provenance", "tracked") == "exception":
            reason = getattr(r, "exception_reason", None) or "no reason given"
            click.echo(f"       EXCEPTION (reason: {reason})")
        for f in getattr(r, "files", []):
            if getattr(f, "frozen", False):
                click.echo(f"       FROZEN (trusted hash, not re-read): {f.path}")
            _echo_external(f)


def _echo_external(f) -> None:
    """One line for an input read from outside the project (if ``f`` is one)."""
    if not getattr(f, "external", False):
        return
    state = "MISSING on this machine" if f.status.value == "missing" else f.status.value
    click.echo(f"       EXTERNAL input ({state}, not bundled): {f.path}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@click.command(cls=SpecCommand, help_spec=CLI_HELP["dag"])
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
@click.option(
    "--minimal",
    is_flag=True,
    help="Verify only the file-level minimal slice (see `clew slice`).",
)
@click.option(
    "--level",
    default=1,
    show_default=True,
    type=click.IntRange(1, 2),
    help="Slice level with --minimal (1 path-pruned, 2 declared deps).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def dag(
    ctx: click.Context,
    targets,
    claims: bool,
    strict: bool,
    minimal: bool,
    level: int,
    as_json: bool,
):
    """Verify the DAG for one or more targets (or every claim).

    \b
    Examples:
      clew dag --target results/foo.csv --json
      clew dag --claims --strict --json
    """
    from scitex_clew._chain import verify_dag, verify_dag_strict
    from scitex_clew._claim import verify_claims_dag

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
        result = verify_claims_dag(minimal=minimal, level=level)
    else:
        result = verify_dag(list(targets), minimal=minimal, level=level)

    payload = _dag_payload(result)

    if _json_mode(ctx):
        click.echo(json.dumps(payload, indent=2, default=str))
        return

    _echo_dag_human(result, label="DAG")


@click.command(cls=SpecCommand, help_spec=CLI_HELP["chain"])
@click.argument("target_file")
@click.option(
    "--minimal",
    is_flag=True,
    help="Verify only the file-level minimal slice (see `clew slice`).",
)
@click.option(
    "--level",
    default=1,
    show_default=True,
    type=click.IntRange(1, 2),
    help="Slice level with --minimal (1 path-pruned, 2 declared deps).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def chain(
    ctx: click.Context, target_file: str, minimal: bool, level: int, as_json: bool
):
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

    result = clew.chain(str(path.resolve()), minimal=minimal, level=level)

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
                "external_inputs": [f.path for f in r.files if f.external],
                "missing_external_files": [f.path for f in r.missing_external_files],
            }
            for r in result.runs
        ],
        **_slice_payload(result.slice),
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
        if getattr(r, "provenance", "tracked") == "exception":
            reason = getattr(r, "exception_reason", None) or "no reason given"
            click.echo(f"       EXCEPTION (reason: {reason})")
        for f in getattr(r, "files", []):
            if getattr(f, "frozen", False):
                click.echo(f"       FROZEN (trusted hash, not re-read): {f.path}")
            _echo_external(f)


@click.command("slice", cls=SpecCommand, help_spec=CLI_HELP["slice"])
@click.argument("targets", nargs=-1, required=True)
@click.option(
    "--level",
    default=1,
    show_default=True,
    type=click.IntRange(0, 2),
    help="0 run-level closure, 1 path-pruned, 2 declared per-output deps.",
)
@click.option(
    "--compare",
    is_flag=True,
    help="Report node/edge counts at every level (0, 1, 2) instead.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def slice_cmd(ctx: click.Context, targets, level: int, compare: bool, as_json: bool):
    """Minimal provenance slice: only runs and files on a path to TARGETS.

    TARGETS are files, claim ids, or ``paper.tex:L42`` claim locations.
    """
    from scitex_clew._chain._slice import build_slice, compare_levels

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    if compare:
        counts = compare_levels(list(targets))
        if _json_mode(ctx):
            click.echo(json.dumps({str(k): v for k, v in counts.items()}, indent=2))
            return
        for lvl, c in counts.items():
            click.echo(
                f"level {lvl}: runs={c['runs']} files={c['files']} "
                f"nodes={c['nodes']} edges={c['edges']}"
            )
        return

    sl = build_slice(list(targets), level=level)
    if _json_mode(ctx):
        click.echo(json.dumps(sl.to_dict(), indent=2, default=str))
        return
    c = sl.counts()
    click.echo(
        f"slice level={sl.level} runs={c['runs']} files={c['files']} "
        f"nodes={c['nodes']} edges={c['edges']}"
    )
    for sid in sl.runs:
        click.echo(f"  run {sid}")
        for p in sl.run_inputs.get(sid, []):
            tag = "  [EXTERNAL: outside the project, not bundled]"
            click.echo(f"    <- {p}{tag if p in sl.external else ''}")
        for p in sl.run_outputs.get(sid, []):
            click.echo(f"    -> {p}")
    for sid, paths in sl.dropped_outputs.items():
        click.echo(f"  dropped outputs of {sid}: {len(paths)}")
    for sid, paths in sl.dropped_inputs.items():
        click.echo(f"  dropped inputs of {sid}: {len(paths)}")
    for sid, reason in sl.fallback_runs.items():
        click.echo(f"  level-2 fallback for {sid}: {reason}")
    required = sl.required_external()
    if required:
        click.echo(
            f"  REQUIRED BUT NOT BUNDLED: {len(required)} external input(s) must "
            "exist at these paths with these hashes to re-run:"
        )
        for item in required:
            via = f"  (via {item['via']})" if item["via"] else ""
            click.echo(f"    {item['path']}  sha256={item['hash']}{via}")


@click.command("rerun-dag", cls=SpecCommand, help_spec=CLI_HELP["rerun_dag"])
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


@click.command("rerun-claims", cls=SpecCommand, help_spec=CLI_HELP["rerun_claims"])
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
