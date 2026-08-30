# SciTeX Clew Examples

This directory contains simple, standalone examples demonstrating the `scitex-clew` package API.

The `scitex-clew` package provides **hash-based reproducibility verification** for scientific pipelines:
- Track session runs and file outputs
- Verify that outputs haven't been modified
- Re-execute scripts in sandboxes to confirm reproducibility
- Visualize dependency DAGs

## Quick Start

### 1. Run Basic Verification Example

```bash
python 01_basic_verification.py
```

This initializes the bundled example data and shows:
- Overall verification status
- List of tracked runs
- Database statistics

### 2. Run Chain Verification Example

```bash
python 02_chain_verification.py
```

This demonstrates dependency chain tracing:
- Verifies the full DAG
- Shows which sessions produced outputs
- Displays verification status of each step

### 3. Generate Mermaid Diagram

```bash
python 03_mermaid_diagram.py
```

This generates a Mermaid flowchart of the dependency DAG:
- Can be embedded in Markdown files
- Render to PNG/SVG with mermaid-cli
- Visualize on https://mermaid.live

## What Each Example Does

### `01_basic_verification.py`

Minimal example showing:
- `clew.init_examples()` - copy bundled example scripts
- `clew.status()` - get git-status-like overview
- `clew.list_runs()` - list tracked session runs
- `clew.stats()` - database statistics

**Output**: Terminal summary of verification status.

### `02_chain_verification.py`

Dependency tracing example showing:
- `clew.dag()` - verify complete dependency DAG
- Inspection of runs and edges
- Verification badges (✓ = verified, ✗ = failed)

**Output**: List of sessions in the DAG with their verification status.

### `03_mermaid_diagram.py`

Visualization example showing:
- `clew.mermaid()` - generate Mermaid diagram code
- Embedding in Markdown
- Rendering to PNG/SVG with mermaid-cli

**Output**: Mermaid flowchart code (can be embedded in docs).

## Prerequisites

These examples work with any version of the `scitex-clew` package:

```bash
pip install scitex-clew
```

Or with optional dependencies:

```bash
pip install scitex-clew[cli,mcp,docs]
```

## Running with Real Data

The examples use bundled example data from `/src/scitex_clew/_example_data/`.

To generate outputs and populate the verification database:

```bash
# Initialize examples in a working directory
python 01_basic_verification.py   # Copies example scripts to /tmp/clew_example

# Run the pipeline
cd /tmp/clew_example
./00_run_all.sh                    # Execute all scripts and record outputs

# Then re-run the verification examples to see actual data
cd /path/to/examples
python 02_chain_verification.py    # Now shows real runs
python 03_mermaid_diagram.py       # Now shows real DAG
```

## Bundled Example Data

The package includes a complete example pipeline (`_example_data/`):

```
01_source_a.py       →  source_A.csv
02_preprocess_a.py   →  clean_A.csv
                        ↘
03_source_b.py       →  source_B.csv      ↘
04_preprocess_b.py   →  clean_B.csv   →  07_merge.py  →  final.csv  →  08_analyze.py
                        ↗              →  final.csv
05_source_c.py       →  source_C.csv
06_preprocess_c.py   →  clean_C.csv
```

Each script records:
- Session ID (timestamp + hash)
- Input files loaded
- Output files saved
- SHA256 hashes of all files

## API Overview

All examples use the public API from `scitex_clew`:

```python
import scitex_clew as clew

# Verification
clew.status()                      # Git-status-like overview
clew.list_runs(limit=100)          # List tracked runs
clew.run(session_id)               # Verify a specific run
clew.chain(target_file)            # Trace file → source chain
clew.dag(targets)                  # Verify full DAG
clew.rerun(target)                 # Re-execute & compare (sandbox)
clew.stats()                       # Database statistics

# Visualization
clew.mermaid(claims=True)          # Generate Mermaid DAG diagram

# Examples
clew.init_examples(dest)           # Copy bundled examples
```

See the individual example scripts for detailed comments.

## Further Reading

- **scitex-clew Documentation**: https://scitex-clew.readthedocs.io
- **GitHub Repository**: https://github.com/ywatanabe1989/scitex-clew
- **Mermaid Syntax**: https://mermaid.js.org/syntax/flowchart.html

## Notes

- Examples initialize data in `/tmp/clew_example` by default
- Database is stored in `~/.scitex/clew/` (configurable via environment)
- Provenance is recorded in the per-host PostgreSQL store (`host_store()`)
- When used with scitex, integration is automatic via `@stx.session` + `stx.io`
