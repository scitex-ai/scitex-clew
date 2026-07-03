#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``clew export-claims`` (mirrors ``_cli/_export.py``).

Per PA-306 §3 (no mocks): real isolated DB + CliRunner. Per PA-307 §3: AAA
markers + one assertion per test.
"""

from __future__ import annotations

import json
import os

import pytest

CliRunner = pytest.importorskip("click.testing").CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli._main import main
from scitex_clew._db import set_db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    set_db(tmp_path / "cli_export.db")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


@pytest.fixture
def runner():
    return CliRunner()


def test_unified_export_writes_unified_schema(runner, tmp_path):
    # Arrange
    import scitex_clew as clew

    clew.add_citation("Berens2009", doi="10.1/x")
    out = tmp_path / "unified.json"
    # Act
    result = runner.invoke(
        main,
        ["export-claims", "--unified", "--path", str(out), "--no-read-only"],
    )
    # Assert
    assert json.loads(out.read_text())["schema_version"] == "1.6-unified"


def test_unified_export_exits_zero(runner, tmp_path):
    # Arrange
    out = tmp_path / "unified.json"
    # Act
    result = runner.invoke(
        main,
        ["export-claims", "--unified", "--path", str(out), "--no-read-only"],
    )
    # Assert
    assert result.exit_code == 0


def test_default_export_is_per_claim_v14(runner, tmp_path):
    # Arrange
    out = tmp_path / "v14.json"
    # Act
    result = runner.invoke(
        main,
        ["export-claims", "--path", str(out), "--no-read-only"],
    )
    # Assert
    assert json.loads(out.read_text())["schema_version"] == "1.4"


def test_json_flag_emits_path(runner, tmp_path):
    # Arrange
    out = tmp_path / "u.json"
    # Act
    result = runner.invoke(
        main,
        ["export-claims", "--unified", "--path", str(out), "--no-read-only", "--json"],
    )
    # Assert
    assert json.loads(result.output)["unified"] is True


# EOF
