# P0.6 — Guard/Sizing trim-derisk action vocabulary (design)

Status: drafted 2026-07-13 (DEVELOPMENT-PLAN §1 P0.6). Scope: `alpha/guard` + `alpha/sizing`
only. Companion field request to the P0.5 owner is in §6.

## 1. The problem, restated from the code

The doctrine's `derisk_on_breakdown.rule` (growth manuscript §4.4: 持仓龙头单日量 ≥ 2× 20 日均量且
收盘跌破 50 日线 → 触发 event_reread + 持仓降至核心仓位（原仓位的 1/2）) has **no execution
surface**. The manuscript itself marks it prose-level (§4.4, §0.7-4, Appendix-B row
`derisk_on_breakdown.rule | guard/sizing trim | 落点不存在 | 阻塞`).

## 2. Exploration finding — holdings are NOT modeled anywhere

Traced the whole decide path. Every layer is stateless day-to-day with respect to *what we
already hold*:

- `DecisionPackage` / `Candidate` (`alpha/eval/decision.py`) — a day's `a_t`: a list of NEW picks
  to ENTER (symbol, confidence, narrative, entry, exit_stop, size_tier…). No field carries a
  current position, held-since date, or held size.
- `LLMAgentPolicy.decide` (`alpha/agent/agent.py`) — reads `state + universe → DecisionPackage`.
  No holdings input.
- `GuardedPolicy` / `screen_decision` (`alpha/guard/screen.py`) — `veto(ctx)` computes an L4
  hard veto on a **new entry** and DROPS the vetoed candidate. `CandidateContext` is entirely
  "inputs the guard needs to clear a NEW entry".
- `SizingPolicy` / `size_decision` (`alpha/sizing/policy.py`) — assigns `size_tier` to each KEPT
  candidate and a `Portfolio` exposure plan. Sizes **new** decisions. Verdict-neutral.
- `InnerLoop.run` (`alpha/loop/inner_loop.py`) — each day `decision = agent.decide(...)`;
  `entries = {c.symbol: … for c in decision.candidates}`; scored at `t+horizon`. No position
  ledger carried across days; each day is an independent new-entry decision.
- `save_decisions.py` — act-only, one package/day, no holdings.
- Scoring (`ReturnScorer`/`PoolScorer`, `alpha/eval/scorer.py`) — score = forward return,
  equal-weighted, reads only `c.symbol` / `c.pattern`. Never reads `size_tier`, `portfolio`, or
  any action. (Verdict-neutrality invariant.)

Conclusion: `derisk_on_breakdown` is fundamentally about a **held** position; there is no
position-state feed. This is the task's **Option (b)**: deliver the additive per-candidate action
vocabulary, default `enter` (byte-identical), and state honestly what a real holdings-aware derisk
needs and where it would come from — do NOT invent a holdings subsystem.

## 3. Design (minimal, honest, additive)

### 3.1 The vocabulary — `alpha/sizing/action.py` (new, leaf)

```
RecommendationAction = Literal["enter", "trim", "exit"]
DEFAULT_ACTION: RecommendationAction = "enter"
def candidate_action(c) -> RecommendationAction:  # getattr(c, "action", DEFAULT_ACTION)
def derisk_tier(action, tier: SizeTier) -> SizeTier
```

`derisk_tier` is the **executable meaning** the doctrine's "reduce to core" needed:
- `enter` → `tier` unchanged (a normal new bet).
- `trim`  → cap at `core` (weight 0.5 = "降至核心仓位 = 原仓位的 1/2"); never raises a smaller tier.
- `exit`  → `flat` (weight 0.0 — fully out).

Home is `alpha/sizing` because `derisk_tier` maps into `SizeTier` (`alpha/sizing/position.py`).
`alpha/guard/screen.py` imports the two symbols it needs (`DEFAULT_ACTION`, `candidate_action`) —
one new guard→sizing edge to a pure leaf module (no cycle: `action.py` imports only
`position.py` + typing; sizing never imports guard).

### 3.2 Sizing honors the action — `size_decision` (`alpha/sizing/policy.py`)

Per candidate: `tier = derisk_tier(candidate_action(c), size_tier(c.confidence, rg))`. The
`Portfolio` exposure plan is built from **`enter` candidates only** — the exposure planner is a
new-bet planner (its docstring/semantics), and a trim/exit adds no new exposure. Trim/exit still
receive a per-name derisked `size_tier` for the human-confirmation surface.

### 3.3 Guard is action-aware — `screen_decision` (`alpha/guard/screen.py`)

The L4 **new-entry** veto applies to `enter` candidates only. A `trim`/`exit` (a derisk action on
a name we already hold, not a new chase) passes through unvetoed — "don't veto entering a name
you're reducing".

### 3.4 Byte-identical + verdict-neutral (the invariants)

- **Byte-identical today.** No `Candidate` carries `action`, so `candidate_action` → `"enter"`
  everywhere: `derisk_tier("enter", t) == t` (identical tiers + identical portfolio), the
  portfolio is built from all candidates (all are `enter`), and every candidate still runs through
  the veto exactly as before. Pinned by regression.
- **Verdict-neutral.** Scoring never reads `size_tier`/`portfolio`/`action`; annotations do not
  change the scored set. Pinned by a scorer regression (annotated vs plain decision → identical
  scores).

## 4. Files touched

- `alpha/sizing/action.py` — NEW (vocabulary + `derisk_tier` + `candidate_action`).
- `alpha/sizing/policy.py` — `size_decision` applies `derisk_tier`; portfolio from `enter` only.
- `alpha/guard/screen.py` — `screen_decision` veto applies to `enter` only.
- Tests: `tests/sizing/test_action.py`, `tests/sizing/test_policy.py` (append),
  `tests/guard/test_screen.py` (append).

Not in `tcb.lock` (`scripts/gen_tcb_lock.py::TCB_FILES` lists neither guard nor sizing) — no TCB
ritual. No new deps.

## 5. What stays deferred (the honest wire-for-later)

Making trim/exit *actually fire* needs, in order:
1. **A `Candidate.action` field** (shared model, `alpha/eval/decision.py`) — see §6; my seams
   (`candidate_action` = `getattr` default) are already forward-compatible.
2. **A position-state feed** — the real trigger reads a HELD leader's live size + its bars
   (vol ≥ 2× 20DMA AND close < 50DMA). Candidate sources: Alpaca `GET /v2/positions` (broker
   positions), or a persisted holdings ledger reconstructed from confirmed `DecisionPackage`s
   (`human_confirm == "confirm"`). Neither exists; this is a P4/P5-class feed, not P0.6.
3. **A breakdown detector** — a pure `derisk_on_breakdown(bars) -> bool` guard predicate (sibling
   of `halt_then_dump_proxy`) is computable from existing bars, but has no held-name to evaluate
   until (2). Left unbuilt (an unwired detector is dead code and edges toward the barred holdings
   subsystem).
4. **A verdict scoring fence** — see §6; once trim/exit candidates can exist, the loop/eval must
   NOT score them as new long entries.

## 6. Requests to the P0.5 owner (shared models / loop — not mine to edit)

1. **Add the field** to `Candidate` (`alpha/eval/decision.py`):
   ```python
   action: Literal["enter", "trim", "exit"] = "enter"   # P0.6: enter=new bet; trim/exit=derisk a held name
   ```
   Default `"enter"` keeps every existing construction byte-identical. Import the type from
   `alpha.sizing.action.RecommendationAction` if a shared alias is wanted (leaf module, no cycle).
2. **Verdict scoring fence (constraint, when trim/exit go live).** `InnerLoop.run` /
   `walk_forward` build `entries` from `decision.candidates` and score each as a forward-return
   long. A `trim`/`exit` candidate is NOT a new long and must be fenced out of scoring (mirror the
   P-B `for_asof(kind="trade")` fence). Today this is inert (no such candidates); flag it so the
   activation that adds the field also adds the fence.
