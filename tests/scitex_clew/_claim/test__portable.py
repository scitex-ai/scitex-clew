#!/usr/bin/env python3
"""Claim exports name in-project files relative to the project root.

``claims.json`` 1.5 and the unified feed 1.7-unified: a path inside the
project root is repo-relative; one outside stays absolute and is flagged
``<field>_external``. Real store, real files; no mocks.
"""

from __future__ import annotations

import json
import os
import warnings

import pytest
import scitex_clew as clew


@pytest.fixture
def project(tmp_path):
    """A project with an in-project and an out-of-project source, two claims."""
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    root = tmp_path / "paper"
    (root / ".git").mkdir(parents=True)
    tex = root / ".scitex" / "writer" / "01_manuscript" / "contents" / "abstract.tex"
    tex.parent.mkdir(parents=True)
    tex.write_text("x\n" * 12)
    inside = root / "data" / "slices" / "summary.json"
    inside.parent.mkdir(parents=True)
    inside.write_text(json.dumps({"n": 3}))
    outside = tmp_path / "shared" / "atlas.json"
    outside.parent.mkdir()
    outside.write_text(json.dumps({"n": 4}))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        clew.add_claim(str(tex), "value", 10, "3", source_file=str(inside),
                       claim_id="inside", project_root=root)  # fmt: skip
        clew.add_claim(str(tex), "value", 11, "4", source_file=str(outside),
                       claim_id="outside", project_root=root)  # fmt: skip
    with clew.project_root(root):
        per_claim = json.loads(
            clew.export_claims_json(
                path=tmp_path / "c.json", read_only=False
            ).read_text()
        )
        unified = json.loads(
            clew.export_manuscript_claims(
                path=tmp_path / "u.json", read_only=False
            ).read_text()
        )
    yield {
        "outside": str(outside),
        "claims": {c["claim_id"]: c for c in per_claim["claims"]},
        "unified": {c["claim_id"]: c for c in unified["claims"]},
        "per_claim_doc": per_claim,
    }
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def test_manuscript_path_is_project_relative(project):
    # Arrange
    claim = project["claims"]["inside"]
    # Act
    path = claim["file_path"]
    # Assert
    assert path == ".scitex/writer/01_manuscript/contents/abstract.tex"


def test_in_project_source_is_project_relative(project):
    # Arrange
    claim = project["claims"]["inside"]
    # Act
    path = claim["source_file"]
    # Assert
    assert path == "data/slices/summary.json"


def test_in_project_source_is_not_external(project):
    # Arrange
    claim = project["claims"]["inside"]
    # Act
    flag = claim["source_file_external"]
    # Assert
    assert flag is False


def test_out_of_project_source_stays_absolute(project):
    # Arrange
    claim = project["claims"]["outside"]
    # Act
    path = claim["source_file"]
    # Assert
    assert path == project["outside"]


def test_out_of_project_source_is_flagged_external(project):
    # Arrange
    claim = project["claims"]["outside"]
    # Act
    flag = claim["source_file_external"]
    # Assert
    assert flag is True


def test_per_claim_export_states_the_path_convention(project):
    # Arrange
    doc = project["per_claim_doc"]
    # Act
    relative_to = doc["paths"]["relative_to"]
    # Assert
    assert relative_to == "project_root"


def test_unified_entry_paths_are_project_relative(project):
    # Arrange
    entry = project["unified"]["inside"]
    # Act
    paths = (entry["file_path"], entry["source_file"], entry["link"])
    # Assert
    assert paths == (
        ".scitex/writer/01_manuscript/contents/abstract.tex",
        "data/slices/summary.json",
        "data/slices/summary.json",
    )


def test_unified_entry_flags_an_external_source(project):
    # Arrange
    entry = project["unified"]["outside"]
    # Act
    flags = (entry["source_file"], entry["source_file_external"])
    # Assert
    assert flags == (project["outside"], True)


def test_no_export_path_leaks_the_project_root(project):
    # Arrange
    entries = list(project["claims"].values()) + list(project["unified"].values())
    root = os.path.dirname(project["outside"]).rsplit("/shared", 1)[0] + "/paper"
    # Act
    leaked = [e["claim_id"] for e in entries if root in json.dumps(e)]
    # Assert
    assert leaked == []


# EOF
