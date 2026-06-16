# Evolving-Alpha-US — Architecture Blueprint

> **Version:** 1.0 · **Date:** 2026-06-13
> **Scope:** US-first greenfield rebuild of the self-evolving speculative-momentum co-pilot.
> **Status:** Authoritative US architecture reference (knowledge survives `reference/cn/` deletion).
> **Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md`

---

## 0. TL;DR

Port the *Continual Harness* `H=(p,G,K,M)` two-loop self-evolving agent (paper 2605.09998, Princeton/ARISE/DeepMind) from A-share 游资/超短 trading to **US speculative-momentum trading**. The engine self-improves via two nested loops:

- **Inner loop (daily close, reset-free):** Refiner reads the most recent trajectory, identifies failure signatures, and edits `H` via meta-tool CRUD (four passes: `p`, `G`, `K`, `M`).
- **Outer loop (cross-period, US-2+):** local policy `π_θ` runs replay rollouts → process-reward scoring → low-reward windows relabeled via frontier teacher + realized-future oracle → soft-SFT / LoRA update (θ reset-free). The outer loop is **deferred to US-2+**; what US-2 validates is the inner loop only.

The system is a **decision-support co-pilot**. It produces a `DecisionPackage` (ranked candidates + plans + rationale + per-candidate size tier + portfolio risk budget + fill-feasibility). A human confirms. **No automatic live orders.**

This is a **greenfield rebuild** — clean US-native data model, all-English code and docs. "Ported from CN" means reimplemented cleanly with tests, using `reference/cn/` as algorithmic reference only, never a literal copy.

---

## 1. Why Continual Harness

Three reasons the Continual Harness is the right architecture for US speculative momentum trading:

### 1.1 Alpha decay / non-stationarity

Any playbook, once widely copied, loses its premium and can reverse (alpha decay). The CN system's
name "轮回" (reincarnation) captures this: old leaders die, new narratives emerge, the cycle
repeats. **The only sustainable edge is a system that edits its own playbook** — precisely the
Continual Harness thesis.

US equities share this property. Momentum factors have documented 3–5-year half-lives; gap-and-go
patterns get arbed as they gain attention; meme/squeeze mechanics evolve as market participants
adapt. A frozen harness is a harness that is decaying.

### 1.2 Reset-free in-episode compounding

The Continual Harness accumulates failure signatures within an episode without resetting. In trading
terms: a full momentum cycle (Washout → Recovery → Heating → Trend → Distribution → Exhaustion)
is one reset-free episode. Failure patterns from the Trend phase compound into better Refiner edits
for the next Distribution/Exhaustion phase — the hardest parts of a cycle to trade. No mid-episode
reset means no loss of this in-episode credit.

### 1.3 Reflexivity

The US tape is adversarial and reflexive. When a setup is widely known, front-running changes the
setup's distribution. Static model weights decay; static harness rules decay. The meta-tool CRUD
loop is the only mechanism that can adapt the scaffolding itself faster than the environment
degrades each individual skill.

**The tension vs the paper:** the paper assumes a stationary environment with a perfect oracle
(Dijkstra). US trading has a near-perfect oracle (realized future returns) but the environment is
non-stationary and adversarial. The blueprint adds six non-stationarity gates on top of the
paper's two loops: regime labels, decay-weighted stats, dormant-skill revival, alpha-decay monitor
(`eval/alpha_decay.py`), capability-floor fallback, and OOS/shadow/PIT lookahead firewall.

---

## 2. Positioning and Non-Goals

- **Co-pilot, human-confirmed.** Output is a `DecisionPackage` (§4.1). The human confirms,
  rejects, or modifies — this doubles as DAgger expert labeling for the future outer loop.
  **No automatic live orders.**
- **Two-loop, but staged.** The outer loop (LoRA / θ training) is deferred to US-2+. US-2's
  acceptance validates the inner loop only (harness self-refinement); passing US-2 demonstrates
  "self-editing harness ≥ frozen-expert harness on OOS", not that the full two-loop system
  converges.
- **Non-goals (now):** intraday execution, real brokerage order routing, options/derivatives
  pricing, social-sentiment ingestion (US-3 enrichment), the outer-loop LoRA training (US-2+),
  multi-market abstraction (CN is reference-only).
- **In scope (not deferred):** the sizing/portfolio (§4 L3) and risk-guard/veto (§4 L4) layers —
  these are survival-critical and ship in US-1.

---

## 3. Concept Mapping: A-Share 游资 → US Speculative Momentum

The structural key: **US has no daily price limits.** It has LULD volatility pauses, SSR (a
short-sale price test, *not* a halt), and market-wide circuit breakers. Each maps to a different
A-share concept; the mechanics differ materially.

### 3.1 High-Fidelity Port — Corrected Mechanics

| A-share concept | US analog (precise) | Daily-cadence proxy (US-0/US-1) |
|---|---|---|
| 涨停 limit-up | **LULD halt-up** = transient 5-min volatility pause (price outside band ≥15s; Tier-1 S&P/Russell-1000 vs Tier-2 bands; reopens via auction; **not** a day-lock — runner can keep going, repeated pauses) + extreme % gainer | top % gainer / large up-close |
| 跌停 limit-down | **LULD halt-down** (same mechanics, downside) + extreme loser | large down-close |
| (no A-share analog) | **SSR (Reg SHO Rule 201)** = short-sale price test, triggers at −10% intraday vs prior close, restricts shorting to above-NBB for rest of day + next session; does **not** halt or limit price | SSR-flag = prior-day close-to-close ≤ −10% (daily proxy of the intraday Rule 201 trigger); for this long-only co-pilot, read as a no-chase veto on a one-sided/exhaustion tape (`dont_fight_ssr`), not short-side logic (wired US-3b) |
| 连板 N consecutive boards | **multi-day runner** (repeated halt-ups / consecutive large up-days) | N consecutive up-days with size |
| 炸板 failed board | **failed breakout / first red day / gap-up→red-close** | gap-up→red-close, fade-from-high |
| 一字板 gap-locked (unbuyable) | **true fill-infeasibility** = LULD-locked with no offer / sub-penny-size micro-float with displayed size ≪ intended order. NOT an ordinary gap-up (US gap-ups fill at the higher open). | size-at-offer vs intended order (intraday); daily proxy = extreme gap + near-zero liquidity |
| 封单 seal-order size | resting size at offer / halt-resumption auction imbalance | (intraday enrichment, US-3) |
| 弱转强 weak-to-strong | **distinct setups**: gap-and-go (opens above prior close, no gap-fill) vs VWAP-reclaim (opens weak, recovers above VWAP) vs ORB (breaks first-N-min range) — modeled as separate skills | gap-up holding vs prior close (daily proxy of gap-and-go) |
| 龙头 dragon-head | lead runner / relative-strength leader | strongest ticker in a theme |
| 接力 relay | continuation chase on day N+1 | buy yesterday's leader's follow-through |
| 题材 / 概念 | sectors + narratives (AI, quantum, nuclear, biotech, crypto-adj, defense) | catalyst/theme tag |
| 题材轮动 / sympathy | narrative rotation / sympathy plays | co-movement with leader |
| 情绪值 / 情绪周期 | risk-on momentum regime (gainer breadth, # halts, follow-through, failed-breakout rate) | daily breadth scalars |
| 赚钱/亏钱效应 | risk-on / risk-off effect (do yesterday's runners follow through or get sold) | next-day runner survival rate |
| 预期差 / 预期链 | catalyst surprise (earnings vs whisper/consensus, FDA, guidance, contract) | event tag + gap reaction |
| 核按钮 dump | parabolic blowoff / max-pain flush | large reversal day |
| 880005 / 大盘结构 + 熔断 | **index & breadth** (SPY/QQQ/IWM trend, % above MA, A/D, new-highs/lows) + **MWCB** (S&P −7%/−13%/−20% market-wide halts) | daily index/breadth; MWCB as a risk-gate event |
| 容量行情 | liquidity/volume regime (small-cap & IWM turnover) | daily volume regime |
| T+1 same-day-sell ban | US has **no** same-day-sell ban (day-trading allowed). Two distinct US facts: settlement is T+1 (since 2024-05-28) and the PDT rule (<$25k margin → ≤3 day-trades/5d). **The real port is an eval rule**: enforce **horizon ≥ 2** (no same-day open-buy/close-sell) in the backtest to avoid inflated round-trips. | horizon ≥ 2 enforced in scorer |
| 幸存者偏差 / PIT | survivorship/PIT (delistings, ticker changes, reverse splits, halts). **Delisting is a terminal LOSS to be scored, not a data gap to drop.** | PIT snapshots + delist→terminal-loss oracle |

### 3.2 Weak / No Direct Analog (Enrichment, Not Core)

- **龙虎榜** (Dragon-Tiger top-trader disclosure) has no single daily US equivalent. The
  substitutes: **FINRA daily short-sale-volume files** (next-morning, free, per-symbol short/total
  ratio) and the **Reg SHO daily threshold-securities list** are genuinely daily; short interest
  (bi-monthly, lagged), 13F (quarterly), Form 4 (≤2 business days) are slower. The daily FINRA
  short-volume + Reg SHO list are a **meme/squeeze** enrichment (US-3).
- **短线 intraday:** halt-resumption auction, VWAP-reclaim exact mechanics, ORB, real-time SSR
  flag — all US-3 intraday enrichments. Daily proxies ship in US-0/US-1.

---

## 4. Layered Architecture and Data Flow

```
alpha/
  data/         # L0 — sources + PIT + lookahead firewall
    source.py            # MarketDataSource protocol (+ GuardedSource wrapper)
    alpaca.py            # AlpacaSource: daily bars (raw/unadjusted) + corp-actions
    calendar.py          # US market calendar (NYSE/Nasdaq)
    firewall.py          # AsOfGuard / LookaheadError
    pit_store.py         # PIT snapshot store (parquet, atomic); stores RAW prices (PIT). A separate
                         #   PIT adjustment-factor table is deferred to US-1 (raw-only satisfies the
                         #   split-vintage firewall; adjusted levels are recomputed when needed)
    snapshot_source.py   # offline PIT source (SnapshotSource)
    capture.py           # window prefetch → store (PIT-correct, idempotent)
    corp_actions.py      # splits / reverse-splits / delistings / dilution-filings (ATM/shelf/offering) — PIT by announcement date
  state/
    market.py            # MarketState, RunnerRung (连板梯队 analog), as-of timestamp
    decision.py          # DecisionPackage schema (frozen; the action a_t + DAgger record)
    builder.py           # build_market_state from daily universe
  features/     # L0→L1 — US momentum features (regime-relative; TRAILING-only windows)
    breadth.py runner.py failed_breakout.py relative_strength.py builder.py
  regime/       # G_cycle — read-only sub-agent of H.G (SSOT: never writes phase back into H)
    cycle.py classifier.py
  universe/     # candidate universe (gainers/gap-ups/high-RVOL/runners), PIT, EXOGENOUS oracle screen
    stock.py universe.py
  harness/      # H=(p,G,K,M) — containers, 9 meta-tools, persistence, immutable-core guard,
                #   snapshot/rollback, registry, store, regime_label, edit_log
  agent/        # L2 decision: master-dispatch orchestrator + named G sub-agents
    agent.py prompt.py parse.py retrieval.py
    subagents.py         # leader/relay, theme-miner, expectation-gap dispatch (G members)
  sizing/       # L3 — sizing / portfolio / correlation (survival-critical)
    position.py          # confidence→size-tier (flat/probe/core/heavy) + risk budget
    correlation.py       # same-narrative/sympathy = ONE correlated bet; exposure netting
    portfolio.py         # total exposure vs global risk-gate/size-multiplier; batching/scale-in
  guard/        # L4 — hard-veto layer (overrides Agent suggestions)
    stops.py             # form/regime/time stop-loss with veto power
    veto.py              # dilution/offering/ATM-shelf, halt-then-dump, going-concern, regulatory veto
    breaker.py           # single-name/single-day/consecutive-loss circuit breaker; MWCB awareness
  refine/       # inner-loop Refiner: refiner, refiner_prompt, credit, signatures, ops, retire-discipline
  eval/         # walk_forward, trajectory, oracle, return_oracle, scorer, metrics, baselines,
                #   decision-eval, fill (inference-path fill-feasibility), alpha_decay
  loop/         # inner_loop (scorer-aware floor breaker), compare (HCH/Hexpert/Hmin), run_store
  llm/          # client (protocol + MockLLMClient), anthropic.py, openai_compat.py, config.py,
                #   cache, extract
  config.py
alpha_web/      # FastAPI + HTMX cockpit (research + decision), domain-isolated, single-way dependency
seeds/          # four US playbook families, family-tagged: runner / swing / event / meme
docs/           # FIRST-CLASS English docs: blueprint.md, PROJECT_STATE.md, ROADMAP.md, specs/, plans/
scripts/        # capture_window, smoke_alpaca, smoke_agent, serve_web, sample_run
tests/          # mirror modules, offline (MockLLM + FakeSource); firewall/immutable-core regressions
reference/cn/   # copied CN system — reference during rebuild, DELETED when done
```

**Decision pipeline (execution order):**
```
data → features → regime (G_cycle) → universe →
agent (master-dispatch + G sub-agents) → sizing (L3) → guard (L4 veto) →
DecisionPackage → human confirmation
```

Self-evolution machinery (`harness/`, `refine/`, `loop/`, `eval/`) wraps this pipeline.

### 4.1 `DecisionPackage` Schema (the action `a_t`)

Frozen (`state/decision.py`). The human-confirmation surface and DAgger label record.

```jsonc
{
  "date": "...", "as_of": "...",
  "regime_read": {
    "global_risk_gate": 0.4,
    "lines": [{"narrative":"AI","phase":"Trend","frontside":true,"confidence":0.7}]
  },
  "ranked_candidates": [
    {
      "ticker":"...", "name":"...", "family":"runner|swing|event|meme",
      "pattern":"gap-and-go", "skill_id":"...",
      "entry":"...", "exit_stop":"...",
      "size_tier":"flat|probe|core|heavy",              // from sizing/ (L3)
      "fill_feasibility": {"buyable":true,"reason":"..."}, // from eval/fill on inference path
      "taboo_check":[{"rule":"no-chase-in-risk-off","status":"pass"}], // from guard/ (L4)
      "reason":"K skill + M analog", "confidence":0.62,
      "counterview":"if AI line flips to backside, drop"
    }
  ],
  "no_trade_reason": "...",
  "key_risks": ["..."],
  "portfolio": {
    "total_exposure_budget": 0.5,
    "correlated_groups": [["AAA","BBB"]]
  },
  "human_confirm": null  // confirm | reject | modify(+reason)
}
```

**Named `G` sub-agents** (dispatched by `agent/`): `G_cycle` (regime classifier — **read-only**,
SSOT), leader/relay identifier, theme/narrative miner, expectation-gap evaluator, `G_risk`
(stops/veto — in `guard/`), regulatory/halt veto (in `guard/`), fill-feasibility evaluator
(in `eval/fill` + inference path). The Refiner owns the review/reflection function.

---

## 5. Two-Loop Diagram

```
╔══════════════════════════════════════════════════════════════════════╗
║                        OUTER LOOP  (US-2+)                          ║
║   θ  ──► replay rollout ──► PRM score ──► oracle relabel ──► LoRA   ║
║                                                                      ║
║  ┌───────────────────────────────────────────────────────────────┐   ║
║  │                    INNER LOOP  (daily close)                  │   ║
║  │                                                               │   ║
║  │  market close ──► Refiner reads trajectory                    │   ║
║  │        │                                                       │   ║
║  │        ▼                                                       │   ║
║  │  identify failure signatures (credit, signatures, ops)        │   ║
║  │        │                                                       │   ║
║  │        ▼                                                       │   ║
║  │  CRUD pass 1: p  (doctrine update)                            │   ║
║  │  CRUD pass 2: G  (sub-agent roster / prompt edit)             │   ║
║  │  CRUD pass 3: K  (skill library: create/update/retire)        │   ║
║  │  CRUD pass 4: M  (replay memory: annotate/tag/surface)        │   ║
║  │        │                                                       │   ║
║  │        ▼                                                       │   ║
║  │  updated H ──► next day's decision pipeline                   │   ║
║  │                                                               │   ║
║  └───────────────────────────────────────────────────────────────┘   ║
╚══════════════════════════════════════════════════════════════════════╝
```

**Key properties:**
- **Reset-free:** the inner loop never resets H mid-episode. A full momentum cycle is one episode.
- **SSOT:** `G_cycle` (regime) is read-only; phase lives on `s_t`, never written back into `H`.
- **Immutable-core guard:** the Refiner cannot edit the core doctrine lines that define the
  hard-veto rules, the firewall, the immutable-core itself, or the scoring oracle interface.
- **Capability-floor breaker:** if the inner loop degrades HCH below a scorer-aware floor
  (daily advantage = score − same-day baseline < floor), the loop freezes and emits an alert.

---

## 6. US Momentum Regime Machine

Two-level, like CN: **global mother-state** × **per-narrative lines**. The "轮回/reincarnation"
insight ports directly and drives **dormant-skill revival**.

**Three US refinements vs CN:**
1. **Global mother-state = risk-gate + size multiplier** (consumed by `sizing/portfolio.py`), not
   the primary regime signal. **Per-line phase drives playbook/family selection.**
2. **Frontside / backside is a per-line attribute** (scalar), not a 7th global state.
3. **Follow-through day is a transition event**, not a dwelt-in state.

| US State | CN Analog | Observable Daily Criteria | Transition → |
|---|---|---|---|
| **Washout / Freeze** | 混沌/冰点 | few gainers, runners failing, IWM down, new-lows high, no follow-through | gappers hold + leader emerges → Recovery |
| **Recovery / First-Green** | 修复启动 | first clean gap-and-go survivors, a day-2 continuation, breadth ticking up | narrative gets multiple movers → Heating |
| **Heating / Ignition** | 情绪回暖/题材启动 | narrative ignites (many tickers up big same day), index FTD, RVOL spikes | lead runner + sympathy basket → Trend |
| **Trend / Momentum** | 主升 | leader new highs daily, sympathy runs, gap-and-go's work, low failed-breakout rate | first big distribution day + no next-day recovery → Distribution |
| **Distribution / Churn** | 震荡/补涨 | choppy, laggards run while leaders churn, failed-breakout rate climbing, risk-off spreading | leader breaks down on volume / blowoff → Exhaustion |
| **Exhaustion / Flush** | 退潮 | leaders + sympathy co-flush, hot ticker dumped, MWCB risk | breadth collapses, old leaders stop falling + new narrative stirs → Washout/Reset |

Output: continuous confidence per narrative line + global risk-gate scalar + per-line
frontside/backside flag. Criteria are objective and oracle-auditable; they are calibratable
judgments, not frozen formulas.

---

## 7. Four Playbook Families

All family-tagged inside one `H`. **Design bias: defense seeds (failure-detectors + taboos) richer
than offense seeds** — guardrails clear the capability floor faster. But an explicit
**alpha-production channel** is maintained: offense skills can be created and promoted via the
incubation tournament. Eval reports the **offense-vs-defense contribution split** so US-2 can
distinguish self-evolution that adds edge from self-evolution that only trims risk.

**Per-phase functional scope:**

| Family | US-1 (daily data only) | Full offense unlocked |
|---|---|---|
| **Swing** (mid/large) | **Fully functional** — base breakout, pullback-to-MA, RS-leader continuation, sector rotation, earnings-gap continuation; failures: failed breakout, distribution cluster, leader breakdown | US-1 |
| **Runner** (low-float) | Defense seeds + **daily proxies** (multi-day up-days, gap%, daily RVOL, gap-up-hold); failures: parabolic blowoff, first red day, dilution/ATM, reverse-split pump, **halt-then-dump (US-3e daily proxy)** | Halt-resumption / VWAP-reclaim / ORB / halt count / MWCB → **US-3 intraday-feed deferred** |
| **Event/catalyst** | Defense seeds + **news-tag proxy** (Alpaca news); failures: fade-on-event, gap-fill | Earnings-calendar proximity, surprise% vs whisper → **US-3** |
| **Meme/squeeze** | Defense seeds + **both squeeze offenses activated** (US-3c `short_squeeze` via `short_interest`/`days_to_cover`; US-3f `gamma_squeeze` via `options_flow`) — `depends_on`-gated, surfaced when data is live; both stay incubating pending evidence; `social_sentiment` rendered (US-3f) | real options-flow / social / borrow feeds + per-narrative-line phase tagging → deferred |

**Shared immutable-core doctrine** (Refiner can never edit):
- Respect the regime (no chasing in risk-off).
- Same-narrative / sympathy = ONE correlated bet (enforced by `sizing/correlation.py`).
- Stop discipline and fill-feasibility must be checked.
- Survivorship/PIT awareness (no looking past the as-of cursor).
- Position and loss circuit-breakers.
- "Don't fight SSR" is an **active** immutable doctrine line, wired in US-3b via `ssr_active` +
  `screen_decision` (opt-in `LoopConfig.screen`; global default-on gated on the richer `features/builder`
  landing so the regime arm reads frontside).

Seeds bootstrapped from this design + established US momentum knowledge.

---

## 8. Data, Universe, and the Four Firewall Surfaces

### 8.1 Data Layer

**AlpacaSource** implements `MarketDataSource` (protocol in `alpha/data/source.py`):
- `trading_calendar() -> list[Date]` — NYSE/Nasdaq schedule via `/v2/calendar`.
- `daily_bars(symbol, start, end) -> DataFrame[date,open,high,low,close,volume]` — **RAW/unadjusted**.
- `daily_snapshot(day) -> DataFrame[symbol,name,open,high,low,close,volume,prev_close,short_interest?,days_to_cover?,free_float?]`
  — built by `capture_window` from raw bars + prior close; the optional `short_interest`/`days_to_cover`
  enrichment columns (US-3c) ride here when supplied (real FINRA join deferred). AlpacaSource.daily_snapshot
  raises NotImplementedError (no "top gainers" API endpoint).
- `corporate_actions(start, end) -> DataFrame[symbol,announce_date,ex_date,kind,ratio]`.

No "top gainers" endpoint exists → universe is built by scanning daily snapshots and ranking. PIT:
`capture_window` → `PITStore` (parquet, atomic) → `SnapshotSource` (offline) → `GuardedSource`
(firewall wrapper).

**Free-tier caveat:** Alpaca's free tier uses the IEX feed — adequate for OHLCV history (to ~2016)
but thin for full-market gainer screening. Universe completeness is the real free-tier limit, not
history depth.

### 8.2 Split / Adjustment Vintage (Firewall Surface 3)

Stored bars are **RAW/unadjusted**. `PITStore` gives PIT pool membership and raw prices. A stored
single-vintage adjusted slice is **not** point-in-time for level features.

- Price-level/float-sensitive features (price thresholds, RVOL denominators, penny/low-float
  screens) **must** compute from raw point-in-time prices.
- Forward-return ratios are split-invariant within a contiguous slice — return labels are fine
  without split-rebasing within a slice.
- Reverse-split / delisting (PIT): detected via `corp_actions.py` keyed on **announcement date**,
  never the future ex-date.

### 8.3 Universe (Candidate Pool)

Screen daily cross-section for: big % gainers, gap-ups, high RVOL, multi-day runners, near-52w-high.
**All windows strictly trailing (≤ as-of day).** `StockSnapshot` (frozen pydantic model, PIT,
honest `None` for missing fields). `CandidateUniverse` (indexed by symbol, duplicate-checked).

### 8.4 The Four Firewall Surfaces

The lookahead firewall is law. Four regression tests enforce zero leakage:

| Surface | What it guards | Test location | Implementation |
|---|---|---|---|
| **1. Date-lookahead** | `GuardedSource.check(requested > as_of)` raises `LookaheadError` | `tests/data/test_source.py::test_guarded_source_blocks_future_snapshot` | `alpha/data/firewall.py`, `alpha/data/source.py` |
| **2. Corp-action announce-date PIT** | Split detection keys on `announce_date ≤ as_of`, never the future `ex_date` | `tests/data/test_corp_actions.py::test_has_reverse_split_pending_pit` | `alpha/data/corp_actions.py` |
| **3. Split-vintage raw-PIT** | Stored prices are raw; a $14 close pre-reverse-split stays $14, not future-adjusted $140 | `tests/data/test_snapshot_source.py::test_bars_are_raw_not_future_adjusted` | `alpha/data/pit_store.py`, `alpha/data/snapshot_source.py` |
| **4. Windowed-rank trailing-only** | RVOL = today_volume / mean(trailing window strictly < day); today's bar never enters the denominator | `tests/universe/test_build_universe.py::test_rvol_uses_only_trailing_bars` | `alpha/universe/universe.py::_trailing_rvol` |

**Corp-action consumption (surface 2), as designed:** PIT detection runs on the *full captured*
corp-actions table (`PITStore.get_corp_actions()`) filtered in-process by
`known_corporate_actions(table, as_of)` (announce-date ≤ as_of). This is deliberately distinct from
the `MarketDataSource.corporate_actions(start, end)` method, which windows by `ex_date` (for future
adjustment bookkeeping) and is therefore guarded on `end`. A reverse split announced before `as_of`
but with a *future* ex-date is "pending" and must be visible to detection — so detection does **not**
go through the ex-date-windowed guarded query — US-3b adds the PIT-by-announce `corporate_actions_known(as_of)`
source primitive for exactly this, and `screen_decision` is its first live consumer (the reverse-split veto).

### 8.5 Eval Oracles

All oracles are **firewall-clean** — future labels appear only in the relabel step, never on the
inference path.

- **Forward-return oracle (PRIMARY):** next-open → t+N-close. **Horizon ≥ 2 enforced** (`entry ==
  exit` raises) — no same-day round-trip inflation. Market-neutral, reimplemented with tests.
- **Delisting/halt-to-zero = terminal loss (P0):** a candidate delisted/halted-to-zero between
  entry and exit is scored as `return = −1.0` (or documented haircut; pool-category = `nuked`).
  Never discarded for missing OHLCV. Distinguish "never captured" (drop) from "tradable at entry
  then delisted" (terminal loss) via the inactive/delist table.
- **Pool-category oracle (optional diagnostic, EXOGENOUS):** "continued/faded/nuked" membership
  uses a **fixed, exogenous threshold** defined outside `H` — not a Refiner-evolvable skill.
  Oracle label cannot be gamed by editing `H`. Default: rely on the return oracle.
- **Cost/slippage (GROSS, stated):** eval expectancy is gross (no cost/slippage/borrow-fee).
  For US low-float runners, spreads/slippage are first-order; a cost model is a US-3 enrichment.
  Do **not** treat gross expectancy as a tradeable edge.
- **Fill-feasibility on the inference path:** `eval/fill` → `DecisionPackage.fill_feasibility`
  so unfillable candidates are de-ranked before a human sees them.
- **Baselines:** "chase the biggest gainer" (`Hmin`) + "no-trade".
- **Alpha-decay monitor (`eval/alpha_decay.py`):** independent monitor of each active skill's
  recent-window OOS slope → Refiner retire/down-weight; consumes a crowding/reflexivity feature.

---

## 9. Phasing: US-0 → US-3

Each phase has a design spec, implementation plan, offline tests, and explicit acceptance gate.

| Phase | Contents | Acceptance Gate |
|---|---|---|
| **US-0 Foundations** | Alpaca daily source (raw bars; PIT adjustment-factor table deferred to US-1) + calendar + corp-actions + firewall (incl. 3 new US surfaces) + PITStore + SnapshotSource + MarketState + US universe builder (trailing-only) + English blueprint | Four firewall-surface regression tests green; universe reproduces deterministically offline |
| **US-1 Harness + eval + sizing + guard** | `H=(p,G,K,M)` (containers, 9 meta-tools, persistence, immutable-core, snapshot/rollback), seeds v1 (four families, per-phase scope, defense-heavy + alpha-production channel), return oracle (horizon≥2, delist→terminal-loss) + optional exogenous pool-category, walk-forward, baselines, regime classifier + state machine, `sizing/` (L3) + `guard/` (L4), `DecisionPackage` schema | Firewall no-leak + baselines reproduce + sizing/guard unit-tested (baseline-only, no agent yet) |
| **US-2 Agent + inner loop** | Per-role LLM agent (+ Claude client, master-dispatch + G sub-agents), Refiner 4-pass CRUD + credit + signatures + retire-discipline, scorer-aware capability-floor breaker, inner loop, three-way HCH/Hexpert/Hmin compare | Statistical decision procedure: multi-seed, paired HCH−Hexpert with CI, temp=0, window MDE < expected effect; offense-vs-defense contribution reported |
| **US-3 Web + enrichment** | `alpha_web` cockpit (research + decision); progressive enrichment unlocking full offense per §6 | Runner intraday/halts → meme short-interest/SSR/FINRA-short-volume → event earnings calendar/surprise → social sentiment; cost/slippage model |

### 9.1 Evaluation Protocol

- **Code tests:** fully offline (`MockLLMClient` + `FakeSource`). Port market-neutral regression
  tests (firewall date-lookahead, immutable-core write-guard, hallucination defense) **and add**
  the 3 new firewall-surface tests. Smoke scripts hit Alpaca/LLM manually only.
- **Eval methodology:** strict OOS/walk-forward, **purged & embargoed CV** (prevent train/test
  leakage at window edges), **multi-seed**, **regime-stratified** evaluation (doubly important
  given the US narrative-fragmented regime), and the **statistical decision procedure** for US-2
  (paired CI, MDE check, temp=0). Report per-family metrics and offense-vs-defense contribution.

---

## 10. Key Risks

1. **Capability floor (honest):** even with a strong Refiner and retire-discipline, CN reached
   only **parity** with frozen-expert seeds (initially degraded 3/3 windows). Mitigation: scorer-
   aware floor breaker + frozen-doctrine shadow + alpha-production channel + statistical decision
   procedure. Beating frozen seeds is the research frontier; parity is the honest expected outcome.

2. **Alpha decay + reflexivity:** edges have half-lives. Six non-stationarity gates carry over:
   regime labels, decay-weighted stats, dormant revival, alpha-decay monitor, capability-floor
   fallback, OOS/shadow/PIT. These gates are the real defense; strong Refiner alone is insufficient.

3. **Unfalsifiable success bar:** "HCH ≥ Hexpert" needs §9.1's statistical procedure. At ~30
   trading days a bare mean sign is noise (MDE ≈ 0.26; frozen arm drifts on resampling).
   temp=0 + multi-seed + CI + larger window are the fix.

4. **US data realities:**
   - Survivorship → delist-as-terminal-loss (never silently dropped).
   - Reverse-split distortion → raw-PIT + announcement-date detection.
   - No daily 龙虎榜 — FINRA short-volume/Reg-SHO are the daily substitutes (US-3).
   - **Free-tier limit is the IEX-only feed degrading full-market gainer-universe completeness**,
     NOT daily history depth (Alpaca daily history reaches ~2016). Universe completeness may need a
     broader snapshot source; logged as a US-3 risk.

5. **Narrative fragmentation:** global regime is weaker than CN; per-line classification may be
   noisy on small samples. Fallback: global risk-gate + family priors.

6. **Greenfield re-derivation risk:** reimplementing firewall/immutable-core could reintroduce CN
   bugs. Mitigation: port their regression tests verbatim (market-neutral) first.

7. **All-four-on-one-engine plumbing:** the family-tag flow (seed → regime filter → retrieval →
   prompt) and per-family eval separation are specified but unproven until US-2. If cross-family
   interference appears, split retrieval/eval by family before sharing one `H`.

---

## 11. Glossary

| English term | CN term | Paper / domain term |
|---|---|---|
| Continual Harness | — | `H=(p,G,K,M)` (paper 2605.09998) |
| doctrine | 作战方案 / 道 | `p` (policy component of H) |
| skill library | 葵花宝典 + 技能注册表 | `K` (knowledge component of H) |
| replay memory | 复盘知识库 | `M` (memory component of H) |
| sub-agent group | 子Agent群 | `G` (sub-agent set in H) |
| inner loop | 每日复盘 / 内循环 | inner loop (daily, reset-free) |
| outer loop | 跨周期协同学习 | outer loop (LoRA / θ update, US-2+) |
| candidate universe | zt-pool | daily screened stock pool |
| gainer | 涨幅榜 | large % up-close |
| gap-up | 跳空高开 | open > prior close by ≥ threshold |
| runner (multi-day) | 连板 N consecutive boards | N consecutive up-days with size |
| failed breakout | 炸板 | gap-up → red close |
| fill-infeasibility | 一字板 (unbuyable) | LULD-locked / micro-float no offer |
| RVOL | 换手率 (proxy) | relative volume = today_vol / trailing avg |
| regime | 情绪周期 | momentum cycle state |
| breadth | 情绪值 / 赚钱效应 | gainer/loser counts + follow-through rate |
| narrative line | 题材线 | sector/story cluster for per-line phase |
| risk-gate | 大盘结构 | global size multiplier scalar |
| terminal loss | 退市/ST归零 | delist/halt-to-zero → return = −1.0 |
| PIT (point-in-time) | 防前视 | no data after as-of cursor |
| lookahead firewall | 防前视防火墙 | AsOfGuard / LookaheadError |
| immutable-core guard | 不可变核心护栏 | Refiner cannot edit the hard-veto doctrine |
| DecisionPackage | 决策包 | action a_t (ranked candidates + rationale) |
| DAgger | DAgger (imitation learning) | human confirm = expert label |
| oracle | 已实现未来 | realized future returns (forward-return oracle) |
| LULD halt | 涨/跌停 (analog) | Limit-Up Limit-Down volatility pause (5-min) |
| SSR | — (no A-share analog) | Reg SHO Rule 201 short-sale price test |
| MWCB | 熔断 (analog) | Market-Wide Circuit Breaker (S&P −7/−13/−20%) |
| PDT rule | — | Pattern Day Trader < $25k → ≤3 round-trips/5d |
| T+1 settlement | T+1 (same-day-sell ban, different!) | US: settlement lag; no same-day-sell ban |
| horizon ≥ 2 | — | eval rule: no same-day open-buy/close-sell |
| alpha-decay monitor | alpha decay 监控 | per-skill recent OOS slope → retire/downweight |
| incubation tournament | 育种场 | skill sandbox: compete vs current before promote |
| swing family | 震荡/补涨 (partial) | mid/large cap base breakout + continuation |
| runner family | 连板/超短 | low-float multi-day momentum |
| event family | 预期差/催化剂 | catalyst gap + earnings surprise |
| meme/squeeze family | — | squeeze mechanics + social sentiment |
