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
            "verified", "suspect", "unverified", "exception")


class TestUnifiedExportCitations:
    def test_verified_citation_maps_to_verified(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert _entries_by_type(payload, "citation")[0]["status"] == "verified"

    def test_stub_citation_maps_to_unverified_red(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act
        payload = _export(tmp_path)
        # Assert
        assert _entries_by_type(payload, "citation")[0]["status"] == "unverified"

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


# EOF
