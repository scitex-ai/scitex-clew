# Changelog

All notable changes to `scitex-clew` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
- **WAL + `busy_timeout` on clew's sqlite connections (#123).** All
  connections now open with `journal_mode=WAL` + `synchronous=NORMAL`
  (writable opens, best-effort) + `busy_timeout=300000` (always) via a
  single stdlib-only connect helper, mirroring scitex-db's proven PRAGMA
  set WITHOUT taking the dependency (clew stays zero-dep). Fixes the
  immediate "database is locked" failure under concurrent writers.

### Changed
- **Default DB renamed `db.sqlite` → `clew.db` (#124).** The default store
  is now `<project_root>/.scitex/clew/runtime/clew.db` (reference
  implementation of the fleet `.scitex/<pkg>/runtime/<pkg>.db` convention;
  `.db` is also `stx.io.load`-recognized). A transparent, WAL-safe
  auto-migration renames an existing `runtime/db.sqlite` (or legacy flat
  `db.sqlite`) on first open: it `wal_checkpoint(TRUNCATE)`s to fold the
  `-wal` back into the main file, then atomically `os.replace`s it — no
  data loss, even for multi-GB WAL DBs. The gate name-match accepts
  `clew.db` (falling back to `db.sqlite`).

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
- **Explicit-store rendering: `render_dag(..., db_path=...)`** (clew-feat-render-dag-explicit-store). `render_dag` gains a `db_path` keyword so host-side/post-run callers can target a store outside the current tree (e.g. `<runs>/<capsule>/.scitex/clew/runtime/db.sqlite`) without chdir. Resolution precedence matches `VerificationDB`: (1) explicit `db_path`, (2) `SCITEX_CLEW_DB_PATH`, (3) project-root walk from cwd; the store is activated only for the duration of the call (a `set_db()`-configured global instance is untouched and is restored afterwards). Fail-loud, no silent no-op renders: a missing store raises `FileNotFoundError` naming the path tried and the three-tier precedence, and a store that exists but yields an EMPTY view (`claims=True` with zero claims, or session/target filters matching nothing) raises `ValueError` instead of returning without writing the requested file. New internals `scitex_clew._db.resolve_db_path()` / `use_db()` / `get_active_db_path()`. CLI: `clew print-mermaid --db PATH` pins the store explicitly (fail-loud when missing).

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
- `render_dag(output_path=…)` now raises a targeted error when handed the clew STORE path (`.sqlite`/`.db`) as the render OUTPUT target — "that's the clew store, not a render target; pass `.png`/`.svg`/`.html`/`.json`/`.mmd`" — instead of the generic "Unsupported format". (render_dag reads the DAG from the store internally and infers the output format from the output-path suffix; the store is never a render target.)

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
Operator directive 2026-06-01 (paper-scitex-clew rollout): clew should be self-contained — the canonical claims JSON should live under `.scitex/clew/runtime/` per the ecosystem local-state-directories convention, with the DB as source of truth and the JSON as a derived read-only artifact. Downstream consumers (verifier, scitex-writer) can now point at one canonical path without touching sqlite.

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
