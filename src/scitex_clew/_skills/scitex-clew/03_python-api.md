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

This section records the no-false-green invariant for every cache mechanism
in clew. A "false-green" is a cached `VERIFIED` result returned for content
that has since changed. The operator's hard invariant is that this must never
happen. The guarantees below are audited against the source.

> **Summary.** All clew caches are content-hash-keyed; there is no mtime-based
> logic anywhere in the package — so no cache can return verified for content
> that has changed.

### Verification levels at a glance

| Level | Constant | Meaning |
|-------|----------|---------|
| L1 | `CACHE` | Compare stored SHA-256 hashes vs current file bytes (milliseconds) |
| L2 | `RERUN` | Re-execute the script in a sandbox and compare outputs |
| L3 | `REGISTERED` | L2 + hash registered with a server-side timestamp (scitex.ai) |

Source: `_chain/_types.py` (`VerificationLevel`). `RunVerification.is_verified_from_scratch`
is `True` only when `level == RERUN`, so a strict hook can require full
re-execution by checking that property.

### (a) L1 CACHE — direct content hashing (on `develop`)

**What it does.** `verify_run()` in `_chain/_verify_ops.py` calls `hash_file(path)`
from `_hash.py` for every input, output, and script file recorded in the
session. `hash_file` reads the file in 8 KiB chunks through `hashlib.sha256`
and returns the first 32 hex characters of the digest. There is no module-global
state, no mtime/size shortcut, and no cross-call caching — every invocation
reads the bytes fresh from disk.

**Guarantee.** Because the hash is computed from file bytes on each call, a
changed file is always detected. There is no fast-path that skips the read.
A git hook running `clew run <session>` (L1) correctly reports MISMATCH if
any tracked file has been modified since the session was recorded.

**Only assumption.** The file is not overwritten during a single `hash_file`
call (each call is sub-millisecond for typical files).

**Confirmed no mtime.** A project-wide grep for `mtime`, `getmtime`, and
`st_mtime` across `src/` returns zero results.

### (b) Per-pass hash cache (pending: `perf/verify-hash-cache`)

This is an in-flight performance optimisation, not yet merged to `develop`.
It is documented here so a reviewer or hook author can assess the safety of
the change before it lands.

**What it adds.** `_chain/_hash_cache.py` introduces `HashCache = Dict[str, str]`
and `new_hash_cache()` which returns a fresh empty dict. `hash_file` gains an
optional `hash_cache=` parameter: on a cache hit (resolved path already in
the dict) the stored hash is returned without re-reading the file; on a miss
the file is read, hashed, and the result stored. The cache is created once
at the top-level verify entry point and passed down through the call stack —
it is never a module-global and never a mutable default argument.

**Guarantee.** Within a single pass a file is hashed at most once (perf win
for DAGs where a shared config file is an input to many sessions). Across
independent passes the cache is discarded and every file is re-hashed from
scratch, so a file changed between two independent calls to `verify_run()`
is always detected. The cached value is the content hash itself — there is no
mtime or size shortcut in the cache key or the miss path.

**Only assumption.** A file is not rewritten during a single pass (passes are
short-lived; same assumption as (a)).

### (c) Freshness-skip for incremental rerun (pending: `perf/rerun-incremental-skip`)

Also in-flight, not yet merged to `develop`.

**What it adds.** `rerun_dag(skip_unchanged=True)` is an opt-in flag. Before
launching a subprocess re-execution for each session, `_is_session_fresh()`
in `_chain/_freshness.py` is called. It re-hashes the script and every
recorded input file and compares each hash to the value stored in the
database. Any mismatch returns `False` immediately, causing `rerun_dag` to
fall through to the normal subprocess re-execution path. Only when every
check passes is the session skipped, returning
`RunVerification(level=CACHE, status=VERIFIED)`.

**Guarantee.** A changed script or input can never be skipped — every freshness
check re-reads the actual file bytes; there is no mtime shortcut.

**Honest caveats.**
- The check covers inputs and the script; it does NOT re-hash output files.
  The purpose is to answer "would re-running this session produce the same
  outputs?" (i.e., are inputs unchanged?), not "are the on-disk outputs
  untampered?". To also catch a hand-edited output file, pair
  `skip_unchanged=True` with an L1 `verify_chain()` pass — the L1 pass
  compares stored output hashes against the current files.
- A skipped session is recorded as `level=CACHE` (not `RERUN`), so
  `RunVerification.is_verified_from_scratch` is `False`. A strict hook that
  requires full re-execution can enforce this by asserting
  `result.is_verified_from_scratch`.
- The freshness check assumes the script is deterministic given identical
  inputs. Scripts that fetch live data or use unseeded randomness should not
  use `skip_unchanged=True`.

### (d) Proposed persistent verdict cache (design — NOT yet implemented)

ROADMAP: planned for v0.2.20. No code implementing this has been merged.
The design is recorded here for review.

**Design intent.** Avoid re-running the expensive L2 subprocess or the L3
registry round-trip when nothing in the pipeline has changed since the last
verified run. L1 is already fast (just hashing); the persistent cache
primarily benefits repeated L2/L3 calls in CI or git hooks.

**Proposed cache key.**
```
key = H(verification_level ‖ script_hash ‖ sorted(input_hashes) ‖ source_hash)
```
where each component is a SHA-256 of the current file bytes, computed at
lookup time. The key is never path+mtime.

**Automatic invalidation.** Because the key IS the content fingerprint, any
change to the script, any input, or the source file yields a different key
(cache miss) and triggers re-verification. No separate invalidation step is
needed and none can be accidentally skipped.

**Critical safety property.** Forming the key requires re-hashing all
relevant files on every lookup. The persistent cache therefore cannot skip
the content read — it only skips the expensive subprocess (L2) or registry
call (L3) after the hashes confirm nothing has changed. Corollary: the cache
saves essentially nothing on L1 (L1 is only hashing anyway); the real
hook-speed lever is L1 combined with a `frozen-input` flag planned alongside
this feature.
