---
description: |
  [TOPIC] clew as an evidence provider for scitex-live-paper
  [DETAILS] Implements contract scitex-live-paper.evidence-report 1.2.0 (schema vendored); entry point scitex.livepaper.renderers -> clew (port "evidence"); `clew export-evidence --out report.json`; outcome -> state/reason table; level-1 slice -> graph nodes/edges.
tags: [scitex-clew-evidence-provider]
---

# Evidence provider (scitex-live-paper contract 1.2.0)

clew supplies the per-claim evidence that scitex-live-paper renders. The two
are coupled **only** through live-paper's published, provider-neutral
contract `scitex-live-paper.evidence-report` **1.2.0**. clew does not import
live-paper, and live-paper does not import clew. The schema is vendored
version-pinned at
`src/scitex_clew/_evidence_provider/evidence-report.schema.1.2.0.json`, and
clew's own tests validate every report against it.

## Connecting

In process, live-paper discovers the entry point (no configuration needed
once both are installed):

```toml
[project.entry-points."scitex.livepaper.renderers"]
clew = "scitex_clew._evidence_provider:EvidenceEntry"   # port = "evidence", name = "clew"
```

```bash
scitex-live-paper render bundle/ --out site/ --evidence-provider clew --evidence-root /path/to/project
```

Out of process, write the report file and hand it over:

```bash
clew export-evidence --out report.json                  # all registered claims of ./
clew export-evidence --project-root ../paper --claim auc --out -   # stdout
scitex-live-paper render bundle/ --out site/ --evidence-report report.json
```

`export-evidence` exits 0 when the report was written, whatever the claims'
states. It is an export, not a gate (`clew verify --strict` is the gate).

Python: `scitex_clew._evidence_provider.build_evidence_report(root, claim_ids, options)`
and `build_evidence_graph(root, claim_id, options)`. Option
`with_graphs=False` omits each `graph` key, so the consumer fetches graphs on
demand.

## What the report holds

It holds one entry per **registered** claim. Unregistered text never appears.
Verification is always `verify_all_claims(strict=True)`, scoped to
`project_root`. A value counts as supported only when its source also has a
recorded computation behind it.

| clew outcome (code) | state | reason |
|---|---|---|
| OK (0) | supported | value and sources check out against the recorded run |
| VALUE_MISMATCH (21) | not_supported | value in source differs: `<src>` in source vs `<stated>` stated |
| HASH_MISMATCH (12) | not_supported | source changed after the claim was registered |
| STALE_LINEAGE (18) | not_supported | source changed after the run (an input, script or run changed) |
| EXTERNAL_MISSING (22) | not_supported | an input from outside the project is absent here, … |
| ENV_NOT_REPRODUCIBLE (23) | not_supported | the recorded software environment cannot be reproduced … |
| SOURCE_MISSING (11) / VERIFY_ERROR (19) / UNSOURCED (17) | not_supported | plain reason |
| VALUE_UNCHECKED (24) | not_checkable | no locator, value not checked |
| NO_LINEAGE (13) | no_evidence_graph | no evidence graph: the source has no recorded computation behind it |
| UNVERIFIED (10) | no_evidence_graph | no evidence graph: no source is linked to the claim |
| anything else | not_supported | clew reported `<NAME>` (never supported) |

`provider_status` is `{name, code}` and `details` is clew's per-claim
details list. `location.file` and `source.file` are relative to
`project_root` (absolute when outside it). `source.locator` is the claim's
`source_keys`. `source.value` (contract 1.2.0) is what the source holds NOW at
that locator: a scalar for a `"."` locator, else `{field: value}`. It is
omitted when the claim has no locator or nothing could be read there (clew's
details say why), so a VALUE_MISMATCH shows the differing source value.

**Graph:** the claim's level-1 slice is converted as follows.

- Each run becomes a `process` node, labelled with its session id.
- Each file becomes an `output` node if a kept run wrote it, otherwise an
  `input` node. Its label is the path relative to the project root, it
  carries its `hash`, and an input from outside the project has
  `external: true`.
- The claim gets a `claim` node with `supports` edges from the slice targets.
- The summary reads `level-1 slice: N run(s), M file(s)`.

A claim with no source file has `graph: null` and a `graph_error`.

**Where the evidence broke (contract 1.1.0 `node.failure`).** The graph
marks the nodes clew's own verification failed on, as
`failure: {kind, detail}`, so a reviewer sees the break on the graph page:

| clew outcome | marked node | `failure.kind` |
|---|---|---|
| SOURCE_MISSING | source file | `missing` |
| HASH_MISMATCH | source file | `changed` (differs from the hash recorded at registration) |
| VALUE_MISMATCH | source file (located value differs; detail `<src> in source vs <stated> stated`), else the claim node | `mismatched` |
| STALE_LINEAGE / EXTERNAL_MISSING | every file the re-verified minimal chain reports MISMATCH (`changed`) or MISSING (`missing`); a run whose execution failed (`failed`). A recorded file pruned from the drawn slice is reported on its run's node, naming the file. | as listed |
| any other | nothing (no node broke: no locator, no lineage, environment) | — |

When Clew has an in-project script path and hash for a producing run, the
process node includes `script.file` and `script.hash`. The label remains the
recorded run ID. A reader can use the metadata to locate and verify the
script through its own authorized project file access.


A graph can carry `relation: "author_interpretation"` on the result-to-claim
edge. The relationship is declared at registration. A supported state for
this entry attests to the recorded trace and any direct comparisons only.

## Citation verdicts

`verify_citations` returns each BibTeX key's Clew status and canonical color.
When the registered identity agrees, the verdict also carries Scholar's
recorded `resolver_source` and `provenance` if available. The citation ledger
checks source identity. Use a recorded acquisition run and its response
artifacts to trace retrieval.
