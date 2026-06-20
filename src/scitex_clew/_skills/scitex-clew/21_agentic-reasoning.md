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

### Before signalling DONE — the `clew verify` gate

Registering claims is not the same as verifying them. A claim can be
`status="registered"` with `verified_at=null` and **no computation behind
its source** — that is exactly what happens when an agent, blocked on some
runtime error, hand-codes "estimated" numbers into a `results.json`,
registers claims pointing at it, and declares success. Clew records the
missing provenance, but you MUST act on it.

So, immediately before you signal DONE, run:

```bash
clew verify --strict        # claim-set mode: verify EVERY registered claim
echo $?                     # 0 == legitimate DONE; anything else == abstain
```

`DONE` is legitimate **only when `clew verify` exits `0`**. The exit code is
a documented, machine-actionable contract:

| Exit | Name             | Meaning                                                        |
|------|------------------|----------------------------------------------------------------|
| `0`  | `OK`             | every claim is source-verified (strict: + has `@stx.session` lineage) |
| `10` | `UNVERIFIED`     | claim(s) registered but never verified — **the fabrication case** |
| `11` | `SOURCE_MISSING` | a claim's source file is gone                                  |
| `12` | `HASH_MISMATCH`  | a claim's source changed since registration                    |
| `13` | `NO_LINEAGE`     | `--strict`: source is a hand-written leaf, no upstream computation |
| `20` | `NO_CLAIMS`      | nothing registered — there is nothing to stand behind a DONE   |

On any nonzero exit you MUST NOT claim success. Emit an honest abstention
instead — `null` for the affected answer(s) plus a one-line reason (e.g.
"abstained: TF version blocker, metrics could not be computed") — per the
scitexification honest-grounding rule. Fabricating a value and labelling it
DONE scores zero and is worse than an honest `null`.

**Reproduce before you abstain.** A "TF version blocker" / "environment
won't run" is usually *surmountable*, not a reason to abstain. If you run
inside the SciTeX agent container with `nested_build`, rebuild the source's
pinned environment and run the REAL code, then ground your claims in its
outputs:

```bash
export APPTAINER_TMPDIR=/tmp APPTAINER_CACHEDIR=/tmp/.apptainer-cache
apptainer build env.sif docker://<registry>/<published-image>:<tag>   # or build its Dockerfile-derived def
apptainer exec --bind data:/data --bind code:/code --bind "$PWD/results":/results \
  env.sif bash -lc 'cd /code && bash run'
```

You **cannot** use Docker (no daemon inside the container) — use this
apptainer path. Abstain (`null` + reason) only after an honest reproduction
attempt genuinely fails. Mechanism + limits: the `scitexification` (Stage
4.0) and `scitex-agent-container` (nested-apptainer builds) skills.

**The gate is harness-enforced — you cannot skip it.** A `Stop` hook runs
`clew verify --strict` at every turn-end and REFUSES `DONE` while any
submitted answer is unverified, feeding the failure back to you. There is no
"declare DONE anyway": you either reproduce-and-verify, or abstain. Running
`clew verify` early and often is how you avoid being blocked at the end.

Use `--strict` whenever the task expects the answer to come from an actual
computation: it rejects a source whose hash matches but which no
`@stx.session` ever produced (the hand-edited `results.json`). Use the
JSON form (`clew verify --strict --json`) to read `exit_code` / `counts` /
`errors` / `warnings` / per-claim `outcome` programmatically.

Each pattern's severity is configurable per project via `verify.severity` in
`.scitex/clew/config.yaml` (see [20_env-vars.md](20_env-vars.md#config-files-scitexclew)):
a pattern set to `warning` is reported under `warnings` but does **not** block
DONE (exit stays `0`); only `error`-severity patterns fail the gate. Defaults
keep every fabrication/integrity pattern at `error`, so you cannot accidentally
relax the gate — you must opt out explicitly.

### Emit the final answer and stop

Once the closure check passes **and `clew verify` exits 0**, you MUST emit the final answer in the exact format the harness expects (typically `ANSWERS: {"q1": "...", "q5": "..."}` as a single line on stdout, or the equivalent format your task specifies) and then stop calling tools. Registering the chain is necessary but not sufficient — without an emitted final answer, the trial returns no result. Treat "I have computed and registered everything" and "I have produced the answer" as two distinct steps; do not finish at the first.

## Rationale, anti-patterns, and a worked example

The *why* behind this discipline (cache hits, claim-granular tamper
detection, durable final-answer provenance), the values you should and
should not register, and an end-to-end five-step analysis are in
[22_agentic-reasoning-examples.md](22_agentic-reasoning-examples.md).

Refer also to `01_quick-start.md` for the Python API and `12_mcp-tools-for-ai-agents.md` for the MCP tool surface. This skill adds *when-to-call* discipline; the *what-to-call* is unchanged from v1.
