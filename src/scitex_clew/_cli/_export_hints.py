#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`clew export-hints` — regenerate scitex-writer's manuscript-hints artifact.

Emits ``export_manuscript_hints()``'s prose-level "things wrong with this
manuscript" feed (schema ``manuscript-hints/1``) to
``.scitex/writer/hints.json`` by default. This is a DIFFERENT, separate
artifact from ``clew export-claims`` (the per-claim render/verification
feed) — see :mod:`scitex_clew._claim._hints` for the full contract.
"""

from __future__ import annotations

import json as _json

import click


@click.command(
    "export-hints",
    epilog=(
        "Example:\n"
        "  $ scitex-clew export-hints\n"
        "  $ scitex-clew export-hints --path build/hints.json --json"
    ),
)
@click.option(
    "--path",
    "path",
    default=None,
    help="Output path (default: canonical .scitex/writer/hints.json).",
)
@click.option(
    "--read-only/--no-read-only",
    "read_only",
    default=True,
    help="chmod 0o444 the output after writing (default: read-only).",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="Print the target path + mode that WOULD be written; do not write.",
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
def export_hints(
    ctx: click.Context,
    path,
    read_only: bool,
    dry_run: bool,
    yes: bool,
    as_json: bool,
) -> None:
    """Regenerate the manuscript-hints.json artifact (schema manuscript-hints/1)."""
    del yes  # accepted for §2 compliance
    if dry_run:
        target = path if path else "<canonical .scitex/writer/hints.json>"
        preview = {"dry_run": True, "path": str(target)}
        if as_json or (ctx.obj and ctx.obj.get("json")):
            click.echo(_json.dumps(preview, indent=2))
        else:
            click.echo(f"DRY RUN — would export manuscript hints -> {target}")
        return

    from scitex_clew import export_manuscript_hints

    out = export_manuscript_hints(path=path, read_only=read_only)

    payload = {"path": str(out)}
    if as_json or (ctx.obj and ctx.obj.get("json")):
        click.echo(_json.dumps(payload, indent=2))
    else:
        click.echo(f"[EXPORTED] manuscript hints -> {out}")


# EOF
