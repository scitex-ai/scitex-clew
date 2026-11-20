#!/usr/bin/env python3
"""Claim VALUE integrity (:mod:`scitex_clew._claim._value_check`).

Two defects found by the paper's planted-fault instrument (E3, clew 0.26.0):

1. the claim text (``claim_value``) was never compared with a registered
   structured ``value`` — a manuscript number that drifted from its
   registration verified OK;
2. a value claim with no ``source_keys`` passed ``--strict`` on its source
   file's hash alone, without saying the value was never checked.

Real store, real files, real recorded runs; no mocks.
"""

from __future__ import annotations

import json
import os
import warnings

import pytest
import scitex_clew as clew
from scitex_clew._tracker import SessionTracker


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
    """A source file written by a recorded run (so its lineage verifies)."""
    script = tmp_path / f"make_{sid}.py"
    script.write_text("# make\n")
    out = tmp_path / name
    if isinstance(content, bytes):
        out.write_bytes(content)
    else:
        out.write_text(content)
    tracker = SessionTracker(sid, script_path=str(script))
    tracker.record_output(out)
    tracker.finalize()
    return out


def _claim(tmp_path, text, source, claim_id, claim_type="value", **kw):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return clew.add_claim(
            str(tmp_path / "paper.tex"),
            claim_type,
            None,
            text,
            source_file=str(source),
            claim_id=claim_id,
            **kw,
        )


def _outcome(result, claim_id):
    return next(c for c in result.claims if c.claim_id == claim_id).outcome


@pytest.fixture
def r_json(tmp_path):
    return _produce(tmp_path, "r.json", json.dumps({"v": 0.25}))


class TestE3Reproduction:
    """The paper's minimal project, verbatim in shape."""

    def test_text_differs_from_registered_value_is_value_mismatch(
        self, tmp_path, r_json
    ):
        # Arrange — manuscript says 1.375, registration and source say 0.25
        _claim(
            tmp_path,
            "1.375",
            r_json,
            "text_differs",
            value=0.25,
            source_keys={".": "/v"},
        )
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert (result.exit_name, result.exit_code) == ("VALUE_MISMATCH", 21)

    def test_text_differs_without_locator_is_value_mismatch(self, tmp_path, r_json):
        # Arrange
        _claim(tmp_path, "1.375", r_json, "text_differs_nl", value=0.25)
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert _outcome(result, "text_differs_nl") == "VALUE_MISMATCH"

    def test_no_locator_value_absent_from_source_fails_strict_as_unchecked(
        self, tmp_path, r_json
    ):
        # Arrange — claims 1.375, source holds 0.25, nothing locates the value
        _claim(tmp_path, "1.375", r_json, "no_locator", value=1.375)
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert (result.exit_name, result.exit_code) == ("VALUE_UNCHECKED", 24)

    def test_no_locator_unchecked_is_a_warning_by_default(self, tmp_path, r_json):
        # Arrange
        _claim(tmp_path, "1.375", r_json, "no_locator", value=1.375)
        # Act
        result = clew.verify_all_claims()
        # Assert — never silent: exit 0 but the warning is named
        assert (result.exit_code, result.warnings) == (0, ["VALUE_UNCHECKED"])

    def test_unchecked_claim_is_not_green(self, tmp_path, r_json):
        # Arrange
        claim = _claim(tmp_path, "1.375", r_json, "no_locator", value=1.375)
        # Act
        result = clew.verify_claim(claim.claim_id)
        # Assert
        assert result["claim"]["status"] == "suspect"

    def test_both_wrong_control_stays_value_mismatch(self, tmp_path, r_json):
        # Arrange
        _claim(
            tmp_path,
            "1.375",
            r_json,
            "both_wrong",
            value=1.375,
            source_keys={".": "/v"},
        )
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "VALUE_MISMATCH"


class TestTextStatesValue:
    @pytest.mark.parametrize(
        "text, value",
        [
            ("0.25", 0.25),
            ("0.25", 0.2534),  # text rounds the registered value
            ("25%", 0.25),  # percent of a stored proportion
            ("25.0\\%", 25.0),  # LaTeX percent of a stored percentage
            ("1.2 × 10^-3", 0.0012),
            ("$1.2 \\times 10^{-3}$", 0.00121),
            ("1.2e-3", 0.0012),
            ("12,345 participants", 12345),
            ("AUC = 0.91 ± 0.02", 0.91),
            ("−0.5", -0.5),
            ("$p < 0.001$", 0.0002),  # a bound the value satisfies
            ("$p \\leq .001$", 0.001),
            ("n > 100", 120),
        ],
    )
    def test_formats_that_agree_verify(self, tmp_path, text, value):
        # Arrange
        src = _produce(tmp_path, "r.json", json.dumps({"v": value}))
        _claim(tmp_path, text, src, "c", value=value, source_keys={".": "/v"})
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "OK", result.claims[0].details

    @pytest.mark.parametrize(
        "text, value",
        [
            ("0.26", 0.25),  # outside the text's own precision
            ("0.91 ± 0.25", 0.25),  # an uncertainty never stands for the value
            ("1.2 × 10^-4", 0.0012),
            ("$p < 0.001$", 0.003),  # the stated bound is false
            ("$p < 0.001$", 0.001),  # strict bound
        ],
    )
    def test_formats_that_disagree_are_value_mismatch(self, tmp_path, text, value):
        # Arrange
        src = _produce(tmp_path, "r.json", json.dumps({"v": value}))
        _claim(tmp_path, text, src, "c", value=value, source_keys={".": "/v"})
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "VALUE_MISMATCH"

    def test_declared_tolerance_governs_text_agreement(self, tmp_path):
        # Arrange — "0.3" alone implies ±0.05; a declared ±0.001 is stricter
        src = _produce(tmp_path, "r.json", json.dumps({"v": 0.27}))
        _claim(
            tmp_path,
            "0.3",
            src,
            "c",
            value=0.27,
            source_keys={".": "/v"},
            tolerance={"abs_tol": 0.001},
        )
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "VALUE_MISMATCH"

    def test_dict_value_every_field_must_be_written(self, tmp_path):
        # Arrange
        src = _produce(tmp_path, "r.json", json.dumps({"auc": 0.91, "n": 120}))
        _claim(
            tmp_path,
            "AUC = 0.91 (n = 120)",
            src,
            "c",
            value={"auc": 0.91, "n": 120},
            source_keys={"auc": "/auc", "n": "/n"},
        )
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "OK"

    def test_text_without_any_number_is_not_compared(self, tmp_path, r_json):
        # Arrange — a label, not a number: nothing to contradict
        _claim(tmp_path, "the AUC", r_json, "c", value=0.25, source_keys={".": "/v"})
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "OK"


class TestDisplayTextAgainstLocatedSource:
    def test_text_only_claim_with_prefix_reads_its_number(self, tmp_path):
        # Arrange — no structured value: the display text is the claimed value
        src = _produce(tmp_path, "r.json", json.dumps({"p": 0.003}))
        _claim(tmp_path, "p = 0.003", src, "c", source_keys={".": "/p"})
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "OK"

    def test_text_only_percent_against_proportion(self, tmp_path):
        # Arrange
        src = _produce(tmp_path, "r.json", json.dumps({"acc": 0.4531}))
        _claim(tmp_path, "45.3%", src, "c", source_keys={".": "/acc"})
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "OK"


class TestLocatorFreeJustification:
    def test_unique_match_in_json_justifies_the_value(self, tmp_path):
        # Arrange
        src = _produce(tmp_path, "r.json", json.dumps({"a": {"auc": 0.8123}}))
        claim = _claim(tmp_path, "0.81", src, "c")
        # Act
        result = clew.verify_claim(claim.claim_id)
        # Assert — justified, and the report says where it was found
        found = [c for c in result["value_checks"] if c["ok"]]
        assert found[0]["locator"] == {"pointer": "/a/auc"}

    def test_unique_match_passes_strict(self, tmp_path):
        # Arrange
        src = _produce(tmp_path, "r.json", json.dumps({"a": {"auc": 0.8123}}))
        _claim(tmp_path, "0.81", src, "c")
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "OK"

    def test_ambiguous_match_is_unchecked(self, tmp_path):
        # Arrange — 0.25 at two places: the search cannot say which is meant
        src = _produce(tmp_path, "r.json", json.dumps({"x": 0.25, "y": 0.25}))
        _claim(tmp_path, "0.25", src, "c")
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "VALUE_UNCHECKED"

    def test_csv_cell_match(self, tmp_path):
        # Arrange
        src = _produce(tmp_path, "t.csv", "subject,auc\nS01,0.91\nS02,0.85\n")
        claim = _claim(tmp_path, "AUC 0.85", src, "c", claim_type="statistic")
        # Act
        result = clew.verify_claim(claim.claim_id)
        # Assert
        hit = next(c for c in result["value_checks"] if c["ok"])
        assert hit["locator"] == {"row": 1, "column": "auc"}

    def test_npy_scalar_match(self, tmp_path):
        # Arrange
        np = pytest.importorskip("numpy")
        path = tmp_path / "v.npy"
        np.save(path, np.float64(3.14159))
        src = _produce(tmp_path, "v.npy", path.read_bytes())
        _claim(tmp_path, "3.14", src, "c", value=3.14)
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "OK"

    def test_bound_is_not_searched_as_a_point_value(self, tmp_path):
        # Arrange — "p < 0.001" against a source holding p = 0.001: finding
        # 0.001 would "justify" a bound the source actually contradicts
        src = _produce(tmp_path, "r.json", json.dumps({"p": 0.001}))
        _claim(tmp_path, "p < 0.001", src, "c", claim_type="statistic")
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "VALUE_UNCHECKED"

    def test_unsearchable_source_is_unchecked(self, tmp_path):
        # Arrange — a text report is not a structured source
        src = _produce(tmp_path, "report.txt", "the value is 0.25\n")
        _claim(tmp_path, "0.25", src, "c")
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "VALUE_UNCHECKED"

    def test_figure_claim_without_value_needs_no_value_check(self, tmp_path):
        # Arrange — a file claim ("Figure 2") states no value to verify
        src = _produce(tmp_path, "fig.png", b"\x89PNG\r\n\x1a\n")
        _claim(tmp_path, "Figure 2", src, "c", claim_type="figure")
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "OK"

    def test_unchecked_ranks_below_a_real_failure(self, tmp_path, r_json):
        # Arrange — one unchecked value + one contradicted value
        _claim(tmp_path, "1.375", r_json, "unchecked", value=1.375)
        _claim(tmp_path, "0.5", r_json, "wrong", source_keys={".": "/v"})
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "VALUE_MISMATCH"


# EOF
