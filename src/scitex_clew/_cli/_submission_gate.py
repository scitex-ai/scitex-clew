#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Submission-completeness CLI — ``clew gate-completeness``.

The HARD 1:1 question_id↔claim_id gate as a command: load a ``{qid: cid}`` JSON
submission and assert a strict bijection with clew's grounded claims. Exits
non-zero with the failure report on any discrepancy (missing / orphan /
cardinality). See :mod:`scitex_clew._submission_gate`.
"""

from __future__ import annotations

import json

import click

from ._claim import _json_mode


@click.command(
    "gate-completeness",
    epilog=(
        "Example:\n"
        "  $ scitex-clew gate-completeness --submission answers.json\n"
        "  $ scitex-clew gate-completeness --submission answers.json --json\n"
        "\n"
        "answers.json is a mapping of question_id -> claim_id, e.g.\n"
        '  {"q1": "claim_a", "q2": "claim_b"}'
    ),
)
@click.option(
    "--submission",
    "submission_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a JSON file mapping question_id -> claim_id.",
)
@click.option(
    "--workdir",
    "workdir",
    type=click.Path(),
    help="Capsule/project dir to locate the clew DB + sources manifest.",
)
@click.option(
    "--db-path",
    "db_path",
    type=click.Path(),
    help="Explicit clew DB path (overrides the workdir DB search).",
)
@click.option(
    "--sources-path",
    "sources_path",
    type=click.Path(),
    help="Explicit sources manifest path.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
@click.pass_context
def gate_completeness_cmd(
    ctx: click.Context,
    submission_path,
    workdir,
    db_path,
    sources_path,
    as_json: bool,
):
    """Assert a strict 1:1 correspondence between a submission and grounded claims.

    Loads --submission (a {question_id: claim_id} JSON) and checks it against
    clew's GROUNDED claim_ids. Exits 0 when the correspondence is exactly 1:1;
    exits 1 with the failure report on any missing / orphan / cardinality
    violation.
    """
    from .._submission_gate import check_submission_completeness

    if as_json:
        ctx.obj = ctx.obj or {}
        ctx.obj["json"] = True

    with open(submission_path, "r", encoding="utf-8") as fh:
        submission = json.load(fh)
    if not isinstance(submission, dict):
        raise click.ClickException(
            "submission JSON must be an object mapping question_id -> claim_id."
        )
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in submission.items()):
        raise click.ClickException(
            "every submission entry must be a string question_id -> string claim_id."
        )

    result = check_submission_completeness(
        submission,
        workdir=workdir,
        db_path=db_path,
        sources_path=sources_path,
    )

    if _json_mode(ctx):
        click.echo(
            json.dumps(
                {
                    "ok": result.ok,
                    "missing": result.missing,
                    "orphan": result.orphan,
                    "duplicate_claims": result.duplicate_claims,
                    "grounded": result.grounded,
                    "report": result.report(),
                },
                indent=2,
            )
        )
    elif result.ok:
        click.secho(result.report(), fg="green")
    else:
        click.secho(result.report(), fg="red", err=True)

    if not result.ok:
        ctx.exit(1)


# EOF
