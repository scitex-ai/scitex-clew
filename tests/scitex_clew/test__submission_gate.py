#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the submission-completeness gate (HARD 1:1 question_id↔claim_id).

Real temp DB + files (no mocks): build grounded claims exactly as the
grounded_claim_ids tests do (register a source, record a run reading it ->
output, claim on the output with an explicit claim_id, verify), then diff a
{question_id: claim_id} submission against the grounded claim_ids. The check is
non-raising; the assert form RAISES SubmissionCompletenessError on any
missing / orphan / cardinality violation.

Each test keeps a single assertion (PA-307 STX-TQ007) and AAA marker comments
(STX-TQ002); the expensive real-DB arrange is shared via fixtures.
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
    """Register a source, run reading it -> output, claim on output (helper)."""
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


@pytest.fixture
def grounded_workdir_two(tmp_path):
    """A workdir whose clew DB has TWO grounded+verified claims: c1, c2."""
    db_path = _db_path(tmp_path)
    manifest = tmp_path / ".scitex" / "clew" / "sources.json"
    with use_db(db_path):
        _make_grounded_claim(tmp_path, manifest, "c1", src_name="a.csv", out_name="a.json")
        _make_grounded_claim(tmp_path, manifest, "c2", src_name="b.csv", out_name="b.json")
        clew.verify_all_claims()
    return tmp_path


@pytest.fixture
def grounded_workdir_one(tmp_path):
    """A workdir whose clew DB has ONE grounded+verified claim: c1."""
    db_path = _db_path(tmp_path)
    manifest = tmp_path / ".scitex" / "clew" / "sources.json"
    with use_db(db_path):
        _make_grounded_claim(tmp_path, manifest, "c1", src_name="a.csv", out_name="a.json")
        clew.verify_all_claims()
    return tmp_path


@pytest.fixture
def empty_db_path(tmp_path):
    """A real, empty clew DB (exists, zero claims)."""
    db_path = _db_path(tmp_path)
    with use_db(db_path):
        pass
    return db_path


# ── all-match: strict 1:1 correspondence is OK ──


def test_all_match_result_is_ok(grounded_workdir_two):
    # Arrange
    submission = {"q1": "c1", "q2": "c2"}
    # Act
    result = check_submission_completeness(submission, workdir=grounded_workdir_two)
    # Assert
    assert result.ok is True


def test_all_match_has_no_orphan(grounded_workdir_two):
    # Arrange
    submission = {"q1": "c1", "q2": "c2"}
    # Act
    result = check_submission_completeness(submission, workdir=grounded_workdir_two)
    # Assert
    assert result.orphan == []


def test_all_match_assert_does_not_raise(grounded_workdir_two):
    # Arrange
    submission = {"q1": "c1", "q2": "c2"}
    # Act
    outcome = assert_submission_complete(submission, workdir=grounded_workdir_two)
    # Assert
    assert outcome is None


# ── missing: an answer with no grounded provenance ──


def test_missing_claim_id_flagged_in_map(grounded_workdir_one):
    # Arrange
    submission = {"q1": "c1", "q2": "not_grounded"}
    # Act
    result = check_submission_completeness(submission, workdir=grounded_workdir_one)
    # Assert
    assert result.missing == {"q2": "not_grounded"}


def test_missing_claim_id_result_not_ok(grounded_workdir_one):
    # Arrange
    submission = {"q1": "c1", "q2": "not_grounded"}
    # Act
    result = check_submission_completeness(submission, workdir=grounded_workdir_one)
    # Assert
    assert result.ok is False


def test_missing_claim_id_raises_completeness_error(grounded_workdir_one):
    # Arrange
    submission = {"q1": "c1", "q2": "not_grounded"}
    # Act
    gate = lambda: assert_submission_complete(submission, workdir=grounded_workdir_one)
    # Assert
    with pytest.raises(SubmissionCompletenessError):
        gate()


def test_missing_report_names_offending_claim(grounded_workdir_one):
    # Arrange
    submission = {"q1": "c1", "q2": "not_grounded"}
    # Act
    result = check_submission_completeness(submission, workdir=grounded_workdir_one)
    # Assert
    assert "not_grounded" in result.report()


# ── orphan: a grounded claim cited by no answer ──


def test_orphan_grounded_claim_flagged(grounded_workdir_two):
    # Arrange
    submission = {"q1": "c1"}
    # Act
    result = check_submission_completeness(submission, workdir=grounded_workdir_two)
    # Assert
    assert result.orphan == ["c2"]


def test_orphan_grounded_claim_raises_error(grounded_workdir_two):
    # Arrange
    submission = {"q1": "c1"}
    # Act
    gate = lambda: assert_submission_complete(submission, workdir=grounded_workdir_two)
    # Assert
    with pytest.raises(SubmissionCompletenessError):
        gate()


# ── cardinality: a claim cited by more than one question_id ──


def test_duplicate_claim_citation_flagged(grounded_workdir_two):
    # Arrange
    submission = {"q1": "c1", "q2": "c1"}
    # Act
    result = check_submission_completeness(submission, workdir=grounded_workdir_two)
    # Assert
    assert result.duplicate_claims == {"c1": ["q1", "q2"]}


def test_duplicate_claim_citation_raises_error(grounded_workdir_two):
    # Arrange
    submission = {"q1": "c1", "q2": "c1"}
    # Act
    gate = lambda: assert_submission_complete(submission, workdir=grounded_workdir_two)
    # Assert
    with pytest.raises(SubmissionCompletenessError):
        gate()


# ── empty submission + empty DB: trivially satisfied ──


def test_empty_submission_empty_db_ok(empty_db_path):
    # Arrange
    submission = {}
    # Act
    result = check_submission_completeness(submission, db_path=empty_db_path)
    # Assert
    assert result.ok is True


def test_empty_submission_empty_db_assert_passes(empty_db_path):
    # Arrange
    submission = {}
    # Act
    outcome = assert_submission_complete(submission, db_path=empty_db_path)
    # Assert
    assert outcome is None


# ── no DB: grounded == [] -> every cited answer is missing ──


def test_no_db_marks_all_answers_missing(tmp_path):
    # Arrange
    submission = {"q1": "c1", "q2": "c2"}
    # Act
    result = check_submission_completeness(submission, workdir=tmp_path)
    # Assert
    assert result.missing == {"q1": "c1", "q2": "c2"}


def test_no_db_leaves_no_orphan(tmp_path):
    # Arrange
    submission = {"q1": "c1", "q2": "c2"}
    # Act
    result = check_submission_completeness(submission, workdir=tmp_path)
    # Assert
    assert result.orphan == []


def test_no_db_raises_completeness_error(tmp_path):
    # Arrange
    submission = {"q1": "c1", "q2": "c2"}
    # Act
    gate = lambda: assert_submission_complete(submission, workdir=tmp_path)
    # Assert
    with pytest.raises(SubmissionCompletenessError):
        gate()


# ── public re-exports from the package root ──


def test_public_check_function_reexported(tmp_path):
    # Arrange
    expected = check_submission_completeness
    # Act
    actual = clew.check_submission_completeness
    # Assert
    assert actual is expected


def test_public_assert_function_reexported(tmp_path):
    # Arrange
    expected = assert_submission_complete
    # Act
    actual = clew.assert_submission_complete
    # Assert
    assert actual is expected


def test_public_result_type_reexported(tmp_path):
    # Arrange
    submission = {}
    # Act
    result = clew.check_submission_completeness(submission, workdir=tmp_path)
    # Assert
    assert isinstance(result, clew.SubmissionCompletenessResult)


def test_public_error_type_reexported(tmp_path):
    # Arrange
    expected = SubmissionCompletenessError
    # Act
    actual = clew.SubmissionCompletenessError
    # Assert
    assert actual is expected
