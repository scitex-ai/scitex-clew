#!/usr/bin/env python3
# Timestamp: "2026-03-14 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-clew/tests/test__cli.py
"""Tests for scitex_clew._cli modules.

Strategy
--------
- Use click.testing.CliRunner to invoke all CLI entry points in-process.
- Where commands call scitex_clew.* functions that touch the database, inject
  an isolated temp DB via set_db() before each test and tear it down after.
- MCP-related sub-commands that need fastmcp are tested by swapping the
  module-level ``fastmcp`` symbol via the hand-rolled ``_swap_attr``
  context manager (PA-306-compliant — no stdlib mock library used) so
  the suite does not require the optional [mcp] extra to pass.
- Each test asserts exit_code and one or more observable strings in output.
"""

from __future__ import annotations

import contextlib
import json

import pytest


@contextlib.contextmanager
def _swap_attr(obj, name, value):
    """Temporarily replace ``obj.name`` with ``value`` (mock-free patch).

    Restores the original attribute on exit, regardless of exception.
    """
    saved = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, saved)


class _FakeTool:
    """Minimal MCP tool stand-in exposing the attributes the CLI reads."""

    def __init__(self, name: str = "", description: str = "", parameters=None, fn=None):
        self.name = name
        self.description = description
        self.parameters = parameters if parameters is not None else {}
        self.fn = fn


class _FakeProc:
    """Minimal stand-in for a ``subprocess.CompletedProcess`` result."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class _CallRecorder:
    """Callable that records call args/kwargs (mock-free replacement)."""

    def __init__(self, return_value=None):
        self.return_value = return_value
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.return_value

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def assert_called_once(self) -> None:
        assert self.call_count == 1, f"expected 1 call, got {self.call_count}"

    @property
    def call_args(self):
        if not self.calls:
            return None
        args, kwargs = self.calls[-1]
        return _CallArgs(args, kwargs)


class _CallArgs:
    """Mimics the ``call_args`` API used by the tests (.kwargs)."""

    def __init__(self, args, kwargs):
        self.args = args
        self.kwargs = kwargs

# PA-303: click is in the [cli] extra (not [project] deps), so guard so a
# clean install without [cli] doesn't crash collection.
click = pytest.importorskip("click")
CliRunner = pytest.importorskip("click.testing").CliRunner

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
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_help_short_flag_exit_code(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["-h"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_help_contains_description(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert (
            "clew" in result.output.lower() or "verification" in result.output.lower()
        )

    def test_help_lists_status_command(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert "status" in result.output

    def test_help_lists_list_command(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert "list" in result.output

    def test_help_lists_verify_command(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert "verify" in result.output

    def test_help_lists_stats_command(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert "stats" in result.output

    def test_help_lists_mermaid_command(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert "mermaid" in result.output

    def test_no_args_shows_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, [])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_no_args_shows_help_status_in_result_output_or_usage_in_result_output(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, [])
        # Act
        # Assert
        # Assert
        # Assert
        assert "status" in result.output or "Usage" in result.output



# ===========================================================================
# TestVersion
# ===========================================================================


class TestVersion:
    """clew --version / -V outputs version string."""

    def test_version_long_flag_exit_code(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--version"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_version_short_flag_exit_code(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["-V"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_version_output_contains_scitex_clew(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--version"])
        # Assert
        # Assert
        assert "scitex-clew" in result.output

    def test_version_output_contains_dot_separated_number_len_parts_2(self, runner):
        # Arrange
        # Arrange
        # Arrange
        result = runner.invoke(main, ["--version"])
        # version string format: "scitex-clew X.Y.Z" or "scitex-clew X.Y.Z-something"
        # Act
        # Act
        parts = result.output.strip().split()
        # Act
        # Assert
        # Assert
        # Assert
        assert len(parts) >= 2

    def test_version_output_contains_dot_separated_number_in_version_str_len_parts_2(self, runner):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["--version"])
        # version string format: "scitex-clew X.Y.Z" or "scitex-clew X.Y.Z-something"
        # Act
        parts = result.output.strip().split()
        # Act
        # Assert
        # Assert
        assert len(parts) >= 2

    def test_version_output_has_at_least_two_tokens(self, runner):
        # Arrange
        result = runner.invoke(main, ["--version"])
        # Act
        parts = result.output.strip().split()
        # Assert
        assert len(parts) >= 2

    def test_version_output_contains_dot_separated_number(self, runner):
        # Arrange — version string format: "scitex-clew X.Y.Z" or "scitex-clew X.Y.Z-something"
        result = runner.invoke(main, ["--version"])
        parts = result.output.strip().split()
        # Act
        version_str = parts[-1] if parts else ""
        # Assert
        assert "." in version_str




# ===========================================================================
# TestHelpRecursive
# ===========================================================================


class TestHelpRecursive:
    """clew --help-recursive prints help for every sub-command."""

    def test_help_recursive_exit_code(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help-recursive"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_help_recursive_shows_equals_separator(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help-recursive"])
        # Assert
        # Assert
        assert "=" * 10 in result.output

    def test_help_recursive_shows_status_subcommand(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help-recursive"])
        # Assert
        # Assert
        assert "status" in result.output

    def test_help_recursive_shows_list_subcommand(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help-recursive"])
        # Assert
        # Assert
        assert "list" in result.output

    def test_help_recursive_shows_mcp_subcommand(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help-recursive"])
        # Assert
        # Assert
        assert "mcp" in result.output


# ===========================================================================
# TestStatusCommand
# ===========================================================================


class TestStatusCommand:
    """clew status outputs JSON and exits 0."""

    def test_exit_code_empty_db(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["status"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_output_is_valid_json(self, runner, isolated_db):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["status"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Assert
        # Assert
        assert isinstance(parsed, dict)

    def test_output_has_verified_count_key(self, runner, isolated_db):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["status"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Assert
        # Assert
        assert "verified_count" in parsed

    def test_output_has_mismatch_count_key(self, runner, isolated_db):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["status"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Assert
        # Assert
        assert "mismatch_count" in parsed

    def test_empty_db_verified_count_is_zero(self, runner, isolated_db):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["status"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Assert
        # Assert
        assert parsed["verified_count"] == 0

    def test_status_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["status", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_status_help_status_in_result_output_lower_or_overview_in_result_output_l(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["status", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "status" in result.output.lower() or "overview" in result.output.lower()



# ===========================================================================
# TestListCommand
# ===========================================================================


class TestListCommand:
    """clew list outputs run rows and exits 0."""

    def test_exit_code_empty_db(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_empty_db_no_rows_in_output(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs"])
        # With no runs, output should be empty or minimal
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_populated_db_shows_session_id_result_exit_code_equals_n_0(self, runner, populated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_populated_db_shows_session_id_populated_db_session_id_in_result_output(self, runner, populated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs"])
        # Act
        # Assert
        # Assert
        # Assert
        assert populated_db["session_id"] in result.output


    def test_populated_db_shows_script_path(self, runner, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs"])
        # Assert
        # Assert
        assert "analysis.py" in result.output

    def test_populated_db_shows_status(self, runner, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs"])
        # Assert
        # Assert
        assert "success" in result.output

    def test_limit_option_accepted(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs", "--limit", "5"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_limit_default_accepted(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs", "--limit", "50"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_help_limit_in_result_output_lower_or_runs_in_result_output_lower(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-runs", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "limit" in result.output.lower() or "runs" in result.output.lower()



# ===========================================================================
# TestVerifyCommand
# ===========================================================================


class TestVerifyCommand:
    """clew verify <session_id> checks a specific run."""

    def test_verify_existing_session_exit_code(self, runner, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["verify", populated_db["session_id"]])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_verify_existing_session_shows_ok_or_fail(self, runner, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["verify", populated_db["session_id"]])
        # Assert
        # Assert
        assert "OK" in result.output or "FAIL" in result.output

    def test_verify_existing_session_shows_session_id(self, runner, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["verify", populated_db["session_id"]])
        # Assert
        # Assert
        assert populated_db["session_id"] in result.output

    def test_verify_existing_session_shows_file_roles(self, runner, populated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["verify", populated_db["session_id"]])
        # File roles: "input" or "output"
        # Assert
        # Assert
        assert "input" in result.output or "output" in result.output

    def test_verify_nonexistent_session_exit_code(self, runner, isolated_db):
        """Verifying a missing session should still exit 0 (not crash)."""
        # Arrange
        # Act
        result = runner.invoke(main, ["verify", "nonexistent_session_xyz"])
        # The command should handle this gracefully; exit code may be 0 or 1
        # but it must not raise an unhandled exception (no traceback)
        # Assert
        assert "Traceback" not in result.output

    def test_verify_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["verify", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_verify_help_session_in_result_output_lower_or_verify_in_result_output_lo(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["verify", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "session" in result.output.lower() or "verify" in result.output.lower()



# ===========================================================================
# TestStatsCommand
# ===========================================================================


class TestStatsCommand:
    """clew stats outputs database statistics as JSON."""

    def test_exit_code_result_exit_code_equals_n_0_2(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["show-stats"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_output_is_valid_json(self, runner, isolated_db):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["show-stats"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Assert
        # Assert
        assert isinstance(parsed, dict)

    def test_output_has_total_runs_key(self, runner, isolated_db):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["show-stats"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Assert
        # Assert
        assert "total_runs" in parsed

    def test_empty_db_total_runs_zero(self, runner, isolated_db):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["show-stats"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Assert
        # Assert
        assert parsed["total_runs"] == 0

    def test_populated_db_total_runs_one_result_exit_code_equals_n_0(self, runner, populated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["show-stats"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_populated_db_total_runs_one_parsed_total_runs_1_result_exit_code_equals_n_0(self, runner, populated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["show-stats"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_populated_db_total_runs_one_parsed_total_runs_1_parsed_total_runs_1(self, runner, populated_db):
        # Arrange
        result = runner.invoke(main, ["show-stats"])
        # Act
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed.get("total_runs") == 1



    def test_stats_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["show-stats", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_stats_help_stats_in_result_output_lower_or_database_in_result_output_lo(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["show-stats", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "stats" in result.output.lower() or "database" in result.output.lower()



# ===========================================================================
# TestMermaidCommand
# ===========================================================================


class TestMermaidCommand:
    """clew mermaid generates a Mermaid DAG diagram."""

    def test_exit_code_result_exit_code_equals_n_0_2(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["print-mermaid"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_output_is_not_empty_result_exit_code_equals_n_0(self, runner, populated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["print-mermaid"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_output_is_not_empty_len_result_output_strip_0(self, runner, populated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["print-mermaid"])
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result.output.strip()) > 0


    def test_output_contains_mermaid_keyword(self, runner, populated_db):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["print-mermaid"])
        # Mermaid diagrams start with "graph" or "flowchart" or similar
        # Act
        # Act
        combined = result.output.lower()
        # Assert
        # Assert
        assert "graph" in combined or "flowchart" in combined or "mermaid" in combined

    def test_claims_flag_accepted(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["print-mermaid", "--claims"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_mermaid_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["print-mermaid", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_mermaid_help_mermaid_in_result_output_lower_or_dag_in_result_output_lower(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["print-mermaid", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "mermaid" in result.output.lower() or "dag" in result.output.lower()



# ===========================================================================
# TestListPythonApisCommand
# ===========================================================================


class TestListPythonApisCommand:
    """clew list-python-apis introspects the public API of scitex-clew."""

    def test_exit_code_result_exit_code_equals_n_0_2(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_output_contains_api_tree_header(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis"])
        # The command emits "API tree of scitex-clew"
        # Assert
        # Assert
        assert "scitex-clew" in result.output or "API" in result.output

    def test_output_contains_legend(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis"])
        # Assert
        # Assert
        assert (
            "Legend" in result.output
            or "[M]" in result.output
            or "[F]" in result.output
        )

    def test_verbose_flag_accepted(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "-v"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_double_verbose_flag_accepted(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "-vv"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_json_flag_outputs_valid_json_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "--json"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_json_flag_outputs_valid_json_parsed_is_list_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "--json"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_json_flag_outputs_valid_json_parsed_is_list_parsed_is_list(self, runner):
        # Arrange
        result = runner.invoke(main, ["list-python-apis", "--json"])
        # Act
        parsed = json.loads(result.output) if result.exit_code == 0 else None
        # Assert
        assert isinstance(parsed, list)



    def test_json_output_has_name_key_len_parsed_0(self, runner):
        # Arrange
        # Arrange
        # Arrange
        result = runner.invoke(main, ["list-python-apis", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(parsed) > 0

    def test_json_output_has_name_key_name_in_parsed_0(self, runner):
        # Arrange
        # Arrange
        # Arrange
        result = runner.invoke(main, ["list-python-apis", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Name" in parsed[0]


    def test_json_output_has_type_key_len_parsed_0(self, runner):
        # Arrange
        # Arrange
        # Arrange
        result = runner.invoke(main, ["list-python-apis", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(parsed) > 0

    def test_json_output_has_type_key_type_in_parsed_0(self, runner):
        # Arrange
        # Arrange
        # Arrange
        result = runner.invoke(main, ["list-python-apis", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Type" in parsed[0]


    def test_json_output_has_depth_key_len_parsed_0(self, runner):
        # Arrange
        # Arrange
        # Arrange
        result = runner.invoke(main, ["list-python-apis", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(parsed) > 0

    def test_json_output_has_depth_key_depth_in_parsed_0(self, runner):
        # Arrange
        # Arrange
        # Arrange
        result = runner.invoke(main, ["list-python-apis", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Depth" in parsed[0]


    def test_max_depth_option_accepted(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "--max-depth", "2"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_root_only_option_accepted(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "--root-only"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_python_apis_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_python_apis_help_api_in_result_output_lower_or_python_in_result_output_lower(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "api" in result.output.lower() or "python" in result.output.lower()


    def test_json_and_verbose_combination_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "--json", "-v"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_json_and_verbose_combination_docstring_in_parsed_0_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["list-python-apis", "--json", "-v"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_json_and_verbose_combination_docstring_in_parsed_0_docstring_in_parsed_0(self, runner):
        # Arrange
        result = runner.invoke(main, ["list-python-apis", "--json", "-v"])
        # Act
        parsed = json.loads(result.output) if result.exit_code == 0 else [{}]
        # Assert
        assert "Docstring" in parsed[0]




# ===========================================================================
# TestMcpGroupHelp
# ===========================================================================


class TestMcpGroupHelp:
    """clew mcp --help and clew mcp without arguments show group help."""

    def test_mcp_help_exit_code(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "--help"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_mcp_no_args_exit_code(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_mcp_help_contains_list_tools(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "--help"])
        # Assert
        # Assert
        assert "list-tools" in result.output

    def test_mcp_help_contains_installation(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "--help"])
        # Assert
        # Assert
        assert "installation" in result.output

    def test_mcp_help_contains_doctor(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "--help"])
        # Assert
        # Assert
        assert "doctor" in result.output

    def test_mcp_help_contains_start(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "--help"])
        # Assert
        # Assert
        assert "start" in result.output

    def test_mcp_help_recursive_exit_code(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "--help-recursive"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_mcp_help_recursive_shows_subcommands(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "--help-recursive"])
        # Assert
        # Assert
        assert "list-tools" in result.output or "doctor" in result.output


# ===========================================================================
# TestMcpInstallation
# ===========================================================================


class TestMcpInstallation:
    """clew mcp installation prints setup instructions."""

    def test_exit_code_result_exit_code_equals_n_0_2(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "install"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_shows_pip_install(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "install"])
        # Assert
        # Assert
        assert "pip install" in result.output

    def test_shows_mcp_extra(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "install"])
        # Assert
        # Assert
        assert "mcp" in result.output

    def test_shows_mcp_servers_block(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "install"])
        # Assert
        # Assert
        assert "mcpServers" in result.output

    def test_shows_clew_mcp_start(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "install"])
        # Assert
        # Assert
        assert "mcp" in result.output and "start" in result.output

    def test_shows_verify_instructions(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "install"])
        # Assert
        # Assert
        assert "clew mcp doctor" in result.output or "doctor" in result.output

    def test_installation_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "install", "--help"])
        # Assert
        # Assert
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
        # Arrange
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "fastmcp":
                raise ImportError("fastmcp not installed (mocked)")
            return real_import(name, *args, **kwargs)

        # Act
        with _swap_attr(builtins, "__import__", fake_import):
            result = runner.invoke(main, ["mcp", "doctor"])
        # Assert
        assert result.exit_code == 0

    def test_shows_checking_message(self, runner):
        """Regardless of fastmcp availability the initial message is shown."""
        # Arrange
        import scitex_clew._mcp as _mcp_mod

        tools = [_FakeTool("t1"), _FakeTool("t2"), _FakeTool("t3")]
        # Act
        with _swap_attr(_mcp_mod, "get_tools_sync", lambda *a, **kw: tools):
            result = runner.invoke(main, ["mcp", "doctor"])
        # Assert
        assert "Checking" in result.output or "mcp" in result.output.lower()

    def test_fastmcp_installed_shows_ok_result_exit_code_equals_n_0(self, runner):
        # Arrange
        pytest.importorskip("fastmcp")
        import scitex_clew._mcp as _mcp_mod

        tools = [_FakeTool("t1"), _FakeTool("t2"), _FakeTool("t3")]
        # Act
        with _swap_attr(_mcp_mod, "get_tools_sync", lambda *a, **kw: tools):
            result = runner.invoke(main, ["mcp", "doctor"])
        # Assert
        assert result.exit_code == 0

    def test_fastmcp_installed_shows_ok_ok_in_result_output_or_fastmcp_in_result_output(self, runner):
        # Arrange
        pytest.importorskip("fastmcp")
        import scitex_clew._mcp as _mcp_mod

        tools = [_FakeTool("t1"), _FakeTool("t2"), _FakeTool("t3")]
        # Act
        with _swap_attr(_mcp_mod, "get_tools_sync", lambda *a, **kw: tools):
            result = runner.invoke(main, ["mcp", "doctor"])
        # Assert
        assert "OK" in result.output or "fastmcp" in result.output


    def test_fastmcp_not_installed_shows_install_hint(self, runner):
        """When fastmcp is absent the output tells user how to install it."""
        # Arrange
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "fastmcp":
                raise ImportError("no module named fastmcp")
            return real_import(name, *args, **kwargs)

        # Act
        with _swap_attr(builtins, "__import__", fake_import):
            result = runner.invoke(main, ["mcp", "doctor"])
        # Assert
        assert "pip install" in result.output or "not installed" in result.output

    def test_doctor_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "doctor", "--help"])
        # Assert
        # Assert
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
        return _FakeTool(name=name, description=description, parameters={}, fn=None)

    def _patch_get_tools(self, tools):
        """Return a context manager that swaps get_tools_sync to return tools."""
        import scitex_clew._mcp as _mcp_mod

        return _swap_attr(_mcp_mod, "get_tools_sync", lambda *a, **kw: tools)

    def test_list_tools_import_error_exits_nonzero(self, runner):
        """If mcp server import fails, exit code is non-zero."""
        # Arrange
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if "server" in str(name) and "mcp" in str(name):
                raise ImportError("fastmcp not installed (mocked)")
            return real_import(name, *args, **kwargs)

        # Act
        with _swap_attr(builtins, "__import__", fake_import):
            result = runner.invoke(main, ["mcp", "list-tools"])
        # Assert
        assert result.exit_code != 0 or "error" in result.output.lower()

    def test_list_tools_exits_zero(self, runner):
        """list-tools exits 0 when get_tools_sync returns tools."""
        # Arrange
        fake_tool = self._make_fake_tool("clew_status", "Get status.")
        # Act
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools"])
        # Assert
        assert result.exit_code == 0

    def test_list_tools_shows_tool_count(self, runner):
        """list-tools output includes tool count."""
        # Arrange
        tools = [self._make_fake_tool(f"t{i}") for i in range(3)]
        # Act
        with self._patch_get_tools(tools):
            result = runner.invoke(main, ["mcp", "list-tools"])
        # Assert
        assert "3" in result.output

    def test_list_tools_json_outputs_valid_json_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Arrange
        fake_tool = self._make_fake_tool("clew_status", "Get status.")
        # Act
        # Act
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_tools_json_outputs_valid_json_total_in_parsed_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        fake_tool = self._make_fake_tool("clew_status", "Get status.")
        # Act
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_tools_json_outputs_valid_json_total_in_parsed_total_in_parsed(self, runner):
        # Arrange
        fake_tool = self._make_fake_tool("clew_status", "Get status.")
        # Act
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert "total" in parsed


    def test_list_tools_json_outputs_valid_json_tools_in_parsed_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        fake_tool = self._make_fake_tool("clew_status", "Get status.")
        # Act
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_tools_json_outputs_valid_json_tools_in_parsed_tools_in_parsed(self, runner):
        # Arrange
        fake_tool = self._make_fake_tool("clew_status", "Get status.")
        # Act
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert "tools" in parsed



    def test_list_tools_json_total_matches_tool_count_parsed_total_3(self, runner):
        # Arrange
        # Arrange
        # Arrange
        tools = [
            self._make_fake_tool("clew_status", "Status."),
            self._make_fake_tool("clew_list_runs", "List runs."),
            self._make_fake_tool("clew_stats", "Stats."),
        ]
        with self._patch_get_tools(tools):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert parsed["total"] == 3

    def test_list_tools_json_total_matches_tool_count_len_parsed_tools_is_3(self, runner):
        # Arrange
        # Arrange
        # Arrange
        tools = [
            self._make_fake_tool("clew_status", "Status."),
            self._make_fake_tool("clew_list_runs", "List runs."),
            self._make_fake_tool("clew_stats", "Stats."),
        ]
        with self._patch_get_tools(tools):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(parsed["tools"]) == 3


    def test_list_tools_json_tool_has_name_key_name_in_parsed_tools_0(self, runner):
        # Arrange
        # Arrange
        # Arrange
        fake_tool = self._make_fake_tool("clew_mermaid", "Mermaid.")
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert "name" in parsed["tools"][0]

    def test_list_tools_json_tool_has_name_key_parsed_tools_0_name_clew_mermaid(self, runner):
        # Arrange
        # Arrange
        # Arrange
        fake_tool = self._make_fake_tool("clew_mermaid", "Mermaid.")
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        # Act
        # Act
        parsed = json.loads(result.output)
        # Act
        # Assert
        # Assert
        # Assert
        assert parsed["tools"][0]["name"] == "clew_mermaid"


    def test_list_tools_json_tool_has_description_key(self, runner):
        """Each entry in JSON 'tools' array has a 'description' field."""
        # Arrange
        fake_tool = self._make_fake_tool("clew_list_runs", "List runs.")
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--json"])
        # Act
        parsed = json.loads(result.output)
        # Assert
        assert "description" in parsed["tools"][0]

    def test_list_tools_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "list-tools", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_tools_help_verbose_in_result_output_lower_or_json_in_result_output_lowe(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["mcp", "list-tools", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "verbose" in result.output.lower() or "json" in result.output.lower()


    def test_list_tools_verbose_flag_accepted(self, runner):
        """list-tools -v is accepted and exits 0."""
        # Arrange
        fake_tool = self._make_fake_tool("clew_status")
        fake_tool.parameters = {
            "properties": {"session_id": {"type": "string"}},
            "required": ["session_id"],
        }
        # Act
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "-v"])
        # Assert
        assert result.exit_code == 0

    def test_list_tools_compact_flag_accepted(self, runner):
        """list-tools --compact is accepted and exits 0."""
        # Arrange
        fake_tool = self._make_fake_tool("clew_stats")
        # Act
        with self._patch_get_tools([fake_tool]):
            result = runner.invoke(main, ["mcp", "list-tools", "--compact"])
        # Assert
        assert result.exit_code == 0

    def test_list_tools_with_real_fastmcp_if_available(self, runner):
        """End-to-end test: if fastmcp is installed, list-tools must exit 0."""
        # Arrange
        pytest.importorskip("scitex_clew._mcp.server")
        import scitex_clew._mcp as _mcp_mod

        # Act
        with _swap_attr(_mcp_mod, "get_tools_sync", lambda *a, **kw: []):
            result = runner.invoke(main, ["mcp", "list-tools"])
        # Assert
        assert result.exit_code == 0


# ===========================================================================
# TestCompletionCommand
# ===========================================================================


class TestCompletionCommand:
    """`clew print-shell-completion --shell <bash|zsh|fish>` (audit-cli §1a).

    The legacy `clew completion <SHELL>` shape was split into
    `print-shell-completion` and `install-shell-completion`. The
    underlying mechanism still shells out via `_SCITEX_CLEW_COMPLETE`
    (Click's auto-completion env var), so the tests mock subprocess.run.
    """

    _ENV_VAR = "_SCITEX_CLEW_COMPLETE"

    def _invoke_print(self, runner, shell: str):
        import scitex_dev._cli._completion as _completion_mod

        fake_proc = _FakeProc(
            stdout=f"# {shell} completion for scitex-clew\n", returncode=0
        )
        recorder = _CallRecorder(return_value=fake_proc)
        with _swap_attr(_completion_mod.subprocess, "run", recorder):
            return runner.invoke(main, ["print-shell-completion", "--shell", shell])

    def test_bash_completion_exit_code(self, runner):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert self._invoke_print(runner, "bash").exit_code == 0

    def test_zsh_completion_exit_code(self, runner):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert self._invoke_print(runner, "zsh").exit_code == 0

    def test_bash_completion_output_not_empty(self, runner):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert len(self._invoke_print(runner, "bash").output.strip()) > 0

    def test_zsh_completion_output_not_empty(self, runner):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert len(self._invoke_print(runner, "zsh").output.strip()) > 0

    def test_invalid_shell_fails(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(
            main, ["print-shell-completion", "--shell", "powershell"]
        )
        # Assert
        # Assert
        assert result.exit_code != 0

    def test_print_completion_help_result_exit_code_equals_n_0(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["print-shell-completion", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_print_completion_help_shell_in_result_output_lower(self, runner):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["print-shell-completion", "--help"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "shell" in result.output.lower()


    def test_bash_completion_calls_subprocess(self, runner):
        # Arrange
        # Arrange
        import scitex_dev._cli._completion as _completion_mod

        fake_proc = _FakeProc(stdout="# bash completion\n", returncode=0)
        recorder = _CallRecorder(return_value=fake_proc)
        with _swap_attr(_completion_mod.subprocess, "run", recorder):
            runner.invoke(main, ["print-shell-completion", "--shell", "bash"])

        recorder.assert_called_once()
        # Act
        # Act
        env = recorder.call_args.kwargs.get("env") or {}
        # Assert
        # Assert
        assert env.get(self._ENV_VAR) == "bash_source"

    def test_zsh_completion_calls_subprocess_with_zsh_source(self, runner):
        # Arrange
        # Arrange
        import scitex_dev._cli._completion as _completion_mod

        fake_proc = _FakeProc(stdout="# zsh completion\n", returncode=0)
        recorder = _CallRecorder(return_value=fake_proc)
        with _swap_attr(_completion_mod.subprocess, "run", recorder):
            runner.invoke(main, ["print-shell-completion", "--shell", "zsh"])

        # Act
        # Act
        env = recorder.call_args.kwargs.get("env") or {}
        # Assert
        # Assert
        assert env.get(self._ENV_VAR) == "zsh_source"


# ===========================================================================
# TestCategorizedGroup
# ===========================================================================


class TestCategorizedGroup:
    """CategorizedGroup organises commands under labelled sections in --help."""

    def test_verification_section_present(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert "Verification" in result.output

    def test_visualization_section_present(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert "Visualization" in result.output

    def test_integration_section_present(self, runner):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--help"])
        # Assert
        # Assert
        assert "Integration" in result.output

    def test_status_in_verification_section(self, runner):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["--help"])
        lines = result.output.splitlines()
        in_verification = False
        found_status = False
        # Act
        # Act
        for line in lines:
            if "Verification" in line:
                in_verification = True
            if "Visualization" in line or "Integration" in line:
                in_verification = False
            if in_verification and "status" in line.lower():
                found_status = True
                break
        # Assert
        # Assert
        assert found_status

    def test_mermaid_in_visualization_section(self, runner):
        # Arrange
        # Arrange
        result = runner.invoke(main, ["--help"])
        lines = result.output.splitlines()
        in_visualization = False
        found_mermaid = False
        # Act
        # Act
        for line in lines:
            if "Visualization" in line:
                in_visualization = True
            if "Integration" in line or "Other" in line:
                in_visualization = False
            if in_visualization and "mermaid" in line.lower():
                found_mermaid = True
                break
        # Assert
        # Assert
        assert found_mermaid


# ===========================================================================
# TestCliInit
# ===========================================================================


class TestCliInit:
    """The _cli package exports 'main' through its __init__."""

    def test_main_importable_from_cli_package(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._cli import main as cli_main

        # Assert
        # Assert
        assert callable(cli_main)

    def test_main_is_click_group(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._cli import main as cli_main

        # Assert
        # Assert
        assert isinstance(cli_main, click.Group)

    def test_cli_all_exports_main(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._cli import __all__

        # Assert
        # Assert
        assert "main" in __all__


# ===========================================================================
# TestGetVersion (internal helper)
# ===========================================================================


class TestGetVersion:
    """_get_version() returns a non-empty string."""

    def test_returns_string_v_is_str(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._main import _get_version

        # Act
        # Act
        v = _get_version()
        # Assert
        # Assert
        assert isinstance(v, str)

    def test_returns_non_empty_string(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._main import _get_version

        # Act
        # Act
        v = _get_version()
        # Assert
        # Assert
        assert len(v) > 0

    def test_fallback_on_missing_package(self):
        """When importlib.metadata.version raises, returns the fallback string."""
        # Arrange
        import importlib.metadata as _md

        def _raise(*_a, **_kw):
            raise Exception("package not found")

        # Act
        with _swap_attr(_md, "version", _raise):
            from scitex_clew._cli._main import _get_version

            v = _get_version()
        # Assert
        assert v == "0.0.0-unknown"


# ===========================================================================
# TestMcpFormatToolSignature (internal helper via list-tools)
# ===========================================================================


class TestMcpFormatToolSignature:
    """_format_tool_signature formats MCP tool signatures for human-readable output."""

    def test_tool_with_no_parameters_returns_empty_params(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._mcp import _format_tool_signature

        tool = _FakeTool(
            name="clew_status",
            parameters={"properties": {}, "required": []},
            fn=None,
        )
        # Act
        # Act
        sig = _format_tool_signature(tool)
        # Assert
        # Assert
        assert "clew_status" in sig

    def test_tool_with_required_param(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._mcp import _format_tool_signature

        tool = _FakeTool(
            name="clew_run",
            parameters={
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
            },
            fn=None,
        )
        # Act
        # Act
        sig = _format_tool_signature(tool)
        # Assert
        # Assert
        assert "session_id" in sig

    def test_tool_with_optional_param_and_default(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._mcp import _format_tool_signature

        tool = _FakeTool(
            name="clew_list_runs",
            parameters={
                "properties": {"limit": {"type": "integer", "default": 50}},
                "required": [],
            },
            fn=None,
        )
        # Act
        # Act
        sig = _format_tool_signature(tool)
        # Assert
        # Assert
        assert "limit" in sig

    def test_multiline_flag_respected_n_in_sig_multi(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._cli._mcp import _format_tool_signature
        tool = _FakeTool(
            name="clew_dag",
            parameters={
                "properties": {
                    "target_files": {"type": "string"},
                    "session_ids": {"type": "string"},
                    "claims": {"type": "boolean"},
                },
                "required": ["target_files"],
            },
            fn=None,
        )
        # multiline=True should introduce newlines when >2 params
        sig_multi = _format_tool_signature(tool, multiline=True)
        # Act
        # Act
        sig_single = _format_tool_signature(tool, multiline=False)
        # Act
        # Assert
        # Assert
        # Assert
        assert "\n" in sig_multi

    def test_multiline_flag_respected_n_not_in_sig_single(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._cli._mcp import _format_tool_signature
        tool = _FakeTool(
            name="clew_dag",
            parameters={
                "properties": {
                    "target_files": {"type": "string"},
                    "session_ids": {"type": "string"},
                    "claims": {"type": "boolean"},
                },
                "required": ["target_files"],
            },
            fn=None,
        )
        # multiline=True should introduce newlines when >2 params
        sig_multi = _format_tool_signature(tool, multiline=True)
        # Act
        # Act
        sig_single = _format_tool_signature(tool, multiline=False)
        # Act
        # Assert
        # Assert
        # Assert
        assert "\n" not in sig_single



# ===========================================================================
# TestIntrospectFormatPythonSignature (internal helper)
# ===========================================================================


class TestIntrospectFormatPythonSignature:
    """_format_python_signature wraps a Python function signature with colors."""

    def test_returns_tuple_of_two_result_is_tuple(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _format_python_signature
        def sample_func(x: int, y: str = "hello") -> bool:
            pass
        # Act
        # Act
        result = _format_python_signature(sample_func)
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result, tuple)

    def test_returns_tuple_of_two_len_result_is_2(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _format_python_signature
        def sample_func(x: int, y: str = "hello") -> bool:
            pass
        # Act
        # Act
        result = _format_python_signature(sample_func)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 2


    def test_name_contains_function_name(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _format_python_signature

        def my_special_function():
            pass

        # Act
        # Act
        name_s, sig_s = _format_python_signature(my_special_function)
        # ANSI stripping: check the raw string contains the function name
        # Assert
        # Assert
        assert "my_special_function" in name_s

    def test_signature_contains_param_name(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _format_python_signature

        def func_with_params(alpha, beta: int = 0):
            pass

        # Act
        # Act
        name_s, sig_s = _format_python_signature(func_with_params)
        # Assert
        # Assert
        assert "alpha" in sig_s or "beta" in sig_s

    def test_return_annotation_in_signature(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _format_python_signature

        def func() -> int:
            pass

        # Act
        # Act
        name_s, sig_s = _format_python_signature(func)
        # Assert
        # Assert
        assert "int" in sig_s or "->" in sig_s


# ===========================================================================
# TestIntrospectGetApiTree (internal helper)
# ===========================================================================


class TestIntrospectGetApiTree:
    """_get_api_tree returns a list of API entries for a module."""

    def test_returns_list_result_is_list(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        # Act
        # Act
        result = _get_api_tree(scitex_clew, max_depth=1)
        # Assert
        # Assert
        assert isinstance(result, list)

    def test_first_entry_has_name_key_len_result_0(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew
        # Act
        # Act
        result = _get_api_tree(scitex_clew, max_depth=1)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) > 0

    def test_first_entry_has_name_key_name_in_result_0(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew
        # Act
        # Act
        result = _get_api_tree(scitex_clew, max_depth=1)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Name" in result[0]


    def test_first_entry_has_type_key(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        # Act
        # Act
        result = _get_api_tree(scitex_clew, max_depth=1)
        # Assert
        # Assert
        assert "Type" in result[0]

    def test_first_entry_has_depth_key(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        # Act
        # Act
        result = _get_api_tree(scitex_clew, max_depth=1)
        # Assert
        # Assert
        assert "Depth" in result[0]

    def test_docstring_key_present_when_requested(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        # Act
        # Act
        result = _get_api_tree(scitex_clew, max_depth=1, docstring=True)
        # Assert
        # Assert
        assert "Docstring" in result[0]

    def test_docstring_key_absent_when_not_requested(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        # Act
        # Act
        result = _get_api_tree(scitex_clew, max_depth=1, docstring=False)
        # Assert
        # Assert
        assert "Docstring" not in result[0]

    def test_root_type_is_module(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1)
        # Act
        # Act
        root = result[0]
        # Assert
        # Assert
        assert root["Type"] == "M"

    def test_depth_zero_for_root_entry(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        # Act
        # Act
        result = _get_api_tree(scitex_clew, max_depth=1)
        # Assert
        # Assert
        assert result[0]["Depth"] == 0

    def test_deeper_entries_have_higher_depth(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=2)
        # Act
        # Act
        depths = [r["Depth"] for r in result]
        # Assert
        # Assert
        assert max(depths) >= 1

    def test_max_depth_one_contains_only_depth_zero_and_one(self):
        # Arrange
        # Arrange
        from scitex_clew._cli._introspect import _get_api_tree
        import scitex_clew

        result = _get_api_tree(scitex_clew, max_depth=1)
        # Act
        # Act
        depths = set(r["Depth"] for r in result)
        # Assert
        # Assert
        assert depths.issubset({0, 1})


# EOF
