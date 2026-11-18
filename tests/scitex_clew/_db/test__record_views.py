#!/usr/bin/env python3
"""Per-session views over ``file_hashes`` (``scitex_clew._db._record_views``).

A real ``VerificationDB`` on a real PostgreSQL store. No mocks.
"""

from __future__ import annotations

import pytest

from scitex_clew._db import get_db
from scitex_clew._db._record_views import RECORD_KEYS, decode_record


@pytest.fixture
def db():
    db = get_db()
    db.add_file_hash("rv_sess", "/p/in.csv", "a" * 64, "input", size_bytes=3)
    db.add_file_hash(
        "rv_sess",
        "/p/ext.csv",
        "b" * 64,
        "input",
        external={"via": "/p/link", "size": 1, "mtime": 2.0},
    )
    db.add_file_hash("rv_sess", "/p/big.bin", "c" * 64, "input", frozen=True)
    db.add_file_hash(
        "rv_sess", "/p/out.csv", "d" * 64, "output", derived_from=["/p/in.csv"]
    )
    db.add_file_hash("rv_other", "/p/in.csv", "e" * 64, "input")
    return db


class TestViews:
    def test_hashes_of_one_role(self, db):
        # Arrange
        # Act
        got = db.get_file_hashes("rv_sess", role="output")
        # Assert
        assert got == {"/p/out.csv": "d" * 64}

    def test_hashes_of_every_role_exclude_other_sessions(self, db):
        # Arrange
        # Act
        got = db.get_file_hashes("rv_sess")
        # Assert
        assert sorted(got.values()) == ["a" * 64, "b" * 64, "c" * 64, "d" * 64]

    def test_frozen_files_lists_only_frozen_rows(self, db):
        # Arrange
        # Act
        got = db.get_frozen_files("rv_sess")
        # Assert
        assert got == {"/p/big.bin"}

    def test_external_files_carry_their_payload(self, db):
        # Arrange
        # Act
        got = db.get_external_files("rv_sess")
        # Assert
        assert got == {"/p/ext.csv": {"via": "/p/link", "size": 1, "mtime": 2.0}}

    def test_file_records_keep_the_public_keys_only(self, db):
        # Arrange
        # Act
        got = {tuple(sorted(r)) for r in db.get_file_records("rv_sess")}
        # Assert
        assert got == {tuple(sorted(RECORD_KEYS))}

    def test_file_records_parse_declarations(self, db):
        # Arrange
        # Act
        got = db.get_file_records("rv_sess", role="output")[0]["derived_from"]
        # Assert
        assert got == ["/p/in.csv"]


def test_decode_record_parses_json_columns_and_keeps_frozen():
    # Arrange
    values = {
        "file_path": "/p/x",
        "hash": "h",
        "recorded_at": "t",
        "role": "input",
        "derived_from": None,
        "external": '{"via": null}',
        "size_bytes": 1,
        "frozen": 1,
    }
    # Act
    record = decode_record(values)
    # Assert
    assert (record["external"], record["frozen"]) == ({"via": None}, True)


# EOF
