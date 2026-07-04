"""Tests for ``scitex_clew._chain._chain_ops`` (verify_chain, get_status).

The chain ops drive a real DB plus on-disk file hashing. To keep
tests deterministic we use the PA-306 §1 DI seams exposed by
production:

  - ``db_factory``    — zero-arg callable returning a fake DB exposing
    only ``find_session_by_file`` / ``get_chain`` / ``list_runs``.
  - ``verify_run_fn`` — ``(session_id) -> RunVerification`` that
    returns canned values, so the chain status logic can be exercised
    without disk hashing.

No attribute swapping; the production signature documents the seam.
"""

from __future__ import annotations

from typing import Any

from scitex_clew._chain._chain_ops import get_status, verify_chain
from scitex_clew._chain._types import (
    ChainVerification,
    FileVerification,
    RunVerification,
    VerificationStatus,
)


class _FakeDB:
    """Stand-in for ``VerificationDB`` exposing only what chain_ops calls.

    ``verify_chain`` now resolves the chain from file save->load handshakes
    (``get_file_hashes`` + ``find_session_by_file``), so this fake synthesizes
    file records from the ``chain`` list: each consecutive pair
    ``chain[i] -> chain[i+1]`` becomes a file that ``chain[i]`` outputs and
    ``chain[i+1]`` loads. The file-route resolver then reconstructs exactly
    that chain, and the status-propagation assertions remain meaningful.
    """

    def __init__(
        self,
        *,
        sessions_for_file: list[str] | None = None,
        chain: list[str] | None = None,
        runs: list[dict[str, Any]] | None = None,
    ):
        self._sessions_for_file = sessions_for_file or []
        self._chain = chain or []
        self._runs = runs or []
        # Synthesize save->load records from the (root-first) chain list.
        self._producer_of: dict[str, list[str]] = {}
        self._inputs_of: dict[str, list[str]] = {}
        for parent, child in zip(self._chain, self._chain[1:]):
            edge_file = f"__edge::{parent}->{child}"
            self._producer_of[edge_file] = [parent]
            self._inputs_of.setdefault(child, []).append(edge_file)

    def find_session_by_file(self, target: str, role: str = "output") -> list[str]:
        if target in self._producer_of:
            return list(self._producer_of[target])
        return list(self._sessions_for_file)

    def find_sessions_by_files(
        self, file_paths: list[str], role: str = "output"
    ) -> dict[str, list[str]]:
        """Batch variant used by the refactored _parents_via_files."""
        result: dict[str, list[str]] = {}
        for fp in file_paths:
            producers = self.find_session_by_file(fp, role=role)
            if producers:
                result[fp] = producers
        return result

    def get_file_hashes(self, session_id: str, role: str | None = None) -> dict:
        if role == "input":
            return {f: "h" for f in self._inputs_of.get(session_id, [])}
        return {}

    def get_chain(self, session_id: str) -> list[str]:
        return list(self._chain)

    def list_runs(self, *, limit: int = 1_000) -> list[dict[str, Any]]:
        return list(self._runs)


def _make_run(
    session_id: str = "s1",
    status: VerificationStatus = VerificationStatus.VERIFIED,
    files=None,
) -> RunVerification:
    return RunVerification(
        session_id=session_id,
        script_path=None,
        status=status,
        files=files or [],
        combined_hash_expected=None,
        combined_hash_current=None,
    )


def _bucket_verify(sid: str) -> RunVerification:
    """Shared ``verify_run_fn`` for the get_status bucket tests:
    v1 → VERIFIED, m1 → MISMATCH with one mismatched file, x1 → MISSING."""
    if sid == "v1":
        return _make_run(session_id=sid, status=VerificationStatus.VERIFIED)
    if sid == "m1":
        mismatched = FileVerification(
            path="/m.csv",
            role="output",
            expected_hash="00",
            current_hash="ff",
            status=VerificationStatus.MISMATCH,
        )
        return _make_run(
            session_id=sid,
            status=VerificationStatus.MISMATCH,
            files=[mismatched],
        )
    missing = FileVerification(
        path="/x.csv",
        role="output",
        expected_hash="00",
        current_hash=None,
        status=VerificationStatus.MISSING,
    )
    return _make_run(session_id=sid, status=VerificationStatus.MISSING, files=[missing])


_BUCKET_RUNS = [
    {"session_id": "v1"},
    {"session_id": "m1"},
    {"session_id": "x1"},
]


# ----- verify_chain -------------------------------------------------------- #


def test_verify_chain_returns_unknown_when_target_has_no_session_out_is_chainverification():
    # Arrange
    db_factory = lambda: _FakeDB()
    # Act
    out = verify_chain("/some/output.csv", db_factory=db_factory)
    # Assert
    assert isinstance(out, ChainVerification)


def test_verify_chain_returns_unknown_when_target_has_no_session_out_status_equals_verificationstatus_unknown():
    # Arrange
    db_factory = lambda: _FakeDB()
    # Act
    out = verify_chain("/some/output.csv", db_factory=db_factory)
    # Assert
    assert out.status == VerificationStatus.UNKNOWN


def test_verify_chain_returns_unknown_when_target_has_no_session_out_runs_equals_case():
    # Arrange
    db_factory = lambda: _FakeDB()
    # Act
    out = verify_chain("/some/output.csv", db_factory=db_factory)
    # Assert
    assert out.runs == []


def test_verify_chain_all_verified_propagates_verified_status_out_status_equals_verificationstatus_verified():
    # Arrange
    db_factory = lambda: _FakeDB(sessions_for_file=["s2"], chain=["s1", "s2"])
    verify_run_fn = lambda sid: _make_run(session_id=sid)
    # Act
    out = verify_chain("/out.csv", db_factory=db_factory, verify_run_fn=verify_run_fn)
    # Assert
    assert out.status == VerificationStatus.VERIFIED


def test_verify_chain_all_verified_propagates_verified_status_r_session_id_for_r_in_out_runs_s1_s2():
    # Arrange
    db_factory = lambda: _FakeDB(sessions_for_file=["s2"], chain=["s1", "s2"])
    verify_run_fn = lambda sid: _make_run(session_id=sid)
    # Act
    out = verify_chain("/out.csv", db_factory=db_factory, verify_run_fn=verify_run_fn)
    # Assert
    assert [r.session_id for r in out.runs] == ["s1", "s2"]


def test_verify_chain_all_verified_propagates_verified_status_out_is_verified():
    # Arrange
    db_factory = lambda: _FakeDB(sessions_for_file=["s2"], chain=["s1", "s2"])
    verify_run_fn = lambda sid: _make_run(session_id=sid)
    # Act
    out = verify_chain("/out.csv", db_factory=db_factory, verify_run_fn=verify_run_fn)
    # Assert
    assert out.is_verified


def test_verify_chain_propagates_mismatch_when_any_run_mismatched():
    # Arrange
    def _verify(sid: str) -> RunVerification:
        return _make_run(
            session_id=sid,
            status=(
                VerificationStatus.MISMATCH
                if sid == "s1"
                else VerificationStatus.VERIFIED
            ),
        )

    db_factory = lambda: _FakeDB(sessions_for_file=["s2"], chain=["s1", "s2"])
    # Act
    out = verify_chain("/out.csv", db_factory=db_factory, verify_run_fn=_verify)
    # Assert
    assert out.status == VerificationStatus.MISMATCH


def test_verify_chain_propagates_missing_when_no_mismatch_but_missing():
    # Arrange
    db_factory = lambda: _FakeDB(sessions_for_file=["s1"], chain=["s1"])
    verify_run_fn = lambda sid: _make_run(status=VerificationStatus.MISSING)
    # Act
    out = verify_chain("/out.csv", db_factory=db_factory, verify_run_fn=verify_run_fn)
    # Assert
    assert out.status == VerificationStatus.MISSING


def test_verify_chain_unknown_when_runs_have_no_explicit_status():
    """All runs UNKNOWN → chain UNKNOWN (not VERIFIED, MISMATCH, MISSING)."""
    # Arrange
    db_factory = lambda: _FakeDB(sessions_for_file=["s1"], chain=["s1"])
    verify_run_fn = lambda sid: _make_run(status=VerificationStatus.UNKNOWN)
    # Act
    out = verify_chain("/out.csv", db_factory=db_factory, verify_run_fn=verify_run_fn)
    # Assert
    assert out.status == VerificationStatus.UNKNOWN


def test_verify_chain_target_path_is_resolved(tmp_path):
    """Relative target paths are resolved via Path(...).resolve()."""
    # Arrange
    captured = {}

    class _Capture(_FakeDB):
        def find_session_by_file(self, target, role="output"):
            captured["arg"] = target
            return []

    f = tmp_path / "result.csv"
    f.write_text("x")
    # Act
    verify_chain(str(f), db_factory=lambda: _Capture())
    # Assert
    assert captured["arg"] == str(f.resolve())


# ----- get_status ---------------------------------------------------------- #


def test_get_status_counts_each_bucket_out_verified_count_1():
    # Arrange
    db_factory = lambda: _FakeDB(runs=_BUCKET_RUNS)
    # Act
    out = get_status(db_factory=db_factory, verify_run_fn=_bucket_verify)
    # Assert
    assert out["verified_count"] == 1


def test_get_status_counts_each_bucket_out_mismatch_count_1():
    # Arrange
    db_factory = lambda: _FakeDB(runs=_BUCKET_RUNS)
    # Act
    out = get_status(db_factory=db_factory, verify_run_fn=_bucket_verify)
    # Assert
    assert out["mismatch_count"] == 1


def test_get_status_counts_each_bucket_out_missing_count_1():
    # Arrange
    db_factory = lambda: _FakeDB(runs=_BUCKET_RUNS)
    # Act
    out = get_status(db_factory=db_factory, verify_run_fn=_bucket_verify)
    # Assert
    assert out["missing_count"] == 1


def test_get_status_counts_each_bucket_out_mismatched_0_session_id_m1():
    # Arrange
    db_factory = lambda: _FakeDB(runs=_BUCKET_RUNS)
    # Act
    out = get_status(db_factory=db_factory, verify_run_fn=_bucket_verify)
    # Assert
    assert out["mismatched"][0]["session_id"] == "m1"


def test_get_status_counts_each_bucket_out_mismatched_0_files_m_csv():
    # Arrange
    db_factory = lambda: _FakeDB(runs=_BUCKET_RUNS)
    # Act
    out = get_status(db_factory=db_factory, verify_run_fn=_bucket_verify)
    # Assert
    assert out["mismatched"][0]["files"] == ["/m.csv"]


def test_get_status_counts_each_bucket_out_missing_0_session_id_x1():
    # Arrange
    db_factory = lambda: _FakeDB(runs=_BUCKET_RUNS)
    # Act
    out = get_status(db_factory=db_factory, verify_run_fn=_bucket_verify)
    # Assert
    assert out["missing"][0]["session_id"] == "x1"


def test_get_status_counts_each_bucket_out_missing_0_files_x_csv():
    # Arrange
    db_factory = lambda: _FakeDB(runs=_BUCKET_RUNS)
    # Act
    out = get_status(db_factory=db_factory, verify_run_fn=_bucket_verify)
    # Assert
    assert out["missing"][0]["files"] == ["/x.csv"]


def test_get_status_handles_empty_db():
    # Arrange
    db_factory = lambda: _FakeDB(runs=[])
    # Act
    out = get_status(db_factory=db_factory)
    # Assert
    assert out == {
        "verified_count": 0,
        "mismatch_count": 0,
        "missing_count": 0,
        "mismatched": [],
        "missing": [],
    }


# ----- VerificationStatus.SUSPECT (3-colour DAG) -------------------------- #


def test_verify_chain_propagates_suspect_when_any_run_is_suspect():
    # Arrange — chain s1 → s2 where s1 is SUSPECT (locally valid, upstream
    # broken) and s2 is VERIFIED. No locally-failed runs in the chain.
    def _verify(sid: str) -> RunVerification:
        return _make_run(
            session_id=sid,
            status=(
                VerificationStatus.SUSPECT
                if sid == "s1"
                else VerificationStatus.VERIFIED
            ),
        )

    db_factory = lambda: _FakeDB(sessions_for_file=["s2"], chain=["s1", "s2"])
    # Act
    out = verify_chain("/out.csv", db_factory=db_factory, verify_run_fn=_verify)
    # Assert
    assert out.status == VerificationStatus.SUSPECT


def test_verify_chain_mismatch_outranks_suspect_in_severity():
    # Arrange — chain has both a SUSPECT run AND a MISMATCH run. MISMATCH
    # must win because the user has to fix the locally-broken run first;
    # surfacing SUSPECT here would hide the worse failure.
    def _verify(sid: str) -> RunVerification:
        if sid == "s1":
            return _make_run(session_id=sid, status=VerificationStatus.SUSPECT)
        return _make_run(session_id=sid, status=VerificationStatus.MISMATCH)

    db_factory = lambda: _FakeDB(sessions_for_file=["s2"], chain=["s1", "s2"])
    # Act
    out = verify_chain("/out.csv", db_factory=db_factory, verify_run_fn=_verify)
    # Assert
    assert out.status == VerificationStatus.MISMATCH
