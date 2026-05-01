#!/usr/bin/env python3
"""Chain verification - trace provenance of a file via @stx.session.

Demonstrates dependency chain tracing:
1. Initialize bundled example data
2. Verify the full dependency DAG
3. Print chain details

Usage:
    python 02_chain_verification.py
"""

from pathlib import Path

import scitex as stx
import scitex_clew as clew


@stx.session
def main(
    CONFIG=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    """Run chain verification example."""
    OUT = Path(CONFIG.SDIR_OUT)

    logger.info("Initializing example pipeline...")
    clew.init_examples("/tmp/clew_example")

    logger.info("=== Chain Verification ===")
    logger.info("Verifying the full dependency DAG...")

    result = clew.dag(claims=True)

    logger.info("DAG Verification Result:")
    logger.info(
        f"  Overall Status: {result.status.value if hasattr(result, 'status') else 'unknown'}"
    )
    logger.info(
        f"  Is Verified: {result.is_verified if hasattr(result, 'is_verified') else 'unknown'}"
    )

    if hasattr(result, "runs") and result.runs:
        logger.info(f"  Total Runs: {len(result.runs)}")
        for run in result.runs:
            badge = "✓" if run.is_verified else "✗"
            session_id = run.session_id[:12]
            logger.info(f"    {badge} {session_id}")
    else:
        logger.info("  No runs tracked yet.")
        logger.info(
            "  Run '00_run_all.sh' in /tmp/clew_example to generate pipeline outputs."
        )

    if hasattr(result, "edges") and result.edges:
        logger.info(f"  Total Dependencies: {len(result.edges)}")
    else:
        logger.info("  No dependencies tracked yet.")

    report_path = OUT / "chain_report.txt"
    with open(report_path, "w") as f:
        f.write(
            f"DAG Status: {result.status.value if hasattr(result, 'status') else 'unknown'}\n"
        )
        f.write(
            f"Verified: {result.is_verified if hasattr(result, 'is_verified') else 'unknown'}\n"
        )
    logger.info(f"Report saved to: {report_path}")

    return 0


if __name__ == "__main__":
    main()
