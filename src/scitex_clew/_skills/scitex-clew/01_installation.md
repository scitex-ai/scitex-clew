---
description: |
  [TOPIC] Installation
  [DETAILS] pip install scitex-clew. Records provenance in the per-host PostgreSQL store. Auto-integrates with @stx.session and stx.io if scitex is present.
tags: [scitex-clew-installation]
---

# Installation

## Standard

```bash
pip install scitex-clew
```

Provenance is stored in the per-host PostgreSQL instance, reached through
`scitex_dev.store.host_store()`.

## Optional (auto-integration)

```bash
pip install scitex          # umbrella; enables @stx.session + stx.io hooks
```

When `scitex` is importable, `clew` auto-fingerprints inputs/outputs of every
`@stx.session` run and every `stx.io.save/load` call.

## Verify

```bash
clew --version
clew status                                # git-status-like overview
python -c "import scitex_clew; print(scitex_clew.__version__)"
```

## Store location

clew has **no database file**. Its four stores (`runs`, `file_hashes`,
`claims`, `citations`, …) resolve through
`scitex_dev.store.host_store()`: `SCITEX_STORE_DSN` if set, otherwise the
per-host PostgreSQL over its UNIX socket. See
[20_env-vars.md](20_env-vars.md) for details.

Provenance is per-HOST, not per-project — every project on one machine
shares the one store. `SCITEX_CLEW_DB_PATH` is retired and has no effect.

## Editable install (development)

```bash
git clone https://github.com/ywatanabe1989/scitex-clew
cd scitex-clew
pip install -e .
```
