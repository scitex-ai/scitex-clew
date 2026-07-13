#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the manuscript-hints producer (:mod:`scitex_clew._claim._hints`).

``export_manuscript_hints`` reads clew's claim ledger + ingested citation
ledger and emits ONE ``hints`` list in scitex-writer's ``manuscript-hints/1``
schema: per-entry {id, kind, severity, message, location, claim_id, source}.
This is a DIFFERENT, separate concern from ``export_manuscript_claims`` (see
``test__manuscript.py``) — do not confuse the two.

Per PA-306 §3 (no mocks): real isolated DB. Per PA-307 §3: AAA markers + one
assertion per test.
"""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

import scitex_clew as clew
import scitex_clew._db as _db_module
from scitex_clew._db import set_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    set_db(tmp_path / "hints.db")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _export(tmp_path, path=None):
    out = clew.export_manuscript_hints(
        path=path or (tmp_path / "hints.json"), read_only=False
    )
    return json.loads(out.read_text())


def _force_claim_status(isolated_db, status: str) -> None:
    """Force the (single) registered claim's raw status via direct sqlite."""
    conn = sqlite3.connect(str(isolated_db.db_path))
    conn.execute("UPDATE claims SET status = ? WHERE 1=1", (status,))
    conn.commit()
    conn.close()


class TestHintsSchema:
    def test_schema_key_is_manuscript_hints_v1(self, isolated_db, tmp_path):
        # Arrange
        # (no fixture setup needed — an empty claim/citation ledger is valid)
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["schema"] == "manuscript-hints/1"

    def test_hints_key_is_a_list(self, isolated_db, tmp_path):
        # Arrange
        # (no fixture setup needed — an empty claim/citation ledger is valid)
        # Act
        payload = _export(tmp_path)
        # Assert
        assert isinstance(payload["hints"], list)

    def test_no_attention_needed_writes_empty_hints_list(self, isolated_db, tmp_path):
        # Arrange — a claim forced to 'verified' needs no hint
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
        )
        _force_claim_status(isolated_db, "verified")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["hints"] == []

    def test_hint_entry_has_locked_field_set(self, isolated_db, tmp_path):
        # Arrange — a mismatch claim always needs a hint
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert set(entry.keys()) == {
            "id", "kind", "severity", "message", "location", "claim_id", "source",
        }

    def test_hint_location_has_file_line_page(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert set(entry["location"].keys()) == {"file", "line", "page"}

    def test_hint_source_is_scitex_clew(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["source"] == "scitex-clew"

    def test_hint_id_prefixed_hint(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value",
            line_number=1,
            claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["id"].startswith("hint_")


class TestClaimSeverityMapping:
    def test_mismatch_claim_is_error(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["severity"] == "error"

    def test_missing_claim_is_error(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        _force_claim_status(isolated_db, "missing")
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["severity"] == "error"

    def test_registered_never_verified_claim_is_warning(self, isolated_db, tmp_path):
        # Arrange — freshly registered, never verified (default status)
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["severity"] == "warning"

    def test_suspect_claim_is_warning(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        _force_claim_status(isolated_db, "suspect")
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["severity"] == "warning"

    def test_verified_claim_emits_no_hint(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        _force_claim_status(isolated_db, "verified")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["hints"] == []

    def test_mismatch_claim_id_matches_claim(self, isolated_db, tmp_path):
        # Arrange
        c = clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["claim_id"] == c.claim_id


class TestCitationSeverityMapping:
    def test_verified_citation_emits_no_hint(self, isolated_db, tmp_path):
        # Arrange — resolved + DOI -> derive_status() == 'verified'
        clew.add_citation("Berens2009", doi="10.1/x")
        # Act
        payload = _export(tmp_path)
        # Assert
        assert payload["hints"] == []

    def test_stub_citation_is_warning(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["severity"] == "warning"

    def test_unverified_citation_is_warning(self, isolated_db, tmp_path):
        # Arrange — resolved=False, no DOI, not flagged stub -> 'unverified'
        clew.add_citation("Xyz2024", resolved=False)
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["severity"] == "warning"

    def test_citation_claim_id_is_cite_key(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["claim_id"] == "Pinto2023"

    def test_stub_citation_kind_is_citation_stub(self, isolated_db, tmp_path):
        # Arrange
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act
        entry = _export(tmp_path)["hints"][0]
        # Assert
        assert entry["kind"] == "citation-stub"


class TestDeterminism:
    def test_same_input_produces_identical_hints_list(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        clew.add_citation("Pinto2023", is_stub=True, resolved=False)
        # Act — export to two distinct files from the same DB state
        first = _export(tmp_path, tmp_path / "h1.json")
        second = _export(tmp_path, tmp_path / "h2.json")
        # Assert
        assert first["hints"] == second["hints"]

    def test_hint_id_stable_across_reexport(self, isolated_db, tmp_path):
        # Arrange
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        # Act
        id1 = _export(tmp_path, tmp_path / "h1.json")["hints"][0]["id"]
        id2 = _export(tmp_path, tmp_path / "h2.json")["hints"][0]["id"]
        # Assert
        assert id1 == id2


class TestMergeBySource:
    def _foreign_payload(self):
        return {
            "schema": "manuscript-hints/1",
            "hints": [
                {
                    "id": "hint_foreign000",
                    "kind": "figrecipe-oversize",
                    "severity": "warning",
                    "message": "Figure exceeds column width.",
                    "location": {"file": "fig1.tex", "line": 10, "page": None},
                    "claim_id": "figures/fig1.png",
                    "source": "figrecipe",
                }
            ],
        }

    def test_foreign_source_entries_preserved(self, isolated_db, tmp_path):
        # Arrange
        path = tmp_path / "hints.json"
        path.write_text(json.dumps(self._foreign_payload()))
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        # Act
        clew.export_manuscript_hints(path=path, read_only=False)
        payload = json.loads(path.read_text())
        # Assert
        assert any(h["source"] == "figrecipe" for h in payload["hints"])

    def test_clew_entries_do_not_duplicate_on_reexport(self, isolated_db, tmp_path):
        # Arrange
        path = tmp_path / "hints.json"
        path.write_text(json.dumps(self._foreign_payload()))
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        clew.export_manuscript_hints(path=path, read_only=False)
        # Act — re-export with unchanged clew state
        clew.export_manuscript_hints(path=path, read_only=False)
        payload = json.loads(path.read_text())
        # Assert
        clew_entries = [h for h in payload["hints"] if h["source"] == "scitex-clew"]
        assert len(clew_entries) == 1

    def test_foreign_entries_not_present_in_clew_slice(self, isolated_db, tmp_path):
        # Arrange
        path = tmp_path / "hints.json"
        path.write_text(json.dumps(self._foreign_payload()))
        clew.add_claim(
            file_path=str(tmp_path / "p.tex"),
            claim_type="value", line_number=1, claim_value="0.94",
        )
        _force_claim_status(isolated_db, "mismatch")
        # Act
        clew.export_manuscript_hints(path=path, read_only=False)
        payload = json.loads(path.read_text())
        # Assert
        assert all(h.get("id") != "hint_foreign000" or h["source"] == "figrecipe"
                    for h in payload["hints"])

    def test_file_created_fresh_when_missing(self, isolated_db, tmp_path):
        # Arrange
        path = tmp_path / "hints.json"
        # Act
        clew.export_manuscript_hints(path=path, read_only=False)
        # Assert
        assert path.exists()

    def test_unparsable_existing_file_treated_as_empty(self, isolated_db, tmp_path):
        # Arrange
        path = tmp_path / "hints.json"
        path.write_text("not valid json {{{")
        # Act
        clew.export_manuscript_hints(path=path, read_only=False)
        payload = json.loads(path.read_text())
        # Assert
        assert payload["schema"] == "manuscript-hints/1"


class TestReadOnly:
    def test_read_only_default_chmods_0444(self, isolated_db, tmp_path):
        # Arrange
        path = tmp_path / "hints.json"
        # Act
        out = clew.export_manuscript_hints(path=path)
        # Assert
        assert (out.stat().st_mode & 0o777) == 0o444

    def test_read_only_false_leaves_file_writable(self, isolated_db, tmp_path):
        # Arrange
        path = tmp_path / "hints.json"
        # Act
        out = clew.export_manuscript_hints(path=path, read_only=False)
        # Assert
        assert (out.stat().st_mode & 0o200) != 0


# EOF
