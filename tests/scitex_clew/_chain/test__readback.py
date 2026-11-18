#!/usr/bin/env python3
"""Same-bytes read-back rewrites in the slice — real store, real files, no mocks.

The paper's E2 shape: one script ran twice; each run READ its output ``F``
and REWROTE it with identical bytes. The slice of ``F`` must hold ONE
producer (the originating one), while a real chain (different bytes), a run
kept for another output, the level-0 closure and full-chain verification are
unchanged.
"""

from __future__ import annotations

import os
import warnings

import pytest
import scitex_clew as clew
from scitex_clew._chain import VerificationStatus, verify_chain
from scitex_clew._chain._slice import build_slice
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
    """One recorded run: record inputs (as on disk now), then write outputs."""
    script = tmp_path / f"{sid}.py"
    script.write_text("# step\n")
    tracker = SessionTracker(sid, script_path=str(script))
    for path in inputs:
        tracker.record_input(path)
    for path, content in (outputs or {}).items():
        path.write_text(content)
        tracker.record_output(path)
    tracker.finalize()


@pytest.fixture
def rerun(tmp_path):
    """R1 writes F; R2 and R3 each read F and rewrite it with the same bytes."""
    data, out = tmp_path / "data.csv", tmp_path / "stat.json"
    data.write_text("x\n1\n2\n")
    _run(tmp_path, "R1", inputs=[data], outputs={out: '{"mean": 1.5}'})
    _run(tmp_path, "R2", inputs=[data, out], outputs={out: '{"mean": 1.5}'})
    _run(tmp_path, "R3", inputs=[data, out], outputs={out: '{"mean": 1.5}'})
    return {"data": data, "out": out}


@pytest.fixture
def chain_different_bytes(tmp_path):
    """R1 writes F@h1; R2 reads F@h1 and writes F@h2 (a real dependency)."""
    data, out = tmp_path / "data.csv", tmp_path / "stat.json"
    data.write_text("x\n1\n2\n")
    _run(tmp_path, "R1", inputs=[data], outputs={out: '{"mean": 1.5}'})
    _run(tmp_path, "R2", inputs=[out], outputs={out: '{"mean": 1.5, "n": 2}'})
    return {"data": data, "out": out}


@pytest.fixture
def readback_and_other_output(tmp_path):
    """R2 reads F@h, rewrites F@h AND writes G (G may depend on F's bytes)."""
    data, out, fig = (tmp_path / n for n in ("data.csv", "stat.json", "fig.txt"))
    data.write_text("x\n1\n2\n")
    _run(tmp_path, "R1", inputs=[data], outputs={out: '{"mean": 1.5}'})
    _run(tmp_path, "R2", inputs=[out], outputs={out: '{"mean": 1.5}', fig: "1.5\n"})
    return {"data": data, "out": out, "fig": fig}


class TestSameBytesRerun:
    @pytest.mark.parametrize("level", [1, 2])
    def test_slice_holds_only_the_originating_producer(self, rerun, level):
        # Arrange
        target = str(rerun["out"])
        # Act
        sl = build_slice([target], level=level)
        # Assert
        assert sl.runs == ["R1"]

    def test_slice_keeps_the_originating_producers_inputs(self, rerun):
        # Arrange
        target = str(rerun["out"])
        # Act
        sl = build_slice([target], level=1)
        # Assert
        assert sl.run_inputs["R1"] == [str(rerun["data"].resolve())]

    def test_level0_closure_still_holds_every_rerun(self, rerun):
        # Arrange
        target = str(rerun["out"])
        # Act
        sl = build_slice([target], level=0)
        # Assert
        assert sorted(sl.runs) == ["R1", "R2", "R3"]

    def test_readback_of_unproduced_bytes_keeps_the_rewriter(self, tmp_path):
        # Arrange: the bytes pre-date every recorded run (hand-written)
        out = tmp_path / "stat.json"
        out.write_text('{"mean": 1.5}')
        _run(tmp_path, "R1", inputs=[out], outputs={out: '{"mean": 1.5}'})
        # Act
        sl = build_slice([str(out)], level=1)
        # Assert
        assert (sl.runs, sl.run_inputs["R1"]) == (["R1"], [str(out.resolve())])


class TestRealDependenciesUnaffected:
    def test_different_bytes_rewrite_keeps_both_runs(self, chain_different_bytes):
        # Arrange
        target = str(chain_different_bytes["out"])
        # Act
        sl = build_slice([target], level=1)
        # Assert
        assert (sl.runs, sl.parents["R2"]) == (["R1", "R2"], ["R1"])

    def test_other_output_of_a_readback_run_keeps_the_earlier_producer(
        self, readback_and_other_output
    ):
        # Arrange
        target = str(readback_and_other_output["fig"])
        # Act
        sl = build_slice([target], level=1)
        # Assert
        assert (sl.runs, sl.parents["R2"]) == (["R1", "R2"], ["R1"])

    def test_readback_runs_own_rewrite_is_not_a_demanded_output(
        self, readback_and_other_output
    ):
        # Arrange
        target = str(readback_and_other_output["fig"])
        # Act
        sl = build_slice([target], level=1)
        # Assert
        assert sl.run_outputs["R2"] == [str(readback_and_other_output["fig"].resolve())]


class TestVerificationUnchanged:
    def test_full_chain_still_walks_every_rerun(self, rerun):
        # Arrange
        target = str(rerun["out"])
        # Act
        chain = verify_chain(target)
        # Assert
        assert sorted(r.session_id for r in chain.runs) == ["R1", "R2", "R3"]

    def test_full_chain_verifies(self, rerun):
        # Arrange
        target = str(rerun["out"])
        # Act
        chain = verify_chain(target)
        # Assert
        assert chain.status == VerificationStatus.VERIFIED

    def test_minimal_chain_verifies_the_single_producer(self, rerun):
        # Arrange
        target = str(rerun["out"])
        # Act
        chain = verify_chain(target, minimal=True)
        # Assert
        assert ([r.session_id for r in chain.runs], chain.status) == (
            ["R1"],
            VerificationStatus.VERIFIED,
        )

    @pytest.mark.parametrize("minimal", [False, True])
    def test_tampered_input_still_fails(self, rerun, minimal):
        # Arrange
        rerun["data"].write_text("x\n999\n")
        # Act
        chain = verify_chain(str(rerun["out"]), minimal=minimal)
        # Assert: a changed source input marks the lineage SUSPECT either way
        assert chain.status == VerificationStatus.SUSPECT

    def test_claim_on_rewritten_file_verifies(self, rerun, tmp_path):
        # Arrange
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            clew.add_claim(
                str(tmp_path / "paper.tex"),
                "value",
                3,
                "1.5",
                source_file=str(rerun["out"]),
            )
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "OK"

    def test_claim_lineage_goes_stale_when_input_changes(self, rerun, tmp_path):
        # Arrange
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            clew.add_claim(
                str(tmp_path / "paper.tex"),
                "value",
                3,
                "1.5",
                source_file=str(rerun["out"]),
            )
        rerun["data"].write_text("x\n999\n")
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_name == "STALE_LINEAGE"


# EOF
