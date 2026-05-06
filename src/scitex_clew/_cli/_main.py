#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main CLI entry point for scitex-clew.

Universal output mode
---------------------
Every subcommand respects the top-level ``--json`` flag (F5). The flag is
stored on ``ctx.obj['json']`` and read by helpers in ``_claim`` / ``_hash``
/ ``_stamp`` and inline in this module via ``_json_mode(ctx)``.
"""

from __future__ import annotations

import json
import sys

try:
    import click
except ImportError:
    # Graceful fallback: if click is not installed, print a helpful message
    # and fall back to the minimal argparse behavior.
    def main(argv=None):
        print(
            "ERROR: click is not installed. Install with: pip install scitex-clew[cli]",
            file=sys.stderr,
        )
        raise SystemExit(1)

else:
    from ._claim import _json_mode, claim
    from ._hash import hash_directory, hash_file
    from ._introspect import list_python_apis
    from ._mcp import mcp
    from ._stamp import check_stamp, list_stamps, stamp

    CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}

    COMMAND_CATEGORIES = [
        ("Verification", ["status", "list", "verify", "stats", "dag"]),
        ("Claims", ["claim"]),
        ("Hashing", ["hash-file", "hash-directory"]),
        ("Stamping", ["stamp", "list-stamps", "check-stamp"]),
        ("Visualization", ["mermaid"]),
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
        """clew - Hash-based reproducibility verification for scientific pipelines."""
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

    # -----------------------------------------------------------------------
    # Subcommands: status, list, verify, stats, mermaid, dag
    # -----------------------------------------------------------------------

    @main.command()
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help="Emit JSON (also accepted at top level).",
    )
    @click.pass_context
    def status(ctx: click.Context, as_json: bool):
        """Git-status-like overview of verification state."""
        import scitex_clew as clew

        if as_json:
            ctx.obj = ctx.obj or {}
            ctx.obj["json"] = True

        result = clew.status()
        # status has historically printed indented JSON; preserve that as the
        # default human output and emit pure JSON when --json is set.
        if _json_mode(ctx):
            click.echo(json.dumps(result, default=str))
        else:
            click.echo(json.dumps(result, indent=2, default=str))

    @main.command("list")
    @click.option("--limit", type=int, default=50, help="Maximum number of runs.")
    @click.option(
        "--status",
        "status_filter",
        default=None,
        help="Filter by status (success/failed/running).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
    @click.pass_context
    def list_runs(ctx: click.Context, limit: int, status_filter, as_json: bool):
        """List tracked runs."""
        import scitex_clew as clew

        if as_json:
            ctx.obj = ctx.obj or {}
            ctx.obj["json"] = True

        runs = clew.list_runs(limit=limit, status=status_filter)
        if _json_mode(ctx):
            click.echo(
                json.dumps({"count": len(runs), "runs": runs}, indent=2, default=str)
            )
            return

        for r in runs:
            sid = r["session_id"]
            run_status = r.get("status", "?")
            script = r.get("script_path", "")
            click.echo(f"  {run_status:<8} {sid}  {script}")

    @main.command()
    @click.argument("session_id")
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
    @click.pass_context
    def verify(ctx: click.Context, session_id: str, as_json: bool):
        """Verify a specific run by session ID."""
        import scitex_clew as clew

        if as_json:
            ctx.obj = ctx.obj or {}
            ctx.obj["json"] = True

        result = clew.run(session_id)

        if _json_mode(ctx):
            payload = {
                "session_id": result.session_id,
                "script_path": result.script_path,
                "status": result.status.value,
                "is_verified": result.is_verified,
                "files": [
                    {
                        "path": f.path,
                        "role": f.role,
                        "status": f.status.value,
                        "expected_hash": f.expected_hash,
                        "current_hash": f.current_hash,
                        "is_verified": f.is_verified,
                    }
                    for f in result.files
                ],
            }
            click.echo(json.dumps(payload, indent=2, default=str))
            return

        icon = "OK" if result.is_verified else "FAIL"
        click.echo(f"[{icon}] {result.session_id} ({result.status.value})")
        for f in result.files:
            ficon = "OK" if f.is_verified else "!!"
            click.echo(f"  [{ficon}] {f.role:<6} {f.path}")

    @main.command()
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
    @click.pass_context
    def stats(ctx: click.Context, as_json: bool):
        """Database statistics."""
        import scitex_clew as clew

        if as_json:
            ctx.obj = ctx.obj or {}
            ctx.obj["json"] = True

        result = clew.stats()
        if _json_mode(ctx):
            click.echo(json.dumps(result, default=str))
        else:
            click.echo(json.dumps(result, indent=2, default=str))

    @main.command()
    @click.option("--claims", is_flag=True, help="Build DAG from registered claims.")
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
    @click.pass_context
    def mermaid(ctx: click.Context, claims: bool, as_json: bool):
        """Generate Mermaid DAG diagram."""
        import scitex_clew as clew

        if as_json:
            ctx.obj = ctx.obj or {}
            ctx.obj["json"] = True

        code = clew.mermaid(claims=claims)
        if _json_mode(ctx):
            click.echo(json.dumps({"mermaid": code, "claims": claims}, default=str))
        else:
            click.echo(code)

    @main.command()
    @click.option(
        "--target",
        "targets",
        multiple=True,
        help="Target file(s). Repeat for multiple targets.",
    )
    @click.option(
        "--claims",
        is_flag=True,
        help="Build DAG from all registered claims (instead of explicit targets).",
    )
    @click.option(
        "--strict",
        is_flag=True,
        help="On hash mismatch, return failure-attribution payload (F2).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
    @click.pass_context
    def dag(
        ctx: click.Context,
        targets,
        claims: bool,
        strict: bool,
        as_json: bool,
    ):
        """Verify the DAG for one or more targets (or every claim).

        \b
        Examples:
          clew dag --target results/foo.csv --json
          clew dag --claims --strict --json
        """
        from scitex_clew._claim import verify_claims_dag
        from scitex_clew._dag import verify_dag, verify_dag_strict

        if as_json:
            ctx.obj = ctx.obj or {}
            ctx.obj["json"] = True

        # F2: strict mode → failure attribution dict (always JSON-shaped).
        if strict:
            payload = verify_dag_strict(
                targets=list(targets) or None,
                claims=claims,
            )
            # Compact JSON when --json explicit, else indent=2 for readability.
            indent = None if _json_mode(ctx) else 2
            click.echo(json.dumps(payload, indent=indent, default=str))
            return

        # Non-strict: existing DAGVerification surface.
        if claims:
            result = verify_claims_dag()
        else:
            result = verify_dag(list(targets))

        payload = {
            "target_files": result.target_files,
            "status": result.status.value,
            "is_verified": result.is_verified,
            "num_runs": len(result.runs),
            "num_edges": len(result.edges),
            "topological_order": result.topological_order,
            "runs": [
                {
                    "session_id": r.session_id,
                    "script_path": r.script_path,
                    "status": r.status.value,
                    "is_verified": r.is_verified,
                }
                for r in result.runs
            ],
            "edges": [{"parent": p, "child": c} for p, c in result.edges],
        }

        if _json_mode(ctx):
            click.echo(json.dumps(payload, indent=2, default=str))
            return

        # Human summary
        icon = "OK" if result.is_verified else "FAIL"
        click.echo(
            f"[{icon}] DAG status={result.status.value} "
            f"runs={len(result.runs)} edges={len(result.edges)}"
        )
        for r in result.runs:
            ficon = "OK" if r.is_verified else "!!"
            click.echo(
                f"  [{ficon}] {r.session_id} ({r.status.value})  {r.script_path or ''}"
            )

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
    # Register integration / claim / hash / stamp commands
    # -----------------------------------------------------------------------

    main.add_command(list_python_apis)
    main.add_command(mcp)

    # F1: claim group, hash-file/-directory, stamp / list-stamps / check-stamp.
    main.add_command(claim)
    main.add_command(hash_file)
    main.add_command(hash_directory)
    main.add_command(stamp)
    main.add_command(list_stamps)
    main.add_command(check_stamp)

    try:
        from scitex_dev.cli import docs_click_group

        main.add_command(docs_click_group(package="scitex-clew"))
    except ImportError:
        pass

    try:
        from scitex_dev.cli import skills_click_group

        main.add_command(skills_click_group(package="scitex-clew"))
    except ImportError:
        pass

    # §1a: install-shell-completion + print-shell-completion (canonical leaves)
    try:
        from scitex_dev._cli._completion import attach_shell_completion

        attach_shell_completion(main, prog_name="scitex-clew")
    except ImportError:
        pass


# audit §4 — inject version into root --help
try:
    from importlib.metadata import version as _v
    main.help = (
        f"scitex-clew (v{_v('scitex-clew')}) — "
        + (main.help or "").lstrip()
    )
except Exception:
    pass

# audit-cli §1a — packages with _skills/ MUST expose
# `<cli> skills {list,get,install}`.
from ._skills import skills_group as _skills_group

main.add_command(_skills_group, name="skills")
