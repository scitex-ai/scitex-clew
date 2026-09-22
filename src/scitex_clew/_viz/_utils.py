#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/verify/_viz/_utils.py
"""Utility functions for verification visualization."""

from __future__ import annotations

import sys
from typing import Any, Dict, List

from .._chain import VerificationStatus, verify_run
from ._colors import Colors
from ._format import format_run_detailed


def print_verification_summary(
    runs: List[Dict[str, Any]],
    show_all: bool = False,
) -> None:
    """
    Print a summary of verification status to stdout.

    Parameters
    ----------
    runs : list of dict
        List of run records
    show_all : bool
        Show all runs (not just problematic ones)
    """
    verified = 0
    mismatched = 0
    missing = 0

    # PS-220: library code must not use print() — this summary is the
    # function's stdout data contract (tested via capsys), so it stays on
    # stdout through sys.stdout.write (the serializer-free data-transport
    # surface the auditor recognizes), byte-identical to before.
    sys.stdout.write(f"\n{Colors.BOLD}Verification Summary{Colors.RESET}\n")
    sys.stdout.write("=" * 50 + "\n")

    for run in runs:
        v = verify_run(run["session_id"])
        if v.status == VerificationStatus.VERIFIED:
            verified += 1
            if show_all:
                sys.stdout.write(format_run_detailed(v) + "\n")
        elif v.status == VerificationStatus.MISMATCH:
            mismatched += 1
            sys.stdout.write(format_run_detailed(v) + "\n")
        else:
            missing += 1
            sys.stdout.write(format_run_detailed(v) + "\n")

    sys.stdout.write("\n")
    sys.stdout.write(f"{Colors.GREEN}●{Colors.RESET} Verified:  {verified}\n")
    sys.stdout.write(f"{Colors.RED}●{Colors.RESET} Mismatch:  {mismatched}\n")
    sys.stdout.write(f"{Colors.YELLOW}○{Colors.RESET} Missing:   {missing}\n")
    sys.stdout.write("\n")


# EOF
