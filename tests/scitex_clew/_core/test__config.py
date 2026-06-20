#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the ``.scitex/clew`` layered config resolver (``_config``).

Pins the SciTeX ``.scitex/<pkg>`` convention: user (``$SCITEX_DIR/clew``)
< project (``<git-root>/.scitex/clew``) < explicit ``--config``, deep-merged,
with ``config.yaml`` + a ``config/`` overlay dir. Fail-loud on malformed or
missing-explicit config (no silent fallbacks).

PA-306 §3 (no mocks): real files on disk + real ``$SCITEX_DIR`` mutation with
explicit undo. PA-307 §3: AAA markers + one observable assertion per test.
"""

from __future__ import annotations

import os

import pytest

from scitex_clew._core import _config


@pytest.fixture(autouse=True)
def isolate_user_scope(tmp_path):
    # Pin the user scope to an empty temp dir so the real ~/.scitex/clew can
    # never leak into these tests (real env mutation, explicit undo).
    prev = os.environ.get("SCITEX_DIR")
    os.environ["SCITEX_DIR"] = str(tmp_path / "user_home")
    yield
    if prev is None:
        os.environ.pop("SCITEX_DIR", None)
    else:
        os.environ["SCITEX_DIR"] = prev


def _user_cfg(tmp_path, body):
    """Seed ``$SCITEX_DIR/clew/config.yaml`` (user scope)."""
    d = tmp_path / "user_home" / "clew"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.yaml").write_text(body)


def _project(tmp_path, body=None):
    """Make a git-root project dir; optionally seed .scitex/clew/config.yaml."""
    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True, exist_ok=True)
    if body is not None:
        d = root / ".scitex" / "clew"
        d.mkdir(parents=True, exist_ok=True)
        (d / "config.yaml").write_text(body)
    return root


class TestLoadConfig:
    def test_absent_config_returns_empty(self, tmp_path):
        # Arrange — git root with no .scitex, empty user scope.
        root = _project(tmp_path)
        # Act
        cfg = _config.load_config(start=root)
        # Assert
        assert cfg == {}

    def test_user_scope_is_loaded(self, tmp_path):
        # Arrange
        _user_cfg(tmp_path, "verify:\n  severity:\n    unverified: warning\n")
        root = _project(tmp_path)
        # Act
        cfg = _config.load_config(start=root)
        # Assert
        assert cfg["verify"]["severity"]["unverified"] == "warning"

    def test_project_overrides_user_per_key(self, tmp_path):
        # Arrange — user sets two keys; project overrides only one (deep merge).
        _user_cfg(
            tmp_path,
            "verify:\n  severity:\n    unverified: warning\n    no_claims: warning\n",
        )
        root = _project(tmp_path, "verify:\n  severity:\n    unverified: error\n")
        # Act
        sev = _config.load_config(start=root)["verify"]["severity"]
        # Assert — project wins on unverified; user's no_claims survives.
        assert sev == {"unverified": "error", "no_claims": "warning"}

    def test_config_dir_overlay_wins_over_config_yaml(self, tmp_path):
        # Arrange — config.yaml base + config/ overlay in the same scope.
        d = tmp_path / "user_home" / "clew"
        (d / "config").mkdir(parents=True, exist_ok=True)
        (d / "config.yaml").write_text(
            "verify:\n  severity:\n    unverified: warning\n"
        )
        (d / "config" / "z.yaml").write_text(
            "verify:\n  severity:\n    unverified: ignore\n"
        )
        # Act
        sev = _config.load_config(start=_project(tmp_path))["verify"]["severity"]
        # Assert
        assert sev["unverified"] == "ignore"

    def test_explicit_file_overrides_scopes(self, tmp_path):
        # Arrange
        _user_cfg(tmp_path, "verify:\n  severity:\n    unverified: warning\n")
        explicit = tmp_path / "override.yaml"
        explicit.write_text("verify:\n  severity:\n    unverified: ignore\n")
        # Act
        cfg = _config.load_config(start=_project(tmp_path), explicit=explicit)
        # Assert
        assert cfg["verify"]["severity"]["unverified"] == "ignore"

    def test_explicit_missing_path_raises(self, tmp_path):
        # Arrange
        missing = tmp_path / "nope.yaml"
        root = _project(tmp_path)
        # Act — loading an explicit-but-missing --config path is the action.
        # Assert — fail loud, no silent fallback.
        with pytest.raises(FileNotFoundError):
            _config.load_config(start=root, explicit=missing)

    def test_malformed_non_mapping_raises(self, tmp_path):
        # Arrange — a YAML list at top level is not a config mapping.
        _user_cfg(tmp_path, "- a\n- b\n")
        root = _project(tmp_path)
        # Act — resolving config with a malformed user file is the action.
        # Assert
        with pytest.raises(ValueError):
            _config.load_config(start=root)


# EOF
