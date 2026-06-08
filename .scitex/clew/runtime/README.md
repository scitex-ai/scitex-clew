# scitex-clew runtime directory

This directory holds regenerable data (cache, logs, SQLite databases,
stamp files) that scitex-clew produces at runtime. Everything under
`runtime/` is gitignored — it is per-host, per-run, and can always be
regenerated from config + source.

See the ecosystem local-state-directories skill for the canonical layout:
`scitex-dev/_skills/general/01_ecosystem/06_local-state-directories.md`
