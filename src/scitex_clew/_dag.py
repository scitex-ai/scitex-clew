#!/usr/bin/env python3
# Timestamp: "2026-05-05 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/clew/_dag.py
"""Multi-target DAG verification — delegates to _chain._dag.

F2 — strict-mode failure attribution is exposed via ``verify_dag_strict``.
"""

from ._chain._dag import (
    _topological_sort,
    verify_dag,
    verify_dag_strict,
)

__all__ = ["_topological_sort", "verify_dag", "verify_dag_strict"]

# EOF
