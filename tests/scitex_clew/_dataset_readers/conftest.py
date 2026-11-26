"""Reuse the evidence provider's REAL clew project (sessions read data/*.csv).

The same module-scoped PostgreSQL schema and project build as
``tests/scitex_clew/_evidence_provider/conftest.py``: two real ``@session``
runs of ``scripts/compute.py`` read ``data/input.csv`` and
``data/input2.csv``, which is exactly the "which scripts read this dataset"
question the dataset provenance contract asks.
"""

from __future__ import annotations

from tests.scitex_clew._evidence_provider.conftest import (  # noqa: F401
    clew_project,
    isolated_store,
    journal_dir,
)
