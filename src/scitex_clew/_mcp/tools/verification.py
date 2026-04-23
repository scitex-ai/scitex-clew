#!/usr/bin/env python3
"""Clew verification MCP tools.

Single source of truth for all clew MCP tool definitions.
scitex-python delegates to these via register_all_tools().
"""

import json
from typing import Optional

from fastmcp import FastMCP


def _json(data: dict) -> str:
    return json.dumps(data, indent=2, default=str)


def _format_dag_result(dag_result) -> str:
    """Format DAGVerification to JSON string."""
    return _json(
        {
            "target_files": dag_result.target_files,
            "status": dag_result.status.value,
            "is_verified": dag_result.is_verified,
            "num_runs": len(dag_result.runs),
            "num_edges": len(dag_result.edges),
            "topological_order": dag_result.topological_order,
            "runs": [
                {
                    "session_id": r.session_id,
                    "script_path": r.script_path,
                    "status": r.status.value,
                    "is_verified": r.is_verified,
                }
                for r in dag_result.runs
            ],
            "edges": [{"parent": p, "child": c} for p, c in dag_result.edges],
        }
    )


def register_tools(mcp: FastMCP) -> None:
    """Register all clew verification tools."""

    @mcp.tool()
    async def clew_list(
        limit: int = 50,
        status_filter: Optional[str] = None,
    ) -> str:
        """List every tracked session run (script execution) with its current hash-verification status — answers "what experiments have I run?" and "which ones are still reproducible?". Use when the user asks to show runs, list sessions, or audit pipeline history.

        Parameters
        ----------
        limit : int, optional
            Maximum number of runs to return (default: 50)
        status_filter : str, optional
            Filter by status: 'success', 'failed', 'running', or None for all

        Returns
        -------
        str
            JSON with list of runs and their verification status
        """
        from scitex_clew import list_runs, run

        runs = list_runs(status=status_filter, limit=limit)

        results = []
        for r in runs:
            verification = run(r["session_id"])
            results.append(
                {
                    "session_id": r["session_id"],
                    "script_path": r.get("script_path"),
                    "db_status": r.get("status"),
                    "verification_status": verification.status.value,
                    "is_verified": verification.is_verified,
                    "started_at": r.get("started_at"),
                    "finished_at": r.get("finished_at"),
                }
            )

        return _json({"count": len(results), "runs": results})

    @mcp.tool()
    async def clew_run(
        session_or_path: str,
    ) -> str:
        """Verify a specific session run by checking all file hashes.

        Parameters
        ----------
        session_or_path : str
            Session ID (e.g., '2025Y-11M-18D-09h12m03s_HmH5') or
            path to a file to find its associated session

        Returns
        -------
        str
            JSON with verification results including file-level details
        """
        from pathlib import Path

        from scitex_clew import get_db, run

        path = Path(session_or_path)
        if path.exists():
            db = get_db()
            sessions = db.find_session_by_file(str(path.resolve()), role="output")
            if not sessions:
                sessions = db.find_session_by_file(str(path.resolve()), role="input")
            if not sessions:
                return _json(
                    {
                        "error": f"No session found for file: {session_or_path}",
                        "session_id": None,
                    }
                )
            session_id = sessions[0]
        else:
            session_id = session_or_path

        verification = run(session_id)

        return _json(
            {
                "session_id": verification.session_id,
                "script_path": verification.script_path,
                "status": verification.status.value,
                "is_verified": verification.is_verified,
                "combined_hash_expected": verification.combined_hash_expected,
                "files": [
                    {
                        "path": f.path,
                        "role": f.role,
                        "status": f.status.value,
                        "expected_hash": f.expected_hash,
                        "current_hash": f.current_hash,
                        "is_verified": f.is_verified,
                    }
                    for f in verification.files
                ],
                "mismatched_count": len(verification.mismatched_files),
                "missing_count": len(verification.missing_files),
            }
        )

    @mcp.tool()
    async def clew_chain(
        target_file: str,
    ) -> str:
        """Verify the dependency chain for a target file.

        Traces back through all sessions that contributed to producing
        the target file and verifies each one.

        Parameters
        ----------
        target_file : str
            Path to the target file to trace

        Returns
        -------
        str
            JSON with chain verification results
        """
        from pathlib import Path

        from scitex_clew import chain

        path = Path(target_file)
        if not path.exists():
            return _json(
                {
                    "error": f"File not found: {target_file}",
                    "target_file": target_file,
                }
            )

        result = chain(str(path.resolve()))

        return _json(
            {
                "target_file": result.target_file,
                "status": result.status.value,
                "is_verified": result.is_verified,
                "chain_length": len(result.runs),
                "failed_runs_count": len(result.failed_runs),
                "runs": [
                    {
                        "session_id": r.session_id,
                        "script_path": r.script_path,
                        "status": r.status.value,
                        "is_verified": r.is_verified,
                        "mismatched_files": [f.path for f in r.mismatched_files],
                        "missing_files": [f.path for f in r.missing_files],
                    }
                    for r in result.runs
                ],
            }
        )

    @mcp.tool()
    async def clew_status() -> str:
        """Git-status-like summary of the whole verification database — counts of verified, mismatched (files changed since the run), and missing (files deleted) sessions. Use when the user asks "what's changed?", "is my pipeline still reproducible?", or "show reproducibility status".

        Returns
        -------
        str
            JSON with counts of verified, mismatched, and missing runs
        """
        from scitex_clew import status

        return _json(status())

    @mcp.tool()
    async def clew_stats() -> str:
        """Return raw database statistics — total sessions, total files tracked, storage size, oldest/newest run. Use when the user asks how many runs/sessions/files are tracked, or wants database-level metrics.

        Returns
        -------
        str
            JSON with database statistics
        """
        from scitex_clew import stats

        return _json(stats())

    @mcp.tool()
    async def clew_mermaid(
        session_id: Optional[str] = None,
        target_file: Optional[str] = None,
        target_files: Optional[str] = None,
        claims: bool = False,
    ) -> str:
        """Generate Mermaid diagram for verification DAG.

        Parameters
        ----------
        session_id : str, optional
            Start from this session
        target_file : str, optional
            Start from session that produced this file
        target_files : str, optional
            Comma-separated list of target files (multi-target DAG)
        claims : bool, optional
            If True, build DAG from all registered claims

        Returns
        -------
        str
            Mermaid diagram code
        """
        from pathlib import Path

        from scitex_clew import mermaid

        if target_file:
            target_file = str(Path(target_file).resolve())

        multi_files = None
        if target_files:
            multi_files = [
                str(Path(f.strip()).resolve()) for f in target_files.split(",")
            ]

        mermaid_code = mermaid(
            session_id=session_id,
            target_file=target_file,
            target_files=multi_files,
            claims=claims,
        )

        return _json(
            {
                "mermaid": mermaid_code,
                "session_id": session_id,
                "target_file": target_file,
                "target_files": multi_files,
                "claims": claims,
            }
        )

    @mcp.tool()
    async def clew_dag(
        target_files: Optional[str] = None,
        claims: bool = False,
    ) -> str:
        """Verify full DAG for multiple targets or claims.

        Parameters
        ----------
        target_files : str, optional
            Comma-separated list of target file paths
        claims : bool, optional
            If True, build DAG from all registered claims

        Returns
        -------
        str
            JSON with DAG verification results
        """
        from pathlib import Path

        from scitex_clew import dag

        if claims:
            dag_result = dag(claims=True)
        elif target_files:
            targets = [str(Path(f.strip()).resolve()) for f in target_files.split(",")]
            dag_result = dag(targets)
        else:
            return _json({"error": "Specify target_files or claims=True"})

        return _format_dag_result(dag_result)

    @mcp.tool()
    async def clew_rerun_dag(
        target_files: Optional[str] = None,
        timeout: int = 300,
    ) -> str:
        """Re-execute entire DAG in topological order and compare outputs.

        Each session is re-executed in a sandbox — original outputs are
        never overwritten. This is the most thorough verification mode.

        Parameters
        ----------
        target_files : str, optional
            Comma-separated list of target file paths.
            If omitted, reruns the entire project DAG.
        timeout : int, optional
            Maximum execution time per session in seconds (default: 300).

        Returns
        -------
        str
            JSON with DAG rerun verification results.
        """
        from pathlib import Path

        from scitex_clew import rerun_dag

        targets = None
        if target_files:
            targets = [str(Path(f.strip()).resolve()) for f in target_files.split(",")]

        dag_result = rerun_dag(targets, timeout=timeout)
        return _format_dag_result(dag_result)

    @mcp.tool()
    async def clew_rerun_claims(
        file_path: Optional[str] = None,
        claim_type: Optional[str] = None,
        timeout: int = 300,
    ) -> str:
        """Re-execute all sessions backing manuscript claims.

        Traces each claim to its source session, builds the upstream DAG,
        and reruns every session in a sandbox.

        Parameters
        ----------
        file_path : str, optional
            Filter claims by manuscript file path.
        claim_type : str, optional
            Filter by claim type: statistic, figure, table, text, value.
        timeout : int, optional
            Maximum execution time per session in seconds (default: 300).

        Returns
        -------
        str
            JSON with DAG rerun verification results.
        """
        from scitex_clew import rerun_claims

        dag_result = rerun_claims(
            file_path=file_path, claim_type=claim_type, timeout=timeout
        )
        return _format_dag_result(dag_result)


# EOF
