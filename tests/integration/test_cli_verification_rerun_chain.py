#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for the rerun / chain / register-intermediate commands.

- Drive each subcommand in-process via ``click.testing.CliRunner``.
- Inject an isolated temp DB via ``set_db()`` so nothing leaks between tests.
- Empty-DB happy paths exercise the wiring (JSON shape, exit code) without
  re-executing any user scripts; error paths cover the obvious failure.
"""

from __future__ import annotations

import json
import os

import pytest

# click lives in the [cli] extra, not the base deps.
CliRunner = pytest.importorskip("click.testing").CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli._main import main
from scitex_clew._db import set_db

_FAKE_SESSION = "2026Y-05M-27D-00h00m00s_Test-main"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    set_db(tmp_path / "cli_rerun_chain.db")
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def no_session_env():
    """Ensure $SCITEX_SESSION_ID is absent, restoring any prior value."""
    saved = os.environ.pop("SCITEX_SESSION_ID", None)
    yield
    if saved is not None:
        os.environ["SCITEX_SESSION_ID"] = saved


# ---------------------------------------------------------------------------
# clew chain
# ---------------------------------------------------------------------------


class TestChain:
    def test_missing_file_exits_one(self, runner, tmp_path):
        # Arrange
        missing = tmp_path / "nope.png"
        # Act
        result = runner.invoke(main, ["chain", str(missing)])
        # Assert
        assert result.exit_code == 1

    def test_missing_file_reports_not_found(self, runner, tmp_path):
        # Arrange
        missing = tmp_path / "nope.png"
        # Act
        result = runner.invoke(main, ["chain", str(missing)])
        # Assert
        assert "not found" in result.output.lower()

    def test_untracked_file_exits_zero(self, runner, tmp_path):
        # Arrange
        target = tmp_path / "fig.png"
        target.write_bytes(b"\x89PNG")
        # Act
        result = runner.invoke(main, ["chain", str(target), "--json"])
        # Assert
        assert result.exit_code == 0

    def test_untracked_file_json_has_chain_keys(self, runner, tmp_path):
        # Arrange
        target = tmp_path / "fig.png"
        target.write_bytes(b"\x89PNG")
        # Act
        result = runner.invoke(main, ["chain", str(target), "--json"])
        # Assert
        assert {"target_file", "status", "chain_length"}.issubset(
            json.loads(result.output)
        )


# ---------------------------------------------------------------------------
# clew rerun-dag
# ---------------------------------------------------------------------------


class TestRerunDag:
    def test_empty_db_exits_zero(self, runner):
        # Arrange
        argv = ["rerun-dag", "--json"]
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert result.exit_code == 0

    def test_empty_db_reports_zero_runs(self, runner):
        # Arrange
        argv = ["rerun-dag", "--json"]
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert json.loads(result.output)["num_runs"] == 0

    def test_human_output_has_label(self, runner):
        # Arrange
        argv = ["rerun-dag"]
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert "rerun-dag" in result.output


# ---------------------------------------------------------------------------
# clew rerun-claims
# ---------------------------------------------------------------------------


class TestRerunClaims:
    def test_no_claims_reports_zero_runs(self, runner):
        # Arrange
        argv = ["rerun-claims", "--json"]
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert json.loads(result.output)["num_runs"] == 0

    def test_invalid_type_rejected(self, runner):
        # Arrange
        argv = ["rerun-claims", "--type", "bogus"]
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# clew claim register-intermediate
# ---------------------------------------------------------------------------


class TestRegisterIntermediate:
    _ARGV = [
        "claim",
        "register-intermediate",
        "--name",
        "n_sig_pathways",
        "--value",
        "42",
        "--session-id",
        _FAKE_SESSION,
        "--supports",
        "upstream_a",
        "--json",
    ]

    def test_explicit_session_exits_zero(self, runner):
        # Arrange
        argv = list(self._ARGV)
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert result.exit_code == 0

    def test_explicit_session_returns_claim_id(self, runner):
        # Arrange
        argv = list(self._ARGV)
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert json.loads(result.output).get("claim_id")

    def test_missing_session_exits_one(self, runner, no_session_env):
        # Arrange
        argv = ["claim", "register-intermediate", "--name", "x", "--value", "1"]
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert result.exit_code == 1

    def test_missing_session_reports_session(self, runner, no_session_env):
        # Arrange
        argv = ["claim", "register-intermediate", "--name", "x", "--value", "1"]
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert "session" in result.output.lower()

    def test_dry_run_exits_zero_without_session(self, runner, no_session_env):
        # Arrange
        argv = [
            "claim",
            "register-intermediate",
            "--name",
            "x",
            "--value",
            "1",
            "--dry-run",
        ]
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert result.exit_code == 0

    def test_dry_run_does_not_write(self, runner, no_session_env):
        # Arrange
        argv = [
            "claim",
            "register-intermediate",
            "--name",
            "x",
            "--value",
            "1",
            "--dry-run",
        ]
        # Act
        result = runner.invoke(main, argv)
        # Assert
        assert "DRY RUN" in result.output


# EOF
