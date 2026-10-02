#!/usr/bin/env python3
# Timestamp: "2026-02-01 (ywatanabe)"
# File: /home/ywatanabe/proj/scitex-python/src/scitex/verify/_viz/_utils.py
"""Utility functions for verification visualization."""

from __future__ import annotations

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
    from scitex_logging import getPlainConsole

    plain = getPlainConsole(__name__)
    verified = 0
    mismatched = 0
    missing = 0

    plain.emit(f"\n{Colors.BOLD}Verification Summary{Colors.RESET}")
    plain.emit("=" * 50)

    for run in runs:
        v = verify_run(run["session_id"])
        if v.status == VerificationStatus.VERIFIED:
            verified += 1
            if show_all:
                plain.emit(format_run_detailed(v))
        elif v.status == VerificationStatus.MISMATCH:
            mismatched += 1
            plain.emit(format_run_detailed(v))
        else:
            missing += 1
            plain.emit(format_run_detailed(v))

    plain.emit("")
    plain.emit(f"{Colors.GREEN}●{Colors.RESET} Verified:  {verified}")
    plain.emit(f"{Colors.RED}●{Colors.RESET} Mismatch:  {mismatched}")
    plain.emit(f"{Colors.YELLOW}○{Colors.RESET} Missing:   {missing}")
    plain.emit("")


# EOF
