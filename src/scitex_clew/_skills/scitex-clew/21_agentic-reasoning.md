---
description: |
  [TOPIC] Agentic Reasoning
  [DETAILS] Use Clew as an active reasoning substrate during multi-step agentic computation. The agent queries the existing Clew DAG before each step, registers each intermediate value as a hashed claim, and verifies dependency closure before producing a final answer. Distinct from passive verification (re-checking a human-written script after the fact). Apply when an LLM agent is solving a multi-step scientific or computational task end-to-end — bioinformatics analysis, experimental data interpretation, pipeline construction, multi-method convergence problems.
tags: [scitex-clew-agentic-reasoning]
---

# Agentic Reasoning with Clew

This skill is for AI agents solving multi-step computations. It is not for verifying a human-written script (use the standard `scitex-clew` skill for that). The premise: the existing v1 Clew API plus its MCP tools form an external working memory the agent should consult at every reasoning step. Without this discipline, agent reasoning is ephemeral — the chain that produced the final answer is gone the moment the conversation closes.

## When this skill applies

Apply when the task has the shape: raw data plus a question, the agent must produce a numerical or categorical answer through some pipeline, and the answer's correctness depends on intermediate computations the agent chooses. Bioinformatics workflows (RNA-seq, ChIP-seq, GO enrichment), epidemiological analyses, multi-method convergence problems on benchmarks like BixBench. Skip for single-step lookups or pure code generation that does not produce numerical results.

## Required behavior

You MUST use the existing Clew API at three points in every multi-step computation. The API is already complete; this skill is about *when to call it*, not *how it works*. Refer to `12_mcp-tools-for-ai-agents.md` for the MCP tool reference and `01_quick-start.md` for the Python API.

### Before computing anything

Call `clew_chain(target_file=<final answer file path>)` to see what dependency chain is already registered for the target. If the chain is empty, you are starting fresh and need to plan the full pipeline. If parts are registered, those intermediate hashes are the cached starting points — do not recompute them.

Call `clew_list(status_filter=None, limit=50)` to enumerate registered runs in the current session. The `script_path` field tells you which steps have been executed.

### After computing each intermediate value

Every numerical or categorical result you compute MUST be registered. Use `clew.add_claim(id=<descriptive>, value=<result>, ...)` for values that are part of the answer chain, and route file-saved intermediates through `stx.io.save()` (which auto-registers via the `@stx.session` decorator). The id should describe the value semantically: `acute_correlation_spearman`, not `result_3`.

If you skip registration, the value cannot enter the dependency chain that backs the final answer. The final-answer verification (next section) will then fail.

### Before producing the final answer

Call `clew_dag(target_files=<final answer path>)` and read the returned `is_verified` boolean and `missing_runs` list. If `is_verified=False` or `missing_runs` is non-empty, the answer chain has gaps. Do not produce the final answer until those gaps are filled. Compute the missing nodes, register them, and call `clew_dag` again.

This is the closure check. An answer with an unverified DAG is by construction unreproducible — even if the value happens to be correct, no third party (or your future self) can trace why.

### Emit the final answer and stop

Once the closure check passes, you MUST emit the final answer in the exact format the harness expects (typically `ANSWERS: {"q1": "...", "q5": "..."}` as a single line on stdout, or the equivalent format your task specifies) and then stop calling tools. Registering the chain is necessary but not sufficient — without an emitted final answer, the trial returns no result. Treat "I have computed and registered everything" and "I have produced the answer" as two distinct steps; do not finish at the first.

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

Refer also to `01_quick-start.md` for the Python API and `12_mcp-tools-for-ai-agents.md` for the MCP tool surface. This skill adds *when-to-call* discipline; the *what-to-call* is unchanged from v1.
