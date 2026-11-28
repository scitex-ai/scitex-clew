---
description: |
  [TOPIC] Evidence bundle — clew's portable, signed exchange format
  [DETAILS] `.scitex/clew/evidence-bundle.json` (scitex-clew.evidence-bundle 1.0.0) travels with the repo so a third party verifies and re-runs the evidence WITHOUT the host store; `clew bundle keygen|export|verify|rerun`; Ed25519 signature over canonical JSON; shipped JSON Schemas; store-free rerun report (scitex-clew.rerun-report 1.1.0; `--work-dir` keeps the replay).
tags: [scitex-clew-evidence-bundle]
---

# Evidence bundle (exchange format 1.0.0)

Runs and claims live in the host store (`scitex_dev.store.host_store()`), which
a journal, reviewer or remote CI cannot reach. `clew bundle export` writes them
to **`<root>/.scitex/clew/evidence-bundle.json`** — commit it with the code —
and `clew bundle verify` / `clew bundle rerun` check it from a checkout alone.

```bash
pip install 'scitex-clew[sign]'                 # cryptography + jsonschema
clew bundle keygen --out ~/.scitex/clew/bundle.key     # 0600; keep OFF the repo
clew bundle export --sign-key ~/.scitex/clew/bundle.key
clew bundle verify .scitex/clew/evidence-bundle.json --json   # exit 0 = ok
clew bundle rerun  .scitex/clew/evidence-bundle.json --json --timeout 1800
```

## Document

`schema` `scitex-clew.evidence-bundle`, `schema_version` `1.0.0`,
`exported_at`, `clew_version`, `project {project_id, root_name}`, then:

| key | content |
|---|---|
| `runs[]` | `run_id`, `script`, `argv`, `interpreter {name, version}`, `cwd`, `inputs {relpath: sha256}`, `outputs {…}`, `external_inputs [{path\|uri, sha256}]`, `status`, `started_at`, `finished_at` (+ `script_sha256`, `command`, `run_dir`) |
| `edges[]` | `{parent, child}` run ids |
| `claims[]` | `claim_id`, `claim_type`, `location {file,line,label}`, `stated_text`, `stated_value`, `precision`, `source {file, locator}`, `state` (supported / not_supported / not_checkable / no_evidence_graph — the evidence-provider vocabulary), `reason`, `producing_runs`, `graph` (evidence-report graph shape) |
| `signature` | optional `{alg: ed25519, key_id, public_key, value}` |

* **Paths** are repo-relative POSIX. A file outside the root is an
  `external_inputs` entry named by the in-project path it was read through,
  else `<external>/<file name>` — never an absolute host path.
* **argv** is replayed as `<python> <argv…>` from `cwd`; in-project absolute
  arguments are rewritten relative to `cwd`.
* **Runs exported** by default: the newest successful producer of each output
  whose recorded hash still matches the file on disk (the runs that made THIS
  snapshot). `--all-runs` exports the whole history.
* **precision** describes clew's claim-check tolerance
  (`_claim/_locator.py:compare`): `declared` abs/rel_tol verbatim, else
  `implied` by the written precision (`2.0` → ±0.05, `p = 0.003` → ±0.0005),
  `exact` for non-numeric values; `fields` per located field.
* **Signature** = Ed25519 over `json.dumps(doc minus "signature",
  sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()`;
  `key_id` = first 16 hex of sha256(raw public key). Signing is pluggable
  (`scitex_clew._exchange.Signer` / `Verifier`, `register_verifier`). Key
  policy is not decided: keys are files; pin one with `verify --expect-key-id`.

Schemas ship in the wheel: `scitex_clew/_exchange/evidence-bundle.schema.1.0.0.json`
(`$id` `https://scitex.ai/schemas/scitex-clew/evidence-bundle/1.0.0`) and
`rerun-report.schema.1.1.0.json` (`…/rerun-report/1.1.0`; 1.0.0 still shipped). Consumers ignore
unknown keys; additive changes keep the major version.

## verify (store-free, read-only)

Schema validity, signature (`signed: false` when absent), and every recorded
input/output/script hash against the files under `--project-root`. Missing
files are findings, not crashes (`--allow-missing` makes them warnings).
Exit 0 ok, 1 findings (JSON `findings[]` with `code`).

**Which tree is checked.** Without `--project-root`, the tree is the bundle's
OWN project (`<root>/.scitex/clew/<file>` → `<root>`, else the git work tree
holding the file; a linked worktree is its own tree, never the shared git dir).
It must be the working directory's project too; if the two differ the command
exits 2 (`ambiguous project root`) instead of guessing. A loose bundle file in
no project is checked against the working directory's project. `verify`,
`rerun` and `export` always print `project root: <path> (<rule>)` (JSON:
`project_root`, `project_root_source`; `rerun --json` prints it on stderr).
Read that line: it is the tree the verdict is about.

## rerun (store-free; EXECUTES PROJECT CODE)

Copies the tree (minus `.git`) to a temp dir, deletes every recorded output,
replays the runs in topological order with an explicit env (clew capture and
journal off, `SCITEX_STORE_DSN` pointing at no server, HOME/TMPDIR inside the
temp dir), compares outputs' sha256 and recomputes each claim from
`source + locator` with the same tolerance. Never writes the project root,
never touches a store, adds **no sandbox** — run it inside an isolated
container. `--work-dir DIR` (absent or empty) replays there and KEEPS it; the
report then names `work_dir`, each run's `run_dir` and each output's
`resolved_path` (relative to `work_dir`) so a host-side verifier can hash
exactly the compared files. Report: `schema` `scitex-clew.rerun-report` 1.1.0, `bundle_sha256`,
`executable`, `runs[] {run_id, exit_code, status: reproduced|differs|failed|skipped,
outputs[], stderr_tail}`, `claims[] {claim_id, status: reproduced|differs|not_checkable,
stated_value, recomputed_value, tolerance}`. Exit 0 iff every run reproduced
and no claim differs. Notebook runs are `skipped`.
