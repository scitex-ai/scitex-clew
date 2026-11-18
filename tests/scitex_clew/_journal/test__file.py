#!/usr/bin/env python3
"""A ``flushed`` marker means "in the store" — never earlier. Real store, no mocks.

The journal replays every row after the last marker, so a marker written
before its rows commit would make a kill lose them. These tests drive the
real deferred queue of a real ``VerificationDB`` against the test's private
schema and read the journal file back.
"""

from __future__ import annotations

import json
import os

import pytest
from scitex_clew._db._core import VerificationDB
from scitex_clew._journal import SessionJournal


@pytest.fixture
def db():
    handle = VerificationDB(project="journal-markers")
    yield handle
    handle.close()


@pytest.fixture
def journal(db):
    created = SessionJournal.create(
        "s-markers", project=db._runs.project, store=db.store_fingerprint, row_host="h"
    )
    yield created
    created.close(delete=True)


def _queue(db, journal, name: str) -> None:
    db.add_file_hash(
        "s-markers", f"/data/{name}", "abc", "input", defer=True, journal=journal
    )


def _kinds(journal) -> list[str]:
    with open(journal.path) as handle:
        return [json.loads(line)["k"] for line in handle]


class _Rollback(Exception):
    pass


class TestMarkers:
    def test_queued_row_is_journaled_before_any_flush(self, db, journal):
        # Arrange
        _queue(db, journal, "a")
        # Act
        kinds = _kinds(journal)
        # Assert
        assert kinds == ["h", "r"]

    def test_flush_appends_a_marker_after_commit(self, db, journal):
        # Arrange
        _queue(db, journal, "a")
        # Act
        db._file_hashes.flush()
        # Assert
        assert _kinds(journal) == ["h", "r", "f"]

    def test_flush_inside_an_open_batch_writes_no_marker_yet(self, db, journal):
        # Arrange
        observed = []
        # Act
        with db._file_hashes.batch():
            _queue(db, journal, "a")
            db._file_hashes.flush()
            observed = _kinds(journal)
        # Assert
        assert observed == ["h", "r"]

    def test_outermost_commit_appends_the_marker(self, db, journal):
        # Arrange
        with db._file_hashes.batch():
            _queue(db, journal, "a")
            db._file_hashes.flush()
        # Act
        kinds = _kinds(journal)
        # Assert
        assert kinds == ["h", "r", "f"]

    def test_rolled_back_batch_writes_no_marker(self, db, journal):
        # Arrange
        try:
            with db._file_hashes.batch():
                _queue(db, journal, "a")
                db._file_hashes.flush()
                raise _Rollback
        except _Rollback:
            pass
        # Act
        kinds = _kinds(journal)
        # Assert
        assert kinds == ["h", "r"]

    def test_journal_file_is_private_to_the_user(self, journal):
        # Arrange
        path = journal.path
        # Act
        mode = os.stat(path).st_mode & 0o777
        # Assert
        assert mode == 0o600


# EOF
