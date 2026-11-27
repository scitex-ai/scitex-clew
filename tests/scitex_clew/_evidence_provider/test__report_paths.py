"""Contract 1.3.0: the evidence report names no build-host path.

A REAL clew project (see :mod:`._clew_project`) plus one claim whose source
lies OUTSIDE the project root (a shared file beside it). The serialized
report must hold no absolute path under the root, name the project only by
its basename, keep the out-of-root source absolute and flag it external, and
validate against the vendored 1.3.0 schema. No mocks: real sessions and a
real PostgreSQL store (one schema per module, see ``conftest.py``).
"""

from __future__ import annotations

import json

import jsonschema
import pytest
from scitex_clew._evidence_provider import SCHEMA_VERSION, EvidenceEntry, load_schema

from ._clew_project import add_external_claim


@pytest.fixture(scope="module")
def shared_source(clew_project, journal_dir):
    """This module's own project gains claim ``ext`` (source outside it).

    Module scope matches the project: ``conftest.py`` builds one project and
    one store schema per module, so no other module sees the extra claim.
    """
    return add_external_claim(clew_project, journal_dir)


@pytest.fixture(scope="module")
def paths_report(clew_project, shared_source):
    return EvidenceEntry.adapter.evidence_report(str(clew_project), None, {})


@pytest.fixture(scope="module")
def ext_claim(paths_report):
    return next(c for c in paths_report["claims"] if c["claim_id"] == "ext")


def test_no_absolute_path_under_the_root_appears_in_the_report(
    paths_report, clew_project
):
    # Arrange
    text = json.dumps(paths_report)
    # Act
    leaked = str(clew_project) in text
    # Assert
    assert leaked is False


def test_report_omits_project_root(paths_report):
    # Arrange
    report = paths_report
    # Act
    present = "project_root" in report
    # Assert
    assert present is False


def test_project_name_is_the_roots_basename(paths_report, clew_project):
    # Arrange
    report = paths_report
    # Act
    name = report["project_name"]
    # Assert
    assert name == clew_project.name


def test_out_of_root_source_stays_absolute_and_is_flagged(ext_claim, shared_source):
    # Arrange
    source = ext_claim["source"]
    # Act
    named = (source["file"], source.get("external"))
    # Assert
    assert named == (str(shared_source), True)


def test_in_root_source_is_not_flagged(paths_report):
    # Arrange
    in_root = [c for c in paths_report["claims"] if c["claim_id"] != "ext"]
    # Act
    flagged = [c["claim_id"] for c in in_root if "external" in c["source"]]
    # Assert
    assert flagged == []


def test_in_root_manuscript_location_is_not_flagged(paths_report):
    # Arrange
    claims = paths_report["claims"]
    # Act
    flagged = [c["claim_id"] for c in claims if "external" in c["location"]]
    # Assert
    assert flagged == []


def test_report_validates_against_the_1_3_0_schema(paths_report):
    # Arrange
    validator = jsonschema.Draft202012Validator(load_schema())
    # Act
    result = (SCHEMA_VERSION, [e.message for e in validator.iter_errors(paths_report)])
    # Assert
    assert result == ("1.3.0", [])
