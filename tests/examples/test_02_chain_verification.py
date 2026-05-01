#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PS303 smoke test for examples/02_chain_verification.py.

Asserts the example is at least syntactically valid (py_compile).
"""

import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "02_chain_verification.py"


def test_example_compiles():
    assert EXAMPLE.exists(), f"missing example: {EXAMPLE}"
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(EXAMPLE)],
        check=True,
    )
