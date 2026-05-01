#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PS303 smoke test for examples/01_basic_verification.py.

Asserts the example is at least syntactically valid (py_compile).
A more involved end-to-end run is intentionally avoided here so the
test stays fast and offline-safe.
"""

import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "01_basic_verification.py"


def test_example_compiles():
    assert EXAMPLE.exists(), f"missing example: {EXAMPLE}"
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(EXAMPLE)],
        check=True,
    )
