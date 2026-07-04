#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI for the registered-source whitelist: register / list / unregister.

``clew register-source`` is the ONE sanctioned, human-run WRITE path for the
manifest (verify/export only ever read it). See :mod:`scitex_clew._sources`.
"""

from __future__ import annotations

import json

import click

from ._claim import _json_mode


@click.command(
    "register-source",
    epilog=(
        "Example:\n"
        "  $ scitex-clew register-source data/raw.csv\n"
        "  $ scitex-clew register-source a.csv b.csv --json"
    ),
)
@click.argument("files", nargs=-1, required=False, type=click.Path(exists=True))
@click.option(
    "--from-list",
    "from_list",
    type=click.Path(exists=True, dir_okay=False),
    help="Read source paths from a file (one path per line; # comments + blank lines skipped).",
)
@click.option(
    "--sources-path",
    "sources_path",
    type=click.Path(),
    help="Manifest path to write (default: the resolved signed/sources.json).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what WOULD be pinned without writing the manifest.",
)
@click.option(
    "--yes",
    "-y",
    "assume_yes",
    is_flag=True,
    help="Skip the confirmation prompt (non-interactive).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def register_source_cmd(
    ctx: click.Context,
    files,
    from_list,
    sources_path,
    dry_run: bool,
    assume_yes: bool,
    as_json: bool,
):
    """Register FILE(s) as trusted sources (idempotent; hash-pinned).

    Computes each file's sha256 and writes/updates a {path, sha256} entry in the
    manifest (default: the resolved signed/sources.json). Re-registering a path
    updates its hash. Paths may be given as arguments and/or via
    --from-list <file> (one path per line; # comments + blank lines skipped) —
    so a human-editable path list compiles straight into the signable JSON
    manifest. The sanctioned human WRITE path — verify/export never write it.
    """
    from pathlib import Path

    from .._sources import full_sha256, list_sources, register_source

    paths = [str(f) for f in files]
    if from_list:
        for line in Path(from_list).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                paths.append(line)
    if not paths:
        raise click.ClickException(
            "no sources given — pass FILE(s) and/or --from-list <file>."
        )
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        raise click.ClickException(
            "source path(s) not found: " + ", ".join(missing)
        )

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    if dry_run:
        planned = [{"path": p, "sha256": full_sha256(p)} for p in paths]
        if _json_mode(ctx):
            click.echo(json.dumps({"dry_run": True, "would_register": planned}, indent=2))
            return
        click.echo(f"[DRY-RUN] would register {len(paths)} source(s):")
        for p in planned:
            click.echo(f"  {p['path']}  {p['sha256'][:12]}...")
        return

    path = register_source(paths, sources_path=sources_path)
    entries = list_sources(sources_path=sources_path)

    if _json_mode(ctx):
        click.echo(
            json.dumps(
                {"manifest": str(path), "registered": len(paths), "sources": entries},
                indent=2,
                default=str,
            )
        )
        return
    click.secho(f"[OK] registered {len(paths)} source(s) -> {path}", fg="green")
    for e in entries:
        click.echo(f"  {e['reason']:<9} {e['path']}  {e['sha256'][:12]}...")


@click.command(
    "list-sources",
    epilog="Example:\n  $ scitex-clew list-sources\n  $ scitex-clew list-sources --json",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def list_sources_cmd(ctx: click.Context, as_json: bool):
    """List registered sources with a validity check (OK / TAMPERED / MISSING)."""
    from .._sources import list_sources

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    entries = list_sources()
    if _json_mode(ctx):
        click.echo(json.dumps({"count": len(entries), "sources": entries}, indent=2))
        return
    if not entries:
        click.echo("no registered sources (gate inactive)")
        return
    for e in entries:
        click.echo(f"  {e['reason']:<9} {e['path']}  {e['sha256'][:12]}...")


@click.command(
    "unregister-source",
    epilog="Example:\n  $ scitex-clew unregister-source data/raw.csv",
)
@click.argument("files", nargs=-1, required=True)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what WOULD be removed without writing the manifest.",
)
@click.option(
    "--yes",
    "-y",
    "assume_yes",
    is_flag=True,
    help="Skip the confirmation prompt (non-interactive).",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def unregister_source_cmd(
    ctx: click.Context, files, dry_run: bool, assume_yes: bool, as_json: bool
):
    """Remove FILE(s) from the registered-source manifest (idempotent)."""
    from .._sources import list_sources, unregister_source

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    if dry_run:
        if _json_mode(ctx):
            click.echo(
                json.dumps({"dry_run": True, "would_unregister": list(files)}, indent=2)
            )
            return
        click.echo(f"[DRY-RUN] would unregister {len(files)} source(s):")
        for f in files:
            click.echo(f"  {f}")
        return

    path = unregister_source(list(files))
    entries = list_sources()
    if _json_mode(ctx):
        click.echo(
            json.dumps(
                {"manifest": str(path), "sources": entries}, indent=2, default=str
            )
        )
        return
    click.echo(f"[OK] unregistered {len(files)} source(s) -> {path}")


# EOF
