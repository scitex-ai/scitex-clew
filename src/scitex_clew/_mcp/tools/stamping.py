#!/usr/bin/env python3
# Timestamp: "2026-05-05 (ywatanabe)"
"""MCP wrappers for the stamping API (F1)."""

from __future__ import annotations

import json
from typing import Optional

from fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, indent=2, default=str)


def register_tools(mcp: FastMCP) -> None:
    """Register clew_stamp / clew_list_stamps / clew_check_stamp."""

    @mcp.tool()
    async def clew_stamp(
        backend: str = "file",
        service_url: Optional[str] = None,
        session_ids: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> str:
        """Record a temporal stamp (root hash + ISO-8601 timestamp).

        Mirrors ``scitex_clew.stamp``.

        Parameters
        ----------
        backend : str
            'file' | 'rfc3161' | 'zenodo' | 'scitex_cloud'.
        service_url : str, optional
            TSA / API URL.
        session_ids : str, optional
            Comma-separated list of session IDs (default: all successful).
        output_dir : str, optional
            Directory for file-based stamps.
        """
        from scitex_clew import stamp

        sids = None
        if session_ids:
            sids = [s.strip() for s in session_ids.split(",") if s.strip()]

        try:
            s = stamp(
                backend=backend,
                service_url=service_url,
                session_ids=sids,
                output_dir=output_dir,
            )
        except ValueError as exc:
            return _json({"error": str(exc), "stamp": None})

        return _json(s.to_dict())

    @mcp.tool()
    async def clew_list_stamps(limit: int = 20) -> str:
        """List recorded stamps. Mirrors ``scitex_clew.list_stamps``."""
        from scitex_clew import list_stamps

        stamps = list_stamps(limit=limit)
        return _json({"count": len(stamps), "stamps": [s.to_dict() for s in stamps]})

    @mcp.tool()
    async def clew_check_stamp(stamp_id: Optional[str] = None) -> str:
        """Verify a stamp (or the latest). Mirrors ``scitex_clew.check_stamp``."""
        from scitex_clew import check_stamp

        return _json(check_stamp(stamp_id=stamp_id))


# EOF
