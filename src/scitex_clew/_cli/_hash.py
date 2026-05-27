#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hash CLI subcommands — `clew hash-file`, `clew hash-directory`.

One-for-one mirror of ``scitex_clew.hash_file`` and ``scitex_clew.hash_directory``.
"""

from __future__ import annotations

import json as _json

import click

from ._claim import _emit, _json_mode


@click.command(
    "hash-file",
    epilog=(
        "Example:\n"
        "  $ scitex-clew hash-file results/data.csv\n"
        "  $ scitex-clew hash-file results/data.csv --json"
    ),
)
@click.argument("path", type=click.Path(exists=False, dir_okay=False))
@click.option(
    "--algorithm", default="sha256", show_default=True, help="Hash algorithm."
)
@click.option(
    "--chunk-size",
    "chunk_size",
    type=int,
    default=8192,
    show_default=True,
    help="Read chunk size (bytes).",
)
@click.pass_context
def hash_file(ctx: click.Context, path: str, algorithm: str, chunk_size: int) -> None:
    """Print the SHA-256 (first 32 chars) of a file."""
    from scitex_clew import hash_file as _hash_file

    try:
        h = _hash_file(path, algorithm=algorithm, chunk_size=chunk_size)
    except FileNotFoundError as exc:
        if _json_mode(ctx):
            click.echo(_json.dumps({"error": str(exc), "path": path}, indent=2))
        else:
            click.echo(f"ERROR: {exc}", err=True)
        ctx.exit(1)

    payload = {"path": path, "algorithm": algorithm, "hash": h}
    _emit(ctx, payload, h)


@click.command(
    "hash-directory",
    epilog=(
        "Example:\n"
        "  $ scitex-clew hash-directory results/\n"
        "  $ scitex-clew hash-directory results/ --pattern '*.csv' --json"
    ),
)
@click.argument("path", type=click.Path(exists=False, file_okay=False))
@click.option("--pattern", default="*", show_default=True, help="Glob pattern.")
@click.option(
    "--recursive/--no-recursive",
    default=True,
    show_default=True,
    help="Walk subdirectories.",
)
@click.option(
    "--algorithm", default="sha256", show_default=True, help="Hash algorithm."
)
@click.pass_context
def hash_directory(
    ctx: click.Context, path: str, pattern: str, recursive: bool, algorithm: str
) -> None:
    """Print SHA-256 of every file in a directory (one per line by default)."""
    from scitex_clew import hash_directory as _hash_directory

    try:
        hashes = _hash_directory(
            path, pattern=pattern, recursive=recursive, algorithm=algorithm
        )
    except NotADirectoryError as exc:
        if _json_mode(ctx):
            click.echo(_json.dumps({"error": str(exc), "path": path}, indent=2))
        else:
            click.echo(f"ERROR: {exc}", err=True)
        ctx.exit(1)

    payload = {
        "path": path,
        "pattern": pattern,
        "recursive": recursive,
        "algorithm": algorithm,
        "hashes": hashes,
    }
    human_lines = [f"{h}  {rel}" for rel, h in sorted(hashes.items())]
    _emit(ctx, payload, "\n".join(human_lines))


# EOF
