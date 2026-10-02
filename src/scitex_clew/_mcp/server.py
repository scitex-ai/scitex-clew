#!/usr/bin/env python3
"""Standalone MCP server for scitex-clew.

Run with: fastmcp run scitex_clew._mcp.server:mcp
"""

try:
    from fastmcp import FastMCP
except ImportError as exc:
    if exc.name != "fastmcp":
        raise
    raise ImportError(
        "fastmcp is required for MCP support; install with: pip install 'scitex-clew[all]'"
    ) from exc

from .tools import register_all_tools

mcp = FastMCP(
    name="scitex-clew",
    instructions=(
        "Hash-based reproducibility verification for scientific pipelines. "
        "Use clew_status for overview, clew_run to verify sessions, "
        "clew_chain to trace provenance, clew_dag for full DAG verification."
    ),
)

register_all_tools(mcp)

# EOF
