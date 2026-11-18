---
description: |
  [TOPIC] Cli Commands
  [DETAILS] CLI reference for the clew command (requires uv pip install 'scitex-clew[all]').
tags: [scitex-clew-cli-commands]
---

# CLI Commands

Requires `uv pip install 'scitex-clew[all]'` (adds `click` and other optional deps).

Entry point: `clew` (also installed as `scitex-clew`).

## Global options

```bash
clew --version          # Print version and exit
clew --help-recursive   # Show help for all commands
clew --json <command>   # Emit JSON for any subcommand (also a per-command flag)
```

## Verification commands

```bash
# Git-status-like overview of all verified/mismatch/missing runs
clew status

# List tracked runs
clew list-runs
clew list-runs --status success --limit 100    # default limit: 50

# Verify a specific run by session ID (hash check)
clew verify <SESSION_ID>
# Output:
#   [OK]   2025Y-11M-18D-09h12m03s_HmH5 (verified)
#     [OK] output results/model.csv
#     [!!] output results/plot.png

# Trace + verify the full provenance chain that produced a file
clew chain results/fig1.png
clew chain results/fig1.png --json
clew chain results/fig1.png --minimal    # only the file-level minimal slice

# Minimal provenance slice: only runs/files on a path to the target
clew slice results/fig1.png              # level 1 (path-pruned, default)
clew slice results/fig1.png --compare    # node/edge counts at levels 0/1/2
clew slice <claim_id> --level 2 --json   # level 2 honours derived_from

# Verify the DAG for explicit targets, or every claim (hash-only)
clew dag --target results/fig1.png --target results/table1.csv
clew dag --claims --strict --json        # --strict → failure-attribution payload

# Database statistics
clew show-stats
```

## Re-execution commands (slow, gold-standard reproducibility)

These actually re-run scripts in a sandbox and compare outputs; originals are
never overwritten. Use when hash-only checks aren't enough. A replay runs the
recorded `argv` from the recorded `cwd` against a sandbox copy of the script
(outputs land in the sandbox's `<script>_out/`; runs whose outputs live
elsewhere are refused), compares outputs by relative path + full hash, then
removes the sandbox and hides the replay's records. A failing replay is
`FAILED`.

```bash
# Re-run the whole DAG (or just the upstream of given targets) in topo order
clew rerun-dag
clew rerun-dag --target results/fig1.png --timeout 600 --json

# Re-run every session backing a manuscript claim
clew rerun-claims
clew rerun-claims --type statistic --json
```

## Visualization commands

```bash
# Generate Mermaid DAG diagram (all runs)
clew print-mermaid

# Generate Mermaid DAG from registered claims
clew print-mermaid --claims
clew print-mermaid --claims --minimal    # only the claims' minimal slice

# Target a store outside the current tree (host-side / post-run)
clew print-mermaid --claims
```

## Claim commands

```bash
clew claim add --file-path paper.tex --type statistic --value 'p=0.003'
clew claim list --file-path paper.tex --type statistic
clew claim verify <claim_id> --project-root /abs/path/to/paper
# Locate the value inside its source; verify re-reads and compares it
clew claim add --file-path paper.tex --type value --value 0.91 \
    --source-file results.json --source-keys '{"pointer": "/test/auc"}'

# Register a computed intermediate value (with upstream support) as a claim
clew claim register-intermediate --name n_sig_pathways --value 42 \
    --supports chronic_r2_min_pvals --supports reactome_v2024
clew claim register-intermediate --name x --value 1 --dry-run   # preview only
```

## Hashing / stamping commands

```bash
clew hash-file path/to/file
clew hash-directory path/to/dir
clew stamp <session_id>
clew list-stamps
clew check-stamp <session_id>
```

## Recording commands

```bash
# Replay the journals of runs whose process was killed before closing
# (SIGKILL / OOM / harness timeout). Every clew command and session start
# already does this quietly; this reports it. Idempotent.
clew recover-journals
clew --json recover-journals --dry-run   # what would be replayed
```

## Integration commands

```bash
# Start MCP server
clew mcp start

# List public Python API (introspect)
clew list-python-apis

# Shell completion
clew install-shell-completion --shell bash    # writes to your rc file
clew print-shell-completion   --shell zsh     # prints the script to stdout
```

## Skills commands (requires scitex-dev)

```bash
clew skills list               # List all skill pages
clew skills get quick-start    # Get a specific skill page
```

## Notes

- `clew verify` accepts a session ID (e.g., `2025Y-11M-18D-09h12m03s_HmH5`)
- Session IDs come from `@stx.session` in scitex, or from `clew list-runs`
- `--json` is accepted both top-level (`clew --json status`) and per command
- `clew claim register-intermediate` needs a session: pass `--session-id` or
  run inside a `@stx.session` script (reads `$SCITEX_SESSION_ID`)
- All commands exit 0 on success; non-zero on errors
