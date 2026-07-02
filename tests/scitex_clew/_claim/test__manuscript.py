#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the unified render bridge (:mod:`scitex_clew._claim._manuscript`).

``export_manuscript_claims`` reads BOTH ledgers (claims + citations) and emits
ONE ``claims`` list in scitex-writer's frozen render schema: per-entry
{claim_id, claim_type in [value|citation|figure], status (4-state), claim_value,
display_color, link, + provenance} + top-level palette/attestation.

Per PA-306 §3 (no mocks): real isolated DB. Per PA-307 §3: AAA markers + one
assertion per test.
"""

from __future__ import annotations

import json
import os

import pytest

import scitex_clew as clew
import scitex_clew._db as _db_module
from scitex_clew._db import set_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    set_db(tmp_path / "manuscript.db")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _export(tmp_path):
    out = clew.export_manuscript_claims(path=tmp_path / "unified.json", read_only=False)
    return json.loads(out.read_text())


def _entries_by_type(payload, claim_type):
    return [e for e in payload["claims"] if e["claim_type"] == claim_type]


class TestUnifiedExportEntries:
    def test_value_claim_becomes_value_entry(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="statistic",
                       line_number=1, claim_value="p=0.003")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert len(_entries_by_type(payload, "value")) == 1

    def test_figure_claim_becomes_figure_entry(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="figure",
                       claim_id="figures/fig1.png", claim_value="Fig1")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert _entries_by_type(payload, "figure")[0]["claim_id"] == "figures/fig1.png"

    def test_value_entry_status_is_4state(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=2, claim_value="0.94")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert _entries_by_type(payload, "value")[0]["status"] in (
            "verified", "suspect", "failed", "exception")

    def test_registered_value_entry_status_is_suspect(self, isolated_db, tmp_path):
        # Arrange — a freshly registered (never verified) claim
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=3, claim_value="0.94")
        # Act
        payload = _export(tmp_path)
        # Assert — v1.5: registered folds into the suspect (amber) bucket
        assert _entries_by_type(payload, "value")[0]["status"] == "suspect"

    def test_value_entry_carries_full7_resolved_status(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=4, claim_value="0.94")
        # Act
        payload = _export(tmp_path)
        # Assert — additive provenance field: the full-7 resolved status
        assert _entries_by_type(payload, "value")[0]["resolved_status"] == "registered"


class TestUnifiedExportCitations:
    def test_verified_citation_maps_to_verified(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert _entries_by_type(payload, "citation")[0]["status"] == "verified"

    def test_stub_citation_maps_to_failed_red(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act
        payload = _export(tmp_path)
        # Assert — v1.5: the red bucket is named 'failed'
        assert _entries_by_type(payload, "citation")[0]["status"] == "failed"

    def test_verified_citation_link_is_doi_resolver(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert _entries_by_type(payload, "citation")[0]["link"] == "https://doi.org/10.1/x"

    def test_citation_claim_id_is_cite_key(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert _entries_by_type(payload, "citation")[0]["claim_id"] == "Berens2009"


class TestUnifiedExportTopLevel:
    def test_toplevel_has_palette(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["palette"]["verified"] == "2da44e"

    def test_attestation_verified_count(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["attestation"]["verified_count"] == 1

    def test_attestation_total_counts_all_entries(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=1, claim_value="0.94")
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["attestation"]["total"] == 2

    def test_schema_version_is_15_unified(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert — v1.5: suspect rename + failed bucket + badge facts
        assert payload["schema_version"] == "1.5-unified"

    def test_toplevel_palette_has_failed_bucket(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert — 4-bucket display palette keys
        assert set(payload["palette"].keys()) == {
            "verified", "suspect", "failed", "exception"}

    def test_toplevel_status_palette_is_full7(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert — full-7 status palette (author tooling / DAG fidelity)
        assert payload["status_palette"] == {
            "verified": "2da44e", "suspect": "d29922", "mismatch": "cf222e",
            "missing": "a40e26", "registered": "6e7781",
            "exception": "8250df", "frozen": "0072b2"}

    def test_toplevel_display_groups_collapse_map(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert — per-status collapse (registered→suspect, frozen→verified)
        assert payload["display_groups"]["registered"] == "suspect"


class TestUnifiedAttestationBadge:
    def test_badge_state_all_verified_when_every_entry_verified(self, isolated_db, tmp_path):
        # Arrange — one resolved citation only
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["attestation"]["badge_state"] == "all_verified"

    def test_badge_state_failing_when_stub_citation_present(self, isolated_db, tmp_path):
        # Arrange — a stub (hallucinated) citation lands in the failed bucket
        clew.add_citation("Berens2009", doi="10.1/x")
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["attestation"]["badge_state"] == "failing"

    def test_badge_state_partial_when_registered_claim_present(self, isolated_db, tmp_path):
        # Arrange — verified citation + a registered (never verified) claim
        clew.add_citation("Berens2009", doi="10.1/x")
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=1, claim_value="0.94")
        # Act
        payload = _export(tmp_path)
        # Assert — not failing, not all verified
        assert payload["attestation"]["badge_state"] == "partial"

    def test_badge_state_failing_when_claim_mismatch(self, isolated_db, tmp_path):
        # Arrange — force a claim into 'mismatch' directly in the DB
        import sqlite3
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=1, claim_value="0.94")
        conn = sqlite3.connect(str(isolated_db.db_path))
        conn.execute("UPDATE claims SET status = 'mismatch' WHERE 1=1")
        conn.commit()
        conn.close()
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["attestation"]["badge_state"] == "failing"

    def test_counts_breakdown_keys_present(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        counts = _export(tmp_path)["attestation"]["counts"]
        # Assert — badge-fact keys: totals + buckets + raw mismatch/missing
        assert set(counts.keys()) == {
            "total", "verified", "unverified", "suspect", "failed",
            "exception", "mismatch", "missing"}

    def test_counts_unverified_is_total_minus_verified(self, isolated_db, tmp_path):
        # Arrange — 1 verified citation + 1 registered claim + 1 stub citation
        clew.add_citation("Berens2009", doi="10.1/x")
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=1, claim_value="0.94")
        # Act
        counts = _export(tmp_path)["attestation"]["counts"]
        # Assert
        assert counts["unverified"] == counts["total"] - counts["verified"]

    def test_counts_missing_tracks_raw_claim_status(self, isolated_db, tmp_path):
        # Arrange — force a claim into 'missing' directly in the DB
        import sqlite3
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=1, claim_value="0.94")
        conn = sqlite3.connect(str(isolated_db.db_path))
        conn.execute("UPDATE claims SET status = 'missing' WHERE 1=1")
        conn.commit()
        conn.close()
        # Act
        counts = _export(tmp_path)["attestation"]["counts"]
        # Assert — raw ledger breakdown distinguishes missing from mismatch
        assert counts["missing"] == 1 and counts["mismatch"] == 0

    def test_superseded_claims_excluded_from_counts(self, isolated_db, tmp_path):
        # Arrange — two claims on the same location/type/value collapse by
        # idempotent id; use distinct values then supersede one via mutate API
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=1, claim_value="0.94", claim_id="c_keep")
        clew.add_claim(file_path=str(tmp_path / "p.tex"), claim_type="value",
                       line_number=2, claim_value="0.95", claim_id="c_old")
        import sqlite3
        conn = sqlite3.connect(str(isolated_db.db_path))
        conn.execute("UPDATE claims SET status = 'superseded' WHERE claim_id = 'c_old'")
        conn.commit()
        conn.close()
        # Act
        counts = _export(tmp_path)["attestation"]["counts"]
        # Assert — the superseded row is excluded from every count
        assert counts["total"] == 1


# EOF
