#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the submission-completeness gate (HARD 1:1 question_id↔claim_id).

Real temp DB + files (no mocks): build grounded claims exactly as the
grounded_claim_ids tests do (register a source, record a run reading it ->
output, claim on the output with an explicit claim_id, verify), then diff a
{question_id: claim_id} submission against the grounded claim_ids. The check is
non-raising; the assert form RAISES SubmissionCompletenessError on any
missing / orphan / cardinality violation.
"""

import pytest

import scitex_clew as clew
from scitex_clew._db import use_db
from scitex_clew._sources._writer import register_source
from scitex_clew._submission_gate import (
    SubmissionCompletenessError,
    assert_submission_complete,
    check_submission_completeness,
)


def _db_path(tmp_path):
    p = tmp_path / ".scitex" / "clew" / "runtime" / "db.sqlite"
    p.parent.mkdir(parents=True)
    return p


def _make_grounded_claim(tmp_path, manifest, claim_id, *, src_name, out_name):
    """Register a source, run reading it -> output, claim on output, verify."""
    src = tmp_path / src_name
    src.write_text(f"x\n1  # {claim_id}\n")
    out = tmp_path / out_name
    out.write_text(f'{{"n": 1, "cid": "{claim_id}"}}\n')
    register_source([src], sources_path=manifest, root=tmp_path)
    with clew.session() as run:
        run.record_input(src)
        run.record_output(out)
    clew.add_claim(
        "paper.tex", "value", 1, "1", source_file=str(out), claim_id=claim_id
    )


def test_all_match_is_ok(tmp_path):
    # Arrange — two grounded claims, submission cites both, 1:1.
    db_path = _db_path(tmp_path)
    manifest = tmp_path / ".scitex" / "clew" / "sources.json"
    with use_db(db_path):
        _make_grounded_claim(tmp_path, manifest, "c1", src_name="a.csv", out_name="a.json")
        _make_grounded_claim(tmp_path, manifest, "c2", src_name="b.csv", out_name="b.json")
        clew.verify_all_claims()

    submission = {"q1": "c1", "q2": "c2"}
    # Act
    result = check_submission_completeness(submission, workdir=tmp_path)
    # Assert
    assert result.ok is True
    assert result.missing == {}
    assert result.orphan == []
    assert result.duplicate_claims == {}
    # The hard gate does not raise.
    assert_submission_complete(submission, workdir=tmp_path)


def test_missing_raises(tmp_path):
    # Arrange — one grounded claim, but an answer cites a claim_id that is NOT
    # grounded -> missing.
    db_path = _db_path(tmp_path)
    manifest = tmp_path / ".scitex" / "clew" / "sources.json"
    with use_db(db_path):
        _make_grounded_claim(tmp_path, manifest, "c1", src_name="a.csv", out_name="a.json")
        clew.verify_all_claims()

    submission = {"q1": "c1", "q2": "not_grounded"}
    # Act
    result = check_submission_completeness(submission, workdir=tmp_path)
    # Assert
    assert result.ok is False
    assert result.missing == {"q2": "not_grounded"}
    # orphan-free: c1 IS cited.
    assert result.orphan == []
    with pytest.raises(SubmissionCompletenessError) as exc:
        assert_submission_complete(submission, workdir=tmp_path)
    assert "missing" in str(exc.value)
    assert "not_grounded" in str(exc.value)


def test_orphan_raises(tmp_path):
    # Arrange — two grounded claims, submission cites only one -> the other is
    # an orphan.
    db_path = _db_path(tmp_path)
    manifest = tmp_path / ".scitex" / "clew" / "sources.json"
    with use_db(db_path):
        _make_grounded_claim(tmp_path, manifest, "c1", src_name="a.csv", out_name="a.json")
        _make_grounded_claim(tmp_path, manifest, "c2", src_name="b.csv", out_name="b.json")
        clew.verify_all_claims()

    submission = {"q1": "c1"}
    # Act
    result = check_submission_completeness(submission, workdir=tmp_path)
    # Assert
    assert result.ok is False
    assert result.missing == {}
    assert result.orphan == ["c2"]
    with pytest.raises(SubmissionCompletenessError) as exc:
        assert_submission_complete(submission, workdir=tmp_path)
    assert "orphan" in str(exc.value)
    assert "c2" in str(exc.value)


def test_duplicate_claim_cardinality_raises(tmp_path):
    # Arrange — two grounded claims, but TWO questions cite the SAME claim_id
    # (and thus the other grounded claim becomes an orphan too). The 1:1
    # bijection is violated.
    db_path = _db_path(tmp_path)
    manifest = tmp_path / ".scitex" / "clew" / "sources.json"
    with use_db(db_path):
        _make_grounded_claim(tmp_path, manifest, "c1", src_name="a.csv", out_name="a.json")
        _make_grounded_claim(tmp_path, manifest, "c2", src_name="b.csv", out_name="b.json")
        clew.verify_all_claims()

    submission = {"q1": "c1", "q2": "c1"}
    # Act
    result = check_submission_completeness(submission, workdir=tmp_path)
    # Assert — c1 cited twice = cardinality violation.
    assert result.ok is False
    assert result.duplicate_claims == {"c1": ["q1", "q2"]}
    with pytest.raises(SubmissionCompletenessError) as exc:
        assert_submission_complete(submission, workdir=tmp_path)
    assert "cardinality" in str(exc.value)


def test_empty_submission_and_empty_db_is_ok(tmp_path):
    # Arrange — a real (empty) DB and an empty submission. Zero grounded claims
    # and zero answers is a trivially-satisfied 1:1 correspondence.
    db_path = _db_path(tmp_path)
    with use_db(db_path):
        pass  # DB exists, no claims.

    # Act
    result = check_submission_completeness({}, db_path=db_path)
    # Assert
    assert result.ok is True
    assert result.grounded == []
    assert_submission_complete({}, db_path=db_path)


def test_no_db_grounded_empty_all_answers_missing(tmp_path):
    # Arrange — a workdir with NO clew DB -> grounded == []. A non-empty
    # submission therefore has every cited answer as missing, and no orphans.
    submission = {"q1": "c1", "q2": "c2"}
    # Act
    result = check_submission_completeness(submission, workdir=tmp_path)
    # Assert
    assert result.ok is False
    assert result.missing == {"q1": "c1", "q2": "c2"}
    assert result.orphan == []
    assert result.duplicate_claims == {}
    with pytest.raises(SubmissionCompletenessError):
        assert_submission_complete(submission, workdir=tmp_path)


def test_public_api_reexports(tmp_path):
    # The public names are re-exported from the package root (lazy __getattr__).
    assert clew.check_submission_completeness is check_submission_completeness
    assert clew.assert_submission_complete is assert_submission_complete
    assert clew.SubmissionCompletenessError is SubmissionCompletenessError
    result = clew.check_submission_completeness({}, workdir=tmp_path)
    assert isinstance(result, clew.SubmissionCompletenessResult)
