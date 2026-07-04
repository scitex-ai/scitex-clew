#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for :mod:`scitex_clew._sources._writer` — register / list / unregister.

Per PA-306 §3 (no mocks): real files, real manifest round-trips.
"""

from __future__ import annotations

import json

from scitex_clew._sources._manifest import full_sha256
from scitex_clew._sources._writer import (
    list_sources,
    register_source,
    unregister_source,
)


def _manifest_path(root):
    return root / ".scitex" / "clew" / "sources.json"


def _mk(root, rel, content="a,b\n1,2\n"):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


class TestRegisterRoundTrip:
    def test_register_creates_manifest_with_entry(self, tmp_path):
        # Arrange
        src = _mk(tmp_path, "raw.csv")
        mp = _manifest_path(tmp_path)
        # Act
        register_source(str(src), sources_path=mp, root=tmp_path)
        entries = list_sources(sources_path=mp, root=tmp_path)
        # Assert
        assert entries[0]["path"] == "raw.csv" and entries[0]["reason"] == "OK"

    def test_register_pins_full_sha256(self, tmp_path):
        # Arrange
        src = _mk(tmp_path, "raw.csv")
        mp = _manifest_path(tmp_path)
        # Act
        register_source(str(src), sources_path=mp, root=tmp_path)
        entries = list_sources(sources_path=mp, root=tmp_path)
        # Assert — the pin is the full 64-char digest.
        assert entries[0]["sha256"] == full_sha256(src)

    def test_reregister_updates_hash_idempotently(self, tmp_path):
        # Arrange — register, mutate, re-register.
        src = _mk(tmp_path, "raw.csv")
        mp = _manifest_path(tmp_path)
        register_source(str(src), sources_path=mp, root=tmp_path)
        src.write_text("v2\n")
        # Act
        register_source(str(src), sources_path=mp, root=tmp_path)
        entries = list_sources(sources_path=mp, root=tmp_path)
        # Assert — one entry, updated hash, still valid.
        assert len(entries) == 1 and entries[0]["reason"] == "OK"

    def test_register_multiple_files(self, tmp_path):
        # Arrange
        a = _mk(tmp_path, "a.csv")
        b = _mk(tmp_path, "b.csv", "x\n")
        mp = _manifest_path(tmp_path)
        # Act
        register_source([str(a), str(b)], sources_path=mp, root=tmp_path)
        entries = list_sources(sources_path=mp, root=tmp_path)
        # Assert
        assert {e["path"] for e in entries} == {"a.csv", "b.csv"}

    def test_manifest_json_carries_reserved_signature(self, tmp_path):
        # Arrange
        src = _mk(tmp_path, "raw.csv")
        mp = _manifest_path(tmp_path)
        # Act
        register_source(str(src), sources_path=mp, root=tmp_path)
        raw = json.loads(mp.read_text())
        # Assert — the reserved (null) signature field is present.
        assert "signature" in raw and raw["schema"] == "sources-1.0"


class TestUnregister:
    def test_unregister_removes_entry(self, tmp_path):
        # Arrange
        a = _mk(tmp_path, "a.csv")
        b = _mk(tmp_path, "b.csv", "x\n")
        mp = _manifest_path(tmp_path)
        register_source([str(a), str(b)], sources_path=mp, root=tmp_path)
        # Act
        unregister_source(str(a), sources_path=mp, root=tmp_path)
        entries = list_sources(sources_path=mp, root=tmp_path)
        # Assert
        assert {e["path"] for e in entries} == {"b.csv"}


class TestListSources:
    def test_list_empty_when_no_manifest(self, tmp_path):
        # Arrange — no manifest.
        mp = _manifest_path(tmp_path)
        # Act
        entries = list_sources(sources_path=mp, root=tmp_path)
        # Assert
        assert entries == []


# EOF
