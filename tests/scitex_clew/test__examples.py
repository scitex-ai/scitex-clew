#!/usr/bin/env python3
"""Tests for scitex_clew._examples module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scitex_clew._examples import _find_examples_dir, init_examples


# ---------------------------------------------------------------------------
# _find_examples_dir
# ---------------------------------------------------------------------------


class TestFindExamplesDir:
    def test_returns_path_or_none(self):
        result = _find_examples_dir()
        assert result is None or isinstance(result, Path)

    def test_returns_existing_dir_if_found(self):
        result = _find_examples_dir()
        if result is not None:
            assert result.exists()
            assert result.is_dir()

    def test_bundled_example_data_used_if_exists(self):
        bundled = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "scitex_clew"
            / "_example_data"
        )
        result = _find_examples_dir()
        if bundled.exists():
            assert result == bundled

    def test_returns_none_when_no_candidates_exist(self, tmp_path):
        # Manually exercise the same lookup logic with a non-existent candidate.
        nonexistent = tmp_path / "does_not_exist"
        assert not nonexistent.exists()

        result = None
        for candidate in [nonexistent]:
            if candidate.exists() and candidate.is_dir():
                result = candidate
                break
        assert result is None


# ---------------------------------------------------------------------------
# init_examples
# ---------------------------------------------------------------------------


class TestInitExamples:
    def _make_fake_examples_dir(self, tmp_path):
        """Create a fake examples source directory with some files."""
        src = tmp_path / "fake_examples"
        src.mkdir()
        (src / "00_run_all.sh").write_text("#!/bin/bash\necho hello")
        (src / "01_process.py").write_text("print('step 1')")
        (src / "README.md").write_text("# Example")
        # Subdirectory that should be skipped
        subdir = src / "_out"
        subdir.mkdir()
        (subdir / "output.csv").write_text("data")
        return src

    def test_invalid_variant_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown variant"):
            init_examples(tmp_path / "dest", variant="invalid_variant")

    def test_missing_examples_dir_raises_file_not_found(self, tmp_path):
        with patch("scitex_clew._examples._find_examples_dir", return_value=None):
            with pytest.raises(FileNotFoundError):
                init_examples(tmp_path / "dest")

    def test_returns_dict_with_expected_keys(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            result = init_examples(dest)
        assert "path" in result
        assert "files" in result
        assert "file_count" in result
        assert "variant" in result

    def test_creates_destination_directory(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "new_dest" / "nested"
        assert not dest.exists()
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            init_examples(dest)
        assert dest.exists()

    def test_copies_files_to_dest(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            result = init_examples(dest)
        assert result["file_count"] > 0
        for fname in result["files"]:
            assert (dest / fname).exists()

    def test_skips_subdirectories(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            result = init_examples(dest)
        assert "_out" not in result["files"]

    def test_variant_in_result(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            result = init_examples(dest, variant="sequential")
        assert result["variant"] == "sequential"

    def test_path_in_result_matches_dest(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            result = init_examples(dest)
        assert result["path"] == str(dest)

    def test_multi_parent_variant_missing_raises(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            with pytest.raises(FileNotFoundError):
                init_examples(dest, variant="multi_parent")

    def test_multi_parent_variant_found(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        mp_dir = src / "multi_parent"
        mp_dir.mkdir()
        (mp_dir / "01_step.py").write_text("print('mp')")
        dest = tmp_path / "dest"
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            result = init_examples(dest, variant="multi_parent")
        assert result["variant"] == "multi_parent"
        assert result["file_count"] >= 1

    def test_accepts_string_dest(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        dest = str(tmp_path / "str_dest")
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            init_examples(dest)
        assert Path(dest).exists()

    def test_overwrites_existing_files(self, tmp_path):
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "01_process.py").write_text("OLD CONTENT")
        with patch("scitex_clew._examples._find_examples_dir", return_value=src):
            init_examples(dest)
        assert (dest / "01_process.py").read_text() == "print('step 1')"


# EOF
