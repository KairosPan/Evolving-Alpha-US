# P2 — Growth market-clock classifier (GCycle's growth successor)

> Spec. 2026-07-13. Owner: KairosPan. Executes DEVELOPMENT-PLAN §1 P2 (as retargeted by its
> 2026-07-12 pivot note): GCycle's growth-pack successor reads the manuscript's three-state MARKET
> clock (§1.1 `market_three_states` + the cross-cut `panic_state` flag) instead of the momo six
> phases, wired pack-conditionally so momo stays byte-identical.

## 1. Goal & framing

The momo `GCycle` (`alpha/regime/classifier.py`) reads a single day's breadth into six phases whose
`follow_through_rate >= 0.4` frontside test is the A-share 连板 signature — structurally rare in the
US, so the production-posture verdict reads ~35/59 backside and the immutable `no_chase_risk_off`
veto suppresses ~all new longs (thin-by-construction). The 2026-07-12 pivot redirected the doctrine
to weeks-to-months sector-growth investing; its market read is the manuscript's **three-state clock**:

- `confirmed_uptrend` — a follow-through day has confirmed the uptrend; **new buys allowed** (attack).
- `under_pressure` — a distribution-day cluster; **禁新建仓** (no new entries), graded appetite.
- `correction` — deep breadth weakness; **禁新建仓、禁加仓, 现金是仓位** (risk-off floor).
- `panic_state` — a cross-cut FLAG (momentum-crash rebound), NOT a mutually-exclusive state.

Doctrine sources: manuscript §1.1 (`market_three_states`, `panic_state`), §4.3
(`market_state_actions.rule` — FTD confirms uptrend; 25-session distribution days ≥5 →
under_pressure/correction; per-state stop-tightening tiers), §4.8 tombstone (`no_chase_risk_off`'s
frontside wording retired, replaced by the three-state action semantics). Vocabulary: Option B
scale-typed tokens (`alpha/harness/growth_regime.py`) — `market:confirmed_uptrend` etc. There is **no
runtime momo→growth bridge** (user-ratified, `growth_regime.py` tail): the three-state read is built
NATIVELY from tape/breadth facts, never by translating momo phases.

## 2. Key decisions

### 2.1 The FTD / distribution-day proxy (honest limits)

`MarketState` carries **no index price and no index volume**. The breadth family
(`pct_above_200dma`, `net_new_highs`, `advances`/`declines`) is P0.4-optional and is **None on the
live decide path** (no caller threads a `BreadthReading` into `build_market_state`). So the only
always-present market-direction signal is the gainer/loser counts — exactly the primitive the panic
detector already uses. The classifier therefore reads the **index-direction proxy**

```
gainer_share(state) = gainer / (gainer + loser)     # 0.0 on a 0/0 empty tape (feed outage)
```

and maps the manuscript's two literary events onto it:

| Manuscript event | Literal definition | Our proxy (documented limit) |
|---|---|---|
| Follow-through day | index up ≥~1.5% on **higher volume**, day 4-7 of a rally attempt | a **strong-breadth up day**: `gainer_share ≥ FTD_SHARE`. No volume/no index price → "up on volume" is approximated by broad up-breadth; a broad-but-low-volume up day counts as an FTD. We do NOT require the O'Neil day-4 attempt count (too strict for weeks-cadence breadth and it would suppress the confirmation the doctrine wants); a strong up day out of a downgraded state confirms. |
| Distribution day | index down >0.2% on **higher volume** than the prior day | a **down-breadth day**: `gainer_share ≤ DD_SHARE` (losers meaningfully outnumber gainers). No volume → severity is proxied by breadth weakness, not volume. |

When the breadth family IS present (a future caller threads it), `advances`/`declines` refine the
DD test and `pct_above_200dma` the depth read — but the classifier never REQUIRES them (falls back to
gainer_share), so it works on today's live path unchanged. This is the same "honest proxy, stated not
assumed" posture as the panic detector; every threshold is a named constant 「文献值待verdict校准」.

### 2.2 The three-state machine (cross-day, pure function of history)

P1's lesson: a memoryless per-day detector flickers. So the state is computed by **replaying a
deterministic state machine forward over** `history + today` — a *pure function of `(history, today)`*
with **no hidden mutable state** (recomputable, same inputs → same answer), exactly like
`detect_panic_state`'s latch. No-signal (0/0) days are dropped from the window (a feed outage is not
evidence), mirroring the panic detector.

**Anchor at the last confirmation (O'Neil).** Distribution days and the deep-breadth mean are counted
**SINCE the most recent follow-through day** (`anchor`), NOT over a fixed trailing window. A fresh FTD
resets the count. This is load-bearing: counting DDs over a fixed trailing window carries *stale
pre-FTD DDs* into a freshly-confirmed state and un-confirms it the very next day — the ABAB day-parity
oscillation the first adversarial review caught (four identical `share=1.00` days that read
confirmed/under_pressure/confirmed/under_pressure). Anchoring makes the eight identical strong days
after a DD cluster all read confirmed.

Replay (start conservative at `under_pressure`; `dd_count` = distribution days in
`shares[anchor+1 : i]` capped at `DD_WINDOW`; `deep` = a **sustained recent** collapse — mean of the
last `DEEP_MIN_DAYS` days, clamped so it never reaches across the anchor and needs a full
`DEEP_MIN_DAYS` post-anchor days, so a single weak day cannot flip confirmed→correction):

```
anchor = -1
for each day d (index i, chronological) with share s:
  dd_count = # DDs in shares[max(anchor+1, i-DD_WINDOW+1) : i+1]
  deep     = a full DEEP_MIN_DAYS post-anchor days averaging <= DEEP_SHARE
  if state == confirmed_uptrend:
     if dd_count >= DD_CORRECTION or deep:      state = correction        # deep/sustained breakdown
     elif dd_count >= DD_UNDER_PRESSURE:        state = under_pressure    # DD cluster downgrade
     # else STAY confirmed_uptrend  (hysteresis: isolated weakness does not un-confirm)
  else:  # under_pressure / correction
     if s >= FTD_SHARE:            state = confirmed_uptrend; anchor = i   # FTD confirms AND resets the DD count
     elif dd_count >= DD_CORRECTION or deep:     state = correction
     elif state == correction and s >= UP_DAY_SHARE and dd_count < DD_UNDER_PRESSURE:
                                                 state = under_pressure    # heal correction→pressure
final state after `today` is the read.
```

**Hysteresis is deliberate and cross-day:** once `confirmed_uptrend`, the state persists through
isolated down days until a *cluster* (`≥ DD_UNDER_PRESSURE` DDs SINCE the anchor) accrues — it does not
re-derive per day. Once downgraded, a single follow-through day re-confirms and re-anchors. This is a
genuine state machine replayed over history, not per-day banding.

**Warm-up:** fewer than `MIN_HISTORY` non-empty prior days → the backdrop cannot be assessed →
return `under_pressure` (conservative, NOT frontside), regardless of today. **Empty (0/0) today also
abstains** — a feed-outage day is no evidence, so the state is carried forward from the prior read
(today is NOT baked in as a synthetic share-0.0 max-bearish distribution day, which would diverge from
the panic detector and let a datum a later day treats as never-existing move the read). Warm-up is also
load-bearing for the P1 battery: the blowoff/backside trap days carry empty history → not-frontside →
the guard still drops them.

### 2.3 Frontside / risk_gate mapping (zero guard changes)

The immutable veto (`alpha/guard/veto.py`) keys only on `RegimeRead.risk_gate < RISK_OFF_THRESHOLD`
(0.2) OR `not RegimeRead.frontside`. The three states express the manuscript action semantics
THROUGH that existing surface — **no guard edit needed**:

| State | `frontside` | `risk_gate` | Which existing veto branch fires | Manuscript §4.3 |
|---|---|---|---|---|
| `confirmed_uptrend` | **True** | `UPTREND_GATE` (0.60) | none — new buys allowed | 可新建仓、可加仓 |
| `under_pressure` | **False** | `PRESSURE_GATE` (0.35) | `not frontside` → "backside regime …: no new entries" | 禁新建仓, 加仓减半 |
| `correction` | **False** | `CORRECTION_GATE` (0.15) | `risk_gate < 0.2` → "risk-off … no chasing" | 禁新建仓、禁加仓, 现金是仓位 |

`RegimeRead.phase` carries the growth token (`"market:confirmed_uptrend"` …), so the veto reason
strings render descriptively. The per-state **stop-tightening tiers** (7-8 / 5-6 / 3-4%) and 加仓减半
act on HELD positions, which the guard does not model (no holdings) — they ride the graded `risk_gate`
into sizing (verdict-neutral) and are otherwise carried forward for a future holdings/trim producer
(the same fence P0.6 pinned). No new `RegimeRead` fields; momo `GCycle` is byte-identical.

### 2.4 Panic flag — home & one implementation (spine preserved, NO relocation)

`detect_panic_state` (P1) is the ONE momentum-crash detector. It stays in `alpha/guard/panic.py`
(**not relocated**). The growth clock does **not** import it — instead the guard orchestrates the
single call: `screen_decision` computes `panic = detect_panic_state(history, state)` (byte-identical
to P1 for momo) and passes it to `CandidateContext.panic_state` (the authoritative, frontside-
independent block) for BOTH vocabularies. The three-state read and the panic flag are **orthogonal**
— matching the manuscript's "cross-cut flag" framing: a sharp rebound out of a bear reads
`confirmed_uptrend` (a strong up day = FTD) yet is blocked by the panic veto (exactly the trap
`panic_state` targets). So `GrowthMarketClock` imports only `alpha.state.market` +
`alpha.regime.classifier.RegimeRead` — a pure leaf, upstream of `guard/` — and the spine
`state < regime < guard` is untouched: **no back-edge, no re-export shim, no duplicated logic**. (The
alternative — relocating the detector to `alpha/regime/panic.py` + a guard re-export shim — was
considered and rejected as unnecessary churn once dependency injection removes the import entirely.)

### 2.5 Pack-conditional selection (vocabulary rides with the harness)

`screen_decision`/`GuardedPolicy` gain a `vocabulary` param, read from the **H being run**
(`h.vocabulary`), never the process env — the P0.5 "pack rides with the harness" invariant. `"growth"`
→ `GrowthMarketClock().read(history, state)`; anything else → `GCycle().read(state)` (unchanged). The
`SizingPolicy` fallback stays `decision.regime or GCycle().read(state)`; because the guard populates
`decision.regime` before sizing on every guarded run, sizing reads the growth read for free (the
momo-`GCycle` fallback only bites the screen-off unguarded baseline, where sizing is verdict-neutral
display-only — accepted).

### 2.6 Symmetric history threading (activates the P1 panic veto)

P1 built the panic veto DORMANT (no driver threads `state_history`). P2 activates it by giving each
policy a **growing trailing window** of the daily `MarketState`s it has decided on, accumulated
**inside `GuardedPolicy`** (opt-in `track_history=True`): `decide` reads `self._history` (strictly
prior) then appends `state`. Each arm owns its own accumulator, so HCH and Hexpert — fed the same
source/window — build identical histories: **symmetric by construction** (the screen-flag / recall
pattern; HCH gets nothing Hexpert doesn't). `InnerLoop` passes its own persistent list by reference
so history **survives a breaker rollback** (a rollback rebuilds the policy but not the forward-only
regime context — the existing inner_loop invariant). `walk_forward` needs no change: the wrapped
`GuardedPolicy` (constructed in `compare._wrap` with `track_history=True`) accumulates internally as
`walk()` drives it. The legacy P1 path (`track_history=False`, fixed `state_history` context, default
`None`) is preserved byte-for-byte.

### 2.7 Market-breadth input is screen-independent

The clock (and the panic detector) read `MarketState.gainer_count`/`loser_count`. Those are built from
the CANDIDATE universe, which — under the growth pack's own intended `trend_template` screen — carries
NO gainer/loser counts (every name is status `trend_template`), so the clock + panic would **silently
starve** (permanent warm-up/under_pressure, dead panic veto). `alpha/universe/universe.py::tape_breadth`
counts the market-wide ±10% tape from the full daily snapshot, independent of the candidate screen;
`build_market_state(market_counts=...)` feeds it into the two market-breadth fields. Under the gainer
screen `tape_breadth == counts(universe)` exactly (byte-identical — mirrors `build_universe`'s
gainer/gap_up/loser order), so momo is untouched; under any other screen the clock reads the real tape.
The three growth-relevant drivers (`InnerLoop`, `walk_forward`, `save_decisions`) thread it. (The
momo-oriented `MarketState` features — sentiment/echelon/follow-through — stay candidate-scoped; the
GCycle that reads them only runs under the gainer screen, where the two coincide.)

## 3. Files

New:
- `alpha/regime/growth_clock.py` — `GrowthMarketClock` + thresholds + `gainer_share`/`market_share` helpers.
  `market_share` prefers the full-cross-section `advances`/`declines` when present, else `gainer_share`
  (live path); so a caller that threads the breadth family gets a richer market-trend read, byte-identical
  otherwise.
- `scripts/calibrate_growth_clock.py` — the reproducible acceptance-evidence producer (offline, keyless):
  replays the clock over a captured PIT window, prints the state/frontside/panic distribution + stability
  diagnostics (state-changes / single-day islands / ABAB points); `--breadth` threads full advance/decline.
  Library `calibrate()` + `main()` (scan_tradeable / run_verdict convention).
- `tests/regime/test_growth_clock.py` — three-state truth table, hysteresis, **confirmation-anchor / no-ABAB
  regressions, empty-today abstain**, warm-up, boundary probes, a/d preference.
- `tests/guard/test_growth_market_clock_wiring.py` — pack-conditional guard wiring + momo byte-identity.
- `tests/loop/test_p2_history_symmetry.py` — verdict-symmetry regression (both arms same history/panic).
- `tests/state/test_market_breadth_decoupling.py` — the clock/panic breadth is screen-independent (`tape_breadth`).
- `tests/scripts/test_calibrate_growth_clock.py` — pins the producer against a synthetic FakeSource tape.

Changed (all NON-TCB — verified against `scripts/gen_tcb_lock.py::TCB_FILES`):
- `alpha/regime/classifier.py` — **docstring drift fix only** (GCycle claims Refiner-editable thresholds that no edit path touches — kairos-mining §4.5); no logic change.
- `alpha/guard/screen.py` — `screen_decision`/`GuardedPolicy` gain `vocabulary` + `track_history`; growth read branch.
- `alpha/universe/universe.py` — `tape_breadth` helper (full-tape ±10% market breadth, screen-independent).
- `alpha/state/builder.py` — `build_market_state` gains `market_counts` (decouples the clock/panic breadth from the candidate screen; default None = byte-identical).
- `alpha/loop/inner_loop.py` — persistent `market_history` + `market_counts=tape_breadth(snap)`, threaded with vocabulary into `_rebind`'s GuardedPolicy.
- `alpha/loop/compare.py` — `_wrap` sets `vocabulary` (from the seed H) + `track_history=True` on every arm.
- `alpha/eval/walk_forward.py` — threads `market_counts=tape_breadth(snap)` into `build_market_state`.
- `scripts/save_decisions.py` — the live producer now threads `vocabulary=h.vocabulary` + `track_history=True` + `market_counts` (was screened by momo GCycle with the panic veto dead — review finding #3).
- `alpha_web/templates/_macros.html`, `dashboard.html` — `phase_pill`/`phase_ring`/tagline lookups degrade for a non-canonical `market:<state>` phase (never 500).

## 4. Acceptance

- Full offline suite green (keyless), incl. the **P1 trap-day battery** (`tests/guard/test_trap_day_battery.py`) and panic unit file — unchanged, still green.
- Momo path byte-identical: a momo H run selects `GCycle` and its regime reads are unchanged; growth read is invoked only when `h.vocabulary == "growth"` (pinned).
- `lint_doctrine` 0, `gen_tcb_lock --check` 0.
- Calibration (DONE, reproducible via `python scripts/calibrate_growth_clock.py verdict_pit_broad`, offline
  replay over the captured window, 90 days 2025-11-17..2026-03-27, production `gainer_share` proxy —
  regenerated on the **anchor-fixed** machine): **confirmed_uptrend 75 (83.3%) / under_pressure 10 (11.1%) /
  correction 5 (5.6%); frontside 83.3%; panic flag 18.9%**. NOT thin-by-construction (the opposite — a
  broadly-up window). **Stability (the anchor fix): state_changes 49→10, single-day islands 35→3, ABAB
  points 21→2** — the day-parity oscillation is gone. `--breadth` (full a/d): confirmed 77 (85.6%) /
  under_pressure 9 (10.0%) / correction 4 (4.4%); stability 12 / 5 / 4. Runs in <1s. (The pre-fix 41.1 /
  27.8 / 31.1 "balance" was an artifact of the oscillation — spurious under_pressure days — not a real
  read.) The high confirmed rate is the §5 dead-band limit and is 待verdict校准.

## 5. Out of scope / carried forward

- **H-params metatool / Refiner calibration of the thresholds** — the plan's conditional sub-item;
  deferred (fix the GCycle docstring instead, per the plan). Thresholds are fixed named constants.
- **Populating the breadth family live** (`pct_above_200dma` etc. into `build_market_state`) — the
  classifier consumes them when present but the heavy cross-sectional per-day computation is left to
  P5 (theme/sector breadth feed); today it reads gainer_share.
- **Per-narrative-line / theme + stock clocks** — P2 is the MARKET clock only; theme/stock reads need
  the theme-breadth feed (P5) and narrative clustering.
- **Growth `phase_from_read` → skill phase-ordering** — the agent's growth market token is not yet
  extracted by `phase_from_read` (momo-only aliases); growth skills still surface (unordered by market
  phase). Left as a P0.5 follow-up (touches TCB `retrieval.py` matching); reported, not built here.
- **`alpha_web` growth console instrument** — the console's six-phase ring/pill are momo-shaped. P2 is
  the first to put a non-canonical `market:<state>` phase into a persistable `DecisionPackage.regime`,
  which `phase_pill`/`phase_ring`/the `/deck` tagline looked up unguarded (a `/decisions` 500 for a growth
  package — adversarial-review finding). Fixed defensively HERE: the lookups degrade gracefully (render
  the raw token / empty, never 500), with `/decisions` + `/deck` growth regressions. A proper three-state
  growth instrument (ring/legend) is its own design, deferred.

### Known limits (待verdict校准 — thresholds are literature values pending verdict calibration)

| Limit | What / why | Candidate fix (deferred) |
|---|---|---|
| **0.41–0.59 dead band** | A day with share in `(DD_SHARE, FTD_SHARE)` is neither a distribution day nor a follow-through day, so a slow net-declining grind (e.g. share 0.45 = 55% of movers down every day) never accrues DDs and a confirmed uptrend **stays confirmed forever**. Inherent to the FTD/DD rule pair; it is the main driver of the high confirmed rate (window mean share 0.58 sits in the band). The deep-mean leg only catches a *sustained deep* collapse (mean ≤ `DEEP_SHARE` 0.30), so the 0.30–0.50 mild-decline band still holds confirmed after the anchor fix. | A mean-since-confirmation floor (downgrade when the post-anchor mean sits below `UP_DAY_SHARE` for a sustained run), or raising `DD_SHARE` — both change the frontside base rate, so they are verdict-calibration decisions, not free choices. |
| **Non-gainer-screen features** | Under `trend_template`, only the market-breadth fields (gainer/loser) are decoupled (§2.7); sentiment/echelon/follow-through remain candidate-scoped (unused by the growth clock, and the momo GCycle that reads them never runs under that screen). | Full market-tape perception, if a non-clock consumer ever needs those features under a non-gainer screen. |
