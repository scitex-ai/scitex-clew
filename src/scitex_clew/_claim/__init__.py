#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claim layer — link paper assertions to the verification chain.

Claims represent specific assertions in manuscripts (statistics, figures,
tables) that can be traced back through the verification chain to source data.

Five claim types:
  - statistic: A numerical result (p-value, effect size, etc.)
  - figure:    A figure reference linked to a recipe/image
  - table:     A table reference linked to source CSV
  - text:      A textual assertion linked to computational output
  - value:     A specific computed value (count, percentage, etc.)

This package was split out of the former single-file ``_claim.py`` (which grew
past the 512-line limit) into focused modules — ``_model`` (dataclasses +
palette + table + id), ``_register`` (add/list/format), ``_export`` (enriched
claims.json), ``_verify`` (verify_claim / verify_all_claims / dag), ``_mutate``
(remove / supersede). This ``__init__`` re-exports the full public surface so
``from scitex_clew._claim import X`` and the top-level lazy-attr map keep
resolving unchanged.
"""

from __future__ import annotations

from ._export import export_claims_json
from ._manuscript import export_manuscript_claims
from ._model import (
    CLAIM_TYPES,
    Claim,
    ClaimVerification,
    VerificationResult,
    migrate_add_claims_table,
)
from ._mutate import (
    remove_claim,
    remove_claims_by_prefix,
    supersede_claim,
    supersede_claims_by_prefix,
)
from ._register import add_claim, format_claims, list_claims
from ._verify import verify_all_claims, verify_claim, verify_claims_dag

__all__ = [
    "CLAIM_TYPES",
    "Claim",
    "ClaimVerification",
    "VerificationResult",
    "add_claim",
    "list_claims",
    "format_claims",
    "export_claims_json",
    "export_manuscript_claims",
    "verify_claim",
    "verify_all_claims",
    "verify_claims_dag",
    "migrate_add_claims_table",
    "remove_claim",
    "remove_claims_by_prefix",
    "supersede_claim",
    "supersede_claims_by_prefix",
]

# EOF
