#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the zero-dep clew.session() provenance recorder.

The recorder writes a REAL run (+ input->output edges) using only clew's
pure-stdlib core, so a minimal-mode script produces runs>=1 + a source-reachable
DAG. No mocks — real temp DB + real files, scoped via use_db.
"""

import sqlite3

import pytest

import scitex_clew as clew
from scitex_clew._claim._register import list_claims
from scitex_clew._db import use_db
from scitex_clew._sources import is_grounded, load_sources_manifest


def _db_path(tmp_path):
    p = tmp_path / ".scitex" / "clew" / "runtime" / "clew.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _runs(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        conn.close()


def _roles(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute("SELECT role FROM file_hashes")}
    finally:
        conn.close()


class TestSessionRecording:
    def test_session_records_one_run(self, tmp_path):
        # Arrange
        db_path = _db_path(tmp_path)
        # Act
        with use_db(db_path):
            with clew.session(script_path="analysis.py"):
                pass
        # Assert
        assert _runs(db_path) == 1

    def test_record_input_output_write_edges(self, tmp_path):
        # Arrange
        db_path = _db_path(tmp_path)
        src = tmp_path / "raw.csv"
        src.write_text("x\n1\n")
        out = tmp_path / "out.json"
        out.write_text('{"n": 1}\n')
        # Act
        with use_db(db_path):
            with clew.session() as run:
                run.record_input(src)
                run.record_output(out)
        # Assert
        assert {"input", "output"} <= _roles(db_path)

    def test_module_level_record_uses_current_session(self, tmp_path):
        # Arrange
        db_path = _db_path(tmp_path)
        out = tmp_path / "o.txt"
        out.write_text("hi\n")
        # Act
        with use_db(db_path):
            with clew.session():
                digest = clew.record_output(out)
        # Assert
        assert digest is not None and len(digest) > 0

    def test_record_outside_session_raises(self, tmp_path):
        # Arrange
        db_path = _db_path(tmp_path)
        f = tmp_path / "f.txt"
        f.write_text("x")
        with use_db(db_path):
            clew.stop_tracking()
            # Act
            # Assert
            with pytest.raises(RuntimeError):
                clew.record_output(f)

    def test_claim_on_recorded_output_grounds_to_registered_source(self, tmp_path):
        # Arrange — register the raw input as a source; record a run raw->out.
        db_path = _db_path(tmp_path)
        src = tmp_path / "raw.csv"
        src.write_text("x,y\n1,2\n")
        out = tmp_path / "out.json"
        out.write_text('{"n": 2}\n')
        manifest = tmp_path / "sources.json"
        with use_db(db_path) as db:
            clew.register_source([src], sources_path=manifest, root=tmp_path)
            with clew.session(script_path="analysis.py") as run:
                run.record_input(src)
                run.record_output(out)
            clew.add_claim("paper.tex", "value", 1, "2", source_file=str(out))
            claim = list_claims(limit=10)[0]
            manifest_obj = load_sources_manifest(manifest, root=tmp_path)
        # Act — ground the claim: out <- run <- raw.csv(registered source).
        grounded = is_grounded(claim, manifest_obj, db)
        # Assert
        assert grounded is True

    def test_exception_in_block_still_records_and_finalizes(self, tmp_path):
        # Arrange
        db_path = _db_path(tmp_path)
        # Act — an exception in the block still records + finalizes the run.
        with use_db(db_path):
            try:
                with clew.session():
                    raise ValueError("boom")
            except ValueError:
                pass
        # Assert — the run was still recorded (finalized as error in the finally).
        assert _runs(db_path) == 1
