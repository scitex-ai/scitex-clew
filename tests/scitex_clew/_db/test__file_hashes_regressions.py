#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for two dogfooding-discovered VerificationDB bugs.

Both bugs were "confident wrong answer, no exception, no log line" failures
in scitex_clew._db._file_hashes (FileHashMixin) — exactly the failure class
clew exists to prevent, except happening INSIDE clew's own query layer.

* clew-fix-path-normalization-find-session — ``find_session_by_file`` /
  ``find_sessions_by_files`` did not normalize the query path the way
  ``verify_chain`` normalizes its own ``target`` argument
  (``str(Path(target).resolve())``), so a RELATIVE query path silently
  matched nothing even though the equivalent absolute path matched fine.

* clew-fix-truncated-hash-comparison — ``hash_file`` (and
  ``hash_archived_file``/``hash_archive_members``) truncated the sha256
  hex digest to the first 32 of 64 characters at WRITE time, so
  ``get_file_hashes(session)[path] ==
  hashlib.sha256(open(path, "rb").read()).hexdigest()`` was always False
  for every tracked file, forever, with no error.

Split out from test__file_hashes.py (which is already near the repo's
512-line/file limit) rather than growing that file further.

All tests use a real temp VerificationDB and real files on disk — no mocks
(PA-307). Each test contains exactly one assertion, with
# Arrange / # Act / # Assert markers each on its own line in that order.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from scitex_clew import VerificationDB
from scitex_clew._hash import hash_file


def _make_db(tmp_path, name="test.db"):
    return VerificationDB(tmp_path / name)


@pytest.fixture
def chdir_tmp(tmp_path):
    """cd into ``tmp_path`` for the test, restoring cwd after (no mocks:
    manual os.chdir + restore, not ``monkeypatch.chdir`` — PA-306 §3)."""
    prev = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(prev)


# ---------------------------------------------------------------------------
# clew-fix-path-normalization-find-session
# ---------------------------------------------------------------------------


class TestFindSessionByFilePathNormalization:
    """A relative query path must return the SAME result as its absolute
    equivalent — the same "does clew know about this file" question should
    get the same answer regardless of how the path was spelled."""

    def test_relative_path_finds_the_producer_session(self, tmp_path, chdir_tmp):
        # Arrange
        db = _make_db(tmp_path, name="norm1.db")
        abs_path = str(tmp_path / "data" / "out.csv")
        db.add_run("producer", script_path="/scripts/producer.py")
        db.add_file_hash("producer", abs_path, "deadbeef", "output")
        # Act
        found = db.find_session_by_file("data/out.csv", role="output")
        # Assert
        assert found == ["producer"]

    def test_relative_and_absolute_queries_return_identical_result(
        self, tmp_path, chdir_tmp
    ):
        # Arrange
        db = _make_db(tmp_path, name="norm2.db")
        abs_path = str(tmp_path / "data" / "out.csv")
        db.add_run("producer", script_path="/scripts/producer.py")
        db.add_file_hash("producer", abs_path, "deadbeef", "output")
        # Act
        by_relative = db.find_session_by_file("data/out.csv", role="output")
        by_absolute = db.find_session_by_file(abs_path, role="output")
        # Assert
        assert by_relative == by_absolute

    def test_dotted_relative_path_also_normalizes(self, tmp_path, chdir_tmp):
        # Arrange — "./data/out.csv" and "data/out.csv" must be equivalent.
        db = _make_db(tmp_path, name="norm3.db")
        abs_path = str(tmp_path / "data" / "out.csv")
        db.add_run("producer", script_path="/scripts/producer.py")
        db.add_file_hash("producer", abs_path, "deadbeef", "output")
        # Act
        found = db.find_session_by_file("./data/out.csv", role="output")
        # Assert
        assert found == ["producer"]

    def test_no_role_filter_relative_path_still_normalizes(
        self, tmp_path, chdir_tmp
    ):
        # Arrange
        db = _make_db(tmp_path, name="norm4.db")
        abs_path = str(tmp_path / "out.csv")
        db.add_run("producer", script_path="/scripts/producer.py")
        db.add_file_hash("producer", abs_path, "deadbeef", "output")
        # Act
        found = db.find_session_by_file("out.csv")
        # Assert
        assert found == ["producer"]


class TestFindSessionsByFilesPathNormalization:
    """Batch counterpart: same normalization, keyed by the caller's
    original (un-resolved) spelling so ``result[p]`` works for whatever
    ``p`` was passed in ``file_paths``."""

    def test_relative_path_in_batch_finds_producer(self, tmp_path, chdir_tmp):
        # Arrange
        db = _make_db(tmp_path, name="norm5.db")
        abs_path = str(tmp_path / "out.csv")
        db.add_run("producer", script_path="/scripts/producer.py")
        db.add_file_hash("producer", abs_path, "deadbeef", "output")
        # Act
        result = db.find_sessions_by_files(["out.csv"], role="output")
        # Assert
        assert result == {"out.csv": ["producer"]}

    def test_result_keyed_by_original_spelling_not_resolved_form(
        self, tmp_path, chdir_tmp
    ):
        # Arrange
        db = _make_db(tmp_path, name="norm6.db")
        abs_path = str(tmp_path / "sub" / "out.csv")
        db.add_run("producer", script_path="/scripts/producer.py")
        db.add_file_hash("producer", abs_path, "deadbeef", "output")
        # Act
        result = db.find_sessions_by_files(["sub/out.csv"], role="output")
        # Assert
        assert abs_path not in result

    def test_mixed_relative_and_absolute_paths_both_resolve(
        self, tmp_path, chdir_tmp
    ):
        # Arrange
        db = _make_db(tmp_path, name="norm7.db")
        abs_a = str(tmp_path / "a.csv")
        abs_b = str(tmp_path / "b.csv")
        db.add_run("prod_a", script_path="/a.py")
        db.add_run("prod_b", script_path="/b.py")
        db.add_file_hash("prod_a", abs_a, "ha", "output")
        db.add_file_hash("prod_b", abs_b, "hb", "output")
        # Act
        result = db.find_sessions_by_files(["a.csv", abs_b], role="output")
        # Assert
        assert result == {"a.csv": ["prod_a"], abs_b: ["prod_b"]}


# ---------------------------------------------------------------------------
# clew-fix-truncated-hash-comparison
# ---------------------------------------------------------------------------


class TestGetFileHashesFullDigest:
    """get_file_hashes must return the FULL sha256 digest recorded for a
    real tracked file, matching an independently-computed
    hashlib.sha256(...).hexdigest() exactly — not merely a shared prefix."""

    def test_recorded_hash_equals_independently_computed_sha256(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path, name="hash1.db")
        tracked = tmp_path / "tracked.csv"
        tracked.write_bytes(b"a,b\n1,2\n" * 100)
        db.add_run("s_full", script_path="/script.py")
        db.add_file_hash("s_full", str(tracked), hash_file(tracked), "output")
        # Act
        recorded = db.get_file_hashes("s_full", role="output")[str(tracked)]
        # Assert
        assert recorded == hashlib.sha256(tracked.read_bytes()).hexdigest()

    def test_recorded_hash_is_full_64_char_digest_not_truncated(self, tmp_path):
        # Arrange
        db = _make_db(tmp_path, name="hash2.db")
        tracked = tmp_path / "tracked2.csv"
        tracked.write_bytes(b"some content")
        db.add_run("s_len", script_path="/script.py")
        db.add_file_hash("s_len", str(tracked), hash_file(tracked), "output")
        # Act
        recorded = db.get_file_hashes("s_len", role="output")[str(tracked)]
        # Assert
        assert len(recorded) == 64

    def test_hash_file_itself_returns_full_digest(self, tmp_path):
        # Arrange — the write-time root cause, isolated from the DB.
        tracked = tmp_path / "tracked3.csv"
        tracked.write_bytes(b"other content")
        # Act
        result = hash_file(tracked)
        # Assert
        assert result == hashlib.sha256(tracked.read_bytes()).hexdigest()


# EOF
