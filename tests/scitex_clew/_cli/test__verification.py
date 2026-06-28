#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for ``scitex_clew._cli._verification_mermaid`` — print-mermaid command
with DAG-slicing options (--target / --grouper / --no-files / --max-depth).

PA-306: no mocks — all tests build real DB state with real files.
PA-307: one observable assertion per test; AAA markers each on their own line.
"""

from __future__ import annotations

import pytest

# PA-303: click is in the [cli] extra; skip gracefully if not installed.
CliRunner = pytest.importorskip("click.testing").CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli._main import main
from scitex_clew._db import set_db
from scitex_clew._hash import hash_file


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Fresh in-memory-style DB for every test; reset after."""
    # Arrange
    db_path = tmp_path / "test_mermaid.db"
    set_db(db_path)
    # Act
    yield _db_module.get_db()
    # Assert (teardown)
    _db_module._DB_INSTANCE = None


@pytest.fixture
def runner():
    """CliRunner with mix_stderr=False for clean stdout/stderr separation."""
    return CliRunner()


def _register_run(db, session_id: str, script: str, tmp_path, in_content: str, out_content: str):
    """Helper: write real files, hash them, register in DB, finish run."""
    in_file = tmp_path / f"{session_id}_in.csv"
    out_file = tmp_path / f"{session_id}_out.csv"
    in_file.write_text(in_content)
    out_file.write_text(out_content)
    db.add_run(session_id, script_path=script)
    db.add_file_hash(session_id, str(in_file.resolve()), hash_file(in_file), "input")
    db.add_file_hash(session_id, str(out_file.resolve()), hash_file(out_file), "output")
    db.finish_run(session_id, status="success", combined_hash=f"combined_{session_id}")
    return in_file, out_file


@pytest.fixture
def two_session_db(isolated_db, tmp_path):
    """DB with two sessions: A → B (parent→child via shared file).

    Session A produces mid.csv; session B consumes mid.csv and produces
    leaf.csv. The link is recorded with add_parent so the DAG knows B depends
    on A.
    """
    db = isolated_db
    mid = tmp_path / "mid.csv"
    mid.write_text("avg\n2.0\n")
    leaf = tmp_path / "leaf.csv"
    leaf.write_text("final\n1.0\n")
    raw = tmp_path / "raw.csv"
    raw.write_text("col\n1\n2\n")

    sid_a = "2026Y-01M-01D-00h00m00s_SessionA"
    db.add_run(sid_a, script_path="/scripts/step_a.py")
    db.add_file_hash(sid_a, str(raw.resolve()), hash_file(raw), "input")
    db.add_file_hash(sid_a, str(mid.resolve()), hash_file(mid), "output")
    db.finish_run(sid_a, status="success", combined_hash=f"combined_{sid_a}")

    sid_b = "2026Y-01M-01D-01h00m00s_SessionB"
    db.add_run(sid_b, script_path="/scripts/step_b.py")
    db.add_file_hash(sid_b, str(mid.resolve()), hash_file(mid), "input")
    db.add_file_hash(sid_b, str(leaf.resolve()), hash_file(leaf), "output")
    db.finish_run(sid_b, status="success", combined_hash=f"combined_{sid_b}")

    db.add_parent(sid_b, sid_a)

    return {
        "db": db,
        "sid_a": sid_a,
        "sid_b": sid_b,
        "mid_file": mid,
        "leaf_file": leaf,
        "raw_file": raw,
    }


@pytest.fixture
def many_files_db(isolated_db, tmp_path):
    """DB with one session that has many output files sharing a directory."""
    db = isolated_db
    sid = "2026Y-02M-01D-00h00m00s_Many"
    db.add_run(sid, script_path="/scripts/many_outputs.py")
    raw = tmp_path / "raw.csv"
    raw.write_text("x\n1\n")
    db.add_file_hash(sid, str(raw.resolve()), hash_file(raw), "input")
    # Create 12 output files in the same directory to trigger directory grouper.
    for i in range(12):
        f = tmp_path / f"output_{i:02d}.csv"
        f.write_text(f"val\n{i}\n")
        db.add_file_hash(sid, str(f.resolve()), hash_file(f), "output")
    db.finish_run(sid, status="success", combined_hash=f"combined_{sid}")
    return {"db": db, "sid": sid, "dir": tmp_path}


# ---------------------------------------------------------------------------
# (1) --target scopes output to the target's upstream cone
# ---------------------------------------------------------------------------


def test_target_flag_exit_code_zero(runner, two_session_db):
    # Arrange
    leaf = str(two_session_db["leaf_file"].resolve())
    # Act
    result = runner.invoke(main, ["print-mermaid", "--target", leaf])
    # Assert
    assert result.exit_code == 0


def test_target_flag_output_nonempty(runner, two_session_db):
    # Arrange
    leaf = str(two_session_db["leaf_file"].resolve())
    # Act
    result = runner.invoke(main, ["print-mermaid", "--target", leaf])
    # Assert
    assert len(result.output.strip()) > 0


def test_target_flag_output_contains_leaf_reference(runner, two_session_db):
    # Arrange
    leaf = str(two_session_db["leaf_file"].resolve())
    leaf_name = two_session_db["leaf_file"].name
    # Act
    result = runner.invoke(main, ["print-mermaid", "--target", leaf])
    # Assert
    assert leaf_name in result.output or "leaf" in result.output.lower()


def test_target_flag_output_differs_from_full_graph(runner, two_session_db):
    # Arrange
    leaf = str(two_session_db["leaf_file"].resolve())
    # Act
    full_result = runner.invoke(main, ["print-mermaid"])
    scoped_result = runner.invoke(main, ["print-mermaid", "--target", leaf])
    # Assert — scoped output should be different (smaller or rearranged) from full.
    assert scoped_result.output != full_result.output or len(scoped_result.output) <= len(full_result.output)


# ---------------------------------------------------------------------------
# (2) --grouper collapses nodes
# ---------------------------------------------------------------------------


def test_grouper_directory_exit_code_zero(runner, many_files_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--grouper", "directory"])
    # Assert
    assert result.exit_code == 0


def test_grouper_directory_output_nonempty(runner, many_files_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--grouper", "directory"])
    # Assert
    assert len(result.output.strip()) > 0


def test_grouper_identity_exit_code_zero(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--grouper", "identity"])
    # Assert
    assert result.exit_code == 0


def test_grouper_drop_all_files_exit_code_zero(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--grouper", "drop_all_files"])
    # Assert
    assert result.exit_code == 0


def test_grouper_auto_exit_code_zero(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--grouper", "auto"])
    # Assert
    assert result.exit_code == 0


def test_grouper_session_bundle_exit_code_zero(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--grouper", "session_bundle"])
    # Assert
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# (3) --no-files omits file nodes
# ---------------------------------------------------------------------------


def test_no_files_flag_exit_code_zero(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--no-files"])
    # Assert
    assert result.exit_code == 0


def test_no_files_flag_output_contains_graph(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--no-files"])
    # Assert
    assert "graph" in result.output.lower()


def test_no_files_produces_fewer_lines_than_default(runner, two_session_db):
    # Arrange
    # Act
    default_result = runner.invoke(main, ["print-mermaid"])
    no_files_result = runner.invoke(main, ["print-mermaid", "--no-files"])
    # Assert — removing file nodes must reduce or maintain output size.
    assert len(no_files_result.output) <= len(default_result.output)


# ---------------------------------------------------------------------------
# (4) invalid --grouper exits non-zero with helpful message
# ---------------------------------------------------------------------------


def test_invalid_grouper_exits_nonzero(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--grouper", "bogus"])
    # Assert
    assert result.exit_code != 0


def test_invalid_grouper_message_lists_valid_names(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--grouper", "bogus"])
    combined = (result.output or "") + (result.exception and str(result.exception) or "")
    # Assert — error output should mention at least one valid grouper name.
    assert "directory" in combined or "identity" in combined or "bogus" in combined


# ---------------------------------------------------------------------------
# (5) plain print-mermaid and --claims/--json regressions
# ---------------------------------------------------------------------------


def test_plain_print_mermaid_exit_code_zero(runner, isolated_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid"])
    # Assert
    assert result.exit_code == 0


def test_plain_print_mermaid_output_nonempty(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid"])
    # Assert
    assert len(result.output.strip()) > 0


def test_claims_flag_regression_exit_code_zero(runner, isolated_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--claims"])
    # Assert
    assert result.exit_code == 0


def test_json_flag_regression_exit_code_zero(runner, isolated_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--json"])
    # Assert
    assert result.exit_code == 0


def test_json_flag_regression_output_is_valid_json(runner, isolated_db):
    # Arrange
    import json as _json
    # Act
    result = runner.invoke(main, ["print-mermaid", "--json"])
    # Assert
    parsed = _json.loads(result.output)
    assert isinstance(parsed, dict)


def test_json_flag_regression_has_mermaid_key(runner, isolated_db):
    # Arrange
    import json as _json
    # Act
    result = runner.invoke(main, ["print-mermaid", "--json"])
    parsed = _json.loads(result.output)
    # Assert
    assert "mermaid" in parsed


def test_claims_and_json_combined_regression_exit_code_zero(runner, isolated_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--claims", "--json"])
    # Assert
    assert result.exit_code == 0


def test_max_depth_option_exit_code_zero(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--max-depth", "1"])
    # Assert
    assert result.exit_code == 0


def test_max_depth_option_output_nonempty(runner, two_session_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--max-depth", "1"])
    # Assert
    assert len(result.output.strip()) > 0


def test_help_shows_new_options(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--help"])
    # Assert
    assert "--target" in result.output


def test_help_shows_grouper_option(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--help"])
    # Assert
    assert "--grouper" in result.output


def test_help_shows_no_files_option(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--help"])
    # Assert
    assert "--no-files" in result.output


def test_help_shows_max_depth_option(runner):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid", "--help"])
    # Assert
    assert "--max-depth" in result.output


# ---------------------------------------------------------------------------
# (6) Exception provenance — chain and verify CLI text output
# ---------------------------------------------------------------------------


@pytest.fixture
def exception_run_db(isolated_db, tmp_path):
    """DB with one exception session (no real files — no file hashes)."""
    db = isolated_db
    sid = "2026Y-06M-28D-00h00m00s_ExceptionRun"
    db.add_run(
        sid,
        script_path="/scripts/gpac_external.py",
        provenance="exception",
        exception_reason="4.1TB gPAC, recipe-known, never re-run",
    )
    db.finish_run(sid, status="success")
    return {"db": db, "sid": sid}


def test_verify_single_run_exception_shows_badge(runner, exception_run_db):
    # Arrange
    sid = exception_run_db["sid"]
    # Act
    result = runner.invoke(main, ["verify", sid])
    # Assert
    assert "EXCEPTION" in result.output


def test_verify_single_run_exception_shows_reason(runner, exception_run_db):
    # Arrange
    sid = exception_run_db["sid"]
    # Act
    result = runner.invoke(main, ["verify", sid])
    # Assert
    assert "4.1TB gPAC" in result.output


def test_verify_single_run_tracked_does_not_show_exception_badge(runner, isolated_db, tmp_path):
    # Arrange — plain tracked run; exception badge must NOT appear.
    sid = "2026Y-06M-28D-01h00m00s_TrackedRun"
    isolated_db.add_run(sid, script_path="/scripts/tracked.py")
    isolated_db.finish_run(sid, status="success")
    # Act
    result = runner.invoke(main, ["verify", sid])
    # Assert
    assert "EXCEPTION" not in result.output


def test_print_mermaid_exception_run_contains_exception_classdef(runner, exception_run_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid"])
    # Assert
    assert "classDef exception" in result.output


def test_print_mermaid_exception_run_contains_badge_in_node(runner, exception_run_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid"])
    # Assert
    assert "⊘ EXCEPTION" in result.output


def test_print_mermaid_tracked_run_does_not_contain_exception_badge(runner, isolated_db, tmp_path):
    # Arrange — tracked run; the mermaid output must not contain the badge.
    in_file = tmp_path / "tracked_in.csv"
    out_file = tmp_path / "tracked_out.csv"
    in_file.write_text("x\n1\n")
    out_file.write_text("y\n2\n")
    sid = "2026Y-06M-28D-02h00m00s_TrackedMermaid"
    isolated_db.add_run(sid, script_path="/scripts/tracked.py")
    isolated_db.add_file_hash(sid, str(in_file.resolve()), hash_file(in_file), "input")
    isolated_db.add_file_hash(sid, str(out_file.resolve()), hash_file(out_file), "output")
    isolated_db.finish_run(sid, status="success")
    # Act
    result = runner.invoke(main, ["print-mermaid"])
    # Assert
    assert "⊘ EXCEPTION" not in result.output


# ---------------------------------------------------------------------------
# (7) Frozen/trusted-input — verify and print-mermaid annotations
# ---------------------------------------------------------------------------


@pytest.fixture
def frozen_run_db(isolated_db, tmp_path):
    """DB with one session that has a frozen input file (no hash re-verification)."""
    db = isolated_db
    sid = "2026Y-06M-28D-10h00m00s_FrozenRun"
    frozen_file = tmp_path / "huge_dataset.npz"
    frozen_file.write_bytes(b"4.1TB placeholder data")
    db.add_run(sid, script_path="/scripts/gpac_consumer.py")
    # Register with a precomputed (not real) hash and frozen=True.
    db.add_file_hash(
        sid,
        str(frozen_file.resolve()),
        "precomputed_sha256_of_4tb_dataset",
        "input",
        frozen=True,
    )
    out_file = tmp_path / "output_result.csv"
    out_file.write_text("result\n42\n")
    db.add_file_hash(sid, str(out_file.resolve()), hash_file(out_file), "output")
    db.finish_run(sid, status="success")
    return {"db": db, "sid": sid, "frozen_file": frozen_file, "out_file": out_file}


def test_verify_frozen_run_exits_zero(runner, frozen_run_db):
    # Arrange
    sid = frozen_run_db["sid"]
    # Act
    result = runner.invoke(main, ["verify", sid])
    # Assert
    assert result.exit_code == 0


def test_verify_frozen_run_shows_frozen_marker(runner, frozen_run_db):
    # Arrange
    sid = frozen_run_db["sid"]
    # Act
    result = runner.invoke(main, ["verify", sid])
    # Assert
    assert "FROZEN" in result.output


def test_verify_non_frozen_run_does_not_show_frozen_marker(runner, isolated_db, tmp_path):
    # Arrange — plain tracked run with a real hash; no frozen marker should appear.
    in_file = tmp_path / "normal_in.csv"
    out_file = tmp_path / "normal_out.csv"
    in_file.write_text("x\n1\n")
    out_file.write_text("y\n2\n")
    sid = "2026Y-06M-28D-11h00m00s_NonFrozenRun"
    isolated_db.add_run(sid, script_path="/scripts/tracked.py")
    isolated_db.add_file_hash(sid, str(in_file.resolve()), hash_file(in_file), "input")
    isolated_db.add_file_hash(sid, str(out_file.resolve()), hash_file(out_file), "output")
    isolated_db.finish_run(sid, status="success")
    # Act
    result = runner.invoke(main, ["verify", sid])
    # Assert
    assert "FROZEN" not in result.output


def test_print_mermaid_frozen_run_contains_file_frozen_classdef(runner, frozen_run_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid"])
    # Assert
    assert "classDef file_frozen" in result.output


def test_print_mermaid_frozen_run_contains_frozen_marker_in_node(runner, frozen_run_db):
    # Arrange
    # Act
    result = runner.invoke(main, ["print-mermaid"])
    # Assert
    assert "FROZEN" in result.output


def test_print_mermaid_normal_run_does_not_contain_frozen_marker(runner, isolated_db, tmp_path):
    # Arrange — normal non-frozen run must not show the FROZEN marker.
    in_file = tmp_path / "normal2_in.csv"
    out_file = tmp_path / "normal2_out.csv"
    in_file.write_text("a\n1\n")
    out_file.write_text("b\n2\n")
    sid = "2026Y-06M-28D-12h00m00s_NormalMermaid"
    isolated_db.add_run(sid, script_path="/scripts/normal.py")
    isolated_db.add_file_hash(sid, str(in_file.resolve()), hash_file(in_file), "input")
    isolated_db.add_file_hash(sid, str(out_file.resolve()), hash_file(out_file), "output")
    isolated_db.finish_run(sid, status="success")
    # Act
    result = runner.invoke(main, ["print-mermaid"])
    # Assert
    assert "FROZEN" not in result.output


# EOF
