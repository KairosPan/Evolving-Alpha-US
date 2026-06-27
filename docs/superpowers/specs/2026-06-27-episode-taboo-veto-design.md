# Episode-Taboo → L4 Veto (§6 #3) + Episode Aggregation Design

> Status: **APPROVED** (brainstormed 2026-06-27). Next: writing-plans.
> Scope: §6 subsystem #3 (the read-path guard) + the shared episode-aggregation primitive that §6 #2 (auto-promote/demote) will reuse. #2 is its own later spec→plan cycle.

## Goal

Episodes now record outcomes (`continued | faded | nuked`) and are recalled into decisions (§6 v1), but nothing *acts* on a name's negative history. This adds an **episode-taboo veto**: when a candidate symbol has a strong PIT-masked nuke history, the existing L4 guard hard-vetoes the new entry — "this name keeps blowing up on us, don't chase it." It also builds the **shared episode-aggregation primitive** (group PIT-masked episodes into per-key stats) that §6 #2 will reuse for per-skill promote/demote.

## Confirmed decisions (from brainstorming)

1. **#3 first** (the smaller, read-path, lower-risk subsystem); it builds the shared aggregation primitive that #2 reuses. #2 (auto-promote/demote) is a separate later cycle.
2. **Taboo grain = per-symbol, overall** (not phase-scoped) — a name with enough history that mostly nukes is vetoed regardless of the current regime. Phase-scoped taboo is a noted later refinement.
3. **Thresholds: `min_samples=3`, `nuke_rate≥0.5`** — ≥3 PIT-masked episodes for the symbol AND a majority (≥50%) nuked.
4. **PIT-safe / default-off / verdict-symmetric** — recall is masked at `as_of=state.date`; `episode_store=None` → no episode-taboo (byte-identical, verdict-neutral), exactly like episode-recall's wiring. The verdict/compare arms stay symmetric when wired on.

## Architecture

Three additive touches + one new tiny module:

### 1. The shared aggregation primitive — `alpha/memory/aggregate.py` (NEW)

- `EpisodeStats` (frozen pydantic): `n: int`, `continued: int`, `faded: int`, `nuked: int`, `mean_advantage: float`, plus computed `nuke_rate` (`nuked/n`) and `win_rate` (`continued/n`) — `n==0` → rates `0.0`.
- `summarize(episodes: list[Episode], *, key: Callable[[Episode], str]) -> dict[str, EpisodeStats]` — pure, deterministic; groups by `key` and tallies outcomes + mean advantage. (#3 uses `key=lambda e: e.symbol`; #2 will use `key=lambda e: e.skill_id`.)
- `is_episode_taboo(stats: EpisodeStats | None, *, min_samples: int = 3, nuke_rate: float = 0.5) -> bool` — `stats is not None and stats.n >= min_samples and stats.nuke_rate >= nuke_rate`.

This module imports only `Episode` (no guard/agent deps) — a clean, reusable leaf.

### 2. The veto signal — `alpha/guard/veto.py`

- `CandidateContext` gains `episode_taboo: bool = False` (additive frozen-dataclass field).
- `veto()` gains a reason (after the existing flag checks): `if ctx.episode_taboo: reasons.append("episode taboo: strong nuke history (don't chase)")`.

### 3. The wiring — `alpha/guard/screen.py`

- `screen_decision(decision, *, source, state, episode_store=None)` — when `episode_store is not None`: recall `eps = episode_store.for_asof(state.date)` (PIT-masked) ONCE, `stats = summarize(eps, key=lambda e: e.symbol)`; per candidate set `ctx.episode_taboo = is_episode_taboo(stats.get(c.symbol))`. Vetoed candidates are dropped + reason recorded in `key_risks` (the existing path). `episode_store=None` → `episode_taboo` stays `False` (byte-identical).
- `GuardedPolicy.__init__(inner, source, *, episode_store=None)` — stores it; `decide` passes `episode_store=self._episode_store` into `screen_decision`.

## Data flow

```
EpisodeStore.for_asof(state.date) ──► PIT-masked episodes
                                            │  summarize(key=symbol) -> {symbol: EpisodeStats}
                                            ▼
  screen_decision(decision, episode_store) ──► per candidate: ctx.episode_taboo = is_episode_taboo(stats[symbol])
                                            │   veto(ctx) -> drop if (episode_taboo OR existing reasons)
                                            ▼
                                     DecisionPackage (taboo names dropped, reason in key_risks)
```

## PIT safety

Recall goes through `EpisodeStore.for_asof(state.date)` which masks `learned_asof <= state.date` (`superseded = 0` too). A nuke whose outcome became knowable after the decision date cannot taboo that decision. The test asserts a future-`learned_asof` nuke does NOT veto an earlier-date candidate.

## Error handling

- `episode_store=None` (default) → no recall, no taboo, never raises.
- A symbol with no episodes → `stats.get(symbol)` is `None` → `is_episode_taboo(None)` → `False` (not vetoed).
- `n < min_samples` → not taboo (the sample-floor prevents one bad print from vetoing).

## Testing (all offline, deterministic)

- **`summarize` / `is_episode_taboo`** (`tests/memory/`): grouping by key tallies continued/faded/nuked + mean advantage correctly; `nuke_rate`/`win_rate` math (incl. `n==0`); `is_episode_taboo` honors `min_samples` (n=2 all-nuked → False) and `nuke_rate` (n=4, 2 nuked = 0.5 → True; 1 nuked = 0.25 → False).
- **`veto`** (`tests/guard/`): `episode_taboo=True` → `vetoed` with the reason; other flags unaffected; `episode_taboo=False` alone → not vetoed.
- **`screen_decision`** (`tests/guard/`): an in-memory `EpisodeStore` seeded so symbol RUN has ≥3 PIT-masked nuked episodes → a RUN candidate is DROPPED with the taboo reason in `key_risks`; a future-`learned_asof` nuke at an earlier `state.date` does NOT taboo (PIT); `episode_store=None` → candidates unchanged (byte-identical).
- **`GuardedPolicy`** (`tests/guard/` or `tests/agent/`): constructed with `episode_store=`, `decide` over a FakeSource → the taboo candidate is dropped (end-to-end threading).
- Existing guard/screen/GuardedPolicy tests stay green (additive `episode_store=None`).

## Out of scope (deferred)

- **§6 #2 gated auto-promote/demote** — the next cycle; reuses `summarize(key=skill_id)` + `is_*` thresholds.
- **Phase-scoped taboo** (veto only if the name nukes in the *current* regime) — a refinement; v1 is per-symbol overall.
- **Recency-windowed taboo** (only recent nukes count) — v1 uses all PIT-masked episodes for the symbol with the sample-floor.
- ✅ **DONE (2026-06-27)** — **Wiring the live/verdict decide path ON** (symmetric arms), shared with episode-recall's on-switch. Shipped via `docs/superpowers/plans/2026-06-27-episode-readside-on.md`: taboo runs on the act path (`save_decisions --brain`), the evolving path (`refine_live`), and the verdict (`run_verdict --brain`, read-only `recall_store` through `GuardedPolicy` on every arm — symmetric). The `for_asof` 50-cap was lifted at the taboo aggregation site (`limit=None`), so a symbol's full PIT-masked nuke history is counted (a test proves taboo now fires past the old 50-cap). Default-off preserved (no brain → byte-identical).

## Why this shape

- It reuses the entire existing L4 veto stack (`veto`/`CandidateContext`/`screen_decision`/`GuardedPolicy`) — the net-new is one leaf module (`aggregate.py`), one context flag, one veto reason, and one optional `episode_store` thread.
- The `aggregate.py` primitive is the foundation §6 #2 builds on, so doing #3 first front-loads it.
- Default-off + PIT-masked + verdict-symmetric matches exactly how episode-recall and the screen flag were introduced — risk-free until deliberately enabled.
