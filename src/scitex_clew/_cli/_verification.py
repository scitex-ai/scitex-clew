#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verification CLI subcommands — thin orchestrator.

Commands are implemented in focused sub-modules:
  _verification_core.py    status, list-runs, verify, show-stats
  _verification_dag.py     dag, chain, rerun-dag, rerun-claims
  _verification_mermaid.py print-mermaid (with DAG-slicing options)

This module re-exports everything so that ``_main.py`` imports remain
unchanged.
"""

from __future__ import annotations

from ._verification_core import (
    _echo_verify_all_human,
    _run_status_to_exit_code,
    list_runs,
    stats,
    status,
    verify,
)
from ._verification_dag import (
    _dag_payload,
    _echo_dag_human,
    chain,
    dag,
    rerun_claims,
    rerun_dag,
)
from ._verification_mermaid import (
    _GROUPER_REGISTRY_NAMES,
    mermaid,
)

__all__ = [
    # core
    "status",
    "list_runs",
    "verify",
    "stats",
    # dag
    "dag",
    "chain",
    "rerun_dag",
    "rerun_claims",
    # mermaid
    "mermaid",
    # helpers (used by other modules / tests)
    "_dag_payload",
    "_echo_dag_human",
    "_echo_verify_all_human",
    "_run_status_to_exit_code",
    "_GROUPER_REGISTRY_NAMES",
]

# EOF
