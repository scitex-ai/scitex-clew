#!/usr/bin/env python3
"""File-level minimal slice (``clew.slice``) — real store, real files, no mocks.

Toy pipeline (the E2 shape)::

    raw.csv ─┐                    ┌─> clean.csv ──> B ──> result.json  (target)
    unrel.csv┴─> A (loads both) ──┤                  └──> log.txt     (sibling)
                                  └─> side.csv ──> C ──> report.txt   (off-path)

    U ──> unrel.csv   (U produced the unused input)

Level 0 (run-level closure) keeps every input/output of A, B and U; level 1
drops the sibling outputs (side.csv, log.txt) and never reaches C; level 2,
with ``derived_from`` declared, also drops unrel.csv and therefore U.
"""

from __future__ import annotations

import json
import os
import warnings

import pytest
import scitex_clew as clew
from scitex_clew._chain import VerificationStatus, verify_chain, verify_dag
from scitex_clew._chain._slice import build_slice, compare_levels
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


def _run(tmp_path, sid, inputs=(), outputs=None):
    script = tmp_path / f"{sid}.py"
    script.write_text(f"# {sid}\n")
    tracker = SessionTracker(sid, script_path=str(script))
    for path in inputs:
        tracker.record_input(path)
    for path, (content, derived) in (outputs or {}).items():
        path.write_text(content)
        tracker.record_output(path, derived_from=derived)
    tracker.finalize()


def _pipeline(tmp_path, declared: bool):
    p = {
        n: tmp_path / n
        for n in (
            "raw.csv",
            "unrel.csv",
            "clean.csv",
            "side.csv",
            "result.json",
            "log.txt",
            "report.txt",
        )
    }
    p["raw.csv"].write_text("x\n1\n")
    _run(tmp_path, "U", outputs={p["unrel.csv"]: ("y\n2\n", [] if declared else None)})
    _run(
        tmp_path,
        "A",
        inputs=[p["raw.csv"], p["unrel.csv"]],
        outputs={
            p["clean.csv"]: ("x\n1\n", [p["raw.csv"]] if declared else None),
            p["side.csv"]: ("summary\n", None),
        },
    )
    _run(
        tmp_path,
        "B",
        inputs=[p["clean.csv"]],
        outputs={
            p["result.json"]: (
                json.dumps({"mean_score": 0.5}),
                [p["clean.csv"]] if declared else None,
            ),
            p["log.txt"]: ("done\n", None),
        },
    )
    _run(
        tmp_path, "C", inputs=[p["side.csv"]], outputs={p["report.txt"]: ("r\n", None)}
    )
    return p


def _names(paths):
    return sorted(os.path.basename(x) for x in paths)


@pytest.fixture
def toy(tmp_path):
    return _pipeline(tmp_path, declared=False)


@pytest.fixture
def toy_declared(tmp_path):
    return _pipeline(tmp_path, declared=True)


class TestLevels:
    def test_level0_keeps_every_file_of_every_ancestor_run(self, toy):
        # Arrange
        target = str(toy["result.json"])
        # Act
        sl = build_slice([target], level=0)
        # Assert
        assert _names(sl.files) == [
            "clean.csv",
            "log.txt",
            "raw.csv",
            "result.json",
            "side.csv",
            "unrel.csv",
        ]

    def test_level1_drops_sibling_outputs(self, toy):
        # Arrange
        target = str(toy["result.json"])
        # Act
        sl = build_slice([target], level=1)
        # Assert
        assert _names(sl.files) == ["clean.csv", "raw.csv", "result.json", "unrel.csv"]

    def test_level1_never_includes_the_sibling_consumer(self, toy):
        # Arrange
        target = str(toy["result.json"])
        # Act
        sl = build_slice([target], level=1)
        # Assert
        assert "C" not in sl.runs

    def test_level1_reports_what_it_dropped(self, toy):
        # Arrange
        target = str(toy["result.json"])
        # Act
        sl = build_slice([target], level=1)
        # Assert
        assert {k: _names(v) for k, v in sl.dropped_outputs.items()} == {
            "A": ["side.csv"],
            "B": ["log.txt"],
        }

    def test_level1_counts_versus_level0(self, toy):
        # Arrange
        target = str(toy["result.json"])
        # Act
        counts = compare_levels([target])
        # Assert
        assert (counts[0], counts[1]) == (
            {"runs": 3, "files": 6, "nodes": 9, "edges": 8},
            {"runs": 3, "files": 4, "nodes": 7, "edges": 6},
        )

    def test_level2_without_declarations_falls_back_to_level1(self, toy):
        # Arrange
        target = str(toy["result.json"])
        # Act
        sl = build_slice([target], level=2)
        # Assert
        assert (sorted(sl.fallback_runs), sl.counts()) == (
            ["A", "B", "U"],
            build_slice([target], level=1).counts(),
        )

    def test_level2_with_declarations_drops_unused_input_and_its_producer(
        self, toy_declared
    ):
        # Arrange
        target = str(toy_declared["result.json"])
        # Act
        sl = build_slice([target], level=2)
        # Assert
        assert (sl.runs, _names(sl.files)) == (
            ["A", "B"],
            ["clean.csv", "raw.csv", "result.json"],
        )

    def test_roots_first_order(self, toy):
        # Arrange
        target = str(toy["result.json"])
        # Act
        sl = build_slice([target], level=1)
        # Assert
        assert sl.runs.index("A") < sl.runs.index("B")

    def test_invalid_level_is_rejected(self, toy):
        # Arrange
        target = str(toy["result.json"])
        # Act
        call = lambda: build_slice([target], level=3)
        # Assert
        with pytest.raises(ValueError):
            call()


class TestTargets:
    def test_slice_by_claim_id_matches_slice_by_file(self, toy, tmp_path):
        # Arrange
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            claim = clew.add_claim(
                str(tmp_path / "paper.tex"),
                "value",
                3,
                "0.5",
                source_file=str(toy["result.json"]),
            )
        # Act
        by_claim = clew.slice(claim.claim_id)
        # Assert
        assert by_claim.files == clew.slice(str(toy["result.json"])).files

    def test_unproduced_target_is_a_lone_file_node(self, tmp_path):
        # Arrange
        raw = tmp_path / "hand_written.json"
        raw.write_text("{}")
        # Act
        sl = clew.slice(str(raw))
        # Assert
        assert (sl.counts(), sl.unproduced_targets) == (
            {"runs": 0, "files": 1, "nodes": 1, "edges": 0},
            [str(raw.resolve())],
        )

    def test_to_dict_carries_counts(self, toy):
        # Arrange
        sl = clew.slice(str(toy["result.json"]))
        # Act
        payload = json.loads(json.dumps(sl.to_dict()))
        # Assert
        assert payload["counts"] == sl.counts()


class TestVerificationChecksOnlyTheSlice:
    def test_tampered_sibling_output_stales_the_closure(self, toy):
        # Arrange
        toy["side.csv"].write_text("tampered\n")
        # Act
        chain = verify_chain(str(toy["result.json"]))
        # Assert
        assert chain.status == VerificationStatus.MISMATCH

    def test_tampered_sibling_output_does_not_stale_the_slice(self, toy):
        # Arrange
        toy["side.csv"].write_text("tampered\n")
        # Act
        chain = verify_chain(str(toy["result.json"]), minimal=True)
        # Assert
        assert chain.status == VerificationStatus.VERIFIED

    def test_tampered_on_path_input_still_fails_the_slice(self, toy):
        # Arrange
        toy["raw.csv"].write_text("x\n999\n")
        # Act
        chain = verify_chain(str(toy["result.json"]), minimal=True)
        # Assert
        assert not chain.is_verified

    def test_minimal_chain_exposes_its_slice(self, toy):
        # Arrange
        target = str(toy["result.json"])
        # Act
        chain = clew.chain(target, minimal=True)
        # Assert
        assert chain.slice.counts() == build_slice([target]).counts()

    def test_minimal_dag_ignores_tampered_sibling(self, toy):
        # Arrange
        toy["log.txt"].write_text("tampered\n")
        # Act
        dag = verify_dag([str(toy["result.json"])], minimal=True)
        # Assert
        assert dag.status == VerificationStatus.VERIFIED

    def test_claim_verification_checks_only_the_slice(self, toy, tmp_path):
        # Arrange
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            clew.add_claim(
                str(tmp_path / "paper.tex"),
                "value",
                4,
                "0.5",
                source_file=str(toy["result.json"]),
            )
        toy["side.csv"].write_text("tampered\n")
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "OK"


# EOF
