#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the citation artifact ingest seam (:mod:`scitex_clew._citation._ingest`).

The scholar↔clew decoupled seam: scholar saves a ``citation_status.json`` via
stx.io; clew's io observer ingests it here (scholar never imports clew). Ingest
maps each entry 1:1 to ``add_citation`` (idempotent upsert), independent of an
active session.

Per PA-306 §3 (no mocks): real isolated DB. Per PA-307 §3: AAA markers + one
assertion per test.
"""

from __future__ import annotations

import os

import pytest

import scitex_clew as clew
import scitex_clew._db as _db_module
from scitex_clew._citation._ingest import (
    ingest_citations_artifact,
    is_citation_artifact,
)
from scitex_clew._db import set_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    set_db(tmp_path / "ingest.db")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _artifact(*citations):
    return {"schema": "scitex-clew/citations/v1", "citations": list(citations)}


class TestIsCitationArtifact:
    def test_marked_dict_is_artifact(self):
        # Arrange
        obj = _artifact()
        # Act
        # Assert
        assert is_citation_artifact(obj) is True

    def test_unmarked_dict_is_not_artifact(self):
        # Arrange
        obj = {"foo": "bar"}
        # Act
        # Assert
        assert is_citation_artifact(obj) is False

    def test_non_dict_is_not_artifact(self):
        # Arrange
        obj = ["not", "a", "dict"]
        # Act
        # Assert
        assert is_citation_artifact(obj) is False


class TestIngest:
    def test_valid_artifact_returns_count(self, isolated_db):
        # Arrange
        obj = _artifact(
            {"cite_key": "Berens2009", "doi": "10.1/x"},
            {"cite_key": "Pinto2023", "is_stub": True, "resolved": False},
        )
        # Act
        n = ingest_citations_artifact(obj)
        # Assert
        assert n == 2

    def test_entries_land_in_ledger(self, isolated_db):
        # Arrange
        obj = _artifact({"cite_key": "Berens2009", "doi": "10.1/x"})
        # Act
        ingest_citations_artifact(obj)
        # Assert
        assert [c.cite_key for c in clew.list_citations()] == ["Berens2009"]

    def test_verified_entry_status(self, isolated_db):
        # Arrange
        obj = _artifact({"cite_key": "Berens2009", "doi": "10.1/x"})
        # Act
        ingest_citations_artifact(obj)
        # Assert
        assert clew.list_citations()[0].status == "verified"

    def test_stub_entry_status(self, isolated_db):
        # Arrange
        obj = _artifact({"cite_key": "Pinto2023", "is_stub": True, "resolved": False})
        # Act
        ingest_citations_artifact(obj)
        # Assert
        assert clew.list_citations()[0].status == "stub"

    def test_non_artifact_returns_zero(self, isolated_db):
        # Arrange
        obj = {"schema": "something-else", "citations": [{"cite_key": "X"}]}
        # Act
        n = ingest_citations_artifact(obj)
        # Assert
        assert n == 0

    def test_entry_without_cite_key_skipped(self, isolated_db):
        # Arrange
        obj = _artifact({"doi": "10.1/x"}, {"cite_key": "Berens2009"})
        # Act
        n = ingest_citations_artifact(obj)
        # Assert
        assert n == 1

    def test_reingesting_same_key_is_idempotent(self, isolated_db):
        # Arrange
        obj = _artifact({"cite_key": "Berens2009", "doi": "10.1/x"})
        ingest_citations_artifact(obj)
        # Act
        ingest_citations_artifact(obj)
        # Assert
        assert len(clew.list_citations()) == 1

    def test_missing_citations_key_returns_zero(self, isolated_db):
        # Arrange
        obj = {"schema": "scitex-clew/citations/v1"}
        # Act
        n = ingest_citations_artifact(obj)
        # Assert
        assert n == 0


class TestObserverSeam:
    """on_io_save routes a citation artifact to ingest (scholar↔clew seam).

    on_io_save's citation branch needs no scitex_io and no active tracker, so
    this exercises the real observer path without the scitex_io-gated file.
    """

    def test_on_io_save_ingests_citation_artifact(self, isolated_db, tmp_path):
        # Arrange
        from scitex_clew._observers import on_io_save
        from scitex_clew._tracker import set_tracker

        set_tracker(None)
        obj = _artifact({"cite_key": "Berens2009", "doi": "10.1/x"})
        # Act
        on_io_save(tmp_path / "citation_status.json", obj, {})
        # Assert
        assert [c.cite_key for c in clew.list_citations()] == ["Berens2009"]

    def test_on_io_save_non_artifact_ingests_nothing(self, isolated_db, tmp_path):
        # Arrange
        from scitex_clew._observers import on_io_save
        from scitex_clew._tracker import set_tracker

        set_tracker(None)
        # Act
        on_io_save(tmp_path / "data.csv", {"x": 1}, {})
        # Assert
        assert clew.list_citations() == []


# EOF
