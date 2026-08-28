#!/usr/bin/env python3
"""Tests for scitex_clew._core._node_class module."""

from __future__ import annotations

import pytest

from scitex_clew import VerificationDB
from scitex_clew._core._node_class import (
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
    """NOTE (sqlite-migration-scitex-clew-20260828 PR 4 — accepted behavior
    change): the pre-migration tests here hand-created a raw sqlite3
    ``file_hashes`` table (no ``node_class`` column) and asserted that
    ``migrate_add_node_class`` ran ``ALTER TABLE ... ADD COLUMN`` against
    it, checking ``PRAGMA table_info`` before/after. That premise no longer
    holds: ``node_class`` is now a plain field of ``FILE_HASHES_SCHEMA``
    (see ``_db/_schema.py``), created as a real column by
    ``Store.__init__``'s ``CREATE TABLE IF NOT EXISTS`` the moment a
    ``file_hashes`` store is opened — there is no more separate raw-sqlite
    ``file_hashes`` table for this function to inspect or ALTER. Retargeted
    to verify what IS still true: the call is a safe, idempotent way to
    ensure the DB is ready, and the ``node_class`` field it used to "add"
    is genuinely usable end-to-end afterward.
    """

    def test_is_idempotent_and_does_not_raise(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        # Act
        migrate_add_node_class(db_path)
        migrate_add_node_class(db_path)
        # Assert — reaching here without raising is the assertion.
        assert True

    def test_node_class_field_usable_after_migrate(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        migrate_add_node_class(db_path)
        db = VerificationDB(db_path)
        db.add_run("sess1", "/path/script.py")
        db.add_file_hash("sess1", "/path/data.csv", "abc123", "input")
        # Act
        set_node_class(db_path, "sess1", "/path/data.csv", "input")
        matches = [
            row
            for row in db._file_hashes.rows()
            if row.values.get("file_path") == "/path/data.csv"
        ]
        # Assert
        assert matches[0].values["node_class"] == "input"


# ---------------------------------------------------------------------------
# set_node_class
# ---------------------------------------------------------------------------


class TestSetNodeClass:
    """NOTE (sqlite-migration-scitex-clew-20260828 PR 4 — accepted behavior
    change): the pre-migration ``_setup_db`` helper hand-created a raw
    sqlite3 ``file_hashes`` table and inserted a row directly, bypassing
    ``VerificationDB``. Now that ``file_hashes`` is a
    ``scitex_dev.store.Store`` table, records only exist once written
    through the real API (``add_run`` + ``add_file_hash``); retargeted to
    seed via that API and to read the result back via
    ``db._file_hashes.rows()`` instead of raw SQL.
    """

    def _setup_db(self, db_path):
        """Create a real VerificationDB with one file_hash record."""
        db = VerificationDB(db_path)
        db.add_run("sess1", "/path/script.py")
        db.add_file_hash("sess1", "/path/data.csv", "abc123", "input")
        return db

    def test_set_valid_node_class(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        db = self._setup_db(db_path)
        # Act
        set_node_class(db_path, "sess1", "/path/data.csv", "input")
        matches = [
            row
            for row in db._file_hashes.rows()
            if row.values.get("session_id") == "sess1"
        ]
        # Assert
        assert matches[0].values["node_class"] == "input"

    def test_set_all_valid_classes(self, tmp_path):
        # Arrange
        # Act
        # Assert
        for nc in NODE_CLASSES:
            db_path = tmp_path / f"test_{nc}.db"
            db = self._setup_db(db_path)

            set_node_class(db_path, "sess1", "/path/data.csv", nc)

            matches = [
                row
                for row in db._file_hashes.rows()
                if row.values.get("session_id") == "sess1"
            ]
            assert matches[0].values["node_class"] == nc

    def test_multiple_roles_same_session_and_file_all_updated(self, tmp_path):
        # Arrange — the WHERE clause is (session_id, file_path) only, not the
        # full (session_id, file_path, role) composite identity, so a file
        # recorded under two roles in one session gets BOTH rows updated.
        db_path = tmp_path / "test.db"
        db = VerificationDB(db_path)
        db.add_run("sess1", "/path/script.py")
        db.add_file_hash("sess1", "/path/shared.csv", "hash-in", "input")
        db.add_file_hash("sess1", "/path/shared.csv", "hash-out", "output")
        # Act
        set_node_class(db_path, "sess1", "/path/shared.csv", "processing")
        matches = [
            row
            for row in db._file_hashes.rows()
            if row.values.get("session_id") == "sess1"
            and row.values.get("file_path") == "/path/shared.csv"
        ]
        # Assert
        assert len(matches) == 2 and all(
            row.values["node_class"] == "processing" for row in matches
        )

    def test_invalid_node_class_raises_value_error(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        self._setup_db(db_path)
        # Act
        def _call():
            set_node_class(db_path, "sess1", "/path/data.csv", "invalid_class")

        # Assert
        with pytest.raises(ValueError, match="Invalid node_class"):
            _call()


# ---------------------------------------------------------------------------
# auto_classify
# ---------------------------------------------------------------------------


class TestAutoClassify:
    """NOTE (sqlite-migration-scitex-clew-20260828 PR 4 — accepted behavior
    change): the pre-migration ``_setup_db`` helper hand-created a raw
    sqlite3 ``file_hashes`` table and bulk-inserted rows directly. Now that
    ``file_hashes`` is a ``scitex_dev.store.Store`` table, rows only exist
    once written through the real API (``add_run`` + ``add_file_hash``);
    retargeted to seed via that API and to read results back via
    ``db._file_hashes.rows()`` instead of raw SQL. "Already classified"
    rows are seeded via ``set_node_class`` (already covered by its own
    tests above) rather than a raw INSERT.
    """

    def _setup_db(self, db_path, rows):
        """Create a real VerificationDB with the given (session_id, file_path,
        hash, role) file_hash records, none classified yet."""
        db = VerificationDB(db_path)
        seen_sessions = set()
        for session_id, file_path, hash_value, role in rows:
            if session_id not in seen_sessions:
                db.add_run(session_id, f"/scripts/{session_id}.py")
                seen_sessions.add(session_id)
            db.add_file_hash(session_id, file_path, hash_value, role)
        return db

    def _node_class_for(self, db, file_path):
        matches = [
            row
            for row in db._file_hashes.rows()
            if row.values.get("file_path") == file_path
        ]
        return matches[0].values.get("node_class")

    def test_classifies_unclassified_rows(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [
            ("s1", "data.csv", "h1", "input"),
            ("s1", "figure.png", "h2", "output"),
            ("s1", "script.py", "h3", "script"),
        ]
        self._setup_db(db_path, rows)
        # Act
        updated = auto_classify(db_path)
        # Assert
        assert updated > 0

    def test_skips_already_classified_rows(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        db = self._setup_db(db_path, [("s1", "data.csv", "h1", "input")])
        set_node_class(db_path, "s1", "data.csv", "source")
        # Act
        updated = auto_classify(db_path)
        # Assert — already classified, should not update
        assert updated == 0

    def test_returns_count_of_updated_updated_is_int(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [
            ("s1", "file1.csv", "h1", "input"),
            ("s1", "file2.py", "h2", "script"),
        ]
        self._setup_db(db_path, rows)
        # Act
        updated = auto_classify(db_path)
        # Assert
        assert isinstance(updated, int)

    def test_returns_count_of_updated_updated_0(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [
            ("s1", "file1.csv", "h1", "input"),
            ("s1", "file2.py", "h2", "script"),
        ]
        self._setup_db(db_path, rows)
        # Act
        updated = auto_classify(db_path)
        # Assert
        assert updated >= 0

    def test_classifies_tex_output_as_claim(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [("s1", "paper.tex", "h1", "output")]
        db = self._setup_db(db_path, rows)
        # Act
        auto_classify(db_path)
        # Assert
        assert self._node_class_for(db, "paper.tex") == "claim"

    def test_classifies_png_output_as_output(self, tmp_path):
        # Arrange
        db_path = tmp_path / "test.db"
        rows = [("s1", "fig.png", "h1", "output")]
        db = self._setup_db(db_path, rows)
        # Act
        auto_classify(db_path)
        # Assert
        assert self._node_class_for(db, "fig.png") == "output"


# EOF
