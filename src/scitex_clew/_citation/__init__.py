#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Citation layer — link manuscript ``\\cite`` keys to scholar-verified sources.

Extends clew's claim->source verification from VALUES to CITATIONS. Every
``\\cite{key}`` in a manuscript becomes a citation node linked to a real,
scholar-resolved source (DOI + metadata). A hallucinated / stub / unresolved
citation is caught automatically at compile time ("一発アウト"), mirroring the
value gate (:mod:`scitex_clew._claim`).

Division of labour (push model)
-------------------------------
- **scitex-scholar** resolves each ``\\cite`` key -> real source (DOI +
  metadata), flags stubs, and pushes the result into clew via
  :func:`add_citation`. clew never imports scholar and never re-does DOI
  resolution — it is the *ledger*, scholar is the *resolver*.
- **scitex-clew** (this package) stores citation nodes and answers
  :func:`verify_citations` — the per-key status map the compiler gates on.
- **scitex-writer** extracts USED ``\\cite`` keys at compile and calls the
  gate; any non-``verified`` key blocks the compile in a research project.

Per-key status vocabulary (the compiler's contract)
---------------------------------------------------
``verified``   scholar-registered real source (resolved, non-stub, has DOI).
``stub``       scholar stub OR the entry matches the local stub heuristic
               (note="Auto-generated stub" / journal="Pending scitex-scholar
               metadata lookup" / no DOI). The hallucination case.
``unverified`` present but not confirmed to a real source yet.
``unknown``    no clew citation node and no usable bib metadata.

These reduce onto the aggregate exit-code contract (see
:mod:`scitex_clew._cli._exit_codes`): ``verified``->OK, ``stub``->CITATION_STUB,
``unverified``->CITATION_UNRESOLVED (or HASH_MISMATCH on drift), ``unknown``->
CITATION_UNLINKED — so citations gate ``clew verify`` alongside value claims.
"""

from __future__ import annotations

from ._api import (
    add_citation,
    format_citations,
    format_verify_map,
    list_citations,
    verify_all_citations,
    verify_citations,
)
from ._model import (
    CITATION_STATUSES,
    Citation,
    migrate_add_citations_table,
)

__all__ = [
    "CITATION_STATUSES",
    "Citation",
    "add_citation",
    "list_citations",
    "verify_citations",
    "verify_all_citations",
    "format_citations",
    "format_verify_map",
    "migrate_add_citations_table",
]

# EOF
