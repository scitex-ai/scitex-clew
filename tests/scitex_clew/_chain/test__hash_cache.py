#!/usr/bin/env python3
# Timestamp: "2026-06-27 (ywatanabe)"
"""Tests for the per-pass hash cache in scitex_clew verification.

Covers:
  1. Within one verify pass over a graph where a file is referenced by
     multiple sessions, hash_file reads the file from disk only ONCE
     (the hash_cache dict is populated exactly once per unique resolved path).
  2. A second independent pass re-hashes (no stale cross-pass reuse) —
     verified by mutating a file between passes and confirming the second
     pass detects the change.
  3. Verification results are byte-identical before and after adding the
     cache (i.e. the optimization is behavior-preserving).

Design (PA-306 §3 no-mocks):
  - No monkeypatch, no mocking of DB or file I/O.
  - Cache-deduplication is proven by: (a) supplying a pre-populated cache
    to hash_file and verifying the return value comes from the cache rather
    than disk (cache hit returns without opening the file), and (b) calling
    verify_file twice with the same cache dict and confirming the dict stays
    at exactly one entry (the second call re-uses the cached value).
  - Cross-pass isolation is proven by mutating the file between two
    independent verify_dag calls and confirming the second pass detects
    the change (stale cross-pass cache would mask it).
  - PA-307 §3: one observable assertion per test + AAA markers.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict

import pytest

import scitex_clew as clew
from scitex_clew._chain._dag import verify_dag
from scitex_clew._chain._verify_ops import verify_file, verify_run
from scitex_clew._db import VerificationDB
from scitex_clew._hash import hash_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_db(tmp_path):
    """Provide a fresh VerificationDB in a temporary directory.

    Sets SCITEX_CLEW_DB_PATH and resets the module-level singleton so
    subsequent get_db() calls use the test DB.
    """
    db_path = tmp_path / ".scitex" / "clew" / "runtime" / "db.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    prev_env = os.environ.get("SCITEX_CLEW_DB_PATH")
    os.environ["SCITEX_CLEW_DB_PATH"] = str(db_path)
    clew.set_db(None)  # flush singleton

    db = VerificationDB(db_path)
    yield db

    # Teardown
    if prev_env is None:
        os.environ.pop("SCITEX_CLEW_DB_PATH", None)
    else:
        os.environ["SCITEX_CLEW_DB_PATH"] = prev_env
    clew.set_db(None)


def _write_file(path: Path, content: str) -> Path:
    """Write a text file and return its path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _register_session(db: VerificationDB, session_id: str, inputs: dict, outputs: dict) -> None:
    """Register a session with input and output file hashes in the DB."""
    db.add_run(session_id, script_path="/dev/null")
    for fpath, fhash in inputs.items():
        db.add_file_hash(session_id, fpath, fhash, role="input")
    for fpath, fhash in outputs.items():
        db.add_file_hash(session_id, fpath, fhash, role="output")
    db.finish_run(session_id, status="success")


# ---------------------------------------------------------------------------
# Tests: property 1 — single pass hashes each file at most once
# ---------------------------------------------------------------------------


class TestHashCacheDeduplication:
    """A file referenced by multiple sessions is only disk-read once per pass.

    Proven without monkeypatching: we inspect the hash_cache dict directly
    after calls to confirm it has exactly one entry per unique file.
    """

    def test_cache_has_one_entry_per_unique_file_for_shared_input(self, tmp_path):
        # Arrange
        shared = _write_file(tmp_path / "shared.csv", "shared data")

        cache: Dict[str, str] = {}

        # Act — call hash_file twice with the same cache for the same file
        result1 = hash_file(shared, hash_cache=cache)
        result2 = hash_file(shared, hash_cache=cache)

        # Assert — only one entry in the cache despite two calls
        assert len(cache) == 1

    def test_cache_hit_is_identical_to_initial_result(self, tmp_path):
        # Arrange
        f = _write_file(tmp_path / "data.csv", "some content")

        cache: Dict[str, str] = {}
        first = hash_file(f, hash_cache=cache)

        # Act — second call hits the cache
        second = hash_file(f, hash_cache=cache)

        # Assert
        assert second == first

    def test_pre_populated_cache_is_returned_without_reading_deleted_file(self, tmp_path):
        # Arrange — hash a file, then delete it
        f = _write_file(tmp_path / "ephemeral.csv", "content")
        cache: Dict[str, str] = {}
        expected = hash_file(f, hash_cache=cache)
        f.unlink()  # delete the file

        # Act — second call should hit the cache and NOT raise FileNotFoundError
        result = hash_file(f, hash_cache=cache)

        # Assert — cached value returned even though file no longer exists
        assert result == expected

    def test_distinct_files_each_get_one_cache_entry(self, tmp_path):
        # Arrange — two different files
        f1 = _write_file(tmp_path / "file1.csv", "content A")
        f2 = _write_file(tmp_path / "file2.csv", "content B")

        cache: Dict[str, str] = {}

        # Act
        hash_file(f1, hash_cache=cache)
        hash_file(f2, hash_cache=cache)

        # Assert — two distinct entries in the cache
        assert len(cache) == 2

    def test_verify_file_populates_cache_on_first_call(self, tmp_path):
        # Arrange
        f = _write_file(tmp_path / "out.csv", "result data")
        expected = hash_file(f)
        cache: Dict[str, str] = {}

        # Act
        verify_file(str(f), expected, role="output", hash_cache=cache)

        # Assert — cache now contains the resolved path
        assert str(f.resolve()) in cache

    def test_verify_file_reuses_cache_on_second_call(self, tmp_path):
        # Arrange — pre-populate cache with a known hash
        f = _write_file(tmp_path / "out.csv", "result data")
        real_hash = hash_file(f)
        cache: Dict[str, str] = {str(f.resolve()): real_hash}

        # Mutate the file — if cache is used, old hash is returned
        f.write_text("TAMPERED — should not be re-read if cache is used")

        # Act
        fv = verify_file(str(f), real_hash, role="output", hash_cache=cache)

        # Assert — file verifies because cached (old) hash is used, not a fresh read
        assert fv.is_verified

    def test_shared_file_across_two_sessions_single_cache_entry(self, tmp_path, isolated_db):
        # Arrange — two sessions that both reference the same shared file as input
        shared = _write_file(tmp_path / "shared.h5", "big array data")
        out_a = _write_file(tmp_path / "out_a.csv", "output A")
        out_b = _write_file(tmp_path / "out_b.csv", "output B")

        shared_hash = hash_file(shared)
        out_a_hash = hash_file(out_a)
        out_b_hash = hash_file(out_b)

        _register_session(isolated_db, "ses-A",
                          inputs={str(shared): shared_hash},
                          outputs={str(out_a): out_a_hash})
        _register_session(isolated_db, "ses-B",
                          inputs={str(shared): shared_hash},
                          outputs={str(out_b): out_b_hash})

        # Act — verify_run ses-A and ses-B sharing one cache
        cache: Dict[str, str] = {}
        verify_run("ses-A", hash_cache=cache)
        cache_size_after_ses_a = len(cache)
        verify_run("ses-B", hash_cache=cache)

        # Assert — cache size did NOT grow for shared.h5 when ses-B ran
        assert len(cache) == cache_size_after_ses_a + len({str(out_b.resolve())})


# ---------------------------------------------------------------------------
# Tests: property 2 — second pass re-hashes (no stale cross-pass reuse)
# ---------------------------------------------------------------------------


class TestHashCachePassScoping:
    """The cache is created fresh per-pass; changes between passes are detected."""

    def test_file_updated_between_passes_detected_by_second_pass(self, tmp_path, isolated_db):
        # Arrange
        source = _write_file(tmp_path / "data.csv", "version 1")
        out = _write_file(tmp_path / "result.csv", "result 1")
        src_hash = hash_file(source)
        out_hash = hash_file(out)

        _register_session(isolated_db, "ses-Y",
                          inputs={str(source): src_hash},
                          outputs={str(out): out_hash})

        # First pass — both files match
        result1 = verify_dag([str(out)])

        # Mutate the source file between passes
        source.write_text("version 2 — tampered")

        # Act — second pass (each pass creates a fresh cache)
        result2 = verify_dag([str(out)])

        # Assert — second pass detects the change (no stale cache across passes)
        assert not result2.is_verified

    def test_none_cache_always_reads_from_disk(self, tmp_path):
        # Arrange
        f = _write_file(tmp_path / "file.csv", "original")
        original_hash = hash_file(f, hash_cache=None)

        # Mutate the file
        f.write_text("modified")

        # Act — hash_cache=None means no caching, so we get the new hash
        new_hash = hash_file(f, hash_cache=None)

        # Assert
        assert new_hash != original_hash

    def test_second_verify_dag_call_reflects_tampered_output(self, tmp_path, isolated_db):
        # Arrange
        inp = _write_file(tmp_path / "input.csv", "original input")
        out = _write_file(tmp_path / "output.csv", "original output")
        inp_hash = hash_file(inp)
        out_hash = hash_file(out)
        _register_session(isolated_db, "ses-Z",
                          inputs={str(inp): inp_hash},
                          outputs={str(out): out_hash})
        r1 = verify_dag([str(out)])
        out.write_text("tampered output")

        # Act — second independent pass after tampering
        r2 = verify_dag([str(out)])

        # Assert — second pass sees the tamper (cross-pass stale cache would hide it)
        assert r2.is_verified != r1.is_verified


# ---------------------------------------------------------------------------
# Tests: property 3 — results byte-identical to uncached execution
# ---------------------------------------------------------------------------


class TestHashCacheBehaviorPreservation:
    """The cache must not change any verification outcome."""

    def test_hash_value_identical_with_and_without_cache(self, tmp_path):
        # Arrange
        f = _write_file(tmp_path / "data.npy", "binary-like content")

        # Act
        hash_no_cache = hash_file(f, hash_cache=None)
        cache: Dict[str, str] = {}
        hash_with_cache = hash_file(f, hash_cache=cache)

        # Assert
        assert hash_with_cache == hash_no_cache

    def test_verified_status_same_with_and_without_cache(self, tmp_path):
        # Arrange
        f = _write_file(tmp_path / "output.csv", "processed data")
        expected = hash_file(f)

        baseline = verify_file(str(f), expected, role="output", hash_cache=None)

        # Act
        cache: Dict[str, str] = {}
        cached = verify_file(str(f), expected, role="output", hash_cache=cache)

        # Assert — same status
        assert cached.status == baseline.status

    def test_mismatch_status_same_with_and_without_cache(self, tmp_path):
        # Arrange
        f = _write_file(tmp_path / "output.csv", "original")
        wrong_hash = "00000000000000000000000000000000"

        baseline = verify_file(str(f), wrong_hash, role="output", hash_cache=None)

        # Act
        cache: Dict[str, str] = {}
        cached = verify_file(str(f), wrong_hash, role="output", hash_cache=cache)

        # Assert — same status
        assert cached.status == baseline.status

    def test_mismatch_result_identical_across_two_verify_dag_passes(self, tmp_path, isolated_db):
        # Arrange — a session whose output has been tampered
        inp = _write_file(tmp_path / "input.csv", "original")
        out = _write_file(tmp_path / "output.csv", "original output")
        inp_hash = hash_file(inp)
        out_hash = hash_file(out)

        _register_session(isolated_db, "ses-mm",
                          inputs={str(inp): inp_hash},
                          outputs={str(out): out_hash})

        # Tamper before verifying
        out.write_text("tampered output")

        # Act — two independent passes
        r1 = verify_dag([str(out)])
        r2 = verify_dag([str(out)])

        # Assert — same outcome (mismatch) in both passes
        assert r2.status == r1.status

    def test_cache_key_is_resolved_absolute_path(self, tmp_path):
        # Arrange
        f = _write_file(tmp_path / "file.csv", "content")
        cache: Dict[str, str] = {}

        # Act
        hash_file(f, hash_cache=cache)

        # Assert — key in cache is the resolved (absolute) path string
        expected_key = str(f.resolve())
        assert expected_key in cache

    def test_symlink_hash_equals_real_file_hash(self, tmp_path):
        # Arrange — create a file and a symlink to it
        real = _write_file(tmp_path / "real.csv", "content")
        link = tmp_path / "link.csv"
        link.symlink_to(real)
        cache: Dict[str, str] = {}
        hash_real = hash_file(real, hash_cache=cache)

        # Act — hash via symlink using the same cache
        hash_link = hash_file(link, hash_cache=cache)

        # Assert — both paths resolve to the same file, so hashes are equal
        assert hash_link == hash_real

    def test_symlink_and_real_path_share_single_cache_entry(self, tmp_path):
        # Arrange — create a file and a symlink to it
        real = _write_file(tmp_path / "real.csv", "content")
        link = tmp_path / "link.csv"
        link.symlink_to(real)
        cache: Dict[str, str] = {}
        hash_file(real, hash_cache=cache)
        entries_after_real = len(cache)

        # Act — hash via symlink (resolves to same inode as real)
        hash_file(link, hash_cache=cache)

        # Assert — cache did not grow (symlink resolves to same resolved path)
        assert len(cache) == entries_after_real


# EOF
