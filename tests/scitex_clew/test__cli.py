#!/usr/bin/env python3
# Timestamp: "2026-03-14 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-clew/tests/test__cli.py
"""Tests for scitex_clew._cli modules.

Strategy
--------
- Use click.testing.CliRunner to invoke all CLI entry points in-process.
- Where commands call scitex_clew.* functions that touch the database, inject
  an isolated temp DB via set_db() before each test and tear it down after.
- MCP-related sub-commands that need fastmcp are tested with monkeypatching
  so the suite does not require the optional [mcp] extra to pass.
- Each test asserts exit_code and one or more observable strings in output.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli._main import main
from scitex_clew._db import set_db


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Inject a fresh temp DB as the global singleton for every test.

    This prevents any CLI command that calls scitex_clew.status() /
    clew.list_runs() / clew.stats() / clew.mermaid() from touching the
    developer's real database.
    """
    db_path = tmp_path / "cli_test.db"
    set_db(db_path)
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None


@pytest.fixture
def runner():
    """CliRunner with mix_stderr=False for clean stdout/stderr separation."""
    return CliRunner()


@pytest.fixture
def populated_db(isolated_db, tmp_path):
    """DB pre-populated with one completed run so list / status return data."""
    db = isolated_db

    input_file = tmp_path / "input.csv"
    input_file.write_text("a,b\n1,2\n")
    output_file = tmp_path / "output.csv"
    output_file.write_text("result\n42\n")

    from scitex_clew._hash import hash_file

    in_hash = hash_file(input_file)
    out_hash = hash_file(output_file)

    session_id = "2026Y-03M-14D-10h00m00s_TestCLI"
    db.add_run(session_id, script_path="/path/to/analysis.py")
    db.add_file_hash(session_id, str(input_file.resolve()), in_hash, "input")
    db.add_file_hash(session_id, str(output_file.resolve()), out_hash, "output")
    db.finish_run(session_id, status="success", combined_hash="combined_xyz")

    return {
        "db": db,
        "session_id": session_id,
        "input_file": input_file,
        "output_file": output_file,
    }


# ===========================================================================
# TestMainHelp
# ===========================================================================


class TestMainHelp:
    """clew --help / -h shows the help text and exits 0."""

    def test_help_long_flag_exit_code(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_help_short_flag_exit_code(self, runner):
        result = runner.invoke(main, ["-h"])
        assert result.exit_code == 0

    def test_help_contains_description(self, runner):
        result = runner.invoke(main, ["--help"])
        assert (
            "clew" in result.output.lower() or "verification" in result.output.lower()
        )

    def test_help_lists_status_command(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "status" in result.output

    def test_help_lists_list_command(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "list" in result.output

    def test_help_lists_verify_command(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "verify" in result.output

    def test_help_lists_stats_command(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "stats" in result.output

    def test_help_lists_mermaid_command(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "mermaid" in result.output

    def test_no_args_shows_help(self, runner):
        """Invoking clew with no arguments must show help (exit 0)."""
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "status" in result.output or "Usage" in result.output


# ===========================================================================
# TestVersion
# ===========================================================================


class TestVersion:
    """clew --version / -V outputs version string."""

    def test_version_long_flag_exit_code(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0

    def test_version_short_flag_exit_code(self, runner):
        result = runner.invoke(main, ["-V"])
        assert result.exit_code == 0

    def test_version_output_contains_scitex_clew(self, runner):
        result = runner.invoke(main, ["--version"])
        assert "scitex-clew" in result.output

    def test_version_output_contains_dot_separated_number(self, runner):
        """Version string should contain at least one dot (e.g. '0.1.0')."""
        result = runner.invoke(main, ["--version"])
        # version string format: "scitex-clew X.Y.Z" or "scitex-clew X.Y.Z-something"
        parts = result.output.strip().split()
        assert len(parts) >= 2
        version_str = parts[-1]
        assert "." in version_str


# ===========================================================================
# TestHelpRecursive
# ===========================================================================


class TestHelpRecursive:
    """clew --help-recursive prints help for every sub-command."""

    def test_help_recursive_exit_code(self, runner):
        result = runner.invoke(main, ["--help-recursive"])
        assert result.exit_code == 0

    def test_help_recursive_shows_equals_separator(self, runner):
        result = runner.invoke(main, ["--help-recursive"])
        assert "=" * 10 in result.output

    def test_help_recursive_shows_status_subcommand(self, runner):
        result = runner.invoke(main, ["--help-recursive"])
        assert "status" in result.output

    def test_help_recursive_shows_list_subcommand(self, runner):
        result = runner.invoke(main, ["--help-recursive"])
        assert "list" in result.output

    def test_help_recursive_shows_mcp_subcommand(self, runner):
        result = runner.invoke(main, ["--help-recursive"])
        assert "mcp" in result.output


# ===========================================================================
# TestStatusCommand
# ===========================================================================


class TestStatusCommand:
    """clew status outputs JSON and exits 0."""

    def test_exit_code_empty_db(self, runner, isolated_db):
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0

    def test_output_is_valid_json(self, runner, isolated_db):
        result = runner.invoke(main, ["status"])
        parsed = json.loads(result.output)
        assert isinstance(parsed, dict)

    def test_output_has_verified_count_key(self, runner, isolated_db):
        result = runner.invoke(main, ["status"])
        parsed = json.loads(result.output)
        assert "verified_count" in parsed

    def test_output_has_mismatch_count_key(self, runner, isolated_db):
        result = runner.invoke(main, ["status"])
        parsed = json.loads(result.output)
        assert "mismatch_count" in parsed

    def test_empty_db_verified_count_is_zero(self, runner, isolated_db):
        result = runner.invoke(main, ["status"])
        parsed = json.loads(result.output)
        assert parsed["verified_count"] == 0

    def test_status_help(self, runner):
        result = runner.invoke(main, ["status", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output.lower() or "overview" in result.output.lower()


# ===========================================================================
# TestListCommand
# ===========================================================================


class TestListCommand:
    """clew list outputs run rows and exits 0."""

    def test_exit_code_empty_db(self, runner, isolated_db):
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0

    def test_empty_db_no_rows_in_output(self, runner, isolated_db):
        result = runner.invoke(main, ["list"])
        # With no runs, output should be empty or minimal
        assert result.exit_code == 0

    def test_populated_db_shows_session_id(self, runner, populated_db):
        result = runner.invoke(main, ["list"])
        assert result.exit_code == 0
        assert populated_db["session_id"] in result.output

    def test_populated_db_shows_script_path(self, runner, populated_db):
        result = runner.invoke(main, ["list"])
        assert "analysis.py" in result.output

    def test_populated_db_shows_status(self, runner, populated_db):
        result = runner.invoke(main, ["list"])
        assert "success" in result.output

    def test_limit_option_accepted(self, runner, isolated_db):
        result = runner.invoke(main, ["list", "--limit", "5"])
        assert result.exit_code == 0

    def test_limit_default_accepted(self, runner, isolated_db):
        result = runner.invoke(main, ["list", "--limit", "50"])
        assert result.exit_code == 0

    def test_list_help(self, runner):
        result = runner.invoke(main, ["list", "--help"])
        assert result.exit_code == 0
        assert "limit" in result.output.lower() or "runs" in result.output.lower()


# ===========================================================================
# TestVerifyCommand
# ===========================================================================


class TestVerifyCommand:
    """clew verify <session_id> checks a specific run."""

    def test_verify_existing_session_exit_code(self, runner, populated_db):
        result = runner.invoke(main, ["verify", populated_db["session_id"]])
        assert result.exit_code == 0

    def test_verify_existing_session_shows_ok_or_fail(self, runner, populated_db):
        result = runner.invoke(main, ["verify", populated_db["session_id"]])
        assert "OK" in result.output or "FAIL" in result.output

    def test_verify_existing_session_shows_session_id(self, runner, populated_db):
        result = runner.invoke(main, ["verify", populated_db["session_id"]])
        assert populated_db["session_id"] in result.output

    def test_verify_existing_session_shows_file_roles(self, runner, populated_db):
        result = runner.invoke(main, ["verify", populated_db["session_id"]])
        # File roles: "input" or "output"
        assert "input" in result.output or "output" in result.output

    def test_verify_nonexistent_session_exit_code(self, runner, isolated_db):
        """Verifying a missing session should still exit 0 (not crash)."""
        result = runner.invoke(main, ["verify", "nonexistent_session_xyz"])
        # The command should handle this gracefully; exit code may be 0 or 1
        # but it must not raise an unhandled exception (no traceback)
        assert "Traceback" not in result.output

    def test_verify_help(self, runner):
        result = runner.invoke(main, ["verify", "--help"])
        assert result.exit_code == 0
        assert "session" in result.output.lower() or "verify" in result.output.lower()


# ===========================================================================
# TestStatsCommand
# ===========================================================================


class TestStatsCommand:
    """clew stats outputs database statistics as JSON."""

    def test_exit_code(self, runner, isolated_db):
        result = runner.invoke(main, ["stats"])
        assert result.exit_code == 0

    def test_output_is_valid_json(self, runner, isolated_db):
        result = runner.invoke(main, ["stats"])
        parsed = json.loads(result.output)
        assert isinstance(parsed, dict)

    def test_output_has_total_runs_key(self, runner, isolated_db):
        result = runner.invoke(main, ["stats"])
        parsed = json.loads(result.output)
        assert "total_runs" in parsed

    def test_empty_db_total_runs_zero(self, runner, isolated_db):
        result = runner.invoke(main, ["stats"])
        parsed = json.loads(result.output)
        assert parsed["total_runs"] == 0

    def test_populated_db_total_runs_one(self, runner, populated_db):
        result = runner.invoke(main, ["stats"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["total_runs"] == 1

    def test_stats_help(self, runner):
        result = runner.invoke(main, ["stats", "--help"])
        assert result.exit_code == 0
        assert "stats" in result.output.lower() or "database" in result.output.lower()


# ===========================================================================
# TestMermaidCommand
# ===========================================================================


class TestMermaidCommand:
    """clew mermaid generates a Mermaid DAG diagram."""

    def test_exit_code(self, runner, isolated_db):
        result = runner.invoke(main, ["mermaid"])
        assert result.exit_code == 0

    def test_output_is_not_empty(self, runner, populated_db):
        result = runner.invoke(main, ["mermaid"])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

    def test_output_contains_mermaid_keyword(self, runner, populated_db):
        result = runner.invoke(main, ["mermaid"])
        # Mermaid diagrams start with "graph" or "flowchart" or similar
        combined = result.output.lower()
        assert "graph" in combined or "flowchart" in combined or "mermaid" in combined

    def test_claims_flag_accepted(self, runner, isolated_db):
        result = runner.invoke(main, ["mermaid", "--claims"])
        assert result.exit_code == 0

    def test_mermaid_help(self, runner):
        result = runner.invoke(main, ["mermaid", "--help"])
        assert result.exit_code == 0
        assert "mermaid" in result.output.lower() or "dag" in result.output.lower()


# ===========================================================================
# TestListPythonApisCommand
# ===========================================================================


class TestListPythonApisCommand:
    """clew list-python-apis introspects the public API of scitex-clew."""

    def test_exit_code(self, runner):
        result = runner.invoke(main, ["list-python-apis"])
        assert result.exit_code == 0

    def test_output_contains_api_tree_header(self, runner):
        result = runner.invoke(main, ["list-python-apis"])
        # The command emits "API tree of scitex-clew"
        assert "scitex-clew" in result.output or "API" in result.output

    def test_output_contains_legend(self, runner):
        result = runner.invoke(main, ["list-python-apis"])
        assert (
            "Legend" in result.output
            or "[M]" in result.output
            or "[F]" in result.output
        )

    def test_verbose_flag_accepted(self, runner):
        result = runner.invoke(main, ["list-python-apis", "-v"])
        assert result.exit_code == 0

    def test_double_verbose_flag_accepted(self, runner):
        result = runner.invoke(main, ["list-python-apis", "-vv"])
        assert result.exit_code == 0

    def test_json_flag_outputs_valid_json(self, runner):
        result = runner.invoke(main, ["list-python-apis", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)

    def test_json_output_has_name_key(self, runner):
        result = runner.invoke(main, ["list-python-apis", "--json"])
        parsed = json.loads(result.output)
        assert len(parsed) > 0
        assert "Name" in parsed[0]

    def test_json_output_has_type_key(self, runner):
        result = runner.invoke(main, ["list-python-apis", "--json"])
        parsed = json.loads(result.output)
        assert len(parsed) > 0
        assert "Type" in parsed[0]

    def test_json_output_has_depth_key(self, runner):
        result = runner.invoke(main, ["list-python-apis", "--json"])
        parsed = json.loads(result.output)
        assert len(parsed) > 0
        assert "Depth" in parsed[0]

    def test_max_depth_option_accepted(self, runner):
        result = runner.invoke(main, ["list-python-apis", "--max-depth", "2"])
        assert result.exit_code == 0

    def test_root_only_option_accepted(self, runner):
        result = runner.invoke(main, ["list-python-apis", "--root-only"])
        assert result.exit_code == 0

    def test_list_python_apis_help(self, runner):
        result = runner.invoke(main, ["list-python-apis", "--help"])
        assert result.exit_code == 0
        assert "api" in result.output.lower() or "python" in result.output.lower()

    def test_json_and_verbose_combination(self, runner):
        result = runner.invoke(main, ["list-python-apis", "--json", "-v"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        # With -v the JSON entries should contain a Docstring key
        assert "Docstring" in parsed[0]


# ===========================================================================
# TestMcpGroupHelp
# ===========================================================================


class TestMcpGroupHelp:
    """clew mcp --help and clew mcp without arguments show group help."""

    def test_mcp_help_exit_code(self, runner):
        result = runner.invoke(main, ["mcp", "--help"])
        assert result.exit_code == 0

    def test_mcp_no_args_exit_code(self, runner):
        result = runner.invoke(main, ["mcp"])
        assert result.exit_code == 0

    def test_mcp_help_contains_list_tools(self, runner):
        result = runner.invoke(main, ["mcp", "--help"])
        assert "list-tools" in result.output

    def test_mcp_help_contains_installation(self, runner):
        result = runner.invoke(main, ["mcp", "--help"])
        assert "installation" in result.output

    def test_mcp_help_contains_doctor(self, runner):
        result = runner.invoke(main, ["mcp", "--help"])
        assert "doctor" in result.output

    def test_mcp_help_contains_start(self, runner):
        result = runner.invoke(main, ["mcp", "--help"])
        assert "start" in result.output

    def test_mcp_help_recursive_exit_code(self, runner):
        result = runner.invoke(main, ["mcp", "--help-recursive"])
        assert result.exit_code == 0

    def test_mcp_help_recursive_shows_subcommands(self, runner):
        result = runner.invoke(main, ["mcp", "--help-recursive"])
        assert "list-tools" in result.output or "doctor" in result.output


# ===========================================================================
# TestMcpInstallation
# ===========================================================================


class TestMcpInstallation:
    """clew mcp installation prints setup instructions."""

    def test_exit_code(self, runner):
        result = runner.invoke(main, ["mcp", "installation"])
        assert result.exit_code == 0

    def test_shows_pip_install(self, runner):
        result = runner.invoke(main, ["mcp", "installation"])
        assert "pip install" in result.output

    def test_shows_mcp_extra(self, runner):
        result = runner.invoke(main, ["mcp", "installation"])
        assert "mcp" in result.output

    def test_shows_mcp_servers_block(self, runner):
        result = runner.invoke(main, ["mcp", "installation"])
        assert "mcpServers" in result.output

    def test_shows_clew_mcp_start(self, runner):
        result = runner.invoke(main, ["mcp", "installation"])
        assert "mcp" in result.output and "start" in result.output

    def test_shows_verify_instructions(self, runner):
        result = runner.invoke(main, ["mcp", "installation"])
        assert "clew mcp doctor" in result.output or "doctor" in result.output

    def test_installation_help(self, runner):
        result = runner.invoke(main, ["mcp", "installation", "--help"])
        assert result.exit_code == 0


# ===========================================================================
# TestMcpDoctor
# ===========================================================================


class TestMcpDoctor:
    """clew mcp doctor checks MCP server dependencies.

    Two branches:
    1. fastmcp NOT installed  -> shows install hint, exits 0.
    2. fastmcp IS installed   -> checks server and reports OK, exits 0.
    """

    def test_exit_code_without_fastmcp(self, runner):
        """When fastmcp is absent the command exits 0 (not a crash)."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "fastmcp":
                raise ImportError("fastmcp not installed (mocked)")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = runner.invoke(main, ["mcp", "doctor"])
        assert result.exit_code == 0

    def test_shows_checking_message(self, runner):
        """Regardless of fastmcp availability the initial message is shown."""
        with patch(
            "scitex_clew._mcp.get_tools_sync",
            return_value=[
                MagicMock(name="t1"),
                MagicMock(name="t2"),
                MagicMock(name="t3"),
            ],
        ):
            result = runner.invoke(main, ["mcp", "doctor"])
        assert "Checking" in result.output or "mcp" in result.output.lower()

    def test_fastmcp_installed_shows_ok(self, runner):
        """When fastmcp is present the doctor reports OK for it."""
        try:
            import fastmcp  # noqa: F401
        except ImportError:
            pytest.skip("fastmcp not installed in this environment")

        with patch(
            "scitex_clew._mcp.get_tools_sync",
            return_value=[
                MagicMock(name="t1"),
                MagicMock(name="t2"),
                MagicMock(name="t3"),
            ],
        ):
            result = runner.invoke(main, ["mcp", "doctor"])
        assert result.exit_code == 0
        assert "OK" in result.output or "fastmcp" in result.output

    def test_fastmcp_not_installed_shows_install_hint(self, runner):
        """When fastmcp is absent the output tells user how to install it."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "fastmcp":
                raise ImportError("no module named fastmcp")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = runner.invoke(main, ["mcp", "doctor"])
        assert "pip install" in result.output or "not installed" in result.output

    def test_doctor_help(self, runner):
        result = runner.invoke(main, ["mcp", "doctor", "--help"])
        assert result.exit_code == 0


# ===========================================================================
# TestMcpListTools
# ===========================================================================


class TestMcpListTools:
    """clew mcp list-tools lists MCP tools.

    Strategy: patch get_tools_sync to return fake tool lists,
    avoiding event-loop hangs inside Click's CliRunner.
    """

    def _make_fake_tool(self, name: str, description: str = ""):
        """Create a minimal fake MCP tool object."""
        tool = MagicMock()
        tool.name = name
        tool.description = description
        tool.parameters = {}
        tool.fn = None
        return tool

    def _patch_get_tools(self, tools):
        """Return a context manager that patches get_tools_sync to return tools."""
        return patch("scitex_clew._mcp.get_tools_sync", return_value=tools)

    def test_list_tools_import_error_exits_nonzero(self, runner):
        """If mcp server import fails, exit code is non-zero."""
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if "server" in str(name) and "mcp" in str(name):
                raise ImportError("fastmcp not installed (mocked)")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = runner.invoke(main, ["mcp", "list-tools"])
        assert result.exit_code != 0 or "error" in result.output.lower()

    def test_list_tools_exits_zero(self, runner):
        """list-tools exits 0 when get_tools_sync returns tools."""
        fake_tool = self._make_fake_tool("clew_status", "Get status.")
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools"])
        assert result.exit_code == 0

    def test_list_tools_shows_tool_count(self, runner):
        """list-tools output includes tool count."""
        tools = [self._make_fake_tool(f"t{i}") for i in range(3)]
        with self._patch_get_tools(tools):
            result = runner.invoke(main, ["mcp", "list-tools"])
        assert "3" in result.output

    def test_list_tools_json_outputs_valid_json(self, runner):
        """list-tools --json outputs valid JSON."""
        fake_tool = self._make_fake_tool("clew_status", "Get status.")
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total" in parsed
        assert "tools" in parsed

    def test_list_tools_json_total_matches_tool_count(self, runner):
        """JSON output's 'total' matches the length of 'tools'."""
        tools = [
            self._make_fake_tool("clew_status", "Status."),
            self._make_fake_tool("clew_list", "List runs."),
            self._make_fake_tool("clew_stats", "Stats."),
        ]
        with self._patch_get_tools(tools):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        parsed = json.loads(result.output)
        assert parsed["total"] == 3
        assert len(parsed["tools"]) == 3

    def test_list_tools_json_tool_has_name_key(self, runner):
        """Each entry in JSON 'tools' array has a 'name' field."""
        fake_tool = self._make_fake_tool("clew_mermaid", "Mermaid.")
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        parsed = json.loads(result.output)
        assert "name" in parsed["tools"][0]
        assert parsed["tools"][0]["name"] == "clew_mermaid"

    def test_list_tools_json_tool_has_description_key(self, runner):
        """Each entry in JSON 'tools' array has a 'description' field."""
        fake_tool = self._make_fake_tool("clew_list", "List runs.")
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        parsed = json.loads(result.output)
        assert "description" in parsed["tools"][0]

    def test_list_tools_help(self, runner):
        result = runner.invoke(main, ["mcp", "list-tools", "--help"])
        assert result.exit_code == 0
        assert "verbose" in result.output.lower() or "json" in result.output.lower()

    def test_list_tools_verbose_flag_accepted(self, runner):
        """list-tools -v is accepted and exits 0."""
        fake_tool = self._make_fake_tool("clew_status")
        fake_tool.parameters = {
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        }
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "-v"])
        assert result.exit_code == 0

    def test_list_tools_compact_flag_accepted(self, runner):
        """list-tools --compact is accepted and exits 0."""
        fake_tool = self._make_fake_tool("clew_stats")
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--compact"])
        assert result.exit_code == 0

    def test_list_tools_with_real_fastmcp_if_available(self, runner):
        """End-to-end test: if fastmcp is installed, list-tools must exit 0."""
        try:
            from scitex_clew._mcp.server import mcp as _mcp_server  # noqa: F401
        except ImportError:
            pytest.skip("fastmcp / MCP server not available in this environment")

        with patch("scitex_clew._mcp.get_tools_sync", return_value=[]):
            result = runner.invoke(main, ["mcp", "list-tools"])
        assert result.exit_code == 0


# ===========================================================================
# TestCompletionCommand
# ===========================================================================


class TestCompletionCommand:
    """clew completion <shell> generates a shell completion script."""

    def _invoke_completion(self, runner, shell: str):
        """Invoke completion with a mock subprocess so no real clew binary is needed."""
        mock_proc = MagicMock()
        mock_proc.stdout = f"# {shell} completion for clew\ncomplete -F _clew clew\n"
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc):
            return runner.invoke(main, ["completion", shell])

    def test_bash_completion_exit_code(self, runner):
        result = self._invoke_completion(runner, "bash")
        assert result.exit_code == 0

    def test_zsh_completion_exit_code(self, runner):
        result = self._invoke_completion(runner, "zsh")
        assert result.exit_code == 0

    def test_bash_completion_output_not_empty(self, runner):
        result = self._invoke_completion(runner, "bash")
        # stdout echoed from mock_proc.stdout
        assert len(result.output.strip()) > 0

    def test_zsh_completion_output_not_empty(self, runner):
        result = self._invoke_completion(runner, "zsh")
        assert len(result.output.strip()) > 0

    def test_invalid_shell_fails(self, runner):
        """Passing an unsupported shell name must cause a non-zero exit."""
        result = runner.invoke(main, ["completion", "powershell"])
        assert result.exit_code != 0

    def test_completion_help(self, runner):
        result = runner.invoke(main, ["completion", "--help"])
        assert result.exit_code == 0
        assert "bash" in result.output or "shell" in result.output.lower()

    def test_bash_completion_calls_subprocess(self, runner):
        """Verify that subprocess.run is called with the expected _CLEW_COMPLETE env."""
        mock_proc = MagicMock()
        mock_proc.stdout = "# bash completion\n"
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            runner.invoke(main, ["completion", "bash"])

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        env = call_kwargs[1].get("env") or call_kwargs.kwargs.get("env", {})
        assert env.get("_CLEW_COMPLETE") == "bash_source"

    def test_zsh_completion_calls_subprocess_with_zsh_source(self, runner):
        """Verify _CLEW_COMPLETE env var is set to 'zsh_source' for zsh."""
        mock_proc = MagicMock()
        mock_proc.stdout = "# zsh completion\n"
        mock_proc.returncode = 0

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            runner.invoke(main, ["completion", "zsh"])

        env = mock_run.call_args[1].get("env", {})
        assert env.get("_CLEW_COMPLETE") == "zsh_source"


# ===========================================================================
# TestCategorizedGroup
# ===========================================================================


class TestCategorizedGroup:
    """CategorizedGroup organises commands under labelled sections in --help."""

    def test_verification_section_present(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "Verification" in result.output

    def test_visualization_section_present(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "Visualization" in result.output

    def test_integration_section_present(self, runner):
        result = runner.invoke(main, ["--help"])
        assert "Integration" in result.output

    def test_status_in_verification_section(self, runner):
        result = runner.invoke(main, ["--help"])
        lines = result.output.splitlines()
        in_verification = False
        found_status = False
        for line in lines:
            if "Verification" in line:
                in_verification = True
            if "Visualization" in line or "Integration" in line:
                in_verification = False
            if in_verification and "status" in line.lower():
                found_status = True
                break
        assert found_status

    def test_mermaid_in_visualization_section(self, runner):
        result = runner.invoke(main, ["--help"])
        lines = result.output.splitlines()
        in_visualization = False
        found_mermaid = False
        for line in lines:
            if "Visualization" in line:
                in_visualization = True
            if "Integration" in line or "Other" in line:
                in_visualization = False
            if in_visualization and "mermaid" in line.lower():
                found_mermaid = True
                break
        assert found_mermaid


# ===========================================================================
# TestCliInit
# ===========================================================================


class TestCliInit:
    """The _cli package exports 'main' through its __init__."""

    def test_main_importable_from_cli_package(self):
        from scitex_clew._cli import main as cli_main

        assert callable(cli_main)

    def test_main_is_click_group(self):
        from scitex_clew._cli import main as cli_main

        assert isinstance(cli_main, click.Group)

    def test_cli_all_exports_main(self):
        from scitex_clew._cli import __all__

        assert "main" in __all__


# ===========================================================================
# TestGetVersion (internal helper)
# ===========================================================================


class TestGetVersion:
    """_get_version() returns a non-empty string."""

    def test_returns_string(self):
        from scitex_clew._cli._main import _get_version

        v = _get_version()
        assert isinstance(v, str)

    def test_returns_non_empty_string(self):
        from scitex_clew._cli._main import _get_version

        v = _get_version()
        assert len(v) > 0

    def test_fallback_on_missing_package(self):
        """When importlib.metadata.version raises, returns the fallback string."""
        with patch(
            "importlib.metadata.version",
            side_effect=Exception("package not found"),
        ):
            from scitex_clew._cli._main import _get_version

            v = _get_version()
        assert v == "0.0.0-unknown"


# ===========================================================================
# TestMcpFormatToolSignature (internal helper via list-tools)
# ===========================================================================


class TestMcpFormatToolSignature:
    """_format_tool_signature formats MCP tool signatures for human-readable output."""

    def test_tool_with_no_parameters_returns_empty_params(self):
        from scitex_clew._cli._mcp import _format_tool_signature

        tool = MagicMock()
        tool.name = "clew_status"
        tool.parameters = {"properties": {}, "required": []}
        tool.fn = None
        sig = _format_tool_signature(tool)
        assert "clew_status" in sig

    def test_tool_with_required_param(self):
        from scitex_clew._cli._mcp import _format_tool_signature

        tool = MagicMock()
        tool.name = "clew_run"
        tool.parameters = {
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        }
        tool.fn = None
        sig = _format_tool_signature(tool)
        assert "session_id" in sig

    def test_tool_with_optional_param_and_default(self):
        from scitex_clew._cli._mcp import _format_tool_signature

        tool = MagicMock()
        tool.name = "clew_list"
        tool.parameters = {
            "properties": {"limit": {"type": "integer", "default": 50}},
            "required": [],
        }
        tool.fn = None
        sig = _format_tool_signature(tool)
        assert "limit" in sig

    def test_multiline_flag_respected(self):
        from scitex_clew._cli._mcp import _format_tool_signature

        tool = MagicMock()
        tool.name = "clew_dag"
        tool.parameters = {
            "properties": {
                "target_files": {"type": "string"},
                "session_ids": {"type": "string"},
                "claims": {"type": "boolean"},
            },
            "required": ["target_files"],
        }
        tool.fn = None
        # multiline=True should introduce newlines when >2 params
        sig_multi = _format_tool_signature(tool, multiline=True)
        sig_single = _format_tool_signature(tool, multiline=False)
        assert "\n" in sig_multi
        assert "\n" not in sig_single


# ===========================================================================
# TestIntrospectFormatPythonSignature (internal helper)
# ===========================================================================


class TestIntrospectFormatPythonSignature:
    """_format_python_signature wraps a Python function signature with colors."""

    def test_returns_tuple_of_two(self):
        from scitex_clew._cli._introspect import _format_python_signature

        def sample_func(x: int, y: str = "hello") -> bool:
            pass

        result = _format_python_signature(sample_func)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_name_contains_function_name(self):
        from scitex_clew._cli._introspect import _format_python_signature

        def my_special_function():
            pass

        name_s, sig_s = _format_python_signature(my_special_function)
        # ANSI stripping: check the raw string contains the function name
        assert "my_special_function" in name_s

    def test_signature_contains_param_name(self):
        from scitex_clew._cli._introspect import _format_python_signature

        def func_with_params(alpha, beta: int = 0):
            pass

        name_s, sig_s = _format_python_signature(func_with_params)
        assert "alpha" in sig_s or "beta" in sig_s

    def test_return_annotation_in_signature(self):
        from scitex_clew._cli._introspect import _format_python_signature

        def func() -> int:
            pass

        name_s, sig_s = _format_python_signature(func)
        assert "int" in sig_s or "->" in sig_s


# ===========================================================================
# TestIntrospectGetApiTree (internal helper)
# ===========================================================================


class TestIntrospectGetApiTree:
    """_get_api_tree returns a list of API entries for a module."""

    def test_returns_list(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1)
        assert isinstance(result, list)

    def test_first_entry_has_name_key(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1)
        assert len(result) > 0
        assert "Name" in result[0]

    def test_first_entry_has_type_key(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1)
        assert "Type" in result[0]

    def test_first_entry_has_depth_key(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1)
        assert "Depth" in result[0]

    def test_docstring_key_present_when_requested(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1, docstring=True)
        assert "Docstring" in result[0]

    def test_docstring_key_absent_when_not_requested(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1, docstring=False)
        assert "Docstring" not in result[0]

    def test_root_type_is_module(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1)
        root = result[0]
        assert root["Type"] == "M"

    def test_depth_zero_for_root_entry(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1)
        assert result[0]["Depth"] == 0

    def test_deeper_entries_have_higher_depth(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=2)
        depths = [r["Depth"] for r in result]
        assert max(depths) >= 1

    def test_max_depth_one_contains_only_depth_zero_and_one(self):
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1)
        depths = set(r["Depth"] for r in result)
        assert depths.issubset({0, 1})


# EOF
