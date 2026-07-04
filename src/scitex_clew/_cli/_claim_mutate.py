#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim mutation CLI subcommands — `clew claim {remove,supersede}`.

Extracted from ``_claim.py`` to keep that file under the 512-line limit.
These subcommands are registered on the ``claim`` group in ``_claim.py``
via ``_register_mutate_commands``.

Mirrors the Python API in ``scitex_clew._claim`` one-for-one.
Each command respects the top-level ``--json`` flag.

§2 compliance:
  - Mutating verbs have ``--dry-run`` (remove) or are soft by design (supersede).
  - No interactive prompts (``click.confirm`` forbidden).  Without ``-y/--yes``
    the command refuses to act — callers must be explicit.
"""

from __future__ import annotations

import json as _json

import click


def _json_mode(ctx: click.Context) -> bool:
    """Return True if the user requested JSON output."""
    if ctx.obj and ctx.obj.get("json"):
        return True
    parent = ctx.parent
    while parent is not None:
        if parent.obj and parent.obj.get("json"):
            return True
        parent = parent.parent
    return False


def _emit(ctx: click.Context, payload, human_text: str) -> None:
    if _json_mode(ctx):
        click.echo(_json.dumps(payload, indent=2, default=str))
    else:
        click.echo(human_text)


def register_mutate_commands(claim_group) -> None:
    """Attach ``remove`` and ``supersede`` onto *claim_group*."""

    @claim_group.command(
        "remove",
        epilog=(
            "Example:\n"
            "  $ clew claim remove claim_abc123 -y\n"
            "  $ clew claim remove paper.tex:L42 -y\n"
            "  $ clew claim remove --file-path-prefix /old/papers/ -y\n"
            "  $ clew claim remove claim_abc123 --dry-run"
        ),
    )
    @click.argument("claim_id_or_location", required=False, default=None)
    @click.option(
        "--file-path-prefix",
        "file_path_prefix",
        default=None,
        help="Bulk-remove all claims whose file_path starts with this prefix.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="Confirm the destructive operation (required unless --dry-run).",
    )
    @click.option(
        "--dry-run",
        "dry_run",
        is_flag=True,
        help="Show what would be removed without actually deleting.",
    )
    @click.pass_context
    def claim_remove(
        ctx: click.Context,
        claim_id_or_location,
        file_path_prefix,
        yes: bool,
        dry_run: bool,
    ) -> None:
        """Hard-delete a claim (or bulk-delete by path prefix).

        Provide either a positional CLAIM_ID_OR_LOCATION (a claim_id, a
        location string like 'paper.tex:L42', or a bare file path), OR
        ``--file-path-prefix`` to remove all claims under a path root.
        These are mutually exclusive.

        Without ``-y/--yes`` the command refuses to act (no interactive
        prompts).  Use ``--dry-run`` to preview without deleting.
        """
        from scitex_clew import remove_claim
        from scitex_clew._claim import list_claims, remove_claims_by_prefix

        if claim_id_or_location and file_path_prefix:
            click.echo(
                "ERROR: provide either CLAIM_ID_OR_LOCATION or "
                "--file-path-prefix, not both.",
                err=True,
            )
            ctx.exit(1)
            return
        if not claim_id_or_location and not file_path_prefix:
            click.echo(
                "ERROR: provide either CLAIM_ID_OR_LOCATION or "
                "--file-path-prefix.",
                err=True,
            )
            ctx.exit(1)
            return

        if file_path_prefix:
            matched = list_claims(
                file_path_prefix=file_path_prefix,
                limit=10_000,
                include_superseded=True,
            )
            count = len(matched)
            if count == 0:
                msg = f"No claims found under prefix '{file_path_prefix}'."
                payload = {"deleted": 0, "file_path_prefix": file_path_prefix}
                _emit(ctx, payload, msg)
                return
            if dry_run:
                msg = (
                    f"[DRY RUN] Would remove {count} claim(s) under "
                    f"'{file_path_prefix}'."
                )
                payload = {
                    "dry_run": True,
                    "would_delete": count,
                    "file_path_prefix": file_path_prefix,
                }
                _emit(ctx, payload, msg)
                return
            if not yes:
                click.echo(
                    f"ERROR: removing {count} claim(s) under "
                    f"'{file_path_prefix}' is destructive. "
                    "Pass -y/--yes to confirm.",
                    err=True,
                )
                ctx.exit(1)
                return
            deleted = remove_claims_by_prefix(file_path_prefix)
            msg = f"[REMOVED] {deleted} claim(s) under prefix '{file_path_prefix}'."
            payload = {"deleted": deleted, "file_path_prefix": file_path_prefix}
            _emit(ctx, payload, msg)
            return

        if dry_run:
            msg = f"[DRY RUN] Would remove claim '{claim_id_or_location}'."
            payload = {"dry_run": True, "claim_id_or_location": claim_id_or_location}
            _emit(ctx, payload, msg)
            return
        if not yes:
            click.echo(
                f"ERROR: permanently deleting claim '{claim_id_or_location}' "
                "is destructive. Pass -y/--yes to confirm.",
                err=True,
            )
            ctx.exit(1)
            return
        found = remove_claim(claim_id_or_location)
        if found:
            msg = f"[REMOVED] claim '{claim_id_or_location}'."
            payload = {"removed": True, "claim_id_or_location": claim_id_or_location}
        else:
            msg = f"No claim found for '{claim_id_or_location}'."
            payload = {"removed": False, "claim_id_or_location": claim_id_or_location}
        _emit(ctx, payload, msg)
        if not found:
            ctx.exit(1)

    @claim_group.command(
        "supersede",
        epilog=(
            "Example:\n"
            "  $ clew claim supersede claim_abc123\n"
            "  $ clew claim supersede paper.tex:L42\n"
            "  $ clew claim supersede --file-path-prefix /old/papers/ -y"
        ),
    )
    @click.argument("claim_id_or_location", required=False, default=None)
    @click.option(
        "--file-path-prefix",
        "file_path_prefix",
        default=None,
        help="Bulk-supersede all claims whose file_path starts with this prefix.",
    )
    @click.option(
        "-y",
        "--yes",
        "yes",
        is_flag=True,
        help="Required for bulk operations (--file-path-prefix). No-op for single.",
    )
    @click.pass_context
    def claim_supersede(
        ctx: click.Context,
        claim_id_or_location,
        file_path_prefix,
        yes: bool,
    ) -> None:
        """Soft-retire a claim (keeps audit trail; excluded from verify gate).

        Superseded claims are excluded from ``clew verify`` and the default
        ``clew claim list`` view but remain in the DB for audit purposes.

        Provide either a positional CLAIM_ID_OR_LOCATION (a claim_id, a
        location string like 'paper.tex:L42', or a bare file path), OR
        ``--file-path-prefix`` to supersede all claims under a path root.
        These are mutually exclusive.

        Bulk operations (``--file-path-prefix``) require ``-y/--yes``; no
        interactive prompts are shown.
        """
        from scitex_clew import supersede_claim
        from scitex_clew._claim import list_claims, supersede_claims_by_prefix

        if claim_id_or_location and file_path_prefix:
            click.echo(
                "ERROR: provide either CLAIM_ID_OR_LOCATION or "
                "--file-path-prefix, not both.",
                err=True,
            )
            ctx.exit(1)
            return
        if not claim_id_or_location and not file_path_prefix:
            click.echo(
                "ERROR: provide either CLAIM_ID_OR_LOCATION or "
                "--file-path-prefix.",
                err=True,
            )
            ctx.exit(1)
            return

        if file_path_prefix:
            matched = list_claims(
                file_path_prefix=file_path_prefix,
                limit=10_000,
                include_superseded=False,
            )
            count = len(matched)
            if count == 0:
                msg = f"No active claims found under prefix '{file_path_prefix}'."
                payload = {"superseded": 0, "file_path_prefix": file_path_prefix}
                _emit(ctx, payload, msg)
                return
            if not yes:
                click.echo(
                    f"ERROR: superseding {count} claim(s) under "
                    f"'{file_path_prefix}' is a bulk operation. "
                    "Pass -y/--yes to confirm.",
                    err=True,
                )
                ctx.exit(1)
                return
            updated = supersede_claims_by_prefix(file_path_prefix)
            msg = (
                f"[SUPERSEDED] {updated} claim(s) under prefix "
                f"'{file_path_prefix}'."
            )
            payload = {"superseded": updated, "file_path_prefix": file_path_prefix}
            _emit(ctx, payload, msg)
            return

        found = supersede_claim(claim_id_or_location)
        if found:
            msg = f"[SUPERSEDED] claim '{claim_id_or_location}'."
            payload = {
                "superseded": True,
                "claim_id_or_location": claim_id_or_location,
            }
        else:
            msg = f"No claim found for '{claim_id_or_location}'."
            payload = {
                "superseded": False,
                "claim_id_or_location": claim_id_or_location,
            }
        _emit(ctx, payload, msg)
        if not found:
            ctx.exit(1)


# EOF
