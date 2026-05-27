---
description: |
  [TOPIC] clew CLI Reference
  [DETAILS] Top-level subcommands of the `clew` CLI — status, list-runs, verify, chain, dag, rerun-dag, rerun-claims, show-stats, print-mermaid, claim, mcp, skills.
tags: [scitex-clew-cli-reference]
---

# CLI Reference

`clew` is the entry point installed by `pip install scitex-clew[cli]`.

## Subcommands

| Command                       | Purpose                                            |
|-------------------------------|----------------------------------------------------|
| `clew status`                 | Git-status-like overview of verification state     |
| `clew list-runs`              | List tracked runs (filter by status)               |
| `clew verify <SESSION>`       | Re-hash a session's files and compare              |
| `clew chain <PATH>`           | Trace + verify the provenance chain for a file     |
| `clew dag`                    | Verify the full DAG (or claims-DAG), hash-only     |
| `clew rerun-dag`              | Re-execute the DAG in a sandbox and compare        |
| `clew rerun-claims`           | Re-execute every claim-backing session and compare |
| `clew print-mermaid`          | Generate a Mermaid diagram of the DAG              |
| `clew show-stats`             | Show verification database statistics              |
| `clew claim <add\|list\|verify\|register-intermediate>` | Manuscript-claim operations |
| `clew mcp start`              | Start the MCP server (stdio) for AI agents         |
| `clew skills <list\|get>`     | List / retrieve embedded skill pages               |

Every command accepts `--json` for machine-parsable output (also accepted at
the top level, e.g. `clew --json status`).

## Hash-only vs. re-execution

- `chain` / `dag` re-hash recorded files — fast, the default check.
- `rerun-dag` / `rerun-claims` actually re-execute scripts in a sandbox and
  compare outputs (slow, the gold-standard reproducibility check). Originals
  are never overwritten.

## Examples

```bash
clew status
clew list-runs --status success --limit 10
clew verify 20261103_120000_abc12345
clew chain results/figure_3.png
clew dag --claims
clew rerun-dag --target results/figure_3.png --timeout 600
clew claim register-intermediate --name n_sig_pathways --value 42 \
    --supports chronic_r2_min_pvals --supports reactome_v2024
clew mcp start                  # MCP over stdio for an AI agent
```

See [11_cli-commands.md](11_cli-commands.md) for extended option-level details
and [10_common-workflows.md](10_common-workflows.md) for end-to-end recipes.
