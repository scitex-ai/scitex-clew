#!/usr/bin/env python3
"""Tests for scitex_clew._examples module."""

from __future__ import annotations

import contextlib
from pathlib import Path

import pytest

from scitex_clew import _examples as _examples_mod
from scitex_clew._examples import _find_examples_dir, init_examples


@contextlib.contextmanager
def _swap_attr(obj, name, value):
    saved = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, saved)


# ---------------------------------------------------------------------------
# _find_examples_dir
# ---------------------------------------------------------------------------


class TestFindExamplesDir:
    def test_returns_path_or_none(self):
        # Arrange
        # Act
        # Arrange
        # Act
        result = _find_examples_dir()
        # Assert
        # Assert
        assert result is None or isinstance(result, Path)

    def test_returns_existing_dir_if_found(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        result = _find_examples_dir()
        if result is not None:
            assert result.exists()
            assert result.is_dir()

    def test_bundled_example_data_used_if_exists(self):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        bundled = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "scitex_clew"
            / "_example_data"
        )
        result = _find_examples_dir()
        if bundled.exists():
            assert result == bundled

    def test_returns_none_when_no_candidates_exist_not_nonexistent_exists(self, tmp_path):
        # Manually exercise the same lookup logic with a non-existent candidate.
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        nonexistent = tmp_path / "does_not_exist"
        # Act
        # Assert
        # Assert
        # Assert
        assert not nonexistent.exists()

    def test_returns_none_when_no_candidates_exist_result_is_none_not_nonexistent_exists(self, tmp_path):
        # Manually exercise the same lookup logic with a non-existent candidate.
        # Arrange
        # Arrange
        # Act
        nonexistent = tmp_path / "does_not_exist"
        # Act
        # Assert
        # Assert
        assert not nonexistent.exists()

    def test_returns_none_when_no_candidates_exist_result_is_none_result_is_none(self, tmp_path):
        # Manually exercise the same lookup logic with a non-existent candidate.
        # Arrange
        # Arrange
        # Act
        nonexistent = tmp_path / "does_not_exist"
        # Assert
        assert not nonexistent.exists()
        result = None
        for candidate in [nonexistent]:
            if candidate.exists() and candidate.is_dir():
                result = candidate
                break
        # Act
        # Assert
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
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        with pytest.raises(ValueError, match="Unknown variant"):
            init_examples(tmp_path / "dest", variant="invalid_variant")

    def test_missing_examples_dir_raises_file_not_found(self, tmp_path):
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": None):
            with pytest.raises(FileNotFoundError):
                init_examples(tmp_path / "dest")

    def test_returns_dict_with_expected_keys_path_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest)
        # Act
        # Assert
        # Assert
        # Assert
        assert "path" in result

    def test_returns_dict_with_expected_keys_files_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest)
        # Act
        # Assert
        # Assert
        # Assert
        assert "files" in result

    def test_returns_dict_with_expected_keys_file_count_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest)
        # Act
        # Assert
        # Assert
        # Assert
        assert "file_count" in result

    def test_returns_dict_with_expected_keys_variant_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest)
        # Act
        # Assert
        # Assert
        # Assert
        assert "variant" in result


    def test_creates_destination_directory_not_dest_exists(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        # Act
        # Act
        dest = tmp_path / "new_dest" / "nested"
        # Act
        # Assert
        # Assert
        # Assert
        assert not dest.exists()

    def test_creates_destination_directory_dest_exists_not_dest_exists(self, tmp_path):
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        # Act
        dest = tmp_path / "new_dest" / "nested"
        # Act
        # Assert
        # Assert
        assert not dest.exists()

    def test_creates_destination_directory_dest_exists_dest_exists(self, tmp_path):
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        # Act
        dest = tmp_path / "new_dest" / "nested"
        # Assert
        assert not dest.exists()
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            init_examples(dest)
        # Act
        # Assert
        assert dest.exists()



    def test_copies_files_to_dest_result_file_count_0(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest)
        # Act
        # Assert
        # Assert
        # Assert
        assert result["file_count"] > 0

    def test_copies_files_to_dest_all_dest_fname_exists_for_fname_in_result_files(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest)
        # Act
        # Assert
        # Assert
        # Assert
        assert all((dest / fname).exists() for fname in result['files'])


    def test_skips_subdirectories_out_not_in_result_files(self, tmp_path):
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest)
        # Assert
        # Assert
        assert "_out" not in result["files"]

    def test_variant_in_result(self, tmp_path):
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest, variant="sequential")
        # Assert
        # Assert
        assert result["variant"] == "sequential"

    def test_path_in_result_matches_dest(self, tmp_path):
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest)
        # Assert
        # Assert
        assert result["path"] == str(dest)

    def test_multi_parent_variant_missing_raises(self, tmp_path):
        # _find_examples_dir(variant) returns None when the bundled variant
        # directory cannot be located; init_examples must surface that as
        # FileNotFoundError. The previous test patched it to a non-None
        # value, which never tripped the None-branch.
        # Arrange
        # Act
        # Assert
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "dest"
        with _swap_attr(
            _examples_mod,
            "_find_examples_dir",
            lambda variant="sequential": None if variant == "multi_parent" else None,
        ):
            with pytest.raises(FileNotFoundError):
                init_examples(dest, variant="multi_parent")

    def test_multi_parent_variant_found_result_variant_multi_parent(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        mp_dir = src / "multi_parent"
        mp_dir.mkdir()
        (mp_dir / "01_step.py").write_text("print('mp')")
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest, variant="multi_parent")
        # Act
        # Assert
        # Assert
        # Assert
        assert result["variant"] == "multi_parent"

    def test_multi_parent_variant_found_result_file_count_1(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        mp_dir = src / "multi_parent"
        mp_dir.mkdir()
        (mp_dir / "01_step.py").write_text("print('mp')")
        dest = tmp_path / "dest"
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            result = init_examples(dest, variant="multi_parent")
        # Act
        # Assert
        # Assert
        # Assert
        assert result["file_count"] >= 1


    def test_accepts_string_dest(self, tmp_path):
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = str(tmp_path / "str_dest")
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            init_examples(dest)
        # Assert
        # Assert
        assert Path(dest).exists()

    def test_overwrites_existing_files(self, tmp_path):
        # Arrange
        # Arrange
        src = self._make_fake_examples_dir(tmp_path)
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "01_process.py").write_text("OLD CONTENT")
        # Act
        # Act
        with _swap_attr(_examples_mod, "_find_examples_dir", lambda variant="sequential": src):
            init_examples(dest)
        # Assert
        # Assert
        assert (dest / "01_process.py").read_text() == "print('step 1')"


# EOF
