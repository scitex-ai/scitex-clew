# Clew v2 — Agent Reasoning Substrate (Design Doc)

Status: design only. v1 (current passive-verification API) is the *substrate*; v2 is mostly *skill + harness + experiment*, not new code in this package.

## What changed from the first draft

The first draft proposed a 7-call new API surface (`query_dag`, `register_claim`, `verify_dag_complete`, …). On review against `~/proj/scitex-clew/src/scitex_clew/__init__.py` and the MCP server, those calls already exist as `clew.chain`, `clew.add_claim`, `clew.dag`, `clew.rerun`, `clew.list_claims`, `clew.verify_claim`. The v1 package ships 19 public Python functions plus 9 MCP tools. For an agent reasoning substrate, that surface is essentially complete.

The genuine gap is not API; it is the *prompt scaffolding and pilot harness* that makes an agent actually use the API at every reasoning step. v2 is a thin layer on top of v1.

## Existing v1 surface (what an agent already has)

Python API (subset relevant to agentic use):

```python
import scitex_clew as clew

clew.chain(target_file)            # target → source dependency chain
clew.dag(targets)                  # full DAG; returns is_verified + missing_runs
clew.add_claim(id, value, ...)     # register manuscript / output assertion
clew.verify_claim(claim_id)        # check claim still hashes-equal
clew.list_claims(...)              # enumerate registered claims
clew.rerun(target)                 # re-execute and compare in sandbox
clew.rerun_dag(targets)            # rerun full DAG topo-sorted
clew.mermaid(...)                  # generate visualization
```

MCP tools (over `mcp__scitex__clew_*`): `clew_status`, `clew_list`, `clew_run`, `clew_chain`, `clew_dag`, `clew_mermaid`, `clew_rerun_dag`, `clew_rerun_claims`, `clew_stats`. All return JSON suitable for direct LLM consumption.

DB-level operations (`_db/_chain.py`): `get_chain`, `get_children`, `set_parent`. The graph-traversal primitives the audit named.

## Real v2 deliverables

### 1. The `agentic-clew` skill

Single markdown file in `_skills/scitex-clew/` (or wherever the project's skill loader picks them up). Imperative form, since LLMs follow `MUST` better than indicative descriptions. Sketch:

```markdown
# agentic-clew skill

When solving a multi-step computation that produces a final answer:

1. BEFORE computing X, call `clew_chain(target=X)` to see what sources
   X will depend on, and `clew_list` filtered to the current session
   to see what is already registered.
2. AFTER computing each intermediate value, MUST call
   `clew.add_claim(id=<name>, value=<result>, parent_session=<upstream session>)`.
   The id should be descriptive (e.g. `acute_correlation_spearman`).
3. BEFORE producing a final answer, MUST call `clew_dag(target_files=<final>)`
   and confirm `is_verified=True`. If a `missing_runs` list comes back,
   compute those before answering.
4. If a registered claim turns out wrong, call `clew_rerun_dag` with the
   affected target and let the existing topo-sorted re-execution
   propagate. Do not start over.

Force + reward:
- Final answers without a passing `clew_dag` verification are not committed.
- Repeated computation of the same input set is automatically a cache
  hit on Clew's side — re-running an identical pipeline returns in ms,
  not the seconds the original took (proven by bix-6: 87 s → 8 s on
  second run via the existing mygene cache pattern).
```

### 2. One small genuine API addition

The v1 API does not currently have a *single-call* "register an intermediate value with explicit support set inside an active session" verb. `clew.add_claim` is oriented toward manuscript-final claims; intermediates currently flow through `stx.io.save()` + the session decorator. For agentic use this should become a thin convenience wrapper:

```python
clew.register_intermediate(
    name: str,                  # human-readable id
    value,                      # the computed object
    supports: list[str],        # explicit upstream claim ids or paths
    session_id: str | None = None,
) -> str                        # returns the hash
```

Implementation: ~30 lines on top of `_claim.add_claim` plus the existing `_db/_chain.set_parent` to record the explicit support edges. Lives on `feat/v2-agent-substrate` until the v1 arxiv ships.

### 3. The pilot harness

Lives in `~/proj/paper-scitex-clew/scripts/v2_pilot/bix6_agent_pilot.py`, NOT in scitex-clew (it is project-side experimentation, not core infrastructure).

| | Arm A | Arm B | Arm C |
|---|---|---|---|
| Agent | claude-haiku-4-5 | claude-haiku-4-5 | claude-haiku-4-5 |
| Tooling | plain Jupyter | scitex + clew + agentic-clew skill | scitex without clew skill |
| Capsule | bix-6 | bix-6 | bix-6 |
| Trials | 5 | 5 | 5 |

Metrics: accuracy match to BixBench reference (`q1=chronic round 2`, `q5=25%`); tokens used; wall clock; backtracking events (count of `recompute_from` / re-fit calls); DAG complexity (B only — n claims registered, depth).

Pass criterion (directional, n=5 per arm): B ≥ 4/5 AND A ≤ 2/5. Modest signal, worth scaling. Fail criterion: B ≤ A on accuracy — the skill adds nothing measurable; revisit phrasing or the force+reward design.

## Scaling plan once pilot is positive

Same arms × 5 capsules (the 5 already-verified-reproducible from BixBench: bix-6, bix-19, bix-29, bix-33, bix-16). N = 5 × 3 × 5 = 75 runs. Statistical baseline.

If the 5-capsule study replicates the pilot's signal, full BixBench-205 × 3 arms × 3 trials ≈ 1850 runs. Spartan with `clew.sif` overnight; cost envelope at claude-haiku rates ≈ $90.

## Out of scope

Multi-agent collaboration on shared DAGs; reasoning over claims across published papers; live editing of the DAG by humans during agent runs. All deferrable.

## Risks and mitigations

The agent does not call Clew often enough → imperative skill phrasing, plus making un-registered intermediates structurally unable to land in the final answer.

The skill phrasing is too verbose and burns context → keep skill ≤200 lines; the existing 19-call API + 9 MCP tools should not need additional wrapper documentation in the skill itself, only the *when-to-call* discipline.

DAG queries become slow at full BixBench-205 scale → SQLite is already indexed in v1; profile at the 5-capsule study if latency exceeds 100 ms per query, pre-compute reachability into a flat materialized view.

## Decision points (user-owned)

The skill ships with `scitex-clew` so any agentic-Clew user gets it automatically, or as a separate repo `agentic-clew` to keep v1's verification claim narrow?

The pilot runs now (parallel with v1 arxiv finalization, on a feature branch), or strictly after arxiv ships?

If positive signal, target Nature 本誌 with paired v1+v2 narrative, or stage v2 arxiv → Nature Methods → Nature?
