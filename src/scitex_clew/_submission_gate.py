#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Submission-completeness gate — the HARD 1:1 question_id↔claim_id assertion.

A consumer submits a mapping of ``question_id -> claim_id`` (one answer per
question). This module asserts a STRICT 1:1 correspondence (a bijection) between
the submission's cited claim_ids and clew's GROUNDED claim_ids:

- **missing**  — a submitted answer whose ``claim_id`` is NOT grounded (an
  answer with no grounded provenance).
- **orphan**   — a grounded ``claim_id`` cited by NO submission answer (a
  grounded claim the submission failed to cite).
- **cardinality** — a ``claim_id`` cited by more than one ``question_id`` (the
  correspondence must be exactly 1:1). A ``question_id`` mapping to more than one
  ``claim_id`` is structurally impossible for a ``Mapping`` (keys are unique), so
  that direction is guaranteed by construction.

Grounding is NOT reimplemented here — it reuses :func:`grounded_claim_ids` (the
pure primitive in :mod:`scitex_clew._grounded`). This module only computes the
submission↔grounded diff and, in :func:`assert_submission_complete`, RAISES on
any discrepancy (the load-bearing "must raise" gate the operator asked for; the
soft ``logger.warning`` predecessor lives in ``_observers/_session.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Union

from ._grounded import grounded_claim_ids


class SubmissionCompletenessError(ValueError):
    """Raised by :func:`assert_submission_complete` when the gate fails.

    Subclasses :class:`ValueError` (clew has no dedicated gate/verify exception
    base). The message is the :meth:`SubmissionCompletenessResult.report`
    human-readable summary of every discrepancy.
    """


@dataclass(frozen=True)
class SubmissionCompletenessResult:
    """Non-raising result of :func:`check_submission_completeness`.

    Attributes
    ----------
    ok : bool
        ``True`` iff the submission is a strict 1:1 bijection with the grounded
        claim_ids (no missing, no orphan, no duplicate-claim citations).
    missing : dict[str, str]
        ``question_id -> claim_id`` for answers whose claim_id is NOT grounded.
    orphan : list[str]
        Sorted grounded claim_ids cited by no submission answer.
    duplicate_claims : dict[str, list[str]]
        ``claim_id -> sorted[question_id, ...]`` for any claim_id cited by more
        than one question_id (cardinality violation).
    grounded : list[str]
        The sorted grounded claim_ids the check ran against (for reporting).
    """

    ok: bool
    missing: Dict[str, str] = field(default_factory=dict)
    orphan: List[str] = field(default_factory=list)
    duplicate_claims: Dict[str, List[str]] = field(default_factory=dict)
    grounded: List[str] = field(default_factory=list)

    def report(self) -> str:
        """Return a human-readable summary of the gate outcome."""
        if self.ok:
            return (
                "submission-completeness OK: strict 1:1 correspondence between "
                f"{len(self.grounded)} grounded claim(s) and the submission's answers."
            )
        lines: List[str] = [
            "submission-completeness FAILED — the submission is not a strict 1:1 "
            "correspondence with clew's grounded claims:",
        ]
        if self.missing:
            lines.append(
                f"  missing ({len(self.missing)}): answer(s) with no grounded provenance —"
            )
            for qid in sorted(self.missing):
                lines.append(f"    question_id={qid!r} -> claim_id={self.missing[qid]!r} (not grounded)")
        if self.orphan:
            lines.append(
                f"  orphan ({len(self.orphan)}): grounded claim(s) cited by no answer —"
            )
            for cid in self.orphan:
                lines.append(f"    claim_id={cid!r}")
        if self.duplicate_claims:
            lines.append(
                f"  cardinality ({len(self.duplicate_claims)}): claim(s) cited by "
                "more than one question_id —"
            )
            for cid in sorted(self.duplicate_claims):
                qids = ", ".join(repr(q) for q in self.duplicate_claims[cid])
                lines.append(f"    claim_id={cid!r} <- question_ids=[{qids}]")
        return "\n".join(lines)


def check_submission_completeness(
    submission: Mapping[str, str],
    *,
    workdir: Optional[Union[str, Path]] = None,
    db_path: Optional[Union[str, Path]] = None,
    sources_path: Optional[Union[str, Path]] = None,
) -> SubmissionCompletenessResult:
    """Compute the submission↔grounded diff WITHOUT raising.

    Parameters
    ----------
    submission : Mapping[str, str]
        ``question_id -> claim_id`` (one answer per question).
    workdir, db_path, sources_path
        Passed straight through to :func:`grounded_claim_ids` to locate the DB
        and sources manifest.

    Returns
    -------
    SubmissionCompletenessResult
        With ``.ok``, ``.missing``, ``.orphan``, ``.duplicate_claims``, and a
        ``.report()`` summary. An empty submission is OK iff there are also zero
        grounded claims; a missing DB yields ``grounded == []`` (so every cited
        answer is ``missing`` and there are no orphans).
    """
    grounded = grounded_claim_ids(
        workdir, db_path=db_path, sources_path=sources_path
    )
    grounded_set = set(grounded)

    # Reverse map: claim_id -> [question_id, ...] that cite it.
    cid_to_qids: Dict[str, List[str]] = {}
    for qid, cid in submission.items():
        cid_to_qids.setdefault(cid, []).append(qid)

    missing = {
        qid: cid for qid, cid in submission.items() if cid not in grounded_set
    }
    cited = set(submission.values())
    orphan = sorted(grounded_set - cited)
    duplicate_claims = {
        cid: sorted(qids)
        for cid, qids in cid_to_qids.items()
        if len(qids) > 1
    }

    ok = not missing and not orphan and not duplicate_claims
    return SubmissionCompletenessResult(
        ok=ok,
        missing=missing,
        orphan=orphan,
        duplicate_claims=duplicate_claims,
        grounded=grounded,
    )


def assert_submission_complete(
    submission: Mapping[str, str],
    *,
    workdir: Optional[Union[str, Path]] = None,
    db_path: Optional[Union[str, Path]] = None,
    sources_path: Optional[Union[str, Path]] = None,
) -> None:
    """HARD gate: RAISE :class:`SubmissionCompletenessError` unless strictly 1:1.

    Calls :func:`check_submission_completeness` and, if the result is not
    ``ok``, raises with the ``.report()`` message. Returns ``None`` on success.
    This is the "must raise, not just warn" behavior the operator required.
    """
    result = check_submission_completeness(
        submission,
        workdir=workdir,
        db_path=db_path,
        sources_path=sources_path,
    )
    if not result.ok:
        raise SubmissionCompletenessError(result.report())


# EOF
