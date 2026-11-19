#!/usr/bin/env python3
"""`clew export-evidence` — write a ``scitex-live-paper.evidence-report`` file.

The out-of-process path of the evidence-provider contract: the same report the
``scitex.livepaper.renderers`` entry point returns in process (see
:mod:`scitex_clew._evidence_provider`), written as JSON for a consumer that
does not have clew installed. This is an export, not a gate: it exits 0 when
the report was written, whatever the claims' states are (``clew verify
--strict`` is the gate).
"""

from __future__ import annotations

import json as _json
from collections import Counter
from pathlib import Path

import click
from scitex_dev.ecosystem import SpecCommand

from ._help_specs import CLI_HELP


@click.command(
    "export-evidence", cls=SpecCommand, help_spec=CLI_HELP["export_evidence"]
)
@click.option(
    "--out",
    "out",
    required=True,
    help="Report path to write ('-' writes the report to stdout).",
)
@click.option(
    "--project-root",
    "project_root",
    default=".",
    show_default=True,
    type=click.Path(file_okay=False, exists=True),
    help="The clew project whose registered claims are reported.",
)
@click.option(
    "--claim",
    "claim_ids",
    multiple=True,
    help="Report only this registered claim id (repeatable; default: all).",
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="Print what WOULD be written; verify nothing, write nothing.",
)
@click.option(
    "-y",
    "--yes",
    "yes",
    is_flag=True,
    help="Confirmation flag retained for §2 audit-cli compliance (no-op here).",
)
@click.option(
    "--json", "as_json", is_flag=True, help="Emit JSON (also accepted at top level)."
)
@click.pass_context
def export_evidence(
    ctx: click.Context,
    out: str,
    project_root: str,
    claim_ids: tuple[str, ...],
    dry_run: bool,
    yes: bool,
    as_json: bool,
) -> None:
    """Write the evidence report (scitex-live-paper.evidence-report 1.2.0)."""
    del yes  # accepted for §2 compliance
    from scitex_clew._evidence_provider import SCHEMA_ID, SCHEMA_VERSION

    json_mode = as_json or bool(ctx.obj and ctx.obj.get("json"))
    root = str(Path(project_root).resolve())
    if dry_run:
        preview = {
            "dry_run": True,
            "out": out,
            "project_root": root,
            "claims": list(claim_ids) or None,
            "schema": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
        }
        if json_mode:
            click.echo(_json.dumps(preview, indent=2))
        else:
            click.echo(f"DRY RUN — would write {SCHEMA_ID} {SCHEMA_VERSION} -> {out}")
        return

    from scitex_clew._evidence_provider import build_evidence_report

    report = build_evidence_report(root, list(claim_ids) or None, {})
    text = _json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if out == "-":
        click.echo(text, nl=False)
        return
    path = Path(out).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

    counts = dict(Counter(c["state"] for c in report["claims"]))
    if json_mode:
        payload = {"path": str(path), "claims": len(report["claims"]), "states": counts}
        click.echo(_json.dumps(payload, indent=2))
    else:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"
        click.echo(f"[EXPORTED] {len(report['claims'])} claim(s) ({summary}) -> {path}")


# EOF
