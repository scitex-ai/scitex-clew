#!/usr/bin/env python3
"""Basic verification example - verify a session run.

Demonstrates the simplest usage of scitex-clew via @stx.session:
1. Initialize bundled example data
2. Query the verification status
3. List tracked runs

Usage:
    python 01_basic_verification.py
"""

from pathlib import Path

import scitex as stx
import scitex_clew as clew


@stx.session
def main(
    CONFIG=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    """Run basic verification example."""
    OUT = Path(CONFIG.SDIR_OUT)

    logger.info("Initializing example pipeline...")
    examples = clew.init_examples("/tmp/clew_example")
    logger.info(f"  Copied to: {examples['path']}")
    logger.info(f"  Files: {examples['file_count']}")

    logger.info("=== Verification Status ===")
    status = clew.status()
    logger.info(f"Total runs: {status.get('total_runs', 0)}")
    logger.info(f"Verified runs: {status.get('verified_runs', 0)}")
    logger.info(f"Failed runs: {status.get('failed_runs', 0)}")

    logger.info("=== Recent Runs (limit=5) ===")
    runs = clew.list_runs(limit=5)
    if runs:
        for run in runs:
            session_id = run["session_id"]
            script_path = run.get("script_path", "unknown")
            run_status = run.get("status", "unknown")
            logger.info(f"  {session_id}: {script_path} [{run_status}]")
    else:
        logger.info("  No runs tracked yet.")
        logger.info(
            "  Run '00_run_all.sh' in the examples directory to generate pipeline outputs."
        )

    logger.info("=== Database Statistics ===")
    stats = clew.stats()
    logger.info(f"Total sessions: {stats.get('total_runs', 0)}")
    logger.info(f"Total files: {stats.get('total_files', 0)}")
    logger.info(f"Database location: {stats.get('db_path', 'unknown')}")

    report_path = OUT / "status_report.txt"
    with open(report_path, "w") as f:
        f.write("=== Verification Status ===\n")
        f.write(f"Total runs: {status.get('total_runs', 0)}\n")
        f.write(f"Verified runs: {status.get('verified_runs', 0)}\n")
        f.write(f"Failed runs: {status.get('failed_runs', 0)}\n")
    logger.info(f"Report saved to: {report_path}")

    return 0


if __name__ == "__main__":
    main()
