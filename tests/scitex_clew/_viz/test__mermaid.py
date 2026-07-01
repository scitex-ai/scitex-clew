#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for render_dag format handling (:mod:`scitex_clew._viz._mermaid`).

Covers the targeted error when a caller mistakenly passes the clew STORE path
(.sqlite/.db) as the render OUTPUT target (reported by paper-scitex-clew
dogfooding: a launcher used the old to_svg(db, out) signature).

Per PA-307 §3: AAA markers + one assertion per test.
"""

from __future__ import annotations

import pytest

from scitex_clew._viz._mermaid import render_dag


class TestRenderDagStoreAsTarget:
    def test_sqlite_output_raises_store_not_target(self, tmp_path):
        # Arrange
        out = tmp_path / ".scitex" / "clew" / "db.sqlite"
        # Act
        # Assert
        with pytest.raises(ValueError, match="store, not a render target"):
            render_dag(str(out), claims=True)

    def test_db_output_raises_store_not_target(self, tmp_path):
        # Arrange
        out = tmp_path / "store.db"
        # Act
        # Assert
        with pytest.raises(ValueError, match="store, not a render target"):
            render_dag(str(out), claims=True)

    def test_unknown_ext_still_generic_error(self, tmp_path):
        # Arrange
        out = tmp_path / "dag.xyz"
        # Act
        # Assert
        with pytest.raises(ValueError, match="Unsupported format"):
            render_dag(str(out), claims=True)


# EOF
