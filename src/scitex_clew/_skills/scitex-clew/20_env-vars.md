---
description: |
  [TOPIC] Env Vars
  [DETAILS] Environment variables read by scitex-clew at import / runtime. Follow SCITEX_<MODULE>_* convention — see general/10_arch-environment-variables.md.
tags: [scitex-clew-env-vars]
---

# scitex-clew — Environment Variables

| Variable | Purpose | Default | Type |
|---|---|---|---|
| `SCITEX_CLEW_DB_PATH` | Override for the claim-verification SQLite database location. | `~/.scitex/clew/runtime/db.sqlite` | path |
| `SCITEX_CLEW_DEBUG_MODE` | Enable verbose tracing for claim execution and DAG re-run. | `false` | bool |
| `SCITEX_API_TOKEN` | Ecosystem-wide API token (shared with scitex-cloud); used when clew tools call remote endpoints. | `—` | string (required when remote) |
| `SCITEX_REGISTRY_URL` | URL of the optional SciTeX registry for cross-machine claim lookup. | unset | string (URL) |

## Feature flags

- **opt-in:** `SCITEX_CLEW_DEBUG_MODE=true` to enable debug tracing (verbose, default off).

## Audit

```bash
grep -rhoE 'SCITEX_[A-Z0-9_]+' $HOME/proj/scitex-clew/src/ | sort -u
```
