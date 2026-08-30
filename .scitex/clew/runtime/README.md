# scitex-clew runtime directory

This directory holds regenerable data (cache, logs, `claims.json`, stamp
proof files) that scitex-clew produces at runtime. It holds no database:
provenance lives in the per-host PostgreSQL store, resolved by
`scitex_dev.store.host_store()`. Everything under
`runtime/` is gitignored — it is per-host, per-run, and can always be
regenerated from config + source.

See the ecosystem local-state-directories skill for the canonical layout:
`scitex-dev/_skills/general/01_ecosystem/06_local-state-directories.md`
