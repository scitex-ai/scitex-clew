---
description: |
  [TOPIC] clew CLI Reference
  [DETAILS] Top-level subcommands of the `clew` CLI — status, list, verify, stats, mermaid, mcp, skills.
tags: [scitex-clew-cli-reference]
---

# CLI Reference

`clew` is the entry point installed by `pip install scitex-clew`.

## Subcommands

| Command                | Purpose                                            |
|------------------------|----------------------------------------------------|
| `clew status`          | Git-status-like overview of verification state     |
| `clew list`            | List tracked runs (filter by status)               |
| `clew verify <SESSION>`| Re-hash a session's files and compare              |
| `clew chain <PATH>`    | Trace provenance chain for a target file           |
| `clew dag`             | Verify the full DAG (or claims-DAG)                |
| `clew rerun <TARGET>`  | Re-execute and compare outputs                     |
| `clew mermaid`         | Generate a Mermaid diagram of the DAG              |
| `clew stats`           | Show verification database statistics              |
| `clew mcp start`       | Start the MCP server (stdio) for AI agents         |
| `clew skills list`     | List embedded skill pages                          |
| `clew skills get <ID>` | Retrieve one skill page                            |

## Examples

```bash
clew status
clew list --status drift
clew verify 20261103_120000_abc12345
clew chain results/figure_3.png
clew dag --claims
clew mcp start                  # speak MCP/stdio for an AI agent
```

See [11_cli-commands.md](11_cli-commands.md) for extended option-level details
and [10_common-workflows.md](10_common-workflows.md) for end-to-end recipes.
