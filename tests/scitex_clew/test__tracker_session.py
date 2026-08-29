#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the zero-dep clew.session() provenance recorder.

The recorder writes a REAL run (+ input->output edges) using only clew's
pure-stdlib core, so a minimal-mode script produces runs>=1 + a source-reachable
DAG. No mocks — a real database and real files.

RETARGETED (clew's Postgres migration): there is no database FILE any more and
no `use_db(path)` to scope one. Every store resolves through
`scitex_dev.store.host_store()`, and the autouse `isolated_store` fixture in
tests/conftest.py already gives each test its own throwaway PostgreSQL schema.
`_runs`/`_roles` therefore open a `VerificationDB()` with no argument and read
back through its real public/Store surface.
"""

import pytest

import scitex_clew as clew
from scitex_clew import VerificationDB
from scitex_clew._claim._register import list_claims
from scitex_clew._db import get_db
from scitex_clew._sources import is_grounded, load_sources_manifest


def _runs():
    return len(VerificationDB().list_runs(limit=10_000))


def _roles():
    return {r.values.get("role") for r in VerificationDB()._file_hashes.rows()}


class TestSessionRecording:
    def test_session_records_one_run(self):
        # Arrange
        # Act
        with clew.session(script_path="analysis.py"):
            pass
        # Assert
        assert _runs() == 1

    def test_record_input_output_write_edges(self, tmp_path):
        # Arrange
        src = tmp_path / "raw.csv"
        src.write_text("x\n1\n")
        out = tmp_path / "out.json"
        out.write_text('{"n": 1}\n')
        # Act
        with clew.session() as run:
            run.record_input(src)
            run.record_output(out)
        # Assert
        assert {"input", "output"} <= _roles()

    def test_module_level_record_uses_current_session(self, tmp_path):
        # Arrange
        out = tmp_path / "o.txt"
        out.write_text("hi\n")
        # Act
        with clew.session():
            digest = clew.record_output(out)
        # Assert
        assert digest is not None and len(digest) > 0

    def test_record_outside_session_raises(self, tmp_path):
        # Arrange
        f = tmp_path / "f.txt"
        f.write_text("x")
        clew.stop_tracking()
        # Act
        # Assert
        with pytest.raises(RuntimeError):
            clew.record_output(f)

    def test_claim_on_recorded_output_grounds_to_registered_source(self, tmp_path):
        # Arrange — register the raw input as a source; record a run raw->out.
        src = tmp_path / "raw.csv"
        src.write_text("x,y\n1,2\n")
        out = tmp_path / "out.json"
        out.write_text('{"n": 2}\n')
        manifest = tmp_path / "sources.json"
        db = get_db()
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

    def test_exception_in_block_still_records_and_finalizes(self):
        # Arrange
        # Act — an exception in the block still records + finalizes the run.
        try:
            with clew.session():
                raise ValueError("boom")
        except ValueError:
            pass
        # Assert — the run was still recorded (finalized as error in the finally).
        assert _runs() == 1
