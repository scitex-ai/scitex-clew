#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Manifest tier-3 precedence: signed/ > user_definitions/ > legacy > default.

Real temp dirs, no mocks — _resolve_sources_tier3 takes the clew dir explicitly
so the precedence is exercised against a real filesystem.
"""

from scitex_clew._sources._manifest import _resolve_sources_tier3


def test_prefers_signed_when_present(tmp_path):
    # Arrange
    signed = tmp_path / "signed" / "sources.json"
    signed.parent.mkdir(parents=True)
    signed.write_text("{}")
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert
    assert path == signed


def test_falls_back_to_user_definitions(tmp_path):
    # Arrange — no signed/, but a pre-rename user_definitions/ manifest.
    ud = tmp_path / "user_definitions" / "sources.json"
    ud.parent.mkdir(parents=True)
    ud.write_text("{}")
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert
    assert path == ud


def test_legacy_flat_still_resolved(tmp_path):
    # Arrange — only the flat legacy path exists.
    legacy = tmp_path / "sources.json"
    legacy.write_text("{}")
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert
    assert path == legacy


def test_defaults_new_manifest_to_signed(tmp_path):
    # Arrange — nothing exists yet.
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert — new writes default to signed/ (register-source + sign share it).
    assert path == tmp_path / "signed" / "sources.json"


def test_signed_wins_over_legacy_when_both_exist(tmp_path):
    # Arrange — both signed/ and legacy present; signed/ must win.
    signed = tmp_path / "signed" / "sources.json"
    signed.parent.mkdir(parents=True)
    signed.write_text("{}")
    (tmp_path / "sources.json").write_text("{}")
    # Act
    path, _label = _resolve_sources_tier3(tmp_path)
    # Assert
    assert path == signed
