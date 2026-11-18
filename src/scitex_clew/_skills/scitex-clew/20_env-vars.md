---
description: |
  [TOPIC] Env Vars
  [DETAILS] Environment variables read by scitex-clew at import / runtime. Follow SCITEX_<MODULE>_* convention — see general/10_arch-environment-variables.md.
tags: [scitex-clew-env-vars]
---

# scitex-clew — Environment Variables

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_STORE_DSN` | Override for THE store this host uses. Owned by `scitex_dev.store.host_store()`, not by clew. | per-host PostgreSQL over its UNIX socket | Postgres DSN |
| `SCITEX_CLEW_CAPTURE` | Whole-capture switch. `0`/`false`/`no`/`off` turns ALL automatic recording off: the `@stx.session` / `stx.io` hooks open no run, record no file, install no audit hook and never touch the store (one WARNING per process says so). Explicit API calls (`clew.session()`, `record_input`, `add_claim`, `verify`) still run. For no-recording baselines and runs you do not want recorded. See 16_unconscious-capture.md. | `1` (on) | bool |
| `SCITEX_CLEW_AUDIT_CAPTURE` | Inside a session, record files opened under the project root by any Python code (audit hook). `0`/`false`/`no`/`off` disables it for performance-sensitive runs (a WARNING says so); imported-code capture stays on. See 16_unconscious-capture.md. | `1` (on) | bool |
| `SCITEX_CLEW_JOURNAL` | Kill-durable recording journal. Every queued row is also appended to a per-session journal so a run killed before close (SIGKILL, OOM, harness timeout) is recovered at the next clew start; also gates the SIGTERM/SIGHUP handlers. `0`/`false`/`no`/`off` turns it off (a kill then loses the queued rows). See 17_killed-runs-journal.md. | `1` (on) | bool |
| `SCITEX_CLEW_JOURNAL_DIR` | Where journals live (one sub-directory per machine). Must be a local, persistent path the user owns — never `/tmp`. | `$SCITEX_DIR/clew/journal` (`~/.scitex/clew/journal`) | path |
| `SCITEX_CLEW_FLUSH_SECONDS` | The oldest queued row waits at most this long before a recording flushes the queue to the store (visibility for long runs; durability comes from the journal). `0` = flush every row. | `30` | float (s) |
| `SCITEX_CLEW_DEBUG_MODE` | Enable verbose tracing for claim execution and DAG re-run. | `false` | bool |
| `SCITEX_API_TOKEN` | Ecosystem-wide API token (shared with scitex-cloud); used when clew tools call remote endpoints. | `—` | string (required when remote) |
| `SCITEX_REGISTRY_URL` | URL of the optional SciTeX registry for cross-machine claim lookup. | unset | string (URL) |

Store resolution (`scitex_dev.store.host_store()`): `SCITEX_STORE_DSN` if
set, otherwise the per-host PostgreSQL over its UNIX socket. There are only
those two steps, and there is deliberately no local-file fallback — a host
whose Postgres is down must fail loudly rather than start writing to a
private store nobody else can see.

clew has **no database file** and no clew-specific path variable.
`SCITEX_CLEW_DB_PATH` is retired and has no effect.

Storage is per-HOST; RECORDS are still per-project. Every project on one
machine shares the one database, where clew's stores are separated by
store `name` (`runs`, `file_hashes`, `claims`, `citations`, …) and each
project's records are separated by a `project` identity column. That
column matters because `claim_id` and `cite_key` are chosen by the author:
without it, two manuscripts citing `smith2020` would be one row.

`SCITEX_CLEW_PROJECT` overrides the project scope. Unset, it is the
absolute project-root path — the same thing the old per-project file
keyed on. Set it to pin a project across a MOVE: a path-derived scope
changes when the directory does, where the old file simply travelled with
it.

## Feature flags

- **opt-in:** `SCITEX_CLEW_DEBUG_MODE=true` to enable debug tracing (verbose, default off).
- **opt-out:** `SCITEX_CLEW_CAPTURE=0` turns all automatic recording off;
  `SCITEX_CLEW_AUDIT_CAPTURE=0` only the `open()` capture;
  `SCITEX_CLEW_EXTERNAL_CAPTURE=0` only external-input recording.
  `SCITEX_CLEW_JOURNAL=0` turns off the kill-durable journal (and the
  SIGTERM/SIGHUP handlers).

## Config files (`.scitex/clew`)

Beyond env vars, scitex-clew reads layered YAML config from the SciTeX
`.scitex/<pkg>` convention (`pkg = clew`):

| Scope | Path | Precedence |
|---|---|---|
| user | `$SCITEX_DIR/clew/` (default `~/.scitex/clew/`) | low |
| project | `<git-root>/.scitex/clew/` | high (overrides user, per key) |
| explicit | `clew verify --config PATH` (file or dir) | highest |

Within a scope, `config.yaml` is the base and any `config/*.yaml` files are
deep-merged on top (sorted by name) — the `{config.yaml, config/}` shape.
`$SCITEX_DIR` relocates the user-scope root.

Currently consumed: **`verify.severity`** — per-pattern severity for
`clew verify` (`error` fails the run / blocks DONE, `warning` is reported but
tolerated, `ignore` is dropped):

```yaml
verify:
  severity:
    unverified: error      # the fabrication case
    source_missing: error
    hash_mismatch: error
    no_lineage: warning    # only fires under --strict, which promotes it to error
    no_claims: error
```

Absent config → the built-in defaults above. A malformed file, an unknown
pattern key, or an invalid severity value **raises** (fail-loud, no silent
fallback).

## Audit

```bash
grep -rhoE 'SCITEX_[A-Z0-9_]+' $HOME/proj/scitex-clew/src/ | sort -u
```
