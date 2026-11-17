---
description: |
  [TOPIC] Unconscious capture
  [DETAILS] Inside an @stx.session run, clew records files opened by ANY Python code (pandas.read_csv, numpy.load, open()) under the project root, data files read from OUTSIDE the root (shared datasets, sibling projects, in-project symlinks to elsewhere) as EXTERNAL inputs, and every imported project-local module, as run inputs/outputs — not only stx.io.load/save. Scope rules, external-input boundary + exclusions, dedupe with stx.io, opt-out env vars, overhead, and what it cannot see.
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
| a data file read **outside** the project root (`/data`, `/scratch`, a NAS mount, `~/datasets`, a sibling project's outputs) or through an in-project **symlink** whose target is outside (`data/raw -> /mnt/shared/raw`) | same hook; `stx.io.load` / `clew.record_input` of such a file too | **external input**: resolved path + hash + `external = {via: link path used, size, mtime}` |

So `clew.slice(claim)` / `clew.chain(...)` now include the data a third-party
loader read and the helper code the result was computed with.

**Project root** = scitex-session's `metadata["project_root"]` (git root,
else the script's directory); older sessions: `git.root`, else script dir.

## External inputs (the capture boundary)

A read whose real path leaves the project root is an **external input**: an
ordinary input edge (so `slice` / `chain` / `verify` follow it) flagged
`external`. A slice cannot bundle it, so:

- `clew slice` marks it `[EXTERNAL: outside the project, not bundled]` at
  every level; `to_dict()["required_not_bundled"]` lists `path`, `hash`,
  `size`, `via`, `mtime`, `runs` — what a re-run needs at those paths.
- `clew verify` hash-checks it like any input: changed → `STALE_LINEAGE`
  (18); **absent on this machine → `EXTERNAL_MISSING` (22)**, never a pass.
- WARNING at session close (`session S depends on N file(s) outside the
  project: …`) and a `RuntimeWarning` at `add_claim` (`claim X depends on N
  file(s) outside the project: … — the slice cannot bundle them`).

Never recorded as external (precision): the interpreter (`sys.prefix`,
`base_prefix`, sysconfig/site paths), `site-/dist-packages`, `__pycache__`,
`.py/.pyc`, directories of imported packages (editable installs, package
data), `/proc /sys /dev /etc /usr /lib* /bin /sbin /boot /run /var /snap
/nix /opt` (+ macOS `/System /Library /private`), `tempfile.gettempdir()`,
`$SCITEX_DIR` (`~/.scitex`), hidden dot-paths (`~/.cache`, `~/.config`, …;
not a dot-dir that is an ancestor of the project), directories, non-regular
files. Writes outside the root are not outputs (only remembered so a
read-back is not an input).

```bash
SCITEX_CLEW_EXTERNAL_INCLUDE=/opt/lab-data:~/.cache/huggingface  # override built-in exclusions
SCITEX_CLEW_EXTERNAL_EXCLUDE=/mnt/scratch-junk                    # always wins
SCITEX_CLEW_EXTERNAL_CAPTURE=0                                    # stop recording externals only
```

Same keys in `.scitex/clew/config.yaml`: `capture: {external: {enabled,
include: [...], exclude: [...]}}`.

## Precision rules

- Outside the root: only regular data files that pass the external policy
  above, recorded as external inputs.
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
  `code_inputs`, `code_changed`, `open_reads`, `open_writes`,
  `external_inputs`, `external` (the policy), `errors`.

## Opt out (performance-sensitive runs)

```bash
SCITEX_CLEW_AUDIT_CAPTURE=0 python script.py   # default: on
```

Disables the `open` capture only (a WARNING says provenance relies on stx.io
alone); imported-code capture stays on. Overhead per `open()` is a few µs on
the cached path — measure with `tests/develop/bench_audit_capture.py`.

## Not seen

C/C++ code that opens files without Python's `open` (HDF5 via `h5py`, some
`pyarrow` readers) and spawned (non-forked) subprocesses. Use `stx.io.load` /
`clew.record_input`.
