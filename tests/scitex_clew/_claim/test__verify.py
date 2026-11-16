#!/usr/bin/env python3
"""Claim verification: value-vs-source (:mod:`scitex_clew._claim._verify`).

``source_keys`` (scitex-writer's shape: RFC 6901 pointer / csv cell) +
tolerance (declared, else implied by the written precision): verification
compares the claimed value with the value read from the source. A lineage
walk that raises is never reported OK.

Real store, real files, no mocks. The chain-error fault is a genuinely
corrupted provenance record written straight into the store.
"""

from __future__ import annotations

import json
import os
import warnings

import pytest
import scitex_clew as clew
from scitex_clew._db import get_db
from scitex_clew._tracker import SessionTracker
from scitex_dev.store import ANY_REVISION


@pytest.fixture(autouse=True)
def _no_claims_export():
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    yield
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _produce(tmp_path, name, content, sid="S1"):
    script = tmp_path / "make.py"
    script.write_text("# make\n")
    out = tmp_path / name
    out.write_text(content)
    tracker = SessionTracker(sid, script_path=str(script))
    tracker.record_output(out)
    tracker.finalize()
    return out


def _claim(tmp_path, display, source, **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return clew.add_claim(
            str(tmp_path / "paper.tex"),
            "value",
            1,
            display,
            source_file=str(source),
            **kw,
        )


@pytest.fixture
def results_json(tmp_path):
    return _produce(
        tmp_path, "results.json", json.dumps({"test": {"auc": 0.8123, "n": 120}})
    )


@pytest.fixture
def table_csv(tmp_path):
    return _produce(
        tmp_path,
        "table.csv",
        "subject,metric,value\nS01,auc,0.91\nS02,auc,0.85\n",
        sid="S2",
    )




class TestValueCheck:
    def test_precision_implied_tolerance_passes(self, tmp_path, results_json):
        # Arrange — 0.81 written to 2 places -> ±0.005 covers 0.8123
        _claim(tmp_path, "0.81", results_json, source_keys={".": "/test/auc"})
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "OK"

    def test_value_outside_implied_tolerance_is_value_mismatch(
        self, tmp_path, results_json
    ):
        # Arrange
        _claim(tmp_path, "0.91", results_json, source_keys={".": "/test/auc"})
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert (result.exit_name, result.exit_code) == ("VALUE_MISMATCH", 21)

    def test_structured_value_fields_are_each_checked(self, tmp_path, results_json):
        # Arrange
        _claim(
            tmp_path,
            "AUC 0.81 (n=120)",
            results_json,
            value={"auc": 0.81, "n": 121},
            source_keys={"auc": {"pointer": "/test/auc"}, "n": "/test/n"},
            tolerance={"abs_tol": 0.01},
        )
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "VALUE_MISMATCH"

    def test_csv_row_selected_by_column_values(self, tmp_path, table_csv):
        # Arrange
        _claim(
            tmp_path,
            "0.91",
            table_csv,
            source_keys={".": {"row": {"subject": "S01"}, "column": "value"}},
        )
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "OK"

    def test_csv_row_index_mismatch(self, tmp_path, table_csv):
        # Arrange
        _claim(tmp_path, "0.91", table_csv, source_keys={".": {"row": 1, "column": 2}})
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "VALUE_MISMATCH"

    def test_unresolvable_pointer_is_verify_error(self, tmp_path, results_json):
        # Arrange
        _claim(tmp_path, "0.81", results_json, source_keys={".": "/test/nope"})
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "VERIFY_ERROR"



class TestChainErrorIsNeverOk:
    @staticmethod
    def _corrupt(path):
        get_db()._file_hashes.put(
            {
                "session_id": "S1",
                "file_path": str(path.resolve()),
                "role": "output",
                "derived_from": "{not json",
            },
            expected_revision=ANY_REVISION,
        )

    def test_corrupted_lineage_record_is_verify_error(self, tmp_path, results_json):
        # Arrange — a real corrupted provenance row: undecodable derived_from
        _claim(tmp_path, "x", results_json)
        self._corrupt(results_json)
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert (result.exit_name, result.verified) == ("VERIFY_ERROR", 0)

    def test_chain_error_is_reported_in_details(self, tmp_path, results_json):
        # Arrange
        claim = _claim(tmp_path, "x", results_json)
        self._corrupt(results_json)
        # Act
        result = clew.verify_claim(claim.claim_id)
        # Assert
        assert result["chain_status"] == "error"


# EOF
