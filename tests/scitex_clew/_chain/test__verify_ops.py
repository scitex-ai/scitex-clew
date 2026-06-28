#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for ``scitex_clew._chain._verify_ops`` — provenance surfacing.

Mirrors src/scitex_clew/_chain/_verify_ops.py per the project mirror rule.

All tests build real temp DBs via the package DB API — no mocks (PA-307).
Each test has exactly one assertion, with # Arrange / # Act / # Assert
markers each on their own lines in that order.
"""

from __future__ import annotations

import pytest

import scitex_clew._db as _db_module
from scitex_clew._chain._types import RunVerification, VerificationStatus
from scitex_clew._chain._verify_ops import verify_run
from scitex_clew._db import get_db, set_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Fresh DB for every test; reset the global singleton after."""
    # Arrange
    db_path = tmp_path / "verify_ops_test.db"
    set_db(db_path)
    # Act
    yield get_db()
    # Assert (teardown)
    _db_module._DB_INSTANCE = None


class TestVerifyRunProvenanceSurfacing:
    """verify_run must populate provenance + exception_reason from the DB."""

    def test_verify_run_returns_tracked_provenance_by_default(self, isolated_db):
        # Arrange
        isolated_db.add_run("tracked_001", "/script.py")
        # Act
        result = verify_run("tracked_001")
        # Assert
        assert result.provenance == "tracked"

    def test_verify_run_returns_none_exception_reason_for_tracked(self, isolated_db):
        # Arrange
        isolated_db.add_run("tracked_002", "/script.py")
        # Act
        result = verify_run("tracked_002")
        # Assert
        assert result.exception_reason is None

    def test_verify_run_surfaces_exception_provenance(self, isolated_db):
        # Arrange
        isolated_db.add_run(
            "exception_001",
            "/script.py",
            provenance="exception",
            exception_reason="4.1TB gPAC, recipe-known, never re-run",
        )
        # Act
        result = verify_run("exception_001")
        # Assert
        assert result.provenance == "exception"

    def test_verify_run_surfaces_exception_reason(self, isolated_db):
        # Arrange
        isolated_db.add_run(
            "exception_002",
            "/script.py",
            provenance="exception",
            exception_reason="4.1TB gPAC, recipe-known, never re-run",
        )
        # Act
        result = verify_run("exception_002")
        # Assert
        assert result.exception_reason == "4.1TB gPAC, recipe-known, never re-run"

    def test_verify_run_result_is_runverification_instance(self, isolated_db):
        # Arrange
        isolated_db.add_run("check_type_001", "/script.py")
        # Act
        result = verify_run("check_type_001")
        # Assert
        assert isinstance(result, RunVerification)

    def test_verify_run_exception_with_no_files_is_verified(self, isolated_db):
        # Arrange — an exception node with no file hashes and success status
        # should be VERIFIED (all files verify vacuously).
        isolated_db.add_run(
            "exception_nf_001",
            "/script.py",
            provenance="exception",
            exception_reason="reason",
        )
        isolated_db.finish_run("exception_nf_001", status="success")
        # Act
        result = verify_run("exception_nf_001")
        # Assert
        assert result.status == VerificationStatus.VERIFIED

    def test_verify_run_exception_node_with_missing_output_is_not_verified(
        self, isolated_db, tmp_path
    ):
        # Arrange — exception node registers an output file that doesn't exist;
        # the exception marker must NOT mask the missing-file failure.
        gone_path = str(tmp_path / "gone.csv")
        isolated_db.add_run(
            "exception_missing_001",
            "/script.py",
            provenance="exception",
            exception_reason="external job",
        )
        isolated_db.add_file_hash(
            "exception_missing_001",
            gone_path,
            "deadbeef" * 8,
            "output",
        )
        # Act
        result = verify_run("exception_missing_001")
        # Assert
        assert not result.is_verified


# EOF
