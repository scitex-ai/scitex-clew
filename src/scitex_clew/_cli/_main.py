#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main CLI entry point for scitex-clew.

Universal output mode
---------------------
Every subcommand respects the top-level ``--json`` flag (F5). The flag is
stored on ``ctx.obj['json']`` and read by helpers in ``_claim`` / ``_hash``
/ ``_stamp`` / ``_verification`` and via ``_json_mode(ctx)``.

This module is a thin orchestrator: command families live in their own
modules (``_verification`` / ``_claim`` / ``_hash`` / ``_stamp`` /
``_introspect`` / ``_mcp``) and are registered on the root group below.
"""

from __future__ import annotations

import json
import sys

import click

from ._citation import citation, verify_citations_cmd
from ._claim import claim
from ._estimate import estimate
from ._export import export_claims as export_claims_cmd
from ._hash import hash_directory, hash_file
from ._introspect import list_python_apis
from ._mcp import mcp
from ._stamp import check_stamp, list_stamps, stamp
from ._verification import (
    chain,
    dag,
    list_runs,
    mermaid,
    rerun_claims,
    rerun_dag,
    stats,
    status,
    verify,
)

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

COMMAND_CATEGORIES = [
    (
        "Verification",
        [
            "status",
            "list-runs",
            "verify",
            "show-stats",
            "dag",
            "chain",
            "rerun-dag",
            "rerun-claims",
            "estimate",
        ],
    ),
    ("Claims", ["claim", "export-claims"]),
    ("Citations", ["verify-citations", "citation"]),
    ("Hashing", ["hash-file", "hash-directory"]),
    ("Stamping", ["stamp", "list-stamps", "check-stamp"]),
    ("Visualization", ["print-mermaid"]),
    ("Integration", ["mcp", "list-python-apis", "completion"]),
]

class CategorizedGroup(click.Group):
    """Custom Click group that displays commands organized by category."""

    def format_commands(self, ctx, formatter):
        """Write categorized commands to the formatter."""
        commands = {}
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is not None and not cmd.hidden:
                commands[subcommand] = cmd

        if not commands:
            return

        displayed = set()

        for category_name, category_commands in COMMAND_CATEGORIES:
            category_items = []
            for name in category_commands:
                if name in commands and name not in displayed:
                    cmd = commands[name]
                    help_text = cmd.get_short_help_str(limit=formatter.width)
                    category_items.append((name, help_text))
                    displayed.add(name)

            if category_items:
                with formatter.section(category_name):
                    formatter.write_dl(category_items)

        uncategorized = [
            (name, commands[name].get_short_help_str(limit=formatter.width))
            for name in sorted(commands.keys())
            if name not in displayed
        ]
        if uncategorized:
            with formatter.section("Other"):
                formatter.write_dl(uncategorized)

def _show_recursive_help(ctx: click.Context) -> None:
    """Recursively show help for all commands."""
    click.echo(ctx.get_help())
    click.echo()
    group = ctx.command
    if isinstance(group, click.Group):
        for name in sorted(group.list_commands(ctx)):
            cmd = group.get_command(ctx, name)
            sub_ctx = click.Context(cmd, parent=ctx, info_name=name)
            click.echo(f"{'=' * 60}")
            click.echo(f"Command: {name}")
            click.echo(f"{'=' * 60}")
            click.echo(sub_ctx.get_help())
            click.echo()
            if isinstance(cmd, click.Group):
                for sub_name in sorted(cmd.list_commands(sub_ctx)):
                    sub_cmd = cmd.get_command(sub_ctx, sub_name)
                    sub_sub_ctx = click.Context(
                        sub_cmd, parent=sub_ctx, info_name=sub_name
                    )
                    click.echo(f"  {'─' * 56}")
                    click.echo(f"  Subcommand: {name} {sub_name}")
                    click.echo(f"  {'─' * 56}")
                    click.echo(sub_sub_ctx.get_help())
                    click.echo()

def _get_version() -> str:
    """Read version from importlib.metadata."""
    try:
        from importlib.metadata import version

        return version("scitex-clew")
    except Exception:
        return "0.0.0-unknown"

@click.group(
    cls=CategorizedGroup,
    invoke_without_command=True,
    context_settings=CONTEXT_SETTINGS,
)
@click.option("--version", "-V", is_flag=True, help="Show version and exit.")
@click.option("--help-recursive", is_flag=True, help="Show help for all commands.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit machine-parsable JSON for every subcommand (F5).",
)
@click.pass_context
def main(
    ctx: click.Context, version: bool, help_recursive: bool, as_json: bool
) -> None:
    """clew - Hash-based reproducibility verification for scientific pipelines.

    \b
    Configuration precedence (highest -> lowest):
      1. Explicit CLI flags
      2. ./config.yaml (project-local)
      3. $SCITEX_CLEW_CONFIG (path to a YAML file)
      4. ~/.scitex/clew/config.yaml (user-wide)
      5. Built-in defaults
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = bool(as_json)

    if version:
        if as_json:
            click.echo(
                json.dumps({"version": _get_version(), "package": "scitex-clew"})
            )
        else:
            click.echo(f"scitex-clew {_get_version()}")
        ctx.exit(0)

    if help_recursive:
        _show_recursive_help(ctx)
        ctx.exit(0)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())

# §1a: install-shell-completion + print-shell-completion are registered
# via scitex_dev._cli._completion.attach_shell_completion(...) at the
# bottom of this module. The legacy `completion <SHELL>` positional
# form is preserved here as a hidden deprecated redirect.
@main.command(
    "completion-legacy",
    hidden=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.pass_context
def completion_legacy(ctx):
    """(deprecated) Use `install-shell-completion` or `print-shell-completion`."""
    click.echo(
        "error: `clew completion <SHELL>` was split into:\n"
        "  clew install-shell-completion --shell <bash|zsh|fish>\n"
        "  clew print-shell-completion   --shell <bash|zsh|fish>",
        err=True,
    )
    ctx.exit(2)

# -----------------------------------------------------------------------
# Register command families
# -----------------------------------------------------------------------

# Verification (status / list-runs / verify / show-stats / print-mermaid /
# dag / chain / rerun-dag / rerun-claims).
main.add_command(status)
main.add_command(list_runs)
main.add_command(verify)
main.add_command(stats)
main.add_command(mermaid)
main.add_command(dag)
main.add_command(chain)
main.add_command(rerun_dag)
main.add_command(rerun_claims)

main.add_command(estimate)
main.add_command(list_python_apis)
main.add_command(mcp)

# F1: claim group, hash-file/-directory, stamp / list-stamps / check-stamp.
main.add_command(claim)
main.add_command(export_claims_cmd)

# Citation gate: verify-citations (compiler pre-flight) + citation group.
main.add_command(verify_citations_cmd)
main.add_command(citation)
main.add_command(hash_file)
main.add_command(hash_directory)
main.add_command(stamp)
main.add_command(list_stamps)
main.add_command(check_stamp)

from scitex_dev.cli import docs_click_group, skills_click_group

main.add_command(docs_click_group(package="scitex-clew"))
main.add_command(skills_click_group(package="scitex-clew"))

# §1a: install-shell-completion + print-shell-completion (canonical leaves)
from scitex_dev._cli._completion import attach_shell_completion

attach_shell_completion(main, prog_name="scitex-clew")


# audit §4 — inject version into root --help
try:
    from importlib.metadata import version as _v

    main.help = f"scitex-clew (v{_v('scitex-clew')}) — " + (main.help or "").lstrip()
except Exception:
    pass

# audit-cli §1a — packages with _skills/ MUST expose
# `<cli> skills {list,get,install}`.
from ._skills import skills_group as _skills_group

main.add_command(_skills_group, name="skills")

# EOF
