#!/usr/bin/env python3
"""MCP wrappers for the citation API (\\cite -> scholar-verified source gate).

Each tool mirrors a Python signature in :mod:`scitex_clew._citation` one-for-one
(per §6 MCP-parity: ``scitex_clew.add_citation`` -> ``clew_add_citation``).
Output is always indented JSON, matching ``claims.py`` / ``verification.py``.
"""

from __future__ import annotations

import json
from typing import List, Optional

from fastmcp import FastMCP


def _json(data) -> str:
    return json.dumps(data, indent=2, default=str)


def register_tools(mcp: FastMCP) -> None:
    """Register clew_add_citation / list_citations / verify_citations / verify_all."""

    @mcp.tool()
    async def clew_add_citation(
        cite_key: str,
        manuscript_file: Optional[str] = None,
        line_number: Optional[int] = None,
        doi: Optional[str] = None,
        source_id: Optional[str] = None,
        metadata: Optional[dict] = None,
        url: Optional[str] = None,
        is_stub: bool = False,
        resolved: bool = True,
    ) -> str:
        """Register (push) a scholar-resolved citation node into the clew ledger.

        Mirrors ``scitex_clew.add_citation`` exactly. This is the push-model
        write path: scholar resolves a ``\\cite`` key to a real source and
        records the outcome here.

        Parameters
        ----------
        cite_key : str
            BibTeX citation key (e.g. 'Berens2009CircStat').
        manuscript_file : str, optional
            Manuscript the key is cited from.
        line_number : int, optional
            Line number of the ``\\cite`` in the manuscript.
        doi : str, optional
            Resolved DOI of the real source (None for a stub / unresolved).
        source_id : str, optional
            Scholar's internal source identifier.
        metadata : dict, optional
            Bib fields (author/year/title/journal/doi) for the content hash.
        url : str, optional
            Explicit source URL (takes precedence over the derived doi.org
            link — supply for no-DOI CorpusId-only records).
        is_stub : bool, optional
            True if scholar flagged this as a stub / placeholder.
        resolved : bool, optional
            True if scholar resolved the key to a real source.
        """
        from scitex_clew import add_citation

        try:
            c = add_citation(
                cite_key,
                manuscript_file=manuscript_file,
                line_number=line_number,
                doi=doi,
                source_id=source_id,
                metadata=metadata,
                url=url,
                is_stub=is_stub,
                resolved=resolved,
            )
        except ValueError as exc:
            return _json({"error": str(exc), "citation": None})
        return _json(c.to_dict())

    @mcp.tool()
    async def clew_list_citations(
        manuscript_file: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 1000,
    ) -> str:
        """List registered citation nodes with optional filters.

        Mirrors ``scitex_clew.list_citations`` exactly.

        Parameters
        ----------
        manuscript_file : str, optional
            Filter by manuscript file path.
        status : str, optional
            Filter by status (verified/stub/unverified/unknown).
        limit : int, optional
            Maximum nodes to list.
        """
        from scitex_clew import list_citations

        cits = list_citations(
            manuscript_file=manuscript_file, status=status, limit=limit
        )
        return _json({"count": len(cits), "citations": [c.to_dict() for c in cits]})

    @mcp.tool()
    async def clew_verify_citations(entries: List[dict]) -> str:
        """Return the per-key verdict map the compiler gates on.

        Mirrors ``scitex_clew.verify_citations`` exactly.

        Parameters
        ----------
        entries : list of dict
            Cited keys. Each dict carries at least 'key' plus any bib fields
            (doi/journal/note/title/author/year). Returns
            ``{cite_key: {status, doi, source_id, reason}}`` where status is
            one of {verified, stub, unverified, unknown}.
        """
        from scitex_clew import verify_citations

        return _json(verify_citations(entries))

    @mcp.tool()
    async def clew_verify_all_citations(
        entries: List[dict], strict: bool = False
    ) -> str:
        """Reduce cited keys to a fail-loud VerificationResult (same-run gate).

        Mirrors ``scitex_clew.verify_all_citations`` exactly.

        Parameters
        ----------
        entries : list of dict
            Cited keys (see clew_verify_citations).
        strict : bool, optional
            Reserved for parity with the claim gate.
        """
        from scitex_clew import verify_all_citations

        result = verify_all_citations(entries, strict=strict)
        return _json(result.to_dict())


# EOF
