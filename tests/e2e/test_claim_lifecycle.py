"""E2E layer — claim lifecycle against real subsystems.

Seeds a real tracked source (file hash + run row) in the isolated
PostgreSQL schema, registers a claim, and verifies it end to end.
Loopback/fleet-PG only, no internet. Slow by design: skipped by
default, runs with RUN_E2E=1.
"""

from __future__ import annotations

import os

import pytest

import scitex_clew as clew
import scitex_clew._db as _db_module
from scitex_clew._hash import hash_file

pytestmark = pytest.mark.e2e

if os.environ.get("RUN_E2E") != "1":
    pytest.skip(
        "e2e needs live subsystems — set RUN_E2E=1 to run",
        allow_module_level=True,
    )


@pytest.fixture(autouse=True)
def isolated_db():
    """Disable the read-only claims.json auto-export (explicit undo)."""
    previous = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    try:
        yield _db_module.get_db()
    finally:
        if previous is None:
            os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
        else:
            os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = previous


def _seed_verified_claim(db, tmp_path):
    """Register one claim whose source file is tracked and finished."""
    src = tmp_path / "evidence.txt"
    src.write_text("result=0.94\n")
    sid = "2026Y-06M-19D-00h00m00s_E2e-main"
    db.add_run(sid, str(tmp_path / "make_evidence.py"))
    db.add_file_hash(sid, str(src.resolve()), hash_file(src), "output")
    db.finish_run(sid, status="success")
    paper = tmp_path / "paper.tex"
    paper.write_text("result=0.94\n")
    return clew.add_claim(
        file_path=str(paper),
        claim_type="value",
        line_number=1,
        claim_value="0.94",
        source_file=str(src),
    )


def test_e2e_claim_source_verifies(isolated_db, tmp_path):
    # Arrange
    claim = _seed_verified_claim(isolated_db, tmp_path)
    # Act
    result = clew.verify_claim(claim.claim_id)
    # Assert
    assert result["source_verified"] is True


def test_e2e_verified_claim_lists_as_verified(isolated_db, tmp_path):
    # Arrange
    claim = _seed_verified_claim(isolated_db, tmp_path)
    clew.verify_claim(claim.claim_id)
    # Act
    verified = clew.list_claims(status="verified")
    # Assert
    assert claim.claim_id in [c.claim_id for c in verified]
