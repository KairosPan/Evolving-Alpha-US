# The Forge — Gated Auto-Promote/Demote from Episodes (§6 #2) Design

> Status: **APPROVED** (brainstormed 2026-06-27). Next: writing-plans.
> Scope: §6 subsystem #2 — the LAST §6 piece. A deterministic, LLM-free episode-evidence-driven self-evolution proposer that promotes/demotes skills through the existing gate.

## Goal

Episodes are written (§6) and now recalled (§6 v1) + vetoed-on (§6 #3), but no skill is *promoted or demoted* from their evidence. The forge closes that: aggregate per-skill episode outcomes (`summarize(key=skill_id)` — the §6 #3 primitive) and, for skills whose history is decisively good or bad, propose `promote_skill` / `retire_skill` through the existing gate — with the gate's own skill-stats floors as a second confirmation and the §5 `conflict_queue` so a contest of a teaching-owned skill escalates to the user instead of auto-applying. Deterministic and LLM-free.

## Confirmed decisions (from brainstorming)

1. **Demote = soft (`dormant`, revivable).** `retire_skill(permanent=False)` → `active → dormant`; `revive_skill` brings it back. An autonomous demote benches a skill, never permanently kills it (matches the system's reversibility discipline).
2. **A standalone deterministic script** (`scripts/evolve_from_episodes.py`), mirroring `refine_live`'s lock→load→propose→save shape but with the episode proposer (no LLM, no PIT window) — a different trigger/cadence than `refine_live`'s InnerLoop pass.
3. **Thresholds:** promote = `incubating` + `n≥5` + `win_rate≥0.5` + `mean_advantage>0`; retire = `active` + `n≥5` + `nuke_rate≥0.5`. Tunable params.
4. **Close the write→read loop:** wire `refine_live` to *write* episodes to `ALPHA_EPISODES_DB` (it currently runs the InnerLoop with `episode_store=None`), so the forge has real data to read.
5. **Double-gate + teaching-owned escalation:** the episode aggregate *proposes*; the gate independently *confirms* on the skill's own stats; teaching-owned contests are HELD (§5), never auto-applied.

## Architecture

### 1. The proposer — `alpha/refine/forge.py` (NEW)

`propose_skill_ops(harness, episode_store, *, asof, promote_min_samples=5, promote_min_winrate=0.5, retire_min_samples=5, retire_min_nukerate=0.5) -> list[RefineOp]`:
- `stats = summarize(episode_store.for_asof(asof), key=lambda e: e.skill_id)` (PIT-masked; `for_asof` masks `learned_asof <= asof`).
- For each `skill_id` present in BOTH `stats` and `harness.skills`:
  - `skill.status == "incubating"` AND `s.n >= promote_min_samples` AND `s.win_rate >= promote_min_winrate` AND `s.mean_advantage > 0` → `RefineOp(tool="promote_skill", args={"skill_id": skill_id}, rationale=f"forge: episode evidence n={s.n} win_rate={s.win_rate:.2f} mean_adv={s.mean_advantage:+.2f}")`.
  - `skill.status == "active"` AND `s.n >= retire_min_samples` AND `s.nuke_rate >= retire_min_nukerate` → `RefineOp(tool="retire_skill", args={"skill_id": skill_id, "permanent": False}, rationale=f"forge: episode evidence n={s.n} nuke_rate={s.nuke_rate:.2f} mean_adv={s.mean_advantage:+.2f}")`.
- Deterministic + pure (reads, never writes). Returns the op list (possibly empty).

### 2. The gated applier — `forge_skills(harness, episode_store, meta, *, asof, conflict_queue=None, min_promote_samples=3, min_retire_samples=5, **proposer_kwargs) -> ForgeReport`

- `ops = propose_skill_ops(harness, episode_store, asof=asof, **proposer_kwargs)`.
- For each op: `try_apply_op(meta, harness, op, allowed=frozenset({"promote_skill", "retire_skill"}), min_promote_samples=min_promote_samples, min_retire_samples=min_retire_samples, provenance=EditProvenance(path="self_study", proposer="forge"), conflict_queue=conflict_queue)`.
- **Double-gate:** the episode aggregate triggers the proposal; the gate independently enforces the skill's OWN stats (promote: `skill.stats.n >= min_promote_samples` AND `expectancy > 0`; retire: `skill.stats.n >= min_retire_samples`). An op applies only if BOTH agree. A held outcome (teaching-owned contest, §5) is enqueued, never applied.
- `ForgeReport(applied: list[str], held: list[str], rejected: list[tuple[str, str]])` (skill_ids + reject reasons), e.g. counts for the runner to print.

### 3. The runner — `scripts/evolve_from_episodes.py` (NEW, mirrors `refine_live.py`)

`run_evolve_from_episodes(*, brain_dir, conflicts_dir, episodes_db, asof, **kwargs) -> dict`:
- Under `LiveBrainStore(brain_dir).lock()`: `h, log = bstore.load()`; `episode_store = EpisodeStore.open(episodes_db)`; `report = forge_skills(h, episode_store, MetaTools(h, log), asof=asof, conflict_queue=ConflictQueue(conflicts_dir))`; `bstore.save(h, log)`.
- Returns `{"applied": [...], "held": [...], "rejected": [...]}`.
- CLI: `evolve_from_episodes.py [--asof YYYY-MM-DD]` (default = today, passed in — scripts get the date via arg since `date.today()` is fine in a script); env `ALPHA_LIVE_BRAIN_DIR` / `ALPHA_CONFLICTS_DIR` / `ALPHA_EPISODES_DB` (default `./state/brain.db`). LLM-free.

### 4. Close the write→read loop — `scripts/refine_live.py` + `alpha/loop/inner_loop.py`

`refine_live.run_refine_live` opens `EpisodeStore.open(os.environ.get("ALPHA_EPISODES_DB", …))` and passes `episode_store=` into the `InnerLoop(...)` (the InnerLoop already threads it to `apply_credit`). So refine_live now *writes* episodes to the same brain.db the forge *reads*. Additive (an optional `episodes_db=None` param on `run_refine_live`; when None, episode writing stays off — existing refine_live tests unchanged).

## Data flow

```
refine_live (InnerLoop, episode_store) ──writes──► brain.db (EpisodeStore)
                                                          │  forge reads
  evolve_from_episodes ── LiveBrainStore.lock() ──► summarize(for_asof(asof), key=skill_id)
                                                          │  propose_skill_ops (promote/retire)
                                                          ▼
              try_apply_op (gate: skill-stats floor; provenance forge/self_study; conflict_queue)
                ├─ both floors agree, not teaching-owned ─► applied (incubating→active / active→dormant)
                ├─ contests a teaching-owned skill ────────► HELD → ConflictQueue → Conflicts page
                └─ skill-stats floor disagrees ────────────► rejected (no change)
                                                          ▼
                                            LiveBrainStore.save(evolved H)
```

## PIT safety

The forge reads `episode_store.for_asof(asof)` (masks `learned_asof <= asof`). For an offline operator run, `asof` is the run date — only episodes whose outcomes are knowable by then drive promotions/demotions. (The forge is not in the live decide path, so there is no per-decision PIT key here — it is a deliberate maintenance pass.)

## Error handling / safety

- **Gated:** every change goes through the one write-waist (`try_apply_op`) — rationale + the skill-stats evidence floor + red-lines apply.
- **Soft demote:** `retire_skill(permanent=False)` → dormant (revivable), never `retired`.
- **Teaching-owned escalation:** a forge op contesting a teaching-owned skill is HELD to the `conflict_queue` (§5), never auto-applied.
- **Brain lock:** the runner holds `LiveBrainStore.lock()` across load→forge→save (serialized vs Sonia / workbench / refine_live).
- **Empty/missing brain.db:** `EpisodeStore.open(create_if_missing=True)` → no episodes → no ops → no-op run (not an error).
- **Operator script:** errors propagate (fail loud), like `refine_live`.

## Testing (all offline, deterministic)

- **`summarize` reuse / `propose_skill_ops`** (`tests/refine/`): an incubating skill with 5 wins / mean_adv>0 → a `promote_skill` op; an active skill with ≥50% nuked → a `retire_skill(permanent=False)` op; status gating (an ACTIVE skill with great stats → no promote; an INCUBATING skill with nukes → no retire); below-floor → no op. PIT (`for_asof`) honored.
- **`forge_skills` (the double-gate)** (`tests/refine/`): an incubating skill whose episode evidence AND `skill.stats` both clear the floors → applied (status `active` in the harness); a skill whose episodes say promote but `skill.stats.expectancy<=0` → REJECTED by the gate (the double-gate); a teaching-owned active skill the episodes want to retire (with a `conflict_queue`) → HELD (in the queue, status unchanged).
- **runner e2e** (`tests/scripts/`): seed a tmp live brain (an incubating skill with strong `SkillStats`) + a tmp brain.db (strong-positive episodes for it) → `run_evolve_from_episodes` → the SAVED live brain has the skill `active`; held/rejected reported.
- **refine_live write loop** (`tests/scripts/`): `run_refine_live(..., episodes_db=tmp)` → after the run, the brain.db has episodes (the write loop closed); `episodes_db=None` → no episode store (existing behavior unchanged).
- Existing gate / refine / InnerLoop / refine_live tests stay green (all additions are additive params / new files).

## Out of scope (deferred)

- **Memory (lesson) demote from episodes** — episodes are keyed by skill; lesson demote stays the Refiner's job.
- **Promotion to a richer skill edit** (patch on promote) — v1 is status-only promote/retire.
- **A console/UI trigger** for the forge (offline operator script for now; shares the deferred refine-live UI-trigger item).
- **Per-narrative / phase-scoped forge** — v1 aggregates per skill overall.

## Why this shape

- Reuses everything: `summarize` (§6 #3), the gate + floors + provenance + `conflict_queue` (§5), the `refine_live` runner shape, the `LiveBrainStore.lock()`. The net-new is one `forge.py` proposer/applier + one runner + a small episode-write wire into `refine_live`.
- The **double-gate** (episode evidence proposes; skill-stats floor confirms) makes autonomous promotion/retirement conservative — both independent signals must agree.
- Deterministic + LLM-free keeps the forge cheap, auditable, and reproducible — the opposite end of the spectrum from the LLM Refiner, but routed through the same one gate.
