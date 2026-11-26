"""clew's dataset provenance adapter on a REAL project (no mocks).

Contract: ``scitex-dataset.provenance-readers`` 1.0.0 — for each requested
project-relative path, the scripts recorded as READING it.
"""

from __future__ import annotations

from importlib.metadata import entry_points

import jsonschema
from scitex_clew._dataset_readers import (
    CONTRACT_VERSION,
    ReadersEntry,
    load_schema,
    readers,
)


def test_a_read_dataset_names_the_script_that_read_it(clew_project):
    # Arrange
    paths = ["data/input.csv"]
    # Act
    answer = readers(str(clew_project), paths)
    # Assert
    assert [r["script"] for r in answer["data/input.csv"]] == ["scripts/compute.py"]


def test_each_record_carries_its_run(clew_project):
    # Arrange
    paths = ["data/input2.csv"]
    # Act
    (record,) = readers(str(clew_project), paths)["data/input2.csv"]
    # Assert
    assert record["run_id"] and record["started_at"]


def test_a_path_no_run_read_is_absent(clew_project):
    # Arrange
    paths = ["paper/manual.json", "data/input.csv"]
    # Act
    answer = readers(str(clew_project), paths)
    # Assert
    assert sorted(answer) == ["data/input.csv"]


def test_an_output_is_not_reported_as_read(clew_project):
    # Arrange
    paths = ["results/results.json"]
    # Act
    answer = readers(str(clew_project), paths)
    # Assert
    assert answer == {}


def test_the_answer_validates_against_the_vendored_schema(clew_project):
    # Arrange
    validator = jsonschema.Draft202012Validator(load_schema())
    # Act
    answer = readers(str(clew_project), ["data/input.csv", "data/input2.csv"])
    # Assert
    assert validator.is_valid(answer)


def test_a_project_clew_never_scoped_gets_no_records(tmp_path):
    # Arrange
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.csv").write_text("x\n1\n")
    # Act
    answer = readers(str(tmp_path), ["data/a.csv"])
    # Assert
    assert answer == {}


def test_asking_never_writes_into_the_project(tmp_path):
    # Arrange
    (tmp_path / "data").mkdir()
    # Act
    readers(str(tmp_path), ["data/a.csv"])
    # Assert
    assert not (tmp_path / ".scitex").exists()


def test_the_entry_object_declares_the_contract_version():
    # Arrange
    entry = ReadersEntry()
    # Act
    declared = (entry.name, entry.contract_version)
    # Assert
    assert declared == ("clew", CONTRACT_VERSION)


def test_the_vendored_schema_is_the_declared_version():
    # Arrange
    schema = load_schema()
    # Act
    version = schema["$id"].rsplit("/", 1)[-1]
    # Assert
    assert version == CONTRACT_VERSION


def test_the_entry_point_is_registered_for_the_dataset_group():
    # Arrange
    group = "scitex.dataset.provenance"
    # Act
    values = {ep.name: ep.value for ep in entry_points(group=group)}
    # Assert
    assert values.get("clew") == "scitex_clew._dataset_readers:ReadersEntry"
