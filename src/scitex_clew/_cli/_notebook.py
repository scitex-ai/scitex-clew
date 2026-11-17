#!/usr/bin/env python3
"""``clew execute-notebook`` — execute a notebook headless, as a run's recipe does.

The re-execution recipe a slice carries for a notebook run
(:func:`scitex_clew._chain._notebook.rerun_recipe`) is ``python -m scitex_clew
execute-notebook <nb> --cwd <recorded cwd>``. nbclient is optional: without it
the command exits :data:`~scitex_clew._chain._notebook.EXIT_NO_EXECUTOR` (3) and
says what to install.
"""

from __future__ import annotations

import click
from scitex_dev.ecosystem import SpecCommand

from ._help_specs import CLI_HELP


@click.command("execute-notebook", cls=SpecCommand, help_spec=CLI_HELP["execute_notebook_cmd"])
@click.argument("notebook", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--cwd",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Kernel working directory (default: the notebook's directory).",
)
@click.option("--timeout", type=int, default=None, help="Per-cell timeout (s).")
@click.pass_context
def execute_notebook_cmd(
    ctx: click.Context, notebook: str, cwd: str | None, timeout: int | None
) -> None:
    """Execute NOTEBOOK top to bottom in a fresh kernel (file not modified)."""
    from .._chain._notebook import EXIT_NO_EXECUTOR, execute_notebook

    try:
        execute_notebook(notebook, cwd, timeout=timeout)
    except ModuleNotFoundError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        ctx.exit(EXIT_NO_EXECUTOR)
    except Exception as exc:  # noqa: BLE001 - reported, non-zero exit
        click.echo(f"ERROR: clew execute-notebook: {type(exc).__name__}: {exc}", err=True)
        ctx.exit(1)


# EOF
