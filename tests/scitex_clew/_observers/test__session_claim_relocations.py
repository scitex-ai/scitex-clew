#!/usr/bin/env python3
"""Claims registered DURING a session move with its run dir at close (#191).

A ``@session`` script saves into its own run dir (``RUNNING/<ID>/x.json``) and
registers a claim on it before the session closes; the session manager then
moves the dir to ``FINISHED_<STATUS>/<ID>`` and reports ``relocations``. The
claim must follow the move, or ``verify`` says SOURCE_MISSING and its slice
has no producing run. Real directory moves, the real hooks, the real claims
store on a real PostgreSQL. No mocks.
"""

from __future__ import annotations

import os
import uuid
import warnings

import pytest
import scitex_clew as clew
from scitex_clew._chain._slice import build_slice
from scitex_clew._claim._model import _resolve_claim
from scitex_clew._claim._verify import verify_all_claims
from scitex_clew._cli._exit_codes import NAMES, OK, SOURCE_MISSING, STALE_LINEAGE
from scitex_clew._observers._session import on_session_close, on_session_start
from scitex_clew._tracker import get_tracker, set_tracker


@pytest.fixture(autouse=True)
def _clean():
    set_tracker(None)
    yield
    set_tracker(None)


@pytest.fixture
def project(tmp_path):
    root = (tmp_path / "proj").resolve()
    (root / "script_out" / "RUNNING" / "ID-1").mkdir(parents=True)
    (root / "script.py").write_text("print(1)\n")
    return root


def _session(project, status):
    """Start, save into the run dir, claim on it mid-session, move, close."""
    running = project / "script_out" / "RUNNING" / "ID-1"
    final = project / "script_out" / f"FINISHED_{status.upper()}" / "ID-1"
    sid = f"claimreloc_{uuid.uuid4().hex[:10]}"
    on_session_start(
        sid,
        script_path=str(project / "script.py"),
        metadata={"project_root": str(project), "sdir_run": str(running)},
    )
    (running / "x.json").write_text('{"auc": 0.91}')
    get_tracker().record_output(running / "x.json")
    claim = clew.add_claim(
        str(project / "paper.tex"),
        "value",
        1,
        "0.91",
        source_file=str(running / "x.json"),
        claim_id=f"c_{sid}",
    )
    final.parent.mkdir(parents=True, exist_ok=True)
    os.rename(running, final)
    on_session_close(
        status=status,
        exit_code=0 if status == "success" else 1,
        metadata={"relocations": [{"from": str(running), "to": str(final)}]},
    )
    return sid, claim.claim_id, final


class TestClaimsFollowTheRunDir:
    def test_source_file_is_rewritten_to_the_final_path(self, project):
        # Arrange
        _sid, cid, final = _session(project, "success")
        # Act
        claim = _resolve_claim(cid, None)
        # Assert
        assert claim.source_file == str(final / "x.json")

    def test_success_claim_verifies_after_close(self, project):
        # Arrange
        _session(project, "success")
        # Act
        result = verify_all_claims(strict=True)
        # Assert
        assert (result.exit_code, [c.outcome for c in result.claims]) == (
            OK,
            ["OK"],
        )

    def test_success_claim_slice_has_its_producing_run(self, project):
        # Arrange
        sid, cid, _final = _session(project, "success")
        # Act
        sl = build_slice([cid])
        # Assert
        assert (sl.runs, sl.unproduced_targets) == ([sid], [])

    def test_failed_run_claim_is_stale_not_source_missing(self, project):
        # Arrange: the source moved to FINISHED_ERROR; it exists, but the run
        # that produced it failed, so the claim must not verify
        _sid, cid, final = _session(project, "error")
        # Act
        result = verify_all_claims(strict=True)
        # Assert
        assert (
            _resolve_claim(cid, None).source_file,
            os.path.isfile(final / "x.json"),
            [c.outcome for c in result.claims],
        ) == (str(final / "x.json"), True, [NAMES[STALE_LINEAGE]])

    def test_claim_outside_the_run_dir_is_untouched(self, project):
        # Arrange
        other = project / "table.csv"
        other.write_text("a\n1\n")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            before = clew.add_claim(
                str(project / "paper.tex"), "value", 2, "1", source_file=str(other)
            )
        # Act
        _session(project, "success")
        # Assert
        assert _resolve_claim(before.claim_id, None).source_file == str(other)

    def test_unbound_claim_is_bound_to_the_session_that_recorded_its_bytes(
        self, project
    ):
        # Arrange: claimed BEFORE the run recorded the file (no producer yet)
        running = project / "script_out" / "RUNNING" / "ID-1"
        final = project / "script_out" / "FINISHED_SUCCESS" / "ID-1"
        sid = f"claimreloc_{uuid.uuid4().hex[:10]}"
        on_session_start(
            sid,
            script_path=str(project / "script.py"),
            metadata={"project_root": str(project), "sdir_run": str(running)},
        )
        (running / "y.json").write_text('{"n": 3}')
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            claim = clew.add_claim(
                str(project / "paper.tex"),
                "value",
                3,
                "3",
                source_file=str(running / "y.json"),
            )
        get_tracker().record_output(running / "y.json")
        final.parent.mkdir(parents=True, exist_ok=True)
        os.rename(running, final)
        # Act
        on_session_close(
            metadata={"relocations": [{"from": str(running), "to": str(final)}]}
        )
        # Assert
        after = _resolve_claim(claim.claim_id, None)
        assert (claim.source_session, after.source_session, after.source_file) == (
            None,
            sid,
            str(final / "y.json"),
        )

    def test_without_relocation_the_claim_would_be_source_missing(self, project):
        # Arrange: the 0.24.2 behaviour, reproduced by moving the dir WITHOUT
        # reporting it — the guard that this suite tests the real failure
        running = project / "script_out" / "RUNNING" / "ID-1"
        final = project / "script_out" / "FINISHED_SUCCESS" / "ID-1"
        sid = f"claimreloc_{uuid.uuid4().hex[:10]}"
        on_session_start(
            sid,
            script_path=str(project / "script.py"),
            metadata={"project_root": str(project), "sdir_run": str(running)},
        )
        (running / "x.json").write_text("{}")
        get_tracker().record_output(running / "x.json")
        clew.add_claim(
            str(project / "paper.tex"),
            "value",
            1,
            "x",
            source_file=str(running / "x.json"),
        )
        final.parent.mkdir(parents=True, exist_ok=True)
        os.rename(running, final)
        on_session_close()
        # Act
        result = verify_all_claims(strict=True)
        # Assert
        assert result.exit_code == SOURCE_MISSING




# EOF
