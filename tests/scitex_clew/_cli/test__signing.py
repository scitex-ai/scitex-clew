#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI integration tests for keygen / sign / verify-signatures.

Real click CliRunner + real Ed25519 (no mocks), explicit --key/--pub/manifest
paths so the test is isolated from project-root / home resolution. Skipped when
the optional 'cryptography' dependency is absent.
"""

import json

import pytest

pytest.importorskip("cryptography")

from click.testing import CliRunner  # noqa: E402

from scitex_clew._cli._signing import (  # noqa: E402
    keygen_cmd,
    sign_cmd,
    verify_signatures_cmd,
)


def _write_manifest(path):
    path.write_text(
        json.dumps(
            {
                "schema": "sources-1.0",
                "sources": [{"path": "data/cars2.csv", "sha256": "abc123"}],
                "signature": None,
            }
        )
    )


def test_keygen_sign_verify_roundtrip(tmp_path):
    # Arrange — keygen then sign the manifest with the fresh key.
    runner = CliRunner()
    key = tmp_path / "signing.key"
    pub = tmp_path / "signing.pub"
    manifest = tmp_path / "sources.json"
    _write_manifest(manifest)
    runner.invoke(keygen_cmd, ["--key", str(key), "--pub", str(pub)])
    runner.invoke(sign_cmd, [str(manifest), "--key", str(key)])
    # Act
    result = runner.invoke(verify_signatures_cmd, [str(manifest), "--pub", str(pub)])
    # Assert
    assert result.exit_code == 0


def test_verify_signatures_fails_on_tamper(tmp_path):
    # Arrange — sign, then tamper the manifest on disk.
    runner = CliRunner()
    key = tmp_path / "signing.key"
    pub = tmp_path / "signing.pub"
    manifest = tmp_path / "sources.json"
    _write_manifest(manifest)
    runner.invoke(keygen_cmd, ["--key", str(key), "--pub", str(pub)])
    runner.invoke(sign_cmd, [str(manifest), "--key", str(key)])
    raw = json.loads(manifest.read_text())
    raw["sources"][0]["sha256"] = "tampered"
    manifest.write_text(json.dumps(raw, indent=2, sort_keys=True))
    # Act
    result = runner.invoke(verify_signatures_cmd, [str(manifest), "--pub", str(pub)])
    # Assert
    assert result.exit_code == 1


def test_keygen_refuses_to_overwrite_existing_key(tmp_path):
    # Arrange — a key already exists.
    runner = CliRunner()
    key = tmp_path / "signing.key"
    pub = tmp_path / "signing.pub"
    runner.invoke(keygen_cmd, ["--key", str(key), "--pub", str(pub)])
    # Act — a second keygen without --force.
    result = runner.invoke(keygen_cmd, ["--key", str(key), "--pub", str(pub)])
    # Assert
    assert result.exit_code != 0
