#!/usr/bin/env python3
"""Claim value-vs-source, native claim fields, re-add after remove, project_root.

(g)  ``source_keys`` (scitex-writer's shape: RFC 6901 pointer / csv cell) +
     tolerance (declared, else implied by the written precision); verification
     compares the claimed value with the value read from the source.
(h)  If the lineage walk raises, the claim is never reported OK.
(W2) ``value`` / ``source_keys`` / ``tolerance`` / ``metadata`` are native
     columns; ``claim_value`` stays the display string.
(W3) Re-adding a removed claim id makes it visible again.
(W4) ``project_root=`` scopes claim/verify calls without ``chdir``.

Real store, real files, no mocks. The (h) fault is a genuinely corrupted
provenance record written straight into the store.
"""

from __future__ import annotations

import json
import os
import warnings

import pytest
import scitex_clew as clew
from scitex_clew._claim._locator import (
    SourceLocatorError,
    compare,
    implied_abs_tol,
    normalize_locator,
)
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

    def test_per_locator_tolerance_overrides_claim_level(self):
        # Arrange
        locator = {"pointer": "/x", "abs_tol": 0.0}
        # Act
        ok, _ = compare("0.81", 0.8123, locator, {"abs_tol": 0.1})
        # Assert
        assert not ok

    def test_implied_tolerance_is_half_the_last_written_place(self):
        # Arrange
        written = "4.23"
        # Act
        tol = implied_abs_tol(written)
        # Assert
        assert tol == pytest.approx(0.005)

    def test_malformed_locator_is_rejected(self):
        # Arrange
        bad = {"pointer": "no-leading-slash"}
        # Act
        call = lambda: normalize_locator(bad)
        # Assert
        with pytest.raises(SourceLocatorError):
            call()


class TestNativeClaimFields:
    def test_fields_round_trip_and_display_string_is_kept(self, tmp_path, results_json):
        # Arrange
        _claim(
            tmp_path,
            "AUC = 0.81",
            results_json,
            value={"auc": 0.81},
            source_keys={"auc": "/test/auc"},
            tolerance={"rel_tol": 0.01},
            metadata={"writer_schema": 1, "macro": "\\clewAuc"},
        )
        # Act
        c = clew.list_claims()[0]
        # Assert
        assert (c.claim_value, c.value, c.source_keys, c.tolerance, c.metadata) == (
            "AUC = 0.81",
            {"auc": 0.81},
            {"auc": {"pointer": "/test/auc"}},
            {"rel_tol": 0.01},
            {"writer_schema": 1, "macro": "\\clewAuc"},
        )


class TestReAddAfterRemove:
    def test_readded_claim_is_visible(self, tmp_path, results_json):
        # Arrange
        _claim(tmp_path, "0.81", results_json, claim_id="auc")
        clew.remove_claim("auc")
        # Act
        _claim(tmp_path, "0.81", results_json, claim_id="auc")
        # Assert
        assert [c.claim_id for c in clew.list_claims()] == ["auc"]


class TestProjectRoot:
    def test_project_root_scopes_without_chdir(self, tmp_path):
        # Arrange
        a, b = tmp_path / "proj_a", tmp_path / "proj_b"
        for root in (a, b):
            (root / ".git").mkdir(parents=True)
            (root / "r.json").write_text("{}")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            clew.add_claim(
                "paper.tex",
                "value",
                1,
                "1",
                source_file="r.json",
                claim_id="x",
                project_root=a,
            )
        # Act
        seen = (
            [c.claim_id for c in clew.list_claims(project_root=a)],
            [c.claim_id for c in clew.list_claims(project_root=b)],
        )
        # Assert
        assert seen == (["x"], [])

    def test_relative_paths_resolve_against_project_root(self, tmp_path):
        # Arrange
        root = tmp_path / "proj"
        (root / ".git").mkdir(parents=True)
        (root / "r.json").write_text("{}")
        # Act
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            claim = clew.add_claim(
                "paper.tex", "value", 1, "1", source_file="r.json", project_root=root
            )
        # Assert
        assert claim.source_file == str((root / "r.json").resolve())


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
