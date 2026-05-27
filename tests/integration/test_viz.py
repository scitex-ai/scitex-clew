#!/usr/bin/env python3
# Timestamp: "2026-03-14 (TestDeveloperAgent)"
# File: /home/ywatanabe/proj/scitex-clew/tests/test__viz.py
"""Tests for scitex_clew._viz subpackage.

Covers:
  - _colors.py   (Colors, VerificationLevel, status_icon, status_text)
  - _templates.py (get_timestamp, get_html_template)
  - _format.py   (format_run_verification, format_run_detailed,
                   format_chain_verification, format_status, format_list)
  - _json.py     (format_path, file_to_node_id, verify_file_hash,
                   generate_dag_json – empty-chain path)
  - _mermaid_nodes.py (get_file_icon, append_class_definitions,
                        add_script_node, add_file_nodes)
  - _mermaid_dag.py  (generate_simple_dag, generate_detailed_dag,
                       generate_multi_target_dag – no-targets path)
  - _mermaid.py  (generate_mermaid_dag – empty-db path,
                   generate_html_dag, render_dag)
  - _utils.py    (print_verification_summary – via capsys)
"""

from __future__ import annotations

import contextlib
import json

import pytest

from scitex_clew import (
    ChainVerification,
    FileVerification,
    RunVerification,
    VerificationLevel,
    VerificationStatus,
)
from scitex_clew import _db as _db_mod
from scitex_clew._viz import _mermaid as _mermaid_mod
from scitex_clew._viz import _utils as _utils_mod

# ---------------------------------------------------------------------------
# PA-306-compliant stubs (mock-free monkey-patching helpers)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _swap_attr(obj, name, value):
    """Temporarily swap ``obj.name`` with ``value`` (mock-free patch)."""
    saved = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, saved)


class _FakeDB:
    """Minimal stand-in for ``VerificationDB`` used by tests in this module.

    Only the methods the tests actually invoke are implemented; canned
    return values are supplied via ``__init__`` kwargs.
    """

    def __init__(self, *, list_runs=None, get_chain=None):
        self._list_runs = list_runs if list_runs is not None else []
        self._get_chain = get_chain if get_chain is not None else []

    def list_runs(self, *args, **kwargs):
        return list(self._list_runs)

    def get_chain(self, *args, **kwargs):
        return list(self._get_chain)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_file_verification(
    path: str = "/data/file.csv",
    role: str = "input",
    expected_hash: str = "aabbcc112233",
    current_hash: str = "aabbcc112233",
    status: VerificationStatus = VerificationStatus.VERIFIED,
) -> FileVerification:
    return FileVerification(
        path=path,
        role=role,
        expected_hash=expected_hash,
        current_hash=current_hash,
        status=status,
    )


def _make_run_verification(
    session_id: str = "sess_abc123",
    script_path: str = "/scripts/run.py",
    status: VerificationStatus = VerificationStatus.VERIFIED,
    files: list = None,
    level: VerificationLevel = VerificationLevel.CACHE,
) -> RunVerification:
    return RunVerification(
        session_id=session_id,
        script_path=script_path,
        status=status,
        files=files or [],
        combined_hash_expected=None,
        combined_hash_current=None,
        level=level,
    )


def _make_chain_verification(
    target_file: str = "/data/result.csv",
    runs: list = None,
    status: VerificationStatus = VerificationStatus.VERIFIED,
) -> ChainVerification:
    return ChainVerification(
        target_file=target_file,
        runs=runs or [],
        status=status,
    )


# ===========================================================================
# _colors.py
# ===========================================================================


class TestColors:
    """Colors class provides ANSI escape codes."""

    def test_green_is_ansi_escape(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz._colors import Colors

        # Assert
        # Assert
        assert Colors.GREEN.startswith("\033[")

    def test_red_is_ansi_escape(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz._colors import Colors

        # Assert
        # Assert
        assert Colors.RED.startswith("\033[")

    def test_yellow_is_ansi_escape(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz._colors import Colors

        # Assert
        # Assert
        assert Colors.YELLOW.startswith("\033[")

    def test_reset_is_ansi_escape(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz._colors import Colors

        # Assert
        # Assert
        assert Colors.RESET.startswith("\033[")

    def test_bold_is_ansi_escape(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz._colors import Colors

        # Assert
        # Assert
        assert Colors.BOLD.startswith("\033[")

    def test_all_color_attributes_exist(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz._colors import Colors

        # Assert
        # Assert
        assert all(hasattr(Colors, attr) for attr in ('GREEN', 'RED', 'YELLOW', 'CYAN', 'GRAY', 'RESET', 'BOLD')), f'Missing Colors.{attr}'


class TestVerificationLevelColors:
    """VerificationLevel in _colors is a plain class (not enum)."""

    def test_cache_value_verificationlevel_cache_equals_cache(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz._colors import VerificationLevel

        # Assert
        # Assert
        assert VerificationLevel.CACHE == "cache"

    def test_scratch_value_verificationlevel_scratch_equals_scratch(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz._colors import VerificationLevel

        # Assert
        # Assert
        assert VerificationLevel.SCRATCH == "scratch"


class TestStatusIcon:
    """status_icon returns a coloured bullet for each VerificationStatus."""

    def test_verified_contains_bullet(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import status_icon

        # Act
        # Act
        icon = status_icon(VerificationStatus.VERIFIED)
        # Assert
        # Assert
        assert "●" in icon

    def test_mismatch_contains_bullet(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import status_icon

        # Act
        # Act
        icon = status_icon(VerificationStatus.MISMATCH)
        # Assert
        # Assert
        assert "●" in icon

    def test_missing_contains_circle(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import status_icon

        # Act
        # Act
        icon = status_icon(VerificationStatus.MISSING)
        # Assert
        # Assert
        assert "○" in icon

    def test_unknown_contains_question_mark(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import status_icon

        # Act
        # Act
        icon = status_icon(VerificationStatus.UNKNOWN)
        # Assert
        # Assert
        assert "?" in icon

    def test_scratch_level_verified_gives_double_bullet(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import VerificationLevel, status_icon

        # Act
        # Act
        icon = status_icon(VerificationStatus.VERIFIED, level=VerificationLevel.SCRATCH)
        # Assert
        # Assert
        assert "●●" in icon

    def test_scratch_level_mismatch_gives_single_bullet_not_in_icon(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import VerificationLevel, status_icon
        # Act
        # Act
        icon = status_icon(VerificationStatus.MISMATCH, level=VerificationLevel.SCRATCH)
        # Act
        # Assert
        # Assert
        # Assert
        assert "●●" not in icon

    def test_scratch_level_mismatch_gives_single_bullet_in_icon(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import VerificationLevel, status_icon
        # Act
        # Act
        icon = status_icon(VerificationStatus.MISMATCH, level=VerificationLevel.SCRATCH)
        # Act
        # Assert
        # Assert
        # Assert
        assert "●" in icon


    def test_unknown_status_falls_back_to_question_mark(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import status_icon

        # Pass a sentinel that is not in the icons dict
        # Act
        # Act
        icon = status_icon("completely_unknown_value")
        # Assert
        # Assert
        assert icon == "?"


class TestStatusText:
    """status_text returns coloured text label for each status."""

    def test_verified_contains_word_verified(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import status_text

        # Act
        # Act
        text = status_text(VerificationStatus.VERIFIED)
        # Assert
        # Assert
        assert "verified" in text

    def test_mismatch_contains_word_mismatch(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import status_text

        # Act
        # Act
        text = status_text(VerificationStatus.MISMATCH)
        # Assert
        # Assert
        assert "mismatch" in text

    def test_missing_contains_word_missing(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import status_text

        # Act
        # Act
        text = status_text(VerificationStatus.MISSING)
        # Assert
        # Assert
        assert "missing" in text

    def test_unknown_status_falls_back_to_unknown(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._colors import status_text

        # Act
        # Act
        text = status_text("not_a_real_status")
        # Assert
        # Assert
        assert text == "unknown"


# ===========================================================================
# _templates.py
# ===========================================================================


class TestGetTimestamp:
    """get_timestamp returns a correctly formatted string."""

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._templates import get_timestamp

        # Act
        # Act
        ts = get_timestamp()
        # Assert
        # Assert
        assert isinstance(ts, str)

    def test_format_YYYY_MM_DD_HH_MM_SS(self):
        """Timestamp must match 'YYYY-MM-DD HH:MM:SS'."""
        # Arrange
        import re

        from scitex_clew._viz._templates import get_timestamp

        ts = get_timestamp()
        # Act
        pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        # Assert
        assert re.match(pattern, ts), f"Timestamp '{ts}' doesn't match expected format"


class TestGetHtmlTemplate:
    """get_html_template produces a complete HTML document."""

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._templates import get_html_template

        # Act
        # Act
        html = get_html_template("My Title", "graph TD\n    A --> B")
        # Assert
        # Assert
        assert isinstance(html, str)

    def test_contains_doctype_doctype_html_in_result(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._templates import get_html_template

        # Act
        # Act
        html = get_html_template("T", "graph TD")
        # Assert
        # Assert
        assert "<!DOCTYPE html>" in html

    def test_contains_title_pipeline_dag_in_html(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._templates import get_html_template

        # Act
        # Act
        html = get_html_template("Pipeline DAG", "graph TD")
        # Assert
        # Assert
        assert "Pipeline DAG" in html

    def test_contains_mermaid_code(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._templates import get_html_template

        mermaid_snippet = "graph TD\n    A --> B"
        # Act
        # Act
        html = get_html_template("T", mermaid_snippet)
        # Assert
        # Assert
        assert mermaid_snippet in html

    def test_contains_mermaid_script_tag(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._templates import get_html_template

        # Act
        # Act
        html = get_html_template("T", "graph TD")
        # Assert
        # Assert
        assert "mermaid" in html.lower()

    def test_contains_timestamp_generated_at_in_html(self):
        """HTML footer must include a timestamp."""
        # Arrange
        from scitex_clew._viz._templates import get_html_template

        # Act
        html = get_html_template("T", "graph TD")
        # Generated at: YYYY-MM-DD ...
        # Assert
        assert "Generated at:" in html

    def test_title_injection_safety(self):
        """Title appears in <title> and <h1>."""
        # Arrange
        from scitex_clew._viz._templates import get_html_template

        # Act
        html = get_html_template("Test Title", "graph TD")
        # Assert
        assert html.count("Test Title") >= 2  # At least <title> and <h1>


# ===========================================================================
# _json.py  — pure helper functions (no DB access)
# ===========================================================================


class TestFormatPath:
    """format_path converts a filesystem path to display string."""

    def test_name_mode_returns_basename(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import format_path

        # Act
        # Act
        result = format_path("/home/user/data/results.csv", "name")
        # Assert
        # Assert
        assert result == "results.csv"

    def test_absolute_mode_returns_resolved_path_result_startswith(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._json import format_path
        # Act
        # Act
        result = format_path("/tmp/data/output.csv", "absolute")
        # Act
        # Assert
        # Assert
        # Assert
        assert result.startswith("/")

    def test_absolute_mode_returns_resolved_path_output_csv_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._json import format_path
        # Act
        # Act
        result = format_path("/tmp/data/output.csv", "absolute")
        # Act
        # Assert
        # Assert
        # Assert
        assert "output.csv" in result


    def test_relative_mode_with_unresolvable_path_result_is_str(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._json import format_path
        # Act
        # Act
        result = format_path("/some/deeply/nested/file.csv", "relative")
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_relative_mode_with_unresolvable_path_file_csv_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._json import format_path
        # Act
        # Act
        result = format_path("/some/deeply/nested/file.csv", "relative")
        # Act
        # Assert
        # Assert
        # Assert
        assert "file.csv" in result


    def test_unknown_path_returns_unknown(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import format_path

        # Act
        # Act
        result = format_path("unknown", "name")
        # Assert
        # Assert
        assert result == "unknown"

    def test_empty_path_returns_unknown(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import format_path

        # Act
        # Act
        result = format_path("", "name")
        # Assert
        # Assert
        assert result == "unknown"

    def test_name_mode_with_no_directory(self):
        """Bare filename still works."""
        # Arrange
        from scitex_clew._viz._json import format_path

        # Act
        result = format_path("file.txt", "name")
        # Assert
        assert result == "file.txt"


class TestFileToNodeId:
    """file_to_node_id produces stable, valid Mermaid node identifiers."""

    def test_starts_with_file_prefix(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import file_to_node_id

        # Act
        # Act
        node_id = file_to_node_id("/data/results.csv")
        # Assert
        # Assert
        assert node_id.startswith("file_")

    def test_same_path_same_id(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import file_to_node_id

        id1 = file_to_node_id("/data/results.csv")
        # Act
        # Act
        id2 = file_to_node_id("/data/results.csv")
        # Assert
        # Assert
        assert id1 == id2

    def test_different_paths_different_ids(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import file_to_node_id

        id1 = file_to_node_id("/data/a.csv")
        # Act
        # Act
        id2 = file_to_node_id("/data/b.csv")
        # Assert
        # Assert
        assert id1 != id2

    def test_dots_replaced_with_underscores(self):
        """Node IDs must not contain dots (invalid Mermaid syntax)."""
        # Arrange
        from scitex_clew._viz._json import file_to_node_id

        # Act
        node_id = file_to_node_id("/data/my.data.csv")
        # Should not contain bare dots in the name portion
        # The hash suffix guarantees uniqueness; check the name part only
        # Assert
        assert "." not in node_id

    def test_hyphens_replaced_with_underscores(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import file_to_node_id

        # Act
        # Act
        node_id = file_to_node_id("/data/my-file.csv")
        # After replacing hyphens we should not see '-' in the name segment
        # Assert
        # Assert
        assert "-" not in node_id

    def test_spaces_replaced_with_underscores(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import file_to_node_id

        # Act
        # Act
        node_id = file_to_node_id("/data/my file.csv")
        # Assert
        # Assert
        assert " " not in node_id

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import file_to_node_id

        # Act
        # Act
        result = file_to_node_id("/path/to/file.csv")
        # Assert
        # Assert
        assert isinstance(result, str)


class TestVerifyFileHash:
    """verify_file_hash checks file existence and hash equality."""

    def test_returns_false_for_missing_file(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import verify_file_hash

        missing = tmp_path / "no_such_file.txt"
        # Act
        # Act
        result = verify_file_hash(str(missing), "anyhash")
        # Assert
        # Assert
        assert result is False

    def test_returns_true_for_correct_hash(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._hash import hash_file
        from scitex_clew._viz._json import verify_file_hash

        f = tmp_path / "data.txt"
        f.write_text("hello world")
        # Act
        # Act
        correct_hash = hash_file(str(f))
        # Assert
        # Assert
        assert verify_file_hash(str(f), correct_hash) is True

    def test_returns_false_for_wrong_hash(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import verify_file_hash

        f = tmp_path / "data.txt"
        # Act
        # Act
        f.write_text("hello world")
        # Assert
        # Assert
        assert verify_file_hash(str(f), "0000000000000000") is False


class TestGenerateDagJsonEmptyChain:
    """generate_dag_json with no session/target returns empty-graph structure."""

    def test_no_args_returns_dict_with_required_keys_nodes_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._json import generate_dag_json
        # Act
        # Act
        from scitex_clew import _db as _db_mod
        fake_db = _FakeDB()
        with _swap_attr(_db_mod, "get_db", lambda: fake_db):
            result = generate_dag_json()
        # Act
        # Assert
        # Assert
        # Assert
        assert "nodes" in result

    def test_no_args_returns_dict_with_required_keys_links_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._json import generate_dag_json
        # Act
        # Act
        from scitex_clew import _db as _db_mod
        fake_db = _FakeDB()
        with _swap_attr(_db_mod, "get_db", lambda: fake_db):
            result = generate_dag_json()
        # Act
        # Assert
        # Assert
        # Assert
        assert "links" in result

    def test_no_args_returns_dict_with_required_keys_metadata_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._json import generate_dag_json
        # Act
        # Act
        from scitex_clew import _db as _db_mod
        fake_db = _FakeDB()
        with _swap_attr(_db_mod, "get_db", lambda: fake_db):
            result = generate_dag_json()
        # Act
        # Assert
        # Assert
        # Assert
        assert "metadata" in result


    def test_empty_chain_returns_empty_nodes_and_links_result_nodes(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._json import generate_dag_json
        # Act
        # Act
        from scitex_clew import _db as _db_mod
        fake_db = _FakeDB()
        with _swap_attr(_db_mod, "get_db", lambda: fake_db):
            result = generate_dag_json(session_id="nonexistent_sess")
        # Act
        # Assert
        # Assert
        # Assert
        assert result["nodes"] == []

    def test_empty_chain_returns_empty_nodes_and_links_result_links(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._json import generate_dag_json
        # Act
        # Act
        from scitex_clew import _db as _db_mod
        fake_db = _FakeDB()
        with _swap_attr(_db_mod, "get_db", lambda: fake_db):
            result = generate_dag_json(session_id="nonexistent_sess")
        # Act
        # Assert
        # Assert
        # Assert
        assert result["links"] == []


    def test_metadata_contains_generated_at(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import generate_dag_json

        # Act
        # Act
        from scitex_clew import _db as _db_mod
        fake_db = _FakeDB()
        with _swap_attr(_db_mod, "get_db", lambda: fake_db):

            result = generate_dag_json(session_id="nonexistent_sess")

        # Assert
        # Assert
        assert "generated_at" in result["metadata"]

    def test_metadata_empty_flag_set_when_chain_empty(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._json import generate_dag_json

        # Act
        # Act
        from scitex_clew import _db as _db_mod
        fake_db = _FakeDB()
        with _swap_attr(_db_mod, "get_db", lambda: fake_db):

            result = generate_dag_json(session_id="nonexistent_sess")

        # Assert
        # Assert
        assert result["metadata"].get("empty") is True


# ===========================================================================
# _mermaid_nodes.py
# ===========================================================================


class TestGetFileIcon:
    """get_file_icon maps file extensions to emoji strings."""

    def test_python_file_returns_snake_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("script.py")
        # Assert
        # Assert
        assert icon == "🐍"

    def test_csv_file_returns_chart_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("data.csv")
        # Assert
        # Assert
        assert icon == "📊"

    def test_json_file_returns_clipboard_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("config.json")
        # Assert
        # Assert
        assert icon == "📋"

    def test_yaml_file_returns_gear_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("params.yaml")
        # Assert
        # Assert
        assert icon == "⚙️"

    def test_yml_file_returns_gear_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("params.yml")
        # Assert
        # Assert
        assert icon == "⚙️"

    def test_png_file_returns_image_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("plot.png")
        # Assert
        # Assert
        assert icon == "🖼️"

    def test_pdf_file_returns_document_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("report.pdf")
        # Assert
        # Assert
        assert icon == "📄"

    def test_unknown_extension_returns_default_document_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("file.xyz")
        # Assert
        # Assert
        assert icon == "📄"

    def test_no_extension_returns_default_document_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("Makefile")
        # Assert
        # Assert
        assert icon == "📄"

    def test_npy_file_returns_number_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("array.npy")
        # Assert
        # Assert
        assert icon == "🔢"

    def test_pkl_file_returns_package_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("model.pkl")
        # Assert
        # Assert
        assert icon == "📦"

    def test_h5_file_returns_disk_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("data.h5")
        # Assert
        # Assert
        assert icon == "💾"

    def test_sh_file_returns_terminal_emoji(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        # Act
        icon = get_file_icon("run.sh")
        # Assert
        # Assert
        assert icon == "🖥️"

    def test_case_insensitive_extension_match(self):
        """Extension lookup must be case-insensitive (.CSV -> 📊)."""
        # Arrange
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        # Act
        icon = get_file_icon("DATA.CSV")
        # Assert
        assert icon == "📊"


class TestAppendClassDefinitions:
    """append_class_definitions adds all required Mermaid classDef blocks."""

    def _get_class_defs(self) -> list:
        from scitex_clew._viz._mermaid_nodes import append_class_definitions

        lines = []
        append_class_definitions(lines)
        return lines

    def test_appends_multiple_lines(self):
        # Arrange
        # Act
        # Arrange
        # Act
        lines = self._get_class_defs()
        # Assert
        # Assert
        assert len(lines) > 0

    def test_contains_script_classdef(self):
        # Arrange
        # Arrange
        lines = self._get_class_defs()
        # Act
        # Act
        combined = "\n".join(lines)
        # Assert
        # Assert
        assert "classDef script" in combined

    def test_contains_verified_classdef(self):
        # Arrange
        # Arrange
        lines = self._get_class_defs()
        # Act
        # Act
        combined = "\n".join(lines)
        # Assert
        # Assert
        assert "classDef verified" in combined

    def test_contains_failed_classdef(self):
        # Arrange
        # Arrange
        lines = self._get_class_defs()
        # Act
        # Act
        combined = "\n".join(lines)
        # Assert
        # Assert
        assert "classDef failed" in combined

    def test_contains_file_classdef(self):
        # Arrange
        # Arrange
        lines = self._get_class_defs()
        # Act
        # Act
        combined = "\n".join(lines)
        # Assert
        # Assert
        assert "classDef file" in combined

    def test_contains_fill_color_specs(self):
        # Arrange
        # Arrange
        lines = self._get_class_defs()
        # Act
        # Act
        combined = "\n".join(lines)
        # Assert
        # Assert
        assert "fill:" in combined

    def test_all_expected_classdefs_present(self):
        """All eight class names from the source must appear."""
        # Arrange
        expected_classes = {
            "script",
            "verified",
            "verified_scratch",
            "failed",
            "file",
            "file_ok",
            "file_rerun",
            "file_bad",
        }
        lines = self._get_class_defs()
        # Act
        combined = "\n".join(lines)
        # Assert
        assert all(f'classDef {cls}' in combined for cls in expected_classes), f'Missing classDef {cls}'


class TestAddScriptNode:
    """add_script_node inserts a correctly formatted Mermaid node line."""

    def _make_verification(self, verified=True, from_scratch=False):
        level = VerificationLevel.RERUN if from_scratch else VerificationLevel.CACHE
        status = (
            VerificationStatus.VERIFIED if verified else VerificationStatus.MISMATCH
        )
        return _make_run_verification(status=status, level=level)

    def _make_run_dict(self, script_path="/scripts/run.py", script_hash="deadbeef"):
        return {"script_path": script_path, "script_hash": script_hash}

    def test_verified_node_uses_verified_class_len_lines_is_1(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node
        lines = []
        verification = self._make_verification(verified=True, from_scratch=False)
        run = self._make_run_dict()
        # Act
        # Act
        add_script_node(lines, 0, "sess_001", run, verification, "name")
        # Act
        # Assert
        # Assert
        # Assert
        assert len(lines) == 1

    def test_verified_node_uses_verified_class_verified_in_lines_0(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node
        lines = []
        verification = self._make_verification(verified=True, from_scratch=False)
        run = self._make_run_dict()
        # Act
        # Act
        add_script_node(lines, 0, "sess_001", run, verification, "name")
        # Act
        # Assert
        # Assert
        # Assert
        assert ":::verified" in lines[0]


    def test_verified_from_scratch_uses_verified_scratch_class(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification(verified=True, from_scratch=True)
        run = self._make_run_dict()
        # Act
        # Act
        add_script_node(lines, 0, "sess_001", run, verification, "name")
        # Assert
        # Assert
        assert ":::verified_scratch" in lines[0]

    def test_failed_node_uses_failed_class(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification(verified=False)
        run = self._make_run_dict()
        # Act
        # Act
        add_script_node(lines, 0, "sess_001", run, verification, "name")
        # Assert
        # Assert
        assert ":::failed" in lines[0]

    def test_failed_input_overrides_verified_to_failed(self):
        """A verified script with a failed upstream input becomes failed."""
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification(verified=True)
        run = self._make_run_dict()
        # Act
        add_script_node(
            lines, 0, "sess_001", run, verification, "name", has_failed_input=True
        )
        # Assert
        assert ":::failed" in lines[0]

    def test_node_id_uses_script_index(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        run = self._make_run_dict()
        # Act
        # Act
        add_script_node(lines, 3, "sess_001", run, verification, "name")
        # Assert
        # Assert
        assert lines[0].strip().startswith("script_3")

    def test_script_name_appears_in_node(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        run = self._make_run_dict(script_path="/scripts/analyse.py")
        # Act
        # Act
        add_script_node(lines, 0, "sess_001", run, verification, "name")
        # Assert
        # Assert
        assert "analyse.py" in lines[0]

    def test_hash_display_when_show_hashes_true(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        run = self._make_run_dict(script_hash="cafebabe99887766")
        # Act
        # Act
        add_script_node(
            lines, 0, "sess_001", run, verification, "name", show_hashes=True
        )
        # First 8 chars of hash should appear
        # Assert
        # Assert
        assert "cafebabe" in lines[0]

    def test_no_hash_display_when_show_hashes_false(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        run = self._make_run_dict(script_hash="cafebabe99887766")
        # Act
        # Act
        add_script_node(
            lines, 0, "sess_001", run, verification, "name", show_hashes=False
        )
        # Assert
        # Assert
        assert "cafebabe" not in lines[0]

    def test_none_run_dict_produces_unknown_label(self):
        """When run is None, the node label uses 'unknown'."""
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        # Act
        add_script_node(lines, 0, "sess_001", None, verification, "name")
        # Assert
        assert "unknown" in lines[0]


class TestAddFileNodes:
    """add_file_nodes adds file node declarations and edge lines."""

    def test_adds_node_for_each_file(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        # Create real files so verify_file_hash returns True
        f1 = tmp_path / "data.csv"
        f1.write_text("a,b\n1,2")
        from scitex_clew._hash import hash_file

        h1 = hash_file(str(f1))

        lines = []
        file_nodes = {}
        # Act
        # Act
        add_file_nodes(
            lines,
            "script_0",
            {str(f1): h1},
            file_nodes,
            show_hashes=False,
            path_mode="name",
            role="input",
        )
        # One node declaration + one edge
        # Assert
        # Assert
        assert len(lines) == 2

    def test_input_role_creates_arrow_to_script(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        f = tmp_path / "input.csv"
        f.write_text("x")
        from scitex_clew._hash import hash_file

        h = hash_file(str(f))

        lines = []
        file_nodes = {}
        add_file_nodes(
            lines,
            "script_0",
            {str(f): h},
            file_nodes,
            show_hashes=False,
            path_mode="name",
            role="input",
        )
        # Act
        # Act
        edge_line = lines[-1]
        # Assert
        # Assert
        assert "--> script_0" in edge_line

    def test_output_role_creates_arrow_from_script(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        f = tmp_path / "output.csv"
        f.write_text("result")
        from scitex_clew._hash import hash_file

        h = hash_file(str(f))

        lines = []
        file_nodes = {}
        add_file_nodes(
            lines,
            "script_0",
            {str(f): h},
            file_nodes,
            show_hashes=False,
            path_mode="name",
            role="output",
        )
        # Act
        # Act
        edge_line = lines[-1]
        # Assert
        # Assert
        assert "script_0 -->" in edge_line

    def test_duplicate_file_path_adds_only_one_node_decl(self, tmp_path):
        """When the same file appears twice it must only be declared once."""
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        f = tmp_path / "shared.csv"
        f.write_text("data")
        from scitex_clew._hash import hash_file

        h = hash_file(str(f))

        lines = []
        file_nodes = {}
        # First call – declares node + edge
        add_file_nodes(
            lines,
            "script_0",
            {str(f): h},
            file_nodes,
            show_hashes=False,
            path_mode="name",
            role="input",
        )
        first_len = len(lines)
        # Second call with same file – only edge should be added
        # Act
        add_file_nodes(
            lines,
            "script_1",
            {str(f): h},
            file_nodes,
            show_hashes=False,
            path_mode="name",
            role="input",
        )
        # Assert
        assert len(lines) == first_len + 1  # only the edge line added

    def test_failed_file_uses_file_bad_class(self):
        """A file whose hash doesn't exist on disk gets file_bad class."""
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        lines = []
        file_nodes = {}
        add_file_nodes(
            lines,
            "script_0",
            {"/nonexistent/file.csv": "deadbeef"},
            file_nodes,
            show_hashes=False,
            path_mode="name",
            role="output",
        )
        # Act
        node_line = lines[0]
        # Assert
        assert ":::file_bad" in node_line

    def test_verified_output_without_rerun_uses_file_ok_class(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        f = tmp_path / "ok.csv"
        f.write_text("ok")
        from scitex_clew._hash import hash_file

        h = hash_file(str(f))

        lines = []
        file_nodes = {}
        # Act
        # Act
        add_file_nodes(
            lines,
            "script_0",
            {str(f): h},
            file_nodes,
            show_hashes=False,
            path_mode="name",
            role="output",
            is_script_rerun_verified=False,
        )
        # Assert
        # Assert
        assert ":::file_ok" in lines[0]

    def test_verified_output_with_rerun_uses_file_rerun_class(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        f = tmp_path / "rerun.csv"
        f.write_text("data")
        from scitex_clew._hash import hash_file

        h = hash_file(str(f))

        lines = []
        file_nodes = {}
        # Act
        # Act
        add_file_nodes(
            lines,
            "script_0",
            {str(f): h},
            file_nodes,
            show_hashes=False,
            path_mode="name",
            role="output",
            is_script_rerun_verified=True,
        )
        # Assert
        # Assert
        assert ":::file_rerun" in lines[0]


# ===========================================================================
# _mermaid_dag.py — pure-logic helpers (no DB/filesystem needed for
#                   generate_simple_dag and generate_multi_target_dag empty path)
# ===========================================================================


class TestGenerateSimpleDag:
    """generate_simple_dag emits one node line per run and edges between them."""

    def _make_runs_data(self, session_ids, verified=True):
        runs_data = []
        status = (
            VerificationStatus.VERIFIED if verified else VerificationStatus.MISMATCH
        )
        for sid in session_ids:
            run = {"script_path": f"/scripts/{sid}.py", "script_hash": "abc"}
            verification = _make_run_verification(session_id=sid, status=status)
            runs_data.append(
                {
                    "session_id": sid,
                    "run": run,
                    "verification": verification,
                    "inputs": {},
                    "outputs": {},
                }
            )
        return runs_data

    def test_single_run_produces_one_node_no_edge_len_lines_is_1(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_simple_dag
        runs_data = self._make_runs_data(["sess_a"])
        lines = []
        # Act
        # Act
        generate_simple_dag(lines, runs_data, ["sess_a"])
        # Act
        # Assert
        # Assert
        # Assert
        assert len(lines) == 1

    def test_single_run_produces_one_node_no_edge_not_in_lines_0(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_simple_dag
        runs_data = self._make_runs_data(["sess_a"])
        lines = []
        # Act
        # Act
        generate_simple_dag(lines, runs_data, ["sess_a"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "-->" not in lines[0]


    def test_two_runs_produces_node_and_edge_len_lines_is_3(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_simple_dag
        sids = ["sess_a", "sess_b"]
        runs_data = self._make_runs_data(sids)
        lines = []
        # Act
        # Act
        generate_simple_dag(lines, runs_data, sids)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(lines) == 3

    def test_two_runs_produces_node_and_edge_any_in_l_for_l_in_lines(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_simple_dag
        sids = ["sess_a", "sess_b"]
        runs_data = self._make_runs_data(sids)
        lines = []
        # Act
        # Act
        generate_simple_dag(lines, runs_data, sids)
        # Act
        # Assert
        # Assert
        # Assert
        assert any("-->" in l for l in lines)


    def test_verified_run_uses_verified_class(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        runs_data = self._make_runs_data(["sess_ok"], verified=True)
        lines = []
        # Act
        # Act
        generate_simple_dag(lines, runs_data, ["sess_ok"])
        # Assert
        # Assert
        assert ":::verified" in lines[0]

    def test_failed_run_uses_failed_class(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        runs_data = self._make_runs_data(["sess_bad"], verified=False)
        lines = []
        # Act
        # Act
        generate_simple_dag(lines, runs_data, ["sess_bad"])
        # Assert
        # Assert
        assert ":::failed" in lines[0]

    def test_script_name_appears_in_node_label(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        sids = ["sess_x"]
        runs_data = self._make_runs_data(sids)
        # Override script path to a distinctive name
        runs_data[0]["run"]["script_path"] = "/path/distinctive_script.py"
        lines = []
        # Act
        # Act
        generate_simple_dag(lines, runs_data, sids)
        # Assert
        # Assert
        assert "distinctive_script.py" in lines[0]

    def test_hyphens_in_session_id_replaced(self):
        """Session IDs with hyphens must become valid Mermaid node ids."""
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        sids = ["sess-with-hyphens"]
        runs_data = self._make_runs_data(sids)
        lines = []
        # Act
        generate_simple_dag(lines, runs_data, sids)
        # Assert
        assert "-" not in lines[0].split("[")[0]


class TestGenerateMultiTargetDagNoTargets:
    """generate_multi_target_dag with no targets/claims returns empty diagram."""

    def test_no_targets_no_claims_returns_mermaid_string(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_multi_target_dag

        # Act
        # Act
        result = generate_multi_target_dag(target_files=None, claims=False)
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_no_targets_contains_graph_td(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_multi_target_dag

        # Act
        # Act
        result = generate_multi_target_dag(target_files=None, claims=False)
        # Assert
        # Assert
        assert "graph TD" in result

    def test_no_targets_contains_no_targets_message(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid_dag import generate_multi_target_dag

        # Act
        # Act
        result = generate_multi_target_dag(target_files=None, claims=False)
        # Assert
        # Assert
        assert "No targets specified" in result


# ===========================================================================
# _mermaid.py
# ===========================================================================


class TestGenerateMermaidDagEmpty:
    """generate_mermaid_dag with an empty database returns valid Mermaid."""

    def _patched_empty_db(self):
        """Return a fake DB that holds no runs."""
        return _FakeDB(list_runs=[], get_chain=[])

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        # Act
        # Act
        from scitex_clew._viz import _mermaid as _mermaid_mod
        _fake_db_val = self._patched_empty_db()
        with _swap_attr(_mermaid_mod, "get_db", lambda: _fake_db_val):
            result = generate_mermaid_dag()
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_starts_with_graph_td(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        # Act
        # Act
        from scitex_clew._viz import _mermaid as _mermaid_mod
        _fake_db_val = self._patched_empty_db()
        with _swap_attr(_mermaid_mod, "get_db", lambda: _fake_db_val):
            result = generate_mermaid_dag()
        # Assert
        # Assert
        assert result.startswith("graph TD")

    def test_empty_db_produces_no_runs_found_message(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        # Act
        # Act
        from scitex_clew._viz import _mermaid as _mermaid_mod
        _fake_db_val = self._patched_empty_db()
        with _swap_attr(_mermaid_mod, "get_db", lambda: _fake_db_val):
            result = generate_mermaid_dag()
        # Assert
        # Assert
        assert "No runs found" in result

    def test_no_targets_claims_invokes_multi_target_once(self):
        """When claims=True the multi-target path is taken."""
        # Arrange
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        from scitex_clew._viz import _mermaid as _mermaid_mod
        _multi_calls = []
        def _fake_multi(*a, **kw):
            _multi_calls.append((a, kw))
            return 'graph TD\n    empty["No runs found"]'
        # Act
        with _swap_attr(_mermaid_mod, "generate_multi_target_dag", _fake_multi):
            generate_mermaid_dag(claims=True)
        # Assert
        assert len(_multi_calls) == 1

    def test_no_targets_claims_returns_string(self):
        """When claims=True the multi-target path returns a string."""
        # Arrange
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        from scitex_clew._viz import _mermaid as _mermaid_mod
        def _fake_multi(*a, **kw):
            return 'graph TD\n    empty["No runs found"]'
        # Act
        with _swap_attr(_mermaid_mod, "generate_multi_target_dag", _fake_multi):
            result = generate_mermaid_dag(claims=True)
        # Assert
        assert isinstance(result, str)

    def test_target_files_calls_generate_multi_target(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        from scitex_clew._viz import _mermaid as _mermaid_mod
        _multi_calls = []
        def _fake_multi(*a, **kw):
            _multi_calls.append((a, kw))
            return 'graph TD\n    empty["No runs found"]'
        with _swap_attr(_mermaid_mod, "generate_multi_target_dag", _fake_multi):
            result = generate_mermaid_dag(target_files=["/some/file.csv"])
        assert len(_multi_calls) == 1


class TestGenerateHtmlDag:
    """generate_html_dag wraps Mermaid output in a complete HTML document."""

    def _mock_mermaid_output(self):
        return "graph TD\n    A --> B"

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import generate_html_dag

        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid_output()):
            result = generate_html_dag()
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_contains_doctype_doctype_html_in_result(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import generate_html_dag

        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid_output()):
            result = generate_html_dag()
        # Assert
        # Assert
        assert "<!DOCTYPE html>" in result

    def test_custom_title_appears_in_output(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import generate_html_dag

        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid_output()):
            result = generate_html_dag(title="Custom Title")
        # Assert
        # Assert
        assert "Custom Title" in result

    def test_mermaid_code_embedded_in_html(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import generate_html_dag

        mermaid_code = "graph TD\n    A --> B"
        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: mermaid_code):
            result = generate_html_dag()
        # Assert
        # Assert
        assert mermaid_code in result


class TestRenderDag:
    """render_dag writes correctly formatted output to the specified file."""

    def _mock_mermaid(self):
        return "graph TD\n    A --> B"

    def _mock_html(self):
        return "<!DOCTYPE html><html><body>test</body></html>"

    def test_render_to_mmd_file_result_equals_out(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.mmd"
        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid()):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert result == out

    def test_render_to_mmd_file_out_exists(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.mmd"
        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid()):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert out.exists()

    def test_render_to_mmd_file_graph_td_in_content_result_equals_out(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.mmd"
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid()):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert result == out

    def test_render_to_mmd_file_graph_td_in_content_out_exists(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.mmd"
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid()):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert out.exists()

    def test_render_to_mmd_file_graph_td_in_content_graph_td_in_content(self, tmp_path):
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.mmd"
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid()):
            render_dag(out)
        content = out.read_text() if out.exists() else ""
        # Assert
        assert "graph TD" in content



    def test_render_to_html_file_result_equals_out(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.html"
        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_html_dag", lambda *a, **kw: self._mock_html()):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert result == out

    def test_render_to_html_file_out_exists(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.html"
        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_html_dag", lambda *a, **kw: self._mock_html()):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert out.exists()

    def test_render_to_html_file_doctype_html_in_content_result_equals_out(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.html"
        # Act
        with _swap_attr(_mermaid_mod, "generate_html_dag", lambda *a, **kw: self._mock_html()):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert result == out

    def test_render_to_html_file_doctype_html_in_content_out_exists(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.html"
        # Act
        with _swap_attr(_mermaid_mod, "generate_html_dag", lambda *a, **kw: self._mock_html()):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert out.exists()

    def test_render_to_html_file_doctype_html_in_content_doctype_html_in_content(self, tmp_path):
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.html"
        # Act
        with _swap_attr(_mermaid_mod, "generate_html_dag", lambda *a, **kw: self._mock_html()):
            render_dag(out)
        content = out.read_text() if out.exists() else ""
        # Assert
        assert "<!DOCTYPE html>" in content



    def test_render_to_json_file_result_equals_out(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert result == out

    def test_render_to_json_file_out_exists(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert out.exists()

    def test_render_to_json_file_nodes_in_parsed_result_equals_out(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert result == out

    def test_render_to_json_file_nodes_in_parsed_out_exists(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert out.exists()

    def test_render_to_json_file_nodes_in_parsed_nodes_in_parsed(self, tmp_path):
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            render_dag(out)
        parsed = json.loads(out.read_text()) if out.exists() else {}
        # Assert
        assert "nodes" in parsed


    def test_render_to_json_file_links_in_parsed_result_equals_out(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert result == out

    def test_render_to_json_file_links_in_parsed_out_exists(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert out.exists()

    def test_render_to_json_file_links_in_parsed_links_in_parsed(self, tmp_path):
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            render_dag(out)
        parsed = json.loads(out.read_text()) if out.exists() else {}
        # Assert
        assert "links" in parsed


    def test_render_to_json_file_metadata_in_parsed_result_equals_out(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert result == out

    def test_render_to_json_file_metadata_in_parsed_out_exists(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        assert out.exists()

    def test_render_to_json_file_metadata_in_parsed_metadata_in_parsed(self, tmp_path):
        # Arrange
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        # Act
        with _swap_attr(_mermaid_mod, "generate_dag_json", lambda *a, **kw: fake_graph):
            render_dag(out)
        parsed = json.loads(out.read_text()) if out.exists() else {}
        # Assert
        assert "metadata" in parsed



    def test_render_creates_parent_dirs(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag

        out = tmp_path / "nested" / "deep" / "diagram.mmd"
        # Act
        # Act
        with _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid()):
            render_dag(out)
        # Assert
        # Assert
        assert out.exists()

    def test_render_unsupported_format_raises_value_error(self, tmp_path):
        # Arrange
        # Arrange
        from scitex_clew._viz._mermaid import render_dag

        # Act
        # Act
        out = tmp_path / "diagram.xyz"
        # Assert
        # Assert
        with pytest.raises(ValueError, match="Unsupported format"):
            render_dag(out)

    def test_render_to_png_falls_back_to_mmd_when_mmdc_missing_result_suffix_equals_mmd(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        import subprocess

        from scitex_clew._viz import _mermaid as _mermaid_mod
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.png"

        def _raise_not_found(*args, **kwargs):
            raise FileNotFoundError("mmdc not found")

        # Act
        # Act
        with (
            _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid()),
            _swap_attr(subprocess, "run", _raise_not_found),
        ):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert result.suffix == ".mmd"

    def test_render_to_png_falls_back_to_mmd_when_mmdc_missing_result_exists(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        import subprocess

        from scitex_clew._viz import _mermaid as _mermaid_mod
        from scitex_clew._viz._mermaid import render_dag
        out = tmp_path / "diagram.png"

        def _raise_not_found(*args, **kwargs):
            raise FileNotFoundError("mmdc not found")

        # Act
        # Act
        with (
            _swap_attr(_mermaid_mod, "generate_mermaid_dag", lambda *a, **kw: self._mock_mermaid()),
            _swap_attr(subprocess, "run", _raise_not_found),
        ):
            result = render_dag(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exists()



# ===========================================================================
# _format.py
# ===========================================================================


class TestFormatRunVerification:
    """format_run_verification produces a correctly structured text block."""

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification

        rv = _make_run_verification()
        # Act
        # Act
        result = format_run_verification(rv)
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_first_line_contains_session_id(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification

        rv = _make_run_verification(session_id="my_unique_session_42")
        # Act
        # Act
        result = format_run_verification(rv)
        # Assert
        # Assert
        assert "my_unique_session_42" in result.split("\n")[0]

    def test_first_line_contains_status_text(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification

        rv = _make_run_verification(status=VerificationStatus.VERIFIED)
        # Act
        # Act
        result = format_run_verification(rv)
        # Assert
        # Assert
        assert "verified" in result

    def test_script_path_appears_when_present_script_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        rv = _make_run_verification(script_path="/my/analysis.py")
        # Act
        # Act
        result = format_run_verification(rv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Script:" in result

    def test_script_path_appears_when_present_my_analysis_py_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        rv = _make_run_verification(script_path="/my/analysis.py")
        # Act
        # Act
        result = format_run_verification(rv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "/my/analysis.py" in result


    def test_no_script_path_when_none(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification

        rv = _make_run_verification(script_path=None)
        # Act
        # Act
        result = format_run_verification(rv)
        # Assert
        # Assert
        assert "Script:" not in result

    def test_verbose_mode_shows_inputs_inputs_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(path="/data/input.csv", role="input")
        rv = _make_run_verification(files=[fv])
        # Act
        # Act
        result = format_run_verification(rv, verbose=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Inputs:" in result

    def test_verbose_mode_shows_inputs_data_input_csv_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(path="/data/input.csv", role="input")
        rv = _make_run_verification(files=[fv])
        # Act
        # Act
        result = format_run_verification(rv, verbose=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert "/data/input.csv" in result


    def test_verbose_mode_shows_outputs_outputs_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(path="/data/output.csv", role="output")
        rv = _make_run_verification(files=[fv])
        # Act
        # Act
        result = format_run_verification(rv, verbose=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Outputs:" in result

    def test_verbose_mode_shows_outputs_data_output_csv_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(path="/data/output.csv", role="output")
        rv = _make_run_verification(files=[fv])
        # Act
        # Act
        result = format_run_verification(rv, verbose=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert "/data/output.csv" in result


    def test_non_verified_shows_mismatched_files_mismatched_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(
            path="/data/bad.csv",
            role="output",
            expected_hash="aabbcc112233445566",
            current_hash="000000000000000000",
            status=VerificationStatus.MISMATCH,
        )
        rv = _make_run_verification(status=VerificationStatus.MISMATCH, files=[fv])
        # Act
        # Act
        result = format_run_verification(rv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Mismatched:" in result

    def test_non_verified_shows_mismatched_files_data_bad_csv_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(
            path="/data/bad.csv",
            role="output",
            expected_hash="aabbcc112233445566",
            current_hash="000000000000000000",
            status=VerificationStatus.MISMATCH,
        )
        rv = _make_run_verification(status=VerificationStatus.MISMATCH, files=[fv])
        # Act
        # Act
        result = format_run_verification(rv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "/data/bad.csv" in result


    def test_non_verified_shows_missing_files_missing_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(
            path="/data/gone.csv",
            role="input",
            current_hash=None,
            status=VerificationStatus.MISSING,
        )
        rv = _make_run_verification(status=VerificationStatus.MISSING, files=[fv])
        # Act
        # Act
        result = format_run_verification(rv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Missing:" in result

    def test_non_verified_shows_missing_files_data_gone_csv_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(
            path="/data/gone.csv",
            role="input",
            current_hash=None,
            status=VerificationStatus.MISSING,
        )
        rv = _make_run_verification(status=VerificationStatus.MISSING, files=[fv])
        # Act
        # Act
        result = format_run_verification(rv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "/data/gone.csv" in result


    def test_verified_without_verbose_hides_files_inputs_not_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(path="/data/clean.csv", role="output")
        rv = _make_run_verification(status=VerificationStatus.VERIFIED, files=[fv])
        # Act
        # Act
        result = format_run_verification(rv, verbose=False)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Inputs:" not in result

    def test_verified_without_verbose_hides_files_outputs_not_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_verification
        fv = _make_file_verification(path="/data/clean.csv", role="output")
        rv = _make_run_verification(status=VerificationStatus.VERIFIED, files=[fv])
        # Act
        # Act
        result = format_run_verification(rv, verbose=False)
        # Act
        # Assert
        # Assert
        # Assert
        assert "Outputs:" not in result



class TestFormatRunDetailed:
    """format_run_detailed shows a tree with input/output icon strips."""

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_detailed

        rv = _make_run_verification()
        # Act
        # Act
        result = format_run_detailed(rv)
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_first_line_contains_session_id(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_detailed

        rv = _make_run_verification(session_id="detailed_sess_99")
        # Act
        # Act
        result = format_run_detailed(rv)
        # Assert
        # Assert
        assert "detailed_sess_99" in result.split("\n")[0]

    def test_inputs_line_contains_tree_prefix(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_detailed

        fv = _make_file_verification(role="input")
        rv = _make_run_verification(files=[fv])
        # Act
        # Act
        result = format_run_detailed(rv)
        # Assert
        # Assert
        assert "inputs:" in result

    def test_outputs_line_contains_tree_prefix(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_detailed

        fv = _make_file_verification(role="output")
        rv = _make_run_verification(files=[fv])
        # Act
        # Act
        result = format_run_detailed(rv)
        # Assert
        # Assert
        assert "outputs:" in result

    def test_script_basename_only_not_full_path_analysis_py_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_detailed
        rv = _make_run_verification(script_path="/very/deep/path/analysis.py")
        # Act
        # Act
        result = format_run_detailed(rv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "analysis.py" in result

    def test_script_basename_only_not_full_path_very_deep_path_not_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_run_detailed
        rv = _make_run_verification(script_path="/very/deep/path/analysis.py")
        # Act
        # Act
        result = format_run_detailed(rv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "/very/deep/path" not in result


    def test_failed_input_filename_highlighted_in_output(self):
        """A failed input file name should appear under the inputs section."""
        # Arrange
        from scitex_clew._viz._format import format_run_detailed

        bad_fv = _make_file_verification(
            path="/data/bad_input.csv",
            role="input",
            expected_hash="abc",
            current_hash="xyz",
            status=VerificationStatus.MISMATCH,
        )
        rv = _make_run_verification(files=[bad_fv])
        # Act
        result = format_run_detailed(rv)
        # Assert
        assert "bad_input.csv" in result


class TestFormatChainVerification:
    """format_chain_verification renders a tree for the entire chain."""

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification

        cv = _make_chain_verification()
        # Act
        # Act
        result = format_chain_verification(cv)
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_contains_target_file(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification

        cv = _make_chain_verification(target_file="/data/target.csv")
        # Act
        # Act
        result = format_chain_verification(cv)
        # Assert
        # Assert
        assert "/data/target.csv" in result

    def test_no_runs_shows_no_runs_found(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification

        cv = _make_chain_verification(runs=[])
        # Act
        # Act
        result = format_chain_verification(cv)
        # Assert
        # Assert
        assert "no runs found" in result

    def test_single_verified_run_shown_with_tree_prefix_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification
        run = _make_run_verification(session_id="sess_one")
        cv = _make_chain_verification(runs=[run])
        # Act
        # Act
        result = format_chain_verification(cv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "└──" in result

    def test_single_verified_run_shown_with_tree_prefix_sess_one_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification
        run = _make_run_verification(session_id="sess_one")
        cv = _make_chain_verification(runs=[run])
        # Act
        # Act
        result = format_chain_verification(cv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "sess_one" in result


    def test_multiple_runs_tree_structure_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification
        runs = [
            _make_run_verification(session_id="sess_first"),
            _make_run_verification(session_id="sess_second"),
        ]
        cv = _make_chain_verification(runs=runs)
        # Act
        # Act
        result = format_chain_verification(cv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "├──" in result

    def test_multiple_runs_tree_structure_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification
        runs = [
            _make_run_verification(session_id="sess_first"),
            _make_run_verification(session_id="sess_second"),
        ]
        cv = _make_chain_verification(runs=runs)
        # Act
        # Act
        result = format_chain_verification(cv)
        # Act
        # Assert
        # Assert
        # Assert
        assert "└──" in result


    def test_shows_script_name_for_runs_with_script(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification

        run = _make_run_verification(
            session_id="sess_x", script_path="/path/preprocess.py"
        )
        cv = _make_chain_verification(runs=[run])
        # Act
        # Act
        result = format_chain_verification(cv)
        # Assert
        # Assert
        assert "preprocess.py" in result

    def test_shows_mismatched_files_for_failed_run(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification

        bad_fv = _make_file_verification(
            path="/data/mismatch.csv",
            role="output",
            expected_hash="aaaa",
            current_hash="bbbb",
            status=VerificationStatus.MISMATCH,
        )
        run = _make_run_verification(
            session_id="sess_fail",
            status=VerificationStatus.MISMATCH,
            files=[bad_fv],
        )
        cv = _make_chain_verification(runs=[run], status=VerificationStatus.MISMATCH)
        # Act
        # Act
        result = format_chain_verification(cv)
        # Assert
        # Assert
        assert "mismatch.csv" in result

    def test_shows_missing_files_for_failed_run(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_chain_verification

        missing_fv = _make_file_verification(
            path="/data/missing.csv",
            role="output",
            current_hash=None,
            status=VerificationStatus.MISSING,
        )
        run = _make_run_verification(
            session_id="sess_missing",
            status=VerificationStatus.MISSING,
            files=[missing_fv],
        )
        cv = _make_chain_verification(runs=[run], status=VerificationStatus.MISSING)
        # Act
        # Act
        result = format_chain_verification(cv)
        # Assert
        # Assert
        assert "missing.csv" in result


class TestFormatStatus:
    """format_status renders a git-status-like summary from a dict."""

    def _make_status_dict(
        self,
        verified_count=3,
        mismatch_count=0,
        missing_count=0,
        mismatched=None,
        missing=None,
    ):
        return {
            "verified_count": verified_count,
            "mismatch_count": mismatch_count,
            "missing_count": missing_count,
            "mismatched": mismatched or [],
            "missing": missing or [],
        }

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status

        # Act
        # Act
        result = format_status(self._make_status_dict())
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_contains_total_runs_count(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status

        status = self._make_status_dict(
            verified_count=5, mismatch_count=1, missing_count=2
        )
        # Act
        # Act
        result = format_status(status)
        # Assert
        # Assert
        assert "8" in result  # total = 5+1+2

    def test_all_verified_shows_all_tracked_verified(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status

        # Act
        # Act
        result = format_status(self._make_status_dict(verified_count=5))
        # Assert
        # Assert
        assert "All tracked files verified" in result

    def test_mismatched_section_shown_when_present_sess_bad_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status
        mismatched = [{"session_id": "sess_bad", "files": ["/data/bad.csv"]}]
        status = self._make_status_dict(mismatch_count=1, mismatched=mismatched)
        # Act
        # Act
        result = format_status(status)
        # Act
        # Assert
        # Assert
        # Assert
        assert "sess_bad" in result

    def test_mismatched_section_shown_when_present_bad_csv_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status
        mismatched = [{"session_id": "sess_bad", "files": ["/data/bad.csv"]}]
        status = self._make_status_dict(mismatch_count=1, mismatched=mismatched)
        # Act
        # Act
        result = format_status(status)
        # Act
        # Assert
        # Assert
        # Assert
        assert "bad.csv" in result


    def test_missing_section_shown_when_present_sess_gone_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status
        missing = [{"session_id": "sess_gone", "files": ["/data/gone.csv"]}]
        status = self._make_status_dict(missing_count=1, missing=missing)
        # Act
        # Act
        result = format_status(status)
        # Act
        # Assert
        # Assert
        # Assert
        assert "sess_gone" in result

    def test_missing_section_shown_when_present_gone_csv_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status
        missing = [{"session_id": "sess_gone", "files": ["/data/gone.csv"]}]
        status = self._make_status_dict(missing_count=1, missing=missing)
        # Act
        # Act
        result = format_status(status)
        # Act
        # Assert
        # Assert
        # Assert
        assert "gone.csv" in result


    def test_more_than_three_files_truncated_with_ellipsis(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status

        files = [f"/data/file_{i}.csv" for i in range(6)]
        mismatched = [{"session_id": "sess_x", "files": files}]
        status = self._make_status_dict(mismatch_count=1, mismatched=mismatched)
        # Act
        # Act
        result = format_status(status)
        # Assert
        # Assert
        assert "more" in result

    def test_more_than_ten_mismatch_sessions_truncated(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status

        mismatched = [
            {"session_id": f"sess_{i}", "files": [f"/data/{i}.csv"]} for i in range(15)
        ]
        status = self._make_status_dict(mismatch_count=15, mismatched=mismatched)
        # Act
        # Act
        result = format_status(status)
        # Assert
        # Assert
        assert "more runs" in result

    def test_verified_count_appears_in_output(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status

        status = self._make_status_dict(verified_count=7)
        # Act
        # Act
        result = format_status(status)
        # Assert
        # Assert
        assert "7" in result

    def test_header_line_present(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_status

        # Act
        # Act
        result = format_status(self._make_status_dict())
        # Assert
        # Assert
        assert "Verification Status" in result


class TestFormatList:
    """format_list renders a table of run records without verification calls."""

    def _make_run_records(self, n=3):
        return [
            {
                "session_id": f"session_{i:03d}_abcdef",
                "script_path": f"/path/to/script_{i}.py",
                "status": "success",
            }
            for i in range(n)
        ]

    def test_returns_string_result_is_str_2(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_list

        # Act
        # Act
        result = format_list(self._make_run_records(), verify=False)
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_header_row_present_session_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_list
        # Act
        # Act
        result = format_list(self._make_run_records(), verify=False)
        # Act
        # Assert
        # Assert
        # Assert
        assert "SESSION" in result

    def test_header_row_present_status_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_list
        # Act
        # Act
        result = format_list(self._make_run_records(), verify=False)
        # Act
        # Assert
        # Assert
        # Assert
        assert "STATUS" in result

    def test_header_row_present_script_in_result(self):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_list
        # Act
        # Act
        result = format_list(self._make_run_records(), verify=False)
        # Act
        # Assert
        # Assert
        # Assert
        assert "SCRIPT" in result


    def test_each_session_id_appears_in_output(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_list

        records = self._make_run_records(3)
        # Act
        # Act
        result = format_list(records, verify=False)
        # Prefix of session IDs should appear
        # Assert
        # Assert
        assert all(rec['session_id'][:20] in result for rec in records)

    def test_script_basename_appears_in_output(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_list

        records = self._make_run_records(1)
        # Act
        # Act
        result = format_list(records, verify=False)
        # Assert
        # Assert
        assert "script_0.py" in result

    def test_empty_run_list_returns_header_only(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_list

        # Act
        # Act
        result = format_list([], verify=False)
        # Should at least contain header
        # Assert
        # Assert
        assert "SESSION" in result

    def test_very_long_session_id_truncated(self):
        """Session IDs longer than 45 chars should be truncated with '..'."""
        # Arrange
        from scitex_clew._viz._format import format_list

        long_id = "x" * 60
        records = [{"session_id": long_id, "script_path": "/s.py", "status": "ok"}]
        # Act
        result = format_list(records, verify=False)
        # Assert
        assert ".." in result

    def test_very_long_script_name_truncated(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_list

        long_script = "/path/" + "a" * 40 + ".py"
        records = [
            {
                "session_id": "sess_abc",
                "script_path": long_script,
                "status": "ok",
            }
        ]
        # Act
        # Act
        result = format_list(records, verify=False)
        # Assert
        # Assert
        assert ".." in result

    def test_no_script_path_shows_dash(self):
        # Arrange
        # Arrange
        from scitex_clew._viz._format import format_list

        records = [{"session_id": "sess_noscript", "status": "ok"}]
        # Act
        # Act
        result = format_list(records, verify=False)
        # Assert
        # Assert
        assert "-" in result


# ===========================================================================
# _utils.py
# ===========================================================================


class TestPrintVerificationSummary:
    """print_verification_summary writes counts to stdout."""

    def _build_run_records(self, statuses):
        """Return run record dicts and patch verify_run for each."""
        records = []
        verifications = {}
        for i, status in enumerate(statuses):
            sid = f"sess_{i:04d}"
            records.append({"session_id": sid})
            verifications[sid] = _make_run_verification(session_id=sid, status=status)
        return records, verifications

    def test_prints_verification_summary_header(self, capsys):
        # Arrange
        # Arrange
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records(
            [VerificationStatus.VERIFIED, VerificationStatus.VERIFIED]
        )
        with _swap_attr(_utils_mod, "verify_run", lambda sid: verifs[sid]):
            print_verification_summary(records)

        # Act
        # Act
        captured = capsys.readouterr()
        # Assert
        # Assert
        assert "Verification Summary" in captured.out

    def test_prints_verified_count(self, capsys):
        # Arrange
        # Arrange
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records(
            [
                VerificationStatus.VERIFIED,
                VerificationStatus.VERIFIED,
                VerificationStatus.MISMATCH,
            ]
        )
        with _swap_attr(_utils_mod, "verify_run", lambda sid: verifs[sid]):
            print_verification_summary(records)

        # Act
        # Act
        captured = capsys.readouterr()
        # Assert
        # Assert
        assert "2" in captured.out  # 2 verified

    def test_prints_mismatch_count(self, capsys):
        # Arrange
        # Arrange
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records(
            [VerificationStatus.MISMATCH, VerificationStatus.VERIFIED]
        )
        with _swap_attr(_utils_mod, "verify_run", lambda sid: verifs[sid]):
            print_verification_summary(records)

        # Act
        # Act
        captured = capsys.readouterr()
        # Assert
        # Assert
        assert "Mismatch" in captured.out

    def test_prints_missing_count(self, capsys):
        # Arrange
        # Arrange
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records([VerificationStatus.MISSING])
        with _swap_attr(_utils_mod, "verify_run", lambda sid: verifs[sid]):
            print_verification_summary(records)

        # Act
        # Act
        captured = capsys.readouterr()
        # Assert
        # Assert
        assert "Missing" in captured.out

    def test_show_all_true_prints_verified_runs_too(self, capsys):
        # Arrange
        # Arrange
        from scitex_clew._viz import _utils as _utils_mod
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records([VerificationStatus.VERIFIED])
        with (
            _swap_attr(_utils_mod, "verify_run", lambda sid: verifs[sid]),
            _swap_attr(_utils_mod, "format_run_detailed", lambda *a, **kw: "RUN_DETAIL_LINE"),
        ):
            print_verification_summary(records, show_all=True)

        # Act
        # Act
        captured = capsys.readouterr()
        # Assert
        # Assert
        assert "RUN_DETAIL_LINE" in captured.out

    def test_empty_run_list_prints_zeros(self, capsys):
        # Arrange
        # Arrange
        from scitex_clew._viz._utils import print_verification_summary

        print_verification_summary([])
        # Act
        # Act
        captured = capsys.readouterr()
        # Assert
        # Assert
        assert "0" in captured.out


# ===========================================================================
# __init__.py  —  public re-exports of viz symbols
# ===========================================================================


class TestVizInitExports:
    """The _viz package exposes its public symbols correctly."""

    def test_colors_importable_from_viz(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import Colors

        # Assert
        # Assert
        assert hasattr(Colors, "GREEN")

    def test_verification_level_importable_from_viz(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import VerificationLevel

        # Assert
        # Assert
        assert VerificationLevel.CACHE == "cache"

    def test_format_run_verification_importable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import format_run_verification

        # Assert
        # Assert
        assert callable(format_run_verification)

    def test_format_chain_verification_importable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import format_chain_verification

        # Assert
        # Assert
        assert callable(format_chain_verification)

    def test_format_status_importable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import format_status

        # Assert
        # Assert
        assert callable(format_status)

    def test_format_list_importable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import format_list

        # Assert
        # Assert
        assert callable(format_list)

    def test_format_run_detailed_importable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import format_run_detailed

        # Assert
        # Assert
        assert callable(format_run_detailed)

    def test_generate_mermaid_dag_importable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import generate_mermaid_dag

        # Assert
        # Assert
        assert callable(generate_mermaid_dag)

    def test_generate_html_dag_importable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import generate_html_dag

        # Assert
        # Assert
        assert callable(generate_html_dag)

    def test_render_dag_importable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import render_dag

        # Assert
        # Assert
        assert callable(render_dag)

    def test_print_verification_summary_importable(self):
        # Arrange
        # Act
        # Arrange
        # Act
        from scitex_clew._viz import print_verification_summary

        # Assert
        # Assert
        assert callable(print_verification_summary)

    def test_all_exports_are_callable_or_class(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        import scitex_clew._viz as viz_pkg

        for name in viz_pkg.__all__:
            obj = getattr(viz_pkg, name)
            assert callable(obj) or isinstance(obj, type), (
                f"{name} should be callable or a class"
            )


# EOF
