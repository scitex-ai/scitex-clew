#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the citation gate (:mod:`scitex_clew._citation`).

Extends clew's claim->source verification from VALUES to CITATIONS: every
``\\cite`` key becomes a citation node linked to a scholar-resolved source, and
:func:`scitex_clew.verify_citations` returns the per-key status map the compiler
gates on. The flagship case is catching a hallucinated / stub citation.

Per PA-306 §3 (no mocks): tests touch the real store — tests/conftest.py gives
each test its own PostgreSQL schema. Per PA-307 §3: AAA marker comments + one
observable assertion per test.
"""

from __future__ import annotations

import pytest

import scitex_clew as clew
from scitex_clew._cli import _exit_codes as codes


# --- add_citation status derivation -----------------------------------------


class TestAddCitation:
    def test_resolved_with_doi_is_verified(self):
        # Arrange
        # Act
        c = clew.add_citation("Berens2009", doi="10.1/x", source_id="s1")
        # Assert
        assert c.status == "verified"

    def test_stub_flag_is_stub(self):
        # Arrange
        # Act
        c = clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Assert
        assert c.status == "stub"

    def test_resolved_without_doi_is_unverified(self):
        # Arrange
        # Act
        c = clew.add_citation("NoDoi2020", resolved=True)
        # Assert
        assert c.status == "unverified"

    def test_empty_key_raises_value_error(self):
        # Arrange
        # Act
        # Assert
        with pytest.raises(ValueError):
            clew.add_citation("  ")


# --- verify_citations per-key verdicts --------------------------------------


class TestVerifyCitationsPerKey:
    def test_pushed_verified_key_is_verified(self):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        result = clew.verify_citations([{"key": "Berens2009", "doi": "10.1/x"}])
        # Assert
        assert result["Berens2009"]["status"] == "verified"

    def test_pushed_stub_key_is_stub(self):
        # Arrange
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act
        result = clew.verify_citations([{"key": "Pinto2023"}])
        # Assert
        assert result["Pinto2023"]["status"] == "stub"

    def test_local_stub_heuristic_flags_no_doi(self):
        # Arrange
        entry = {"key": "X", "journal": "Nature"}
        # Act
        result = clew.verify_citations([entry])
        # Assert
        assert result["X"]["status"] == "stub"

    def test_local_stub_heuristic_flags_pending_journal(self):
        # Arrange
        entry = {"key": "Y", "journal": "Pending scitex-scholar metadata lookup"}
        # Act
        result = clew.verify_citations([entry])
        # Assert
        assert result["Y"]["status"] == "stub"

    def test_in_bib_not_registered_is_unverified(self):
        # Arrange
        entry = {"key": "Z", "doi": "10.2/y"}
        # Act
        result = clew.verify_citations([entry])
        # Assert
        assert result["Z"]["status"] == "unverified"

    def test_bare_key_is_unknown(self):
        # Arrange
        entry = {"key": "Ghost"}
        # Act
        result = clew.verify_citations([entry])
        # Assert
        assert result["Ghost"]["status"] == "unknown"

    def test_bare_string_entry_is_accepted(self):
        # Arrange
        # Act
        result = clew.verify_citations(["Ghost"])
        # Assert
        assert result["Ghost"]["status"] == "unknown"

    def test_changed_doi_trips_drift(self):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        result = clew.verify_citations([{"key": "Berens2009", "doi": "10.9/wrong"}])
        # Assert
        assert result["Berens2009"]["status"] == "unverified"


# --- verify_all_citations aggregate (fail-loud, same-run contract) ----------


class TestVerifyAllCitations:
    def test_all_verified_set_is_ok(self):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        result = clew.verify_all_citations([{"key": "Berens2009", "doi": "10.1/x"}])
        # Assert
        assert result.ok

    def test_stub_blocks_with_citation_stub_code(self):
        # Arrange
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act
        result = clew.verify_all_citations([{"key": "Pinto2023"}])
        # Assert
        assert result.exit_code == codes.CITATION_STUB

    def test_mixed_set_reports_worst_code(self):
        # Arrange
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        entries = [{"key": "Pinto2023"}, {"key": "Ghost"}]
        # Act
        result = clew.verify_all_citations(entries)
        # Assert
        assert result.exit_name == "CITATION_STUB"

    def test_unknown_key_maps_to_unlinked(self):
        # Arrange
        entries = [{"key": "Ghost"}]
        # Act
        result = clew.verify_all_citations(entries)
        # Assert
        assert result.exit_code == codes.CITATION_UNLINKED

    def test_unresolved_key_maps_to_unresolved(self):
        # Arrange
        entries = [{"key": "Z", "doi": "10.2/y"}]
        # Act
        result = clew.verify_all_citations(entries)
        # Assert
        assert result.exit_code == codes.CITATION_UNRESOLVED

    def test_empty_set_is_no_claims(self):
        # Arrange
        # Act
        result = clew.verify_all_citations([])
        # Assert
        assert result.exit_code == codes.NO_CLAIMS


# --- exit-code contract -----------------------------------------------------


class TestCitationExitCodes:
    def test_codes_are_stable_integers(self):
        # Arrange
        actual = (codes.CITATION_STUB, codes.CITATION_UNRESOLVED, codes.CITATION_UNLINKED)
        # Act
        # Assert
        assert actual == (14, 15, 16)

    def test_citation_patterns_default_to_error(self):
        # Arrange
        # Act
        sev = codes.resolve_severity()
        # Assert
        assert sev[codes.CITATION_STUB] == codes.Severity.ERROR


# --- link resolution (render contract) --------------------------------------


class TestCitationLink:
    def test_verified_key_link_is_doi_resolver(self):
        # Arrange
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        result = clew.verify_citations([{"key": "Berens2009", "doi": "10.1/x"}])
        # Assert
        assert result["Berens2009"]["link"] == "https://doi.org/10.1/x"

    def test_scholar_url_overrides_doi_link(self):
        # Arrange
        clew.add_citation("Corpus1", url="https://semanticscholar.org/CorpusID:42")
        # Act
        result = clew.verify_citations([{"key": "Corpus1"}])
        # Assert
        assert result["Corpus1"]["link"] == "https://semanticscholar.org/CorpusID:42"

    def test_unknown_key_link_is_none(self):
        # Arrange
        entry = {"key": "Ghost"}
        # Act
        result = clew.verify_citations([entry])
        # Assert
        assert result["Ghost"]["link"] is None


# --- list_citations ---------------------------------------------------------


class TestListCitations:
    def test_status_filter_returns_only_matching(self):
        # Arrange
        clew.add_citation("A", doi="10.1/a")
        clew.add_citation("B", is_stub=True, resolved=False)
        # Act
        stubs = clew.list_citations(status="stub")
        # Assert
        assert [c.cite_key for c in stubs] == ["B"]


# EOF
