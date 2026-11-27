#!/usr/bin/env python3
"""A slice names each kept run's EXECUTABLE (its script) — real store, no mocks.

The input -> executable -> output triplet: ``clew slice`` printed the inputs
and outputs of a run but never the script that turned one into the other.

Toy pipeline::

    raw.csv ──> prep (scripts/prep.py, in project) ──> clean.csv
    clean.csv ──> fit (<outside>/fit.py, outside project) ──> result.json
"""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from scitex_clew._chain._slice import build_slice
from scitex_clew._chain._slice_records import describe_script
from scitex_clew._cli._verification_dag import slice_cmd
from scitex_clew._hash import hash_file
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


def _run(sid, script, root, inputs, outputs):
    tracker = SessionTracker(
        sid, script_path=str(script), metadata={"project_root": str(root)}
    )
    for path in inputs:
        tracker.record_input(path)
    for path, content in outputs.items():
        path.write_text(content)
        tracker.record_output(path)
    tracker.finalize()


@pytest.fixture
def toy(tmp_path):
    root = tmp_path / "project"
    outside = tmp_path / "elsewhere"
    (root / "scripts").mkdir(parents=True)
    outside.mkdir()
    prep, fit = root / "scripts" / "prep.py", outside / "fit.py"
    prep.write_text("# prep\n")
    fit.write_text("# fit\n")
    raw, clean, result = root / "raw.csv", root / "clean.csv", root / "result.json"
    raw.write_text("x\n1\n")
    _run("prep", prep, root, [raw], {clean: "x\n1\n"})
    _run("fit", fit, root, [clean], {result: json.dumps({"m": 0.5})})
    return {"root": root, "prep": prep, "fit": fit, "result": result}


class TestSliceScripts:
    @pytest.mark.parametrize("level", [0, 1, 2])
    def test_every_kept_run_carries_its_script_and_hash(self, toy, level):
        # Arrange
        target = str(toy["result"])
        # Act
        sl = build_slice([target], level=level)
        # Assert
        assert {s: (e["path"], e["hash"]) for s, e in sl.scripts.items()} == {
            "prep": (str(toy["prep"]), hash_file(toy["prep"])),
            "fit": (str(toy["fit"]), hash_file(toy["fit"])),
        }

    def test_script_is_not_counted_as_a_slice_file(self, toy):
        # Arrange
        target = str(toy["result"])
        # Act
        sl = build_slice([target], level=1)
        # Assert
        assert (sl.counts(), str(toy["prep"]) in sl.files) == (
            {"runs": 2, "files": 3, "nodes": 5, "edges": 4},
            False,
        )

    def test_json_lists_scripts_per_run(self, toy):
        # Arrange
        target = str(toy["result"])
        # Act
        result = CliRunner().invoke(slice_cmd, [target, "--json"])
        # Assert
        scripts = json.loads(result.output)["scripts"]
        assert (result.exit_code, scripts["prep"]["path"], scripts["fit"]["hash"]) == (
            0,
            str(toy["prep"]),
            hash_file(toy["fit"]),
        )

    def test_text_names_script_relative_inside_and_absolute_outside(self, toy):
        # Arrange
        target = str(toy["result"])
        prep_hash, fit_hash = hash_file(toy["prep"]), hash_file(toy["fit"])
        # Act
        result = CliRunner().invoke(slice_cmd, [target])
        # Assert
        lines = [ln for ln in result.output.splitlines() if ln.startswith("  run ")]
        assert (result.exit_code, lines) == (
            0,
            [
                f"  run prep  script: scripts/prep.py (sha256 {prep_hash[:12]})",
                f"  run fit  script: {toy['fit']} (sha256 {fit_hash[:12]})",
            ],
        )


class TestDescribeScript:
    def test_missing_script_is_reported_not_blank(self):
        # Arrange
        entry = None
        # Act
        text = describe_script(entry)
        # Assert
        assert text == "script: not recorded"

    def test_missing_hash_is_reported(self):
        # Arrange
        entry = {"path": "/p/a.py", "hash": None, "project_root": None}
        # Act
        text = describe_script(entry)
        # Assert
        assert text == "script: /p/a.py (hash not recorded)"

    def test_notebook_hash_is_labelled_by_its_scheme(self):
        # Arrange
        entry = {
            "path": "/p/nb.ipynb",
            "hash": "ipynb-code-v1:" + "ab" * 32,
            "project_root": "/p",
        }
        # Act
        text = describe_script(entry)
        # Assert
        assert text == "script: nb.ipynb (ipynb-code-v1 abababababab)"


# EOF
