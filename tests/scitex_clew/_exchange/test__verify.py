"""Store-free verification of a REAL signed bundle, and detection of tampering.

Tampering is done for real on a private copy of the project (``project_copy``):
a data file is edited, the bundle text is edited, the signature is replaced.
No mocks.
"""

from __future__ import annotations

import base64
import json

from scitex_clew._exchange import verify_bundle

BUNDLE = ".scitex/clew/evidence-bundle.json"


def _codes(result: dict) -> set[str]:
    return {f["code"] for f in result["findings"]}


def test_untouched_project_verifies(signed_bundle, bundle_project):
    # Arrange
    root = bundle_project
    # Act
    result = verify_bundle(signed_bundle, root)
    # Assert
    assert (result["ok"], result["findings"]) == (True, [])


def test_signature_is_reported_valid(signed_bundle, bundle_project):
    # Arrange
    root = bundle_project
    # Act
    result = verify_bundle(signed_bundle, root)
    # Assert
    assert (result["signed"], result["signature"]["valid"]) == (True, True)


def test_changed_input_file_is_a_hash_mismatch(project_copy):
    # Arrange
    (project_copy / "data" / "in.csv").write_text("x\n1\n2\n4\n")
    # Act
    result = verify_bundle(project_copy / BUNDLE, project_copy)
    # Assert
    assert [m["path"] for m in result["files"]["mismatched"]] == ["data/in.csv"]


def test_changed_script_is_a_hash_mismatch(project_copy):
    # Arrange
    script = project_copy / "scripts" / "stats.py"
    script.write_text(script.read_text() + "\n# edited\n")
    # Act
    result = verify_bundle(project_copy / BUNDLE, project_copy)
    # Assert
    assert [m["path"] for m in result["files"]["mismatched"]] == ["scripts/stats.py"]


def test_missing_output_is_reported_not_raised(project_copy):
    # Arrange
    (project_copy / "scripts" / "report_out" / "summary.json").unlink()
    # Act
    result = verify_bundle(project_copy / BUNDLE, project_copy)
    # Assert
    assert [m["path"] for m in result["files"]["missing"]] == [
        "scripts/report_out/summary.json"
    ]


def test_missing_output_fails_verification(project_copy):
    # Arrange
    (project_copy / "scripts" / "report_out" / "summary.json").unlink()
    # Act
    result = verify_bundle(project_copy / BUNDLE, project_copy)
    # Assert
    assert result["ok"] is False


def test_allow_missing_turns_missing_files_into_warnings(project_copy):
    # Arrange
    (project_copy / "scripts" / "report_out" / "summary.json").unlink()
    # Act
    result = verify_bundle(project_copy / BUNDLE, project_copy, allow_missing=True)
    # Assert
    assert result["ok"] is True


def test_edited_bundle_breaks_its_signature(project_copy):
    # Arrange
    path = project_copy / BUNDLE
    doc = json.loads(path.read_text())
    doc["claims"][0]["stated_value"] = 999
    path.write_text(json.dumps(doc))
    # Act
    result = verify_bundle(path, project_copy)
    # Assert
    assert _codes(result) == {"signature_invalid"}


def test_replaced_signature_value_is_invalid(project_copy):
    # Arrange
    path = project_copy / BUNDLE
    doc = json.loads(path.read_text())
    doc["signature"]["value"] = base64.b64encode(b"\0" * 64).decode()
    path.write_text(json.dumps(doc))
    # Act
    result = verify_bundle(path, project_copy)
    # Assert
    assert result["signature"]["valid"] is False


def test_unsigned_bundle_says_signed_false(project_copy):
    # Arrange
    path = project_copy / BUNDLE
    doc = json.loads(path.read_text())
    del doc["signature"]
    path.write_text(json.dumps(doc))
    # Act
    result = verify_bundle(path, project_copy)
    # Assert
    assert (result["ok"], result["signed"]) == (True, False)


def test_unexpected_signing_key_fails(signed_bundle, bundle_project):
    # Arrange
    other = "0123456789abcdef"
    # Act
    result = verify_bundle(signed_bundle, bundle_project, expected_key_id=other)
    # Assert
    assert _codes(result) == {"signature_invalid"}


def test_schema_violation_is_a_finding(project_copy):
    # Arrange
    path = project_copy / BUNDLE
    doc = json.loads(path.read_text())
    doc["runs"][0]["inputs"] = {"/etc/passwd": "0" * 64}
    del doc["signature"]
    path.write_text(json.dumps(doc))
    # Act
    result = verify_bundle(path, project_copy)
    # Assert
    assert "schema_invalid" in _codes(result)


def test_unreadable_bundle_is_a_finding_not_a_crash(tmp_path):
    # Arrange
    path = tmp_path / "bundle.json"
    path.write_text("{not json")
    # Act
    result = verify_bundle(path, tmp_path)
    # Assert
    assert _codes(result) == {"unreadable"}


# EOF
