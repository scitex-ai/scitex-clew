#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F1+F5 — CLI tests for claim/hash/stamp + universal --json.

Strategy
--------
- Use ``click.testing.CliRunner`` to drive every subcommand in-process.
- Inject an isolated temp DB via ``set_db()`` so claims/stamps don't leak.
- Cover happy path + at least one error path per command.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli._main import main
from scitex_clew._db import set_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    db_path = tmp_path / "f1_cli.db"
    set_db(db_path)
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def sample_files(tmp_path):
    """A few real files for hash-file / hash-directory tests."""
    src = tmp_path / "src.csv"
    src.write_text("a,b\n1,2\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "x.txt").write_text("hello")
    (sub / "y.txt").write_text("world")
    return {"src": src, "dir": tmp_path, "subdir": sub}


# ---------------------------------------------------------------------------
# clew claim add
# ---------------------------------------------------------------------------


class TestClaimAdd:
    def test_add_minimal_succeeds(self, runner, isolated_db, tmp_path):
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        result = runner.invoke(
            main,
            [
                "claim",
                "add",
                "--file-path",
                str(manuscript),
                "--type",
                "statistic",
                "--value",
                "p = 0.003",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "claim_" in result.output  # human or json both contain claim_<hash>

    def test_add_json_returns_dict(self, runner, isolated_db, tmp_path):
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        result = runner.invoke(
            main,
            [
                "--json",
                "claim",
                "add",
                "--file-path",
                str(manuscript),
                "--type",
                "statistic",
                "--value",
                "p<0.05",
            ],
        )
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert parsed["claim_type"] == "statistic"
        assert parsed["claim_id"].startswith("claim_")

    def test_add_invalid_type_fails(self, runner, isolated_db, tmp_path):
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        # Click rejects values not in the Choice — exit code != 0.
        result = runner.invoke(
            main,
            [
                "claim",
                "add",
                "--file-path",
                str(manuscript),
                "--type",
                "bogus",
            ],
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# clew claim list
# ---------------------------------------------------------------------------


class TestClaimList:
    def _seed(self, runner, tmp_path):
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("x")
        runner.invoke(
            main,
            [
                "claim",
                "add",
                "--file-path",
                str(manuscript),
                "--type",
                "statistic",
                "--line-number",
                "10",
                "--value",
                "p=0.01",
            ],
        )
        return manuscript

    def test_list_empty_db_succeeds(self, runner, isolated_db):
        result = runner.invoke(main, ["claim", "list"])
        assert result.exit_code == 0

    def test_list_json_empty_db(self, runner, isolated_db):
        result = runner.invoke(main, ["--json", "claim", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["count"] == 0
        assert parsed["claims"] == []

    def test_list_after_add(self, runner, isolated_db, tmp_path):
        self._seed(runner, tmp_path)
        result = runner.invoke(main, ["--json", "claim", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["count"] == 1


# ---------------------------------------------------------------------------
# clew claim verify
# ---------------------------------------------------------------------------


class TestClaimVerify:
    def test_verify_nonexistent_exits_nonzero(self, runner, isolated_db):
        result = runner.invoke(main, ["claim", "verify", "claim_doesnotexist"])
        assert result.exit_code != 0

    def test_verify_nonexistent_json_payload(self, runner, isolated_db):
        result = runner.invoke(
            main, ["--json", "claim", "verify", "claim_doesnotexist"]
        )
        # exit_code != 0 but JSON should still be on stdout
        parsed = json.loads(result.output)
        assert parsed["status"] == "not_found"


# ---------------------------------------------------------------------------
# clew hash-file
# ---------------------------------------------------------------------------


class TestHashFile:
    def test_hash_existing_file(self, runner, sample_files):
        result = runner.invoke(main, ["hash-file", str(sample_files["src"])])
        assert result.exit_code == 0
        # Default human output is the bare hex digest
        assert len(result.output.strip()) >= 32 - 5  # 32 chars truncated

    def test_hash_existing_file_json(self, runner, sample_files):
        result = runner.invoke(main, ["--json", "hash-file", str(sample_files["src"])])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["path"] == str(sample_files["src"])
        assert parsed["algorithm"] == "sha256"
        assert isinstance(parsed["hash"], str) and len(parsed["hash"]) > 0

    def test_hash_missing_file_fails(self, runner, tmp_path):
        result = runner.invoke(main, ["hash-file", str(tmp_path / "nope.csv")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# clew hash-directory
# ---------------------------------------------------------------------------


class TestHashDirectory:
    def test_hash_dir_basic(self, runner, sample_files):
        result = runner.invoke(main, ["hash-directory", str(sample_files["dir"])])
        assert result.exit_code == 0
        # output should contain at least one of our seeded files
        assert "x.txt" in result.output or "src.csv" in result.output

    def test_hash_dir_json(self, runner, sample_files):
        result = runner.invoke(
            main, ["--json", "hash-directory", str(sample_files["dir"])]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["path"] == str(sample_files["dir"])
        assert isinstance(parsed["hashes"], dict)
        assert len(parsed["hashes"]) >= 3  # src.csv, sub/x.txt, sub/y.txt

    def test_hash_dir_missing_path_fails(self, runner, tmp_path):
        result = runner.invoke(main, ["hash-directory", str(tmp_path / "no-such-dir")])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# clew stamp / list-stamps / check-stamp
# ---------------------------------------------------------------------------


class TestStampGroup:
    def test_stamp_with_no_runs_fails(self, runner, isolated_db):
        # File backend with no successful runs should raise ValueError → exit 1.
        result = runner.invoke(main, ["stamp", "--backend", "file"])
        assert result.exit_code != 0

    def test_list_stamps_empty(self, runner, isolated_db):
        result = runner.invoke(main, ["list-stamps"])
        assert result.exit_code == 0
        assert "No stamps recorded." in result.output or result.output.strip() == ""

    def test_list_stamps_json_empty(self, runner, isolated_db):
        result = runner.invoke(main, ["--json", "list-stamps"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["count"] == 0
        assert parsed["stamps"] == []

    def test_check_stamp_no_stamps_fails(self, runner, isolated_db):
        result = runner.invoke(main, ["check-stamp"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# F5 — universal --json on existing commands
# ---------------------------------------------------------------------------


class TestUniversalJsonFlag:
    """Every CLI command must accept --json (top-level or sub-level)."""

    def test_status_top_level_json(self, runner, isolated_db):
        result = runner.invoke(main, ["--json", "status"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "verified_count" in parsed

    def test_list_top_level_json(self, runner, isolated_db):
        result = runner.invoke(main, ["--json", "list"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "count" in parsed and "runs" in parsed

    def test_stats_top_level_json(self, runner, isolated_db):
        result = runner.invoke(main, ["--json", "stats"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "total_runs" in parsed

    def test_mermaid_top_level_json(self, runner, isolated_db):
        result = runner.invoke(main, ["--json", "mermaid"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "mermaid" in parsed

    def test_status_sub_level_json(self, runner, isolated_db):
        # Sub-level --json must work too.
        result = runner.invoke(main, ["status", "--json"])
        assert result.exit_code == 0
        json.loads(result.output)  # must parse

    def test_dag_top_level_json_no_targets(self, runner, isolated_db):
        # dag with empty targets should still succeed and produce JSON.
        result = runner.invoke(main, ["--json", "dag", "--claims"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "status" in parsed


# EOF
