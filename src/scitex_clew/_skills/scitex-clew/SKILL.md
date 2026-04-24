---
description: Hash-based reproducibility verification for scientific pipelines — SHA-256 fingerprints every input/output file, builds a provenance DAG, and rechecks hashes on demand (git-status-like). Use whenever the user asks to "verify a run", "check if results are reproducible", "did this pipeline change?", "trace where this figure came from", "audit the DAG", "rerun the whole pipeline and compare", "register a manuscript claim", "link a figure to its source session", "stamp a file's provenance", or "show the Mermaid DAG of my experiments". Drop-in replacement for ad-hoc `md5sum` logs, `dvc status`, Snakemake hash tracking, and manual "did I rerun this?" checks. Zero-dependency pure-stdlib; auto-integrates with `@stx.session` and `stx.io.save/load`.
allowed-tools: mcp__scitex__clew_*
primary_interface: cli
interfaces:
  python: 2
  cli: 3
  mcp: 2
  skills: 2
  hook: 0
  http: 0
---

# scitex-clew

> **Interfaces:** Python ⭐⭐ · CLI ⭐⭐⭐ (primary) · MCP ⭐⭐ · Skills ⭐⭐ · Hook — · HTTP —

Hash-based verification tracking for reproducible science. Zero dependencies (pure stdlib + sqlite3). Auto-integrates with `@stx.session` and `stx.io` when scitex is present.

## Installation & import (two equivalent paths)

The same module is reachable via two install paths. Both forms work at
runtime; which one a user has depends on their install choice.

```python
# Standalone — pip install scitex-clew
import scitex_clew
scitex_clew.status(...)

# Umbrella — pip install scitex
import scitex.clew
scitex.clew.status(...)
```

`pip install scitex-clew` alone does NOT expose the `scitex` namespace;
`import scitex.clew` raises `ModuleNotFoundError`. To use the
`scitex.clew` form, also `pip install scitex`.

See [../../general/02_interface-python-api.md] for the ecosystem-wide
rule and empirical verification table.

## Sub-skills

### Core
* [01_quick-start.md](01_quick-start.md) — Basic API, session tracking, first verification
* [02_grouping.md](02_grouping.md) — Collapse related files into DAG nodes with Merkle roots

### Workflows
* [10_common-workflows.md](10_common-workflows.md) — Claims, DAG patterns, stamps, reproducibility
* [11_cli-commands.md](11_cli-commands.md) — CLI reference (`clew status`, `clew verify`, etc.)
* [12_mcp-tools-for-ai-agents.md](12_mcp-tools-for-ai-agents.md) — MCP tool reference for AI agents

## MCP Tools

| Tool | Purpose |
|------|---------|
| `clew_status` | Git-status-like overview of verification state |
| `clew_list` | List all tracked runs with verification status |
| `clew_run` | Verify a session by checking all file hashes |
| `clew_chain` | Trace provenance chain for a target file |
| `clew_dag` | Verify full DAG for multiple targets or claims |
| `clew_mermaid` | Generate Mermaid diagram for verification DAG |
| `clew_rerun_dag` | Re-execute entire DAG and compare outputs |
| `clew_rerun_claims` | Re-execute sessions backing manuscript claims |
| `clew_stats` | Show verification database statistics |

## CLI

```bash
clew status              # Git-status-like overview
clew list                # List tracked runs
clew verify <SESSION_ID> # Verify a specific run
clew stats               # Database statistics
clew mermaid             # Generate Mermaid DAG diagram
clew mcp start           # Start MCP server
clew skills list         # List skill pages
clew skills get SKILL    # Get a specific skill page
```


## Environment

- [13_env-vars.md](13_env-vars.md) — SCITEX_* env vars read by scitex-clew at runtime
