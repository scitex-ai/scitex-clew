#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP server commands for scitex-clew."""

import click


@click.group(invoke_without_command=True)
@click.option("--help-recursive", is_flag=True, help="Show help for all subcommands.")
@click.pass_context
def mcp(ctx, help_recursive):
    """MCP (Model Context Protocol) server commands."""
    if help_recursive:
        _print_help_recursive(ctx)
        ctx.exit(0)
    elif ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def _print_help_recursive(ctx):
    """Print help for mcp and all its subcommands."""
    fake_parent = click.Context(click.Group(), info_name="clew")
    parent_ctx = click.Context(mcp, info_name="mcp", parent=fake_parent)

    click.secho("=== clew mcp ===", fg="cyan", bold=True)
    click.echo(mcp.get_help(parent_ctx))

    for name in sorted(mcp.list_commands(ctx) or []):
        cmd = mcp.get_command(ctx, name)
        if cmd is None:
            continue
        click.echo()
        click.secho(f"=== clew mcp {name} ===", fg="cyan", bold=True)
        with click.Context(cmd, info_name=name, parent=parent_ctx) as sub_ctx:
            click.echo(cmd.get_help(sub_ctx))


def _format_tool_signature(tool, multiline: bool = False, indent: str = "  ") -> str:
    """Format MCP tool as Python-like function signature."""
    import inspect

    params = []
    if hasattr(tool, "parameters") and tool.parameters:
        schema = tool.parameters
        props = schema.get("properties", {})
        required = schema.get("required", [])
        for name, info in props.items():
            ptype = info.get("type", "any")
            default = info.get("default")
            if name in required:
                p = (
                    f"{click.style(name, fg='white', bold=True)}: "
                    f"{click.style(ptype, fg='cyan')}"
                )
            elif default is not None:
                def_str = repr(default) if len(repr(default)) < 20 else "..."
                p = (
                    f"{click.style(name, fg='white', bold=True)}: "
                    f"{click.style(ptype, fg='cyan')} = "
                    f"{click.style(def_str, fg='yellow')}"
                )
            else:
                p = (
                    f"{click.style(name, fg='white', bold=True)}: "
                    f"{click.style(ptype, fg='cyan')} = "
                    f"{click.style('None', fg='yellow')}"
                )
            params.append(p)

    ret_type = ""
    if hasattr(tool, "fn") and tool.fn:
        try:
            sig = inspect.signature(tool.fn)
            if sig.return_annotation != inspect.Parameter.empty:
                ret = sig.return_annotation
                ret_name = ret.__name__ if hasattr(ret, "__name__") else str(ret)
                ret_type = f" -> {click.style(ret_name, fg='magenta')}"
        except Exception:
            pass

    name_s = click.style(tool.name, fg="green", bold=True)
    if multiline and len(params) > 2:
        param_indent = indent + "    "
        params_str = ",\n".join(f"{param_indent}{p}" for p in params)
        return f"{indent}{name_s}(\n{params_str}\n{indent}){ret_type}"
    return f"{indent}{name_s}({', '.join(params)}){ret_type}"


@mcp.command(
    "list-tools",
    epilog=(
        "Example:\n"
        "  $ scitex-clew mcp list-tools\n"
        "  $ scitex-clew mcp list-tools -vv\n"
        "  $ scitex-clew mcp list-tools --json"
    ),
)
@click.option(
    "-v", "--verbose", count=True, help="Verbosity: -v sig, -vv +desc1, -vvv full."
)
@click.option("-c", "--compact", is_flag=True, help="Compact signatures (single line).")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_tools(verbose: int, compact: bool, as_json: bool) -> None:
    """List available MCP tools.

    \b
    Verbosity levels:
      (none)  Tool names only
      -v      Full signatures
      -vv     Signatures + first line of description
      -vvv    Signatures + full description
    """
    try:
        from .._mcp.server import mcp as mcp_server
    except ImportError as e:
        raise click.ClickException(
            f"fastmcp not installed. Install with: pip install scitex-clew[mcp]\n{e}"
        ) from e

    from .._mcp import get_tools_sync

    tools = get_tools_sync(mcp_server)
    total = len(tools)

    if as_json:
        import json

        output = {
            "total": total,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description or "",
                }
                for t in tools
            ],
        }
        click.echo(json.dumps(output, indent=2))
        return

    click.secho(f"scitex-clew MCP: {total} tools", fg="cyan", bold=True)
    click.echo()

    for tool in sorted(tools, key=lambda t: t.name):
        if verbose == 0:
            click.echo(f"  {tool.name}")
        elif verbose == 1:
            sig = _format_tool_signature(tool, multiline=not compact)
            click.echo(sig)
        elif verbose == 2:
            sig = _format_tool_signature(tool, multiline=not compact)
            click.echo(sig)
            if tool.description:
                desc = tool.description.split("\n")[0].strip()
                click.echo(f"    {desc}")
            click.echo()
        else:
            sig = _format_tool_signature(tool, multiline=not compact)
            click.echo(sig)
            if tool.description:
                for line in tool.description.strip().split("\n"):
                    click.echo(f"    {line}")
            click.echo()


@mcp.command(
    "start",
    epilog=("Example:\n  $ scitex-clew mcp start\n  $ scitex-clew mcp start --dry-run"),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate dependencies and report what would be served; do not start the server.",
)
@click.option(
    "-y",
    "--yes",
    "yes",
    is_flag=True,
    help="Confirmation flag retained for §2 audit-cli compliance.",
)
def start_server(dry_run: bool, yes: bool) -> None:
    """Start the scitex-clew MCP server."""
    del yes  # accepted for §2 compliance
    try:
        from .._mcp.server import mcp as mcp_server
    except ImportError as e:
        raise click.ClickException(
            f"Failed to import MCP server. "
            f"Install fastmcp: pip install scitex-clew[mcp]\n{e}"
        ) from e

    if dry_run:
        from .._mcp import get_tools_sync

        tool_count = len(get_tools_sync(mcp_server))
        click.echo(
            f"DRY RUN — would serve scitex-clew MCP ({tool_count} tools) over stdio"
        )
        return

    click.echo("Starting scitex-clew MCP server...")
    mcp_server.run()


@mcp.command(
    "installation", hidden=True, context_settings={"ignore_unknown_options": True}
)
@click.pass_context
def installation_deprecated(ctx) -> None:
    """(deprecated) Renamed to `install`."""
    click.echo(
        "error: `clew mcp installation` was renamed to `clew mcp install`.\n"
        "Re-run with: clew mcp install",
        err=True,
    )
    ctx.exit(2)


@mcp.command(
    "install",
    epilog=(
        "Example:\n  $ scitex-clew mcp install\n  $ scitex-clew mcp install --dry-run"
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Accepted for §2; this verb is informational, never mutates state.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Accepted for §2; this verb is informational, never mutates state.",
)
def install(dry_run, yes) -> None:
    """Show installation instructions for MCP server integration."""
    del dry_run, yes  # audit §2 — no-op flags
    click.echo("Install scitex-clew with MCP support:")
    click.echo()
    click.echo("  pip install scitex-clew[mcp]")
    click.echo()
    click.echo("Add to your MCP client configuration:")
    click.echo()
    click.echo("  {")
    click.echo('    "mcpServers": {')
    click.echo('      "scitex-clew": {')
    click.echo('        "command": "clew",')
    click.echo('        "args": ["mcp", "start"]')
    click.echo("      }")
    click.echo("    }")
    click.echo("  }")
    click.echo()
    click.echo("Verify with:")
    click.echo("  clew mcp doctor")
    click.echo("  clew mcp list-tools")


@mcp.command(
    "doctor",
    epilog=("Example:\n  $ scitex-clew mcp doctor"),
)
def doctor() -> None:
    """Check MCP server dependencies and configuration."""
    click.echo("Checking MCP dependencies...")

    try:
        import fastmcp

        click.echo(f"  [OK] fastmcp {fastmcp.__version__}")
    except ImportError:
        click.echo("  [!!] fastmcp not installed")
        click.echo("    Install with: pip install scitex-clew[mcp]")
        return

    try:
        from .._mcp.server import mcp as mcp_server
        from .._mcp import get_tools_sync

        tool_count = len(get_tools_sync(mcp_server))
        click.echo(f"  [OK] MCP server loaded ({tool_count} tools)")
    except Exception as e:
        click.echo(f"  [!!] MCP server error: {e}")
        return

    click.echo()
    click.echo("MCP server is ready.")
    click.echo("Run with: clew mcp start")
