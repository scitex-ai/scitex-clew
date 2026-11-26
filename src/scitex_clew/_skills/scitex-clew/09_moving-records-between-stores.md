---
description: |
  [TOPIC] Moving a project's clew records between stores
  [DETAILS] `clew records export --out F.json` / `clew records import F.json [--project-scope S] [--rebase SRC_ROOT=DST_ROOT]... [--dry-run]` — every row of the current project scope from all eight clew stores (runs, file_hashes, verification_results, session_parents, environments, claims, citations, stamps) in a checksummed `scitex-clew.project-records` 1.0.0 document; the target never connects to the source; idempotent import that rewrites the project scope and (with --rebase) the recorded paths, reporting external ones; DML only — works as a tenant login on a provision_tenant_store store (the Hub Clew app's target) or a provision_store_acl store.
tags: [scitex-clew-moving-records-between-stores]
---

# Moving records between stores

Clew writes to ONE store — the one `SCITEX_STORE_DSN` names (else the
per-host PostgreSQL) — and files every row under a **project scope**
(`$SCITEX_CLEW_PROJECT`, else `<root>/.scitex/clew/project-id`). To move a
project's records from one store to another (a private PostgreSQL -> a Cloud
tenant store whose Clew app reads a fixed scope), export them to a file and
import the file on the other side. The two stores never connect to each
other; the file is the only thing that travels.

```bash
# 1. source side (SCITEX_STORE_DSN -> the private store)
clew records export --out records.json                          # current scope
clew records export --out records.json --project-scope clew-1a2b...  # explicit

# 2. move records.json (scp, upload, ...)

# 3. target side (SCITEX_STORE_DSN -> the target store, e.g. the tenant login)
clew records import records.json --project-scope TENANT_SCOPE \
    --rebase /home/me/proj/paper=/srv/projects/paper --dry-run
clew records import records.json --project-scope TENANT_SCOPE \
    --rebase /home/me/proj/paper=/srv/projects/paper --json
SCITEX_CLEW_PROJECT=TENANT_SCOPE clew verify
```

`--project-scope` on import is the scope the rows are filed under; omitted,
it is the target side's current resolved scope. Every row's `project` field
is rewritten to it.

## What is in the file

Schema id **`scitex-clew.project-records`**, `schema_version` **`1.0.0`**:

| key | content |
|---|---|
| `schema`, `schema_version` | format id; import refuses any other |
| `clew_version`, `exported_at` | producer + UTC time |
| `source.project` | the scope the rows were exported from |
| `counts` | rows per table |
| `tables.<name>.rows[]` | `{"values": {field: value}, "hidden": bool}` — every field but `project` |
| `payload_sha256` | SHA-256 of the canonical JSON (sorted keys, `(",", ":")` separators, UTF-8) of the whole document without this key |

All eight clew stores are exported, empty or not: `runs`, `file_hashes`,
`verification_results`, `session_parents`, `environments`, `claims`,
`citations`, `stamps` — everything `clew verify` / `clew slice` / the claim
listing / the Clew app read. Removed claims travel as `"hidden": true` and
stay hidden. **Values only — never the DSN** or any credential.

## Import semantics

* **Refused before writing**: a `payload_sha256` that does not match (the
  file was edited or truncated), an unknown `schema` / `schema_version`, an
  unknown table or field (upgrade scitex-clew).
* Per record, by identity under the target scope: `created` (absent),
  `unchanged` (identical — **skipped**, nothing written), `updated`
  (different — the document's values **replace** the record's, NULLs
  included).
* A different value in a **write-once** field (a verification result, a
  session-parent edge's `recorded_at`, ...) refuses the whole import before
  any table is written: two histories for one key are resolved by hand.
* Re-importing the same file is a no-op: every row reports `unchanged`.
* `--dry-run` reports the same per-table counts and writes no record.
  (Like any clew command, opening a self-managed store that has no clew
  tables yet creates them, empty; a managed or tenant store is never
  altered.)

## Moving paths: `--rebase SRC_ROOT=DST_ROOT`

clew records absolute paths, so a document exported on one machine names
that machine's checkout. A target that checks every path against its own
project root (the Hub Clew app refuses anything outside it) needs them
moved. `--rebase SRC_ROOT=DST_ROOT` (repeatable; both absolute) rewrites
every recorded path that IS a source root or lies under one (component
boundary — `/a/proj` covers `/a/proj/x`, not `/a/project`; the longest
matching root wins):

* scalar fields: `runs.script_path`, `file_hashes.file_path`,
  `claims.file_path`, `claims.source_file`, `citations.manuscript_file`;
* string leaves inside the JSON fields `runs.metadata` (cwd, argv, ...),
  `file_hashes.derived_from`, `file_hashes.external`.

An absolute path under **no** source root is left as recorded and reported
as **external** (`paths.external`, `paths.external_by_field`, up to 20
`paths.external_examples`) — a shared dataset is not this checkout's to
move. Not rewritten: `claim_id` (an identity, even when it was derived from
the old location) and free-form caller data (`claims.metadata`, stamp
metadata). The checksum is checked on the document as exported; rebasing
happens after.

## Admin-provisioned target stores

Import writes through the same `ProjectScopedStore(Store(host_store(...)))`
seam `get_db()` and the claim / citation / stamp stores use, so it needs
exactly the rights clew's own writes need. Two provisioning contracts are
tested:

* **Tenant store** (`scitex_dev.store.provision_tenant_store` — the Hub Clew
  app's target): an unprivileged tenant LOGIN, a NOLOGIN owner, FORCE
  row-level security. Set `SCITEX_STORE_DSN` to the tenant login DSN and
  import; the app's worker (`_django/services/worker.py`) then reads the
  records with its own project root.
* **Shared managed store** (`provision_store_acl`): a NOLOGIN
  `scitex_store_owner` owns the tables; the login is a DML-only `scitex_rw`
  member.

When the tables exist, import issues only DML. When one is missing,
`Store()` refuses (`StoreProvisionError` on a managed store) — the admin
provisions all eight schemas; import never attempts DDL itself.

## Limitations

* **Without `--rebase`, paths are the source machine's.** Hash and value
  checks on the target re-read the recorded paths, so verification there
  matches the source only when the same files exist at those paths. For a
  review that must not depend on any store, use the evidence bundle
  ([08](08_evidence-bundle.md)).
* Each table is written in its own transaction: an infrastructure failure
  mid-import can leave earlier tables imported. Re-running the import is
  safe (idempotent) and completes it.
* The target's oplog records the import as new writes by the importing
  node; the source's oplog history is not copied.
