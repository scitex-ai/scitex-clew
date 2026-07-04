#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI tests for ``clew claim {remove,supersede,list --file-path-prefix}``.

Mirrors ``src/scitex_clew/_cli/_claim.py``.

Per PA-306 §3 (no mocks): real isolated DB via set_db + CliRunner.
Per PA-307 §3: AAA marker comments + one observable assertion per test.
"""
from __future__ import annotations

import json
import os

import pytest

CliRunner = pytest.importorskip("click.testing").CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli._main import main
from scitex_clew._db import set_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Fresh isolated DB per test; auto-export disabled to avoid path noise."""
    db_path = tmp_path / "cli_claim_test.db"
    set_db(db_path)
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


@pytest.fixture
def runner():
    return CliRunner()


def _add_claim(runner, file_path, line_number=1, value="0.94"):
    """Helper: invoke claim add via CLI and return claim_id from JSON output."""
    result = runner.invoke(
        main,
        [
            "--json",
            "claim",
            "add",
            "--file-path",
            file_path,
            "--type",
            "value",
            "--line-number",
            str(line_number),
            "--value",
            value,
        ],
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["claim_id"]


# ---------------------------------------------------------------------------
# clew claim remove — single claim by ID
# ---------------------------------------------------------------------------


class TestClaimRemoveById:
    def test_remove_existing_claim_exit_code_zero(self, runner, isolated_db, tmp_path):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        claim_id = _add_claim(runner, str(paper))
        # Act
        result = runner.invoke(main, ["claim", "remove", claim_id, "-y"])
        # Assert
        assert result.exit_code == 0

    def test_remove_existing_claim_json_removed_true(self, runner, isolated_db, tmp_path):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        claim_id = _add_claim(runner, str(paper))
        # Act
        result = runner.invoke(main, ["--json", "claim", "remove", claim_id, "-y"])
        # Assert
        payload = json.loads(result.output)
        assert payload["removed"] is True

    def test_remove_nonexistent_claim_exits_nonzero(self, runner, isolated_db):
        # Arrange
        # Act
        result = runner.invoke(main, ["claim", "remove", "claim_nonexistent_000", "-y"])
        # Assert
        assert result.exit_code != 0

    def test_remove_claim_subsequent_list_is_empty(self, runner, isolated_db, tmp_path):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        claim_id = _add_claim(runner, str(paper))
        runner.invoke(main, ["claim", "remove", claim_id, "-y"])
        # Act
        result = runner.invoke(main, ["--json", "claim", "list"])
        # Assert
        payload = json.loads(result.output)
        assert payload["count"] == 0


# ---------------------------------------------------------------------------
# clew claim remove — bulk by prefix
# ---------------------------------------------------------------------------


class TestClaimRemoveByPrefix:
    def test_bulk_remove_by_prefix_exit_code_zero(self, runner, isolated_db, tmp_path):
        # Arrange
        dir_a = tmp_path / "proj_a"
        dir_a.mkdir()
        _add_claim(runner, str(dir_a / "paper.tex"))
        # Act
        result = runner.invoke(
            main, ["claim", "remove", "--file-path-prefix", str(dir_a), "-y"]
        )
        # Assert
        assert result.exit_code == 0

    def test_bulk_remove_reports_count_in_json(self, runner, isolated_db, tmp_path):
        # Arrange
        dir_a = tmp_path / "proj_a"
        dir_a.mkdir()
        _add_claim(runner, str(dir_a / "paper.tex"), line_number=1)
        _add_claim(runner, str(dir_a / "paper.tex"), line_number=2)
        # Act
        result = runner.invoke(
            main,
            ["--json", "claim", "remove", "--file-path-prefix", str(dir_a), "-y"],
        )
        # Assert
        payload = json.loads(result.output)
        assert payload["deleted"] == 2

    def test_bulk_remove_prefix_no_match_exit_zero(self, runner, isolated_db, tmp_path):
        # Arrange — no claims exist
        dir_x = tmp_path / "nonexistent"
        # Act
        result = runner.invoke(
            main, ["claim", "remove", "--file-path-prefix", str(dir_x), "-y"]
        )
        # Assert — should succeed gracefully (0 matches is not an error)
        assert result.exit_code == 0

    def test_bulk_remove_errors_when_both_id_and_prefix_given(
        self, runner, isolated_db, tmp_path
    ):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        claim_id = _add_claim(runner, str(paper))
        # Act
        result = runner.invoke(
            main,
            [
                "claim",
                "remove",
                claim_id,
                "--file-path-prefix",
                str(tmp_path),
                "-y",
            ],
        )
        # Assert — mutually exclusive → non-zero exit
        assert result.exit_code != 0

    def test_bulk_remove_errors_when_neither_given(self, runner, isolated_db):
        # Arrange
        # Act
        result = runner.invoke(main, ["claim", "remove", "-y"])
        # Assert
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# clew claim supersede — single claim by ID
# ---------------------------------------------------------------------------


class TestClaimSupersede:
    def test_supersede_existing_claim_exit_code_zero(self, runner, isolated_db, tmp_path):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        claim_id = _add_claim(runner, str(paper))
        # Act
        result = runner.invoke(main, ["claim", "supersede", claim_id])
        # Assert
        assert result.exit_code == 0

    def test_supersede_returns_superseded_true_in_json(self, runner, isolated_db, tmp_path):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        claim_id = _add_claim(runner, str(paper))
        # Act
        result = runner.invoke(main, ["--json", "claim", "supersede", claim_id])
        # Assert
        payload = json.loads(result.output)
        assert payload["superseded"] is True

    def test_supersede_nonexistent_claim_exits_nonzero(self, runner, isolated_db):
        # Arrange
        # Act
        result = runner.invoke(main, ["claim", "supersede", "claim_nonexistent_000"])
        # Assert
        assert result.exit_code != 0

    def test_supersede_claim_excluded_from_default_list(self, runner, isolated_db, tmp_path):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        claim_id = _add_claim(runner, str(paper))
        runner.invoke(main, ["claim", "supersede", claim_id])
        # Act
        result = runner.invoke(main, ["--json", "claim", "list"])
        # Assert
        payload = json.loads(result.output)
        assert payload["count"] == 0


# ---------------------------------------------------------------------------
# clew claim supersede — bulk by prefix
# ---------------------------------------------------------------------------


class TestClaimSupersedeBulk:
    def test_bulk_supersede_exit_code_zero(self, runner, isolated_db, tmp_path):
        # Arrange
        dir_a = tmp_path / "proj_a"
        dir_a.mkdir()
        _add_claim(runner, str(dir_a / "paper.tex"))
        # Act
        result = runner.invoke(
            main, ["claim", "supersede", "--file-path-prefix", str(dir_a), "-y"]
        )
        # Assert
        assert result.exit_code == 0

    def test_bulk_supersede_reports_count_in_json(self, runner, isolated_db, tmp_path):
        # Arrange
        dir_a = tmp_path / "proj_a"
        dir_a.mkdir()
        _add_claim(runner, str(dir_a / "paper.tex"), line_number=1)
        _add_claim(runner, str(dir_a / "paper.tex"), line_number=2)
        # Act
        result = runner.invoke(
            main,
            ["--json", "claim", "supersede", "--file-path-prefix", str(dir_a), "-y"],
        )
        # Assert
        payload = json.loads(result.output)
        assert payload["superseded"] == 2

    def test_bulk_supersede_errors_when_both_given(self, runner, isolated_db, tmp_path):
        # Arrange
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        claim_id = _add_claim(runner, str(paper))
        # Act
        result = runner.invoke(
            main,
            [
                "claim",
                "supersede",
                claim_id,
                "--file-path-prefix",
                str(tmp_path),
                "-y",
            ],
        )
        # Assert
        assert result.exit_code != 0

    def test_bulk_supersede_errors_when_neither_given(self, runner, isolated_db):
        # Arrange
        # Act
        result = runner.invoke(main, ["claim", "supersede"])
        # Assert
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# clew claim list --file-path-prefix
# ---------------------------------------------------------------------------


class TestClaimListFilePathPrefix:
    def test_list_prefix_returns_only_matching(self, runner, isolated_db, tmp_path):
        # Arrange
        dir_a = tmp_path / "proj_a"
        dir_b = tmp_path / "proj_b"
        dir_a.mkdir()
        dir_b.mkdir()
        _add_claim(runner, str(dir_a / "paper.tex"), line_number=1)
        _add_claim(runner, str(dir_b / "paper.tex"), line_number=1)
        # Act
        result = runner.invoke(
            main,
            ["--json", "claim", "list", "--file-path-prefix", str(dir_a)],
        )
        # Assert
        payload = json.loads(result.output)
        assert payload["count"] == 1

    def test_list_prefix_excludes_non_matching(self, runner, isolated_db, tmp_path):
        # Arrange
        dir_a = tmp_path / "proj_a"
        dir_b = tmp_path / "proj_b"
        dir_a.mkdir()
        dir_b.mkdir()
        _add_claim(runner, str(dir_a / "paper.tex"), line_number=1)
        _add_claim(runner, str(dir_b / "paper.tex"), line_number=1)
        # Act
        result = runner.invoke(
            main,
            ["--json", "claim", "list", "--file-path-prefix", str(dir_a)],
        )
        # Assert
        payload = json.loads(result.output)
        dir_b_str = str(dir_b.resolve())
        assert not any(dir_b_str in c["file_path"] for c in payload["claims"])


# EOF
