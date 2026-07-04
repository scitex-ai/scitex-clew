---
description: |
  [TOPIC] Zero-dependency clew.session() provenance recorder
  [DETAILS] Record a real run (runs row + input->output edges) using only clew's pure-stdlib core — for stripped environments where `import scitex` / @stx.session cannot load, OR whenever you want the file_hashes edges GUARANTEED. Makes a minimal-mode script produce runs>=1 + a source-reachable DAG that passes the gate. clew's own recorder (does NOT import scitex-session); the zero-dep counterpart to @stx.session.
tags: [scitex-clew-zero-dep-session]
---

# Zero-dependency `clew.session()` provenance recorder

## Why

The provenance gate needs `runs >= 1` and a chain that reaches a registered
source — which requires the per-file `input -> output` edges in `file_hashes`.
Normally `@stx.session` records the run and `stx.io.save` populates those edges
via clew's save hook. But in a **stripped environment** `import scitex` fails
(no numpy/h5py/system libs), so `@stx.session` is uncallable; and even with the
full stack, if the save hook doesn't fire, `file_hashes` can come up empty — so
a claim on the output never grounds and the gate blocks it.

`clew.session()` closes both gaps: it records a **real** run AND writes the
`file_hashes` edges **explicitly**, using ONLY clew's zero-dependency pure-stdlib
core — so provenance works even where the full stack can't load, and the edges
are guaranteed regardless of any auto-hook.

## Use it

```python
import scitex_clew as clew

with clew.session(script_path=__file__) as run:
    run.record_input("data/raw.csv")          # hash + link as a run input
    # ... stdlib compute (no numpy/h5py needed) ...
    with open("results/out.json", "w") as fh:
        json.dump(result, fh)                 # write however you like
    run.record_output("results/out.json")     # hash + link as a run output

    clew.add_claim("paper.tex", "value", 42, "0.94",
                   source_file="results/out.json")
```

This writes the `runs` row + the `raw.csv -> run -> out.json` `file_hashes`
edges. The claim on `out.json` then **grounds** through the recorded run to
`raw.csv` — and if `raw.csv` is a registered source, the claim passes the gate.

Module-level convenience (acts on the current session):

```python
with clew.session():
    clew.record_input("a.csv")
    clew.record_output("b.json")
```

Or the imperative pair (also public): `clew.start_tracking(session_id, ...)` /
`clew.stop_tracking()`, calling `record_input`/`record_output` on the returned
tracker.

## Semantics

- **Zero-dep:** uses `hashlib` + sqlite only. No numpy/h5py/scitex import.
- **Not competing with `@stx.session`:** this is clew's OWN recorder writing
  clew's OWN `runs`/`file_hashes` tables — the *inverse* of the observer seam
  (instead of `@stx.session` firing hooks into clew, you call clew directly). It
  does NOT import scitex-session. Use `@stx.session` when the full stack loads;
  use `clew.session()` as the stripped-environment fallback OR to guarantee the
  `file_hashes` edges. Use one per run, not both.
- **Finalization:** the run is finalized on exit — `status="success"`, or
  `status="error"` if the block raised (the exception still propagates).
- **Grounding:** a claim registered against a recorded OUTPUT grounds via the
  recorded run to whatever registered source feeds it (parents are auto-linked
  from `record_input`).
