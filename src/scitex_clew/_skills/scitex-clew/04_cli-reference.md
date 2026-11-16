---
description: |
  [TOPIC] clew CLI Reference
  [DETAILS] Top-level subcommands of the `clew` CLI — status, list-runs, verify, chain, slice, dag, rerun-dag, rerun-claims, show-stats, print-mermaid, claim, mcp, skills.
tags: [scitex-clew-cli-reference]
---

# CLI Reference

`clew` is the entry point installed by `uv pip install 'scitex-clew[all]'`.

## Subcommands

| Command                       | Purpose                                            |
|-------------------------------|----------------------------------------------------|
| `clew status`                 | Git-status-like overview of verification state     |
| `clew list-runs`              | List tracked runs (filter by status)               |
| `clew verify`                 | Verify EVERY registered claim; fail-loud exit code |
| `clew verify <SESSION>`       | Re-hash one session's files and compare (fail-loud)|
| `clew chain <PATH>`           | Trace + verify the provenance chain for a file     |
| `clew slice <TARGET...>`      | Minimal provenance slice (only runs/files on a path to the target) |
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

## Minimal slice — `clew slice` and `--minimal`

A run-level chain includes every input and output of every ancestor run. The
**minimal slice** keeps only what lies on a path that ends at the target
(file, claim id, or `paper.tex:L42`):

| Level | Meaning |
|-------|---------|
| `0` | run-level closure — the historical `chain` view |
| `1` | path-pruned (default): drops sibling outputs, their consumers, and runs/files on no path to the target. All inputs of a KEPT run stay (Clew cannot see inside a run) |
| `2` | level 1 + per-output `derived_from` declarations (`record_output(path, derived_from=[...])`): an output only pulls the inputs it declares; undeclared runs fall back to level 1 |

```bash
clew slice results/fig3.png                # level-1 slice, per-run inputs/outputs
clew slice results/fig3.png --compare      # node/edge counts at levels 0, 1, 2
clew slice auc_claim --level 2 --json
clew chain results/fig3.png --minimal      # verify only the slice's files
clew dag --claims --minimal
clew print-mermaid --target results/fig3.png --minimal
```

`clew verify` / `clew claim verify` always check a claim against its level-1
slice, so a changed sibling output elsewhere in a run never stales the claim.

## Claim value vs source — `clew claim add --source-keys`

A matching hash proves the source FILE is unchanged, not that the number in
the manuscript is the number in the file. Register WHERE the value lives
(same shape as scitex-writer's `source_keys`) and verification re-reads it:

```bash
clew claim add --file-path paper.tex --type value --value 0.91 \
    --source-file results.json --source-keys '{"pointer": "/test/auc"}'
clew claim add --file-path paper.tex --type value --value 0.91 \
    --source-file metrics.csv \
    --source-keys '{"row": {"split": "test"}, "column": "auc"}' \
    --tolerance '{"abs_tol": 0.01}'
clew claim verify auc_claim --project-root /abs/path/to/my-paper
```

`pointer` is an RFC 6901 JSON Pointer (json/yaml); csv/tsv take `row` (0-based
index or a `{column: value}` selector matching exactly one row) + `column`.
Tolerance: per locator or per claim (`abs_tol`/`rel_tol`), else implied by
the written precision (`0.91` -> ±0.005). `--structured-value` / `--metadata`
take JSON; `{field: locator}` maps fields of a structured value.

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

A claim whose recorded lineage is **stale** (an upstream input changed after
the pipeline ran, or a run in the lineage failed) exits `18 STALE_LINEAGE`
in BOTH modes — a stale claim is never reported verified. (Through 0.21.0 the
default mode passed such a claim on its source hash alone, and `--strict`
mislabelled it `NO_LINEAGE`.)

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
| `17` | `UNSOURCED`      | link-verified but ungrounded (only when the source gate is active) |
| `19` | `VERIFY_ERROR`   | the claim could not be checked: its lineage walk raised, or a `source_keys` locator could not be read. Never reported OK |
| `18` | `STALE_LINEAGE`  | source has recorded lineage but it no longer holds — an upstream input/output/script changed or a run in it FAILED. Fires in default AND `--strict` mode |
| `20` | `NO_CLAIMS`      | nothing registered — nothing to verify                           |
| `21` | `VALUE_MISMATCH` | the value at a claim's `source_keys` disagrees with the claimed value beyond tolerance |

When several `error`-severity classes co-occur, the single returned code is
the highest-severity one (tamper/missing > value-mismatch > verify-error > stale-lineage > unverified > unsourced > no-lineage > empty);
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
