#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end tests for the registered-source gate (verify + export + CLI).

Exercises the OPT-IN gate through the public surfaces a harness uses:
``clew.verify_all_claims`` (exit code UNSOURCED=17), ``export_claims_json``
(resolved_status/color), monotonicity, precedence vs hash failures, and the
``clew register-source`` / ``list-sources`` CLI round-trip.

Per PA-306 §3 (no mocks): real isolated DB, real manifest on disk, real
chain walk. Lives under tests/integration/ (out of the src<->test mirror
scope) because it spans _sources + _claim + _cli.
"""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

import scitex_clew as clew
import scitex_clew._db as _db_module
from scitex_clew._cli import _exit_codes as codes
from scitex_clew._cli._main import main
from scitex_clew._db import set_db
from scitex_clew._hash import hash_file
from scitex_clew._sources._manifest import SOURCES_SCHEMA, full_sha256


@pytest.fixture(autouse=True)
def sandbox(tmp_path):
    """Isolated DB + isolated sources manifest, both cleaned up."""
    prev_export = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    prev_sources = os.environ.get("SCITEX_CLEW_SOURCES")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    os.environ["SCITEX_CLEW_SOURCES"] = str(
        tmp_path / ".scitex" / "clew" / "sources.json"
    )
    set_db(tmp_path / ".scitex" / "clew" / "runtime" / "db.sqlite")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    for key, prev in (
        ("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", prev_export),
        ("SCITEX_CLEW_SOURCES", prev_sources),
    ):
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


def _seed_tracked_source(db, tmp_path, name="results.json"):
    src = tmp_path / name
    src.write_text('{"acc": 0.94}\n')
    sid = "2026Y-07M-03D-00h00m00s_Seed-main"
    db.add_run(sid, str(tmp_path / "make.py"))
    db.add_file_hash(sid, str(src.resolve()), hash_file(src), "output")
    db.finish_run(sid, status="success")
    return src, sid


def _write_manifest(tmp_path, files):
    entries = [
        {"path": str(f.relative_to(tmp_path)), "sha256": full_sha256(f)}
        for f in files
    ]
    path = tmp_path / ".scitex" / "clew" / "sources.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema": SOURCES_SCHEMA, "sources": entries, "signature": None})
    )
    return path


def _add_claim(tmp_path, src, sid=None):
    paper = tmp_path / "paper.tex"
    paper.write_text("acc=0.94\n")
    return clew.add_claim(
        file_path=str(paper), claim_type="value", line_number=1,
        claim_value="0.94", source_file=str(src), source_session=sid,
    )


class TestGateOptIn:
    def test_no_manifest_verified_claim_stays_ok(self, sandbox, tmp_path):
        # Arrange — no manifest => gate inactive => unchanged behavior.
        src, sid = _seed_tracked_source(sandbox, tmp_path)
        _add_claim(tmp_path, src, sid)
        # Act
        summary = clew.verify_all_claims()
        # Assert
        assert summary.exit_code == codes.OK and summary.verified == 1

    def test_grounded_claim_stays_ok(self, sandbox, tmp_path):
        # Arrange — register the claim's source => grounded.
        src, sid = _seed_tracked_source(sandbox, tmp_path)
        _add_claim(tmp_path, src, sid)
        _write_manifest(tmp_path, [src])
        # Act
        summary = clew.verify_all_claims()
        # Assert
        assert summary.exit_code == codes.OK


class TestUnsourcedVerdict:
    def test_ungrounded_claim_returns_unsourced(self, sandbox, tmp_path):
        # Arrange — manifest active via an UNRELATED source; claim ungrounded.
        src, sid = _seed_tracked_source(sandbox, tmp_path)
        _add_claim(tmp_path, src, sid)
        unrelated = tmp_path / "unrelated.csv"
        unrelated.write_text("z\n")
        _write_manifest(tmp_path, [unrelated])
        # Act
        summary = clew.verify_all_claims()
        # Assert — link-verified but ungrounded => amber, non-zero exit.
        assert summary.exit_code == codes.UNSOURCED

    def test_export_demotes_ungrounded_verified_to_unsourced(self, sandbox, tmp_path):
        # Arrange — verify first (stamps status=verified), then export with gate.
        src, sid = _seed_tracked_source(sandbox, tmp_path)
        _add_claim(tmp_path, src, sid)
        unrelated = tmp_path / "unrelated.csv"
        unrelated.write_text("z\n")
        _write_manifest(tmp_path, [unrelated])
        clew.verify_all_claims()
        out = tmp_path / "claims.json"
        # Act
        clew.export_claims_json(path=out, read_only=False)
        payload = json.loads(out.read_text())
        # Assert — the false-green claim resolves to amber unsourced.
        assert payload["claims"][0]["resolved_status"] == "unsourced"

    def test_export_color_is_burnt_amber(self, sandbox, tmp_path):
        # Arrange
        src, sid = _seed_tracked_source(sandbox, tmp_path)
        _add_claim(tmp_path, src, sid)
        unrelated = tmp_path / "unrelated.csv"
        unrelated.write_text("z\n")
        _write_manifest(tmp_path, [unrelated])
        clew.verify_all_claims()
        out = tmp_path / "claims.json"
        # Act
        clew.export_claims_json(path=out, read_only=False)
        payload = json.loads(out.read_text())
        # Assert
        assert payload["claims"][0]["color"] == "b26a00"


class TestPrecedence:
    def test_hash_mismatch_outranks_unsourced(self, sandbox, tmp_path):
        # Arrange — the claim's source changes after registration (hash fail)
        # AND it is ungrounded; the red integrity failure must win.
        src, sid = _seed_tracked_source(sandbox, tmp_path)
        _add_claim(tmp_path, src, sid)
        unrelated = tmp_path / "unrelated.csv"
        unrelated.write_text("z\n")
        _write_manifest(tmp_path, [unrelated])
        src.write_text('{"acc": 0.99}\n')  # tamper the claim's source
        # Act
        summary = clew.verify_all_claims()
        # Assert — HASH_MISMATCH (red), not UNSOURCED (amber).
        assert summary.exit_code == codes.HASH_MISMATCH


class TestMonotonic:
    def test_registering_source_flips_unsourced_to_ok(self, sandbox, tmp_path):
        # Arrange — start ungrounded (unsourced).
        src, sid = _seed_tracked_source(sandbox, tmp_path)
        _add_claim(tmp_path, src, sid)
        unrelated = tmp_path / "unrelated.csv"
        unrelated.write_text("z\n")
        _write_manifest(tmp_path, [unrelated])
        before = clew.verify_all_claims().exit_code
        # Act — now register the actual source too.
        _write_manifest(tmp_path, [unrelated, src])
        after = clew.verify_all_claims().exit_code
        # Assert — registering can only turn amber -> green.
        assert before == codes.UNSOURCED and after == codes.OK


class TestCliRoundTrip:
    def test_register_source_then_list_shows_ok(self, sandbox, tmp_path):
        # Arrange
        src = tmp_path / "raw.csv"
        src.write_text("a\n")
        runner = CliRunner()
        # Act
        reg = runner.invoke(main, ["register-source", str(src)])
        listed = runner.invoke(main, ["list-sources", "--json"])
        # Assert
        payload = json.loads(listed.output)
        assert reg.exit_code == 0 and payload["sources"][0]["reason"] == "OK"

    def test_register_source_dry_run_does_not_write(self, sandbox, tmp_path):
        # Arrange
        src = tmp_path / "raw.csv"
        src.write_text("a\n")
        runner = CliRunner()
        # Act
        result = runner.invoke(main, ["register-source", str(src), "--dry-run"])
        listed = json.loads(
            runner.invoke(main, ["list-sources", "--json"]).output
        )
        # Assert — dry-run reports but writes nothing.
        assert result.exit_code == 0 and listed["count"] == 0

    def test_register_source_yes_flag_is_accepted(self, sandbox, tmp_path):
        # Arrange
        src = tmp_path / "raw.csv"
        src.write_text("a\n")
        runner = CliRunner()
        # Act
        result = runner.invoke(main, ["register-source", str(src), "--yes"])
        # Assert
        assert result.exit_code == 0

    def test_verify_cli_exits_17_when_unsourced(self, sandbox, tmp_path):
        # Arrange
        src, sid = _seed_tracked_source(sandbox, tmp_path)
        _add_claim(tmp_path, src, sid)
        unrelated = tmp_path / "unrelated.csv"
        unrelated.write_text("z\n")
        _write_manifest(tmp_path, [unrelated])
        runner = CliRunner()
        # Act
        result = runner.invoke(main, ["verify"])
        # Assert
        assert result.exit_code == codes.UNSOURCED


# EOF
