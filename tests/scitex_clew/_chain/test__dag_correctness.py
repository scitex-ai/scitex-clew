#!/usr/bin/env python3
"""Back-trace correctness of the provenance DAG — real store, real files.

Each class reproduces one defect of the claim -> DAG back-trace:

1. Parent binding by PATH (a later overwrite re-parents an earlier consumer).
2. Resolvers that disagree (rerun_dag / verify_dag_strict / dag JSON /
   mermaid each walked a different parent model).
3. A FAILED run rendered / counted as verified.
4. A claim whose lineage contains a changed upstream input passing verify.
5. Hash prefix matches accepted as verification.

No mocks: every test records real runs through ``SessionTracker`` into the
per-test PostgreSQL schema that ``tests/conftest.py`` provisions, over real
files under ``tmp_path``.
"""

from __future__ import annotations

import os
import warnings

import pytest
import scitex_clew as clew
from scitex_clew._chain import VerificationStatus, verify_chain, verify_run
from scitex_clew._chain._dag import verify_dag_strict
from scitex_clew._chain._routes import resolve_file_dag, resolve_lineage
from scitex_clew._chain._verify_ops import verify_file
from scitex_clew._claim._model import _open_store
from scitex_clew._cli import _exit_codes as codes
from scitex_clew._db import get_db
from scitex_clew._hash import hash_file, hashes_match
from scitex_clew._tracker import SessionTracker
from scitex_dev.store import ANY_REVISION


@pytest.fixture(autouse=True)
def _no_claims_export():
    prev = os.environ.get("SCITEX_CLEW_AUTO_EXPORT_CLAIMS")
    os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = "0"
    yield
    if prev is None:
        os.environ.pop("SCITEX_CLEW_AUTO_EXPORT_CLAIMS", None)
    else:
        os.environ["SCITEX_CLEW_AUTO_EXPORT_CLAIMS"] = prev


def _script(tmp_path, name):
    path = tmp_path / name
    if not path.exists():
        path.write_text(f"# {name}\n")
    return path


def _run(tmp_path, sid, script, inputs=(), outputs=None, status="success"):
    """Record one real run: load ``inputs``, write+save ``outputs``."""
    tracker = SessionTracker(sid, script_path=str(_script(tmp_path, script)))
    for path in inputs:
        tracker.record_input(path)
    for path, content in (outputs or {}).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        tracker.record_output(path)
    tracker.finalize(status=status, exit_code=0 if status == "success" else 1)
    return sid


def _claim_quietly(paper, value, source_file):
    """add_claim, silencing its expected no-lineage RuntimeWarning."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return clew.add_claim(
            str(paper), "value", 1, value, source_file=str(source_file)
        )


# ---------------------------------------------------------------------------
# 1. Parent binding is by content hash + record time, never by path alone
# ---------------------------------------------------------------------------


def _overwrite_pipeline(tmp_path):
    p = tmp_path / "data" / "p.csv"
    q = tmp_path / "data" / "q.csv"
    _run(tmp_path, "A", "make_p.py", outputs={p: "v1\n"})
    _run(tmp_path, "B", "use_p.py", inputs=[p], outputs={q: "from v1\n"})
    # A later, unrelated run overwrites p.csv with different bytes.
    _run(tmp_path, "C", "remake_p.py", outputs={p: "v2\n"})
    return p, q


class TestHashBoundParents:
    def test_overwrite_does_not_reparent_earlier_consumer(self, tmp_path):
        # Arrange
        _overwrite_pipeline(tmp_path)
        # Act
        adjacency, _ = resolve_file_dag(["B"], db=get_db())
        # Assert
        assert adjacency["B"] == ["A"]

    def test_chain_of_consumer_output_excludes_overwriter(self, tmp_path):
        # Arrange
        _, q = _overwrite_pipeline(tmp_path)
        # Act
        chain = verify_chain(q)
        # Assert
        assert [r.session_id for r in chain.runs] == ["A", "B"]

    def test_deterministic_rerun_after_consumer_is_not_the_parent(self, tmp_path):
        # Arrange — A2 re-produces byte-identical p.csv AFTER B loaded it.
        p = tmp_path / "p.csv"
        _run(tmp_path, "A", "make_p.py", outputs={p: "same\n"})
        _run(tmp_path, "B", "use_p.py", inputs=[p], outputs={tmp_path / "q": "x"})
        _run(tmp_path, "A2", "make_p.py", outputs={p: "same\n"})
        # Act
        adjacency, _ = resolve_file_dag(["B"], db=get_db())
        # Assert
        assert adjacency["B"] == ["A"]

    def test_input_matching_no_producer_hash_is_unbound(self, tmp_path):
        # Arrange — p.csv edited out of band between producer and consumer.
        p = tmp_path / "p.csv"
        _run(tmp_path, "A", "make_p.py", outputs={p: "v1\n"})
        p.write_text("hand edited\n")
        _run(tmp_path, "B", "use_p.py", inputs=[p], outputs={tmp_path / "q": "x"})
        # Act
        lineage = resolve_lineage(["B"], db=get_db())
        # Assert
        assert lineage.adjacency["B"] == []

    def test_input_matching_no_producer_hash_is_flagged_unmatched(self, tmp_path):
        # Arrange
        p = tmp_path / "p.csv"
        _run(tmp_path, "A", "make_p.py", outputs={p: "v1\n"})
        p.write_text("hand edited\n")
        _run(tmp_path, "B", "use_p.py", inputs=[p], outputs={tmp_path / "q": "x"})
        # Act
        lineage = resolve_lineage(["B"], db=get_db())
        # Assert
        assert [(u.file_path, u.reason) for u in lineage.unbound_inputs["B"]] == [
            (str(p.resolve()), "unmatched")
        ]

    def test_raw_source_is_reported_external(self, tmp_path):
        # Arrange
        raw = tmp_path / "raw.csv"
        raw.write_text("raw\n")
        _run(tmp_path, "A", "clean.py", inputs=[raw], outputs={tmp_path / "c": "c"})
        # Act
        lineage = resolve_lineage(["A"], db=get_db())
        # Assert
        assert [u.reason for u in lineage.unbound_inputs["A"]] == ["external"]

    def test_tracker_records_only_hash_bound_parent(self, tmp_path):
        # Arrange — B loads v2, which only C produced.
        p = tmp_path / "p.csv"
        _run(tmp_path, "A", "make_p.py", outputs={p: "v1\n"})
        _run(tmp_path, "C", "remake_p.py", outputs={p: "v2\n"})
        _run(tmp_path, "B", "use_p.py", inputs=[p], outputs={tmp_path / "q": "q"})
        # Act
        parents = get_db().get_parents("B")
        # Assert
        assert parents == ["C"]


# ---------------------------------------------------------------------------
# 2. One resolver behind every DAG view
# ---------------------------------------------------------------------------


def _pipeline_with_stale_stored_parent(tmp_path):
    """A -> B via p.csv; X is an unrelated run wrongly stored as B's parent."""
    p = tmp_path / "p.csv"
    q = tmp_path / "q.csv"
    x = tmp_path / "x.csv"
    _run(tmp_path, "A", "make_p.py", outputs={p: "v1\n"})
    _run(tmp_path, "X", "other.py", outputs={x: "x\n"})
    _run(tmp_path, "B", "use_p.py", inputs=[p], outputs={q: "q\n"})
    get_db().set_parent("B", "X")  # stale entry in the legacy parent tables
    return q, x


class TestSingleResolver:
    def test_rerun_dag_uses_file_resolver(self, tmp_path):
        # Arrange
        from scitex_clew._rerun import rerun_dag

        q, _ = _pipeline_with_stale_stored_parent(tmp_path)
        # Act
        dag = rerun_dag([str(q)], skip_unchanged=True)
        # Assert
        assert sorted(dag.topological_order) == ["A", "B"]

    def test_strict_claim_invalidation_uses_file_resolver(self, tmp_path):
        # Arrange — X fails, but X is NOT in q's real lineage.
        q, x = _pipeline_with_stale_stored_parent(tmp_path)
        paper = tmp_path / "paper.tex"
        paper.write_text("q\n")
        claim = _claim_quietly(paper, "q", q)
        x.write_text("tampered\n")
        # Act
        result = verify_dag_strict(targets=[str(q), str(x)])
        # Assert
        assert claim.claim_id in result["still_valid_claims"]

    def test_dag_json_by_session_uses_file_resolver(self, tmp_path):
        # Arrange
        from scitex_clew._viz._json import generate_dag_json

        _pipeline_with_stale_stored_parent(tmp_path)
        # Act
        graph = generate_dag_json(session_id="B")
        # Assert
        assert {n["session_id"] for n in graph["nodes"] if n["type"] == "script"} == {
            "A",
            "B",
        }

    def test_mermaid_by_session_excludes_stale_parent(self, tmp_path):
        # Arrange
        _pipeline_with_stale_stored_parent(tmp_path)
        # Act
        diagram = clew.mermaid(session_id="B")
        # Assert
        assert "other.py" not in diagram

    def test_mermaid_by_session_includes_real_parent(self, tmp_path):
        # Arrange
        _pipeline_with_stale_stored_parent(tmp_path)
        # Act
        diagram = clew.mermaid(session_id="B")
        # Assert
        assert "make_p.py" in diagram


# ---------------------------------------------------------------------------
# 3. A failed run is never verified
# ---------------------------------------------------------------------------


def _failed_run(tmp_path, status="failed"):
    out = tmp_path / "out.csv"
    _run(tmp_path, "F", "crashes.py", outputs={out: "partial\n"}, status=status)
    return out


class TestFailedRun:
    def test_failed_run_is_not_verified(self, tmp_path):
        # Arrange
        _failed_run(tmp_path)
        # Act
        status = verify_run("F").status
        # Assert
        assert status == VerificationStatus.FAILED

    def test_error_status_is_also_failed(self, tmp_path):
        # Arrange
        _failed_run(tmp_path, status="error")
        # Act
        status = verify_run("F").status
        # Assert
        assert status == VerificationStatus.FAILED

    def test_status_does_not_count_failed_run_as_verified(self, tmp_path):
        # Arrange
        _failed_run(tmp_path)
        # Act
        summary = clew.status()
        # Assert
        assert (summary["verified_count"], summary["failed_count"]) == (0, 1)

    def test_mermaid_does_not_draw_failed_run_verified(self, tmp_path):
        # Arrange
        _failed_run(tmp_path)
        # Act
        diagram = clew.mermaid(session_id="F")
        # Assert
        script_line = next(ln for ln in diagram.splitlines() if "crashes.py" in ln)
        assert ":::failed" in script_line and "✓" not in script_line

    def test_consumer_of_failed_run_chain_is_not_verified(self, tmp_path):
        # Arrange
        out = _failed_run(tmp_path)
        res = tmp_path / "res.csv"
        _run(tmp_path, "G", "use.py", inputs=[out], outputs={res: "r\n"})
        # Act
        chain = verify_chain(res)
        # Assert
        assert chain.status == VerificationStatus.FAILED

    def test_consumer_of_failed_run_is_suspect(self, tmp_path):
        # Arrange
        out = _failed_run(tmp_path)
        _run(tmp_path, "G", "use.py", inputs=[out], outputs={tmp_path / "r": "r"})
        # Act
        status = verify_run("G").status
        # Assert
        assert status == VerificationStatus.SUSPECT


# ---------------------------------------------------------------------------
# 4. A changed upstream input fails default claim verification
# ---------------------------------------------------------------------------


def _two_step_pipeline_with_symlinked_claim(tmp_path):
    raw = tmp_path / "data" / "raw.csv"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("a,b\n1,2\n")
    clean = tmp_path / "scripts" / "01_clean_out" / "data" / "clean.csv"
    result = tmp_path / "scripts" / "02_analyze_out" / "data" / "result.json"
    _run(tmp_path, "S1", "01_clean.py", inputs=[raw], outputs={clean: "1,2\n"})
    _run(tmp_path, "S2", "02_analyze.py", inputs=[clean], outputs={result: "3\n"})
    # symlink_from_cwd-style link: the claim names the symlink, not the file.
    link = tmp_path / "data" / "result.json"
    link.symlink_to(result)
    paper = tmp_path / "paper.tex"
    paper.write_text("value 3\n")
    _claim_quietly(paper, "3", link)
    return raw


class TestStaleLineageClaim:
    def test_intact_lineage_passes_default(self, tmp_path):
        # Arrange
        _two_step_pipeline_with_symlinked_claim(tmp_path)
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_code == codes.OK

    def test_intact_lineage_through_symlink_passes_strict(self, tmp_path):
        # Arrange
        _two_step_pipeline_with_symlinked_claim(tmp_path)
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_code == codes.OK

    def test_changed_upstream_input_fails_default(self, tmp_path):
        # Arrange
        raw = _two_step_pipeline_with_symlinked_claim(tmp_path)
        raw.write_text("a,b\n9,9\n")
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert (result.exit_code, result.verified) == (codes.STALE_LINEAGE, 0)

    def test_changed_upstream_input_is_not_no_lineage_in_strict(self, tmp_path):
        # Arrange
        raw = _two_step_pipeline_with_symlinked_claim(tmp_path)
        raw.write_text("a,b\n9,9\n")
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_name == "STALE_LINEAGE"

    def test_verify_claim_reports_stale_chain_status(self, tmp_path):
        # Arrange
        raw = _two_step_pipeline_with_symlinked_claim(tmp_path)
        raw.write_text("a,b\n9,9\n")
        (claim,) = clew.list_claims()
        # Act
        result = clew.verify_claim(claim.claim_id)
        # Assert
        assert result["chain_status"] == VerificationStatus.SUSPECT.value

    def test_verify_claim_intact_lineage_is_verified(self, tmp_path):
        # Arrange
        _two_step_pipeline_with_symlinked_claim(tmp_path)
        (claim,) = clew.list_claims()
        # Act
        result = clew.verify_claim(claim.claim_id)
        # Assert
        assert result["claim"]["status"] == "verified"

    def test_hand_written_leaf_still_no_lineage_in_strict(self, tmp_path):
        # Arrange
        src = tmp_path / "results.json"
        src.write_text("{}\n")
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        _claim_quietly(paper, "x", src)
        # Act
        result = clew.verify_all_claims(strict=True)
        # Assert
        assert result.exit_code == codes.NO_LINEAGE

    def test_hand_written_leaf_still_ok_by_default(self, tmp_path):
        # Arrange
        src = tmp_path / "results.json"
        src.write_text("{}\n")
        paper = tmp_path / "paper.tex"
        paper.write_text("x\n")
        _claim_quietly(paper, "x", src)
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_code == codes.OK


# ---------------------------------------------------------------------------
# 5. Full hash equality
# ---------------------------------------------------------------------------


class TestFullHashEquality:
    def test_short_prefix_is_a_mismatch(self, tmp_path):
        # Arrange
        f = tmp_path / "f.txt"
        f.write_text("content\n")
        # Act
        fv = verify_file(f, hash_file(f)[:8])
        # Assert
        assert fv.status == VerificationStatus.MISMATCH

    def test_full_hash_verifies(self, tmp_path):
        # Arrange
        f = tmp_path / "f.txt"
        f.write_text("content\n")
        # Act
        fv = verify_file(f, hash_file(f))
        # Assert
        assert fv.status == VerificationStatus.VERIFIED

    def test_legacy_32_char_truncation_still_verifies(self, tmp_path):
        # Arrange
        f = tmp_path / "f.txt"
        f.write_text("content\n")
        # Act
        fv = verify_file(f, hash_file(f)[:32])
        # Assert
        assert fv.status == VerificationStatus.VERIFIED

    def test_empty_recorded_hash_never_matches(self):
        # Arrange
        recorded, current = "", "abc"
        # Act
        matched = hashes_match(recorded, current)
        # Assert
        assert matched is False

    def test_claim_with_prefix_source_hash_is_mismatch(self, tmp_path):
        # Arrange — rewrite the claim's stored source hash to a 6-char prefix.
        out = tmp_path / "out.json"
        _run(tmp_path, "P", "make.py", outputs={out: "1\n"})
        paper = tmp_path / "paper.tex"
        paper.write_text("1\n")
        claim = _claim_quietly(paper, "1", out)
        store = _open_store()
        try:
            store.put(
                {"claim_id": claim.claim_id, "source_hash": hash_file(out)[:6]},
                expected_revision=ANY_REVISION,
            )
        finally:
            store.close()
        # Act
        result = clew.verify_all_claims()
        # Assert
        assert result.exit_code == codes.HASH_MISMATCH


# EOF
