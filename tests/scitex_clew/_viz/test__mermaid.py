#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for render_dag format handling (:mod:`scitex_clew._viz._mermaid`).

Covers the error raised for an output suffix render_dag cannot write.

Per PA-307 §3: AAA markers + one assertion per test.
"""

from __future__ import annotations

import pytest

from scitex_clew._viz._mermaid import render_dag


class TestRenderDagUnsupportedFormat:
    def test_unknown_ext_still_generic_error(self, tmp_path):
        # Arrange
        out = tmp_path / "dag.xyz"
        # Act
        # Assert
        with pytest.raises(ValueError, match="Unsupported format"):
            render_dag(str(out), claims=True)


# EOF
