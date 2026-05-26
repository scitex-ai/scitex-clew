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

# PA-303: click is in the [cli] extra (not [project] deps).
CliRunner = pytest.importorskip("click.testing").CliRunner

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
    def test_add_minimal_succeeds_result_exit_code_equals_n_0(self, runner, isolated_db, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        # Act
        # Act
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
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_add_minimal_succeeds_claim_in_result_output(self, runner, isolated_db, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        # Act
        # Act
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
        # Act
        # Assert
        # Assert
        # Assert
        assert "claim_" in result.output  # human or json both contain claim_<hash>


    def test_add_json_returns_dict_result_exit_code_equals_n_0(self, runner, isolated_db, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        # Act
        # Act
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
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_add_json_returns_dict_parsed_claim_type_statistic_result_exit_code_equals_n_0(self, runner, isolated_db, tmp_path):
        # Arrange
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        # Act
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
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_add_json_returns_dict_parsed_claim_type_statistic_parsed_claim_type_statistic(self, runner, isolated_db, tmp_path):
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        # Act
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
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed.get("claim_type") == "statistic", result.output


    def test_add_json_returns_dict_parsed_claim_id_startswith_claim_result_exit_code_equals_n_0(self, runner, isolated_db, tmp_path):
        # Arrange
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        # Act
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
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_add_json_returns_dict_parsed_claim_id_startswith_claim_parsed_claim_id_startswith_claim(self, runner, isolated_db, tmp_path):
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        # Act
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
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed.get("claim_id", "").startswith("claim_"), result.output



    def test_add_invalid_type_fails(self, runner, isolated_db, tmp_path):
        # Arrange
        # Arrange
        manuscript = tmp_path / "paper.tex"
        manuscript.write_text("dummy")
        # Click rejects values not in the Choice — exit code != 0.
        # Act
        # Act
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
        # Assert
        # Assert
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
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["claim", "list"])
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_json_empty_db_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "claim", "list"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_json_empty_db_parsed_count_0_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "claim", "list"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_json_empty_db_parsed_count_0_parsed_count_0(self, runner, isolated_db):
        # Arrange
        result = runner.invoke(main, ["--json", "claim", "list"])
        # Act
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed.get("count") == 0, result.output


    def test_list_json_empty_db_parsed_claims_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "claim", "list"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_json_empty_db_parsed_claims_parsed_claims(self, runner, isolated_db):
        # Arrange
        result = runner.invoke(main, ["--json", "claim", "list"])
        # Act
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed.get("claims") == [], result.output



    def test_list_after_add_result_exit_code_equals_n_0(self, runner, isolated_db, tmp_path):
        # Arrange
        # Arrange
        # Arrange
        self._seed(runner, tmp_path)
        # Act
        # Act
        result = runner.invoke(main, ["--json", "claim", "list"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_after_add_parsed_count_1_result_exit_code_equals_n_0(self, runner, isolated_db, tmp_path):
        # Arrange
        # Arrange
        self._seed(runner, tmp_path)
        # Act
        result = runner.invoke(main, ["--json", "claim", "list"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_after_add_parsed_count_1_parsed_count_1(self, runner, isolated_db, tmp_path):
        # Arrange
        self._seed(runner, tmp_path)
        # Act
        result = runner.invoke(main, ["--json", "claim", "list"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed.get("count") == 1, result.output




# ---------------------------------------------------------------------------
# clew claim verify
# ---------------------------------------------------------------------------


class TestClaimVerify:
    def test_verify_nonexistent_exits_nonzero(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["claim", "verify", "claim_doesnotexist"])
        # Assert
        # Assert
        assert result.exit_code != 0

    def test_verify_nonexistent_json_payload(self, runner, isolated_db):
        # Arrange
        # Arrange
        result = runner.invoke(
            main, ["--json", "claim", "verify", "claim_doesnotexist"]
        )
        # exit_code != 0 but JSON should still be on stdout
        # Act
        # Act
        parsed = json.loads(result.output)
        # Assert
        # Assert
        assert parsed["status"] == "not_found"


# ---------------------------------------------------------------------------
# clew hash-file
# ---------------------------------------------------------------------------


class TestHashFile:
    def test_hash_existing_file_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["hash-file", str(sample_files["src"])])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_existing_file_len_result_output_strip_32_5(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["hash-file", str(sample_files["src"])])
        # Act
        # Assert
        # Assert
        # Assert
        assert len(result.output.strip()) >= 32 - 5  # 32 chars truncated


    def test_hash_existing_file_json_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "hash-file", str(sample_files["src"])])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_existing_file_json_parsed_path_str_sample_files_src_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "hash-file", str(sample_files["src"])])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_existing_file_json_parsed_path_str_sample_files_src_parsed_path_str_sample_files_src(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "hash-file", str(sample_files["src"])])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed["path"] == str(sample_files["src"])


    def test_hash_existing_file_json_parsed_algorithm_sha256_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "hash-file", str(sample_files["src"])])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_existing_file_json_parsed_algorithm_sha256_parsed_algorithm_sha256(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "hash-file", str(sample_files["src"])])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed["algorithm"] == "sha256"


    def test_hash_existing_file_json_isinstance_parsed_hash_str_and_len_parsed_hash_0_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "hash-file", str(sample_files["src"])])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_existing_file_json_isinstance_parsed_hash_str_and_len_parsed_hash_0_isinstance_parsed_hash_str_and_len_parsed_hash_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "hash-file", str(sample_files["src"])])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert isinstance(parsed["hash"], str) and len(parsed["hash"]) > 0



    def test_hash_missing_file_fails(self, runner, tmp_path):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["hash-file", str(tmp_path / "nope.csv")])
        # Assert
        # Assert
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# clew hash-directory
# ---------------------------------------------------------------------------


class TestHashDirectory:
    def test_hash_dir_basic_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["hash-directory", str(sample_files["dir"])])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_dir_basic_x_txt_in_result_output_or_src_csv_in_result_output(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["hash-directory", str(sample_files["dir"])])
        # Act
        # Assert
        # Assert
        # Assert
        assert "x.txt" in result.output or "src.csv" in result.output


    def test_hash_dir_json_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(
            main, ["--json", "hash-directory", str(sample_files["dir"])]
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_dir_json_parsed_path_str_sample_files_dir_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(
            main, ["--json", "hash-directory", str(sample_files["dir"])]
        )
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_dir_json_parsed_path_str_sample_files_dir_parsed_path_str_sample_files_dir(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(
            main, ["--json", "hash-directory", str(sample_files["dir"])]
        )
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed["path"] == str(sample_files["dir"])


    def test_hash_dir_json_isinstance_parsed_hashes_dict_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(
            main, ["--json", "hash-directory", str(sample_files["dir"])]
        )
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_dir_json_isinstance_parsed_hashes_dict_isinstance_parsed_hashes_dict(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(
            main, ["--json", "hash-directory", str(sample_files["dir"])]
        )
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert isinstance(parsed["hashes"], dict)


    def test_hash_dir_json_len_parsed_hashes_3_result_exit_code_equals_n_0(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(
            main, ["--json", "hash-directory", str(sample_files["dir"])]
        )
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_hash_dir_json_len_parsed_hashes_3_len_parsed_hashes_3(self, runner, sample_files):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(
            main, ["--json", "hash-directory", str(sample_files["dir"])]
        )
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert len(parsed["hashes"]) >= 3  # src.csv, sub/x.txt, sub/y.txt



    def test_hash_dir_missing_path_fails(self, runner, tmp_path):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["hash-directory", str(tmp_path / "no-such-dir")])
        # Assert
        # Assert
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# clew stamp / list-stamps / check-stamp
# ---------------------------------------------------------------------------


class TestStampGroup:
    def test_stamp_with_no_runs_fails(self, runner, isolated_db):
        # File backend with no successful runs should raise ValueError → exit 1.
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["stamp", "--backend", "file"])
        # Assert
        # Assert
        assert result.exit_code != 0

    def test_list_stamps_empty_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-stamps"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_stamps_empty_no_stamps_recorded_in_result_output_or_result_output_strip(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["list-stamps"])
        # Act
        # Assert
        # Assert
        # Assert
        assert "No stamps recorded." in result.output or result.output.strip() == ""


    def test_list_stamps_json_empty_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "list-stamps"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_stamps_json_empty_parsed_count_0_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "list-stamps"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_stamps_json_empty_parsed_count_0_parsed_count_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "list-stamps"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed["count"] == 0


    def test_list_stamps_json_empty_parsed_stamps_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "list-stamps"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_stamps_json_empty_parsed_stamps_parsed_stamps(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "list-stamps"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert parsed["stamps"] == []



    def test_check_stamp_no_stamps_fails(self, runner, isolated_db):
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["check-stamp"])
        # Assert
        # Assert
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# F5 — universal --json on existing commands
# ---------------------------------------------------------------------------


class TestUniversalJsonFlag:
    """Every CLI command must accept --json (top-level or sub-level)."""

    def test_status_top_level_json_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "status"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_status_top_level_json_verified_count_in_parsed_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "status"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_status_top_level_json_verified_count_in_parsed_verified_count_in_parsed(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "status"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert "verified_count" in parsed



    def test_list_top_level_json_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "list-runs"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_top_level_json_count_in_parsed_and_runs_in_parsed_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "list-runs"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_list_top_level_json_count_in_parsed_and_runs_in_parsed_count_in_parsed_and_runs_in_parsed(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "list-runs"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert "count" in parsed and "runs" in parsed



    def test_stats_top_level_json_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "show-stats"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_stats_top_level_json_total_runs_in_parsed_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "show-stats"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_stats_top_level_json_total_runs_in_parsed_total_runs_in_parsed(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "show-stats"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert "total_runs" in parsed



    def test_mermaid_top_level_json_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "print-mermaid"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_mermaid_top_level_json_mermaid_in_parsed_result_exit_code_equals_n_0(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "print-mermaid"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_mermaid_top_level_json_mermaid_in_parsed_mermaid_in_parsed(self, runner, isolated_db):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "print-mermaid"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert "mermaid" in parsed



    def test_status_sub_level_json(self, runner, isolated_db):
        # Sub-level --json must work too.
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["status", "--json"])
        # Assert
        # Assert
        assert result.exit_code == 0
        json.loads(result.output)  # must parse

    def test_dag_top_level_json_no_targets_result_exit_code_equals_n_0(self, runner, isolated_db):
        # dag with empty targets should still succeed and produce JSON.
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "dag", "--claims"])
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_dag_top_level_json_no_targets_status_in_parsed_result_exit_code_equals_n_0(self, runner, isolated_db):
        # dag with empty targets should still succeed and produce JSON.
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "dag", "--claims"])
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0

    def test_dag_top_level_json_no_targets_status_in_parsed_status_in_parsed(self, runner, isolated_db):
        # dag with empty targets should still succeed and produce JSON.
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(main, ["--json", "dag", "--claims"])
        parsed = json.loads(result.output) if result.exit_code == 0 else {}
        # Assert
        assert "status" in parsed




# EOF
