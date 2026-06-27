# Episode Recall Into Decisions (§6 recall scoring, v1) Design

> Status: **APPROVED** (brainstormed 2026-06-26). Next: writing-plans.
> Scope: v1 of §6 recall — read the written episodes back INTO the agent's decisions. Decomposed from the §6 bundle; auto-promote/demote (#2) and taboo→L4 veto (#3) are deferred to their own spec→plan cycles.

## Goal

§6 writes `Episode` rows to `brain.db` (`EpisodeStore`) at the credit seam with a PIT-safe `learned_asof`, and `EpisodeStore.for_asof(asof, phase=…, narrative=…, limit=…)` already recalls them PIT-masked — but **nothing reads them back into a decision**. The agent (`LLMAgentPolicy`) injects PIT-masked *lessons* into its prompt but has no `EpisodeStore` handle and never recalls episodes. This wires the read path: recall PIT-masked episodes, **score them by regime relevance**, and inject the top-K into the agent's decision prompt — the first time episodes actually influence a decision.

## Confirmed decisions (from brainstorming)

1. **v1 scope = recall-into-decisions only.** Auto-promote/demote (#2) and taboo→L4 veto (#3) are deferred (each its own spec/plan) — both *aggregate* recalled episodes, so the recall+scoring path is the foundation they build on.
2. **Regime/phase-scored ranking, recency + |advantage|.** Recall within the matched phase (the current regime), rank by `learned_asof` desc with `|advantage|` as the impact tiebreak, top-`budget`. A soft blended score is a later refinement.
3. **Narrative-scoping deferred.** Narrative is assigned per-candidate *post*-decision (and needs theme breadth — already a deferred item); v1 is regime/phase-scored only.
4. **Additive / default-off / symmetric verdict.** No `EpisodeStore` wired → byte-identical to today. This is the first §6 piece that is *not* verdict-neutral (it changes decisions — the point); safety is that the `compare_harnesses`/verdict path stays **symmetric** (both arms get the same store or neither), exactly like the `screen` flag.

## Architecture

Three additive touches, no new modules:

### 1. The recall+scoring unit — `alpha/agent/retrieval.py`

`select_episodes_for_prompt(episode_store, *, phase_prior: str | None, asof, budget: int = 8) -> list[Episode]` (mirrors `select_for_prompt`):
- `episode_store is None` (or `asof is None`) → `[]`.
- Recall via `episode_store.for_asof(asof)` (broad, its existing default `limit` — a PIT-masked pool; `learned_asof <= asof` enforced inside `for_asof`, so PIT-safe by construction). NB: episodes store the **raw** `regime_read` as `phase`, while `phase_prior` is the **canonical** token — so the regime match is done in the ranking (`normalize_phase(episode.phase) == canon`), NOT as a SQL `phase=` filter.
- **Rank** the recalled episodes by `(phase_match, learned_asof desc, abs(advantage) desc)` — episodes whose canonicalized phase matches the current regime first, then recency, then impact; take the top `budget`. (`phase_prior is None` → no phase boost; pure recency + |advantage|.)
- Self-normalizes `asof` (`datetime → date`) the same way `select_for_prompt` does, for a direct caller.

### 2. Injection — `alpha/agent/prompt.py`

`build_system_prompt(h, *, injection="full", phase_prior=None, …, asof=None, episode_store=None, episode_budget: int = 8)`:
- When `episode_store is not None`, call `select_episodes_for_prompt(episode_store, phase_prior=phase_prior, asof=asof_d, budget=episode_budget)` and render a compact **`RECALLED EPISODES`** block immediately after the lessons block — one line per episode: `[<phase>] <SYMBOL>/<skill_id> -> <outcome> (adv <±advantage>): <reflection_text>`.
- `episode_store is None` (the default) → no block; byte-identical to today's prompt.
- Applies in BOTH injection modes (`full` and the curated mode), matching the lesson PIT-mask treatment.

### 3. Wiring — `alpha/agent/agent.py`

`LLMAgentPolicy(h, llm, *, episode_store=None)` stores the handle and passes it into `build_system_prompt(..., asof=state.as_of, episode_store=self._episode_store)` in `decide` (alongside the existing `asof` threading). Default `None` → off.

## Data flow

```
brain.db (EpisodeStore) ──for_asof(asof, phase=phase_prior)──► PIT-masked episodes
                                                                      │  rank (learned_asof desc, |adv| desc), top-K
                                                                      ▼
  LLMAgentPolicy.decide(state, universe) ──► build_system_prompt(asof=state.as_of, episode_store)
                                                   │  renders RECALLED EPISODES block (after lessons)
                                                   ▼
                                            prompt ──► LLM ──► DecisionPackage
```

## PIT safety

The recall is PIT-safe by construction: `for_asof` masks `learned_asof <= asof`, and the agent passes `asof = state.as_of` (the same key used for lessons). No episode whose outcome became knowable after the decision date can surface. The tests assert a future-`learned_asof` episode is excluded.

## Error handling

- `episode_store` is the only new input; `None` → empty recall (no block), never raises.
- A malformed/empty `brain.db` (no episodes) → `for_asof` returns `[]` → no block (not an error).
- Rendering tolerates empty `reflection_text`/`narrative` (the Episode defaults are `""`).

## Testing (all offline, deterministic)

- **`select_episodes_for_prompt`** (`tests/agent/`): with an in-memory `EpisodeStore` seeded with episodes across phases + `learned_asof` dates — (a) a future-`learned_asof` episode is excluded at an earlier `asof` (PIT mask); (b) `phase_prior` filters to the matched phase; (c) ranking is recency-then-|advantage| and the budget cap holds; (d) `episode_store=None` → `[]`; (e) `phase_prior=None` → recall across phases.
- **`build_system_prompt`** (`tests/agent/`): with a store, the built prompt contains a `RECALLED EPISODES` block with the recalled episode lines and honors `asof` (a future episode absent); without a store, no block (and the rest of the prompt is unchanged).
- **`LLMAgentPolicy.decide`** (`tests/agent/`): constructed with an `episode_store`, a `MarketState` with `as_of`, drives `decide` and asserts (via a capture/MockLLM that records the system prompt) that a recalled episode line is in the prompt the LLM saw — i.e. the store + `state.as_of` were threaded.
- Existing agent/prompt/retrieval tests stay green (additive `episode_store=None`).

## Out of scope (deferred, each its own spec→plan)

- **#2 gated auto-promote/demote** from aggregated episode evidence.
- **#3 taboo→L4 veto** from strongly-negative episodes.
- Soft blended recall score (beyond recency + |advantage|); narrative-scoped recall (needs pre-decision narrative/theme signals).
- ✅ **DONE (2026-06-27)** — Wiring the live `EpisodeStore` into the production decide path + the verdict harness's symmetric arms. Shipped via `docs/superpowers/plans/2026-06-27-episode-readside-on.md`: recall reads the live brain on the act path (`save_decisions --brain`/`$ALPHA_EPISODES_DB`) and the evolving path (`refine_live`, `recall_store=episode_store`); the verdict (`run_verdict --brain` → `compare_harnesses`/`multi_window`) threads a **read-only** `recall_store` symmetrically into both arms (HCH via `InnerLoop.recall_store`, NEVER `episode_store=` — no self-write; Hexpert via `LLMAgentPolicy(episode_store=…)`). The `for_asof` 50-cap was lifted at the recall read site (`limit=None`). Default-off preserved (no brain → byte-identical).

## Why this shape

- It reuses the existing `for_asof` PIT-masked recall and the existing lesson-injection pattern (`select_for_prompt` + `build_system_prompt` + the `asof` threading) — the net new surface is one retrieval function + one prompt block + one agent param.
- Default-off + symmetric-verdict keeps the change risk-free until deliberately enabled, consistent with how `screen`/`size` were introduced.
- Regime/phase-scored recall is the explainable foundation; #2 and #3 (the episode write-back and veto uses) sit cleanly on top once episodes are recalled and scored.
