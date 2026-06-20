#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the ``verify_all_claims`` Python API and its
``VerificationResult`` (both in :mod:`scitex_clew._claim`, exposed at the
top level as ``scitex_clew.verify_all_claims``).

This is the entry point the ``clew verify`` CLI wraps: it walks every
registered claim, source-verifies each, and reduces to a fail-loud exit
code.

Per PA-306 §3 (no mocks): the API tests touch a real isolated DB seeded
with real runs / file hashes. Per PA-307 §3: AAA marker comments + one
observable assertion per test.
"""

from __future__ import annotations

import os

import pytest

import scitex_clew as clew
import scitex_clew._db as _db_module
from scitex_clew._cli import _exit_codes as codes
from scitex_clew._db import set_db
from scitex_clew._hash import hash_file


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    # Real env mutation with explicit undo (PA-306 forbids monkeypatch):
    # disable the read-only claims.json auto-export between temp DBs.
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    set_db(tmp_path / "verify_all.db")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _seed_tracked_source(db, tmp_path):
    src = tmp_path / "results.json"
    src.write_text('{"acc": 0.94}\n')
    sid = "2026Y-06M-19D-00h00m00s_Seed-main"
    db.add_run(sid, str(tmp_path / "make_results.py"))
    db.add_file_hash(sid, str(src.resolve()), hash_file(src), "output")
    db.finish_run(sid, status="success")
    return src


class TestVerifyAllClaimsApi:
    def test_no_claims_returns_no_claims_code(self, isolated_db):
        # Arrange — empty DB.
        # Act
        summary = clew.verify_all_claims()
        # Assert
        assert summary.exit_code == codes.NO_CLAIMS

    def test_mixed_set_returns_worst_code(self, isolated_db, tmp_path):
        # Arrange — one OK claim + one fabrication claim in the same set.
        src = _seed_tracked_source(isolated_db, tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\nfabricated p=0.003\n")
        clew.add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
            source_file=str(src),
        )
        clew.add_claim(
            file_path=str(paper),
            claim_type="statistic",
            line_number=2,
            claim_value="p=0.003",  # no source -> fabrication
        )
        # Act
        summary = clew.verify_all_claims()
        # Assert — the unverified fabrication drags the whole set to nonzero.
        assert summary.exit_code == codes.UNVERIFIED

    def test_ok_set_reports_full_verified_count(self, isolated_db, tmp_path):
        # Arrange
        src = _seed_tracked_source(isolated_db, tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        clew.add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
            source_file=str(src),
        )
        # Act
        summary = clew.verify_all_claims()
        # Assert
        assert summary.exit_code == codes.OK and summary.verified == 1

    def test_strict_flag_is_echoed_in_summary(self, isolated_db, tmp_path):
        # Arrange
        src = _seed_tracked_source(isolated_db, tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        clew.add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
            source_file=str(src),
        )
        # Act
        summary = clew.verify_all_claims(strict=True)
        # Assert
        assert summary.strict is True


class TestVerificationResult:
    def test_to_dict_has_canonical_json_keys(self, isolated_db):
        # Arrange — empty DB yields a NO_CLAIMS result.
        result = clew.verify_all_claims()
        # Act
        payload = result.to_dict()
        # Assert
        assert set(payload) == {
            "exit_code",
            "exit_name",
            "reason",
            "strict",
            "total",
            "verified",
            "counts",
            "severities",
            "errors",
            "warnings",
            "claims",
        }

    def test_ok_property_tracks_verified_set(self, isolated_db, tmp_path):
        # Arrange — one fully-grounded, lineage-backed claim.
        src = _seed_tracked_source(isolated_db, tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("acc=0.94\n")
        clew.add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
            source_file=str(src),
        )
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.ok is True and result.verified == 1
