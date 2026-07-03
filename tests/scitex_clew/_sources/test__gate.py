#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :mod:`scitex_clew._sources._gate` — the chain-walk grounding gate.

Per PA-306 §3 (no mocks): a real isolated DB seeded with real runs/file
hashes, a real on-disk manifest, and the real chain walk. Per PA-307 §3:
AAA markers + one observable assertion per test.
"""

from __future__ import annotations

import os

import pytest

import scitex_clew._db as _db_module
from scitex_clew._claim._register import add_claim
from scitex_clew._db import set_db
from scitex_clew._hash import hash_file
from scitex_clew._sources._gate import is_grounded
from scitex_clew._sources._manifest import full_sha256, load_sources_manifest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    set_db(tmp_path / "gate.db")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _manifest_path(root):
    return root / ".scitex" / "clew" / "sources.json"


def _mk(root, rel, content="x\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _write_manifest(root, files):
    import json

    from scitex_clew._sources._manifest import SOURCES_SCHEMA

    entries = [
        {"path": str(f.relative_to(root)), "sha256": full_sha256(f)} for f in files
    ]
    path = _manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"schema": SOURCES_SCHEMA, "sources": entries, "signature": None})
    )
    return path


class TestIsGrounded:
    def test_grounded_when_claim_source_is_registered(self, isolated_db, tmp_path):
        # Arrange — the claim's own source file IS a registered source.
        src = _mk(tmp_path, "raw.csv")
        _write_manifest(tmp_path, [src])
        manifest = load_sources_manifest(_manifest_path(tmp_path), root=tmp_path)
        paper = _mk(tmp_path, "p.tex", "v\n")
        claim = add_claim(
            file_path=str(paper), claim_type="value", line_number=1,
            claim_value="1", source_file=str(src),
        )
        # Act
        grounded = is_grounded(claim, manifest, isolated_db)
        # Assert
        assert grounded is True

    def test_ungrounded_when_chain_reaches_no_registered_source(
        self, isolated_db, tmp_path
    ):
        # Arrange — the manifest is active via an UNRELATED source; the claim's
        # source is not registered and reaches nothing registered.
        unrelated = _mk(tmp_path, "other.csv")
        _write_manifest(tmp_path, [unrelated])
        manifest = load_sources_manifest(_manifest_path(tmp_path), root=tmp_path)
        src = _mk(tmp_path, "handmade.csv", "0.94\n")
        paper = _mk(tmp_path, "p.tex", "v\n")
        claim = add_claim(
            file_path=str(paper), claim_type="value", line_number=1,
            claim_value="0.94", source_file=str(src),
        )
        # Act
        grounded = is_grounded(claim, manifest, isolated_db)
        # Assert — the biomarker case: link-verified but ungrounded.
        assert grounded is False

    def test_mixed_chain_with_one_registered_root_is_grounded(
        self, isolated_db, tmp_path
    ):
        # Arrange — a session with TWO root inputs (one registered, one not).
        reg = _mk(tmp_path, "reg.csv", "R\n")
        unreg = _mk(tmp_path, "unreg.csv", "U\n")
        out = _mk(tmp_path, "out.csv", "O\n")
        sid = "2026Y-07M-03D-00h00m00s_Mix-main"
        isolated_db.add_run(sid, str(tmp_path / "make.py"))
        isolated_db.add_file_hash(sid, str(reg.resolve()), hash_file(reg), "input")
        isolated_db.add_file_hash(sid, str(unreg.resolve()), hash_file(unreg), "input")
        isolated_db.add_file_hash(sid, str(out.resolve()), hash_file(out), "output")
        isolated_db.finish_run(sid, status="success")
        _write_manifest(tmp_path, [reg])  # only ONE root registered
        manifest = load_sources_manifest(_manifest_path(tmp_path), root=tmp_path)
        paper = _mk(tmp_path, "p.tex", "v\n")
        claim = add_claim(
            file_path=str(paper), claim_type="value", line_number=1,
            claim_value="1", source_file=str(out), source_session=sid,
        )
        # Act
        grounded = is_grounded(claim, manifest, isolated_db)
        # Assert — laundering guard: >=1 registered root grounds the whole chain.
        assert grounded is True

    def test_tampered_anchor_does_not_ground(self, isolated_db, tmp_path):
        # Arrange — manifest active via an unrelated valid source; the claim's
        # source WAS registered but its content changed (tampered => invalid).
        valid_other = _mk(tmp_path, "other.csv")
        src = _mk(tmp_path, "raw.csv", "orig\n")
        _write_manifest(tmp_path, [valid_other, src])
        src.write_text("TAMPERED\n")  # break the pinned hash for src
        manifest = load_sources_manifest(_manifest_path(tmp_path), root=tmp_path)
        paper = _mk(tmp_path, "p.tex", "v\n")
        claim = add_claim(
            file_path=str(paper), claim_type="value", line_number=1,
            claim_value="1", source_file=str(src),
        )
        # Act
        grounded = is_grounded(claim, manifest, isolated_db)
        # Assert — a tampered entry is not a trust anchor.
        assert grounded is False


# EOF
