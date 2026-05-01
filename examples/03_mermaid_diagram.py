#!/usr/bin/env python3
"""Generate a Mermaid DAG diagram via @stx.session.

Demonstrates Mermaid diagram generation:
1. Initialize bundled example data
2. Generate Mermaid code for the DAG
3. Save .mmd file under @stx.session output dir

The output can be:
- Embedded in GitHub Markdown with ```mermaid ... ```
- Rendered using mermaid-cli: `mmdc -i diagram.mmd -o diagram.png`
- Visualized with https://mermaid.live

Usage:
    python 03_mermaid_diagram.py
"""

from pathlib import Path

import scitex as stx
import scitex_clew as clew


@stx.session
def main(
    CONFIG=stx.session.INJECTED,
    logger=stx.session.INJECTED,
):
    """Run Mermaid diagram generation example."""
    OUT = Path(CONFIG.SDIR_OUT)

    logger.info("Initializing example pipeline...")
    clew.init_examples("/tmp/clew_example")

    logger.info("=== Generating Mermaid DAG Diagram ===")
    logger.info("Generating diagram from all registered claims...")

    mermaid_code = clew.mermaid(claims=True)

    if mermaid_code:
        logger.info("Mermaid Diagram Code:")
        logger.info("-" * 60)
        logger.info(mermaid_code)
        logger.info("-" * 60)

        mmd_path = OUT / "dag.mmd"
        with open(mmd_path, "w") as f:
            f.write(mermaid_code + "\n")
        logger.info(f"Diagram saved to: {mmd_path}")
        logger.info("Usage:")
        logger.info("  1. Embed in GitHub Markdown with ```mermaid ... ```")
        logger.info("  2. Render: mmdc -i dag.mmd -o dag.png")
        logger.info("  3. View online at https://mermaid.live")
    else:
        logger.info("No runs tracked yet.")
        logger.info(
            "Run '00_run_all.sh' in /tmp/clew_example to generate pipeline outputs."
        )

    return 0


if __name__ == "__main__":
    main()
