"""Tests for ``scitex_clew._chain._chain_ops`` (verify_chain, get_status).

The chain ops drive a real DB plus on-disk file hashing. To keep
tests deterministic we monkeypatch:

  - `get_db` (used inside both `_chain_ops` and `_verify_ops`) →
    `_FakeDB` with scripted return values.
  - `verify_run` (used inside `_chain_ops.verify_chain` /
    `_chain_ops.get_status`) → returns canned `RunVerification`s
    so the chain status logic can be exercised without disk hashing.
"""

from __future__ import annotations

from typing import Any


from scitex_clew._chain import _chain_ops
from scitex_clew._chain._chain_ops import get_status, verify_chain
from scitex_clew._chain._types import (
    ChainVerification,
    RunVerification,
    VerificationStatus,
)


class _FakeDB:
    """Stand-in for `VerificationDB` exposing only what chain_ops calls."""

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

    def find_session_by_file(self, target: str, role: str = "output") -> list[str]:
        return list(self._sessions_for_file)

    def get_chain(self, session_id: str) -> list[str]:
        return list(self._chain)

    def list_runs(self, *, limit: int = 1000) -> list[dict[str, Any]]:
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


# ----- verify_chain -------------------------------------------------------- #


def test_verify_chain_returns_unknown_when_target_has_no_session(monkeypatch):
    monkeypatch.setattr(_chain_ops, "get_db", lambda: _FakeDB())
    out = verify_chain("/some/output.csv")
    assert isinstance(out, ChainVerification)
    assert out.status == VerificationStatus.UNKNOWN
    assert out.runs == []


def test_verify_chain_all_verified_propagates_verified_status(monkeypatch):
    monkeypatch.setattr(
        _chain_ops,
        "get_db",
        lambda: _FakeDB(sessions_for_file=["s2"], chain=["s1", "s2"]),
    )
    monkeypatch.setattr(_chain_ops, "verify_run", lambda sid: _make_run(session_id=sid))
    out = verify_chain("/out.csv")
    assert out.status == VerificationStatus.VERIFIED
    assert [r.session_id for r in out.runs] == ["s1", "s2"]
    assert out.is_verified


def test_verify_chain_propagates_mismatch_when_any_run_mismatched(monkeypatch):
    monkeypatch.setattr(
        _chain_ops,
        "get_db",
        lambda: _FakeDB(sessions_for_file=["s2"], chain=["s1", "s2"]),
    )

    def _verify(sid: str) -> RunVerification:
        return _make_run(
            session_id=sid,
            status=(
                VerificationStatus.MISMATCH
                if sid == "s1"
                else VerificationStatus.VERIFIED
            ),
        )

    monkeypatch.setattr(_chain_ops, "verify_run", _verify)
    out = verify_chain("/out.csv")
    assert out.status == VerificationStatus.MISMATCH


def test_verify_chain_propagates_missing_when_no_mismatch_but_missing(monkeypatch):
    monkeypatch.setattr(
        _chain_ops,
        "get_db",
        lambda: _FakeDB(sessions_for_file=["s1"], chain=["s1"]),
    )
    monkeypatch.setattr(
        _chain_ops,
        "verify_run",
        lambda sid: _make_run(status=VerificationStatus.MISSING),
    )
    out = verify_chain("/out.csv")
    assert out.status == VerificationStatus.MISSING


def test_verify_chain_unknown_when_runs_have_no_explicit_status(monkeypatch):
    """All runs UNKNOWN → chain UNKNOWN (not VERIFIED, MISMATCH, MISSING)."""
    monkeypatch.setattr(
        _chain_ops,
        "get_db",
        lambda: _FakeDB(sessions_for_file=["s1"], chain=["s1"]),
    )
    monkeypatch.setattr(
        _chain_ops,
        "verify_run",
        lambda sid: _make_run(status=VerificationStatus.UNKNOWN),
    )
    out = verify_chain("/out.csv")
    assert out.status == VerificationStatus.UNKNOWN


def test_verify_chain_target_path_is_resolved(monkeypatch, tmp_path):
    """Relative target paths are resolved via Path(...).resolve()."""
    captured = {}

    class _Capture(_FakeDB):
        def find_session_by_file(self, target, role="output"):
            captured["arg"] = target
            return []

    monkeypatch.setattr(_chain_ops, "get_db", lambda: _Capture())
    f = tmp_path / "result.csv"
    f.write_text("x")
    verify_chain(str(f))
    assert captured["arg"] == str(f.resolve())


# ----- get_status ---------------------------------------------------------- #


def test_get_status_counts_each_bucket(monkeypatch):
    runs_meta = [{"session_id": "v1"}, {"session_id": "m1"}, {"session_id": "x1"}]
    monkeypatch.setattr(_chain_ops, "get_db", lambda: _FakeDB(runs=runs_meta))

    def _verify(sid):
        if sid == "v1":
            return _make_run(session_id=sid, status=VerificationStatus.VERIFIED)
        if sid == "m1":
            from scitex_clew._chain._types import FileVerification

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
        # missing-files run
        from scitex_clew._chain._types import FileVerification

        missing = FileVerification(
            path="/x.csv",
            role="output",
            expected_hash="00",
            current_hash=None,
            status=VerificationStatus.MISSING,
        )
        return _make_run(
            session_id=sid, status=VerificationStatus.MISSING, files=[missing]
        )

    monkeypatch.setattr(_chain_ops, "verify_run", _verify)
    out = get_status()

    assert out["verified_count"] == 1
    assert out["mismatch_count"] == 1
    assert out["missing_count"] == 1
    assert out["mismatched"][0]["session_id"] == "m1"
    assert out["mismatched"][0]["files"] == ["/m.csv"]
    assert out["missing"][0]["session_id"] == "x1"
    assert out["missing"][0]["files"] == ["/x.csv"]


def test_get_status_handles_empty_db(monkeypatch):
    monkeypatch.setattr(_chain_ops, "get_db", lambda: _FakeDB(runs=[]))
    out = get_status()
    assert out == {
        "verified_count": 0,
        "mismatch_count": 0,
        "missing_count": 0,
        "mismatched": [],
        "missing": [],
    }
