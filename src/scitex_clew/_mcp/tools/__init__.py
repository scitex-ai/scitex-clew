#!/usr/bin/env python3
"""MCP tool registration for scitex-clew."""

from fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register all clew MCP tools with the server."""
    from . import citations, claims, hashing, skills, stamping, verification

    verification.register_tools(mcp)
    claims.register_tools(mcp)
    citations.register_tools(mcp)
    hashing.register_tools(mcp)
    stamping.register_tools(mcp)
    skills.register_tools(mcp)


__all__ = ["register_all_tools"]

# EOF
