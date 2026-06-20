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
| `clew verify`                 | Verify EVERY registered claim; fail-loud exit code |
| `clew verify <SESSION>`       | Re-hash one session's files and compare (fail-loud)|
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

## `clew verify` — fail-loud exit codes (the DONE gate)

`clew verify` runs in two modes:

- **`clew verify`** (no argument) — claim-set mode. Re-verifies **every**
  registered claim and exits with a nuanced, documented code. This is the
  command an AI solver MUST run before signalling DONE.
- **`clew verify <SESSION>`** — single-run mode. Re-hashes one session's
  files; now also fail-loud (nonzero exit when the run does not verify).

Add `--strict` (claim-set mode) to additionally require that each claim's
source has upstream `@stx.session` lineage — this rejects a hand-written
leaf (e.g. a hand-edited `results.json`) even when its hash matches.

Per-pattern **severity** is configurable: each outcome can be `error` (fails
the run), `warning` (reported, tolerated, exit `0`), or `ignore`, via
`verify.severity` in `.scitex/clew/config.yaml` (user- and project-level; see
[20_env-vars.md](20_env-vars.md#config-files-scitexclew)). Pass an explicit
file/dir with `clew verify --config PATH`. Defaults: every pattern is `error`
except `no_lineage` (`warning`, which `--strict` promotes to `error`).

| Exit | Name             | Meaning                                                          |
|------|------------------|------------------------------------------------------------------|
| `0`  | `OK`             | every claim is source-verified (strict: + has `@stx.session` lineage) |
| `10` | `UNVERIFIED`     | claim(s) registered but never verified (the fabrication case)    |
| `11` | `SOURCE_MISSING` | a claim's source file is gone                                    |
| `12` | `HASH_MISMATCH`  | a claim's source changed since registration                      |
| `13` | `NO_LINEAGE`     | `--strict` only: source is a hand-written leaf, no computation   |
| `20` | `NO_CLAIMS`      | nothing registered — nothing to verify                           |

When several `error`-severity classes co-occur, the single returned code is
the highest-severity one (tamper/missing > unverified > no-lineage > empty);
`warning`/`ignore` patterns never set the exit code (they surface under
`warnings` in `--json`).
`DONE` is legitimate **only on exit `0`**; on any nonzero exit the agent
must abstain honestly (`null` + reason) instead of claiming success. The
codes are stable constants in `scitex_clew._cli._exit_codes` and are also
exposed as `exit_code` / `exit_name` / `counts` in `--json` output and via
the `clew.verify_all_claims(...)` Python API.

## Examples

```bash
clew status
clew list-runs --status success --limit 10
clew verify                                # verify all claims; gate DONE on $?
clew verify --strict --json                # + require @stx.session lineage
clew verify --config .scitex/clew/config.yaml   # tune per-pattern severity
clew verify 20261103_120000_abc12345       # verify one run (fail-loud)
clew chain results/figure_3.png
clew dag --claims
clew rerun-dag --target results/figure_3.png --timeout 600
clew claim register-intermediate --name n_sig_pathways --value 42 \
    --supports chronic_r2_min_pvals --supports reactome_v2024
clew mcp start                  # MCP over stdio for an AI agent
```

See [11_cli-commands.md](11_cli-commands.md) for extended option-level details
and [10_common-workflows.md](10_common-workflows.md) for end-to-end recipes.
