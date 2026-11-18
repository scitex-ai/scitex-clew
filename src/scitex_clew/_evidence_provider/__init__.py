#!/usr/bin/env python3
"""clew as an evidence provider (contract ``scitex-live-paper.evidence-report`` 1.1.0).

Coupling is only through the published, provider-neutral contract: clew does
not import scitex-live-paper, and scitex-live-paper does not import clew. It
discovers :class:`EvidenceEntry` through the ``scitex.livepaper.renderers``
entry-point group (``port = "evidence"``, ``name = "clew"``)::

    [project.entry-points."scitex.livepaper.renderers"]
    clew = "scitex_clew._evidence_provider:EvidenceEntry"

Out of process, ``clew export-evidence --out report.json`` writes the same
report as a file.

The schema this package implements is vendored, version-pinned, as
``evidence-report.schema.1.1.0.json`` (copied verbatim from scitex-live-paper's
``src/scitex_live_paper/evidence/evidence-report.schema.json``, schema
``$id`` ``.../evidence-report/1.1.0``). Bump it only together with
:data:`SCHEMA_VERSION`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ._report import (
    PROVIDER_NAME,
    SCHEMA_ID,
    SCHEMA_VERSION,
    build_evidence_graph,
    build_evidence_report,
)
from ._states import OUTCOME_STATES, STATES, classify_outcome

__all__ = [
    "OUTCOME_STATES",
    "PROVIDER_NAME",
    "SCHEMA_ID",
    "SCHEMA_PATH",
    "SCHEMA_VERSION",
    "STATES",
    "EvidenceAdapter",
    "EvidenceEntry",
    "build_evidence_graph",
    "build_evidence_report",
    "classify_outcome",
    "load_schema",
]

#: The vendored, version-pinned contract schema.
SCHEMA_PATH = Path(__file__).with_name(f"evidence-report.schema.{SCHEMA_VERSION}.json")


def load_schema() -> dict:
    """The vendored evidence-report JSON Schema (draft 2020-12)."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class EvidenceAdapter:
    """The ``evidence`` port: an evidence report and on-demand graphs."""

    def evidence_report(
        self,
        project_root: str,
        claim_ids: Sequence[str] | None,
        options: Mapping[str, Any],
    ) -> dict:
        return build_evidence_report(project_root, claim_ids, options)

    def evidence_graph(
        self, project_root: str, claim_id: str, options: Mapping[str, Any]
    ) -> dict | None:
        return build_evidence_graph(project_root, claim_id, options)


class EvidenceEntry:
    """Entry-point object for the ``scitex.livepaper.renderers`` group."""

    port = "evidence"
    name = PROVIDER_NAME
    adapter = EvidenceAdapter()


# EOF
