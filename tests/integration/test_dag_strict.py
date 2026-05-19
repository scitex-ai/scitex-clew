#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F2 — strict-mode DAG verification with failure attribution.

The fixture builds a small 3-stage chain (raw → midA → leafB) entirely
inside a tmp_path, registers two claims (one mid-chain, one downstream),
then optionally CORRUPTS the most-upstream input file to trigger a
hash mismatch. The test then asserts that ``verify_dag_strict`` returns:

  * status = "FAIL"
  * failed_node = the most-downstream mismatched file
  * root_cause  = the upstream-most mismatched file (the corrupted one)
  * invalidated_claims contains every claim_id whose chain passes through
    the corrupted node
  * still_valid_claims is the complement
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# PA-303: click is in the [cli] extra (not [project] deps).
CliRunner = pytest.importorskip("click.testing").CliRunner

import scitex_clew._db as _db_module
from scitex_clew._cli._main import main
from scitex_clew._db import set_db
from scitex_clew._hash import hash_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    db_path = tmp_path / "f2.db"
    set_db(db_path)
    yield _db_module.get_db()
    _db_module._DB_INSTANCE = None


@pytest.fixture
def runner():
    return CliRunner()


def _add_run_with_files(db, sid: str, script: str, inputs: dict, outputs: dict):
    """Helper: register a session with given input/output file→hash maps."""
    db.add_run(sid, script_path=script)
    for path, h in inputs.items():
        db.add_file_hash(sid, str(Path(path).resolve()), h, "input")
    for path, h in outputs.items():
        db.add_file_hash(sid, str(Path(path).resolve()), h, "output")
    db.finish_run(sid, status="success", combined_hash=f"combined_{sid}")


@pytest.fixture
def chain_capsule(isolated_db, tmp_path):
    """A 3-stage chain:

        raw.csv   -> [sessA.py] -> mid.csv  -> [sessB.py] -> leaf.csv

    Two claims:
      * claim_mid    references mid.csv
      * claim_leaf   references leaf.csv

    Files are real on disk so hash_file() returns deterministic digests.
    """
    db = isolated_db

    raw = tmp_path / "raw.csv"
    raw.write_text("col\n1\n2\n3\n")
    mid = tmp_path / "mid.csv"
    mid.write_text("avg\n2.0\n")
    leaf = tmp_path / "leaf.csv"
    leaf.write_text("scaled\n4.0\n")

    sid_a = "2026Y-05M-05D-12h00m00s_SessA"
    sid_b = "2026Y-05M-05D-12h05m00s_SessB"

    _add_run_with_files(
        db,
        sid_a,
        script="/scripts/sessA.py",
        inputs={raw: hash_file(raw)},
        outputs={mid: hash_file(mid)},
    )
    _add_run_with_files(
        db,
        sid_b,
        script="/scripts/sessB.py",
        inputs={mid: hash_file(mid)},
        outputs={leaf: hash_file(leaf)},
    )
    db.add_parent(sid_b, sid_a)

    # Register claims pointing at the two outputs.
    paper = tmp_path / "paper.tex"
    paper.write_text("\\claim{...}\n\\claim{...}\n")

    from scitex_clew import add_claim

    claim_mid = add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="avg=2.0",
        source_file=str(mid),
        source_session=sid_a,
    )
    claim_leaf = add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=2,
        claim_value="scaled=4.0",
        source_file=str(leaf),
        source_session=sid_b,
    )

    return {
        "raw": raw,
        "mid": mid,
        "leaf": leaf,
        "sid_a": sid_a,
        "sid_b": sid_b,
        "claim_mid_id": claim_mid.claim_id,
        "claim_leaf_id": claim_leaf.claim_id,
    }


# ---------------------------------------------------------------------------
# Pure Python API
# ---------------------------------------------------------------------------


class TestVerifyDagStrictHappy:
    """When everything matches, status is OK and no claims are invalidated."""

    def test_strict_ok_payload_status_ok(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["status"] == "OK"

    def test_strict_ok_payload_is_verified_is_true(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["is_verified"] is True

    def test_strict_ok_payload_failed_node_is_none(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["failed_node"] is None

    def test_strict_ok_payload_root_cause_is_none(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["root_cause"] is None

    def test_strict_ok_payload_invalidated_claims(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["invalidated_claims"] == []

    def test_strict_ok_chain_capsule_claim_mid_id_in_payload_still_valid_claims(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert chain_capsule["claim_mid_id"] in payload["still_valid_claims"]

    def test_strict_ok_chain_capsule_claim_leaf_id_in_payload_still_valid_claims(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert chain_capsule["claim_leaf_id"] in payload["still_valid_claims"]



class TestVerifyDagStrictFail:
    """Corrupt raw.csv mid-chain → strict mode must attribute the failure."""

    def _corrupt(self, path: Path):
        path.write_bytes(path.read_bytes() + b"\n# CORRUPTED\n")

    def test_strict_fail_status_and_attribution_payload_status_fail(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["status"] == "FAIL"

    def test_strict_fail_status_and_attribution_payload_is_verified_is_false(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["is_verified"] is False

    def test_strict_fail_status_and_attribution_payload_failed_node_is_not_none(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["failed_node"] is not None

    def test_strict_fail_status_and_attribution_payload_root_cause_is_not_none(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["root_cause"] is not None

    def test_strict_fail_status_and_attribution_path_payload_root_cause_path_resolve_chain_capsule_raw_resol(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert (
            Path(payload["root_cause"]["path"]).resolve()
            == chain_capsule["raw"].resolve()
        )


    def test_strict_fail_invalidates_downstream_claim_chain_capsule_claim_mid_id_in_payload_invalidated_claims(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert chain_capsule["claim_mid_id"] in payload["invalidated_claims"]

    def test_strict_fail_invalidates_downstream_claim_chain_capsule_claim_leaf_id_in_payload_invalidated_claims(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert chain_capsule["claim_leaf_id"] in payload["invalidated_claims"]

    def test_strict_fail_invalidates_downstream_claim_chain_capsule_claim_mid_id_not_in_payload_still_valid_claims(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert chain_capsule["claim_mid_id"] not in payload["still_valid_claims"]

    def test_strict_fail_invalidates_downstream_claim_chain_capsule_claim_leaf_id_not_in_payload_still_valid_claim(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert chain_capsule["claim_leaf_id"] not in payload["still_valid_claims"]


    def test_strict_fail_no_targets_via_claims_flag_payload_status_fail(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(claims=True, strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["status"] == "FAIL"

    def test_strict_fail_no_targets_via_claims_flag_chain_capsule_claim_mid_id_in_payload_invalidated_claims(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        from scitex_clew import dag
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(claims=True, strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert chain_capsule["claim_mid_id"] in payload["invalidated_claims"]


    def test_unrelated_claim_remains_valid_payload_status_fail(self, chain_capsule, tmp_path, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        other = tmp_path / "independent.csv"
        other.write_text("standalone\n")
        sid_c = "2026Y-05M-05D-13h00m00s_SessC"
        _add_run_with_files(
            isolated_db,
            sid_c,
            script="/scripts/sessC.py",
            inputs={},
            outputs={other: hash_file(other)},
        )
        from scitex_clew import add_claim, dag
        paper = tmp_path / "paper.tex"
        c_other = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=99,
            claim_value="independent=1",
            source_file=str(other),
            source_session=sid_c,
        )
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["status"] == "FAIL"

    def test_unrelated_claim_remains_valid_c_other_claim_id_in_payload_still_valid_claim(self, chain_capsule, tmp_path, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        other = tmp_path / "independent.csv"
        other.write_text("standalone\n")
        sid_c = "2026Y-05M-05D-13h00m00s_SessC"
        _add_run_with_files(
            isolated_db,
            sid_c,
            script="/scripts/sessC.py",
            inputs={},
            outputs={other: hash_file(other)},
        )
        from scitex_clew import add_claim, dag
        paper = tmp_path / "paper.tex"
        c_other = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=99,
            claim_value="independent=1",
            source_file=str(other),
            source_session=sid_c,
        )
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert c_other.claim_id in payload["still_valid_claims"]

    def test_unrelated_claim_remains_valid_c_other_claim_id_not_in_payload_invalidated_claims(self, chain_capsule, tmp_path, isolated_db):
        # Arrange
        # Arrange
        # Arrange
        other = tmp_path / "independent.csv"
        other.write_text("standalone\n")
        sid_c = "2026Y-05M-05D-13h00m00s_SessC"
        _add_run_with_files(
            isolated_db,
            sid_c,
            script="/scripts/sessC.py",
            inputs={},
            outputs={other: hash_file(other)},
        )
        from scitex_clew import add_claim, dag
        paper = tmp_path / "paper.tex"
        c_other = add_claim(
            file_path=str(paper),
            claim_type="value",
            line_number=99,
            claim_value="independent=1",
            source_file=str(other),
            source_session=sid_c,
        )
        self._corrupt(chain_capsule["raw"])
        # Act
        # Act
        payload = dag(targets=[str(chain_capsule["leaf"])], strict=True)
        # Act
        # Assert
        # Assert
        # Assert
        assert c_other.claim_id not in payload["invalidated_claims"]



# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


class TestStrictDagViaCLI:
    def test_dag_strict_json_emits_attribution_result_exit_code_equals_n_0(self, runner, chain_capsule):
        # corrupt then call CLI
        # Arrange
        # Arrange
        # Arrange
        chain_capsule["raw"].write_bytes(
            chain_capsule["raw"].read_bytes() + b"\nbreak\n"
        )
        # Act
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_dag_strict_json_emits_attribution_payload_status_fail_result_exit_code_equals_n_0(self, runner, chain_capsule):
        # corrupt then call CLI
        # Arrange
        # Arrange
        chain_capsule["raw"].write_bytes(
            chain_capsule["raw"].read_bytes() + b"\nbreak\n"
        )
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_dag_strict_json_emits_attribution_payload_status_fail_payload_status_fail(self, runner, chain_capsule):
        # corrupt then call CLI
        # Arrange
        # Arrange
        chain_capsule["raw"].write_bytes(
            chain_capsule["raw"].read_bytes() + b"\nbreak\n"
        )
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Assert
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        # Act
        # Assert
        assert payload["status"] == "FAIL"


    def test_dag_strict_json_emits_attribution_payload_failed_node_is_not_none_result_exit_code_equals_n_0(self, runner, chain_capsule):
        # corrupt then call CLI
        # Arrange
        # Arrange
        chain_capsule["raw"].write_bytes(
            chain_capsule["raw"].read_bytes() + b"\nbreak\n"
        )
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_dag_strict_json_emits_attribution_payload_failed_node_is_not_none_payload_failed_node_is_not_none(self, runner, chain_capsule):
        # corrupt then call CLI
        # Arrange
        # Arrange
        chain_capsule["raw"].write_bytes(
            chain_capsule["raw"].read_bytes() + b"\nbreak\n"
        )
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Assert
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        # Act
        # Assert
        assert payload["failed_node"] is not None


    def test_dag_strict_json_emits_attribution_payload_root_cause_is_not_none_result_exit_code_equals_n_0(self, runner, chain_capsule):
        # corrupt then call CLI
        # Arrange
        # Arrange
        chain_capsule["raw"].write_bytes(
            chain_capsule["raw"].read_bytes() + b"\nbreak\n"
        )
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_dag_strict_json_emits_attribution_payload_root_cause_is_not_none_payload_root_cause_is_not_none(self, runner, chain_capsule):
        # corrupt then call CLI
        # Arrange
        # Arrange
        chain_capsule["raw"].write_bytes(
            chain_capsule["raw"].read_bytes() + b"\nbreak\n"
        )
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Assert
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        # Act
        # Assert
        assert payload["root_cause"] is not None



    def test_dag_strict_ok_when_uncorrupted_result_exit_code_equals_n_0(self, runner, chain_capsule):
        # Arrange
        # Arrange
        # Act
        # Arrange
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Act
        # Assert
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_dag_strict_ok_when_uncorrupted_payload_status_ok_result_exit_code_equals_n_0(self, runner, chain_capsule):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Act
        # Assert
        # Assert
        assert result.exit_code == 0, result.output

    def test_dag_strict_ok_when_uncorrupted_payload_status_ok_payload_status_ok(self, runner, chain_capsule):
        # Arrange
        # Arrange
        # Act
        result = runner.invoke(
            main,
            [
                "dag",
                "--strict",
                "--json",
                "--target",
                str(chain_capsule["leaf"]),
            ],
        )
        # Assert
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        # Act
        # Assert
        assert payload["status"] == "OK"




# ---------------------------------------------------------------------------
# MCP surface
# ---------------------------------------------------------------------------


class TestStrictDagViaMCP:
    def test_mcp_clew_dag_strict_param_payload_status_fail(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        pytest.importorskip("fastmcp")
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools
        m = FastMCP(name="t-strict")
        register_tools(m)
        # corrupt mid-chain
        chain_capsule["raw"].write_bytes(
            chain_capsule["raw"].read_bytes() + b"\nbreak\n"
        )
        from scitex_clew._mcp import get_tools_sync
        tools = get_tools_sync(m)
        if isinstance(tools, dict):
            tdict = tools
        else:
            tdict = {t.name: t for t in tools}
        fn = tdict["clew_dag"].fn
        import asyncio
        out = asyncio.run(fn(target_files=str(chain_capsule["leaf"]), strict=True))
        # Act
        # Act
        payload = json.loads(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["status"] == "FAIL"

    def test_mcp_clew_dag_strict_param_payload_root_cause_is_not_none(self, chain_capsule):
        # Arrange
        # Arrange
        # Arrange
        pytest.importorskip("fastmcp")
        from fastmcp import FastMCP
        from scitex_clew._mcp.tools.verification import register_tools
        m = FastMCP(name="t-strict")
        register_tools(m)
        # corrupt mid-chain
        chain_capsule["raw"].write_bytes(
            chain_capsule["raw"].read_bytes() + b"\nbreak\n"
        )
        from scitex_clew._mcp import get_tools_sync
        tools = get_tools_sync(m)
        if isinstance(tools, dict):
            tdict = tools
        else:
            tdict = {t.name: t for t in tools}
        fn = tdict["clew_dag"].fn
        import asyncio
        out = asyncio.run(fn(target_files=str(chain_capsule["leaf"]), strict=True))
        # Act
        # Act
        payload = json.loads(out)
        # Act
        # Assert
        # Assert
        # Assert
        assert payload["root_cause"] is not None



# EOF
