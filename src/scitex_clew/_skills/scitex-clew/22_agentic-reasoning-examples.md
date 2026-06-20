---
description: |
  [TOPIC] Agentic Reasoning — rationale, anti-patterns, worked example
  [DETAILS] The *why* behind the agentic-reasoning discipline in 21_agentic-reasoning.md: what you gain by registering every intermediate (cache hits, claim-granular tamper detection, durable final-answer provenance), which values to register vs. skip, and an end-to-end five-step RNA-seq analysis mapping each step to its Clew API call. Read after 21_agentic-reasoning.md when you want the motivation and a concrete template, not just the rules.
tags: [scitex-clew-agentic-reasoning-examples]
---

# Agentic Reasoning with Clew — rationale and example

This page accompanies [21_agentic-reasoning.md](21_agentic-reasoning.md). That page is the *when-to-call* discipline (the required behavior + the `clew verify` DONE gate); this one is the *why* plus a worked example.

## What you get for following this discipline

Cache hits on identical inputs. The first run of `mygene.querymany` for a given gene list takes 87 seconds; the second returns in 8 seconds because the hash of the input list resolves to a cached output. Generalize this pattern to every external API call, every long-running computation, every parameter sweep. Re-runs of identical pipelines collapse from minutes to milliseconds.

Tamper detection at claim granularity. If any input changes — even one byte in a data file, even one character in a parameter — the affected claim's hash flips. Other claims whose input set does not include the changed value remain insulated. This means you can localize where a divergence began without re-running the entire chain.

Final-answer provenance. The `clew_chain` call from any future inspector returns the full path from the answer back to the source data and code. The agent's reasoning is no longer ephemeral; it survives the conversation as a queryable graph.

## What to avoid

Do not produce final answers without a passing `clew_dag` verification. Do not register every single trivial value (loop counters, intermediate arrays for plotting) — register the *claims* that back the answer, not the implementation noise. Do not use generic ids like `value_1`, `temp`, `result`; the id is the only handle a future inspector has on the value.

Do not use this skill in single-step tasks where the agent's job is just to call one function and return its output. The overhead of registration is not worth it for trivially-traceable computations. The threshold is roughly three or more intermediate values, or any value the agent produced through a non-trivial choice (which method, which threshold, which subset).

## Example: a five-step analysis

The agent receives raw RNA-seq counts plus the question "which condition shows the strongest pathway enrichment?". The five steps and their corresponding API calls:

1. Load and normalize the counts. Save via `stx.io.save(normalized, "counts_normalized.csv")`. Auto-registered.
2. Compute differential expression per condition. Each condition's DE table → `stx.io.save(de_acute, "de_acute.csv")` etc. Auto-registered.
3. Map RefSeq IDs to gene symbols. The mapping dict gets `clew.add_claim(id="refseq_to_symbol_map", value=mapping_hash, ...)`. Cache key.
4. Run pathway over-representation per condition. Each condition's `n_sig_pathways` → `clew.add_claim(id="acute_n_sig_pathways", value=N, ...)`. Repeat for chronic_r1, chronic_r2, chronic_r3.
5. Argmax to pick the winning condition. Final answer → `clew.add_claim(id="q1_answer", value="chronic round 2", ...)` with `parent_session` linking to the four `n_sig_pathways` claims.

Before answering, `clew_dag(target_files="q1_answer")` must return `is_verified=True`. If it does not, look at `missing_runs` and fill them.

## Force and reward summary

The discipline is not optional. Returns from un-registered intermediates cannot land in a verified final-answer chain — the closure check at step 5 will fail. Conversely, registered claims get cached: the second call with identical inputs is a hash lookup, not a recompute. Use the API and the system gets faster; skip it and the system refuses to commit your answer.
