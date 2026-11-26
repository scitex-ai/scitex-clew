#!/usr/bin/env python3
"""`clew records {export,import}` — move a project's records between stores.

See :mod:`scitex_clew._exchange._records`. ``export`` reads the store
``SCITEX_STORE_DSN`` names (the current project scope); ``import`` writes the
store ``SCITEX_STORE_DSN`` names, so the two stores never connect to each
other — the file is the only thing that travels.

Exit codes: ``0`` = ok; ``1`` = the document was refused (checksum / schema)
or the import conflicts with the target store; ``2`` = usage error.
"""

from __future__ import annotations

import json as _json

import click
from scitex_dev.ecosystem import CliHelp, Example, SpecCommand, SpecGroup

_JSON_OPTION = click.option(
    "--json", "as_json", is_flag=True, help="Emit JSON (also accepted at top level)."
)
_YES_OPTION = click.option(
    "-y",
    "--yes",
    "yes",
    is_flag=True,
    help="Confirmation flag retained for audit-cli compliance (never prompts).",
)
_SCOPE_HELP_EXPORT = (
    "Project scope to export (default: the current resolved scope — "
    "$SCITEX_CLEW_PROJECT, else .scitex/clew/project-id)."
)
_SCOPE_HELP_IMPORT = (
    "Project scope to file the records under (default: the current resolved "
    "scope — $SCITEX_CLEW_PROJECT, else .scitex/clew/project-id)."
)


def _json_mode(ctx: click.Context, as_json: bool) -> bool:
    while ctx is not None:
        if ctx.obj and ctx.obj.get("json"):
            return True
        ctx = ctx.parent
    return as_json


def _echo_json(payload) -> None:
    click.echo(_json.dumps(payload, indent=2, ensure_ascii=False, default=str))


@click.group(
    "records",
    cls=SpecGroup,
    help_spec=CliHelp(
        summary="Move a project's clew records between stores through a JSON file.",
        examples=(
            Example("{prog} records export --out records.json"),
            Example(
                "{prog} records import records.json --project-scope tenant-proj --dry-run"
            ),
            Example(
                "{prog} records import records.json --project-scope tenant-proj --json"
            ),
        ),
    ),
)
def records() -> None:
    """Project records (scitex-clew.project-records 1.0.0): export / import."""


@records.command(
    "export",
    cls=SpecCommand,
    help_spec=CliHelp(
        summary="Write every record of the current project scope to a JSON file.",
        examples=(
            Example("{prog} records export --out records.json"),
            Example(
                "{prog} records export --out records.json --project-scope clew-abc --json"
            ),
        ),
    ),
)
@click.option("--out", "out", required=True, type=click.Path(dir_okay=False),
              help="Document path to write ('-' = stdout).")  # fmt: skip
@click.option("--project-scope", "project_scope", default=None, help=_SCOPE_HELP_EXPORT)
@click.option(
    "--dry-run", "dry_run", is_flag=True, help="Count the records; write no file."
)
@_YES_OPTION
@_JSON_OPTION
@click.pass_context
def export(
    ctx, out: str, project_scope, dry_run: bool, yes: bool, as_json: bool
) -> None:
    """Export this project's records (all clew stores) as a versioned document."""
    del yes
    from .._exchange._records import build_records, write_records

    document = build_records(project_scope or None)
    summary = {
        "schema": document["schema"],
        "schema_version": document["schema_version"],
        "project": document["source"]["project"],
        "counts": document["counts"],
        "payload_sha256": document["payload_sha256"],
        "out": out,
        "dry_run": dry_run,
    }
    if out == "-" and not dry_run:
        click.echo(_json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False))
        return
    if not dry_run:
        summary["out"] = str(write_records(document, out).resolve())
    if _json_mode(ctx, as_json):
        _echo_json(summary)
        return
    verb = "DRY RUN — would export" if dry_run else "[EXPORTED]"
    total = sum(summary["counts"].values())
    click.echo(
        f"{verb} {total} record(s) of project {summary['project']!r} -> {summary['out']}"
    )
    for name, count in summary["counts"].items():
        click.echo(f"  {name}: {count}")


@records.command(
    "import",
    cls=SpecCommand,
    help_spec=CliHelp(
        summary="Write a records document into the store SCITEX_STORE_DSN names.",
        description=(
            (
                "Idempotent: an identical record is skipped, a differing one is replaced by "
                "the document's values; a differing write-once field refuses the whole "
                "import before anything is written. The document's checksum and schema "
                "are checked first. Only DML is issued against existing tables."
            ),
        ),
        examples=(
            Example("{prog} records import records.json --dry-run"),
            Example(
                "{prog} records import records.json --project-scope tenant-proj --json"
            ),
            Example(
                "{prog} records import records.json --rebase /home/me/paper=/srv/projects/paper"
            ),
        ),
    ),
)
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--project-scope", "project_scope", default=None, help=_SCOPE_HELP_IMPORT)
@click.option("--dry-run", "dry_run", is_flag=True,
              help="Report what would be created/updated/unchanged; write nothing.")  # fmt: skip
@click.option("--rebase", "rebase", multiple=True, metavar="SRC_ROOT=DST_ROOT",
              help="Rewrite recorded paths under SRC_ROOT to DST_ROOT (repeatable). "
                   "Paths under no SRC_ROOT are kept and reported as external.")  # fmt: skip
@_YES_OPTION
@_JSON_OPTION
@click.pass_context
def import_(
    ctx, path: str, project_scope, dry_run: bool, rebase, yes: bool, as_json: bool
) -> None:
    """Import a project-records document into the current store."""
    del yes
    from .._exchange._rebase import parse_rebase
    from .._exchange._records import (
        RecordsDocumentError,
        RecordsImportConflict,
        import_records,
        load_records,
    )

    try:
        rules = parse_rebase(rebase)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--rebase") from exc
    try:
        document = load_records(path)
        report = import_records(
            document, project=project_scope or None, dry_run=dry_run, rebase=rules
        )
    except RecordsDocumentError as exc:
        raise click.ClickException(f"refused {path}: {exc}") from exc
    except RecordsImportConflict as exc:
        raise click.ClickException(str(exc)) from exc
    if _json_mode(ctx, as_json):
        _echo_json(report)
        return
    verb = "DRY RUN — would import" if dry_run else "[IMPORTED]"
    click.echo(
        f"{verb} {path}: project {report['source_project']!r} -> {report['target_project']!r}"
    )
    for name, c in report["tables"].items():
        click.echo(
            f"  {name}: {c['rows']} row(s) — {c['created']} created, "
            f"{c['updated']} updated, {c['unchanged']} unchanged"
        )
    moved = report["paths"]
    if moved["rules"]:
        click.echo(
            f"  paths: {moved['rewritten']} rebased (+{moved['rewritten_in_json']} inside "
            f"JSON fields), {moved['external']} external (left as recorded)"
        )
        for example in moved["external_examples"]:
            click.echo(f"    external: {example}")


# EOF
