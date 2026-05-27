#!/usr/bin/env python3
# Timestamp: "2026-05-05 (ywatanabe)"
"""MCP wrappers for the claim API (F1).

Each tool is a one-for-one mirror of the Python signature in
``scitex_clew._claim``. Output is always indented JSON, matching the style
of ``verification.py``.
"""

from __future__ import annotations

import json
from typing import Optional

from fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, indent=2, default=str)


def register_tools(mcp: FastMCP) -> None:
    """Register clew_add_claim / list_claims / verify_claim.

    Tool names mirror the Python-API names exactly (per §6 MCP-parity
    rule): `scitex_clew.add_claim` → `clew_add_claim`, etc. The earlier
    `clew_claim_<verb>` naming created spurious §6 misses.
    """

    @mcp.tool()
    async def clew_add_claim(
        file_path: str,
        claim_type: str,
        line_number: Optional[int] = None,
        claim_value: Optional[str] = None,
        source_file: Optional[str] = None,
        source_session: Optional[str] = None,
    ) -> str:
        """Register a manuscript claim linking an assertion to its source file/session.

        Mirrors ``scitex_clew.add_claim`` exactly.

        Parameters
        ----------
        file_path : str
            Path to the manuscript file (e.g., paper.tex).
        claim_type : str
            One of: statistic, figure, table, text, value.
        line_number : int, optional
            Line number in the manuscript.
        claim_value : str, optional
            The asserted value (e.g., 'p = 0.003').
        source_file : str, optional
            Path to the source file that produced the claim.
        source_session : str, optional
            Session ID that produced the source.
        """
        from scitex_clew import add_claim

        try:
            c = add_claim(
                file_path=file_path,
                claim_type=claim_type,
                line_number=line_number,
                claim_value=claim_value,
                source_file=source_file,
                source_session=source_session,
            )
        except ValueError as exc:
            return _json({"error": str(exc), "claim": None})
        return _json(c.to_dict())

    @mcp.tool()
    async def clew_list_claims(
        file_path: Optional[str] = None,
        claim_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> str:
        """List registered claims with optional filters.

        Mirrors ``scitex_clew.list_claims``.
        """
        from scitex_clew import list_claims

        claims = list_claims(
            file_path=file_path,
            claim_type=claim_type,
            status=status,
            limit=limit,
        )
        return _json({"count": len(claims), "claims": [c.to_dict() for c in claims]})

    @mcp.tool()
    async def clew_verify_claim(
        claim_id_or_location: str,
    ) -> str:
        """Verify a registered claim by id or 'file.tex:L42'.

        Mirrors ``scitex_clew.verify_claim``.
        """
        from scitex_clew import verify_claim

        return _json(verify_claim(claim_id_or_location))

    @mcp.tool()
    async def clew_register_intermediate(
        name: str,
        value: str,
        supports: Optional[str] = None,
        session_id: Optional[str] = None,
        claim_type: str = "value",
    ) -> str:
        """Record a computed intermediate value (a scalar/array/result produced mid-pipeline) as a claim in the provenance DAG, with explicit upstream dependencies — so a future inspector can trace and re-verify how that number was derived. Use whenever an agent or script computes a non-trivial intermediate the user may later cite ("there were 42 significant pathways", "the median latency was 13ms") and asks to "record this value", "log this intermediate", "register this result with its inputs", or "make this number reproducible". Mirrors ``scitex_clew.register_intermediate``.

        Parameters
        ----------
        name : str
            Descriptive identifier (e.g. 'n_sig_pathways'). Avoid generic names
            like 'result_3' — this id is the only handle on the value later.
        value : str
            The computed value (stored as its repr for the hash chain).
        supports : str, optional
            Comma-separated upstream claim/session ids this value depends on.
        session_id : str, optional
            Session this value belongs to. Defaults to $SCITEX_SESSION_ID.
        claim_type : str, optional
            One of: statistic, figure, table, text, value (default: value).
        """
        from scitex_clew import register_intermediate

        supports_list = (
            [s.strip() for s in supports.split(",") if s.strip()] if supports else None
        )
        try:
            c = register_intermediate(
                name=name,
                value=value,
                supports=supports_list,
                session_id=session_id,
                claim_type=claim_type,
            )
        except ValueError as exc:
            return _json({"error": str(exc), "claim": None})
        return _json(c.to_dict())


# EOF
