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
| `SCITEX_CLEW_DEBUG_MODE` | Enable verbose tracing for claim execution and DAG re-run. | `false` | bool |
| `SCITEX_API_TOKEN` | Ecosystem-wide API token (shared with scitex-cloud); used when clew tools call remote endpoints. | `—` | string (required when remote) |
| `SCITEX_REGISTRY_URL` | URL of the optional SciTeX registry for cross-machine claim lookup. | unset | string (URL) |

Store resolution (`scitex_dev.store.host_store()`): `SCITEX_STORE_DSN` if
set, otherwise the per-host PostgreSQL over its UNIX socket. There are only
those two steps, and there is deliberately no local-file fallback — a host
whose Postgres is down must fail loudly rather than start writing to a
private store nobody else can see.

clew has **no database file** and no clew-specific path variable.
`SCITEX_CLEW_DB_PATH` is retired and has no effect. Provenance is
per-HOST, not per-project: every project on one machine shares the one
store, and clew's four stores are separated inside it by their store
`name` (`runs`, `file_hashes`, `claims`, `citations`, …), not by
directory.

## Feature flags

- **opt-in:** `SCITEX_CLEW_DEBUG_MODE=true` to enable debug tracing (verbose, default off).

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
