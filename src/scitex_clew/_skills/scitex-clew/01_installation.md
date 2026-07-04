---
description: |
  [TOPIC] Installation
  [DETAILS] pip install scitex-clew. Pure-stdlib + sqlite3, zero deps. Auto-integrates with @stx.session and stx.io if scitex is present.
tags: [scitex-clew-installation]
---

# Installation

## Standard

```bash
pip install scitex-clew
```

Zero dependencies — pure-stdlib + sqlite3. Works standalone.

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

## Database location

By default at `<project_root>/.scitex/clew/runtime/db.sqlite`, where the
project root is found by walking up from the cwd to the nearest directory
containing `.git` or `pyproject.toml` (fallback: cwd itself).
Precedence: explicit `db_path` arg > `SCITEX_CLEW_DB_PATH` env var > this
project-root walk. See [20_env-vars.md](20_env-vars.md) for details.

## Editable install (development)

```bash
git clone https://github.com/ywatanabe1989/scitex-clew
cd scitex-clew
pip install -e .
```
