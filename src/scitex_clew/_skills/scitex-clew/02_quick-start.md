---
description: |
  [TOPIC] Quick Start
  [DETAILS] Basic scitex-clew API, session tracking, and first verification run.
tags: [scitex-clew-quick-start]
---

# Quick Start

## Installation

```bash
uv pip install scitex-clew              # bare (minimal — no optional deps)
uv pip install 'scitex-clew[all]'       # batteries-included (click, fastmcp, matplotlib)
uv pip install 'scitex-clew[dev]'       # + testing tooling
```

## Public API (19 functions)

```python
import scitex_clew as clew

# Verification
clew.status()                      # git-status-like overview
clew.run(session_id)               # verify one run (hash check)
clew.chain(target_file)            # trace file -> source chain
clew.dag(targets)                  # verify full DAG
clew.rerun(target)                 # re-execute & compare (sandbox)
clew.rerun_dag(targets)            # rerun full DAG in topo order
clew.rerun_claims()                # rerun all claim-backing sessions
clew.list_runs(limit=100)          # list tracked runs
clew.stats()                       # database statistics

# Claims
clew.add_claim(...)                # register manuscript assertion
clew.list_claims(...)              # list registered claims
clew.verify_claim(...)             # verify a specific claim

# Stamping
clew.stamp(...)                    # create temporal proof
clew.list_stamps(...)              # list stamps
clew.check_stamp(...)              # verify a stamp

# Hashing
clew.hash_file(path)               # SHA256 of a file
clew.hash_directory(path)          # SHA256 of all files in dir

# Visualization
clew.mermaid(...)                  # generate Mermaid DAG diagram

# Examples
clew.init_examples(dest)           # scaffold example pipeline
```

## Verification status overview

```python
import scitex_clew as clew

# Like git status — shows verified/mismatch/missing/unknown counts
result = clew.status()
# Returns dict: {verified, mismatch, missing, unknown, total}
```

## Verify a session run

```python
# Verify by session ID (hash check — fast)
rv = clew.run("2025Y-11M-18D-09h12m03s_HmH5")
print(rv.is_verified)       # True / False
print(rv.status.value)      # 'verified' / 'mismatch' / 'missing' / 'unknown'

for f in rv.files:
    print(f.path, f.role, f.is_verified)

# Re-execute in sandbox and compare outputs (slow but thorough)
rv = clew.run("2025Y-11M-18D-09h12m03s_HmH5", from_scratch=True)
```

## Trace provenance chain

```python
# Verify the full dependency chain for a file
chain = clew.chain("/path/to/results/model_accuracy.csv")
print(chain.is_verified)            # True if whole chain passes
print(len(chain.runs))              # number of sessions in chain
print(len(chain.failed_runs))       # number with failures
```

## List tracked runs

```python
runs = clew.list_runs(limit=50)
for r in runs:
    print(r["session_id"], r.get("status"), r.get("script_path"))
```

## Hash utilities

```python
# Hash a single file (returns first 32 hex chars of SHA256)
h = clew.hash_file("data.csv")

# Hash all files in a directory
hashes = clew.hash_directory("/path/to/dir")
# Returns dict: {filename: hash, ...}
```

## Auto-integration with scitex

When scitex is installed, clew integrates automatically:

```python
import scitex

@scitex.session
def main(logger=scitex.INJECTED):
    # scitex.io.load/save automatically records hashes via SessionTracker
    data = scitex.io.load("raw_data.csv")
    result = process(data)
    scitex.io.save(result, "processed.csv")
    return 0
```

Every `stx.io.load()` call records an input hash; every `stx.io.save()` records an output hash, linked to the current `@stx.session` ID.
