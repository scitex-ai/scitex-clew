#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Signature-aware ENFORCEMENT: an untrusted manifest grounds nothing.

Real Ed25519 (no mocks). End-to-end: the SAME claim (a run reading a registered
data source) GROUNDS under a validly-signed manifest but is BLOCKED (is_grounded
False) under an unsigned/tampered manifest once a signing.pub is committed —
so editing the manifest to launder a claim fails. Absent a committed pubkey,
signing is not enforced (permissive; zero behavior change). Skipped when the
optional 'cryptography' dependency is absent.
"""

import json

import pytest

pytest.importorskip("cryptography")

import scitex_clew as clew  # noqa: E402
from scitex_clew._claim._register import list_claims  # noqa: E402
from scitex_clew._db import use_db  # noqa: E402
from scitex_clew._sources import is_grounded, load_sources_manifest  # noqa: E402
from scitex_clew._sources._signing import (  # noqa: E402
    generate_keypair,
    sign_manifest,
)
from scitex_clew._sources._writer import register_source  # noqa: E402


def _paths(tmp_path):
    clew_dir = tmp_path / ".scitex" / "clew"
    clew_dir.mkdir(parents=True)
    return clew_dir / "clew.db", clew_dir / "sources.json"


def _register_run_claim(tmp_path, db_path, manifest_path):
    """Register a data source, record a run reading it -> output, claim on the
    output. Returns the Claim (grounds to the source under a trusted manifest)."""
    src = tmp_path / "data.csv"
    src.write_text("x\n1\n")
    out = tmp_path / "out.json"
    out.write_text('{"n": 1}\n')
    with use_db(db_path):
        register_source([src], sources_path=manifest_path, root=tmp_path)
        with clew.session() as run:
            run.record_input(src)
            run.record_output(out)
        clew.add_claim("paper.tex", "value", 1, "1", source_file=str(out))
        return list_claims(limit=10)[0]


def _commit_pubkey(tmp_path):
    private_pem, public_pem = generate_keypair()
    signed_dir = tmp_path / ".scitex" / "clew" / "signed"
    signed_dir.mkdir(parents=True)
    (signed_dir / "signing.pub").write_bytes(public_pem)
    return private_pem


def _sign_on_disk(manifest_path, private_pem):
    raw = json.loads(manifest_path.read_text())
    raw["signature"] = sign_manifest(raw, private_pem)
    manifest_path.write_text(
        json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=False)
    )


# --- manifest-level trust state ---------------------------------------------


def test_no_pubkey_is_permissive_and_active(tmp_path):
    # Arrange — no signing.pub committed.
    _, manifest_path = _paths(tmp_path)
    src = tmp_path / "data.csv"
    src.write_text("x\n1\n")
    register_source([src], sources_path=manifest_path, root=tmp_path)
    # Act
    manifest = load_sources_manifest(manifest_path, root=tmp_path)
    # Assert — signing not enforced -> trusted -> active.
    assert manifest.active is True


def test_unsigned_manifest_under_pubkey_keeps_gate_active(tmp_path):
    # Arrange — pubkey committed, manifest UNSIGNED (untrusted).
    _, manifest_path = _paths(tmp_path)
    src = tmp_path / "data.csv"
    src.write_text("x\n1\n")
    register_source([src], sources_path=manifest_path, root=tmp_path)
    _commit_pubkey(tmp_path)
    # Act
    manifest = load_sources_manifest(manifest_path, root=tmp_path)
    # Assert — gate FIRES even untrusted, so its claims get blocked (not dormant).
    assert manifest.active is True


def test_unsigned_manifest_under_pubkey_anchors_nothing(tmp_path):
    # Arrange
    _, manifest_path = _paths(tmp_path)
    src = tmp_path / "data.csv"
    src.write_text("x\n1\n")
    register_source([src], sources_path=manifest_path, root=tmp_path)
    _commit_pubkey(tmp_path)
    # Act
    manifest = load_sources_manifest(manifest_path, root=tmp_path)
    # Assert — untrusted -> no trusted anchors.
    assert manifest.anchor_paths() == set()


# --- end-to-end grounding (the actual enforcement) --------------------------


def test_signed_manifest_grounds_a_claim(tmp_path):
    # Arrange — register + run + claim, then commit pubkey and SIGN the manifest.
    db_path, manifest_path = _paths(tmp_path)
    claim = _register_run_claim(tmp_path, db_path, manifest_path)
    private_pem = _commit_pubkey(tmp_path)
    _sign_on_disk(manifest_path, private_pem)
    with use_db(db_path) as db:
        manifest = load_sources_manifest(manifest_path, root=tmp_path)
        # Act
        grounded = is_grounded(claim, manifest, db)
    # Assert — trusted signed manifest grounds the claim to its registered source.
    assert grounded is True


def test_untrusted_manifest_blocks_a_grounded_claim(tmp_path):
    # Arrange — identical run+claim, but commit pubkey WITHOUT signing (untrusted).
    db_path, manifest_path = _paths(tmp_path)
    claim = _register_run_claim(tmp_path, db_path, manifest_path)
    _commit_pubkey(tmp_path)
    with use_db(db_path) as db:
        manifest = load_sources_manifest(manifest_path, root=tmp_path)
        # Act
        grounded = is_grounded(claim, manifest, db)
    # Assert — the SAME claim that grounds when signed is BLOCKED when untrusted.
    assert grounded is False


def test_tampered_manifest_blocks_a_grounded_claim(tmp_path):
    # Arrange — sign, then tamper (inject a fabricated source) -> signature breaks.
    db_path, manifest_path = _paths(tmp_path)
    claim = _register_run_claim(tmp_path, db_path, manifest_path)
    private_pem = _commit_pubkey(tmp_path)
    _sign_on_disk(manifest_path, private_pem)
    raw = json.loads(manifest_path.read_text())
    raw["sources"].append({"path": "fabricated.csv", "sha256": "0" * 64})
    manifest_path.write_text(
        json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=False)
    )
    with use_db(db_path) as db:
        manifest = load_sources_manifest(manifest_path, root=tmp_path)
        # Act
        grounded = is_grounded(claim, manifest, db)
    # Assert — tamper breaks the signature -> untrusted -> claim blocked.
    assert grounded is False
