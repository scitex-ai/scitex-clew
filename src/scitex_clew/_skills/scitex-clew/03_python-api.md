---
description: |
  [TOPIC] Python API
  [DETAILS] Public callables — status, list_runs, run, chain, dag, mermaid, rerun, stats and the verify_* family for programmatic checks.
tags: [scitex-clew-python-api]
---

# Python API

## Imports

```python
import scitex_clew
# or via umbrella:
import scitex.clew
```

## Top-level operations

| Callable                        | Purpose                                                   |
|---------------------------------|-----------------------------------------------------------|
| `status()`                      | Git-status-like dict of verification state                |
| `list_runs(limit=100, status=None)` | List tracked runs                                     |
| `run(session_id, from_scratch=False)` | Verify one session by re-hashing every file         |
| `chain(target)`                 | Trace the provenance chain for a file                     |
| `dag(targets=None, claims=False)` | Verify the full DAG (or claims-DAG)                     |
| `rerun(target, timeout=300, cleanup=True)` | Re-execute and compare outputs                 |
| `mermaid(...)`                  | Render Mermaid diagram for the DAG                        |
| `verify_all_claims(strict=False, config=None)` | Verify every claim; returns a `VerificationResult` (fail-loud `exit_code`/`ok`; the `clew verify` DONE gate) |
| `stats()`                       | Database statistics                                       |

## Programmatic verification

```python
from scitex_clew import (
    verify_run, verify_chain, verify_dag, verify_file,
    verify_by_rerun, verify_claims_dag, verify_all_claims,
)

result = verify_run("20261103_120000_abc12345")
ok = verify_file("results/figure_3.png")

# Fail-loud claim-set verification (the `clew verify` DONE gate).
# Returns a VerificationResult dataclass (.to_dict() gives the JSON shape):
summary = verify_all_claims(strict=True)   # optional config="path/to/.scitex/clew"
if not summary.ok:                         # summary.exit_code == 0; see _cli._exit_codes
    abstain(reason=summary.reason)         # never claim success on nonzero
# summary.errors / summary.warnings list fired patterns by name; per-pattern
# severity (error vs warning) is tunable in .scitex/clew/config.yaml.
```

## Tracking primitives

```python
from scitex_clew import (
    get_tracker, set_tracker,
    start_tracking, stop_tracking,
    get_registry,
)
```

`start_tracking()` is invoked automatically by `@stx.session`; you only need
it when integrating clew into a non-scitex pipeline.

## Formatting helpers

`format_claims(...)`, `format_status(...)` — render results as text tables.

See [02_quick-start.md](02_quick-start.md) for usage examples and
[10_common-workflows.md](10_common-workflows.md) for end-to-end recipes.

---

## Verification caching — correctness guarantee

Operator invariant (neurovista, 2026-06-30): dev-speed caching is fine; a
correctness-breaking cache is not. A "false green" — a cached `VERIFIED` for
content that has since changed — must never occur; no mechanism below can
produce one. Audited against the source at **v0.6.0**; paths are current.

> **Summary.** Every clew cache is keyed by content hash — SHA-256 of the
> live file bytes, first 32 hex chars (`_hash.py`). No mtime-based logic
> exists anywhere in the package: `rg -n "mtime" src/ -g '*.py'` → zero
> matches (re-verified at v0.6.0; only this document mentions "mtime").

### Verification levels at a glance

| Level | Constant | Meaning |
|-------|----------|---------|
| L1 | `CACHE` | Compare stored SHA-256 hashes vs current file bytes (milliseconds) |
| L2 | `RERUN` | Re-execute the script in a sandbox and compare outputs |
| L3 | `REGISTERED` | L2 + hash registered with a server-side timestamp (scitex.ai) |

Source: `src/scitex_clew/_chain/_types.py` (`VerificationLevel`).
`RunVerification.is_verified_from_scratch` is `True` only for `level ==
RERUN`, so a strict hook can require full re-execution via that property.

### (a) L1 CACHE — direct content hashing

`verify_run()` in `src/scitex_clew/_chain/_verify_ops.py` calls `hash_file()`
from `src/scitex_clew/_hash.py` for every input, output, and script file
recorded in the session. `hash_file` reads the file in 8 KiB chunks through
`hashlib.sha256` and returns the first 32 hex characters. Unless a per-pass
cache is explicitly threaded in (see (b)), every invocation reads the bytes
fresh from disk — no module-global state, no mtime/size shortcut.

**Guarantee.** A changed file is always detected; there is no fast path that
skips the read. **Only assumption:** the file is not overwritten during the
single `hash_file` call.

### (b) Per-pass hash cache — `src/scitex_clew/_chain/_hash_cache.py` (since v0.2.19)

`HashCache = Dict[str, str]` maps `str(Path(p).resolve())` → content hash.
`new_hash_cache()` returns a fresh empty dict at each top-level verify entry
point (`verify_chain` and the status pass in `_chain/_chain_ops.py`,
`verify_dag` in `_chain/_dag.py`, `verify_all_claims` in
`_claim/_verify.py`, `rerun_dag(skip_unchanged=True)` in `_rerun.py`) and is
threaded down the call stack — never persisted, never a module-global, never
a mutable default argument.

**Guarantee.** Within one pass a file is hashed at most once (the perf win
when one config file feeds many sessions). Across independent passes the
dict is discarded, so a file changed between two calls is always re-hashed.
The cached value is the content hash itself; the key carries no mtime or
size. **Only assumption:** a file is not rewritten mid-pass (passes are
short-lived; same as (a)).

### (c) Freshness-skip incremental rerun — `src/scitex_clew/_chain/_freshness.py` (since v0.2.19)

`rerun_dag(skip_unchanged=True)` (`src/scitex_clew/_rerun.py`) is opt-in
(default `False`). Before each sandbox re-execution, `_is_session_fresh()`
re-hashes the script and EVERY recorded input file and compares against the
values stored at record time. Any mismatch — or a missing `script_hash`
baseline — falls through to the normal re-execution path. Only a
fully-matching session is skipped, returning
`RunVerification(status=VERIFIED, level=CACHE)`.

**Guarantee.** A changed script or input can never be skipped — every
freshness check re-reads actual file bytes.

**Honest caveats.**
- Inputs-only: output files are NOT re-hashed by the freshness check (its
  question is "would a re-run produce the same outputs?", not "are the
  on-disk outputs untampered?"). To also catch a hand-edited output, pair
  `skip_unchanged=True` with an L1 `verify_chain()` pass, which compares
  stored output hashes against the current files.
- A skipped session is `level=CACHE` (not `RERUN`), so
  `is_verified_from_scratch` is `False`; a strict hook can assert that
  property to force real re-runs.
- Determinism is assumed: scripts that fetch live data or use unseeded
  randomness should not use `skip_unchanged=True`.

### (d) Per-pass chain memo — `src/scitex_clew/_claim/_verify.py`

`verify_all_claims()` also keeps a per-pass `chain_cache`
(`{resolved source_file: ChainVerification}`) so N claims sharing one source
walk its provenance chain once per pass. Same discipline as (b): a fresh
dict per call, never persisted; the memoized chain result was itself
computed from live bytes within the same pass.

### (e) `frozen` flag — the one explicit hash-trust opt-out

Not a cache, but the only mechanism that skips re-reading bytes: a file
recorded with `frozen=1` (`file_hashes.frozen`,
`src/scitex_clew/_db/_file_hashes.py`) is trusted at its recorded hash
during verification (`src/scitex_clew/_chain/_verify_ops.py`). It is
per-file, opt-in at record time, and always visible: existence is still
checked (a missing frozen file is `MISSING`), and the result carries
`frozen=True` end-to-end (`FileVerification.frozen`, CLI output, Mermaid
nodes) — a frozen pass is never rendered as fully hash-verified. Freezing a
file is an explicit trust declaration (e.g. archived raw data), not a silent
cache.

### (f) Persistent verdict cache — NOT implemented (design record)

A persistent L2/L3 verdict cache was planned for v0.2.20, but v0.2.20
shipped claim CRUD instead; as of v0.6.0 there is **no persistent verdict
cache in `src/`**. The `verification_results` table
(`src/scitex_clew/_db/_core.py`) is an append-only history log keyed by
`session_id`; its only reader is the Mermaid view
(`src/scitex_clew/_viz/_mermaid_dag.py`), which still performs a live L1
pass and uses the log solely to annotate the level badge when a past
rerun-verified exists — a stored verdict never skips or overrides live
hashing.

The recorded design, kept for when it is built:

```
key = H(verification_level ‖ script_hash ‖ sorted(input_hashes) ‖ source_hash)
```

with every component a SHA-256 of live file bytes computed at lookup time —
never path+mtime. The key IS the content fingerprint, so invalidation is
automatic and total: any changed byte yields a different key (miss) and
triggers re-verification; no separate invalidation step exists to be
skipped. Forming the key REQUIRES re-hashing all relevant files on every
lookup, so the cache can only ever skip the expensive L2 subprocess / L3
registry round-trip — never the content read. Corollary: it saves nothing
on L1 (L1 is only hashing); the shipped `frozen` flag (e) is the L1-speed
lever instead.
