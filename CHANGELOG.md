# Changelog

All notable changes to `scitex-clew` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
