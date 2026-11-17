---
description: |
  [TOPIC] Unconscious capture
  [DETAILS] Inside an @stx.session run, clew records files opened by ANY Python code (pandas.read_csv, numpy.load, open()) under the project root, and every imported project-local module, as run inputs/outputs — not only stx.io.load/save. Scope rules, dedupe with stx.io, opt-out env var, overhead, and what it cannot see.
tags: [scitex-clew-unconscious-capture]
---

# Unconscious capture (audit hook + imported code)

`stx.io.load`/`save` fire clew's io hooks. Since this release clew ALSO
records, for the life of every `@stx.session` run (activated by the
session start/close hooks — nothing to call):

| What | How | Recorded as |
|---|---|---|
| a file **read** under the project root by any Python code (`pd.read_csv`, `np.load`, `open()`, `json.load(open(...))`) | `sys.addaudithook` on the `open` event; access mode from the flags | run **input**, hashed at open time |
| a file **written** under the project root (`open(p, "w")`, `df.to_csv`, `fig.savefig`) | same hook; `os.replace` of a written temp file follows to its target | run **output**, hashed at session close (last bytes win) |
| an imported **project-local module** (`import helper` with `helper.py` under the root, not installed, not the entry script) | `sys.modules` scan at start; late imports at close | run **input** (`.py` → node class `source`) |

So `clew.slice(claim)` / `clew.chain(...)` now include the data a third-party
loader read and the helper code the result was computed with.

**Project root** = scitex-session's `metadata["project_root"]` (git root,
else the script's directory); older sessions: `git.root`, else script dir.

## Precision rules

- Never records anything whose real path is outside the project root
  (a symlink inside the project that points outside is NOT recorded — load
  such data with `stx.io.load` to record it).
- Excluded under the root: `<script>_out/RUNNING|FINISHED*` (session
  bookkeeping) and the run dir, `.git`, `__pycache__`, `*.py/.pyc` opens
  (code comes from the module scan; `.py` opens are tracebacks), the
  interpreter prefix (in-project venv), `site-/dist-packages`, `.scitex`,
  tool caches, `/proc` `/dev` `/sys`.
- A file the run wrote and then read back is an intermediate, not an input.
- Dedupe with stx.io: same resolved path → one input row; an output whose
  bytes stx.io.save already recorded is not re-recorded.
- Forked children never record through the parent's tracker (pid check).

## Loud, never silent

- Hook cannot be installed (restricted interpreter): WARNING once per
  process; run metadata `capture.audit = "unavailable (...)"`.
- A capture/record failure: WARNING + `capture.errors`.
- An imported module changed on disk during the run: WARNING +
  `capture.code_changed`.
- Per-run summary in run metadata `capture`: `audit`, `project_root`,
  `code_inputs`, `code_changed`, `open_reads`, `open_writes`, `errors`.

## Opt out (performance-sensitive runs)

```bash
SCITEX_CLEW_AUDIT_CAPTURE=0 python script.py   # default: on
```

Disables the `open` capture only (a WARNING says provenance relies on stx.io
alone); imported-code capture stays on. Overhead per `open()` is a few µs on
the cached path — measure with `tests/develop/bench_audit_capture.py`.

## Not seen

C/C++ code that opens files without Python's `open` (HDF5 via `h5py`, some
`pyarrow` readers), spawned (non-forked) subprocesses, and data under a
symlink that leaves the project. Use `stx.io.load` / `clew.record_input`.
