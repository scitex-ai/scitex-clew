# Clew v2 — Agent Reasoning Substrate (Design Doc)

Status: design only. Implementation lives on `feat/v2-agent-substrate`. v1 (current passive-verification API) is unaffected.

## Motivation

v1 framing is *passive verification*: a human writes the code, decorates with `@stx.session`, and Clew records hashes for later re-execution and tamper detection. This works (bix-6 demo: 9/9 reproducibility, 5/5 tamper detection across 9 BixBench capsules).

v2 framing is *active reasoning substrate*: an AI agent solving a multi-step computation queries the Clew DAG at each reasoning step, registers intermediate claims as it computes, and verifies dependency closure before committing a final answer. The fast SQLite DAG already implemented in v1 makes per-step queries affordable (millisecond-scale).

The killer experiment is BixBench-205 with three arms (agent baseline, agent + Clew, agent + scitex without Clew) measuring accuracy delta, token cost, and backtracking rate.

## Minimum API surface (7 calls)

These wrap the existing v1 SQLite DAG; they do not introduce new persistence.

```python
import scitex_clew as clew

# Query — read-only operations on the DAG
clew.query_dag(target: str, depth: int | None = None) -> dict
clew.list_pending_claims() -> list[str]
clew.show_path(from_: str, to: str) -> list[str]
clew.verify_dag_complete(target: str) -> tuple[bool, list[str]]

# Register — mutate the DAG
clew.register_claim(id: str, value, supports: list[str], code: str | None = None) -> str
clew.assert_consistency(claim_id: str) -> tuple[bool, list[str]]
clew.recompute_from(node_id: str) -> dict
```

Concrete signatures and SQL equivalents in `v2_api_spec.md` (TBD). Each call returns a JSON-serializable structure suitable for direct LLM consumption.

## The agentic-clew skill

A single skill markdown file shipped with scitex-clew, loaded by agents at session start. Imperative form (per the audit's recommendation that LLMs follow `MUST` better than indicative descriptions).

```markdown
# agentic-clew skill

When solving any multi-step computation:

1. BEFORE computing X, run `clew.query_dag(target=X)` to see what
   inputs are required and which are already registered.
2. AFTER computing each intermediate value, MUST call
   `clew.register_claim(id=<descriptive>, value=<result>, supports=[<upstream>])`.
3. BEFORE producing a final answer, MUST call
   `clew.verify_dag_complete(target=<final>)`. Abort if False.
4. If a registered claim turns out wrong, call `clew.recompute_from(...)`
   instead of starting over — downstream re-validates automatically.

Force + reward design:
- Returns from non-registered intermediates are not committed.
- Registered claims get hash-cached: re-runs of identical inputs
  return cached results in milliseconds (10× speedup proven by
  bix-6: 87s → 8s on second run via mygene cache).
```

## Pilot experiment (1 capsule, 2 arms)

Smallest informative test before scaling.

| Capsule | bix-6 (CRISPRa screen, 23 code cells, 2 reference questions) |
|---|---|
| Agent | claude-haiku-4-5 (cheapest; if signal exists here, scaling to opus is safe) |
| Arm A — control | Agent + plain Jupyter, no Clew tooling |
| Arm B — treatment | Agent + agentic-clew skill + 7-call API |
| Trials | 5 per arm (10 total runs) |
| Metric | accuracy match to BixBench reference (`q1=chronic round 2`, `q5=25%`); tokens used; wall clock; backtracking events |
| Pass criterion (directional) | B ≥ 4/5 AND A ≤ 2/5 — modest signal worth scaling |
| Fail criterion | B ≤ A on accuracy — agentic Clew adds nothing measurable; revisit API design |

Agent receives only: the raw `xlsx` data, the `BixBench.jsonl` row(s) for bix-6 questions, and (in arm B) the agentic-clew skill prompt + access to `clew.*` calls. No notebook, no hint, no example code.

## Scaling plan (post-pilot)

If pilot signal is positive, three escalations in order:

1. Same arms × 5 capsules (bix-6, bix-19, bix-29, bix-33, bix-16 — the 5 already verified to be reproducible). N = 5 × 2 × 5 = 50 runs. Statistical baseline.
2. Add a third arm C (agent + scitex without Clew skill) to ablate Clew's contribution from scitex-the-framework. N = 5 × 3 × 5 = 75 runs.
3. Full BixBench-205 × 3 arms × 3 trials = ~1850 runs. Spartan with `clew.sif` overnight.

Cost envelope at claude-haiku rates: arm × capsule × trial costs roughly $0.05; full benchmark ~$90. Wall clock dominated by sequential agent reasoning (~2-5 min per run); Spartan parallelism brings full benchmark to ~6-12 hours.

## Implementation order

1. v2 API stubs in `_v2_api.py` with full type signatures + docstrings, no behavior. Smoke-test via `python -c "from scitex_clew import _v2_api"` to confirm the module imports.
2. Implement each call against the existing SQLite schema. Order: query first (read-only, low risk), then register (mutates the DAG; needs careful schema migration if v2 needs new columns).
3. Add the agentic-clew skill markdown to `~/proj/scitex-clew/_skills/scitex-clew/`. Imperative phrasing throughout.
4. Pilot harness at `~/proj/paper-scitex-clew/scripts/v2_pilot/bix6_agent_pilot.py`. Two arms; 5 trials each; capture all 4 metrics; aggregate to `summary.json`.
5. Run pilot; if signal, scale per the plan above.

## Out of scope for v2

Multi-agent collaboration on shared DAGs; reasoning over claims across published papers; live editing of the DAG by humans during agent runs. All deferrable.

## Risks

- **Agent doesn't call the API enough.** Mitigation: imperative skill phrasing; force-use design where returns require `register_claim`. Audit-flagged.
- **API too verbose for agents to use efficiently.** Mitigation: each call's return is small (≤200 tokens of JSON). Per-step query cost stays under 5% of agent context.
- **DAG queries become slow at scale.** Mitigation: SQLite indexes already in v1; profile at the BixBench-205 stage. If query latency exceeds 100 ms, pre-compute reachability into a flat materialized view.

## Decision points (user-owned)

1. v2 ships as part of the existing `scitex-clew` package, or as a separate `scitex-clew-reason` (auditor's suggestion to avoid diluting the v1 verification claim)?
2. Pilot timing: now (parallel with v1 arxiv finalization), or post-arxiv?
3. If positive signal, target Nature 本誌 directly with a paired v1+v2 narrative, or stage as v2 arxiv → Nature Methods → Nature?
