#!/usr/bin/env python3
# Timestamp: "2026-05-05 (ywatanabe)"
"""MCP wrappers for the hashing API (F1)."""

from __future__ import annotations

import json

from fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, indent=2, default=str)


def register_tools(mcp: FastMCP) -> None:
    """Register clew_hash_file / clew_hash_directory."""

    @mcp.tool()
    async def clew_hash_file(
        path: str,
        algorithm: str = "sha256",
        chunk_size: int = 8192,
    ) -> str:
        """Compute the SHA-256 (first 32 chars) of a file.

        Mirrors ``scitex_clew.hash_file``.
        """
        from scitex_clew import hash_file

        try:
            h = hash_file(path, algorithm=algorithm, chunk_size=chunk_size)
        except FileNotFoundError as exc:
            return _json({"error": str(exc), "path": path})
        return _json({"path": path, "algorithm": algorithm, "hash": h})

    @mcp.tool()
    async def clew_hash_directory(
        path: str,
        pattern: str = "*",
        recursive: bool = True,
        algorithm: str = "sha256",
    ) -> str:
        """Compute SHA-256 for every file in a directory.

        Mirrors ``scitex_clew.hash_directory``.
        """
        from scitex_clew import hash_directory

        try:
            hashes = hash_directory(
                path,
                pattern=pattern,
                recursive=recursive,
                algorithm=algorithm,
            )
        except NotADirectoryError as exc:
            return _json({"error": str(exc), "path": path})
        return _json(
            {
                "path": path,
                "pattern": pattern,
                "recursive": recursive,
                "algorithm": algorithm,
                "count": len(hashes),
                "hashes": hashes,
            }
        )


# EOF
