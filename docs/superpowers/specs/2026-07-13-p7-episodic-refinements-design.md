# P7 — Episodic Refinements (recall blend · taboo scoping · forge patch/bucketing) Design

> Status: **APPROVED** (built 2026-07-13, task P7). Sources: DEVELOPMENT-PLAN §1 P7; the v1
> specs `2026-06-26-episode-recall-design.md`, `2026-06-27-episode-taboo-veto-design.md`,
> `2026-06-27-forge-auto-promote-demote-design.md` (each names these in its **Out-of-scope**
> section); pb-pc spec. Deferred tuner: DEVELOPMENT-PLAN §4 "Offline recall-weight tuning".

## Goal

Deepen the three shipped v1 episodic-memory capabilities, **each ADDITIVE and DEFAULT-OFF** — a
flag/param left unset ⇒ byte-identical behavior; PIT masking and verdict symmetry preserved and
pinned. Three refinements:

1. **Recall — a soft blended score.** v1 ranks recalled episodes lexicographically by
   `(phase_match, learned_asof, |advantage|)` (a hard, tie-broken filter). This ships a *soft
   blend* over five weighted components — relevance / recency / importance / regime-distance /
   narrative — as a **pure function with documented, hand-set weights** (calibratable; the tuner is
   the deferred §4 item, NOT this task).
2. **Taboo — phase-scoped + recency-windowed.** v1 vetoes a symbol on its *global* PIT-masked nuke
   history. This adds two composable, default-off refinements: **phase-scoped** (veto only if the
   name nukes in the *current* regime) and **recency-windowed** (an old blowup stops tabooing a name
   once it ages out of the window).
3. **Forge — patch-on-promote + per-narrative/phase-scoped aggregation.** v1 emits status-only
   `promote_skill`/`retire_skill` from *global* per-skill evidence. This adds **bucketed promotion
   evidence** (aggregate confirmations within a phase or narrative bucket, not globally) and
   **patch-on-promote** (a surgical `patch_skill` carried alongside the promote, scoping the skill
   to the winning phase — a patch, not a `write_skill` wholesale replace). Lesson demote stays the
   Refiner's job (not built). Retire-on-task stays deferred (no design yet — DEVELOPMENT-PLAN P7).

## Footprint & the default-off contract

Touch only `alpha/memory/*` and `alpha/refine/forge.py` (+ their tests). **No TCB edits** —
`alpha/memory/store.py` and `alpha/agent/retrieval.py` are in `tcb.lock` and stay byte-for-byte
untouched; every refinement lands as a NEW pure module/function or an additive default-off param.

Consumers of recall (`alpha/agent/retrieval.py`, TCB) and taboo (`alpha/guard/screen.py`) are OUT of
this footprint. So refinements #1 and #2 ship as **pure, unit-tested primitives ready to wire**; the
one-line consumer wiring is a documented follow-up (it needs a TCB regen for retrieval, a guard-pkg
edit for screen). Refinement #3 (forge) is wired end-to-end within the footprint (`forge_skills` →
`try_apply_op`), so it ships fully functional through the existing `scripts/evolve_from_episodes.py`.

**Default-off proof obligations (pinned by test):**
- Recall: `alpha/agent/retrieval.py` unchanged ⇒ the live/verdict recall path is byte-identical; the
  new blend is only reachable through the new module. The `recall_store`-into-both-arms verdict
  symmetry is intact by construction.
- Taboo: `summarize` and `is_episode_taboo` are unchanged; a scoped call with no phase and no window
  reduces EXACTLY to `is_episode_taboo(summarize(eps, key=symbol).get(symbol))` — pinned.
- Forge: `propose_skill_ops(bucket_by=None)` and `forge_skills(bucket_by=None, patch_on_promote=False)`
  produce the identical op sequence, order, rationale and provenance as today — the existing
  `test_forge_propose` / `test_forge_apply` suites stay green unchanged.

## Refinement 1 — Recall soft blend (`alpha/memory/recall_score.py`, NEW)

A pure leaf module (imports only `Episode`). No I/O, deterministic.

```python
@dataclass(frozen=True)
class RecallWeights:
    w_rel: float; w_rec: float; w_imp: float; w_reg: float; w_narr: float

DEFAULT_RECALL_WEIGHTS = RecallWeights(w_rel=1.0, w_rec=0.6, w_imp=0.4, w_reg=0.5, w_narr=0.8)

def recall_score(ep, *, asof, phase=None, narrative=None,
                 weights=DEFAULT_RECALL_WEIGHTS, half_life_days=63.0, imp_cap=3.0,
                 phase_of=<identity>, phase_distance=<binary>) -> float
def blended_recall(episodes, *, asof, phase=None, narrative=None, budget=8, **score_kwargs) -> list
```

**The blend** (each component in `[0, 1]`; regime-distance enters as a penalty):

```
score(ep) = w_rel · relevance          # phase-match indicator: 1.0 if phase_of(ep.phase)==phase else 0
          + w_rec · recency            # 0.5 ** (age_days / half_life_days), age = asof - learned_asof
          + w_imp · importance         # min(1.0, |ep.advantage| / imp_cap)  (saturating)
          − w_reg · regime_distance    # phase_distance(ep_phase, phase); default binary {0.0, 1.0}
          + w_narr · narrative_match   # 1.0 if narrative and ep.narrative==narrative else 0
```

- `relevance` (reward for match) and `regime_distance` (penalty for mismatch) are an **asymmetric
  pair**, not redundant: match ⇒ `+w_rel`, mismatch ⇒ `−w_reg`. Default `phase_distance` is binary
  (`0.0` when equal, else `1.0`); a future wiring supplies a *graded* growth-clock distance
  (confirmed↔pressure closer than confirmed↔correction) — the point of a separate `w_reg` knob.
- `narrative` defaults to `None` ⇒ `narrative_match` is inert (0) — faithful to the v1 deferral
  "narrative-scoped recall blocked on pre-decision narrative/theme signals". When a pre-decision
  narrative signal exists, pass it and `w_narr` activates.
- `phase_of` defaults to identity (so unit tests pass canonical strings directly); a wiring passes
  `phase_from_read` (episodes store RAW prose in `.phase`).
- `blended_recall` **PIT-guards defensively**: it drops any `ep.learned_asof > asof` before scoring
  (upstream `for_asof` already masks; this belt-and-suspenders keeps the pure function honest and
  makes the blend layer independently PIT-testable), then sorts by `score` desc (tie: `learned_asof`
  desc, `episode_id`) and returns the top `budget`.

**v1 is the hard limit of this soft blend.** With phase dominating, then recency, then |advantage|,
`blended_recall` reproduces v1's `(phase_match, recency, |adv|)` ordering — so a future wiring is a
graceful generalization, not a behavior swap.

### Weights table (hand-set / 文献-informed — CALIBRATABLE)

| symbol | component | default | why this default |
|---|---|---|---|
| `w_rel` | phase-relevance (match indicator) | **1.0** | primary signal; mirrors v1's phase-match-first rank |
| `w_rec` | recency (exp decay) | **0.6** | second; recent outcomes more predictive |
| `w_imp` | impact (\|advantage\|, saturating) | **0.4** | third; mirrors v1's \|adv\| tiebreak |
| `w_reg` | regime-distance penalty | **0.5** | penalize off-regime recall (graded once clock-distance wired) |
| `w_narr` | narrative match | **0.8** | strong when a pre-decision narrative exists; inert by default |
| `half_life_days` | recency half-life | **63** | ≈ one quarter of trading days |
| `imp_cap` | \|advantage\| saturation cap | **3.0** | advantage beyond this adds no more impact weight |

> These are hand-set starting values, **not** tuned. The deferred DEVELOPMENT-PLAN §4 "Offline
> recall-weight tuning" is the calibrator (sweeps `w_*` + the regime-distance penalty over captured
> PIT windows, pins winners to an H-version). Until then they may be adjusted via self-study/teaching.

## Refinement 2 — Taboo phase-scoping + recency window (`alpha/memory/aggregate.py`, additive)

`summarize` / `EpisodeStats` / `is_episode_taboo` / `TaskStats` / `summarize_task` are **unchanged**.
Three additive pure functions:

```python
def within_recency_window(episodes, *, asof, window_days) -> list[Episode]
    # keep episodes with (asof - window_days) <= learned_asof <= asof  (enforces BOTH bounds → PIT-safe)
def matching_phase(episodes, *, phase, phase_of=<identity>) -> list[Episode]
    # keep episodes whose phase_of(ep.phase) == phase_of(phase)
def is_episode_taboo_scoped(episodes, symbol, *, phase=None, phase_of=<identity>,
                            window_days=None, asof=None, min_samples=3, nuke_rate=0.5) -> bool
    # compose: (window filter?) -> (phase filter?) -> summarize(key=symbol) -> is_episode_taboo(stats[symbol])
```

- **Default reduction (pinned):** `is_episode_taboo_scoped(eps, sym)` (no `phase`, no `window_days`)
  == `is_episode_taboo(summarize(eps, key=lambda e: e.symbol).get(sym))` — the exact v1 semantics.
- **Phase-scoped:** pass `phase=<current canonical regime>` (+`phase_of=phase_from_read` when wiring
  raw-prose episodes). A name that nukes only in phase X is tabooed at `phase="X"` and cleared at
  `phase="Y"`; global (`phase=None`) reflects the combined history.
- **Recency-windowed:** pass `window_days=W` (+`asof`). A name whose only nukes are older than `W`
  days ages out — `n` inside the window drops below `min_samples` (or `nuke_rate` falls), so an old
  blowup no longer tabooes forever. `within_recency_window` enforces `<= asof` too, so it is PIT-safe
  even if handed an un-masked list.
- Both compose (phase + window together). `window_days` requires `asof`; `is_episode_taboo_scoped`
  raises `ValueError` if `window_days` is set without `asof` (fail-loud, not silent).

Consumer wiring into `alpha/guard/screen.py` (swap the `is_episode_taboo(...)` call for
`is_episode_taboo_scoped(..., phase=canon, phase_of=phase_from_read, window_days=..., asof=state.date)`
with a per-source config knob) is a documented **follow-up** — out of the P7 footprint (guard pkg).
Default-off holds because screen.py is untouched.

## Refinement 3 — Forge patch-on-promote + bucketed evidence (`alpha/refine/forge.py`)

`propose_skill_ops` gains `bucket_by: Literal["phase","narrative"] | None = None`; `forge_skills`
gains `bucket_by=None, patch_on_promote=False`. `_FORGE_ALLOWED` and `ForgeReport` are unchanged
(task_forge imports them). A shared internal `_propose(...)` returns `_Proposal(op, patch)` records;
`propose_skill_ops` returns `[p.op for p in _propose(...)]` (its public list-of-ops contract intact).

**Bucketed promotion evidence.** Retire always uses the GLOBAL per-skill aggregate
(`summarize(eps, key=skill_id)`) — a demote must reflect *broad* failure and must never be diluted by
bucketing. Promotion evidence switches on `bucket_by`:
- `None` (default): global per-skill stats — byte-identical to today, same op order (iterates
  `global_stats.items()`), same rationale string.
- `"phase"` / `"narrative"`: episodes are grouped per `(skill_id, bucket)` where the bucket is the
  canonical phase (`phase_of(ep.phase)`) or the raw `ep.narrative`. An incubating skill promotes on
  its **best qualifying bucket** (`n≥promote_min_samples`, `win_rate≥promote_min_winrate`,
  `mean_advantage>0`), chosen deterministically by `(win_rate, n, bucket)`; the rationale cites the
  winning bucket. This lets a skill that only works in *one* regime/narrative earn a promotion its
  diluted global average would deny.

**Patch-on-promote.** When `patch_on_promote=True` AND `bucket_by="phase"` AND the winning phase
canonicalizes to a real token, `_propose` attaches a `patch_skill` op that narrows the skill to that
phase: `args={"skill_id", "phases": [canon], "applies_all_phases": False}` (surgical — a patch, not a
`write_skill` replace). Skipped (no patch, promote-only) when the skill is already scoped to exactly
that phase (would be an empty/no-op patch the gate rejects), or for `bucket_by="narrative"` (no skill
field for narrative). `forge_skills` applies the patch **only after the promote lands** — a rejected
promote never patches — through the same one gate with `allowed = _FORGE_ALLOWED | {"patch_skill"}`
(the widened set is used only when `patch_on_promote` is on; the module constant is unchanged, so
task_forge is unaffected).

**Governance unchanged.** Every op still flows through `try_apply_op` with
`EditProvenance(path="self_study", proposer="forge")`: red-lines, the promote/retire skill-stats
double-gate, empty-patch + domain-immutable guards, and the `conflict_queue` teaching-owned
escalation all bind. A forge patch that contests a teaching-owned skill is HELD, never auto-applied.

## PIT safety

- Recall: `blended_recall` drops `learned_asof > asof` before scoring; recency uses
  `age = asof − learned_asof` (never negative). Upstream `for_asof(asof, limit=None)` remains the
  primary mask (unchanged).
- Taboo: `within_recency_window` enforces `learned_asof <= asof`; the input is the existing
  `for_asof(state.date, limit=None)` PIT-masked pool.
- Forge: reads `for_asof(asof, limit=None)` (masks `learned_asof <= asof`) exactly as today; bucketing
  and patching operate on that already-masked pool.

## Testing (all offline, deterministic, keyless)

- **Default-off / byte-identical (pins):** existing `tests/memory/test_aggregate.py`,
  `tests/refine/test_forge_propose.py`, `tests/refine/test_forge_apply.py` stay green unchanged;
  a new test asserts `is_episode_taboo_scoped(eps, sym)` == the v1 two-step; a new test asserts
  `propose_skill_ops(bucket_by=None)` and `forge_skills(bucket_by=None, patch_on_promote=False)` emit
  the same ops as the v1 path.
- **Recall blend correctness (`tests/memory/test_recall_score.py`):** each component in isolation
  (phase match → +w_rel; recency decay at one/two half-lives; importance saturates at imp_cap;
  mismatch → −w_reg; narrative match → +w_narr; narrative=None inert); the full weighted sum on a
  hand-computed case; `blended_recall` ranks a same-phase-recent-high-adv episode first and honors
  the budget; PIT: a `learned_asof > asof` episode is dropped.
- **Taboo scoping (`tests/memory/test_taboo_scoped.py`):** phase-scoped vetoes only in-regime
  (nukes in X, clean in Y → taboo at X, not at Y, combined at None); recency window expires an old
  blowup (old nukes + recent cleans → global taboo True, windowed False); `within_recency_window`
  enforces both bounds (PIT); `window_days` without `asof` raises.
- **Forge patch + bucketing (`tests/refine/test_forge_patch_bucket.py`):** a skill whose global
  average fails but whose phase-bucket clears the floor promotes under `bucket_by="phase"` and NOT
  under the default; `patch_on_promote=True` lands a `patch_skill` narrowing `phases` to the winning
  phase (asserted on harness state), only after the promote; a rejected promote (double-gate) leaves
  no patch; retire stays global under bucketing; narrative bucketing promotes without a patch.

## Why this shape

- Every refinement is a NEW pure primitive or an additive default-off param — no TCB touched, no
  consumer forced to change, byte-identical until deliberately enabled (exactly how recall/taboo/forge
  v1 and the `screen`/`size` flags were introduced).
- The recall blend generalizes v1's lexicographic rank (v1 = the hard limit), so wiring it on later is
  a smooth calibration, not a rewrite — and it hands the deferred §4 tuner a clean weight vector.
- Taboo scoping composes over the existing `summarize`/`is_episode_taboo` leaf; the guard consumer
  swaps one call.
- Forge bucketing/patching reuses the whole gate + provenance + conflict machinery; retire stays
  global so bucketing can only *add* confirmations, never hide failures.
```

