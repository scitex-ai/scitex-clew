---
name: scitex-clew
description: |
  [WHAT] Hash-based reproducibility verification for scientific pipelines — SHA-256 fingerprints every input/output file, builds a provenance DAG, and rechecks hashes on demand (git-status-like).
  [WHEN] Use whenever the user asks to "verify a run", "check if results are reproducible", "did this pipeline change?", "trace where this figure came from", "audit the DAG", "rerun the whole pipeline and compare", "register a manuscript claim", "link a figure to its source session", "stamp a file's provenance", or "show the Mermaid DAG of my experiments".
  [HOW] Drop-in replacement for ad-hoc `md5sum` logs, `dvc status`, Snakemake hash tracking, and manual "did I rerun this?" checks. Zero-dependency pure-stdlib; auto-integrates with `@stx.session` and `stx.io.save/load`.
tags: [scitex-clew]
allowed-tools: mcp__scitex__clew_*
primary_interface: cli
interfaces:
  python: 2
  cli: 3
  mcp: 2
  skills: 2
  http: 0
---

# scitex-clew

Hash-based verification tracking for reproducible science. Zero dependencies (pure stdlib + sqlite3). Auto-integrates with `@stx.session` and `stx.io` when scitex is present.

## Why clew — the broken-twin incident

Real incident (NeuroVista, 2026-06-30): two same-named "warning-metrics
Table 03/04" scripts coexisted. The broken twin fabricated timestamps
(`times = arange(n) * 60 s` from a block-ordered, no-time-column CSV), so a
uniform-Poisson alarm surrogate beat the real model (AUC 0.46, IoC < 0); the
valid script used real `window_datetime` + `forecasting.evaluate_stream`
(sens 0.70 / spec 0.96 / 0.17 FP/h / lead 10.7 min / IoC +0.56). With no
claim→source→`@stx.session` binding, the two were indistinguishable as "the
source"; hours were lost and near-chance numbers were almost shipped.
Claim→source provenance makes "which code produced this value" unambiguous —
the broken twin has no registered claim. Drove ADR-0021: clew registration
is mandatory for every manuscript value.

## Installation & import

`pip install scitex-clew` exposes `import scitex_clew`. To also reach
`import scitex.clew`, additionally `pip install scitex` (umbrella).
Both forms call the same module. See `../../general/02_interface-python-api.md`.

```python
import scitex_clew                  # standalone
scitex_clew.status(...)
```

## Sub-skills

* [01_installation.md](01_installation.md) — pip install + verify
* [02_quick-start.md](02_quick-start.md) — minimal usage
* [03_python-api.md](03_python-api.md) — public callables
* [04_cli-reference.md](04_cli-reference.md) — `clew` subcommands
* [05_verify-claim-contract.md](05_verify-claim-contract.md) — `verify_claim` consumer contract: signature/return shape, the two status vocabularies (v0.7.0 `partial`→`suspect`), full-7 palette + 4-bucket display collapse, DB precedence, git-agnostic re-verify recipe
* [10_common-workflows.md](10_common-workflows.md), [11_cli-commands.md](11_cli-commands.md), [12_mcp-tools-for-ai-agents.md](12_mcp-tools-for-ai-agents.md) — workflows + CLI detail + MCP refs
* [20_env-vars.md](20_env-vars.md), [14_grouping.md](14_grouping.md) — env vars + DAG-node grouping
* [21_agentic-reasoning.md](21_agentic-reasoning.md) — when-to-call discipline for AI agents using Clew as an active reasoning substrate (v2 framing)
* [22_agentic-reasoning-examples.md](22_agentic-reasoning-examples.md) — rationale (cache/tamper/provenance), anti-patterns, and a worked five-step example for 21_agentic-reasoning

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
clew verify              # Verify ALL claims; fail-loud exit code (DONE gate)
clew verify --strict     # + require @stx.session lineage per claim
clew verify --config F   # tune per-pattern severity (.scitex/clew/config.yaml)
clew verify <SESSION_ID> # Verify a specific run (fail-loud)
clew stats               # Database statistics
clew mermaid             # Generate Mermaid DAG diagram
clew mcp start           # Start MCP server
clew skills list         # List skill pages
clew skills get SKILL    # Get a specific skill page
```

`clew verify` (no arg) is the agent DONE gate: exit `0` only when every
registered claim is source-verified; distinct nonzero codes for the
fabrication case (`10`), missing/changed source (`11`/`12`), missing
lineage under `--strict` (`13`), and no claims (`20`). Per-pattern severity
(`error`/`warning`/`ignore`) is tunable in `.scitex/clew/config.yaml`. See
[04_cli-reference.md](04_cli-reference.md#clew-verify--fail-loud-exit-codes-the-done-gate).


## Environment

See [20_env-vars.md](20_env-vars.md) — SCITEX_* env vars read by scitex-clew at runtime.
