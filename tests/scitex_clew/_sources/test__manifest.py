#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :mod:`scitex_clew._sources._manifest` — load, resolve, tamper-check.

Per PA-306 §3 (no mocks): real manifest files on disk, real sha256 recompute.
Per PA-307 §3: AAA markers + one observable assertion per test.
"""

from __future__ import annotations

import json
import os

import pytest

from scitex_clew._sources._manifest import (
    SOURCES_SCHEMA,
    _resolve_sources_tier3,
    full_sha256,
    load_sources_manifest,
    resolve_sources_path,
)


def _canonical_manifest_path(root):
    return root / ".scitex" / "clew" / "sources.json"


def _write_source(root, rel, content="a,b\n1,2\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _write_manifest(root, entries, signature=None):
    path = _canonical_manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema": SOURCES_SCHEMA, "sources": entries, "signature": signature}
        )
    )
    return path


class TestResolveSourcesPath:
    def test_explicit_arg_is_tier1(self, tmp_path):
        # Arrange
        explicit = tmp_path / "x.json"
        # Act
        path, label = resolve_sources_path(explicit)
        # Assert
        assert path == explicit and "explicit" in label

    def test_env_var_is_tier2(self, tmp_path):
        # Arrange — real env mutation with explicit undo.
        prev = os.environ.get("SCITEX_CLEW_SOURCES")
        os.environ["SCITEX_CLEW_SOURCES"] = str(tmp_path / "env.json")
        try:
            # Act
            path, label = resolve_sources_path()
            # Assert
            assert path == tmp_path / "env.json" and "SCITEX_CLEW_SOURCES" in label
        finally:
            if prev is None:
                os.environ.pop("SCITEX_CLEW_SOURCES", None)
            else:
                os.environ["SCITEX_CLEW_SOURCES"] = prev

    def test_tier3_default_is_scitex_clew_sources_json(self, tmp_path):
        # Arrange — no env; label names the project-root tier.
        prev = os.environ.pop("SCITEX_CLEW_SOURCES", None)
        try:
            # Act
            _path, label = resolve_sources_path()
            # Assert
            assert "project-root" in label
        finally:
            if prev is not None:
                os.environ["SCITEX_CLEW_SOURCES"] = prev


class TestLoadManifest:
    def test_absent_manifest_loads_none(self, tmp_path):
        # Arrange — no manifest file at the path.
        # Act
        manifest = load_sources_manifest(tmp_path / "nope.json")
        # Assert — opt-in: absent => gate inactive.
        assert manifest is None

    def test_valid_entry_is_active(self, tmp_path):
        # Arrange
        src = _write_source(tmp_path, "raw.csv")
        _write_manifest(tmp_path, [{"path": "raw.csv", "sha256": full_sha256(src)}])
        # Act
        manifest = load_sources_manifest(
            _canonical_manifest_path(tmp_path), root=tmp_path
        )
        # Assert
        assert manifest.active is True

    def test_empty_manifest_is_inactive(self, tmp_path):
        # Arrange — a present but empty manifest keeps the gate dormant.
        _write_manifest(tmp_path, [])
        # Act
        manifest = load_sources_manifest(
            _canonical_manifest_path(tmp_path), root=tmp_path
        )
        # Assert
        assert manifest.active is False

    def test_tampered_entry_is_invalid_and_surfaced(self, tmp_path):
        # Arrange — register, then change the file content on disk.
        src = _write_source(tmp_path, "raw.csv")
        _write_manifest(tmp_path, [{"path": "raw.csv", "sha256": full_sha256(src)}])
        src.write_text("CHANGED\n")
        # Act
        manifest = load_sources_manifest(
            _canonical_manifest_path(tmp_path), root=tmp_path
        )
        # Assert — a changed file is not a trust anchor (surfaced as TAMPERED).
        assert manifest.entries[0].reason == "TAMPERED" and not manifest.active

    def test_missing_file_entry_is_invalid(self, tmp_path):
        # Arrange — pin a file that does not exist.
        _write_manifest(tmp_path, [{"path": "ghost.csv", "sha256": "0" * 64}])
        # Act
        manifest = load_sources_manifest(
            _canonical_manifest_path(tmp_path), root=tmp_path
        )
        # Assert
        assert manifest.entries[0].reason == "MISSING"

    def test_malformed_json_fails_loud(self, tmp_path):
        # Arrange — not valid JSON.
        path = _canonical_manifest_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")

        # Act
        def act():
            return load_sources_manifest(path, root=tmp_path)

        # Assert
        with pytest.raises(ValueError):
            act()

    def test_wrong_schema_fails_loud(self, tmp_path):
        # Arrange
        path = _canonical_manifest_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": "sources-9.9", "sources": []}))

        # Act
        def act():
            return load_sources_manifest(path, root=tmp_path)

        # Assert
        with pytest.raises(ValueError):
            act()

    def test_malformed_entry_fails_loud(self, tmp_path):
        # Arrange — an entry missing 'sha256'.
        path = _canonical_manifest_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"schema": SOURCES_SCHEMA, "sources": [{"path": "x"}]})
        )

        # Act
        def act():
            return load_sources_manifest(path, root=tmp_path)

        # Assert
        with pytest.raises(ValueError):
            act()

    def test_signature_field_is_reserved_not_enforced(self, tmp_path):
        # Arrange — a signature is accepted but does NOT block loading now.
        src = _write_source(tmp_path, "raw.csv")
        _write_manifest(
            tmp_path,
            [{"path": "raw.csv", "sha256": full_sha256(src)}],
            signature="not-a-real-signature",
        )
        # Act
        manifest = load_sources_manifest(
            _canonical_manifest_path(tmp_path), root=tmp_path
        )
        # Assert — loads fine; the signature is carried through, not enforced.
        assert manifest.signature == "not-a-real-signature" and manifest.active


# --- tier-3 manifest precedence: signed/ > user_definitions/ > legacy --------


def test_tier3_prefers_signed_when_present(tmp_path):
    # Arrange
    signed = tmp_path / "signed" / "sources.json"
    signed.parent.mkdir(parents=True)
    signed.write_text("{}")
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert
    assert path == signed


def test_tier3_falls_back_to_user_definitions(tmp_path):
    # Arrange — no signed/, but a pre-rename user_definitions/ manifest.
    ud = tmp_path / "user_definitions" / "sources.json"
    ud.parent.mkdir(parents=True)
    ud.write_text("{}")
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert
    assert path == ud


def test_tier3_legacy_flat_still_resolved(tmp_path):
    # Arrange — only the flat legacy path exists.
    legacy = tmp_path / "sources.json"
    legacy.write_text("{}")
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert
    assert path == legacy


def test_tier3_defaults_new_manifest_to_signed(tmp_path):
    # Arrange — nothing exists yet.
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert — new writes default to signed/ (register-source + sign share it).
    assert path == tmp_path / "signed" / "sources.json"


def test_tier3_signed_wins_over_legacy_when_both_exist(tmp_path):
    # Arrange — both signed/ and legacy present; signed/ must win.
    signed = tmp_path / "signed" / "sources.json"
    signed.parent.mkdir(parents=True)
    signed.write_text("{}")
    (tmp_path / "sources.json").write_text("{}")
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert
    assert path == signed


# EOF
