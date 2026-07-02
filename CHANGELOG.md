# Changelog

All notable changes to `scitex-clew` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- **Root-layout refactor (PS-108b headroom) — no behavior change, public API identical** (`scitex_clew.__all__` unchanged: all 34 names and every lazy attribute resolve exactly as before). Flat root files went 15 → 9: `_stamp.py` + `_registry.py` moved into a new `_attest/` subpackage (external attestation: temporal stamping + remote Clew Registry; `scitex_clew._attest` re-exports both surfaces); `_public_api.py` (the `_LAZY_ATTRS` registry) moved to `_core/_public_api.py`; the pure re-export shims `_dag.py` (→ `_chain`) and `_visualize.py` (→ `_viz`) were removed with all internal importers rewired to the real modules; the dead legacy `_chain.py` (shadowed by the `_chain/` package since the split, never importable) was deleted. Test mirrors moved accordingly (`tests/scitex_clew/_attest/`; `test__chain.py` → `_chain/test__types.py`). Internal-only import paths `scitex_clew._stamp` / `._registry` / `._dag` / `._visualize` / `._public_api` no longer exist — use `scitex_clew._attest._stamp` / `._attest._registry` / `._chain` / `._viz` / `._core._public_api` (private modules; the supported surface is the top-level `scitex_clew.*` names, which are untouched).

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

## [Unreleased]

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

### Added
- **Explicit-store rendering: `render_dag(..., db_path=...)`** (clew-feat-render-dag-explicit-store). `render_dag` gains a `db_path` keyword so host-side/post-run callers can target a store outside the current tree (e.g. `<runs>/<capsule>/.scitex/clew/runtime/db.sqlite`) without chdir. Resolution precedence matches `VerificationDB`: (1) explicit `db_path`, (2) `SCITEX_CLEW_DB_PATH`, (3) project-root walk from cwd; the store is activated only for the duration of the call (a `set_db()`-configured global instance is untouched and is restored afterwards). Fail-loud, no silent no-op renders: a missing store raises `FileNotFoundError` naming the path tried and the three-tier precedence, and a store that exists but yields an EMPTY view (`claims=True` with zero claims, or session/target filters matching nothing) raises `ValueError` instead of returning without writing the requested file. New internals `scitex_clew._db.resolve_db_path()` / `use_db()` / `get_active_db_path()`. CLI: `clew print-mermaid --db PATH` pins the store explicitly (fail-loud when missing).
- **Fail-loud `clew verify` claim-set mode + documented exit codes.** `clew verify` (no `SESSION_ID`) now verifies **every** registered claim and exits with a nuanced, machine-actionable code: `0` `OK`, `10` `UNVERIFIED` (registered-but-never-verified — the fabrication case), `11` `SOURCE_MISSING`, `12` `HASH_MISMATCH`, `13` `NO_LINEAGE` (`--strict` only), `20` `NO_CLAIMS`. When several failure classes co-occur the highest-severity code wins. The codes are stable constants in `scitex_clew._cli._exit_codes` and surface as `exit_code`/`exit_name`/`counts` under `--json`.
- `clew verify --strict` — a claim passes only if its source ALSO has upstream `@stx.session` lineage (its provenance chain verifies). Rejects a hand-written leaf (e.g. a hand-edited `results.json`) even when its hash matches → `NO_LINEAGE`.
- `clew verify <SESSION_ID>` (single-run mode) is now also fail-loud: nonzero exit when the run does not verify (was always `0`).
- `scitex_clew.verify_all_claims(file_path=None, claim_type=None, *, strict=False)` Python API — the reusable core behind the CLI; returns the per-claim outcomes + overall `exit_code`. Added to `__all__`.
- **Configurable per-pattern severity for `clew verify`** (a "linter for provenance"). Each outcome's severity — `error` (fails the run / blocks DONE), `warning` (reported, tolerated, exit `0`), or `ignore` — is tunable via `verify.severity` in `.scitex/clew/config.yaml`, resolved user (`$SCITEX_DIR/clew`) < project (`<git-root>/.scitex/clew`) < explicit `clew verify --config PATH`, deep-merged; `config.yaml` + a `config/` overlay dir are both supported. Defaults: every pattern `error` except `no_lineage` (`warning`; `--strict` promotes it to `error`). A malformed config / unknown key / invalid severity value **raises** (fail-loud, no silent fallback). New `scitex_clew._config` resolver + `Severity` enum (`clew.Severity`).
- `verify_all_claims(...)` now returns a **`VerificationResult` dataclass** (was a raw dict; `.to_dict()` preserves the `--json` shape) exposing `exit_code` / `ok` / `errors` / `warnings` / `severities` plus a `ClaimVerification` per claim, and gains a `config=` parameter. Exported as `clew.VerificationResult` / `clew.ClaimVerification`.

### Why
Concrete failure 2026-06-19: a blocked solver hand-coded "estimated" metrics into `results.json`, registered 24 claims pointing at it, and printed "DONE" — but the claims were `status="registered"`, `verified_at=null`, with no `@stx.session` computation behind the source (submission scored 0.0). Clew recorded the missing provenance, but nothing forced verification before DONE and a quick `verify` had no loud, machine-actionable signal. The contract: a solver MUST run `clew verify [--strict]` before signalling DONE; DONE is legitimate only on exit `0`, otherwise the agent must abstain honestly (`null` + reason). Documented in skills `21_agentic-reasoning.md`, `04_cli-reference.md`, `03_python-api.md`, `SKILL.md`.

## [0.3.0]

### Added
- **Citation gate — `\cite` → scholar-verified source.** Extends clew's claim→source verification from VALUES to CITATIONS: a hallucinated / stub / unresolved citation is caught fail-loud at compile ("一発アウト"). New `scitex_clew.add_citation(...)` (scholar push model — clew is the ledger, never re-does DOI resolution), `verify_citations(entries) -> {key: {status, doi, source_id, link, reason}}` (per-key; `status ∈ {verified, stub, unverified, unknown}`; `link` resolves scholar url → `https://doi.org/<doi>` → None for the render layer), `verify_all_citations(...) -> VerificationResult` (same-run fail-loud aggregate), `list_citations(...)`. New exit codes `CITATION_STUB=14` / `CITATION_UNRESOLVED=15` / `CITATION_UNLINKED=16` (ERROR-default, config-tunable under `verify.severity`). CLI `clew verify-citations --bib <merged.bib> --keys … --format json` (compiler pre-flight) + `clew citation list`; 4 MCP tools. DOI-keyed drift detection; local stub heuristic identical to scitex-writer's fallback.

### Fixed
- **`add_claim` no longer silently collapses distinct claims.** The claim id was `hash(file_path, line_number, claim_type)` with `claim_value` excluded, so two distinct numbers sharing a `(file, line, type)` overwrote each other under `INSERT OR REPLACE` — dropping claims at scale (many numbers per manuscript line). `claim_value` is now folded into the derived id (idempotent re-registration preserved), and `add_claim(..., claim_id=...)` accepts an explicit, stable id used verbatim (e.g. a figure image save-path, or a semantic key per number) so render macros can join deterministically. CLI `claim add --claim-id` + MCP `clew_add_claim(claim_id=)` mirror it.

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
