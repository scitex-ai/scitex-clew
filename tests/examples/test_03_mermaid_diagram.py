#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PS303 smoke test for examples/03_mermaid_diagram.py.

Asserts the example is at least syntactically valid (py_compile).
"""

import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "03_mermaid_diagram.py"


def test_example_compiles_example_exists():
    # Arrange
    # Act
    # Assert
    # Arrange
    # Act
    # Assert
    assert EXAMPLE.exists(), f"missing example: {EXAMPLE}"
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(EXAMPLE)],
        check=True,
    )
