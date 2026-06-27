#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mermaid CLI subcommand: print-mermaid with DAG-slicing options.

Extracted from ``_verification.py`` to keep each module under 512 lines.
"""

from __future__ import annotations

import json

import click

from ._claim import _json_mode

# Valid grouper names from scitex_clew._groupers._spec._REGISTRY.
# Keep in sync with that registry if new groupers are added.
_GROUPER_REGISTRY_NAMES = [
    "identity",
    "drop_all_files",
    "pattern",
    "directory",
    "session_bundle",
    "auto",
]


@click.command(
    "print-mermaid",
    epilog=(
        "Examples:\n"
        "  $ scitex-clew print-mermaid > dag.mmd\n"
        "  $ scitex-clew print-mermaid --claims --json\n"
        "  $ scitex-clew print-mermaid --target results/foo.csv\n"
        "  $ scitex-clew print-mermaid --grouper directory --no-files\n"
        "  $ scitex-clew print-mermaid --max-depth 3"
    ),
)
@click.option("--claims", is_flag=True, help="Build DAG from registered claims.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.option(
    "--target",
    "target_files",
    multiple=True,
    metavar="FILE",
    help=(
        "Scope DAG to upstream cone of FILE. Repeat to add multiple targets. "
        "Combine with --claims to scope a claims-based DAG."
    ),
)
@click.option(
    "--grouper",
    "grouper_name",
    default=None,
    metavar="NAME",
    help=(
        "Collapse nodes using a named grouper. "
        f"Valid names: {', '.join(_GROUPER_REGISTRY_NAMES)}. "
        "Groupers reduce visual clutter in large graphs."
    ),
)
@click.option(
    "--no-files",
    "no_files",
    is_flag=True,
    help="Omit file nodes; render session-to-session edges only.",
)
@click.option(
    "--max-depth",
    "max_depth",
    default=10,
    show_default=True,
    type=int,
    metavar="N",
    help="Maximum chain depth to traverse.",
)
@click.pass_context
def mermaid(
    ctx: click.Context,
    claims: bool,
    as_json: bool,
    target_files: tuple,
    grouper_name: str | None,
    no_files: bool,
    max_depth: int,
):
    """Generate Mermaid DAG diagram.

    \b
    DAG-slicing options scope large provenance graphs to manageable slices:
      --target FILE      restrict to FILE's upstream cone
      --grouper NAME     collapse related nodes (directory/pattern/etc.)
      --no-files         session-to-session edges only (fewest nodes)
      --max-depth N      limit traversal depth

    When --claims is combined with slicing options, the claims-based DAG is
    built first and then the slicing options are applied.
    Note: --target is only honoured in multi-target / direct mode;
    in claims-only mode the full claims DAG is built.
    """
    from scitex_clew._visualize import generate_mermaid_dag

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    # Resolve grouper callable from bare name
    grouper = None
    if grouper_name is not None:
        from scitex_clew.groupers import resolve_spec

        if grouper_name not in _GROUPER_REGISTRY_NAMES:
            raise click.BadParameter(
                f"{grouper_name!r} is not a valid grouper name. "
                f"Valid names: {', '.join(_GROUPER_REGISTRY_NAMES)}.",
                param_hint="'--grouper'",
            )
        grouper = resolve_spec({"type": grouper_name})

    show_files = not no_files
    target_files_list = list(target_files) if target_files else None

    code = generate_mermaid_dag(
        claims=claims,
        target_files=target_files_list,
        max_depth=max_depth,
        show_files=show_files,
        grouper=grouper,
    )

    if _json_mode(ctx):
        click.echo(
            json.dumps(
                {
                    "mermaid": code,
                    "claims": claims,
                    "target_files": target_files_list,
                    "grouper": grouper_name,
                    "show_files": show_files,
                    "max_depth": max_depth,
                },
                default=str,
            )
        )
    else:
        click.echo(code)


# EOF
