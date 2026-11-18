#!/usr/bin/env python3
"""``clew recover-journals`` — replay the journals of killed runs.

One-for-one mirror of :func:`scitex_clew.recover_journals`. Every ``clew``
command already does this quietly before it runs (:func:`recover_quietly`);
this command does it explicitly and reports what it found.
"""

from __future__ import annotations

import json as _json

import click
from scitex_dev.ecosystem import SpecCommand

from ._help_specs import CLI_HELP

#: Commands that never touch provenance: no recovery before them.
_NO_RECOVERY = frozenset(
    {
        "recover-journals",
        "completion",
        "completion-legacy",
        "install-shell-completion",
        "print-shell-completion",
        "skills",
        "mcp",
        "list-python-apis",
    }
)


def recover_quietly(subcommand: str | None) -> None:
    """Replay dead sessions' journals before a ``clew`` command (warned)."""
    if subcommand is None or subcommand in _NO_RECOVERY:
        return
    from .._tracker import _recover_dead_sessions

    _recover_dead_sessions()


@click.command(
    "recover-journals", cls=SpecCommand, help_spec=CLI_HELP["recover_journals"]
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Report what would be replayed; change nothing.",
)
@click.pass_context
def recover_journals(ctx: click.Context, dry_run: bool) -> None:
    """Replay the recording journals of runs whose process died."""
    from .._journal import journal_dir
    from .._journal import recover_journals as _recover

    reports = _recover(dry_run=dry_run)
    if (ctx.obj or {}).get("json"):
        click.echo(
            _json.dumps(
                {"journal_dir": str(journal_dir()), "recovered": reports}, indent=2
            )
        )
        return
    if not reports:
        click.echo(f"No journal of a dead run to replay in {journal_dir()}.")
        return
    verb = "Would replay" if dry_run else "Replayed"
    for r in reports:
        click.echo(
            f"{verb} {r['session_id']} (pid {r['pid']}): "
            f"{r['rows_replayed']} queued row(s), {r['captured_inputs']} captured "
            f"input(s); status {r['status_before']} -> "
            f"{r['status_before'] if dry_run else r['status']}"
        )
        if r["unhashed_writes"]:
            click.echo(
                f"  {len(r['unhashed_writes'])} file(s) opened for writing were "
                "never hashed (partial output is not recorded): "
                + ", ".join(r["unhashed_writes"][:5])
            )


# EOF
