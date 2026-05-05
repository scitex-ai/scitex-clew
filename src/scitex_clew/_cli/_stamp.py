#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stamp CLI subcommands — `clew stamp`, `clew list-stamps`, `clew check-stamp`.

One-for-one mirror of ``scitex_clew.stamp`` / ``list_stamps`` / ``check_stamp``.
"""

from __future__ import annotations

import json as _json

import click

from ._claim import _emit, _json_mode


@click.command("stamp")
@click.option(
    "--backend",
    default="file",
    show_default=True,
    type=click.Choice(["file", "rfc3161", "zenodo", "scitex_cloud"]),
    help="Stamping backend.",
)
@click.option("--service-url", "service_url", default=None, help="TSA / API URL.")
@click.option(
    "--session-ids",
    "session_ids",
    default=None,
    help="Comma-separated session IDs to stamp (default: all successful runs).",
)
@click.option(
    "--output-dir",
    "output_dir",
    default=None,
    help="Directory for file-based stamps (default: <db_dir>/stamps).",
)
@click.pass_context
def stamp(
    ctx: click.Context,
    backend: str,
    service_url,
    session_ids,
    output_dir,
) -> None:
    """Record a temporal stamp (root hash + ISO-8601 timestamp)."""
    from scitex_clew import stamp as _stamp

    sids = None
    if session_ids:
        sids = [s.strip() for s in session_ids.split(",") if s.strip()]

    try:
        s = _stamp(
            backend=backend,
            service_url=service_url,
            session_ids=sids,
            output_dir=output_dir,
        )
    except ValueError as exc:
        if _json_mode(ctx):
            click.echo(_json.dumps({"error": str(exc), "stamp": None}, indent=2))
        else:
            click.echo(f"ERROR: {exc}", err=True)
        ctx.exit(1)

    payload = s.to_dict()
    human = (
        f"[STAMPED] {s.stamp_id}\n"
        f"  backend:    {s.backend}\n"
        f"  timestamp:  {s.timestamp}\n"
        f"  root_hash:  {s.root_hash}\n"
        f"  run_count:  {s.run_count}"
    )
    _emit(ctx, payload, human)


@click.command("list-stamps")
@click.option("--limit", type=int, default=20, show_default=True, help="Max stamps.")
@click.pass_context
def list_stamps(ctx: click.Context, limit: int) -> None:
    """List recorded stamps."""
    from scitex_clew import list_stamps as _list_stamps

    stamps = _list_stamps(limit=limit)
    payload = {"count": len(stamps), "stamps": [s.to_dict() for s in stamps]}

    if not stamps:
        human = "No stamps recorded."
    else:
        human_lines = [
            f"  {s.stamp_id}  [{s.backend}]  {s.timestamp}  runs={s.run_count}"
            for s in stamps
        ]
        human = "\n".join(human_lines)
    _emit(ctx, payload, human)


@click.command("check-stamp")
@click.argument("stamp_id", required=False, default=None)
@click.pass_context
def check_stamp(ctx: click.Context, stamp_id) -> None:
    """Verify a stamp (or the latest if STAMP_ID is omitted)."""
    from scitex_clew import check_stamp as _check_stamp

    result = _check_stamp(stamp_id=stamp_id)

    if result.get("status") == "not_found":
        if _json_mode(ctx):
            click.echo(_json.dumps(result, indent=2, default=str))
        else:
            click.echo(f"ERROR: {result.get('message', 'stamp not found')}", err=True)
        ctx.exit(1)

    if _json_mode(ctx):
        click.echo(_json.dumps(result, indent=2, default=str))
    else:
        s = result.get("stamp", {})
        click.echo(f"stamp_id:   {s.get('stamp_id')}")
        click.echo(f"matches:    {result.get('matches')}")
        click.echo(f"stamped:    {s.get('root_hash')}")
        click.echo(f"current:    {result.get('current_root_hash')}")
        for d in result.get("details", []):
            click.echo(f"  - {d}")


# EOF
