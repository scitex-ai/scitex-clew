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

import json
from unittest.mock import MagicMock, patch

import pytest

from scitex_clew import (
    ChainVerification,
    FileVerification,
    RunVerification,
    VerificationLevel,
    VerificationStatus,
)

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
        from scitex_clew._viz._colors import Colors

        assert Colors.GREEN.startswith("\033[")

    def test_red_is_ansi_escape(self):
        from scitex_clew._viz._colors import Colors

        assert Colors.RED.startswith("\033[")

    def test_yellow_is_ansi_escape(self):
        from scitex_clew._viz._colors import Colors

        assert Colors.YELLOW.startswith("\033[")

    def test_reset_is_ansi_escape(self):
        from scitex_clew._viz._colors import Colors

        assert Colors.RESET.startswith("\033[")

    def test_bold_is_ansi_escape(self):
        from scitex_clew._viz._colors import Colors

        assert Colors.BOLD.startswith("\033[")

    def test_all_color_attributes_exist(self):
        from scitex_clew._viz._colors import Colors

        for attr in ("GREEN", "RED", "YELLOW", "CYAN", "GRAY", "RESET", "BOLD"):
            assert hasattr(Colors, attr), f"Missing Colors.{attr}"


class TestVerificationLevelColors:
    """VerificationLevel in _colors is a plain class (not enum)."""

    def test_cache_value(self):
        from scitex_clew._viz._colors import VerificationLevel

        assert VerificationLevel.CACHE == "cache"

    def test_scratch_value(self):
        from scitex_clew._viz._colors import VerificationLevel

        assert VerificationLevel.SCRATCH == "scratch"


class TestStatusIcon:
    """status_icon returns a coloured bullet for each VerificationStatus."""

    def test_verified_contains_bullet(self):
        from scitex_clew._viz._colors import status_icon

        icon = status_icon(VerificationStatus.VERIFIED)
        assert "●" in icon

    def test_mismatch_contains_bullet(self):
        from scitex_clew._viz._colors import status_icon

        icon = status_icon(VerificationStatus.MISMATCH)
        assert "●" in icon

    def test_missing_contains_circle(self):
        from scitex_clew._viz._colors import status_icon

        icon = status_icon(VerificationStatus.MISSING)
        assert "○" in icon

    def test_unknown_contains_question_mark(self):
        from scitex_clew._viz._colors import status_icon

        icon = status_icon(VerificationStatus.UNKNOWN)
        assert "?" in icon

    def test_scratch_level_verified_gives_double_bullet(self):
        from scitex_clew._viz._colors import VerificationLevel, status_icon

        icon = status_icon(VerificationStatus.VERIFIED, level=VerificationLevel.SCRATCH)
        assert "●●" in icon

    def test_scratch_level_mismatch_gives_single_bullet(self):
        """SCRATCH level only doubles for VERIFIED; mismatch stays single."""
        from scitex_clew._viz._colors import VerificationLevel, status_icon

        icon = status_icon(VerificationStatus.MISMATCH, level=VerificationLevel.SCRATCH)
        assert "●●" not in icon
        assert "●" in icon

    def test_unknown_status_falls_back_to_question_mark(self):
        from scitex_clew._viz._colors import status_icon

        # Pass a sentinel that is not in the icons dict
        icon = status_icon("completely_unknown_value")
        assert icon == "?"


class TestStatusText:
    """status_text returns coloured text label for each status."""

    def test_verified_contains_word_verified(self):
        from scitex_clew._viz._colors import status_text

        text = status_text(VerificationStatus.VERIFIED)
        assert "verified" in text

    def test_mismatch_contains_word_mismatch(self):
        from scitex_clew._viz._colors import status_text

        text = status_text(VerificationStatus.MISMATCH)
        assert "mismatch" in text

    def test_missing_contains_word_missing(self):
        from scitex_clew._viz._colors import status_text

        text = status_text(VerificationStatus.MISSING)
        assert "missing" in text

    def test_unknown_status_falls_back_to_unknown(self):
        from scitex_clew._viz._colors import status_text

        text = status_text("not_a_real_status")
        assert text == "unknown"


# ===========================================================================
# _templates.py
# ===========================================================================


class TestGetTimestamp:
    """get_timestamp returns a correctly formatted string."""

    def test_returns_string(self):
        from scitex_clew._viz._templates import get_timestamp

        ts = get_timestamp()
        assert isinstance(ts, str)

    def test_format_YYYY_MM_DD_HH_MM_SS(self):
        """Timestamp must match 'YYYY-MM-DD HH:MM:SS'."""
        import re

        from scitex_clew._viz._templates import get_timestamp

        ts = get_timestamp()
        pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        assert re.match(pattern, ts), f"Timestamp '{ts}' doesn't match expected format"


class TestGetHtmlTemplate:
    """get_html_template produces a complete HTML document."""

    def test_returns_string(self):
        from scitex_clew._viz._templates import get_html_template

        html = get_html_template("My Title", "graph TD\n    A --> B")
        assert isinstance(html, str)

    def test_contains_doctype(self):
        from scitex_clew._viz._templates import get_html_template

        html = get_html_template("T", "graph TD")
        assert "<!DOCTYPE html>" in html

    def test_contains_title(self):
        from scitex_clew._viz._templates import get_html_template

        html = get_html_template("Pipeline DAG", "graph TD")
        assert "Pipeline DAG" in html

    def test_contains_mermaid_code(self):
        from scitex_clew._viz._templates import get_html_template

        mermaid_snippet = "graph TD\n    A --> B"
        html = get_html_template("T", mermaid_snippet)
        assert mermaid_snippet in html

    def test_contains_mermaid_script_tag(self):
        from scitex_clew._viz._templates import get_html_template

        html = get_html_template("T", "graph TD")
        assert "mermaid" in html.lower()

    def test_contains_timestamp(self):
        """HTML footer must include a timestamp."""
        from scitex_clew._viz._templates import get_html_template

        html = get_html_template("T", "graph TD")
        # Generated at: YYYY-MM-DD ...
        assert "Generated at:" in html

    def test_title_injection_safety(self):
        """Title appears in <title> and <h1>."""
        from scitex_clew._viz._templates import get_html_template

        html = get_html_template("Test Title", "graph TD")
        assert html.count("Test Title") >= 2  # At least <title> and <h1>


# ===========================================================================
# _json.py  — pure helper functions (no DB access)
# ===========================================================================


class TestFormatPath:
    """format_path converts a filesystem path to display string."""

    def test_name_mode_returns_basename(self):
        from scitex_clew._viz._json import format_path

        result = format_path("/home/user/data/results.csv", "name")
        assert result == "results.csv"

    def test_absolute_mode_returns_resolved_path(self):
        from scitex_clew._viz._json import format_path

        result = format_path("/tmp/data/output.csv", "absolute")
        # Should be an absolute path (may be same as input on this system)
        assert result.startswith("/")
        assert "output.csv" in result

    def test_relative_mode_with_unresolvable_path(self):
        """A path that cannot be made relative to cwd falls back to str(p)."""
        from scitex_clew._viz._json import format_path

        result = format_path("/some/deeply/nested/file.csv", "relative")
        assert isinstance(result, str)
        assert "file.csv" in result

    def test_unknown_path_returns_unknown(self):
        from scitex_clew._viz._json import format_path

        result = format_path("unknown", "name")
        assert result == "unknown"

    def test_empty_path_returns_unknown(self):
        from scitex_clew._viz._json import format_path

        result = format_path("", "name")
        assert result == "unknown"

    def test_name_mode_with_no_directory(self):
        """Bare filename still works."""
        from scitex_clew._viz._json import format_path

        result = format_path("file.txt", "name")
        assert result == "file.txt"


class TestFileToNodeId:
    """file_to_node_id produces stable, valid Mermaid node identifiers."""

    def test_starts_with_file_prefix(self):
        from scitex_clew._viz._json import file_to_node_id

        node_id = file_to_node_id("/data/results.csv")
        assert node_id.startswith("file_")

    def test_same_path_same_id(self):
        from scitex_clew._viz._json import file_to_node_id

        id1 = file_to_node_id("/data/results.csv")
        id2 = file_to_node_id("/data/results.csv")
        assert id1 == id2

    def test_different_paths_different_ids(self):
        from scitex_clew._viz._json import file_to_node_id

        id1 = file_to_node_id("/data/a.csv")
        id2 = file_to_node_id("/data/b.csv")
        assert id1 != id2

    def test_dots_replaced_with_underscores(self):
        """Node IDs must not contain dots (invalid Mermaid syntax)."""
        from scitex_clew._viz._json import file_to_node_id

        node_id = file_to_node_id("/data/my.data.csv")
        # Should not contain bare dots in the name portion
        # The hash suffix guarantees uniqueness; check the name part only
        assert "." not in node_id

    def test_hyphens_replaced_with_underscores(self):
        from scitex_clew._viz._json import file_to_node_id

        node_id = file_to_node_id("/data/my-file.csv")
        # After replacing hyphens we should not see '-' in the name segment
        assert "-" not in node_id

    def test_spaces_replaced_with_underscores(self):
        from scitex_clew._viz._json import file_to_node_id

        node_id = file_to_node_id("/data/my file.csv")
        assert " " not in node_id

    def test_returns_string(self):
        from scitex_clew._viz._json import file_to_node_id

        result = file_to_node_id("/path/to/file.csv")
        assert isinstance(result, str)


class TestVerifyFileHash:
    """verify_file_hash checks file existence and hash equality."""

    def test_returns_false_for_missing_file(self, tmp_path):
        from scitex_clew._viz._json import verify_file_hash

        missing = tmp_path / "no_such_file.txt"
        result = verify_file_hash(str(missing), "anyhash")
        assert result is False

    def test_returns_true_for_correct_hash(self, tmp_path):
        from scitex_clew._hash import hash_file
        from scitex_clew._viz._json import verify_file_hash

        f = tmp_path / "data.txt"
        f.write_text("hello world")
        correct_hash = hash_file(str(f))
        assert verify_file_hash(str(f), correct_hash) is True

    def test_returns_false_for_wrong_hash(self, tmp_path):
        from scitex_clew._viz._json import verify_file_hash

        f = tmp_path / "data.txt"
        f.write_text("hello world")
        assert verify_file_hash(str(f), "0000000000000000") is False


class TestGenerateDagJsonEmptyChain:
    """generate_dag_json with no session/target returns empty-graph structure."""

    def test_no_args_returns_dict_with_required_keys(self):
        """With an empty DB and no args, result is a valid graph dict."""
        from scitex_clew._viz._json import generate_dag_json

        with patch("scitex_clew._db.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.list_runs.return_value = []
            mock_db.get_chain.return_value = []
            mock_get_db.return_value = mock_db

            result = generate_dag_json()

        assert "nodes" in result
        assert "links" in result
        assert "metadata" in result

    def test_empty_chain_returns_empty_nodes_and_links(self):
        from scitex_clew._viz._json import generate_dag_json

        with patch("scitex_clew._db.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_chain.return_value = []
            mock_get_db.return_value = mock_db

            result = generate_dag_json(session_id="nonexistent_sess")

        assert result["nodes"] == []
        assert result["links"] == []

    def test_metadata_contains_generated_at(self):
        from scitex_clew._viz._json import generate_dag_json

        with patch("scitex_clew._db.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_chain.return_value = []
            mock_get_db.return_value = mock_db

            result = generate_dag_json(session_id="nonexistent_sess")

        assert "generated_at" in result["metadata"]

    def test_metadata_empty_flag_set_when_chain_empty(self):
        from scitex_clew._viz._json import generate_dag_json

        with patch("scitex_clew._db.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_chain.return_value = []
            mock_get_db.return_value = mock_db

            result = generate_dag_json(session_id="nonexistent_sess")

        assert result["metadata"].get("empty") is True


# ===========================================================================
# _mermaid_nodes.py
# ===========================================================================


class TestGetFileIcon:
    """get_file_icon maps file extensions to emoji strings."""

    def test_python_file_returns_snake_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("script.py")
        assert icon == "🐍"

    def test_csv_file_returns_chart_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("data.csv")
        assert icon == "📊"

    def test_json_file_returns_clipboard_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("config.json")
        assert icon == "📋"

    def test_yaml_file_returns_gear_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("params.yaml")
        assert icon == "⚙️"

    def test_yml_file_returns_gear_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("params.yml")
        assert icon == "⚙️"

    def test_png_file_returns_image_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("plot.png")
        assert icon == "🖼️"

    def test_pdf_file_returns_document_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("report.pdf")
        assert icon == "📄"

    def test_unknown_extension_returns_default_document_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("file.xyz")
        assert icon == "📄"

    def test_no_extension_returns_default_document_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("Makefile")
        assert icon == "📄"

    def test_npy_file_returns_number_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("array.npy")
        assert icon == "🔢"

    def test_pkl_file_returns_package_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("model.pkl")
        assert icon == "📦"

    def test_h5_file_returns_disk_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("data.h5")
        assert icon == "💾"

    def test_sh_file_returns_terminal_emoji(self):
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("run.sh")
        assert icon == "🖥️"

    def test_case_insensitive_extension_match(self):
        """Extension lookup must be case-insensitive (.CSV -> 📊)."""
        from scitex_clew._viz._mermaid_nodes import get_file_icon

        icon = get_file_icon("DATA.CSV")
        assert icon == "📊"


class TestAppendClassDefinitions:
    """append_class_definitions adds all required Mermaid classDef blocks."""

    def _get_class_defs(self) -> list:
        from scitex_clew._viz._mermaid_nodes import append_class_definitions

        lines = []
        append_class_definitions(lines)
        return lines

    def test_appends_multiple_lines(self):
        lines = self._get_class_defs()
        assert len(lines) > 0

    def test_contains_script_classdef(self):
        lines = self._get_class_defs()
        combined = "\n".join(lines)
        assert "classDef script" in combined

    def test_contains_verified_classdef(self):
        lines = self._get_class_defs()
        combined = "\n".join(lines)
        assert "classDef verified" in combined

    def test_contains_failed_classdef(self):
        lines = self._get_class_defs()
        combined = "\n".join(lines)
        assert "classDef failed" in combined

    def test_contains_file_classdef(self):
        lines = self._get_class_defs()
        combined = "\n".join(lines)
        assert "classDef file" in combined

    def test_contains_fill_color_specs(self):
        lines = self._get_class_defs()
        combined = "\n".join(lines)
        assert "fill:" in combined

    def test_all_expected_classdefs_present(self):
        """All eight class names from the source must appear."""
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
        combined = "\n".join(lines)
        for cls in expected_classes:
            assert f"classDef {cls}" in combined, f"Missing classDef {cls}"


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

    def test_verified_node_uses_verified_class(self):
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification(verified=True, from_scratch=False)
        run = self._make_run_dict()
        add_script_node(lines, 0, "sess_001", run, verification, "name")
        assert len(lines) == 1
        assert ":::verified" in lines[0]

    def test_verified_from_scratch_uses_verified_scratch_class(self):
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification(verified=True, from_scratch=True)
        run = self._make_run_dict()
        add_script_node(lines, 0, "sess_001", run, verification, "name")
        assert ":::verified_scratch" in lines[0]

    def test_failed_node_uses_failed_class(self):
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification(verified=False)
        run = self._make_run_dict()
        add_script_node(lines, 0, "sess_001", run, verification, "name")
        assert ":::failed" in lines[0]

    def test_failed_input_overrides_verified_to_failed(self):
        """A verified script with a failed upstream input becomes failed."""
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification(verified=True)
        run = self._make_run_dict()
        add_script_node(
            lines, 0, "sess_001", run, verification, "name", has_failed_input=True
        )
        assert ":::failed" in lines[0]

    def test_node_id_uses_script_index(self):
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        run = self._make_run_dict()
        add_script_node(lines, 3, "sess_001", run, verification, "name")
        assert lines[0].strip().startswith("script_3")

    def test_script_name_appears_in_node(self):
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        run = self._make_run_dict(script_path="/scripts/analyse.py")
        add_script_node(lines, 0, "sess_001", run, verification, "name")
        assert "analyse.py" in lines[0]

    def test_hash_display_when_show_hashes_true(self):
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        run = self._make_run_dict(script_hash="cafebabe99887766")
        add_script_node(
            lines, 0, "sess_001", run, verification, "name", show_hashes=True
        )
        # First 8 chars of hash should appear
        assert "cafebabe" in lines[0]

    def test_no_hash_display_when_show_hashes_false(self):
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        run = self._make_run_dict(script_hash="cafebabe99887766")
        add_script_node(
            lines, 0, "sess_001", run, verification, "name", show_hashes=False
        )
        assert "cafebabe" not in lines[0]

    def test_none_run_dict_produces_unknown_label(self):
        """When run is None, the node label uses 'unknown'."""
        from scitex_clew._viz._mermaid_nodes import add_script_node

        lines = []
        verification = self._make_verification()
        add_script_node(lines, 0, "sess_001", None, verification, "name")
        assert "unknown" in lines[0]


class TestAddFileNodes:
    """add_file_nodes adds file node declarations and edge lines."""

    def test_adds_node_for_each_file(self, tmp_path):
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        # Create real files so verify_file_hash returns True
        f1 = tmp_path / "data.csv"
        f1.write_text("a,b\n1,2")
        from scitex_clew._hash import hash_file

        h1 = hash_file(str(f1))

        lines = []
        file_nodes = {}
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
        assert len(lines) == 2

    def test_input_role_creates_arrow_to_script(self, tmp_path):
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
        edge_line = lines[-1]
        assert "--> script_0" in edge_line

    def test_output_role_creates_arrow_from_script(self, tmp_path):
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
        edge_line = lines[-1]
        assert "script_0 -->" in edge_line

    def test_duplicate_file_path_adds_only_one_node_decl(self, tmp_path):
        """When the same file appears twice it must only be declared once."""
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
        add_file_nodes(
            lines,
            "script_1",
            {str(f): h},
            file_nodes,
            show_hashes=False,
            path_mode="name",
            role="input",
        )
        assert len(lines) == first_len + 1  # only the edge line added

    def test_failed_file_uses_file_bad_class(self):
        """A file whose hash doesn't exist on disk gets file_bad class."""
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
        node_line = lines[0]
        assert ":::file_bad" in node_line

    def test_verified_output_without_rerun_uses_file_ok_class(self, tmp_path):
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        f = tmp_path / "ok.csv"
        f.write_text("ok")
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
            is_script_rerun_verified=False,
        )
        assert ":::file_ok" in lines[0]

    def test_verified_output_with_rerun_uses_file_rerun_class(self, tmp_path):
        from scitex_clew._viz._mermaid_nodes import add_file_nodes

        f = tmp_path / "rerun.csv"
        f.write_text("data")
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
            is_script_rerun_verified=True,
        )
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

    def test_single_run_produces_one_node_no_edge(self):
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        runs_data = self._make_runs_data(["sess_a"])
        lines = []
        generate_simple_dag(lines, runs_data, ["sess_a"])
        assert len(lines) == 1
        assert "-->" not in lines[0]

    def test_two_runs_produces_node_and_edge(self):
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        sids = ["sess_a", "sess_b"]
        runs_data = self._make_runs_data(sids)
        lines = []
        generate_simple_dag(lines, runs_data, sids)
        # Two node declarations + one edge
        assert len(lines) == 3
        assert any("-->" in l for l in lines)

    def test_verified_run_uses_verified_class(self):
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        runs_data = self._make_runs_data(["sess_ok"], verified=True)
        lines = []
        generate_simple_dag(lines, runs_data, ["sess_ok"])
        assert ":::verified" in lines[0]

    def test_failed_run_uses_failed_class(self):
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        runs_data = self._make_runs_data(["sess_bad"], verified=False)
        lines = []
        generate_simple_dag(lines, runs_data, ["sess_bad"])
        assert ":::failed" in lines[0]

    def test_script_name_appears_in_node_label(self):
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        sids = ["sess_x"]
        runs_data = self._make_runs_data(sids)
        # Override script path to a distinctive name
        runs_data[0]["run"]["script_path"] = "/path/distinctive_script.py"
        lines = []
        generate_simple_dag(lines, runs_data, sids)
        assert "distinctive_script.py" in lines[0]

    def test_hyphens_in_session_id_replaced(self):
        """Session IDs with hyphens must become valid Mermaid node ids."""
        from scitex_clew._viz._mermaid_dag import generate_simple_dag

        sids = ["sess-with-hyphens"]
        runs_data = self._make_runs_data(sids)
        lines = []
        generate_simple_dag(lines, runs_data, sids)
        assert "-" not in lines[0].split("[")[0]


class TestGenerateMultiTargetDagNoTargets:
    """generate_multi_target_dag with no targets/claims returns empty diagram."""

    def test_no_targets_no_claims_returns_mermaid_string(self):
        from scitex_clew._viz._mermaid_dag import generate_multi_target_dag

        result = generate_multi_target_dag(target_files=None, claims=False)
        assert isinstance(result, str)

    def test_no_targets_contains_graph_td(self):
        from scitex_clew._viz._mermaid_dag import generate_multi_target_dag

        result = generate_multi_target_dag(target_files=None, claims=False)
        assert "graph TD" in result

    def test_no_targets_contains_no_targets_message(self):
        from scitex_clew._viz._mermaid_dag import generate_multi_target_dag

        result = generate_multi_target_dag(target_files=None, claims=False)
        assert "No targets specified" in result


# ===========================================================================
# _mermaid.py
# ===========================================================================


class TestGenerateMermaidDagEmpty:
    """generate_mermaid_dag with an empty database returns valid Mermaid."""

    def _patched_empty_db(self):
        """Return a mock DB that holds no runs."""
        mock_db = MagicMock()
        mock_db.list_runs.return_value = []
        mock_db.get_chain.return_value = []
        return mock_db

    def test_returns_string(self):
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        with patch("scitex_clew._viz._mermaid.get_db") as mock_get_db:
            mock_get_db.return_value = self._patched_empty_db()
            result = generate_mermaid_dag()
        assert isinstance(result, str)

    def test_starts_with_graph_td(self):
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        with patch("scitex_clew._viz._mermaid.get_db") as mock_get_db:
            mock_get_db.return_value = self._patched_empty_db()
            result = generate_mermaid_dag()
        assert result.startswith("graph TD")

    def test_empty_db_produces_no_runs_found_message(self):
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        with patch("scitex_clew._viz._mermaid.get_db") as mock_get_db:
            mock_get_db.return_value = self._patched_empty_db()
            result = generate_mermaid_dag()
        assert "No runs found" in result

    def test_no_targets_claims_calls_generate_multi_target(self):
        """When claims=True the multi-target path is taken."""
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        with patch("scitex_clew._viz._mermaid.generate_multi_target_dag") as mock_multi:
            mock_multi.return_value = 'graph TD\n    empty["No runs found"]'
            result = generate_mermaid_dag(claims=True)
        mock_multi.assert_called_once()
        assert isinstance(result, str)

    def test_target_files_calls_generate_multi_target(self):
        from scitex_clew._viz._mermaid import generate_mermaid_dag

        with patch("scitex_clew._viz._mermaid.generate_multi_target_dag") as mock_multi:
            mock_multi.return_value = 'graph TD\n    empty["No runs found"]'
            result = generate_mermaid_dag(target_files=["/some/file.csv"])
        mock_multi.assert_called_once()


class TestGenerateHtmlDag:
    """generate_html_dag wraps Mermaid output in a complete HTML document."""

    def _mock_mermaid_output(self):
        return "graph TD\n    A --> B"

    def test_returns_string(self):
        from scitex_clew._viz._mermaid import generate_html_dag

        with patch(
            "scitex_clew._viz._mermaid.generate_mermaid_dag",
            return_value=self._mock_mermaid_output(),
        ):
            result = generate_html_dag()
        assert isinstance(result, str)

    def test_contains_doctype(self):
        from scitex_clew._viz._mermaid import generate_html_dag

        with patch(
            "scitex_clew._viz._mermaid.generate_mermaid_dag",
            return_value=self._mock_mermaid_output(),
        ):
            result = generate_html_dag()
        assert "<!DOCTYPE html>" in result

    def test_custom_title_appears_in_output(self):
        from scitex_clew._viz._mermaid import generate_html_dag

        with patch(
            "scitex_clew._viz._mermaid.generate_mermaid_dag",
            return_value=self._mock_mermaid_output(),
        ):
            result = generate_html_dag(title="Custom Title")
        assert "Custom Title" in result

    def test_mermaid_code_embedded_in_html(self):
        from scitex_clew._viz._mermaid import generate_html_dag

        mermaid_code = "graph TD\n    A --> B"
        with patch(
            "scitex_clew._viz._mermaid.generate_mermaid_dag",
            return_value=mermaid_code,
        ):
            result = generate_html_dag()
        assert mermaid_code in result


class TestRenderDag:
    """render_dag writes correctly formatted output to the specified file."""

    def _mock_mermaid(self):
        return "graph TD\n    A --> B"

    def _mock_html(self):
        return "<!DOCTYPE html><html><body>test</body></html>"

    def test_render_to_mmd_file(self, tmp_path):
        from scitex_clew._viz._mermaid import render_dag

        out = tmp_path / "diagram.mmd"
        with patch(
            "scitex_clew._viz._mermaid.generate_mermaid_dag",
            return_value=self._mock_mermaid(),
        ):
            result = render_dag(out)
        assert result == out
        assert out.exists()
        content = out.read_text()
        assert "graph TD" in content

    def test_render_to_html_file(self, tmp_path):
        from scitex_clew._viz._mermaid import render_dag

        out = tmp_path / "diagram.html"
        with patch(
            "scitex_clew._viz._mermaid.generate_html_dag",
            return_value=self._mock_html(),
        ):
            result = render_dag(out)
        assert result == out
        assert out.exists()
        content = out.read_text()
        assert "<!DOCTYPE html>" in content

    def test_render_to_json_file(self, tmp_path):
        from scitex_clew._viz._mermaid import render_dag

        out = tmp_path / "graph.json"
        fake_graph = {
            "nodes": [],
            "links": [],
            "metadata": {"generated_at": "2026-03-14", "empty": True},
        }
        with patch(
            "scitex_clew._viz._mermaid.generate_dag_json",
            return_value=fake_graph,
        ):
            result = render_dag(out)
        assert result == out
        assert out.exists()
        parsed = json.loads(out.read_text())
        assert "nodes" in parsed
        assert "links" in parsed
        assert "metadata" in parsed

    def test_render_creates_parent_dirs(self, tmp_path):
        from scitex_clew._viz._mermaid import render_dag

        out = tmp_path / "nested" / "deep" / "diagram.mmd"
        with patch(
            "scitex_clew._viz._mermaid.generate_mermaid_dag",
            return_value=self._mock_mermaid(),
        ):
            render_dag(out)
        assert out.exists()

    def test_render_unsupported_format_raises_value_error(self, tmp_path):
        from scitex_clew._viz._mermaid import render_dag

        out = tmp_path / "diagram.xyz"
        with pytest.raises(ValueError, match="Unsupported format"):
            render_dag(out)

    def test_render_to_png_falls_back_to_mmd_when_mmdc_missing(self, tmp_path):
        """When mmdc is not installed, render_dag falls back to .mmd file."""
        from scitex_clew._viz._mermaid import render_dag

        out = tmp_path / "diagram.png"
        with (
            patch(
                "scitex_clew._viz._mermaid.generate_mermaid_dag",
                return_value=self._mock_mermaid(),
            ),
            patch(
                "subprocess.run",
                side_effect=FileNotFoundError("mmdc not found"),
            ),
        ):
            result = render_dag(out)
        # Falls back to .mmd
        assert result.suffix == ".mmd"
        assert result.exists()


# ===========================================================================
# _format.py
# ===========================================================================


class TestFormatRunVerification:
    """format_run_verification produces a correctly structured text block."""

    def test_returns_string(self):
        from scitex_clew._viz._format import format_run_verification

        rv = _make_run_verification()
        result = format_run_verification(rv)
        assert isinstance(result, str)

    def test_first_line_contains_session_id(self):
        from scitex_clew._viz._format import format_run_verification

        rv = _make_run_verification(session_id="my_unique_session_42")
        result = format_run_verification(rv)
        assert "my_unique_session_42" in result.split("\n")[0]

    def test_first_line_contains_status_text(self):
        from scitex_clew._viz._format import format_run_verification

        rv = _make_run_verification(status=VerificationStatus.VERIFIED)
        result = format_run_verification(rv)
        assert "verified" in result

    def test_script_path_appears_when_present(self):
        from scitex_clew._viz._format import format_run_verification

        rv = _make_run_verification(script_path="/my/analysis.py")
        result = format_run_verification(rv)
        assert "Script:" in result
        assert "/my/analysis.py" in result

    def test_no_script_path_when_none(self):
        from scitex_clew._viz._format import format_run_verification

        rv = _make_run_verification(script_path=None)
        result = format_run_verification(rv)
        assert "Script:" not in result

    def test_verbose_mode_shows_inputs(self):
        from scitex_clew._viz._format import format_run_verification

        fv = _make_file_verification(path="/data/input.csv", role="input")
        rv = _make_run_verification(files=[fv])
        result = format_run_verification(rv, verbose=True)
        assert "Inputs:" in result
        assert "/data/input.csv" in result

    def test_verbose_mode_shows_outputs(self):
        from scitex_clew._viz._format import format_run_verification

        fv = _make_file_verification(path="/data/output.csv", role="output")
        rv = _make_run_verification(files=[fv])
        result = format_run_verification(rv, verbose=True)
        assert "Outputs:" in result
        assert "/data/output.csv" in result

    def test_non_verified_shows_mismatched_files(self):
        from scitex_clew._viz._format import format_run_verification

        fv = _make_file_verification(
            path="/data/bad.csv",
            role="output",
            expected_hash="aabbcc112233445566",
            current_hash="000000000000000000",
            status=VerificationStatus.MISMATCH,
        )
        rv = _make_run_verification(status=VerificationStatus.MISMATCH, files=[fv])
        result = format_run_verification(rv)
        assert "Mismatched:" in result
        assert "/data/bad.csv" in result

    def test_non_verified_shows_missing_files(self):
        from scitex_clew._viz._format import format_run_verification

        fv = _make_file_verification(
            path="/data/gone.csv",
            role="input",
            current_hash=None,
            status=VerificationStatus.MISSING,
        )
        rv = _make_run_verification(status=VerificationStatus.MISSING, files=[fv])
        result = format_run_verification(rv)
        assert "Missing:" in result
        assert "/data/gone.csv" in result

    def test_verified_without_verbose_hides_files(self):
        """A verified run in non-verbose mode should NOT list individual files."""
        from scitex_clew._viz._format import format_run_verification

        fv = _make_file_verification(path="/data/clean.csv", role="output")
        rv = _make_run_verification(status=VerificationStatus.VERIFIED, files=[fv])
        result = format_run_verification(rv, verbose=False)
        # File list sections should be absent
        assert "Inputs:" not in result
        assert "Outputs:" not in result


class TestFormatRunDetailed:
    """format_run_detailed shows a tree with input/output icon strips."""

    def test_returns_string(self):
        from scitex_clew._viz._format import format_run_detailed

        rv = _make_run_verification()
        result = format_run_detailed(rv)
        assert isinstance(result, str)

    def test_first_line_contains_session_id(self):
        from scitex_clew._viz._format import format_run_detailed

        rv = _make_run_verification(session_id="detailed_sess_99")
        result = format_run_detailed(rv)
        assert "detailed_sess_99" in result.split("\n")[0]

    def test_inputs_line_contains_tree_prefix(self):
        from scitex_clew._viz._format import format_run_detailed

        fv = _make_file_verification(role="input")
        rv = _make_run_verification(files=[fv])
        result = format_run_detailed(rv)
        assert "inputs:" in result

    def test_outputs_line_contains_tree_prefix(self):
        from scitex_clew._viz._format import format_run_detailed

        fv = _make_file_verification(role="output")
        rv = _make_run_verification(files=[fv])
        result = format_run_detailed(rv)
        assert "outputs:" in result

    def test_script_basename_only_not_full_path(self):
        from scitex_clew._viz._format import format_run_detailed

        rv = _make_run_verification(script_path="/very/deep/path/analysis.py")
        result = format_run_detailed(rv)
        assert "analysis.py" in result
        # Full directory path should not be shown
        assert "/very/deep/path" not in result

    def test_failed_input_filename_highlighted_in_output(self):
        """A failed input file name should appear under the inputs section."""
        from scitex_clew._viz._format import format_run_detailed

        bad_fv = _make_file_verification(
            path="/data/bad_input.csv",
            role="input",
            expected_hash="abc",
            current_hash="xyz",
            status=VerificationStatus.MISMATCH,
        )
        rv = _make_run_verification(files=[bad_fv])
        result = format_run_detailed(rv)
        assert "bad_input.csv" in result


class TestFormatChainVerification:
    """format_chain_verification renders a tree for the entire chain."""

    def test_returns_string(self):
        from scitex_clew._viz._format import format_chain_verification

        cv = _make_chain_verification()
        result = format_chain_verification(cv)
        assert isinstance(result, str)

    def test_contains_target_file(self):
        from scitex_clew._viz._format import format_chain_verification

        cv = _make_chain_verification(target_file="/data/target.csv")
        result = format_chain_verification(cv)
        assert "/data/target.csv" in result

    def test_no_runs_shows_no_runs_found(self):
        from scitex_clew._viz._format import format_chain_verification

        cv = _make_chain_verification(runs=[])
        result = format_chain_verification(cv)
        assert "no runs found" in result

    def test_single_verified_run_shown_with_tree_prefix(self):
        from scitex_clew._viz._format import format_chain_verification

        run = _make_run_verification(session_id="sess_one")
        cv = _make_chain_verification(runs=[run])
        result = format_chain_verification(cv)
        # Last run gets '└──' prefix
        assert "└──" in result
        assert "sess_one" in result

    def test_multiple_runs_tree_structure(self):
        from scitex_clew._viz._format import format_chain_verification

        runs = [
            _make_run_verification(session_id="sess_first"),
            _make_run_verification(session_id="sess_second"),
        ]
        cv = _make_chain_verification(runs=runs)
        result = format_chain_verification(cv)
        # Non-last run gets '├──'
        assert "├──" in result
        assert "└──" in result

    def test_shows_script_name_for_runs_with_script(self):
        from scitex_clew._viz._format import format_chain_verification

        run = _make_run_verification(
            session_id="sess_x", script_path="/path/preprocess.py"
        )
        cv = _make_chain_verification(runs=[run])
        result = format_chain_verification(cv)
        assert "preprocess.py" in result

    def test_shows_mismatched_files_for_failed_run(self):
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
        result = format_chain_verification(cv)
        assert "mismatch.csv" in result

    def test_shows_missing_files_for_failed_run(self):
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
        result = format_chain_verification(cv)
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

    def test_returns_string(self):
        from scitex_clew._viz._format import format_status

        result = format_status(self._make_status_dict())
        assert isinstance(result, str)

    def test_contains_total_runs_count(self):
        from scitex_clew._viz._format import format_status

        status = self._make_status_dict(
            verified_count=5, mismatch_count=1, missing_count=2
        )
        result = format_status(status)
        assert "8" in result  # total = 5+1+2

    def test_all_verified_shows_all_tracked_verified(self):
        from scitex_clew._viz._format import format_status

        result = format_status(self._make_status_dict(verified_count=5))
        assert "All tracked files verified" in result

    def test_mismatched_section_shown_when_present(self):
        from scitex_clew._viz._format import format_status

        mismatched = [{"session_id": "sess_bad", "files": ["/data/bad.csv"]}]
        status = self._make_status_dict(mismatch_count=1, mismatched=mismatched)
        result = format_status(status)
        assert "sess_bad" in result
        assert "bad.csv" in result

    def test_missing_section_shown_when_present(self):
        from scitex_clew._viz._format import format_status

        missing = [{"session_id": "sess_gone", "files": ["/data/gone.csv"]}]
        status = self._make_status_dict(missing_count=1, missing=missing)
        result = format_status(status)
        assert "sess_gone" in result
        assert "gone.csv" in result

    def test_more_than_three_files_truncated_with_ellipsis(self):
        from scitex_clew._viz._format import format_status

        files = [f"/data/file_{i}.csv" for i in range(6)]
        mismatched = [{"session_id": "sess_x", "files": files}]
        status = self._make_status_dict(mismatch_count=1, mismatched=mismatched)
        result = format_status(status)
        assert "more" in result

    def test_more_than_ten_mismatch_sessions_truncated(self):
        from scitex_clew._viz._format import format_status

        mismatched = [
            {"session_id": f"sess_{i}", "files": [f"/data/{i}.csv"]} for i in range(15)
        ]
        status = self._make_status_dict(mismatch_count=15, mismatched=mismatched)
        result = format_status(status)
        assert "more runs" in result

    def test_verified_count_appears_in_output(self):
        from scitex_clew._viz._format import format_status

        status = self._make_status_dict(verified_count=7)
        result = format_status(status)
        assert "7" in result

    def test_header_line_present(self):
        from scitex_clew._viz._format import format_status

        result = format_status(self._make_status_dict())
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

    def test_returns_string(self):
        from scitex_clew._viz._format import format_list

        result = format_list(self._make_run_records(), verify=False)
        assert isinstance(result, str)

    def test_header_row_present(self):
        from scitex_clew._viz._format import format_list

        result = format_list(self._make_run_records(), verify=False)
        assert "SESSION" in result
        assert "STATUS" in result
        assert "SCRIPT" in result

    def test_each_session_id_appears_in_output(self):
        from scitex_clew._viz._format import format_list

        records = self._make_run_records(3)
        result = format_list(records, verify=False)
        # Prefix of session IDs should appear
        for rec in records:
            assert rec["session_id"][:20] in result

    def test_script_basename_appears_in_output(self):
        from scitex_clew._viz._format import format_list

        records = self._make_run_records(1)
        result = format_list(records, verify=False)
        assert "script_0.py" in result

    def test_empty_run_list_returns_header_only(self):
        from scitex_clew._viz._format import format_list

        result = format_list([], verify=False)
        # Should at least contain header
        assert "SESSION" in result

    def test_very_long_session_id_truncated(self):
        """Session IDs longer than 45 chars should be truncated with '..'."""
        from scitex_clew._viz._format import format_list

        long_id = "x" * 60
        records = [{"session_id": long_id, "script_path": "/s.py", "status": "ok"}]
        result = format_list(records, verify=False)
        assert ".." in result

    def test_very_long_script_name_truncated(self):
        from scitex_clew._viz._format import format_list

        long_script = "/path/" + "a" * 40 + ".py"
        records = [
            {
                "session_id": "sess_abc",
                "script_path": long_script,
                "status": "ok",
            }
        ]
        result = format_list(records, verify=False)
        assert ".." in result

    def test_no_script_path_shows_dash(self):
        from scitex_clew._viz._format import format_list

        records = [{"session_id": "sess_noscript", "status": "ok"}]
        result = format_list(records, verify=False)
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
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records(
            [VerificationStatus.VERIFIED, VerificationStatus.VERIFIED]
        )
        with patch(
            "scitex_clew._viz._utils.verify_run",
            side_effect=lambda sid: verifs[sid],
        ):
            print_verification_summary(records)

        captured = capsys.readouterr()
        assert "Verification Summary" in captured.out

    def test_prints_verified_count(self, capsys):
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records(
            [
                VerificationStatus.VERIFIED,
                VerificationStatus.VERIFIED,
                VerificationStatus.MISMATCH,
            ]
        )
        with patch(
            "scitex_clew._viz._utils.verify_run",
            side_effect=lambda sid: verifs[sid],
        ):
            print_verification_summary(records)

        captured = capsys.readouterr()
        assert "2" in captured.out  # 2 verified

    def test_prints_mismatch_count(self, capsys):
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records(
            [VerificationStatus.MISMATCH, VerificationStatus.VERIFIED]
        )
        with patch(
            "scitex_clew._viz._utils.verify_run",
            side_effect=lambda sid: verifs[sid],
        ):
            print_verification_summary(records)

        captured = capsys.readouterr()
        assert "Mismatch" in captured.out

    def test_prints_missing_count(self, capsys):
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records([VerificationStatus.MISSING])
        with patch(
            "scitex_clew._viz._utils.verify_run",
            side_effect=lambda sid: verifs[sid],
        ):
            print_verification_summary(records)

        captured = capsys.readouterr()
        assert "Missing" in captured.out

    def test_show_all_true_prints_verified_runs_too(self, capsys):
        from scitex_clew._viz._utils import print_verification_summary

        records, verifs = self._build_run_records([VerificationStatus.VERIFIED])
        with (
            patch(
                "scitex_clew._viz._utils.verify_run",
                side_effect=lambda sid: verifs[sid],
            ),
            patch("scitex_clew._viz._utils.format_run_detailed") as mock_fmt,
        ):
            mock_fmt.return_value = "RUN_DETAIL_LINE"
            print_verification_summary(records, show_all=True)

        captured = capsys.readouterr()
        assert "RUN_DETAIL_LINE" in captured.out

    def test_empty_run_list_prints_zeros(self, capsys):
        from scitex_clew._viz._utils import print_verification_summary

        print_verification_summary([])
        captured = capsys.readouterr()
        assert "0" in captured.out


# ===========================================================================
# __init__.py  —  public re-exports of viz symbols
# ===========================================================================


class TestVizInitExports:
    """The _viz package exposes its public symbols correctly."""

    def test_colors_importable_from_viz(self):
        from scitex_clew._viz import Colors

        assert hasattr(Colors, "GREEN")

    def test_verification_level_importable_from_viz(self):
        from scitex_clew._viz import VerificationLevel

        assert VerificationLevel.CACHE == "cache"

    def test_format_run_verification_importable(self):
        from scitex_clew._viz import format_run_verification

        assert callable(format_run_verification)

    def test_format_chain_verification_importable(self):
        from scitex_clew._viz import format_chain_verification

        assert callable(format_chain_verification)

    def test_format_status_importable(self):
        from scitex_clew._viz import format_status

        assert callable(format_status)

    def test_format_list_importable(self):
        from scitex_clew._viz import format_list

        assert callable(format_list)

    def test_format_run_detailed_importable(self):
        from scitex_clew._viz import format_run_detailed

        assert callable(format_run_detailed)

    def test_generate_mermaid_dag_importable(self):
        from scitex_clew._viz import generate_mermaid_dag

        assert callable(generate_mermaid_dag)

    def test_generate_html_dag_importable(self):
        from scitex_clew._viz import generate_html_dag

        assert callable(generate_html_dag)

    def test_render_dag_importable(self):
        from scitex_clew._viz import render_dag

        assert callable(render_dag)

    def test_print_verification_summary_importable(self):
        from scitex_clew._viz import print_verification_summary

        assert callable(print_verification_summary)

    def test_all_exports_are_callable_or_class(self):
        import scitex_clew._viz as viz_pkg

        for name in viz_pkg.__all__:
            obj = getattr(viz_pkg, name)
            assert callable(obj) or isinstance(obj, type), (
                f"{name} should be callable or a class"
            )


# EOF
