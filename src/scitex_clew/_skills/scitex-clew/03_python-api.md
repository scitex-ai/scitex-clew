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
