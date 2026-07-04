---
description: |
  [TOPIC] Registered-source gate + the `unsourced` verdict
  [DETAILS] Opt-in, hash-pinned source whitelist: a claim is green only if its provenance chain traces to a human-registered source, else it gets the amber `unsourced` verdict (exit 17). Covers the manifest, `clew register-source`, the chain-walk grounding gate, and opt-in + monotonic semantics.
tags: [scitex-clew-registered-source-gate]
---

# Registered-source gate + the `unsourced` verdict

`green = link-hash-consistency` is not enough. A claim can be
link-hash-consistent yet reach **no true source** — its provenance chain
terminates at a hand-made leaf. The registered-source gate adds a
human-curated whitelist of trusted source files so that **green means
grounded to a registered source**. A claim that is link-verified but reaches
no registered source gets the new **amber `unsourced`** verdict (exit code
`UNSOURCED = 17`).

The gate is **opt-in** (no manifest ⇒ zero behavior change) and **monotonic**
(registering a source can only turn amber → green, never break an existing
green).

## The manifest (host-side, hash-pinned)

`<project_root>/.scitex/clew/sources.json`:

```json
{
  "schema": "sources-1.0",
  "sources": [{"path": "data/raw.csv", "sha256": "<64-hex>"}],
  "signature": null
}
```

* `path` is relative to the project root; `sha256` is the full digest of the
  file at registration time.
* `signature` is **reserved** (default `null`): accepted-but-not-enforced
  now; a follow-on will gpg-sign the manifest and reject an unsigned one.
* Resolution tiers (mirrors the DB path): explicit arg > `$SCITEX_CLEW_SOURCES`
  > `<project_root>/.scitex/clew/sources.json`.
* The manifest is **read** by verify/export and **written only** by
  `clew register-source` (human-run). Verify/export never write it.

Every entry is **tamper-checked on load**: the file's current sha256 is
recomputed and compared to the pin. A changed file (`TAMPERED`) or an absent
file (`MISSING`) is **not** a trust anchor and is surfaced loudly.

## CLI

```bash
clew register-source data/raw.csv       # pin a trusted source (idempotent)
clew register-source a.csv b.csv        # register several at once
clew list-sources                       # show entries + OK/TAMPERED/MISSING
clew unregister-source data/raw.csv     # remove an entry
```

`register-source` is the one sanctioned WRITE path.

## The verdict (precedence)

When the gate is **active** (a non-empty manifest with ≥1 valid entry):

```
mismatch / missing  (red, hash failures)      # outrank everything
  > unsourced        (amber, ungrounded)       # DEMOTES a would-be green
    > exception / frozen / verified / suspect / registered
```

Key points:

* `unsourced` **demotes an otherwise-green (verified) claim** — being
  link-hash-verified does **not** exempt a claim from the source gate.
* Hash failures still win: a hash-mismatching ungrounded claim reads **red**,
  not amber.
* Colour ≠ exit severity: the node is amber, but the gate still **fails**
  (`clew verify` returns `17`).

When the gate is **inactive** (no manifest), resolution is identical to the
pre-gate behavior — verified stays verified.

## Grounding (the laundering guard)

`is_grounded(claim, manifest, db)` walks the provenance chain to its root(s)
and returns `True` iff **at least one** file in the chain (including the
claim's own source) matches a **valid** registered-source entry by
`(path, sha256)`. So:

* a mixed chain with ≥1 registered root among several is **grounded**;
* a chain whose every root is unregistered is **unsourced**;
* a chain grounded only by a **tampered** entry is **unsourced** (the tampered
  entry is not a valid anchor).

`is_grounded` is a pure function — the compute-time follow-on (a session-exit
observer) will call the identical logic.

## Schema (additive, backward-compatible)

* Per-claim `claims.json` → `1.4`: adds `unsourced` to the palette, a
  per-claim `grounded` bool (`null` when the gate is inactive), an
  `unsourced` legend entry, and `attestation.unsourced_count`.
* Unified render feed → `1.6-unified`: adds the `unsourced` bucket to
  `attestation.counts`; an ungrounded claim makes the badge `partial`.
* Consumers that ignore the new fields are unaffected.

## Palette

`unsourced` = burnt amber `#b26a00` — its own reader bucket (not verified,
not failed-red). The hue clears the palette's colour-universal-design ΔE
floor (CIE76 ≥ 12) against all 7 other states across normal / protanopia /
deuteranopia / tritanopia (Machado-2009, severity 1.0).

## Python API

```python
import scitex_clew as clew
clew.register_source("data/raw.csv")        # write the manifest (human path)
clew.list_sources()                          # entries + validity
clew.load_sources_manifest()                 # SourcesManifest | None
clew.is_grounded(claim, manifest, db)        # the pure gate function
```
