#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/tests/scitex/verify/test__hash.py

"""Tests for scitex.clew._hash module."""

import hashlib

import pytest

from scitex_clew import (
    combine_hashes,
    hash_directory,
    hash_file,
    hash_files,
    verify_hash,
)


class TestHashFile:
    """Tests for hash_file function."""

    def test_hash_file_basic_result_is_str(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        # Hash the file
        # Act
        # Act
        result = hash_file(test_file)
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_hash_file_basic_len_result_is_64(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        # Hash the file
        # Act
        # Act
        result = hash_file(test_file)
        # Act
        # Assert
        # Assert
        # Assert
        # sha256 hex digest is 64 chars — the full digest, not the pre-fix
        # 32-char truncation (clew-fix-truncated-hash-comparison).
        assert len(result) == 64

    def test_hash_file_matches_full_hashlib_sha256_digest(self, tmp_path):
        """Regression test for clew-fix-truncated-hash-comparison.

        Before the fix, ``hash_file`` truncated the digest to the first 32
        of 64 hex chars, so the "obvious" comparison against an
        independently-computed ``hashlib.sha256(...).hexdigest()`` was
        ALWAYS False — silently and permanently — even though the file was
        byte-identical. This asserts the full 64-char digest is returned and
        matches bit-for-bit, not merely "starts with".
        """
        # Arrange
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"some real file content \x00\xff for hashing")

        # Act
        result = hash_file(test_file)
        expected = hashlib.sha256(test_file.read_bytes()).hexdigest()

        # Assert
        assert len(expected) == 64 and result == expected

    def test_hash_file_basic_all_c_in_0123456789abcdef_for_c_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        # Hash the file
        # Act
        # Act
        result = hash_file(test_file)
        # Act
        # Assert
        # Assert
        # Assert
        assert all(c in "0123456789abcdef" for c in result)


    def test_hash_file_deterministic(self, tmp_path):
        """Test that same content produces same hash."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Same content")

        hash1 = hash_file(test_file)
        # Act
        hash2 = hash_file(test_file)

        # Assert
        assert hash1 == hash2

    def test_hash_file_different_content(self, tmp_path):
        """Test that different content produces different hash."""
        # Arrange
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content A")
        file2.write_text("Content B")

        hash1 = hash_file(file1)
        # Act
        hash2 = hash_file(file2)

        # Assert
        assert hash1 != hash2

    def test_hash_file_not_found(self, tmp_path):
        """Test that missing file raises FileNotFoundError."""
        # Arrange
        # Act
        # Assert
        with pytest.raises(FileNotFoundError):
            hash_file(tmp_path / "nonexistent.txt")

    def test_hash_file_binary_result_is_str(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")
        # Act
        # Act
        result = hash_file(test_file)
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_hash_file_binary_len_result_is_64(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")
        # Act
        # Act
        result = hash_file(test_file)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 64


    def test_hash_file_empty_result_is_str(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")
        # Act
        # Act
        result = hash_file(test_file)
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_hash_file_empty_len_result_is_64(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")
        # Act
        # Act
        result = hash_file(test_file)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 64


    def test_hash_file_path_types(self, tmp_path):
        """Test that both str and Path work."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        hash_from_path = hash_file(test_file)
        # Act
        hash_from_str = hash_file(str(test_file))

        # Assert
        assert hash_from_path == hash_from_str


class TestHashDirectory:
    """Tests for hash_directory function."""

    def test_hash_directory_basic_result_is_dict(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        (tmp_path / "file1.txt").write_text("Content 1")
        (tmp_path / "file2.txt").write_text("Content 2")
        # Act
        # Act
        result = hash_directory(tmp_path)
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result, dict)

    def test_hash_directory_basic_len_result_is_2(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        (tmp_path / "file1.txt").write_text("Content 1")
        (tmp_path / "file2.txt").write_text("Content 2")
        # Act
        # Act
        result = hash_directory(tmp_path)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 2

    def test_hash_directory_basic_file1_txt_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        (tmp_path / "file1.txt").write_text("Content 1")
        (tmp_path / "file2.txt").write_text("Content 2")
        # Act
        # Act
        result = hash_directory(tmp_path)
        # Act
        # Assert
        # Assert
        # Assert
        assert "file1.txt" in result

    def test_hash_directory_basic_file2_txt_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        (tmp_path / "file1.txt").write_text("Content 1")
        (tmp_path / "file2.txt").write_text("Content 2")
        # Act
        # Act
        result = hash_directory(tmp_path)
        # Act
        # Assert
        # Assert
        # Assert
        assert "file2.txt" in result


    def test_hash_directory_recursive_len_result_is_2(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file1.txt").write_text("Root file")
        (subdir / "file2.txt").write_text("Subdir file")
        # Act
        # Act
        result = hash_directory(tmp_path, recursive=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 2

    def test_hash_directory_recursive_file1_txt_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file1.txt").write_text("Root file")
        (subdir / "file2.txt").write_text("Subdir file")
        # Act
        # Act
        result = hash_directory(tmp_path, recursive=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert "file1.txt" in result

    def test_hash_directory_recursive_subdir_file2_txt_in_result_or_subdir_file2_txt_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file1.txt").write_text("Root file")
        (subdir / "file2.txt").write_text("Subdir file")
        # Act
        # Act
        result = hash_directory(tmp_path, recursive=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert "subdir/file2.txt" in result or "subdir\\file2.txt" in result


    def test_hash_directory_non_recursive_len_result_is_1(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file1.txt").write_text("Root file")
        (subdir / "file2.txt").write_text("Subdir file")
        # Act
        # Act
        result = hash_directory(tmp_path, recursive=False)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 1

    def test_hash_directory_non_recursive_file1_txt_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file1.txt").write_text("Root file")
        (subdir / "file2.txt").write_text("Subdir file")
        # Act
        # Act
        result = hash_directory(tmp_path, recursive=False)
        # Act
        # Assert
        # Assert
        # Assert
        assert "file1.txt" in result


    def test_hash_directory_pattern_len_result_is_1(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        (tmp_path / "data.csv").write_text("csv data")
        (tmp_path / "config.json").write_text("{}")
        # Act
        # Act
        result = hash_directory(tmp_path, pattern="*.csv")
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 1

    def test_hash_directory_pattern_data_csv_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        (tmp_path / "data.csv").write_text("csv data")
        (tmp_path / "config.json").write_text("{}")
        # Act
        # Act
        result = hash_directory(tmp_path, pattern="*.csv")
        # Act
        # Assert
        # Assert
        # Assert
        assert "data.csv" in result


    def test_hash_directory_not_a_directory(self, tmp_path):
        """Test that file path raises NotADirectoryError."""
        # Arrange
        test_file = tmp_path / "test.txt"
        # Act
        test_file.write_text("test")

        # Assert
        with pytest.raises(NotADirectoryError):
            hash_directory(test_file)

    def test_hash_directory_empty(self, tmp_path):
        """Test hashing empty directory."""
        # Arrange
        # Act
        result = hash_directory(tmp_path)
        # Assert
        assert result == {}


class TestHashFiles:
    """Tests for hash_files function."""

    def test_hash_files_basic_result_is_dict(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")
        # Act
        # Act
        result = hash_files([file1, file2])
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result, dict)

    def test_hash_files_basic_len_result_is_2(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")
        # Act
        # Act
        result = hash_files([file1, file2])
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 2

    def test_hash_files_basic_str_file1_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")
        # Act
        # Act
        result = hash_files([file1, file2])
        # Act
        # Assert
        # Assert
        # Assert
        assert str(file1) in result

    def test_hash_files_basic_str_file2_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("Content 1")
        file2.write_text("Content 2")
        # Act
        # Act
        result = hash_files([file1, file2])
        # Act
        # Assert
        # Assert
        # Assert
        assert str(file2) in result


    def test_hash_files_missing_file_len_result_is_1(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        file1 = tmp_path / "exists.txt"
        file2 = tmp_path / "missing.txt"
        file1.write_text("Content")
        # Act
        # Act
        result = hash_files([file1, file2])
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 1

    def test_hash_files_missing_file_str_file1_in_result(self, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        file1 = tmp_path / "exists.txt"
        file2 = tmp_path / "missing.txt"
        file1.write_text("Content")
        # Act
        # Act
        result = hash_files([file1, file2])
        # Act
        # Assert
        # Assert
        # Assert
        assert str(file1) in result


    def test_hash_files_empty_list(self):
        """Test hashing empty list."""
        # Arrange
        # Act
        result = hash_files([])
        # Assert
        assert result == {}


class TestCombineHashes:
    """Tests for combine_hashes function."""

    def test_combine_hashes_basic_result_is_str(self):
        # Arrange
        # Arrange
        # Arrange
        hashes = {"file1": "abc123", "file2": "def456"}
        # Act
        # Act
        result = combine_hashes(hashes)
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_combine_hashes_basic_len_result_is_64(self):
        # Arrange
        # Arrange
        # Arrange
        hashes = {"file1": "abc123", "file2": "def456"}
        # Act
        # Act
        result = combine_hashes(hashes)
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 64


    def test_combine_hashes_deterministic(self):
        """Test that same hashes produce same combined hash."""
        # Arrange
        hashes = {"a": "hash1", "b": "hash2"}

        result1 = combine_hashes(hashes)
        # Act
        result2 = combine_hashes(hashes)

        # Assert
        assert result1 == result2

    def test_combine_hashes_order_independent(self):
        """Test that key order doesn't matter (sorted internally)."""
        # Arrange
        hashes1 = {"a": "hash1", "b": "hash2"}
        hashes2 = {"b": "hash2", "a": "hash1"}

        result1 = combine_hashes(hashes1)
        # Act
        result2 = combine_hashes(hashes2)

        # Assert
        assert result1 == result2

    def test_combine_hashes_different_content(self):
        """Test that different hashes produce different combined hash."""
        # Arrange
        hashes1 = {"a": "hash1", "b": "hash2"}
        hashes2 = {"a": "hash1", "b": "hash3"}

        result1 = combine_hashes(hashes1)
        # Act
        result2 = combine_hashes(hashes2)

        # Assert
        assert result1 != result2

    def test_combine_hashes_empty_result_is_str(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = combine_hashes({})
        # Act
        # Assert
        # Assert
        # Assert
        assert isinstance(result, str)

    def test_combine_hashes_empty_len_result_is_64(self):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = combine_hashes({})
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result) == 64



class TestVerifyHash:
    """Tests for verify_hash function."""

    def test_verify_hash_match(self, tmp_path):
        """Test verification when hash matches."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        expected = hash_file(test_file)
        # Act
        result = verify_hash(test_file, expected)

        # Assert
        assert result is True

    def test_verify_hash_mismatch(self, tmp_path):
        """Test verification when hash doesn't match."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        # Act
        result = verify_hash(test_file, "wronghash12345678901234567890ab")

        # Assert
        assert result is False

    def test_verify_hash_missing_file(self, tmp_path):
        """Test verification of missing file returns False."""
        # Arrange
        # Act
        result = verify_hash(tmp_path / "missing.txt", "somehash")
        # Assert
        assert result is False

    def test_verify_hash_truncated(self, tmp_path):
        """Test verification with truncated hash."""
        # Arrange
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        full_hash = hash_file(test_file)
        short_hash = full_hash[:16]

        # Act
        result = verify_hash(test_file, short_hash)
        # Assert
        assert result is True


# EOF
