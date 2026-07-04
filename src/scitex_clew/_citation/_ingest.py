#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Citation artifact ingestion — the scholar↔clew decoupled seam.

Operator's loose-coupling / acyclic decision (2026-07-02): scitex-scholar stays
clew-agnostic. Instead of scholar calling ``clew.add_citation`` (a scholar→clew
import), scholar saves a ``citation_status.json`` artifact via ``stx.io.save``;
clew's io post-save observer (:func:`scitex_clew._observers.on_io_save`)
recognizes the artifact by its schema marker and ingests it here. The
``add_citation`` push thus becomes a clew-internal detail — scholar imports
nothing from clew, deps stay acyclic.

Ingest contract (clew owns it — clew parses the artifact)::

    {
      "schema": "scitex-clew/citations/v1",   # REQUIRED marker
      "citations": [
        {
          "cite_key": "Berens2009CircStat",   # REQUIRED (only required field)
          "doi": "10.18637/jss.v031.i10",      # optional
          "source_id": "scholar:berens2009",   # optional
          "resolved": true,                     # optional (default True)
          "is_stub": false,                     # optional (default False)
          "url": null,                          # optional (no-DOI CorpusId case)
          "manuscript_file": "paper.tex",       # optional
          "line_number": 42,                    # optional
          "metadata": {"author": "…", "year": "2009", ...}  # optional
        }
      ]
    }

Ingestion is idempotent (``cite_key`` is UNIQUE → upsert) and INDEPENDENT of an
active ``@stx.session`` (citations are a manuscript-level ledger, unlike file
provenance which records into the current run's DAG).
"""

from __future__ import annotations

from typing import Any

# Schema-marker prefix by which the io observer recognizes a citation artifact.
CITATION_ARTIFACT_SCHEMA_PREFIX = "scitex-clew/citations"


def is_citation_artifact(obj: Any) -> bool:
    """True if ``obj`` is a citation artifact (dict carrying the schema marker)."""
    return isinstance(obj, dict) and str(obj.get("schema", "")).startswith(
        CITATION_ARTIFACT_SCHEMA_PREFIX
    )


def ingest_citations_artifact(obj: Any) -> int:
    """Ingest a citation artifact dict into the citation ledger.

    Parameters
    ----------
    obj : Any
        The saved object. Only a dict carrying a ``"schema"`` that starts with
        ``"scitex-clew/citations"`` is treated as a citation artifact; anything
        else returns 0 (no-op) so the observer can pass every io-save through
        cheaply.

    Returns
    -------
    int
        Number of citation entries ingested (0 if not a citation artifact or no
        valid entries).
    """
    if not is_citation_artifact(obj):
        return 0

    from ._api import add_citation

    entries = obj.get("citations") or []
    count = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        cite_key = entry.get("cite_key")
        if not cite_key or not str(cite_key).strip():
            continue
        add_citation(
            cite_key,
            manuscript_file=entry.get("manuscript_file"),
            line_number=entry.get("line_number"),
            doi=entry.get("doi"),
            source_id=entry.get("source_id"),
            metadata=entry.get("metadata"),
            url=entry.get("url"),
            is_stub=bool(entry.get("is_stub", False)),
            resolved=bool(entry.get("resolved", True)),
        )
        count += 1
    return count


# EOF
