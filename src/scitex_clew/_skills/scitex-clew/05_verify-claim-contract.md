---
description: |
  [TOPIC] verify_claim consumer contract
  [DETAILS] Exact call/return contract of verify_claim for downstream consumers (scitex-live-paper, scitex-writer) — signature, return shape, the two status vocabularies, DB selection precedence, the v1.3 full-7 palette + 4-bucket display collapse, and what clew deliberately does NOT do (git checkout).
tags: [scitex-clew-verify-claim-contract]
---

# `verify_claim` — the consumer contract (v0.7.0)

Audited against `src/scitex_clew/_claim/_verify.py` and
`src/scitex_clew/_claim/_model.py` at **v0.7.0**. A real consumer
(scitex-live-paper, 2026-06-28) integrated against an imagined API —
`against=`/`bundle_root=` kwargs, clew-does-checkout, top-level
`result["status"]`/`verified_at` — and mismatched on all four axes.
This page is the binding contract.

## 1. Signature — one positional, no commit arg, NO checkout

```python
import scitex_clew as clew
result = clew.verify_claim(claim_id_or_location)   # -> Dict
```

- `claim_id_or_location: str` — a `claim_id`, a `"paper.tex:L42"`
  location, or a bare file path (first claim on that file).
- There is **no** `against=`, `bundle_root=`, or commit argument.
- The only other parameters are the internal perf kwargs
  `hash_cache=None` / `chain_cache=None` (per-pass caches threaded in by
  `verify_all_claims`); consumers pass the single positional.
- **clew never runs git.** It re-hashes `claim.source_file` **on disk,
  at its current state** (SHA-256 via `src/scitex_clew/_hash.py`). To
  verify "as of commit X", the HOST must check out X first, then call
  `verify_claim`. This git-agnosticism is by design — there is no
  verify-at-commit helper.
- Side effect: the claim row's `status` and `verified_at` are **written
  back to the DB** on every resolved verification (`_update_claim_status`).

## 2. Return shape — field by field

Unresolved lookup (the ONLY case with a top-level `"status"`):

```python
{"status": "not_found", "message": "No claim found for '...'"}
```

Resolved claim — exactly four top-level keys:

| Key | Type | Meaning |
|---|---|---|
| `claim` | dict | `Claim.to_dict()` — see below |
| `source_verified` | bool | stored `source_hash` matches the re-hash of `source_file` |
| `chain_verified` | bool | upstream `@stx.session` provenance chain verifies (`verify_chain`) |
| `details` | list[str] | human-readable notes (hash match/mismatch, chain run counts, errors) |

`result["claim"]` fields (`_claim/_model.py::Claim.to_dict`): `claim_id`,
`file_path`, `line_number`, `claim_type`, `claim_value`, `source_session`,
`source_file`, `source_hash`, `registered_at`, `verified_at`, `status`.

Gotchas:

- `status` and `verified_at` live **inside `result["claim"]`**, never at
  the top level of a resolved result.
- `result["claim"]["status"]` IS refreshed to this pass's outcome;
  `result["claim"]["verified_at"]` is the value as read at resolution
  time (the DB row gets a new timestamp, the returned dict does not).
- A claim with no `source_file` returns `source_verified=False`,
  `chain_verified=False`, empty `details`, stored status untouched.
- `resolved_status` / `color` / `display_group` / `display_color` are
  **NOT in this return** — they are claims.json enrichment fields (§5).

## 3. Two status vocabularies — do not conflate

**(a) `VerificationStatus` enum** (`src/scitex_clew/_chain/_types.py`) —
for runs / files / chains / DAGs: `VERIFIED`, `MISMATCH`, `SUSPECT`,
`MISSING`, `UNKNOWN`. `SUSPECT` = locally valid but an upstream session
failed.

**(b) Claim `status` strings** (stored on the claims row): `registered`,
`verified`, `suspect`, `mismatch`, `missing` — plus `not_found` as a
lookup outcome (never stored). Written by `verify_claim`:

| Outcome | Claim `status` |
|---|---|
| source file gone | `missing` |
| stored hash ≠ current hash | `mismatch` |
| hash matches, chain fails | `suspect` |
| hash matches, chain verifies | `verified` |
| never verified | `registered` (initial) |

**0.7.0 rename: `partial` → `suspect`.** The claim status `partial` no
longer exists; legacy stored `"partial"` rows are normalized to
`"suspect"` at read time (`_LEGACY_STATUS_MAP` in `_claim/_model.py`).
`suspect` now deliberately spans BOTH vocabularies — that was the point
of the rename: one word for "locally valid, upstream not confirmed".

## 4. claims.json v1.3 fields + precedence (0.7.0)

`export_claims_json()` (`src/scitex_clew/_claim/_export.py`) enriches
each claim with:

- `resolved_status` — the single full-7 status after precedence:
  `mismatch`/`missing` > [**verified claims only**: `exception` >
  `frozen`] > `suspect` > `verified` > `registered`. Chain overrides
  (exception/frozen) NEVER promote an unverified claim — no false-green.
- `color` — bare 6-hex (no `#`) for the resolved status (§5).
- `chain_has_exception` / `chain_has_frozen` — provenance-DAG flags.
- `display_group` — 4-bucket reader collapse: one of
  `verified` / `suspect` / `failed` / `exception`.
- `display_color` — bare hex for the display group.
- `exception_reasons` — reasons for exception nodes in the chain.

Top-level: `schema_version` (`"1.3"`), `palette` (full-7),
`display_palette`, `display_groups` (collapse map), `attestation`,
`legend`, `exceptions`, `claims`.

## 5. Canonical palette (v1.3 full-7) — supersedes all older tables

Source of truth: `_CLAIM_PALETTE` in `src/scitex_clew/_claim/_model.py`.
Bare 6-hex, no `#`, no light/dark variants:

| Status | Hex | Hue |
|---|---|---|
| `verified` | `2da44e` | green |
| `suspect` | `d29922` | amber |
| `mismatch` | `cf222e` | red |
| `missing` | `a40e26` | dark red |
| `registered` | `6e7781` | grey |
| `exception` | `8250df` | violet |
| `frozen` | `0072b2` | blue (Okabe-Ito) |

4-bucket display collapse (`_DISPLAY_GROUPS` / `_DISPLAY_PALETTE`):
`verified`+`frozen` → **verified** `2da44e`; `suspect`+`registered` →
**suspect** `d29922`; `mismatch`+`missing` → **failed** `cf222e`;
`exception` → **exception** `8250df`.

> **Migration note.** Any consumer still holding the pre-v1.3 table
> (`partial d29922`, `missing cf222e`, light/dark variants) has a stale
> copy — that table is SUPERSEDED. Do not hardcode either table: read
> `palette` / `display_palette` / `display_groups` from the exported
> claims.json.

## 6. DB selection precedence — three tiers

`resolve_db_path()` (`src/scitex_clew/_db/_core.py`):

1. **Explicit `db_path`** — `VerificationDB(db_path=...)`, and (new in
   0.7.0) `render_dag(..., db_path=...)` in `src/scitex_clew/_viz/_mermaid.py`
   for rendering a store outside the current tree (fails loud with the
   resolved tier when the store file is missing).
2. **`SCITEX_CLEW_DB_PATH`** environment variable.
3. **Project-root walk from cwd** — nearest ancestor with `.git` or
   `pyproject.toml` (else cwd) → `<root>/.scitex/clew/runtime/db.sqlite`
   (legacy `<root>/.scitex/clew/db.sqlite` auto-migrates with a
   deprecation warning).

Host-side re-verify recipe (the pattern live-paper needed):

```python
# HOST owns git: check out the pinned commit, point clew at the bundle DB.
subprocess.run(["git", "-C", bundle_root, "checkout", pinned_commit], check=True)
os.environ["SCITEX_CLEW_DB_PATH"] = f"{bundle_root}/.scitex/clew/runtime/db.sqlite"
result = clew.verify_claim(claim_id)          # re-hashes files as now on disk
status = result.get("status")                  # only "not_found" appears here
claim_status = result.get("claim", {}).get("status")  # the real per-claim status
```

## 7. Keep these vocabularies apart

- **Client-side transient UI states** (`verifying`, `error`, spinners)
  are NOT clew statuses — never write them into the claims DB or
  claims.json; keep them in the consumer's own view layer.
- **Paper-level badge vocabularies** (e.g. the unified feed's
  `badge_state`: `all_verified` / `partial` / `failing`) are a separate,
  aggregate vocabulary — not per-claim statuses.
- `suspect` is the ONE term intentionally shared across the run/file
  enum and the claim vocabulary (same semantics at both levels).
