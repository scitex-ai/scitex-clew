"""`clew export-evidence`: the evidence report written out of process.

A REAL clew project (see ``tests/scitex_clew/_evidence_provider/_clew_project``)
is built in this test's own PostgreSQL schema, then a scrubbed child
interpreter runs the CLI from outside the project. No mocks.
"""

from __future__ import annotations

import json
import subprocess
import sys

import jsonschema
from scitex_clew._evidence_provider import load_schema

from .._evidence_provider._clew_project import (
    EXPECTED_REPORT,
    build_project,
    child_env,
)


def _export(root, journal, tmp_path, *extra):
    out = tmp_path / "report.json"
    argv = [sys.executable, "-m", "scitex_clew", "export-evidence", "--out", str(out)]
    run = subprocess.run(
        [*argv, "--project-root", str(root), *extra],
        cwd=tmp_path,
        env=child_env(journal),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if run.returncode != 0:
        return {"error": run.stderr[-2_000:]}
    return json.loads(out.read_text())


def test_export_evidence_writes_a_valid_report_with_every_claim_state(
    tmp_path, isolated_journal
):
    # Arrange
    root = build_project(tmp_path / "work", isolated_journal)
    validator = jsonschema.Draft202012Validator(load_schema())
    # Act
    written = _export(root, isolated_journal, tmp_path)
    states = {c["claim_id"]: c["state"] for c in written.get("claims", [])}
    # Assert
    assert (validator.is_valid(written), states) == (
        True,
        {cid: exp[0] for cid, exp in EXPECTED_REPORT.items()},
    ), written
