#!/usr/bin/env python3
"""Build a ``scitex-live-paper.evidence-report`` from clew's own records.

Per registered claim of the project at ``project_root``:

* the verdict of ``clew verify --strict`` (:func:`verify_all_claims` with
  ``strict=True``), mapped to a contract state by :mod:`._states`;
* the claim record (manuscript location, stated text and value, source file
  and locator) from :func:`list_claims`;
* the minimal evidence graph: the claim's level-1 slice
  (:func:`build_slice`), converted by :mod:`._graph`, with the nodes where
  verification failed marked ``failure`` (contract 1.1.0) by
  :mod:`._failures`. A claim clew cannot slice (no source file) gets
  ``graph: null`` and a ``graph_error``.

Every clew call runs inside a :func:`project_root` block, so the project
scope resolves from ``project_root`` and not from the working directory.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .._claim._model import AUTHOR_INTERPRETATION
from ._failures import mark_failures
from ._graph import relative_to_root, slice_to_graph
from ._states import classify_outcome

__all__ = [
    "PROVIDER_NAME",
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "build_evidence_graph",
    "build_evidence_report",
]

#: Contract implemented (the vendored schema in this package pins it).
SCHEMA_ID = "scitex-live-paper.evidence-report"
SCHEMA_VERSION = "1.2.0"
PROVIDER_NAME = "clew"
#: Slice level of the evidence graph: path-pruned (clew's default).
SLICE_LEVEL = 1
_CLAIM_LIMIT = 10_000


def _root(project_root: str | Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"clew project root is not a directory: {root}")
    return root


def _version() -> str | None:
    from .. import __version__

    return __version__


def _claim_graph(
    claim_id: str,
    root: Path,
    *,
    outcome: str,
    reason: str,
    details: list[str],
    source_file: str | None,
    evidence_relation: str = "direct",
) -> dict:
    from .._chain._slice import build_slice
    from .._db import get_db

    db = get_db()
    graph = slice_to_graph(
        build_slice([claim_id], level=SLICE_LEVEL, db=db),
        claim_id,
        root,
        run_lookup=db.get_run,
        evidence_relation=evidence_relation,
    )
    return mark_failures(
        graph,
        outcome=outcome,
        reason=reason,
        details=details,
        source_file=source_file,
        root=root,
    )


def _source_block(record, source_file: str | None, root: Path) -> dict:
    """The contract's ``source``: file, locator and (1.2.0) the value read there.

    ``value`` is what the source holds NOW at the claim's declared locator: a
    scalar for a whole-value locator (``"."``), else ``{field: value}`` for
    the fields that could be read. It is omitted when the claim declares no
    locator or nothing could be read; the reason a read failed is already in
    ``details`` (clew's own value check reports it).
    """
    locator = record.source_keys if record else None
    block: dict[str, Any] = {
        "file": relative_to_root(source_file, root),
        "locator": locator,
    }
    if not (locator and source_file):
        return block
    from .._claim._locator import WHOLE_VALUE, SourceLocatorError, read_source_value

    found: dict[str, Any] = {}
    for field, spec in locator.items():
        try:
            found[field] = read_source_value(Path(source_file), spec)
        except (SourceLocatorError, OSError, ValueError):
            continue
    if set(found) == {WHOLE_VALUE}:
        block["value"] = found[WHOLE_VALUE]
    elif found:
        block["value"] = found
    return block


def _entry(row, record, root: Path, with_graph: bool) -> dict:
    details = [str(d) for d in (row.details or [])]
    state, reason, status = classify_outcome(row.outcome, details)
    manuscript = record.file_path if record else None
    line = record.line_number if record else None
    label = None
    if manuscript:
        label = Path(manuscript).name + (f":L{line}" if line else "")
    source_file = (record.source_file if record else None) or row.source_file
    entry: dict[str, Any] = {
        "claim_id": row.claim_id,
        "location": {
            "file": relative_to_root(manuscript, root),
            "line": line or None,
            "label": label or row.location,
        },
        "claim_type": record.claim_type if record else None,
        "stated_text": (record.claim_value if record else None) or row.claim_value,
        "stated_value": record.checked_value if record else row.claim_value,
        "state": state,
        "reason": reason,
        "source": _source_block(record, source_file, root),
        "details": details,
        "provider_status": status,
    }
    if record and record.evidence_relation == AUTHOR_INTERPRETATION:
        entry["evidence_relation"] = AUTHOR_INTERPRETATION
        if state == "supported":
            entry["reason"] = "Recorded trace verified for the result linked to this author interpretation"
    if not with_graph:
        return entry  # key omitted: the consumer asks evidence_graph on demand
    if not source_file:
        entry["graph"] = None
        entry["graph_error"] = "the claim has no source file, so it has no slice"
        return entry
    try:
        entry["graph"] = _claim_graph(
            row.claim_id,
            root,
            outcome=row.outcome,
            reason=reason,
            details=details,
            source_file=source_file,
            evidence_relation=record.evidence_relation if record else "direct",
        )
    except Exception as exc:  # noqa: BLE001 - surfaced per claim as graph_error
        entry["graph"] = None
        entry["graph_error"] = f"clew could not slice the claim: {exc}"
    return entry


def build_evidence_report(
    project_root: str | Path,
    claim_ids: Iterable[str] | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict:
    """The evidence report for the registered claims at ``project_root``.

    Parameters
    ----------
    project_root
        The clew project (the directory its claims were registered in).
    claim_ids
        Only these registered claims; ``None`` means every claim. An id clew
        does not hold is not a registered claim and is not reported.
    options
        ``with_graphs`` (bool, default True): False omits each ``graph`` key,
        so a consumer fetches graphs through :func:`build_evidence_graph`.
        Other keys are a consumer's own and are ignored.

    Verification is always strict: ``supported`` requires the source to have
    a recorded computation behind it, which non-strict verify does not check.
    """
    from .._claim import list_claims, verify_all_claims
    from .._db._paths import project_root as project_root_cm

    root = _root(project_root)
    with_graphs = bool((options or {}).get("with_graphs", True))
    wanted = set(claim_ids) if claim_ids is not None else None
    with project_root_cm(root):
        result = verify_all_claims(strict=True)
        records = {c.claim_id: c for c in list_claims(limit=_CLAIM_LIMIT)}
        claims = [
            _entry(row, records.get(row.claim_id), root, with_graphs)
            for row in result.claims
            if wanted is None or row.claim_id in wanted
        ]
    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "provider": {"name": PROVIDER_NAME, "version": _version()},
        "project_root": str(root),
        "claims": claims,
    }


def build_evidence_graph(
    project_root: str | Path,
    claim_id: str,
    options: Mapping[str, Any] | None = None,
) -> dict | None:
    """One claim's evidence graph; ``None`` when it has no source to slice.

    Raises :class:`KeyError` when ``claim_id`` is not a registered claim.
    """
    del options  # no graph options yet; the slice level is fixed at 1
    from .._claim import list_claims, verify_all_claims
    from .._db._paths import project_root as project_root_cm

    root = _root(project_root)
    with project_root_cm(root):
        records = {c.claim_id: c for c in list_claims(limit=_CLAIM_LIMIT)}
        if claim_id not in records:
            raise KeyError(f"{claim_id!r} is not a registered clew claim")
        record = records[claim_id]
        if not record.source_file:
            return None
        # The same strict verdict the report uses, so the failing nodes of an
        # on-demand graph equal the report's (scoped to this claim's file).
        result = verify_all_claims(file_path=record.file_path, strict=True)
        row = next(r for r in result.claims if r.claim_id == claim_id)
        details = [str(d) for d in (row.details or [])]
        _state, reason, _status = classify_outcome(row.outcome, details)
        return _claim_graph(
            claim_id,
            root,
            outcome=row.outcome,
            reason=reason,
            details=details,
            source_file=record.source_file or row.source_file,
            evidence_relation=record.evidence_relation,
        )


# EOF
