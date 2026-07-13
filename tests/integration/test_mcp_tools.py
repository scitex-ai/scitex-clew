#!/usr/bin/env python3
# Timestamp: "2026-03-14 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-clew/tests/test__mcp_tools.py
"""Tests for scitex_clew._mcp.tools and _mcp.server modules.

Strategy
--------
- The MCP tool functions are registered as closures on a FastMCP instance
  via register_tools(mcp).  We extract them by name from mcp._tool_manager
  (the internal registry FastMCP uses) and invoke them with asyncio.run().
- Each test creates an isolated temp DB, injects it as the global singleton,
  and calls the tool function directly to validate JSON output structure.
- Error paths (file-not-found, session-not-found) are verified without a
  real server or subprocess.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import scitex_clew._db as _db_module
from scitex_clew._db import set_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run a coroutine synchronously."""
    return asyncio.run(coro)


def _parse(json_str: str) -> dict:
    """Parse the JSON string returned by every tool."""
    return json.loads(json_str)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Inject a fresh temp DB as the global singleton for every test."""
    db_path = tmp_path / "mcp_test.db"
    set_db(db_path)
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None


@pytest.fixture
def populated_db(isolated_db, tmp_path):
    """A DB with one completed run that has real files tracked."""
    db = isolated_db

    # Create two real files (input + output) so hash verification passes
    input_file = tmp_path / "input.csv"
    input_file.write_text("col_a,col_b\n1,2\n3,4\n")
    output_file = tmp_path / "output.csv"
    output_file.write_text("result\n42\n")

    from scitex_clew._hash import hash_file

    in_hash = hash_file(input_file)
    out_hash = hash_file(output_file)

    session_id = "2026Y-03M-14D-10h00m00s_Test"
    db.add_run(session_id, script_path="/path/to/analysis.py")
    db.add_file_hash(session_id, str(input_file.resolve()), in_hash, "input")
    db.add_file_hash(session_id, str(output_file.resolve()), out_hash, "output")
    db.finish_run(session_id, status="success", combined_hash="combined_hash_xyz")

    return {
        "db": db,
        "session_id": session_id,
        "input_file": input_file,
        "output_file": output_file,
        "in_hash": in_hash,
        "out_hash": out_hash,
    }


# ---------------------------------------------------------------------------
# Tool extraction helper
# ---------------------------------------------------------------------------


def _get_tools_dict(mcp):
    """Get the {name: tool} dict from a FastMCP instance (version-agnostic)."""
    from scitex_clew._mcp import get_tools_sync

    tools = get_tools_sync(mcp)
    if isinstance(tools, dict):
        return tools
    return {t.name: t for t in tools}


def _get_tool_fn(mcp, tool_name: str):
    """Extract the raw async function registered under tool_name."""
    tools = _get_tools_dict(mcp)
    tool = tools.get(tool_name)
    if tool is None:
        available = list(tools.keys())
        raise KeyError(f"Tool '{tool_name}' not found. Available: {available}")
    return tool.fn


# ---------------------------------------------------------------------------
# register_tools / register_all_tools
# ---------------------------------------------------------------------------


class TestRegisterTools:
    """register_tools() populates the FastMCP instance with expected tool names."""

    @pytest.fixture
    def mcp(self):
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        m = FastMCP(name="test-clew")
        register_tools(m)
        return m

    def test_clew_list_registered(self, mcp):
        # Arrange
        # Act
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_list_runs" in tools

    def test_clew_run_registered(self, mcp):
        # Arrange
        # Act
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_run" in tools

    def test_clew_chain_registered(self, mcp):
        # Arrange
        # Act
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_chain" in tools

    def test_clew_status_registered(self, mcp):
        # Arrange
        # Act
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_status" in tools

    def test_clew_stats_registered(self, mcp):
        # Arrange
        # Act
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_stats" in tools

    def test_clew_mermaid_registered(self, mcp):
        # Arrange
        # Act
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_mermaid" in tools

    def test_clew_dag_registered(self, mcp):
        # Arrange
        # Act
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_dag" in tools

    def test_clew_rerun_dag_registered(self, mcp):
        # Arrange
        # Act
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_rerun_dag" in tools

    def test_clew_rerun_claims_registered(self, mcp):
        # Arrange
        # Act
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_rerun_claims" in tools

    def test_nine_tools_total(self, mcp):
        """Exactly 9 tools should be registered."""
        # Arrange
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        assert len(tools) == 9


class TestRegisterAllTools:
    """register_all_tools() delegates to verification.register_tools."""

    def test_register_all_tools_populates_same_tools(self):
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools import register_all_tools

        m = FastMCP(name="test-all-tools")
        register_all_tools(m)
        tools = _get_tools_dict(m)
        # Act
        # Act
        expected = {
            "clew_list_runs",
            "clew_run",
            "clew_chain",
            "clew_status",
            "clew_stats",
            "clew_mermaid",
            "clew_dag",
            "clew_rerun_dag",
            "clew_rerun_claims",
            # §5 audit-mcp-tools — skills introspection
            "clew_skills_list",
            "clew_skills_get",
            # F1 — claim/hash/stamp wrappers
            "clew_add_claim",
            "clew_list_claims",
            "clew_verify_claim",
            "clew_register_intermediate",
            "clew_remove_claim",
            "clew_supersede_claim",
            "clew_export_manuscript_claims",
            "clew_is_claim_grounded",
            # citation gate wrappers
            "clew_add_citation",
            "clew_list_citations",
            "clew_verify_citations",
            "clew_verify_all_citations",
            "clew_hash_file",
            "clew_hash_directory",
            "clew_stamp",
            "clew_list_stamps",
            "clew_check_stamp",
        }
        # Assert
        # Assert
        assert set(tools.keys()) == expected

    def test_register_all_tools_callable_import(self):
        """register_all_tools is importable from the tools package."""
        # Arrange
        # Act
        from scitex_clew._mcp.tools import register_all_tools

        # Assert
        assert callable(register_all_tools)


# ---------------------------------------------------------------------------
# MCP server module
# ---------------------------------------------------------------------------


class TestMCPServer:
    """The server module exposes a pre-configured FastMCP instance."""

    def test_mcp_object_exists(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._mcp.server import mcp

        # Assert
        # Assert
        assert mcp is not None

    def test_mcp_name_mcp_name_equals_scitex_clew(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._mcp.server import mcp

        # Assert
        # Assert
        assert mcp.name == "scitex-clew"

    def test_mcp_has_tools(self):
        # Arrange
        # Arrange
        from scitex_clew._mcp.server import mcp

        # Act
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert len(tools) > 0

    def test_mcp_has_clew_status(self):
        # Arrange
        # Arrange
        from scitex_clew._mcp.server import mcp

        # Act
        # Act
        tools = _get_tools_dict(mcp)
        # Assert
        # Assert
        assert "clew_status" in tools

    def test_mcp_instructions_not_empty_instructions_is_not_none(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._mcp.server import mcp

        # FastMCP stores instructions at mcp.instructions or similar
        # Presence of the attribute is sufficient
        # Act
        # Act
        instructions = getattr(mcp, "instructions", None) or getattr(
            mcp, "_instructions", None
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert instructions is not None

    def test_mcp_instructions_not_empty_len_instructions_0(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._mcp.server import mcp

        # FastMCP stores instructions at mcp.instructions or similar
        # Presence of the attribute is sufficient
        # Act
        # Act
        instructions = getattr(mcp, "instructions", None) or getattr(
            mcp, "_instructions", None
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert len(instructions) > 0


# ---------------------------------------------------------------------------
# _json helper
# ---------------------------------------------------------------------------


class TestJsonHelper:
    """_json() is an internal helper — verify it via the output of each tool."""

    def test_json_output_is_valid_json(self, populated_db):
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_stats")
        result = _run(fn())
        # Must be valid JSON
        # Act
        # Act
        parsed = json.loads(result)
        # Assert
        # Assert
        assert isinstance(parsed, dict)

    def test_json_output_is_indented(self, populated_db):
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_stats")
        # Act
        # Act
        result = _run(fn())
        # indent=2 means the output contains newlines and spaces
        # Assert
        # Assert
        assert "\n" in result


# ---------------------------------------------------------------------------
# clew_status tool
# ---------------------------------------------------------------------------


class TestClewStatusTool:
    @pytest.fixture
    def tool_fn(self, populated_db):
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        return _get_tool_fn(mcp, "clew_status")

    def test_returns_string_result_is_str(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _run(tool_fn())
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_returns_valid_json(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert isinstance(result, dict)

    def test_has_verified_count(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert "verified_count" in result

    def test_has_mismatch_count(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert "mismatch_count" in result

    def test_has_missing_count(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert "missing_count" in result

    def test_counts_are_integers_isinstance_result_verified_count_int(self, tool_fn):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result["verified_count"], int)

    def test_counts_are_integers_isinstance_result_mismatch_count_int(self, tool_fn):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result["mismatch_count"], int)

    def test_counts_are_integers_isinstance_result_missing_count_int(self, tool_fn):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result["missing_count"], int)

    def test_empty_db_all_zeros_result_verified_count_0(self, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_status")
        # Act
        # Act
        result = _parse(_run(fn()))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["verified_count"] == 0

    def test_empty_db_all_zeros_result_mismatch_count_0(self, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_status")
        # Act
        # Act
        result = _parse(_run(fn()))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["mismatch_count"] == 0

    def test_empty_db_all_zeros_result_missing_count_0(self, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_status")
        # Act
        # Act
        result = _parse(_run(fn()))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["missing_count"] == 0


# ---------------------------------------------------------------------------
# clew_stats tool
# ---------------------------------------------------------------------------


class TestClewStatsTool:
    @pytest.fixture
    def tool_fn(self, populated_db):
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        return _get_tool_fn(mcp, "clew_stats")

    def test_returns_string_result_is_str(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _run(tool_fn())
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_returns_valid_json(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert isinstance(result, dict)

    def test_has_total_runs(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert "total_runs" in result

    def test_total_runs_is_one(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert result["total_runs"] == 1

    def test_has_success_runs(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert "success_runs" in result

    def test_has_db_path(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert "db_path" in result

    def test_empty_db_total_runs_zero(self, isolated_db):
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_stats")
        # Act
        # Act
        result = _parse(_run(fn()))
        # Assert
        # Assert
        assert result["total_runs"] == 0


# ---------------------------------------------------------------------------
# clew_list tool
# ---------------------------------------------------------------------------


class TestClewListTool:
    @pytest.fixture
    def tool_fn(self, populated_db):
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        return _get_tool_fn(mcp, "clew_list_runs")

    def test_returns_string_result_is_str(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _run(tool_fn())
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_returns_valid_json(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert isinstance(result, dict)

    def test_has_count_key(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert "count" in result

    def test_has_runs_key(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert "runs" in result

    def test_runs_is_list(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert isinstance(result["runs"], list)

    def test_count_equals_one(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert result["count"] == 1

    def test_run_has_session_id_session_id_in_run(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        # Arrange
        result = _parse(_run(tool_fn()))
        # Act
        # Act
        run = result["runs"][0]
        # Act
        # Assert
        # Assert
        # Assert
        assert "session_id" in run

    def test_run_has_session_id_run_session_id_populated_db_session_id(
        self, tool_fn, populated_db
    ):
        # Arrange
        # Arrange
        # Arrange
        result = _parse(_run(tool_fn()))
        # Act
        # Act
        run = result["runs"][0]
        # Act
        # Assert
        # Assert
        # Assert
        assert run["session_id"] == populated_db["session_id"]

    def test_run_has_verification_status(self, tool_fn):
        # Arrange
        # Arrange
        result = _parse(_run(tool_fn()))
        # Act
        # Act
        run = result["runs"][0]
        # Assert
        # Assert
        assert "verification_status" in run

    def test_run_has_is_verified(self, tool_fn):
        # Arrange
        # Arrange
        result = _parse(_run(tool_fn()))
        # Act
        # Act
        run = result["runs"][0]
        # Assert
        # Assert
        assert "is_verified" in run

    def test_run_has_script_path(self, tool_fn):
        # Arrange
        # Arrange
        result = _parse(_run(tool_fn()))
        # Act
        # Act
        run = result["runs"][0]
        # Assert
        # Assert
        assert "script_path" in run

    def test_run_has_db_status(self, tool_fn):
        # Arrange
        # Arrange
        result = _parse(_run(tool_fn()))
        # Act
        # Act
        run = result["runs"][0]
        # Assert
        # Assert
        assert "db_status" in run

    def test_limit_parameter_result_count_2(self, isolated_db):
        """limit parameter restricts number of returned runs."""
        # Arrange
        db = isolated_db
        for i in range(5):
            db.add_run(f"sess_{i:03d}", f"/script_{i}.py")
            db.finish_run(f"sess_{i:03d}", status="success")

        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_list_runs")
        # Act
        result = _parse(_run(fn(limit=2)))
        # Assert
        assert result["count"] == 2

    def test_status_filter_success_result_count_1(self, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        db = isolated_db
        db.add_run("sess_ok", "/script.py")
        db.finish_run("sess_ok", status="success")
        db.add_run("sess_fail", "/script.py")
        db.finish_run("sess_fail", status="failed")
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_list_runs")
        # Act
        # Act
        result = _parse(_run(fn(status_filter="success")))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["count"] == 1

    def test_status_filter_success_result_runs_0_db_status_success(self, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        db = isolated_db
        db.add_run("sess_ok", "/script.py")
        db.finish_run("sess_ok", status="success")
        db.add_run("sess_fail", "/script.py")
        db.finish_run("sess_fail", status="failed")
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_list_runs")
        # Act
        # Act
        result = _parse(_run(fn(status_filter="success")))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["runs"][0]["db_status"] == "success"

    def test_empty_db_count_zero_result_count_0(self, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_list_runs")
        # Act
        # Act
        result = _parse(_run(fn()))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["count"] == 0

    def test_empty_db_count_zero_result_runs(self, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_list_runs")
        # Act
        # Act
        result = _parse(_run(fn()))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["runs"] == []


# ---------------------------------------------------------------------------
# clew_run tool
# ---------------------------------------------------------------------------


class TestClewRunTool:
    @pytest.fixture
    def tool_fn(self, populated_db):
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        return _get_tool_fn(mcp, "clew_run")

    def test_returns_string_result_is_str(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _run(tool_fn(session_or_path=populated_db["session_id"]))
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_returns_valid_json(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert isinstance(result, dict)

    def test_has_session_id(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert result["session_id"] == populated_db["session_id"]

    def test_has_status_status_in_result(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert "status" in result

    def test_has_is_verified(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert "is_verified" in result

    def test_has_files_key(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert "files" in result

    def test_files_is_list(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert isinstance(result["files"], list)

    def test_file_entry_has_path(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert all("path" in f for f in result["files"])

    def test_file_entry_has_role(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert all("role" in f for f in result["files"])

    def test_file_entry_has_status(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert all("status" in f for f in result["files"])

    def test_file_entry_has_is_verified(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert all("is_verified" in f for f in result["files"])

    def test_has_mismatched_count(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert "mismatched_count" in result

    def test_has_missing_count(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert "missing_count" in result

    def test_verified_run_has_no_mismatches_result_mismatched_count_0(
        self, tool_fn, populated_db
    ):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["mismatched_count"] == 0

    def test_verified_run_has_no_mismatches_result_missing_count_0(
        self, tool_fn, populated_db
    ):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["missing_count"] == 0

    def test_nonexistent_session_returns_unknown_status(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path="no_such_session_xyz")))
        # Assert
        # Assert
        assert result["status"] == "unknown"

    def test_nonexistent_file_path_returns_error_status_in_result(
        self, tool_fn, tmp_path
    ):
        # Arrange
        # Arrange
        # Arrange
        nonexistent = str(tmp_path / "does_not_exist.csv")
        # Act
        # Act
        result = _parse(_run(tool_fn(session_or_path=nonexistent)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "status" in result

    def test_nonexistent_file_path_returns_error_result_status_unknown(
        self, tool_fn, tmp_path
    ):
        # Arrange
        # Arrange
        # Arrange
        nonexistent = str(tmp_path / "does_not_exist.csv")
        # Act
        # Act
        result = _parse(_run(tool_fn(session_or_path=nonexistent)))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["status"] == "unknown"

    def test_file_path_resolves_to_session(self, tool_fn, populated_db):
        """Passing a real file path that is an output finds the session."""
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        result = _parse(_run(tool_fn(session_or_path=output_path)))
        # Assert
        assert result["session_id"] == populated_db["session_id"]

    def test_file_path_not_in_db_returns_error(self, tool_fn, tmp_path):
        """An existing file not tracked by any session returns an error dict."""
        # Arrange
        unknown_file = tmp_path / "unknown.txt"
        unknown_file.write_text("not tracked")
        # Act
        result = _parse(_run(tool_fn(session_or_path=str(unknown_file))))
        # Assert
        assert "error" in result

    def test_has_script_path(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_or_path=populated_db["session_id"])))
        # Assert
        # Assert
        assert "script_path" in result


# ---------------------------------------------------------------------------
# clew_chain tool
# ---------------------------------------------------------------------------


class TestClewChainTool:
    @pytest.fixture
    def tool_fn(self, populated_db):
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        return _get_tool_fn(mcp, "clew_chain")

    def test_nonexistent_file_returns_error(self, tool_fn, tmp_path):
        # Arrange
        # Arrange
        nonexistent = str(tmp_path / "does_not_exist.csv")
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=nonexistent)))
        # Assert
        # Assert
        assert "error" in result

    def test_nonexistent_file_error_has_target_file_target_file_in_result(
        self, tool_fn, tmp_path
    ):
        # Arrange
        # Arrange
        # Arrange
        target = str(tmp_path / "missing.csv")
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=target)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "target_file" in result

    def test_nonexistent_file_error_has_target_file_result_target_file_target(
        self, tool_fn, tmp_path
    ):
        # Arrange
        # Arrange
        # Arrange
        target = str(tmp_path / "missing.csv")
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=target)))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["target_file"] == target

    def test_existing_untracked_file_returns_unknown_status_status_in_result(
        self, tool_fn, tmp_path
    ):
        # Arrange
        # Arrange
        # Arrange
        untracked = tmp_path / "untracked.txt"
        untracked.write_text("data")
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=str(untracked))))
        # Act
        # Assert
        # Assert
        # Assert
        assert "status" in result

    def test_existing_untracked_file_returns_unknown_status_result_status_unknown(
        self, tool_fn, tmp_path
    ):
        # Arrange
        # Arrange
        # Arrange
        untracked = tmp_path / "untracked.txt"
        untracked.write_text("data")
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=str(untracked))))
        # Act
        # Assert
        # Assert
        # Assert
        assert result["status"] == "unknown"

    def test_tracked_output_returns_chain_target_file_in_result(
        self, tool_fn, populated_db
    ):
        # Arrange
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "target_file" in result

    def test_tracked_output_returns_chain_status_in_result(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "status" in result

    def test_tracked_output_returns_chain_is_verified_in_result(
        self, tool_fn, populated_db
    ):
        # Arrange
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "is_verified" in result

    def test_tracked_output_returns_chain_runs_in_result(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "runs" in result

    def test_tracked_output_returns_chain_chain_length_in_result(
        self, tool_fn, populated_db
    ):
        # Arrange
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "chain_length" in result

    def test_tracked_output_chain_length_gte_one(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Assert
        # Assert
        assert result["chain_length"] >= 1

    def test_tracked_output_has_failed_runs_count(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Assert
        # Assert
        assert "failed_runs_count" in result

    def test_run_entries_have_session_id(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Assert
        # Assert
        assert all("session_id" in r for r in result["runs"])

    def test_run_entries_have_is_verified(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Assert
        # Assert
        assert all("is_verified" in r for r in result["runs"])


# ---------------------------------------------------------------------------
# clew_mermaid tool
# ---------------------------------------------------------------------------


class TestClewMermaidTool:
    @pytest.fixture
    def tool_fn(self, populated_db):
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        return _get_tool_fn(mcp, "clew_mermaid")

    def test_returns_string_result_is_str(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _run(tool_fn(session_id=populated_db["session_id"]))
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_returns_valid_json(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_id=populated_db["session_id"])))
        # Assert
        # Assert
        assert isinstance(result, dict)

    def test_has_mermaid_key(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_id=populated_db["session_id"])))
        # Assert
        # Assert
        assert "mermaid" in result

    def test_has_session_id_key(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(session_id=populated_db["session_id"])))
        # Assert
        # Assert
        assert "session_id" in result

    def test_session_id_reflected(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        sid = populated_db["session_id"]
        # Act
        # Act
        result = _parse(_run(tool_fn(session_id=sid)))
        # Assert
        # Assert
        assert result["session_id"] == sid

    def test_target_file_param_resolves_mermaid_in_result(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"])
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "mermaid" in result

    def test_target_file_param_resolves_target_file_in_result(
        self, tool_fn, populated_db
    ):
        # Arrange
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"])
        # Act
        # Act
        result = _parse(_run(tool_fn(target_file=output_path)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "target_file" in result

    def test_multiple_target_files_param(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"])
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=output_path)))
        # Assert
        # Assert
        assert "target_files" in result

    def test_claims_flag_included_in_response(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(claims=False)))
        # Assert
        # Assert
        assert "claims" in result

    def test_claims_false_reflected(self, tool_fn, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn(claims=False)))
        # Assert
        # Assert
        assert result["claims"] is False


# ---------------------------------------------------------------------------
# clew_dag tool
# ---------------------------------------------------------------------------


class TestClewDagTool:
    @pytest.fixture
    def tool_fn(self, populated_db):
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        return _get_tool_fn(mcp, "clew_dag")

    def test_no_args_returns_error(self, tool_fn):
        """Calling clew_dag with no arguments returns an error dict."""
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        assert "error" in result

    def test_error_message_mentions_specify(self, tool_fn):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _parse(_run(tool_fn()))
        # Assert
        # Assert
        assert "Specify" in result["error"] or "specify" in result["error"]

    def test_target_files_returns_dag_result_status_in_result(
        self, tool_fn, populated_db
    ):
        # Arrange
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=output_path)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "status" in result

    def test_target_files_returns_dag_result_is_verified_in_result(
        self, tool_fn, populated_db
    ):
        # Arrange
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=output_path)))
        # Act
        # Assert
        # Assert
        # Assert
        assert "is_verified" in result

    def test_dag_result_has_target_files(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=output_path)))
        # Assert
        # Assert
        assert "target_files" in result

    def test_dag_result_has_runs(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=output_path)))
        # Assert
        # Assert
        assert "runs" in result

    def test_dag_result_has_edges(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=output_path)))
        # Assert
        # Assert
        assert "edges" in result

    def test_dag_result_has_topological_order(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=output_path)))
        # Assert
        # Assert
        assert "topological_order" in result

    def test_dag_result_has_num_runs(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=output_path)))
        # Assert
        # Assert
        assert "num_runs" in result

    def test_dag_result_has_num_edges(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=output_path)))
        # Assert
        # Assert
        assert "num_edges" in result

    def test_multiple_target_files_comma_separated(self, tool_fn, populated_db):
        # Arrange
        # Arrange
        output_path = str(populated_db["output_file"].resolve())
        # Pass the same file twice — still valid
        # Act
        # Act
        result = _parse(_run(tool_fn(target_files=f"{output_path},{output_path}")))
        # Assert
        # Assert
        assert "target_files" in result


# ---------------------------------------------------------------------------
# _format_dag_result helper (tested via clew_dag output)
# ---------------------------------------------------------------------------


class TestFormatDagResult:
    """_format_dag_result is internal but exercised through clew_dag and clew_rerun_dag."""

    def test_runs_list_contains_session_id(self, populated_db):
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_dag")
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(fn(target_files=output_path)))
        # Assert
        # Assert
        assert all("session_id" in r for r in result.get("runs", []))

    def test_runs_list_contains_is_verified(self, populated_db):
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_dag")
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(fn(target_files=output_path)))
        # Assert
        # Assert
        assert all("is_verified" in r for r in result.get("runs", []))

    def test_runs_list_contains_script_path(self, populated_db):
        # Arrange
        # Arrange
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools

        mcp = FastMCP(name="t")
        register_tools(mcp)
        fn = _get_tool_fn(mcp, "clew_dag")
        output_path = str(populated_db["output_file"].resolve())
        # Act
        # Act
        result = _parse(_run(fn(target_files=output_path)))
        # Assert
        # Assert
        assert all("script_path" in r for r in result.get("runs", []))


# ---------------------------------------------------------------------------
# Verification module __all__ (tools/__init__.py)
# ---------------------------------------------------------------------------


class TestMCPToolsInit:
    def test_all_exports_register_all_tools(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._mcp.tools import __all__

        # Assert
        # Assert
        assert "register_all_tools" in __all__

    def test_all_has_one_export(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._mcp.tools import __all__

        # Assert
        # Assert
        assert len(__all__) == 1


# EOF
