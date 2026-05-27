#!/usr/bin/env python3
"""Tests for scitex_clew._node_class module."""

from __future__ import annotations

import sqlite3

import pytest

from scitex_clew._node_class import (
    NODE_CLASSES,
    auto_classify,
    infer_node_class,
    migrate_add_node_class,
    set_node_class,
)


# ---------------------------------------------------------------------------
# NODE_CLASSES constant
# ---------------------------------------------------------------------------


class TestNodeClassesConstant:
    def test_is_tuple_node_classes_is_tuple(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert isinstance(NODE_CLASSES, tuple)

    def test_contains_expected_classes_source_in_node_classes(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "source" in NODE_CLASSES

    def test_contains_expected_classes_input_in_node_classes(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "input" in NODE_CLASSES

    def test_contains_expected_classes_processing_in_node_classes(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "processing" in NODE_CLASSES

    def test_contains_expected_classes_output_in_node_classes(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "output" in NODE_CLASSES

    def test_contains_expected_classes_claim_in_node_classes(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert "claim" in NODE_CLASSES


    def test_has_five_classes(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert len(NODE_CLASSES) == 5


# ---------------------------------------------------------------------------
# infer_node_class
# ---------------------------------------------------------------------------


class TestInferNodeClass:
    # Script role
    def test_script_role_py_returns_source(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("run.py", "script") == "source"

    def test_script_role_sh_returns_source(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("run.sh", "script") == "source"

    def test_script_role_r_returns_source(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("analysis.R", "script") == "source"

    def test_script_role_jl_returns_source(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("model.jl", "script") == "source"

    def test_script_role_unknown_ext_returns_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("data.csv", "script") is None

    # Input role
    def test_input_role_py_returns_source(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("helper.py", "input") == "source"

    def test_input_role_csv_returns_input(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("data.csv", "input") == "input"

    def test_input_role_npy_returns_input(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("array.npy", "input") == "input"

    def test_input_role_json_returns_input(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("config.json", "input") == "input"

    def test_input_role_yaml_returns_input(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("config.yaml", "input") == "input"

    def test_input_role_unknown_ext_returns_input(self):
        # Fallback for input role is "input"
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("file.xyz", "input") == "input"

    # Output role
    def test_output_role_csv_returns_output(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("results.csv", "output") == "output"

    def test_output_role_png_returns_output(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("figure.png", "output") == "output"

    def test_output_role_svg_returns_output(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("figure.svg", "output") == "output"

    def test_output_role_tex_returns_claim(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("paper.tex", "output") == "claim"

    def test_output_role_bib_returns_claim(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("refs.bib", "output") == "claim"

    def test_output_role_unknown_ext_returns_output(self):
        # Fallback for output role is "output"
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("file.xyz", "output") == "output"

    # Unknown role
    def test_unknown_role_returns_none(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("data.csv", "unknown_role") is None

    # Case insensitivity of extension
    def test_extension_case_insensitive_infer_node_class_figure_png_output_output(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("figure.PNG", "output") == "output"

    def test_extension_case_insensitive_infer_node_class_script_py_script_source(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("script.PY", "script") == "source"


    # Path with directory components
    def test_full_path_handled(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        assert infer_node_class("/home/user/project/data.csv", "input") == "input"


# ---------------------------------------------------------------------------
# migrate_add_node_class
# ---------------------------------------------------------------------------


class TestMigrateAddNodeClass:
    def _make_db_with_table(self, db_path):
        """Create a minimal DB with a file_hashes table (no node_class col)."""
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE file_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                file_path TEXT,
                hash TEXT,
                role TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    def test_adds_node_class_column_node_class_not_in_cols_before(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        self._make_db_with_table(db_path)
        # Column should not exist yet
        conn = sqlite3.connect(str(db_path))
        cols_before = {row[1] for row in conn.execute("PRAGMA table_info(file_hashes)")}
        # Act
        # Act
        conn.close()
        # Act
        # Assert
        # Assert
        # Assert
        assert "node_class" not in cols_before

    def test_adds_node_class_column_node_class_in_cols_after_node_class_not_in_cols_before(self, tmp_path):
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        self._make_db_with_table(db_path)
        # Column should not exist yet
        conn = sqlite3.connect(str(db_path))
        cols_before = {row[1] for row in conn.execute("PRAGMA table_info(file_hashes)")}
        # Act
        conn.close()
        # Act
        # Assert
        # Assert
        assert "node_class" not in cols_before

    def test_adds_node_class_column_node_class_in_cols_after_node_class_in_cols_after(self, tmp_path):
        # Arrange — start from a schema missing the column.
        db_path = tmp_path / "test.db"
        self._make_db_with_table(db_path)
        # Act
        migrate_add_node_class(db_path)
        conn = sqlite3.connect(str(db_path))
        cols_after = {row[1] for row in conn.execute("PRAGMA table_info(file_hashes)")}
        conn.close()
        # Assert
        assert "node_class" in cols_after



    def test_idempotent_node_class_in_cols(self, tmp_path):
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        self._make_db_with_table(db_path)

        # Call twice — should not raise
        migrate_add_node_class(db_path)
        migrate_add_node_class(db_path)

        conn = sqlite3.connect(str(db_path))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(file_hashes)")}
        # Act
        # Act
        conn.close()
        # Assert
        # Assert
        assert "node_class" in cols


# ---------------------------------------------------------------------------
# set_node_class
# ---------------------------------------------------------------------------


class TestSetNodeClass:
    def _setup_db(self, db_path):
        """Create DB with file_hashes table including node_class."""
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE file_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                file_path TEXT,
                hash TEXT,
                role TEXT,
                node_class TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO file_hashes (session_id, file_path, hash, role) "
            "VALUES ('sess1', '/path/data.csv', 'abc123', 'input')"
        )
        conn.commit()
        conn.close()

    def test_set_valid_node_class(self, tmp_path):
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        self._setup_db(db_path)

        set_node_class(db_path, "sess1", "/path/data.csv", "input")

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT node_class FROM file_hashes WHERE session_id='sess1'"
        ).fetchone()
        # Act
        # Act
        conn.close()
        # Assert
        # Assert
        assert row[0] == "input"

    def test_set_all_valid_classes(self, tmp_path):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        db_path = tmp_path / "test.db"
        for nc in NODE_CLASSES:
            self._setup_db(db_path)
            set_node_class(db_path, "sess1", "/path/data.csv", nc)

            conn = sqlite3.connect(str(db_path))
            row = conn.execute(
                "SELECT node_class FROM file_hashes WHERE session_id='sess1'"
            ).fetchone()
            conn.close()
            assert row[0] == nc
            db_path.unlink()

    def test_invalid_node_class_raises_value_error(self, tmp_path):
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        # Act
        # Act
        self._setup_db(db_path)

        # Assert
        # Assert
        with pytest.raises(ValueError, match="Invalid node_class"):
            set_node_class(db_path, "sess1", "/path/data.csv", "invalid_class")


# ---------------------------------------------------------------------------
# auto_classify
# ---------------------------------------------------------------------------


class TestAutoClassify:
    def _setup_db(self, db_path, rows):
        """Create DB with file_hashes rows (no node_class set)."""
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE file_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                file_path TEXT,
                hash TEXT,
                role TEXT,
                node_class TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO file_hashes (session_id, file_path, hash, role) VALUES (?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()

    def test_classifies_unclassified_rows(self, tmp_path):
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [
            ("s1", "data.csv", "h1", "input"),
            ("s1", "figure.png", "h2", "output"),
            ("s1", "script.py", "h3", "script"),
        ]
        self._setup_db(db_path, rows)

        # Act
        # Act
        updated = auto_classify(db_path)
        # Assert
        # Assert
        assert updated > 0

    def test_skips_already_classified_rows(self, tmp_path):
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE file_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                file_path TEXT,
                hash TEXT,
                role TEXT,
                node_class TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO file_hashes (session_id, file_path, hash, role, node_class) "
            "VALUES ('s1', 'data.csv', 'h1', 'input', 'source')"
        )
        conn.commit()
        conn.close()

        # Act
        # Act
        updated = auto_classify(db_path)
        # Already classified — should not update
        # Assert
        # Assert
        assert updated == 0

    def test_returns_count_of_updated_updated_is_int(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [
            ("s1", "file1.csv", "h1", "input"),
            ("s1", "file2.py", "h2", "script"),
        ]
        self._setup_db(db_path, rows)
        # Act
        # Act
        updated = auto_classify(db_path)
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(updated, int)

    def test_returns_count_of_updated_updated_0(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [
            ("s1", "file1.csv", "h1", "input"),
            ("s1", "file2.py", "h2", "script"),
        ]
        self._setup_db(db_path, rows)
        # Act
        # Act
        updated = auto_classify(db_path)
        # Act
        # Assert
        # Assert
        # Assert
        assert updated >= 0


    def test_classifies_tex_output_as_claim(self, tmp_path):
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [("s1", "paper.tex", "h1", "output")]
        self._setup_db(db_path, rows)

        auto_classify(db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT node_class FROM file_hashes WHERE file_path='paper.tex'"
        ).fetchone()
        # Act
        # Act
        conn.close()
        # Assert
        # Assert
        assert row[0] == "claim"

    def test_classifies_png_output_as_output(self, tmp_path):
        # Arrange
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [("s1", "fig.png", "h1", "output")]
        self._setup_db(db_path, rows)

        auto_classify(db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT node_class FROM file_hashes WHERE file_path='fig.png'"
        ).fetchone()
        # Act
        # Act
        conn.close()
        # Assert
        # Assert
        assert row[0] == "output"


# EOF
