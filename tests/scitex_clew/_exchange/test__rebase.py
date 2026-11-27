"""Path rebasing of a project-records document (pure; real documents shapes)."""

from __future__ import annotations

import json

import pytest

from scitex_clew._exchange._rebase import parse_rebase, rebase_tables

RULES = [("/src/proj", "/dst/proj"), ("/src/proj/data", "/mnt/data")]


def _tables():
    return {
        "runs": {"rows": [{"values": {
            "session_id": "S1", "script_path": "/src/proj/scripts/a.py",
            "metadata": json.dumps({"cwd": "/src/proj", "argv": ["/src/proj/x.py", "-v"],
                                    "note": "ran in /src/proj"}),
        }, "hidden": False}]},
        "file_hashes": {"rows": [
            {"values": {"session_id": "S1", "file_path": "/src/proj/out/r.json", "role": "output",
                        "derived_from": json.dumps(["/src/proj/data/in.csv"]), "external": None},
             "hidden": False},
            {"values": {"session_id": "S1", "file_path": "/shared/atlas.nii", "role": "input",
                        "derived_from": None, "external": json.dumps({"via": None})},
             "hidden": False},
            {"values": {"session_id": "S1", "file_path": "/src/project-two/x", "role": "input",
                        "derived_from": None, "external": None}, "hidden": False},
        ]},
        "claims": {"rows": [{"values": {
            "claim_id": "c1", "file_path": "/src/proj/paper.tex",
            "source_file": "/src/proj/data/t.csv", "metadata": json.dumps({"p": "/src/proj"}),
        }, "hidden": False}]},
    }  # fmt: skip


@pytest.fixture
def rebased():
    return rebase_tables(_tables(), parse_rebase([f"{s}={d}" for s, d in RULES]))


def test_parse_orders_the_most_specific_root_first():
    # Arrange
    specs = ["/a=/b", "/a/deep/=/c"]
    # Act
    rules = parse_rebase(specs)
    # Assert
    assert rules == [("/a/deep", "/c"), ("/a", "/b")]


def test_parse_refuses_a_relative_root():
    # Arrange
    specs = ["src=/dst"]
    # Act
    refuse = pytest.raises(ValueError, match="absolute")
    # Assert
    with refuse:
        parse_rebase(specs)


def test_parse_refuses_a_root_mapped_twice():
    # Arrange
    specs = ["/a=/b", "/a=/c"]
    # Act
    refuse = pytest.raises(ValueError, match="twice")
    # Assert
    with refuse:
        parse_rebase(specs)


def test_script_path_moves_to_the_target_root(rebased):
    # Arrange
    tables, _report = rebased
    # Act
    path = tables["runs"]["rows"][0]["values"]["script_path"]
    # Assert
    assert path == "/dst/proj/scripts/a.py"


def test_most_specific_root_wins(rebased):
    # Arrange
    tables, _report = rebased
    # Act
    path = tables["claims"]["rows"][0]["values"]["source_file"]
    # Assert
    assert path == "/mnt/data/t.csv"


def test_sibling_with_a_common_prefix_is_not_moved(rebased):
    # Arrange
    tables, _report = rebased
    # Act
    path = tables["file_hashes"]["rows"][2]["values"]["file_path"]
    # Assert
    assert path == "/src/project-two/x"


def test_paths_inside_json_fields_move(rebased):
    # Arrange
    tables, _report = rebased
    # Act
    meta = json.loads(tables["runs"]["rows"][0]["values"]["metadata"])
    # Assert
    assert (meta["cwd"], meta["argv"]) == ("/dst/proj", ["/dst/proj/x.py", "-v"])


def test_prose_containing_a_path_is_not_rewritten(rebased):
    # Arrange
    tables, _report = rebased
    # Act
    meta = json.loads(tables["runs"]["rows"][0]["values"]["metadata"])
    # Assert
    assert meta["note"] == "ran in /src/proj"


def test_free_form_claim_metadata_is_untouched(rebased):
    # Arrange
    tables, _report = rebased
    # Act
    meta = tables["claims"]["rows"][0]["values"]["metadata"]
    # Assert
    assert json.loads(meta) == {"p": "/src/proj"}


def test_report_counts_scalar_paths_moved(rebased):
    # Arrange
    _tables_out, report = rebased
    # Act
    moved = report["rewritten"]
    # Assert
    assert moved == 4


def test_report_counts_external_paths_by_field(rebased):
    # Arrange
    _tables_out, report = rebased
    # Act
    by_field = report["external_by_field"]
    # Assert
    assert by_field == {"file_hashes.file_path": 2}


def test_report_names_external_paths(rebased):
    # Arrange
    _tables_out, report = rebased
    # Act
    examples = report["external_examples"]
    # Assert
    assert examples == ["/shared/atlas.nii", "/src/project-two/x"]


def test_input_document_is_not_mutated():
    # Arrange
    tables = _tables()
    before = json.dumps(tables, sort_keys=True)
    # Act
    rebase_tables(tables, parse_rebase(["/src/proj=/dst/proj"]))
    # Assert
    assert json.dumps(tables, sort_keys=True) == before


def test_no_rules_change_nothing():
    # Arrange
    tables = _tables()
    # Act
    out, _report = rebase_tables(tables, [])
    # Assert
    assert out == tables
