---
description: |
  [TOPIC] Minimal provenance slice + claim value-vs-source
  [DETAILS] clew.slice levels 0/1/2 and minimal= on chain/dag/mermaid; claim source_keys (RFC 6901 pointer, csv row+column), tolerance, native value/metadata fields, project_root=, VALUE_MISMATCH/VERIFY_ERROR.
tags: [scitex-clew-minimal-slice-and-claim-values]
---

# Minimal slice and claim values

## Minimal provenance slice

```python
sl = scitex_clew.slice("results/fig3.png", level=1)   # or a claim id / "paper.tex:L42"
sl.runs, sl.files, sl.edges           # only what lies on a path to the target
sl.counts()                           # {"runs", "files", "nodes", "edges"}
sl.dropped_outputs, sl.fallback_runs  # what level 1/2 pruned, and why not
from scitex_clew._chain._slice import compare_levels
compare_levels(["results/fig3.png"])  # {0: counts, 1: counts, 2: counts}

scitex_clew.chain("results/fig3.png", minimal=True)  # verify only slice files
verify_dag(targets, minimal=True, level=2)
```

Level 0 = run-level closure; 1 = path-pruned (keeps every input of a kept
run); 2 = honours per-output `derived_from` (`tracker.record_output(path,
derived_from=[inp])`), falling back to level 1 per undeclared run.

Declarations arrive without clew calls: `stx.io.save(obj, path,
derived_from=[path_or_loaded_obj])` hands them to `on_io_save`
(`kwargs["derived_from"]`), and figrecipe declares a figure rebuilt by
`fr.reproduce(recipe)` and saved unchanged as derived from the recipe and
its data files. Nothing is inferred: without a declaration level 2 equals
level 1. Recording the same bytes of a path twice in one run (figrecipe
records its image, then the `stx.io.save` that called it fires its hook)
keeps the declaration — an undeclared re-record does not erase it, a second
declaration is unioned; new bytes replace it.
`generate_dag_json` / `generate_mermaid_dag` take the same
`minimal=`/`level=`. Claim verification always uses the level-1 slice.

## Claims: value vs source, native fields, `project_root=`

```python
scitex_clew.add_claim(
    "paper.tex", "value", claim_value="AUC = 0.91",   # display string
    source_file="results.json",
    value=0.91,                                       # checked value (else the display string)
    source_keys={".": {"pointer": "/test/auc"}},      # RFC 6901; csv: {"row": 3|{"split":"test"}, "column": "auc"}
    tolerance={"abs_tol": 0.01},                      # optional; else implied by written precision
    metadata={"section": "results"},
    claim_id="auc", project_root="/abs/path/to/my-paper",   # no chdir needed
)
scitex_clew.verify_claim("auc", project_root="/abs/path/to/my-paper")
# -> {"value_verified": True, "value_checks": [...], ...}
```

`source_keys` is scitex-writer's shape (`{field | ".": locator}`, per-locator
`abs_tol`/`rel_tol`). A contradicting value is `VALUE_MISMATCH` (21); an
unreadable locator or a raising lineage walk is `VERIFY_ERROR` (19) — never
OK. `project_root=` is also accepted by `list_claims`, `verify_all_claims`,
`verify_claims_dag`, `remove_claim(s_by_prefix)`, `supersede_claim(s_by_prefix)`.
Re-adding a claim id after `remove_claim` makes it visible again.
