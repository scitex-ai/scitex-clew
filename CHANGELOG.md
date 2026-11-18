# Changelog

All notable changes to `scitex-clew` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

Fixes a 0.30.0 regression: a run killed before it closed lost its record.
0.30.0 queued a session's rows in memory and wrote them at close. A process
killed outright (`SIGKILL`, the OOM killer, a container or agent-harness
timeout, a dead kernel) never reached that write, so every row it had
recorded was lost and the run stayed `running`. Agent harnesses kill runs on
timeouts all the time.

### Added
- **Per-session recording journal** (`scitex_clew._journal`). Each queued
  row is also appended, as it is queued, to
  `$SCITEX_CLEW_JOURNAL_DIR` (default `~/.scitex/clew/journal`)
  `/<host>/<session>.<pid>.jsonl` (mode 0600). Each append is one `os.write`
  of one JSON line, with no `fsync`: the bytes are in the page cache and
  survive the process's death. Files the `open()` capture hashed at open
  (inputs, executed code) and files opened for writing are journaled too.
  When the OUTERMOST store transaction that wrote rows commits, a `flushed`
  marker is appended. A closed session deletes its journal. The owner holds
  an `flock` on the file, and the kernel releases it whatever kills the
  process. The header stores a SHA-256 fingerprint of the store DSN, never
  the DSN itself.
- **Recovery** (`scitex_clew.recover_journals()`,
  `clew recover-journals [--dry-run]`). It also runs quietly at every session
  start and every `clew` command. For each journal on this machine whose
  owner is dead and whose store fingerprint matches, it:
  - writes the rows queued after the last marker;
  - records the captured inputs a close would have recorded (first record
    wins);
  - re-binds every input to its producer;
  - closes a still-`running` run as **`killed`**, with `finished_at` set to
    the journal's last write and `metadata["clew_recovery"]` attached;
  - deletes the journal.

  Replay is idempotent (upserts on the row identity). It skips journals of
  live processes and journals written for other stores.
- **SIGTERM / SIGHUP handling.** Where the handler is the default and the
  code runs on the main thread, clew records the signal and replays the
  session's own journal, which closes the run as `killed` with
  `exit_code = -signum`. It then restores the default action and re-sends
  the signal, so the process still dies of it. If the signal interrupted a
  store write, the handler writes nothing and the next start replays the
  journal instead.
- **Time-bounded flush.** `SCITEX_CLEW_FLUSH_SECONDS` (default 30) is the
  longest the oldest queued row waits before a later recording writes the
  queue. This keeps a long run's rows visible to other processes.
- `VerificationDB(project=...)` pins the project scope, for replaying another
  project's journal.
- Env vars `SCITEX_CLEW_JOURNAL` (`0` turns the journal and the signal
  handlers off), `SCITEX_CLEW_JOURNAL_DIR`, `SCITEX_CLEW_FLUSH_SECONDS`.

### Changed
- An interpreter that exits with a session still open (the script returned
  without closing it, `sys.exit`, an uncaught `KeyboardInterrupt`) now
  records the capture and closes the run as **`incomplete`**. Before, it
  flushed the rows and left the run `running` forever.
- `killed` and `incomplete` join `failed` / `error` as failed run statuses
  for `verify`: such a run's files are not evidence.

### Not recorded for a killed run
- The bytes of files the run only opened for writing are not recorded. A
  clean close hashes them, but a killed run's output may be partial. They
  are listed in `clew_recovery.unhashed_writes`. Outputs recorded through
  `stx.io.save` / `record_output` are hashed when saved, so they are kept.
- Modules first imported after the session started, and symlink metadata.

### Measured (`bench_e5_cost.py`, private local Postgres, 2 interleaved rounds; 0.30.0 -> this)
- A journal append costs 6.8 µs per row (20k rows, in-process). That is
  about 0.4% of the ~1.6-2 ms a recorded input costs.
- One fresh process reading 1000 inputs, with hooks on minus no hooks:
  1.72 / 2.14 ms per input before, 2.08 / 1.81 ms per input after. The
  difference is within this shared host's run-to-run noise.
- N1000-K10 (11 sessions, 1010 inputs), recording CPU: 1.44 / 1.37 s
  before, 1.48 / 1.75 s after. Wall time: 2.89 / 3.08 s before, 3.36 /
  2.79 s after.

## [0.30.0] — 2026-11-18

Performance release driven by the paper's E5 cost measurement: `clew verify`
is now linear in the claim's slice and independent of the rest of the
project, and recording no longer pays a durable commit per file. Nothing
recorded changes — same rows, roles, hashes and lineage (asserted by
`tests/scitex_clew/test__tracker_batch.py`). Measured with the new
`tests/develop/bench_e5_cost.py` (real stx.io + session hooks + Postgres).

### Added
- **`SCITEX_CLEW_CAPTURE=0` — whole-capture off switch.** The
  `@stx.session` / `stx.io` hooks then open no run, record no file, install
  no audit hook and never connect to the store; one WARNING per process says
  recording is off. Explicit calls (`clew.session()`, `record_input`,
  `add_claim`, `verify`) still run. A no-recording baseline no longer needs a
  stub. Documented in README ("Turning Recording Off") and the
  `20_env-vars` / `16_unconscious-capture` skill leaves.
- `tests/develop/bench_e5_cost.py`: recording overhead (cold one-session
  processes: hooks on / no hooks / switch off) and per-claim verify cost on
  E5-shaped synthetic projects, with unrelated bulk in the same project and
  in a second project.

### Changed
- **verify reads each run once, in SQL.** Per-session reads
  (`get_file_hashes`, `get_frozen_files`, `get_external_files`,
  `get_file_records`) were each a scan of the WHOLE `file_hashes` table
  decoded in Python, and a verify made about eight of them per run of the
  slice — cost grew as (slice runs) x (project rows): 21 s for a
  101-run / 1101-file slice. They are now views over ONE SQL-filtered query
  per session (`session_file_records`), and a verify pass shares a read
  cache (`_chain/_pass_cache.PassRecords`: session rows, run rows, producer
  lookups) across the slice walk, every per-run check and every claim of the
  pass. Lookups by path / hash / parent (`find_session_by_file`,
  `find_sessions_by_files`, `find_sessions_by_hash`, `hosts_for_hash`,
  `get_children`, `get_parents`, `get_verification_history`, `list_runs`)
  filter (and page) in SQL too.
- **A project's reads no longer decode other projects' rows.**
  `ProjectScopedStore.rows()` filtered the project scope client-side, so
  every whole-project read decoded every project on the host; the scope is
  now a SQL predicate.
- **A verify pass opens the claims store once**, not three times per claim
  (~0.1 s each).
- **Recording batches its writes.** A session's file rows are queued and
  written in ONE transaction (`_db/_deferred.py`) at close, when the queue
  reaches 500 rows, when anything in the process reads the store
  (read-your-writes), at store close and at interpreter exit — instead of
  one durable commit (~4 ms of disk wait) per recorded file. Inputs' producer
  binding happens at flush in one lookup, with the lineage resolver's rule
  (newest producer of those bytes recorded no later than the input), which
  picks the producer a load-time lookup would have; `tracker.parent_session`
  reads through the queue. Rows carry the time they were recorded, not
  flushed. A process killed outright (`SIGKILL`) before close loses its
  queued rows; such a run never closed and stays `running`.
- **A file stx.io loads is hashed once.** The `open()` audit capture hashes
  the bytes at open; the load hook now reuses that hash when the file's
  `(size, mtime_ns, inode)` is unchanged, instead of reading it again.
- The verification-results and session-parent stores are opened on first
  use (a recording session rarely needs them); their target and project
  scope are still fixed when the database handle is created.

### Measured (`bench_e5_cost.py`, local Postgres; before -> after)
- `verify --strict` (in-process) of the claim on a 101-run / 1101-file
  slice: 21.1-23.4 s -> 0.34 s; 11-run / 1011-file slice: 2.09 s -> 0.23 s;
  a 1-run claim: 0.26 s -> 0.15 s.
- Same 11-run / 110-file slice with 40 unrelated runs (2000 rows) in the
  project and a second project in the store: 9.21 s -> 0.10 s (0.06 s
  without the bulk — the project's size no longer matters).
- One session reading 1000 inputs (whole fresh process): 5.61 s -> 2.02 s
  (0.41 s with no hooks; 0.38 s with `SCITEX_CLEW_CAPTURE=0`): ~5.2 ms ->
  ~1.6 ms per recorded input. The rest is `Store.put`'s per-row statements in
  scitex-dev (no bulk put yet). 101 sessions x 11 inputs in one process: CPU
  6.1-6.8 s -> 5.1 s (wall is dominated by disk waits on a shared host and
  varied 22-55 s before / 8-35 s after).

## [0.29.0] — 2026-11-18

Minor release: claim values are checked, not only their source files, plus
two slice/notebook fixes found by the paper's E2/E3 instruments. New exit
code **24 `VALUE_UNCHECKED`** (warning by default, error under `--strict`):
a value claim without `source_keys` that a search of its source cannot
justify. A claim text that disagrees with its registered `value` is now
`VALUE_MISMATCH` (21). Claims whose stated numbers are absent from their
sources may newly warn (default) or fail (`--strict`).

### Fixed
- **Slice no longer chains same-bytes reruns through a read-back.** When a
  run read a file `F` at hash `h` and rewrote `F` with the same `h` (a script
  run twice that reads its own previous output), the second run's input edge
  pulled the first run into the level-1/2 slice, so it held two producers of
  `h` where one suffices (paper E2 minimality run). A demanded output is now
  credited to its ORIGINATING producer: the slice follows such read-back
  rewrites back to the run that first produced `h` (whose `F` input had
  different bytes, or none), which is sufficient whatever the later
  rewriters did internally. Applies to `clew slice` levels 1-2,
  `chain/dag --minimal` and claim verification; a real chain (`F@h1 ->
  F@h2`), a rewriter kept for ANOTHER output (it keeps its `F` input and that
  input's producer), the level-0 closure and full-chain verification are
  unchanged. New `scitex_clew._chain._readback`; the level-1/2 walk moved to
  `_chain/_slice_walk.py`.
- **The claim text is checked against the registered value.** A claim that
  registered both a display string (`claim_value`, what the manuscript shows)
  and a structured `value` was verified on `value` alone, so a manuscript
  number that drifted from its registration passed (`claim_value="1.375"`,
  `value=0.25`, source 0.25 -> OK; the paper's planted-fault run caught 0/27).
  Every numeric leaf of `value` must now be written in the text, within the
  declared tolerance or the text's own precision; otherwise `VALUE_MISMATCH`
  (21). The parser reads `%`/`\%` (as a percent or a proportion), `1.2e-3`,
  `1.2 × 10^-3` / `\times 10^{-3}`, `10⁻³`, thousands separators, unicode
  minus, and treats a number after `±`/`\pm` as an uncertainty. The same
  parser lets a text-only claim such as `"p = 0.003"` or `"45.3%"` compare
  against its located source value (it used to be an exact string match).
- **A value claim without a locator is never verified silently.** With no
  `source_keys`, verify compared nothing and `--strict` passed on the source
  file's hash alone. A claim that states a value (a `value`, or a number in a
  `value`/`statistic` claim's text) is now searched for in its structured
  source (JSON/YAML leaves, CSV/TSV cells, `.npy` elements up to 100k). A
  match at exactly one location justifies it and is reported with that
  location; no match, several matches, or an unsearchable source leave it
  **`VALUE_UNCHECKED` (new exit 24)**: a warning by default, an error under
  `--strict` (the posture of `NO_LINEAGE`: absent evidence, not a
  contradiction — clew cannot prove a value wrong without a locator). The
  claim's status is `suspect`, not `verified`. (23 is
  `ENV_NOT_REPRODUCIBLE`, 0.28.0.)
- **A notebook run records its notebook in ONE role, as a `.py` run records
  its script.** An in-cell `@session` recorded the `.ipynb` as the run's
  `script` AND as an `input` row, filing the run's own code as data it read
  (the paper's E1 capture precision on notebook probes was 0.80 for that
  extra row alone); a `%run script.py` session likewise recorded the script
  as both `script` and `input`. Now the run's script — notebook or `.py` — is
  `script` only; a `%run` session's driving notebook (code the run did not
  start from) stays an `input` row (identity = code cells). Editing a code
  cell still stales the run (`STALE_LINEAGE`, 18) through the script check
  (`script_hash` is the `ipynb-code-v1:` code identity), and `clew slice`
  still lists the code a notebook run's recipe executes among its `files`.
  Rows recorded by 0.26.0–0.27.0 keep their extra input row.
- **`clew execute-notebook` (and `clew rerun` of a notebook run) no longer
  fails intermittently with `ZMQError: Address already in use`** when kernels
  start concurrently. jupyter_client's tcp transport picks the kernel's five
  ports in the launching process (bind to port 0, read, close) and the kernel
  binds them later in its own process; in between another starting kernel can
  be handed the same port (`LocalPortCache` only deduplicates within one
  process). The kernel now talks over Unix-domain (`ipc`) sockets in a fresh
  private directory per execution, so no two kernels can share an address
  (tcp is kept on Windows, which has no `ipc` kernels). The directory is made
  under the temp dir when the socket paths fit the OS limit (`sun_path`, 107
  bytes on Linux), else under `/tmp`, so a deep `$TMPDIR` (a CI work tree)
  still works. The notebook tests that
  launch kernels through `nbconvert` use the same transport.

## [0.28.0] — 2026-11-18

Minor release: non-reproducible environment requirements are flagged
(PR #204, exit code 23 `ENV_NOT_REPRODUCIBLE`; warning by default, error
under `--strict`). Reads scitex-session >= 0.5.0 `package_provenance`.

### Added

- **Non-reproducible environment requirements are flagged** (exit code
  `23 ENV_NOT_REPRODUCIBLE`). A run's record said `name==version` for a
  dependency the agent had patched and rebuilt locally; it looked identical
  to the index release, and a replay with the index release failed. With
  scitex-session >= 0.5.0 each run records `package_provenance` (PEP 610
  install source, a content fingerprint of the installed wheel, installed
  files edited since installation). Slices carry it
  (`requirements()["provenance"]`, `runs_without_provenance` for older
  records) and `ProvenanceSlice.environment_findings()` /
  `clew slice` / `clew verify` report each requirement that is not
  reproducible from the record:
  - `not_from_index` — installed from a local dir, local archive, editable
    source, VCS or remote archive;
  - `edited_after_install` — an index install whose files were edited,
    overwritten or deleted after installation;
  - `content_differs` — the same version installed here has another
    fingerprint (the E2 case: patched rebuild recorded, index release here);
  - `edited_here` — the same build installed here, edited after install.
  **Severity: warning by default, error under `--strict`.** Default `verify`
  answers "do the recorded hashes and lineage still hold here?" — a locally
  built dependency does not make any recorded hash false, so it is surfaced
  (`warnings`, per-claim `environment`) without failing. `--strict` is the
  reproducibility contract, so there it fails with exit 23 — unless the
  project sets `verify.severity.env_not_reproducible` explicitly (e.g. it
  accepts an editable sibling checkout as policy). It ranks just above
  `NO_LINEAGE`: every integrity / lineage failure outranks it. Version drift
  (another version, or not installed here) is not this finding.

## [0.27.0] — 2026-11-18

Minor release: temp-dir files that pre-existed the process are recorded as
external inputs (PR #203). Runs that read hand-staged temp state now verify
as `EXTERNAL_MISSING` (22) when it is gone instead of passing silently.

### Changed
- **Temp-dir files that pre-existed the process are external inputs.** The
  external-input boundary used to drop the temp dir wholesale, so a scratch
  dir (or symlink) a shell command staged under `/tmp` before a run, and that
  the run then read, left no trace: the minimal DAG looked complete and every
  replay failed (found in the paper's E2 replay of agent-written projects).
  The rule is now by ORIGIN, not by name: under a temp root (`$TMPDIR`,
  `/tmp`, `/var/tmp`) a regular file is recorded — hashed, listed as
  required-but-not-bundled, `EXTERNAL_MISSING` (22) when gone — iff its
  `max(mtime, ctime)` predates the process's start (`/proc/self/stat`;
  elsewhere clew's import time, erring towards recording). Files the run, its
  children, or the same process earlier made (scratch round-trips,
  matplotlib's fallback config dir, a Jupyter kernel's cell/runtime files)
  stay unrecorded. `metadata["capture"]["external"]["temp"]` records the
  roots and threshold. `SCITEX_CLEW_EXTERNAL_EXCLUDE=$TMPDIR` restores the old
  behaviour; an INCLUDE prefix under temp records everything there.

### Added
- **Pre-existing temp-dir symlinks are part of the record.** A symlink under
  a temp root that the run went through and that pre-existed the process is
  recorded in `metadata["links"]` with `"external": true` (its `recreate` is
  the absolute location it named). `verify` reports it gone as a missing
  external input (`EXTERNAL_MISSING`), not a stale lineage; slices list it in
  `required_links()`.

### Fixed
- The test suite's subprocess-coverage `.pth` shim no longer prints a
  traceback in every child interpreter when `coverage` is not installed.

## [0.26.0] — 2026-11-18

Minor release: notebook-produced claims (#199, PR #200). New slice field
(`reruns`), a new stored-hash scheme for notebook code inputs
(`ipynb-code-v1:`), and a new command (`clew execute-notebook`); existing rows
and behaviour unchanged. Pairs with scitex-session >= 0.4.0.

Notebook-produced claims (#199). Pairs with scitex-session >= 0.4.0, which
records a Jupyter kernel's notebook as `entry = {"kind": "notebook", "path",
"invocation", "code_sha256", ...}` (scitex-ai/scitex-session#77).

### Added
- **The notebook is a code input of the run.** For an in-cell `@session` (the
  notebook is the run's `script_path`) and a `%run script.py` session alike,
  the `.ipynb` is recorded as an `input` row, so `clew slice` lists it and
  `clew verify` flags an edited notebook. A `%run` script is also recorded as
  an input row (byte hash): code the notebook ran.
- **Notebook identity = its code cells** (`ipynb-code-v1:<sha256>`, the digest
  scitex-session records as `code_sha256`; shared conformance vector).
  Executing the notebook again or saving new outputs / execution counts /
  metadata does not stale its runs; editing a code cell does. The scheme
  travels with the stored value: every verifier re-hashes through
  `hash_like(path, recorded)` (bytes unless the recorded value carries the
  prefix), so an `.ipynb` recorded as data keeps its byte hash.
  `hash_code(path)` gives a run script's identity.
- **Explicit re-execution recipe** in slices: `to_dict()["reruns"][sid] =
  {"kind": "notebook", "path", "cwd", "python", "argv", "command", "env",
  "invocation", "script", "caveat"}` — run the notebook headless, top to
  bottom, from the recorded cwd; never a replay of the kernel's argv.
- **`clew execute-notebook NB [--cwd DIR]`** (`python -m scitex_clew execute-notebook`)
  executes a notebook headless with nbclient (kernel cwd = DIR, notebook file
  untouched, `$SCITEX_NOTEBOOK_PATH` set for the kernel). nbclient /
  nbformat / ipykernel are optional: without them it exits 3 and says what to
  install. clew still imports nothing beyond its own dependencies.
- **`clew rerun` of an in-cell notebook run** executes a sandbox copy of the
  notebook (kernel in the recorded cwd) and compares outputs as for scripts;
  refused with an install hint when the recorded interpreter has no notebook
  executor.

### Changed
- `dev` extra: `scitex-session>=0.4.0`, `ipykernel`, `nbclient`, `nbconvert`,
  `nbformat` (real-kernel tests).

## [0.25.0] — 2026-11-18

Minor release: clew's project root — store scope / project id, `claims.json`,
hints, and **project-scope config** — now follows the same rule as
scitex-session 0.3.7, and inside a session is the session's recorded root.
Config semantics change (a non-git project now HAS a project scope; a git
repository at `$HOME` no longer is one), hence a minor bump. No schema change.

### Changed
- **One project-root rule for clew and scitex-session.** Inside an
  `@stx.session` run clew adopts `metadata["project_root"]` for the whole run
  (set before the run record opens, cleared after close). Standalone, the new
  `scitex_clew._core._project_root.resolve_project_root` applies the session's
  order: explicit > `$SCITEX_SESSION_PROJECT_ROOT` > git root (not at
  `$HOME`) > nearest marker (`.git`/`.hg`/`.svn`, `pyproject.toml`,
  `setup.cfg`, `setup.py`, `scitex/.scitex-structure-version`,
  `scripts/`+`config/`) > cwd > script dir (warned). Never above `$HOME`/`/`,
  no mount crossing, `.scitex/` is not a marker. Previously clew walked up
  from cwd for `.git`/`pyproject.toml` only, with no `$HOME` stop, so a
  non-git project used from `scripts/` was scoped to `scripts/.scitex/clew/`.
- **Project-scope config** (`_core/_config`) uses the same root instead of
  git-only discovery.
- Capture's fallback for session managers that send no root uses the same
  rule (was: git root, else script dir).
- The root and the rule that chose it are reported by
  `scitex_clew._db._paths.project_root_info()` and recorded on every run as
  `metadata["clew_project_root"]` (`project_root`, `project_root_source`,
  `project_root_marker`, `via` = `argument`/`session`/`detected`).

### Added
- `tests/scitex_clew/conformance/project-root-vectors.json`: shared detection vectors,
  byte-identical in scitex-session, run by both suites.

### Migration
- A project id older clew left where the old rule pointed (e.g.
  `proj/scripts/.scitex/clew/project-id`) is detected: clew keeps using it
  (so history is not split), moves nothing, and warns with the exact
  `mkdir -p … && mv …` command. If both locations hold different ids, a
  TWO-ids warning names both and the command to keep the old one.

## [0.24.3] — 2026-11-18

Patch release: symlinks a run went through are recorded, sliced and verified
(#192); claims registered during a session follow its run-dir move (#191).
No schema change.

### Fixed
- **Symlinks a run went through are recorded, sliced and verified** (#192).
  An input opened through an in-project symlink (`alias -> data`,
  `sub/config -> ../config`, an absolute link, a chain `a -> b -> data`, a
  symlinked directory, imported/exec'd code under a linked dir, or a link to
  outside the project) was recorded by its resolved path only, so a re-run
  of the slice — which opens the LINK path — failed. Every symlink traversed
  to a recorded file whose link file lies inside the project is now kept in
  the run's `metadata["links"]` (`link`, verbatim `target`, `resolved`,
  `in_project`, `recreate`, `kind`, `files`; new `scitex_clew._links`). The
  walk is kernel-faithful (`link/..` climbs from the link's target; the
  capture no longer normalises `..` lexically before resolving). Slices carry
  them (`ProvenanceSlice.links`, `required_links()`, `to_dict()["links"]`;
  `clew slice` prints `SYMLINKS TO RECREATE`): `recreate` keeps a relative
  in-project target verbatim (chains stay chains), turns an absolute
  in-project target relative, and points an external one at its resolved
  path — whose file stays in `required_not_bundled`, now with the `links`
  reaching it. `verify` checks each link (exists, still resolves to the
  recorded target; `FileVerification.link`), besides the target's hash. No
  schema change.
- **Claims registered during a session follow its run-dir move** (#191).
  `relocations` at close now also rewrite every claim of the project whose
  `source_file` (or manuscript `file_path`) lies under the moved directory,
  in one store transaction, and bind a claim registered before its source
  was recorded to the closing session when the bytes match; `claims.json` is
  re-exported. Previously such claims kept the `RUNNING/` path and verified
  `SOURCE_MISSING`.

## [0.24.2] — 2026-11-17

Patch release: the scitex-session 0.3.6 close payload is applied —
relocations, `python -c` rerun, environment in slices (#188). No schema change.

### Added
- **scitex-session >= 0.3.6 close payload is applied** (#188) (clew needs no
  scitex-session at runtime; older sessions keep working):
  - `relocations` (run dir moved `RUNNING/<ID>` -> `FINISHED_*/<ID>` before
    the close hooks): recorded paths are re-keyed before the run is
    finalized — tracker maps and the session's `file_hashes` rows
    (`VerificationDB.relocate_session_paths`, old rows hidden), declared
    `derived_from` included — so run-dir outputs verify at their final path.
    An output absent at its new path is warned about.
  - `python -c` runs (`entry.kind == "command"`, no script) are re-run as
    `python -c <entry.command>` from a sandbox mirroring the recorded cwd;
    refused loudly when only the command hash was recorded or the text does
    not match it. Run-dir outputs are compared as `<run-dir>/<path>` (the
    dir name carries the run id), for script runs too.
  - Slices carry the software environment: `ProvenanceSlice.environment`,
    `requirements()` / `to_dict()["environment"]` (packages + versions,
    cross-run version conflicts, `unresolved_imports`, runs with no package
    record); `clew slice` prints them.
- dev extra: `scitex-session>=0.3.6` for the real-session integration tests.

### Changed
- `VerificationDB`: content-hash queries moved to `_db/_content_queries.py`,
  relocation to `_db/_relocate.py`; tracker helpers to `_tracker_batch.py`
  (imports unchanged).

## [0.24.1] — 2026-11-17

Patch release: project code executed without importing (runpy, exec,
exec_module, %run) is recorded as a code input (#185). No schema change.

### Added
- **Executed-not-imported project code is a code input** (#185). `runpy.run_path`,
  `exec(compile(open(p).read(), p, "exec"))`, `exec(open(p).read())`,
  `importlib.util.spec_from_file_location` + `exec_module` (not in
  `sys.modules`) and IPython `%run` left no module behind, so a claim's slice
  lacked that code. The `exec` audit event (`co_filename`) and, for
  `exec(<str>)`, the `compile` event (source matched by newline-normalised
  hash to a `.py` file the run read; exact match only) now record it, under
  the same project-root / external-input rules; library and stdlib code, the
  temp dir and the entry script are excluded. Run metadata
  `capture.exec_code_inputs`. No schema change.

### Changed
- `scitex_clew._capture` is split: `RunCapture` lives in `_capture/_run.py`,
  exec/compile capture in `_capture/_code.py` (imports unchanged).

## [0.24.0] — 2026-11-17

Minor release (new feature): external inputs — files read from outside the
project root and in-project symlinks to elsewhere are recorded, sliced as
required-but-not-bundled, verified, and warned about (#182). New exit code
22 `EXTERNAL_MISSING`.

### Added
- **External inputs** (#182) — files a run reads from OUTSIDE its project root
  (shared datasets on `/data` `/scratch` / a NAS mount / `~/datasets`,
  downloads, a sibling project's outputs) and in-project symlinks whose
  target lies outside (`data/raw -> /mnt/shared/raw`) were silently dropped
  by the 0.23.0 audit-hook capture. They are now recorded as input rows
  flagged by a new `file_hashes.external` column (`{via, size, mtime}`;
  `file_path` = resolved target, `hash` = bytes read). Precision: the
  interpreter/stdlib/site-packages, imported package directories, system
  trees, the temp dir, `$SCITEX_DIR`, hidden dot-paths, directories and
  non-regular files are never recorded (`scitex_clew._capture._external`).
  Configurable via `SCITEX_CLEW_EXTERNAL_INCLUDE` / `_EXCLUDE` /
  `SCITEX_CLEW_EXTERNAL_CAPTURE=0` or `capture.external` in
  `.scitex/clew/config.yaml`.
- `clew slice` marks external nodes at every level and lists them as
  `required_not_bundled` (path, hash, size, via, mtime, runs).
- `clew verify`: new exit code **22 `EXTERNAL_MISSING`** — a claim's
  lineage reads an outside file that is absent on this machine (and nothing
  else failed). A changed external file is `STALE_LINEAGE` as before.
- WARNING at session close and `RuntimeWarning` at `add_claim` when a
  run/claim depends on files outside the project.

## [0.23.0] — 2026-11-17

Minor release (new feature): unconscious file-I/O and project-code
capture inside `@stx.session` runs (#179). Pairs with scitex-session
0.3.5, which sends `metadata["project_root"]`; older sessions still
work (clew derives the root from `git.root` or the script directory).

### Added
- **Unconscious capture inside `@stx.session` runs** (`scitex_clew._capture`,
  activated by the session start/close hooks). Closes the two largest E1
  recall gaps measured on real agent runs:
  - *Files opened outside stx.io* — a `sys.addaudithook` handler on the
    `open` event records files read (→ input, hashed at open) or written
    (→ output, hashed at close; `os.replace` of a written temp file follows
    to its target) by ANY Python code — `pandas.read_csv`, `numpy.load`,
    `open()` — **under the project root only**. Session bookkeeping
    (`*_out/RUNNING|FINISHED*`), `.git`, `__pycache__`, `.py/.pyc`, the
    interpreter prefix, `site-/dist-packages`, `.scitex`, `/proc /dev /sys`
    and anything whose real path leaves the root are excluded. Deduped with
    the stx.io hooks (same resolved path → one edge).
  - *Imported project-local code* — modules whose file is under the project
    root (not installed, not the entry script) are recorded as run inputs at
    start (late imports at close), so `clew.slice` / `chain` include the
    helper code; a module changed on disk during the run is warned about.
  - Loud, never silent: an uninstallable hook or a failed record WARNS and is
    written to run metadata `capture` (`audit`, `code_inputs`,
    `code_changed`, `open_reads`, `open_writes`, `errors`).
  - Opt out with `SCITEX_CLEW_AUDIT_CAPTURE=0` (default on); code capture
    stays on. Benchmark: `tests/develop/bench_audit_capture.py`.
  - Project root: scitex-session's new `metadata["project_root"]`, else
    `git.root`, else the script's directory.
  - Overhead (10k `open()` loop, `tests/develop/bench_audit_capture.py`):
    +0.25 µs/open with no session active, +2.1 µs/open for a cached project
    file, +0.9 µs/open outside the root; 10k distinct project files: hashed
    at open (+94 µs/open) and recorded in one transaction at close (15.8 s).
- `SessionTracker.record_hashed_inputs` — bulk, pre-hashed input recording
  (one producer lookup, one store transaction).

### Fixed
- `find_producer_records` (called once per recorded input, including every
  `stx.io.load`) decoded the project's WHOLE `file_hashes` table and filtered
  in Python: 0.4 s per input at ~10k rows. It now filters in SQL
  (`ProjectScopedStore.search`) (#179).
- A file read inside `scitex_io.save` (e.g. a read-back check) is no
  longer recorded as a run input (#179).

## [0.22.2] — 2026-11-17

Patch release (bug fix only). Pairs with scitex-io 0.6.0, whose
`stx.io.save(..., derived_from=[...])` hands declarations to clew's io hook
and whose public `save_*` helpers now fire it.

### Fixed
- `record_output`: recording the same bytes of a path twice in one run no
  longer erases a `derived_from` declaration. figrecipe records a figure's
  image declared, then the `stx.io.save` that called it fires the io hook
  for the same file undeclared; last-writer-wins dropped the declaration
  and level 2 silently fell back to level 1. An undeclared re-record now
  keeps it, a second declaration is unioned, and new bytes replace it (#173).

## [0.22.1] — 2026-11-17

Packaging-fix release. **0.22.0 was tagged (`v0.22.0`) but never published to
PyPI**: its tag build stopped at the distribution check, so 0.22.1 is the
first published release carrying the 0.22.0 features — see the 0.22.0
notes below for the full list (minimal provenance
slice `clew.slice` / `clew slice`, claim value-vs-source `VALUE_MISMATCH`
(21), `STALE_LINEAGE` (18), `VERIFY_ERROR` (19), the `FAILED` run status,
additive claim-store columns).

### Fixed

- Packaged CLI-audit dictionary `src/scitex_clew/_cli_audit_dict.yaml` synced
  with its source `.scitex/dev/cli-audit-dict.yaml` (it lacked the `slice`
  verb), which had failed the release build's byte-identity check.
- New test `tests/develop/test_packaged_cli_audit_dict.py` asserts the two
  stay byte-identical, so PR CI catches this drift before tag time.

## [0.22.0] — 2026-11-16 (tagged, never published to PyPI)

Minor release: new exit codes `STALE_LINEAGE` (18), `VERIFY_ERROR` (19),
`VALUE_MISMATCH` (21), the `FAILED` run status, the `clew.slice` / `clew slice`
minimal-provenance API, and additive claim-store columns. (0.21.1 was never
published; its changes ship here.)

### Added — file-level minimal provenance slice

- **`clew.slice(target_or_claim, level=1)`** / `clew slice TARGET [--level]
  [--compare] [--json]` returns only the runs and files on paths that end at
  the target (`scitex_clew._chain._slice.ProvenanceSlice`: `.runs`, `.files`,
  `.edges`, `.counts()`, dropped/fallback diagnostics). Levels:
  0 = run-level closure (every input/output of every ancestor run, the
  historical view); 1 = path-pruned (default; drops sibling outputs, their
  consumers and anything on no path to the target — but keeps ALL inputs of a
  kept run, since Clew cannot see inside a run); 2 = additionally honours
  per-output `derived_from` declarations (`record_output(path,
  derived_from=[...])`, and `stx.io.save(..., derived_from=[...])` via the
  io hook once scitex-io forwards it), falling back to level 1 per undeclared
  run. `compare_levels()` reports node/edge counts per level.
- `verify_chain` / `verify_dag` / `verify_claims_dag` / `clew.chain` /
  `clew.dag` / `generate_dag_json` / `generate_mermaid_dag` take
  `minimal=True, level=...`; CLI `chain`/`dag`/`print-mermaid --minimal`.
  `verify_run(..., slice_files=...)` checks only the slice's files.
- **Claim verification checks only the claim's level-1 slice**: a changed
  sibling output elsewhere in a run no longer stales a claim.
- New nullable `file_hashes.derived_from` column (additive store migration).

### Added — claim value vs source, native claim fields

- Claims gain native `value`, `source_keys`, `tolerance`, `metadata` columns
  (additive store migration); `claim_value` stays the display string.
  `source_keys` uses scitex-writer's shape (RFC 6901 `pointer` for
  json/yaml; `row` index or `{column: value}` selector + `column` for
  csv/tsv; per-locator or claim-level `abs_tol`/`rel_tol`, else tolerance
  implied by the written precision). Verification compares claimed vs source
  value: new exit codes `VALUE_MISMATCH` (21) and `VERIFY_ERROR` (19).
  CLI: `clew claim add --source-keys/--tolerance/--structured-value/--metadata
  /--project-root` (JSON values) and `clew claim verify --project-root`.
- `project_root=` on `add_claim`, `list_claims`, `verify_claim`,
  `verify_all_claims`, `verify_claims_dag`, `remove_claim(s_by_prefix)`,
  `supersede_claim(s_by_prefix)` (and `scitex_clew._db._paths.project_root()`
  context manager): scope calls to a project without `chdir`.

### Fixed — session hooks, rerun, claim verify

- Session hooks were registered twice (the scitex_session module id was
  never remembered), so every start/close fired twice.
- `on_session_start` / `on_session_close` no longer swallow errors unless
  `verbose`: failures are warned, recorded (`HOOK_FAILURES`, run
  `metadata.hook_failures`) and re-raised for the session manager to record.
  Start-payload `capture_errors` are warned. The close hook accepts an
  optional `metadata` payload, merged into the run record.
- The "unrecorded outputs" warning now fires: it reads `sdir_out` from the
  scitex-session start payload, counts files newer than `started_at`, skips
  `RUNNING/` and `FINISHED*/`, and reports each unrecorded path.
- `rerun` replays the recorded `argv` from the recorded `cwd` (recorded
  python when present) into a SANDBOX copy (originals are never overwritten;
  runs with outputs outside `<script>_out/` are refused), compares outputs by
  full relative path + full hash, finds the replay by its unique sandbox
  script path (not "newest of the last 5 runs"), and cleans up (sandbox
  removed, replay records hidden). A failing replay is `FAILED`.
- A claim whose lineage walk raised was reported OK in non-strict mode; it is
  now `VERIFY_ERROR`.
- Re-adding a claim id after `remove_claim` left it hidden; it is visible
  again.

### Fixed — back-trace correctness (claim -> minimal, correct DAG)

- **Parents are bound by content hash, not path.** An input is linked to the
  producer that recorded the SAME hash for that path no later than the input
  was loaded (`_chain._routes.resolve_lineage` / `bind_input`). A later run
  overwriting a file no longer re-parents an earlier consumer; a
  byte-identical re-run after the load is not its parent either. Inputs whose
  bytes match no recorded output are reported as unbound (`external` /
  `unmatched`) instead of being guessed. `SessionTracker.record_input` now
  records only that hash-bound parent (not every producer of the path).
- **One resolver.** `rerun_dag`, `verify_dag_strict` claim invalidation,
  `generate_dag_json(session_id=...)` and `mermaid(session_id=...)` now walk
  the same hash-bound resolver as `verify_chain` / `verify_dag`, instead of
  the legacy `session_parents` table or `get_chain`. Leaf producers of a
  target/claim are chosen by content hash (`resolve_producer`).
- **A failed run is never verified.** New `VerificationStatus.FAILED` for runs
  whose recorded status is `failed`/`error`; consumers of their outputs are
  `SUSPECT`; `clew.status()` adds `failed_count` / `failed` (additive keys);
  Mermaid draws such runs and their outputs `failed`.
- **Full hash equality.** `scitex_clew._hash.hashes_match` replaces every
  prefix comparison; only the legacy 32-char truncated sha256 is tolerated.

### Changed

- **Stale lineage fails default claim verification.** New exit code
  `18 STALE_LINEAGE` (config key `stale_lineage`, default `error`): a claim
  whose source hashes fine but whose recorded lineage no longer verifies (an
  upstream input/output/script changed, or a run in it failed) is not
  verified, in default AND `--strict` mode. Previously default mode passed
  it (`OK`) and `--strict` mislabelled it `NO_LINEAGE`. Existing code names
  and integers are unchanged; `NO_LINEAGE` now means only "no lineage at
  all". Severity ranks above `UNVERIFIED`, below `SOURCE_MISSING`.

## [0.21.0] — pending release

### Added

- Leaf-owned GUI at `scitex_clew._django`, using the canonical SDK App/UI
  packages and the same standalone and plugin interfaces. Preserve the
  `clew_app` model label, registry table and initial migration.
- Project-scoped previews with descriptor-relative reads and symlink denial;
  frontend assertions cover project identity, custom mounts and safe rendering.

### Changed

- GUI and development installs require genuine `scitex-sdk>=0.3.0`. Release
  test gates must install all declared dependencies without falling back to
  a reduced environment. Normal GUI installation requires published SDK 0.3.0.
- Private provenance stays unavailable (503) with public Dev 0.62.0 and
  0.62.1, which lack tenant store APIs. No shared-store fallback
  or multiuser RLS qualification is claimed.

## [0.20.1] — 2026-08-31

### Fixed
- **The declared `scitex-dev` floor was too low to install a working clew.**
  0.20.0 shipped `scitex-dev>=0.17.8` while every store resolves through
  `scitex_dev.store.host_store()`. A consumer holding an older scitex-dev
  therefore RESOLVED CLEANLY and then failed at use — measured on
  scitex-python, which pins `scitex-dev==0.28.0`: `uv pip install`
  succeeded, then `ModuleNotFoundError: No module named 'scitex_dev.store'`
  and three clew integration tests failed on all three Python legs. The
  floor is now `scitex-dev>=0.49.2` in both the runtime and `dev`
  dependency sets, so the bad combination is refused at resolve time
  instead of failing silently later.

  The number is measured, and IMPORTING IS NOT THE TEST: 0.43.1 is the
  first release carrying the module and `host_store`, and it imports every
  symbol clew imports — yet a real write-then-read raises
  `TypeError: tuple indices must be integers or slices, not str` inside
  `Store.rows()`. Running an actual record-and-read-back against
  PostgreSQL with the published 0.20.0 wheel: 0.28.0 FAIL (no module),
  0.43.1 FAIL, 0.46.0 FAIL, 0.48.0 FAIL, 0.49.0 FAIL, **0.49.2 OK**,
  0.49.3 OK, 0.50.0 OK, 0.57.0 OK.

  No code change: 0.20.1 is 0.20.0 with honest metadata.

## [0.20.0] — 2026-08-31

### Added — carried forward from `main`
- **0.20.0 is the first PyPI release to contain everything below.** `main`
  had drifted ahead of `develop`: 0.18.0, 0.19.0 and 0.19.1 were tagged and
  published from `main` while the store migration was being built on
  `develop`, and 0.19.2 was version-bumped on `main` but never tagged or
  published at all. `main` was back-merged into `develop` for this release,
  so `export_manuscript_hints()`, `is_claim_grounded()`, the full-length
  sha256 fix and the stable-`claim_id` gate findings are all present here
  alongside the store migration — a release cut from the pre-merge
  `develop` would have silently DELETED them from the published package.
  Two `main`-only fixes were re-implemented against the store-backed
  code rather than merged verbatim, because the SQL they were written
  against no longer exists: the query-path normalization in
  `find_session_by_file()` / `find_sessions_by_files()`, and the stable
  `claim_id` reference in gate findings.

### Changed
- **clew's four stores moved off the retired embedded file engine onto
  the per-host PostgreSQL.**
  `_attest/_stamp.py` (`stamps`), `_db/_core.py` (`runs`, `file_hashes`,
  `verification_results`, `session_parents`), `_citation/_model.py`
  (`citations`) and `_claim/_store.py` (`claims`) now resolve their target
  through `scitex_dev.store.host_store(pkg="scitex_clew", name=...)`.
  Required by scitex-dev #762, which deletes the file-backed `StoreTarget`
  constructor, its `Backend` member, its path type and `DB_SUFFIX`;
  scitex-clew was the fleet's only production caller. No DSN is written
  in source: the one switch is `SCITEX_STORE_DSN`, owned by
  `host_store()`.

### Removed — BREAKING
- **clew has no database file.** `VerificationDB(db_path)` takes no
  arguments and has no `.db_path`; `set_db()`, `use_db()`,
  `get_active_db_path()` and `resolve_db_path()` are gone (`reset_db()`
  replaces them as a cache invalidator, not a store selector); the
  `SCITEX_CLEW_DB_PATH` environment variable is retired;
  `render_dag(db_path=)`, `clew print-mermaid --db` and
  `clew gate-completeness --db-path` are removed; `stats()` reports
  `"store"` instead of `"db_path"`. The legacy default-store auto-rename
  (`_db/_migrate_rename.py`) is deleted with the file notion it served.

### Capabilities lost by the above, recorded rather than papered over
- **Reading a foreign capsule's provenance.** The submission gate globbed
  `<workdir>/.scitex/clew/**/*.db` and judged a capsule on the provenance
  it carried. A capsule carries none now, so the run/claim half of the
  gate is answered by the store of the host running it. The manifest half
  is still read per-capsule from `<workdir>/.scitex/clew/sources.json`.
- **The chain being readable as a plain file by scitex-io.** Gone with the
  file. `claims.json` remains the file-shaped export.
Per-project key namespacing is NOT among them — see below.

### Preserved: per-project record scoping
- **Every store's identity gains a leading `project` field.** The
  per-project database file used to keep two manuscripts' author-chosen
  keys apart; one host database would have collapsed them, with
  `MergeRule.LAST_WRITER_WINS` silently picking a winner — data loss in
  the one system where it is least acceptable. Identities are now
  `(project, claim_id)`, `(project, cite_key)`, `(project, session_id)`,
  `(project, session_id, file_path, role)`, `(project, session_id,
  parent_session)`, `(project, verification_id)` and `(project,
  stamp_id)`.

  The scope is resolved in ONE place — `_db/_scope.py`'s
  `resolve_project_scope()` — and applied to reads and writes alike by
  `ProjectScopedStore`, so a lookup cannot miss a row it just wrote and no
  call site has to remember the scope. `SCITEX_CLEW_PROJECT` overrides it;
  unset, it is the absolute project-root path, which is what the old file
  location keyed on.

  Caveat: a project MOVED to a new path gets a new scope, where the old
  file travelled with the directory. Pin it with `SCITEX_CLEW_PROJECT`.

## [0.19.2] — 2026-07-18

### Changed
- **Pre-submission gate findings now reference a claim by its stable
  `claim_id`, not by `file:L42` alone** (scitex-todo card
  `clew-feat-gate-question-id-completeness`, part (a)). A finding read
  `claim paper.tex:L42 reaches no registered source (unsourced)`; the
  location shifts on every manuscript re-write (insert one paragraph and
  every downstream line number moves), so nothing could correlate findings
  across gate runs, or join them back to a submission keyed by
  `claim_id`/`question_id`. Findings now read
  `claim <claim_id> (<location>)` — clew's actual primary key first, with
  the location retained as a parenthesised locator so a human still has
  somewhere to go. Message text only; no change to which claims fail or to
  the gate's pass/fail verdict.

## [0.19.1] — 2026-07-14

### Fixed
- **Truncated sha256 hash silently broke every hash comparison
  (clew-fix-truncated-hash-comparison).** `hash_file()` / `combine_hashes()`
  (and the archive-hashing equivalents in `_chain/_archive_lookup.py`)
  truncated the sha256 hex digest to the first 32 of 64 characters at WRITE
  time, so the natural external check `get_file_hashes(session)[path] ==
  hashlib.sha256(open(path, "rb").read()).hexdigest()` was ALWAYS False —
  a confident-wrong-answer bug reporting "this session did not produce
  this file" when it did. Found by paper-scitex-clew dogfooding: their own
  registrar concluded 49 claims had zero session lineage when the lineage
  was there the whole time. Fix: return the full 64-char digest everywhere
  hashes are computed; every existing DB-record comparison site already
  compared prefix-tolerantly (or was made to, see below) for backward
  compatibility with pre-existing truncated rows.
- **`_chain/_freshness.py`'s skip-rerun check used exact hash equality**,
  which would have silently regressed to "always stale" for any
  pre-existing DB once truncation was removed (new full hashes never
  equal old truncated ones under `==`). Added a prefix-tolerant
  `_hashes_match` helper, matching the convention already used in
  `_sources/_gate.py`.
- **Inconsistent path normalization silently broke relative-path lookups
  (clew-fix-path-normalization-find-session).** `find_session_by_file()` /
  `find_sessions_by_files()` did not normalize the query path the way
  `verify_chain()` normalizes its own `target` argument
  (`str(Path(x).resolve())`), so a RELATIVE query path silently matched
  NOTHING even though the equivalent absolute path matched fine — same
  file, same DB, two different answers, no error. Fix: both functions now
  resolve the query path the same way `verify_chain` does before querying;
  `find_sessions_by_files` returns results keyed by the caller's original
  (un-resolved) spelling so existing callers see no shape change.

## [0.19.0] — 2026-07-14

### Added
- **`is_claim_grounded(claim_location, *, workdir=".")` — per-claim grounding
  verdict for a live inline editor.** Thin public wrapper around the pure
  `is_grounded` chain-walk gate, returning a richer `GroundingVerdict`
  instead of a bare bool: `{"grounded", "claim_id", "matched_source",
  "reason", "fix_hint"}`. `reason` distinguishes "nothing registered yet"
  (`no_manifest`, amber, fine) from "a manifest exists and this claim fails
  it" (`no_chain_match` / `manifest_untrusted`, red) — collapsing those into
  the same `False` would misreport a claim's actual provenance status.
  `grounded` is guaranteed to never disagree with `is_grounded` /
  `verify_all_claims` on the same claim (including the defensive-True
  no-valid-anchors edge case). Adds `claim_not_found` as a new reason for an
  unresolvable `claim_location`. Owns opening the sources manifest + DB
  internally via `workdir` — callers never construct a `SourcesManifest` or
  DB handle. New CLI `clew grounding <claim-location> [--workdir] [--json]`
  and MCP tool `clew_is_claim_grounded`. The reason set is exported as the
  stable constant `scitex_clew.GROUNDING_REASONS`. Implements
  scitex-writer's ADR 0001 §4 "Inline engine" (scitex-todo card
  `clew-per-claim-grounding-api`).

## [0.18.0] — 2026-07-14

### Added
- **Manuscript-hints producer: `export_manuscript_hints()` (scitex-todo
  card `clew-feat-manuscript-findings-producer`).** A NEW, SEPARATE export
  from `export_manuscript_claims()` — clew is the single producer of
  citation + claim + source-gate HINTS (prose-level "things wrong with
  this manuscript") into scitex-writer's `manuscript-hints/1` feed at
  `.scitex/writer/hints.json` (confirmed by contract with scitex-writer,
  2026-07-14). Each hint: `{id, kind, severity, message,
  location: {file, line, page}, claim_id, source: "scitex-clew"}`, `id`
  deterministic (`hint_<sha256(claim_id:kind)[:12]>` — same precedent as
  `_generate_claim_id`). Reads clew's claim ledger (full-8 resolved status)
  and clew's INGESTED citation ledger (populated from scholar's
  `citation_status`-schema artifact via the existing io-observer seam) —
  never scholar's raw artifact directly. Severity: claim
  mismatch/missing→error, suspect/registered→warning,
  unsourced/exception→advice, verified/frozen→silent (omitted); citation
  stub/unverified→warning, unknown→advice, verified→silent, any
  unrecognized future status→advice (forward-compatible with scholar's
  not-yet-shipped `semantic_mismatch`). MERGE-BY-SOURCE: rewrites only
  `source == "scitex-clew"` entries in `hints.json`, never touches entries
  from other producers (e.g. figrecipe, writer's own hints). New CLI verb
  `clew export-hints` and MCP tool `clew_export_manuscript_hints`.

## [0.17.0] — 2026-07-06

### Added
- **Hard question_id↔claim_id submission-completeness gate (#121).**
  `assert_submission_complete(submission)` (+ non-raising
  `check_submission_completeness`) enforces a strict 1:1 correspondence
  between a consumer submission (`question_id → claim_id`) and clew's
  GROUNDED claims: raises `SubmissionCompletenessError` on any missing
  (answer with no grounded provenance), orphan (grounded claim uncited),
  or non-1:1 cardinality. Builds on `grounded_claim_ids`; adds the
  `clew gate-completeness` CLI verb.
- **`NO_LINEAGE` warning at `add_claim` (#125).** When `source_file` is
  given but no owning `@stx.session` run produced it, `add_claim` now
  emits a `RuntimeWarning` at registration time (naming the file + the
  fix) instead of silently registering a claim that only fails later at
  `clew verify --strict`. Env-silenceable via
  `SCITEX_CLEW_WARN_NO_LINEAGE=0`. (Diagnosis: paper-scitex-clew.)

### Fixed
- **Optional `scitex_logging` import made failure-tolerant (#122).** The
  optional enhancement import was guarded only against `ImportError`, but
  `scitex_logging` does filesystem work at import time (file handlers
  under `~/.scitex/logs`); on a quota/inode-exhausted filesystem it raises
  `OSError`, which propagated and crashed `import scitex_clew` entirely.
  The fallback now tolerates any failure of the optional path, preserving
  the stdlib-logging fallback and clew's zero-dependency import.
- **WAL + `busy_timeout` on clew's store connections (#123).** All
  connections now open with `journal_mode=WAL` + `synchronous=NORMAL`
  (writable opens, best-effort) + `busy_timeout=300000` (always) via a
  single stdlib-only connect helper, mirroring scitex-db's proven PRAGMA
  set WITHOUT taking the dependency (clew stays zero-dep). Fixes the
  immediate "database is locked" failure under concurrent writers.

### Changed
- **Default DB renamed to `clew.db` (#124).** The default store
  is now `<project_root>/.scitex/clew/runtime/clew.db` (reference
  implementation of the fleet `.scitex/<pkg>/runtime/<pkg>.db` convention;
  `.db` is also `stx.io.load`-recognized). A transparent, WAL-safe
  auto-migration renames the legacy store file — the one under
  `runtime/`, or the older flat one beside it — on first open: it
  `wal_checkpoint(TRUNCATE)`s to fold the `-wal` back into the main file,
  then atomically `os.replace`s it — no data loss, even for multi-GB WAL
  DBs. The gate name-match accepts `clew.db` (falling back to the legacy
  name).

### Docs
- **`verify_claim` consumer contract** documented (new skill leaf
  `05_verify-claim-contract.md` + sphinx `verify-claim-contract.rst`),
  fixing the 4-axis contract mismatch a consumer (scitex-live-paper,
  2026-06-28) integrated against: single positional
  `claim_id_or_location` (no `against=`/`bundle_root=`/commit kwargs);
  clew is git-agnostic (host owns checkout; clew re-hashes
  `source_file` at its current on-disk state); the exact return shape
  (top-level `status` ONLY for `not_found`; otherwise
  `claim`/`source_verified`/`chain_verified`/`details`, with
  `status`/`verified_at` inside `claim`); the two status vocabularies
  (`VerificationStatus` enum vs claim statuses `{registered, verified,
  suspect, mismatch, missing}` after the 0.7.0 `partial`→`suspect`
  rename, with client-side transient UI states and paper-level badge
  vocabularies kept explicitly distinct); the claims.json v1.3
  enrichment fields (`resolved_status`/`color`/`display_group`/
  `display_color` + the no-false-green precedence rule); the three-tier
  DB selection precedence (explicit `db_path` incl. `render_dag`'s new
  kwarg → `SCITEX_CLEW_DB_PATH` → project-root walk); and the canonical
  full-7 palette + 4-bucket display collapse, superseding the stale
  pre-v1.3 table (`partial d29922` / `missing cf222e` / light-dark
  variants) some consumers still hold.

## [0.16.0] — 2026-07-04

### Added
- **Session-close provenance-completeness WARN (#45).** On a successful session
  close, if the run wrote output files but recorded ZERO provenance, clew logs a
  WARNING — the #44-class gap (`@stx.session` + `stx.io.save` but empty
  file_hashes). The saves signal is the session OUTPUT DIR (via
  `metadata["output_dir"]`, populated by the save itself), which is independent
  of `on_io_save` — so it catches exactly the case an on_io_save-derived counter
  is blind to. Predicate: `output_dir has ≥1 file AND recorded == 0 → WARN`;
  false-positive-free (read-only/zero-output sessions stay silent). Robust to the
  RUNNING→FINISHED dir move (globs sibling status subdirs for the session-id
  leaf) and DEFENSIVE — silently inert until `metadata["output_dir"]` is present,
  so it is safe today and auto-activates when scitex-session begins sending it.

## [0.15.0] — 2026-07-04

### Added
- **`register-source --from-list <file>`** — compile a human-editable path list
  (one path per line; `#` comments + blank lines skipped) straight into the
  signable JSON `sources.json`, and **`--sources-path`** to target an explicit
  manifest location. So `clew register-source --from-list CLEW_SOURCE_LIST.txt
  --sources-path signed/sources.json` → `clew sign signed/sources.json` is the
  turnkey list→manifest→sign flow.

### Changed
- **Resolver prefers `signed/`.** `resolve_sources_path` tier-3 now resolves
  `signed/sources.json` > `user_definitions/sources.json` (pre-rename) > legacy
  `.scitex/clew/sources.json`, and defaults NEW manifests to `signed/` — so
  register-source, sign, and the gate share one canonical location (no more
  `SCITEX_CLEW_SOURCES` env-var workaround to read a signed manifest).
- **Colored CLI output.** keygen/sign/verify-signatures + register-source now
  use `click.secho` — green `[OK]`, red `[FAIL]`, cyan hints — for readable
  terminal output (no new dependency; the bare install stays zero-dep).
- **Observer-registration warning deduped.** The peer-registration WARNING fires
  **once per peer per process** (not repeated), names the detected peer version
  as a skew hint, and appends "(does not affect keygen/sign/verify)".
- **Actionable "manifest not found".** `clew sign` on a missing manifest now
  points at `register-source` / `--from-list` (keygen only mints the keypair).

## [0.14.0] — 2026-07-04

### Added
- **`grounded_claim_ids` primitive.** A generic query —
  `scitex_clew.grounded_claim_ids(workdir=<capsule>) -> list[str]` — returning
  the sorted claim_ids whose claims are BOTH verified AND grounded (chain reaches
  a registered, and if signing is enforced a valid, source), reusing the gate's
  exact grounding rule. Lets a consumer (e.g. a cohort submission-completeness
  check) diff its own ids against the grounded set — `missing = ids − grounded`,
  `orphan = grounded − ids` — while clew stays generic (it knows nothing about
  the consumer's id semantics). Exposed lazily (accessible as
  `from scitex_clew import grounded_claim_ids`, not in `__all__`).

## [0.13.0] — 2026-07-04

### Added
- **Signature-aware ENFORCEMENT in the source-manifest gate.** Completing the
  `clew sign` trust layer: once a public key is committed at
  `<root>/.scitex/clew/signed/signing.pub`, the registered-source manifest MUST
  carry a valid Ed25519 signature (over the canonical form) or it is treated as
  UNTRUSTED — it anchors NOTHING, so every claim goes unsourced and the gate
  blocks. This is "without the key it can't be run/edited": editing the manifest
  (e.g. injecting a fabricated source to launder a claim) breaks the signature,
  and re-signing needs the private key the solver/agent doesn't have.
  - `SourcesManifest` gains `signing_enforced` + `signature_valid` and a
    `trusted` property; `active` / `anchor_paths()` / `pinned_for()` return
    empty/None for an untrusted manifest.
  - `load_sources_manifest` verifies the signature when a `signing.pub` is
    present (replacing the old no-op seam), logging a WARNING that names WHY a
    manifest is untrusted (unsigned vs tampered) so the failure is visible.
  - **Opt-in, zero behavior change without a committed pubkey**: absent a
    `signing.pub`, `signing_enforced` is False and the manifest is trusted
    exactly as before.
  - **Fails CLOSED**: if a `signing.pub` is committed but verification is
    unavailable (python-cryptography / `[all]` not installed in the verifying
    env), the manifest is untrusted — signing cannot be bypassed by dropping the
    crypto dependency.

## [0.12.0] — 2026-07-04

### Added
- **Manifest signing — the `clew sign` trust layer.** New `clew keygen`,
  `clew sign`, and `clew verify-signatures` verbs plus a
  `scitex_clew._sources._signing` core give source/exception manifests an
  Ed25519 signature, so "without the key it can't be run/edited":
  - `clew keygen` mints an Ed25519 keypair — the private key (mode 0600) stays
    OFF-tree (default `~/.scitex/clew/signing.key`; override via
    `--key` / `$SCITEX_CLEW_SIGNING_KEY`), the public key goes to
    `signed/signing.pub` to be committed. Refuses to overwrite an existing key
    without `--force` (overwriting would invalidate every prior signature).
  - `clew sign [MANIFEST]` signs the CANONICAL form — pretty-JSON of the
    manifest minus its `signature` field, `sort_keys=True`, `ensure_ascii=False`,
    no trailing newline — and writes the manifest back in that same canonical
    serialization, so the on-disk pretty-JSON (minus its signature) IS the
    signed byte string. Any byte change breaks the signature; re-signing needs
    the private key.
  - `clew verify-signatures [MANIFEST]` fail-loud checks a manifest against the
    committed public key (exit 0 iff signed AND valid; nonzero for unsigned or
    tampered).
  - `register-source` / `unregister-source` now write the canonical (sort_keys)
    serialization and DROP any prior signature when they edit the sources — a
    content change invalidates the signature, so the human re-runs `clew sign`.
  - python-cryptography is behind the `[all]` extra; the bare zero-dependency
    install can neither sign nor verify (nor enforce signing).

### Note
- This is the AUTHORING + standalone-verify half. Signature-aware ENFORCEMENT in
  the grounding gate (an unsigned/tampered manifest rejected once a
  `signing.pub` is committed) and the `signed/`-default resolver land in a
  follow-up; the existing gate behavior is UNCHANGED here.

## [0.11.0] — 2026-07-04

### Added
- **Observer entry-point federation.** clew now registers its peer-hook
  registrars under two entry-point groups —
  `scitex_io.observers` → `register_with_scitex_io` and
  `scitex_session.observers` → `register_with_scitex_session`. A peer package
  that scans its group on import (importlib.metadata) and invokes each 0-arg
  registrar will self-activate clew's auto-provenance hooks from
  `import scitex_io` / `import scitex_session` **alone** — with no
  `import scitex_clew` in the mission script (the clean-idiom path that the
  legacy import-time bootstrap could not reach). Acyclic: the peer discovers the
  callable via entry-point metadata and never imports clew in source.

### Changed
- **`register_with_scitex_io` / `register_with_scitex_session` are now
  idempotent**, keyed on the peer module's `id()`: registration happens exactly
  once per distinct peer instance, so the legacy import-time bootstrap and the
  new entry-point activation path can both be live during rollout with no
  double-registration (no double-firing), while a genuine two-instance module
  split still registers each firing instance.
- **`on_io_save` no longer silently bails when no session tracker is active.**
  It now logs (DEBUG) that a save fired with no active session so nothing was
  recorded — the silent `return` had hidden a real symptom (a save firing while
  the tracker wasn't live across session-start→save). DEBUG, not WARNING,
  because out-of-session saves are legitimate and the loud enforcement is
  already the submission gate (an unrecorded save → unsourced claim → blocked).

## [0.10.1] — 2026-07-04

### Changed
- **Observer registration no longer fails silently.** The import-time peer-hook
  bootstrap (`scitex_io` / `scitex_session` observer self-registration) wrapped
  its registration in a bare `except: pass` and ignored the `register_with_*`
  boolean return, so a registration failure (peer hook-API skew, or the
  registrar returning `False`) was completely invisible — clew's auto-provenance
  hooks would silently not fire, with no signal. Registration now routes through
  a new `scitex_clew._observers.bootstrap_register(register, peer_name)` helper
  that logs a `WARNING` when the registrar raises or returns `False` (naming the
  peer and the failure), while still never being fatal to `import scitex_clew`.
  This surfaces the exact "installed but the hook didn't attach" failure mode
  that otherwise requires code-reading to find. Pure visibility — no behavior
  change on the success path.
- **io-hook registration logs its target module identity (DEBUG).** On
  successful `scitex_io` hook registration, clew now logs (at DEBUG) the
  `id()` and `__file__` of the `scitex_io` module it registered against, so a
  "registered True but the hooks never fire" symptom — a *distinct* `scitex_io`
  instance firing a different hook list than the one clew subscribed to — is
  diagnosable by comparing this id with the firing instance's.

## [0.10.0] — 2026-07-04

### Added
- **Zero-dependency `clew.session()` provenance recorder.** A public
  context manager (`with clew.session(script_path=...) as run:`) plus
  module-level `record_input` / `record_output` that write a REAL run
  (the `runs` row + `input->output` file-hash edges) using ONLY clew's
  pure-stdlib core — no numpy/h5py/matplotlib/scitex stack. This lets a
  minimal-mode script in a stripped environment (where `import scitex` /
  the `@stx.session` decorator cannot load) produce `runs >= 1` and a
  source-reachable DAG that passes the provenance gate. A claim
  registered against a recorded output grounds through the recorded run
  to whatever registered source feeds it. It is clew's OWN recorder (it
  does NOT import scitex-session — the inverse of the observer seam) and
  is the zero-dep counterpart to `@stx.session`, sharing the same
  `runs` / `file_hashes` tables; use one or the other per run. The
  underlying `start_tracking` / `stop_tracking` / `SessionTracker` were
  already public — this adds the ergonomic context manager, auto run-id
  generation, and current-session `record_input`/`record_output`
  convenience, and makes the zero-dep recording path discoverable.

## [0.9.0] — 2026-07-03

### Added
- **Pre-submission GateCheck plugin** (`scitex_clew._gate_plugin:provide`,
  registered via the `scitex_dev.gate.checks` entry point). `scitex-dev gate
  --stage=pre-submission <capsule>` now discovers a `clew-source-reachability`
  check that reads the capsule's OWN clew DB (+ registered-source manifest) and
  FAILS a submission whose claims are not backed by a tracked `@stx.session`
  run reaching a registered source — i.e. `runs == 0` (outputs saved outside
  `@stx.session`) OR any backing claim unverified/`unsourced`. This is the
  v0.8.0 UNSOURCED rule packaged as the paper's layer-2 pre-submission gate;
  it runs clew's real gate (`is_grounded` chain-walk, pointed at the capsule DB
  via `use_db`) so a verified-but-ungrounded claim is caught, not just a
  raw-status read. scitex-clew owns the rule + reading its own DB; scitex-dev
  owns the CLI/aggregation and stays clew-agnostic. `scitex_dev.gate` is
  lazy-imported, so the plugin is a graceful no-op when scitex-dev lacks the
  gate runner. Severity/enforcement is config-driven on scitex-dev's side.

## [0.8.1] — 2026-07-03

### Changed
- **Reader display: `unsourced` folds into the amber `suspect` bucket**
  (operator decision). A claim with no registered source reads as the single
  amber "questionable" state rather than a distinct 5th reader bucket. This
  affects ONLY the 4-bucket reader display + legend: `display_groups` now maps
  `unsourced → suspect`; the separate `unsourced` legend row and the
  `unsourced` `display_palette` entry are removed; the `suspect` legend label
  broadens to include "reaches no registered source". The full-8 STATUS is
  unchanged — the `unsourced` verdict, exit code `UNSOURCED=17`,
  `_CLAIM_PALETTE["unsourced"]` (`b26a00`), per-claim `resolved_status`/`color`,
  the 8-state CUD ΔE floor, and DAG rendering all keep `unsourced` distinct for
  author tooling. `attestation.unsourced_count` is now computed from
  `resolved_status` (the folded display bucket no longer carries the count).
  Consumers rendering the fine per-claim `color` palette are unaffected
  (registered stays grey, missing keeps its own red); fold at the reader layer
  with a one-line `unsourced → suspect` colour alias if desired.

## [0.8.0] — 2026-07-03

### Added
- **Registered-source gate + the amber `unsourced` verdict** (verify/export-time
  core). `green = link-hash-consistency` is no longer enough: a claim is only
  green if its provenance chain traces to a human-registered source; otherwise
  it gets the new **`unsourced`** verdict and `clew verify` fails with exit code
  **`UNSOURCED = 17`**. The gate is **opt-in** (no manifest ⇒ zero behavior
  change) and **monotonic** (registering a source can only turn amber → green).
  - **Hash-pinned manifest** `<project_root>/.scitex/clew/sources.json`
    (`schema: sources-1.0`; per-file flat `{path, sha256}`; reserved
    accepted-but-not-enforced top-level `signature` for the signing follow-on).
    Resolution mirrors the DB path: explicit arg > `$SCITEX_CLEW_SOURCES` >
    `<project_root>/.scitex/clew/sources.json`. Loaded entries are
    **tamper-checked** (recompute each file's sha256 vs the pin); a changed
    (`TAMPERED`) or absent (`MISSING`) file is not a trust anchor and is
    surfaced. Malformed manifests fail loud (`ValueError`), never silent-empty.
  - **Chain-walk gate** `is_grounded(claim, manifest, db)` — a pure, reusable
    function (so the planned compute-time observer calls identical logic): walks
    the provenance chain to its root(s) and returns True iff ≥1 file in the
    chain (including the claim's own source) matches a valid registered entry by
    `(path, sha256)`. Laundering guard: a mixed chain with ≥1 registered root is
    grounded; only a chain whose every root is unregistered is `unsourced`.
  - **Status precedence** (`_resolve_status`, opt-in via a new `grounded`
    signal): `mismatch/missing > unsourced > exception/frozen/verified/suspect/
    registered`. `unsourced` **demotes an otherwise-green (verified) claim** —
    being link-hash-verified does not exempt it from the source gate — but hash
    failures still outrank it (a hash-failing ungrounded claim reads red).
  - **CLI** `clew register-source <file>…` (the one sanctioned WRITE path;
    idempotent, hash-pinned), `clew list-sources` (entries + OK/TAMPERED/MISSING),
    `clew unregister-source <file>…`.
  - **Palette** state 8 `unsourced` = burnt amber `#b26a00`, its own reader
    display bucket (not verified, not failed-red). Clears the palette's
    colour-universal-design ΔE floor (CIE76 ≥ 12) against all 7 other states
    across normal/protanopia/deuteranopia/tritanopia (Machado-2009, sev 1.0);
    the new CUD test covers all 28 pairs of the 8-state palette. Mermaid gains
    `unsourced`/`file_unsourced` class definitions.
  - **Public API** (+7): `register_source`, `unregister_source`, `list_sources`,
    `is_grounded`, `load_sources_manifest`, `resolve_sources_path`,
    `SourcesManifest` (`scitex_clew.__all__` 34 → 41).

### Changed
- **claims.json `1.3` → `1.4`** (additive, backward-compatible): adds
  `unsourced` to the status palette, a per-claim `grounded` bool (`null` when
  the gate is inactive), an `unsourced` legend entry, and
  `attestation.unsourced_count`.
- **Unified render feed `1.5-unified` → `1.6-unified`** (additive): adds the
  `unsourced` bucket to `attestation.counts`; an ungrounded claim makes the
  badge `partial`. Consumers ignoring the new fields are unaffected.

### Docs
- New skill leaf `13_registered-source-gate.md` documenting the manifest, the
  `register-source` CLI, the chain-walk grounding gate, exit code `17`, and the
  opt-in + monotonic semantics.

## [0.7.0] — 2026-07-03

### Changed
- **claims.json v1.3 finalized: color-only full-7 status taxonomy** (operator-approved defaults; supersedes the interim v1.3 shape in-place — coordinated with scitex-writer / scitex-live-paper).
  - **Full-7 palette**, each a distinct CUD-accessible hue (bare 6-hex, no `#`): `verified 2da44e` / `suspect d29922` / `mismatch cf222e` / `missing a40e26` (new distinct dark red) / `registered 6e7781` / `exception 8250df` (violet, new) / `frozen 0072b2` (blue, new). Pairwise distinguishability verified under simulated protanopia/deuteranopia/tritanopia (Machado 2009 matrices; all pairs ΔE ≥ 12).
  - **`partial` → `suspect` rename completed** across markers, legend, and DAG (matches `VerificationStatus.SUSPECT`; same state: source verifies, upstream chain failed). Legacy stored `"partial"` rows still surface as `"suspect"` via the read-time normalization.
  - **Per-claim `resolved_status`** (new field): the single full-7 status after color precedence `mismatch/missing > [verified claims only: exception > frozen] > suspect > verified > registered` — chain-provenance overrides (exception violet / frozen blue) apply ONLY to claims that have PASSED verification; a never-verified (`registered`) or chain-broken (`suspect`) claim is never promoted by its chain flags (no false-green). The per-claim `color` follows the resolved status (e.g. a VERIFIED claim over a frozen chain is frozen-blue, not green).
  - **4-bucket reader collapse renamed/remapped**: `display_groups` is now the per-status map `{verified→verified, suspect→suspect, mismatch→failed, missing→failed, registered→suspect, exception→exception, frozen→verified}` — the red bucket is now named **`failed`** (was `unverified`) and **`registered` moved from the red bucket to the amber `suspect` bucket**. `display_palette` keys: `verified/suspect/failed/exception`. Legend renamed accordingly.
  - **ZERO status icons**: the remaining `⊘` (exception) and `🔒` (frozen) glyphs were dropped from `clew verify` / `verify-dag` human output, the image-DAG labels, and the claim list formatter (`superseded` marker is now `-`); plain words (`EXCEPTION`, `FROZEN`) remain. Mermaid + image DAG renderers keep full-7 fidelity: `file_frozen` nodes are now frozen-blue `#0072b2` (previously folded into green) and the image palette's `missing` status uses `#a40e26`.
- **Unified manuscript feed bumped `1.4-unified` → `1.5-unified`** (`export_manuscript_claims` / `clew export-claims --unified`): per-entry `status` uses the renamed 4-bucket set (`failed` replaces `unverified`; stub citations → `failed`; registered claims → `suspect`); adds per-claim-entry `resolved_status` and top-level `status_palette` (full-7) + `display_groups`. `attestation` now carries the **badge facts** consumed by scitex-writer: `badge_state` (`all_verified` | `partial` | `failing` — failing iff any entry is in the `failed` bucket; all_verified iff every non-superseded entry is verified) and a `counts` breakdown `{total, verified, unverified, suspect, failed, exception, mismatch, missing}` (superseded claims excluded from all counts).
- **Root-layout refactor (PS-108b headroom) — no behavior change, public API identical** (`scitex_clew.__all__` unchanged: all 34 names and every lazy attribute resolve exactly as before). Flat root files went 15 → 9: `_stamp.py` + `_registry.py` moved into a new `_attest/` subpackage (external attestation: temporal stamping + remote Clew Registry; `scitex_clew._attest` re-exports both surfaces); `_public_api.py` (the `_LAZY_ATTRS` registry) moved to `_core/_public_api.py`; the pure re-export shims `_dag.py` (→ `_chain`) and `_visualize.py` (→ `_viz`) were removed with all internal importers rewired to the real modules; the dead legacy `_chain.py` (shadowed by the `_chain/` package since the split, never importable) was deleted. Test mirrors moved accordingly (`tests/scitex_clew/_attest/`; `test__chain.py` → `_chain/test__types.py`). Internal-only import paths `scitex_clew._stamp` / `._registry` / `._dag` / `._visualize` / `._public_api` no longer exist — use `scitex_clew._attest._stamp` / `._attest._registry` / `._chain` / `._viz` / `._core._public_api` (private modules; the supported surface is the top-level `scitex_clew.*` names, which are untouched).

### Added
- **Explicit-store rendering: `render_dag(..., db_path=...)`** (clew-feat-render-dag-explicit-store). `render_dag` gains a `db_path` keyword so host-side/post-run callers can target a store outside the current tree (e.g. the store under `<runs>/<capsule>/.scitex/clew/runtime/`) without chdir. Resolution precedence matches `VerificationDB`: (1) explicit `db_path`, (2) `SCITEX_CLEW_DB_PATH`, (3) project-root walk from cwd; the store is activated only for the duration of the call (a `set_db()`-configured global instance is untouched and is restored afterwards). Fail-loud, no silent no-op renders: a missing store raises `FileNotFoundError` naming the path tried and the three-tier precedence, and a store that exists but yields an EMPTY view (`claims=True` with zero claims, or session/target filters matching nothing) raises `ValueError` instead of returning without writing the requested file. New internals `scitex_clew._db.resolve_db_path()` / `use_db()` / `get_active_db_path()`. CLI: `clew print-mermaid --db PATH` pins the store explicitly (fail-loud when missing).

### Docs
- **Verification caching guarantee** documented across the skill
  (`03_python-api.md` — audited against v0.6.0), sphinx (`concepts.rst`),
  and README: all caches are content-keyed (SHA-256 of live bytes, zero
  mtime logic in `src/`), per-pass hash caches are fresh per pass and never
  persisted, `rerun_dag(skip_unchanged=True)` re-hashes script + all inputs
  (inputs-only; skipped sessions are `level=CACHE`, pair with L1
  `verify_chain` for output tampering), and the v0.2.20-planned persistent
  verdict cache is explicitly recorded as NOT implemented (design key spec
  `H(level ‖ script_hash ‖ sorted(input_hashes) ‖ source_hash)` kept for
  when it is built).
- **Broken-twin case study in README + intro skill.** Documented the real NeuroVista incident (2026-06-30) as the "why clew" motivating example: two same-named warning-metrics Table 03/04 scripts coexisted — the broken twin fabricated timestamps (`times = arange(n) * 60 s` from a block-ordered no-time-column CSV; a uniform-Poisson alarm surrogate beat the real model, AUC 0.46 / IoC < 0) while the valid script used real `window_datetime` + `forecasting.evaluate_stream` (sens 0.70 / spec 0.96 / 0.17 FP/h / lead 10.7 min / IoC +0.56) — and with no claim→source→`@stx.session` binding the two were indistinguishable as "the source"; near-chance numbers were almost shipped. Landed as `README.md` "Case Study: The Broken Twin" + `SKILL.md` "Why clew — the broken-twin incident": claim→source provenance makes "which code produced this value" unambiguous (the broken twin has no registered claim). The incident drove ADR-0021 — clew registration mandatory for every manuscript value.

## [0.6.0]

### Added
- **Subscribe to scitex-session's lifecycle-hook registry (acyclic seam).** `@scitex.session` no longer imports `scitex_clew`: scitex-session exposes `register_session_start_hook` / `register_session_close_hook` (mirroring the `scitex_io` post-save/load hook seam) and clew subscribes lazily via a `sys.meta_path` finder on `import scitex_session`. `scitex_clew._observers.register_with_scitex_session()` is guarded (a scitex-session without the registry API is a silent no-op) and registers keyword-mapping adapters so scitex-session's positional firing — `start(session_id, script_path, metadata)` / `close(status, exit_code)` — routes correctly (metadata never lands in `parent_session`); the public `on_session_start` / `on_session_close` are unchanged. The io-hook bootstrap was generalized to `_bootstrap_pkg_hooks(module, attr)` and now serves both the io and session seams. Completes the loose-coupling design: io, session, and (via the citation io-observer) scholar are all clew-agnostic — clew is the optional observer, peers never import it.

## [0.5.0]

### Added
- **Citation-via-io-observer ingest seam** (loose-coupling / acyclic design). scitex-scholar no longer needs to import clew to populate the citation ledger: it saves a `citation_status.json` via `stx.io`, and clew's io post-save observer recognizes the artifact by its schema marker (`"scitex-clew/citations/v1"`) and ingests it — `scitex_clew._citation.ingest_citations_artifact(obj)` maps each entry (`cite_key` required; `doi`/`source_id`/`resolved`/`is_stub`/`url`/`manuscript_file`/`line_number`/`metadata` optional) 1:1 to `add_citation` (idempotent upsert). Ingestion runs on `on_io_save` **before** the track/session gate (citations are a manuscript-level ledger, not session-scoped) and is exception-safe. scholar imports nothing from clew; deps stay acyclic (io exposes the hook, clew subscribes; io never imports clew).

## [0.4.0]

### Added
- **Unified manuscript-claims render feed.** `scitex_clew.export_manuscript_claims()` / `clew export-claims --unified` — the compile-time bridge scitex-writer's "Clew Render" pre-flight calls. Reads BOTH clew ledgers (value/figure claims + citation nodes) and emits ONE inline `claims` list in writer's frozen render schema: per-entry `{claim_id, claim_type (value|citation|figure), status (4-state verified|suspect|unverified|exception), claim_value, display_color, link, + provenance}` plus top-level `palette` + `attestation{total, verified_count, unverified_count}`. Citation `status`→4-state: verified→verified, stub→unverified (red), unverified→suspect (amber). Writes the canonical `.scitex/clew/runtime/claims.json` (`path=` overrides); the compile calls it last (last-write-wins) so render_clew reads the complete unified shape. New MCP tool `clew_export_manuscript_claims`.

### Fixed
- `render_dag(output_path=…)` now raises a targeted error when handed the clew STORE path (a store suffix such as `.db`) as the render OUTPUT target — "that's the clew store, not a render target; pass `.png`/`.svg`/`.html`/`.json`/`.mmd`" — instead of the generic "Unsupported format". (render_dag reads the DAG from the store internally and infers the output format from the output-path suffix; the store is never a render target.)

## [0.3.0]

### Added
- **Citation gate — `\cite` → scholar-verified source.** Extends clew's claim→source verification from VALUES to CITATIONS: a hallucinated / stub / unresolved citation is caught fail-loud at compile ("一発アウト"). New `scitex_clew.add_citation(...)` (scholar push model — clew is the ledger, never re-does DOI resolution), `verify_citations(entries) -> {key: {status, doi, source_id, link, reason}}` (per-key; `status ∈ {verified, stub, unverified, unknown}`; `link` resolves scholar url → `https://doi.org/<doi>` → None for the render layer), `verify_all_citations(...) -> VerificationResult` (same-run fail-loud aggregate), `list_citations(...)`. New exit codes `CITATION_STUB=14` / `CITATION_UNRESOLVED=15` / `CITATION_UNLINKED=16` (ERROR-default, config-tunable under `verify.severity`). CLI `clew verify-citations --bib <merged.bib> --keys … --format json` (compiler pre-flight) + `clew citation list`; 4 MCP tools. DOI-keyed drift detection; local stub heuristic identical to scitex-writer's fallback.

### Fixed
- **`add_claim` no longer silently collapses distinct claims.** The claim id was `hash(file_path, line_number, claim_type)` with `claim_value` excluded, so two distinct numbers sharing a `(file, line, type)` overwrote each other under `INSERT OR REPLACE` — dropping claims at scale (many numbers per manuscript line). `claim_value` is now folded into the derived id (idempotent re-registration preserved), and `add_claim(..., claim_id=...)` accepts an explicit, stable id used verbatim (e.g. a figure image save-path, or a semantic key per number) so render macros can join deterministically. CLI `claim add --claim-id` + MCP `clew_add_claim(claim_id=)` mirror it.

## [0.2.17]

### Added
- **Fail-loud `clew verify` claim-set mode + documented exit codes.** `clew verify` (no `SESSION_ID`) now verifies **every** registered claim and exits with a nuanced, machine-actionable code: `0` `OK`, `10` `UNVERIFIED` (registered-but-never-verified — the fabrication case), `11` `SOURCE_MISSING`, `12` `HASH_MISMATCH`, `13` `NO_LINEAGE` (`--strict` only), `20` `NO_CLAIMS`. When several failure classes co-occur the highest-severity code wins. The codes are stable constants in `scitex_clew._cli._exit_codes` and surface as `exit_code`/`exit_name`/`counts` under `--json`.
- `clew verify --strict` — a claim passes only if its source ALSO has upstream `@stx.session` lineage (its provenance chain verifies). Rejects a hand-written leaf (e.g. a hand-edited `results.json`) even when its hash matches → `NO_LINEAGE`.
- `clew verify <SESSION_ID>` (single-run mode) is now also fail-loud: nonzero exit when the run does not verify (was always `0`).
- `scitex_clew.verify_all_claims(file_path=None, claim_type=None, *, strict=False)` Python API — the reusable core behind the CLI; returns the per-claim outcomes + overall `exit_code`. Added to `__all__`.
- **Configurable per-pattern severity for `clew verify`** (a "linter for provenance"). Each outcome's severity — `error` (fails the run / blocks DONE), `warning` (reported, tolerated, exit `0`), or `ignore` — is tunable via `verify.severity` in `.scitex/clew/config.yaml`, resolved user (`$SCITEX_DIR/clew`) < project (`<git-root>/.scitex/clew`) < explicit `clew verify --config PATH`, deep-merged; `config.yaml` + a `config/` overlay dir are both supported. Defaults: every pattern `error` except `no_lineage` (`warning`; `--strict` promotes it to `error`). A malformed config / unknown key / invalid severity value **raises** (fail-loud, no silent fallback). New `scitex_clew._config` resolver + `Severity` enum (`clew.Severity`).
- `verify_all_claims(...)` now returns a **`VerificationResult` dataclass** (was a raw dict; `.to_dict()` preserves the `--json` shape) exposing `exit_code` / `ok` / `errors` / `warnings` / `severities` plus a `ClaimVerification` per claim, and gains a `config=` parameter. Exported as `clew.VerificationResult` / `clew.ClaimVerification`.

### Why
Concrete failure 2026-06-19: a blocked solver hand-coded "estimated" metrics into `results.json`, registered 24 claims pointing at it, and printed "DONE" — but the claims were `status="registered"`, `verified_at=null`, with no `@stx.session` computation behind the source (submission scored 0.0). Clew recorded the missing provenance, but nothing forced verification before DONE and a quick `verify` had no loud, machine-actionable signal. The contract: a solver MUST run `clew verify [--strict]` before signalling DONE; DONE is legitimate only on exit `0`, otherwise the agent must abstain honestly (`null` + reason). Documented in skills `21_agentic-reasoning.md`, `04_cli-reference.md`, `03_python-api.md`, `SKILL.md`.

## [0.2.16]

### Fixed
- Provenance resolution now walks **file save→load handshakes** instead of the `session_parents` junction, so a session's parents are the *newest producer of each file it loaded*. Read-only sources/config (no producing session) add no edge. Fixes unreadable lineage (a composed figure showed ~83 "parents") and the `clew.chain()` / `mermaid` hang on dense graphs (`verify_chain` previously followed `runs.parent_session` with no cycle guard). Resolution-only — recording is unchanged. (`_chain/_routes.py`; `verify_chain`/`verify_dag` rewired.)

## [0.2.15] — 2026-06-01

### Added
- `clew.export_claims_json(path=None, *, file_path_filter=None, read_only=True)` — exports every registered claim from the DB to a canonical JSON artifact at `<project>/.scitex/clew/runtime/claims.json` (or `$SCITEX_CLEW_CLAIMS_JSON`, or explicit `path=`). Mirrors the DB's path-resolution chain. The artifact is `0o444` (read-only at the OS layer) by default so accidental hand-edits fail loudly. Payload includes an `_note` warning that the file is auto-generated.
- `_db._core._default_claims_json_path(project_root)` helper — single source for the canonical artifact path, alongside the existing `_default_db_path`.
- Auto-export hook in `add_claim()`: after every successful `clew.add_claim(...)` the canonical JSON is re-emitted in the background. Default ON; opt-out via `SCITEX_CLEW_AUTO_EXPORT_CLAIMS=0` for high-rate streaming workloads. The hook never raises — if the runtime dir is read-only, it emits a `RuntimeWarning` and `add_claim` continues normally.

### Why
Operator directive 2026-06-01 (paper-scitex-clew rollout): clew should be self-contained — the canonical claims JSON should live under `.scitex/clew/runtime/` per the ecosystem local-state-directories convention, with the DB as source of truth and the JSON as a derived read-only artifact. Downstream consumers (verifier, scitex-writer) can now point at one canonical path without touching the database directly.

## [0.2.13]

- feat: host `on_session_start` / `on_session_close` session lifecycle hooks (ported from the scitex-python umbrella; wrap the clew tracker). Lets the umbrella drop its `scitex/clew/` dir and pure-alias to scitex_clew.

## [0.2.12]

### Changed
- CI: bump `actions/upload-artifact` v4→v7 and `actions/download-artifact` v4→v8 (publish + docs/quality workflows) to finish moving off the deprecated Node.js 20 runtime.

## [0.2.11]

### Added
- CLI `clew chain <file>` — trace + verify the provenance chain for a target file (CLI parity with the `clew_chain` MCP tool).
- CLI `clew rerun-dag` / `clew rerun-claims` — re-execute the DAG / claim-backing sessions in a sandbox and compare outputs (CLI parity with the `clew_rerun_*` MCP tools).
- CLI `clew claim register-intermediate` (with `--dry-run` / `--yes`) and MCP `clew_register_intermediate` — record a computed intermediate value as a claim with explicit upstream support.

### Changed
- CI: bump `actions/checkout` v4→v5 and `actions/setup-python` v5→v6 to move off the deprecated Node.js 20 runtime (forced to Node 24 from 2026-06-02).
- Refactor: extract the verification CLI commands from `_cli/_main.py` into `_cli/_verification.py` (one responsibility per module, mirroring `_claim`/`_hash`/`_stamp`).

## [0.2.8]

- Initial CHANGELOG entry — see git log for prior history.
