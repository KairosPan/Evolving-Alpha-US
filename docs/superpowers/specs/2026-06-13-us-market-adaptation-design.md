# Evolving-Alpha-US — Design Spec

> **Date:** 2026-06-13 · **Version:** 1.1 (post adversarial self-review; see §14 changelog)
> **Status:** Design (awaiting user review → implementation plan)
> **Scope:** Greenfield, US-first rebuild of the self-evolving "hot-money"/speculative-momentum
> trading co-pilot, adapting the A-share `Evolving-Alpha` system to US equities.

---

## 0. One-paragraph summary

Port the *Continual Harness* `H=(p,G,K,M)` two-loop self-evolving agent (paper 2605.09998) from
A-share 游资/超短 trading to **US speculative-momentum trading**. The engine self-improves: an
inner loop (daily close review) edits the harness via meta-tool CRUD; an outer loop (replay +
process-reward + realized-future oracle relabel + soft-SFT) co-adapts a policy **(outer loop is
US-2+; what US-2 validates is the inner loop only — see §2)**. It is a **decision-support co-pilot**
— it produces a `DecisionPackage` (ranked candidates + plans + rationale + **per-candidate size tier
+ portfolio risk budget + fill-feasibility**); a human confirms. **No automatic live orders.** This
is a **greenfield rebuild** (not an edit of the CN code): clean US-native data model, all-English
code and docs. "Ported from CN" anywhere in this spec means **reimplemented cleanly with tests,
using the CN version in `reference/cn/` as algorithmic reference** — never a literal copy. The
genuinely market-neutral, hard-to-get-right mechanisms (lookahead firewall, immutable-core
write-guard, hallucination defenses, meta-tool CRUD discipline) are reimplemented first, with their
regression tests.

## 1. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Repo | `KairosPan/Evolving-Alpha-US`, **public**, clean-slate git history | User choice; no secrets (key via env). |
| Strategy | **Greenfield rebuild** (US-first) | User choice; clean US data model, English, public repo. |
| Domains | **All four** as family-tagged seed packs on **one** engine; **per-phase functional scope differs** (§6, §9) | Runner / Swing / Event / Meme. Swing is fully functional at daily cadence in US-1; Runner/Event/Meme ship **defense seeds + daily-proxy offense** in US-1, full offense in US-3 when their data lands. |
| Sequencing | **Unified daily-cadence engine first** | Keeps the daily two-loop intact; fastest path to a validatable inner loop. Intraday/halts/short/social are later enrichments. |
| Data | **Alpaca** (free key; daily bars + news now, intraday/halts later) | Keyed but free; scales without swapping providers. **Caveat (§12):** free tier is IEX-only feed — adequate for OHLCV history (to ~2016) but thin for full-market gainer screening; universe completeness is the real free-tier limit, not history depth. |
| LLM | **Configurable per-role** (Agent cheap, Refiner Claude), via env; **temp=0 for eval determinism** | Agent does many rollouts (cost); Refiner edits `H` (capability). temp=0 controls the resampling noise that makes the success bar untestable (§9, §12). |
| Package | `youzi` → **`alpha`** | English, market-neutral name. |
| Docs/comments | **All English**; documentation is a **first-class deliverable** | Public, US-facing; knowledge survives `reference/cn/` deletion. |
| CN code | Moved to **`reference/cn/`**, deleted when rebuild is done | Reference during rebuild; permanent copy lives in the `Evolving-Alpha` repo. |

## 2. Positioning & non-goals

- **Co-pilot, human-confirmed.** Output is a `DecisionPackage` (schema §4.1); the human
  confirms/rejects/modifies (doubling as DAgger expert labeling for the future outer loop). **No
  auto live orders.**
- **Two-loop, but staged:** the **outer loop (LoRA/θ training) is deferred to US-2+**. US-2's
  acceptance validates the **inner loop only** (Harness self-refinement); passing US-2 demonstrates
  "self-editing harness ≥ frozen-expert harness on OOS", **not** that the full two-loop system
  converges. The §0 summary describes the full target; the *validated* claim at each phase is
  narrower.
- **Non-goals (now):** intraday execution, real brokerage order routing, options/derivatives
  pricing, social-sentiment ingestion (US-3 enrichment), the outer-loop LoRA training (US-2+),
  multi-market abstraction (CN is reference-only here). **In scope (not deferred):** the sizing/
  portfolio (§4 L3) and risk-guard/veto (§4 L4) layers — these are survival-critical and ship in
  US-1.

## 3. Concept mapping (A-share 游资 → US speculative momentum)

The structural key: **US has no daily price limits.** It has LULD volatility pauses, SSR (a
short-sale price test, *not* a halt), and market-wide circuit breakers. Each maps to a *different*
A-share concept; the v1.0 spec bundled several incorrectly (fixed below). For the **daily-cadence
first slice**, intraday halt details collapse into daily proxies (big-gainer / gap / failed
follow-through); precise halt mechanics are a US-3 enrichment.

### 3.1 High-fidelity (core port) — corrected mechanics

| A-share | US analog (precise) | Daily-cadence proxy (slice-1) |
|---|---|---|
| 涨停 limit-up | **LULD halt-up** = transient **5-min volatility pause** (price outside band ≥15s; Tier-1 S&P/Russell-1000 vs Tier-2 bands; reopens via auction; **not a day-lock** — runner can keep going, repeated pauses) + extreme % gainer | top % gainer / large up-close |
| 跌停 limit-down | **LULD halt-down** (same mechanics, downside) + extreme loser | large down-close |
| (no A-share analog) | **SSR (Reg SHO Rule 201)** = short-sale price test, triggers at **−10% intraday vs prior close**, restricts *shorting* to above-NBB for **rest of day + next session**; does **not** halt or limit price | SSR-flag (later); affects short/squeeze logic only |
| 连板 N consecutive boards | **multi-day runner** (repeated halt-ups / consecutive large up-days) | N consecutive up-days with size |
| 炸板 failed board | **failed breakout / first red day / gap-up→red-close** | gap-up→red-close, fade-from-high |
| 一字板 gap-locked (unbuyable) | **true fill-infeasibility** = LULD-locked with no offer / sub-pennysize micro-float with displayed size ≪ intended order. **NOT** an ordinary gap-up (US gap-ups fill at the higher open). | size-at-offer vs intended order (intraday); daily proxy = extreme gap + near-zero liquidity |
| 封单 seal-order size | resting size at offer / halt-resumption auction imbalance | (intraday enrichment) |
| 弱转强 weak-to-strong | **distinct setups, not interchangeable:** gap-and-go (opens strong above prior close, no gap-fill) **vs** VWAP-reclaim (opens weak, recovers back above VWAP) **vs** ORB (breaks first-N-min range). Modeled as separate skills (§6). | gap-up holding vs prior close (daily proxy of gap-and-go) |
| 龙头 dragon-head | lead runner / relative-strength leader | strongest ticker in a theme |
| 接力 relay | continuation chase on day N+1 | buy yesterday's leader's follow-through |
| 题材 / 概念 | sectors + narratives (AI, quantum, nuclear, biotech, crypto-adj, defense) | catalyst/theme tag |
| 题材轮动 / sympathy | narrative rotation / sympathy plays | co-movement with leader |
| 情绪值 / 情绪周期 | risk-on momentum regime (gainer breadth, # halts, follow-through, failed-breakout rate) | daily breadth scalars |
| 赚钱/亏钱效应 | risk-on / risk-off effect (do yesterday's runners follow through or get sold) | next-day runner survival rate |
| 预期差 / 预期链 | catalyst surprise (earnings vs whisper/consensus, FDA, guidance, contract) | event tag + gap reaction (full surprise% = US-3) |
| 核按钮 dump | parabolic blowoff / max-pain flush | large reversal day |
| 880005 / 大盘结构 + 熔断 | **index & breadth** (SPY/QQQ/IWM trend, % above MA, A/D, new-highs/lows) **+ MWCB** (S&P −7%/−13%/−20% market-wide halts) | daily index/breadth; MWCB as a risk-gate event |
| 容量行情 | liquidity/volume regime (small-cap & IWM turnover) | daily volume regime |
| T+1 (same-day-**sell** ban → exit-timing) | US has **no** same-day-sell ban (day-trading allowed). Two distinct US facts: settlement is **T+1** (since 2024-05-28) and the **PDT rule** (<$25k margin → ≤3 day-trades/5d). **The real port is an eval rule, not a market analog:** enforce **horizon ≥ 2** (no same-day open-buy/close-sell) in the backtest to avoid inflated round-trips (§7). | horizon≥2 enforced in scorer |
| 幸存者偏差 / PIT (退市/ST/改名) | survivorship/PIT (delistings, ticker changes, **reverse splits**, halts). **Delisting is a terminal LOSS to be scored, not a data gap to drop (§7, P0).** | PIT snapshots + delist→terminal-loss oracle |

### 3.2 Weak / no direct analog (enrichment, not core)

- **龙虎榜** (Dragon-Tiger top-trader disclosure) has no single daily US equivalent, but the
  substitutes are **not uniformly delayed**: **FINRA daily short-sale-volume files** (next-morning,
  free, per-symbol short/total ratio) and the **Reg SHO daily threshold-securities list** are
  genuinely daily; short interest (bi-monthly, lagged), 13F (quarterly), Form 4 (≤2 business days),
  options flow, dark-pool/ATS (FINRA, lagged) are slower. Core stays without 龙虎榜; the daily FINRA
  short-volume + Reg SHO list are a **meme/squeeze** enrichment (US-3).

## 4. Architecture & module layout (greenfield `alpha/`)

```
alpha/
  data/         # L0 — sources + PIT + lookahead firewall
    source.py            # MarketDataSource protocol (+ GuardedSource wrapper)
    alpaca.py            # AlpacaSource: daily bars (raw + adjusted) + news
    calendar.py          # US market calendar (NYSE/Nasdaq)
    firewall.py          # AsOfGuard / LookaheadError (reimplement, market-neutral)
    pit_store.py         # PIT snapshot store (parquet, atomic); stores RAW + adjustment factors
    snapshot_source.py   # offline PIT source
    capture.py           # window prefetch → store (PIT-correct adjustment, see §7)
    corp_actions.py      # splits / reverse-splits / delistings — PIT by announcement date
  state/
    market.py            # MarketState, RunnerRung (连板梯队 analog), as-of timestamp
    decision.py          # DecisionPackage schema (§4.1) — frozen; the action a_t + DAgger record
  features/     # L0→L1 — US momentum features (regime-relative; TRAILING-only windows)
    breadth.py runner.py failed_breakout.py relative_strength.py builder.py
  regime/       # G_cycle — read-only sub-agent of H.G (SSOT: never writes phase back into H)
    cycle.py classifier.py
  universe/     # candidate universe (gainers/gap-ups/high-RVOL/runners), PIT, EXOGENOUS oracle screen
    stock.py universe.py
  harness/      # H=(p,G,K,M) — reimplement clean (containers, 9 meta-tools, persistence,
                #   immutable-core guard, snapshot/rollback, registry, store, regime_label, edit_log)
  agent/        # L2 decision: master-dispatch orchestrator + named G sub-agents
    agent.py prompt.py parse.py retrieval.py
    subagents.py         # leader/relay, theme-miner, expectation-gap dispatch (G members)
  sizing/       # L3 — sizing / portfolio / correlation (NEW; survival-critical)
    position.py          # confidence→size-tier (flat/probe/core/heavy) + single-name & single-day risk budget
    correlation.py       # same-narrative/sympathy/family = ONE aggregated correlated bet; exposure netting
    portfolio.py         # total exposure vs §5 global risk-gate/size-multiplier; batching / scale-in
  guard/        # L4 — hard-veto layer (NEW; overrides Agent suggestions)
    stops.py             # form/regime/time stop-loss with veto power
    veto.py              # dilution/offering/ATM-shelf, halt-then-dump, going-concern, regulatory hard veto
    breaker.py           # single-name / single-day / consecutive-loss circuit breaker; MWCB awareness
  refine/       # inner-loop Refiner: refiner, refiner_prompt, credit, signatures, ops (+ retire-discipline)
  eval/         # walk_forward, trajectory, oracle, return_oracle, scorer (scorer-aware breaker),
                #   metrics, baselines, decision-eval, fill (inference-path fill-feasibility), alpha_decay
  loop/         # inner_loop (scorer-aware floor breaker), compare (HCH/Hexpert/Hmin), run_store
  llm/          # client (protocol + MockLLMClient), anthropic.py (Claude), openai_compat.py (cheap),
                #   config.py (per-role provider; temp=0 for eval), cache, extract
  config.py
alpha_web/      # FastAPI + HTMX cockpit (research + decision), domain-isolated, single-way dependency
seeds/          # four US playbook families, family-tagged: runner / swing / event / meme
docs/           # FIRST-CLASS English docs: blueprint.md, PROJECT_STATE.md, ROADMAP.md, specs/, plans/
scripts/        # capture_window, smoke_alpaca, smoke_agent, serve_web, sample_run
tests/          # mirror modules, offline (MockLLM + FakeSource); firewall/immutable-core regressions
reference/cn/   # copied CN system — reference during rebuild, DELETED when done
```

**Decision pipeline (who runs in what order):** `data → features → regime (G_cycle) → universe →
agent (master-dispatch + G sub-agents) → sizing (L3) → guard (L4 veto) → DecisionPackage → human`.
Self-evolution machinery (`harness/`, `refine/`, `loop/`, `eval/`) wraps this.

**Named `G` sub-agents** (carried from CN §6.2/§6.4, live in `H.G`, dispatched by `agent/`):
`G_cycle` (regime classifier — **read-only**, SSOT), leader/relay identifier, theme/narrative miner,
expectation-gap evaluator, `G_risk` (stops/veto — in `guard/`), regulatory/halt veto (in `guard/`),
fill-feasibility evaluator (in `eval/fill` + inference path). The Refiner owns the review/reflection
function (no separate self-reflection sub-agent — intentional simplification vs CN's name-only entry).

**Principles:**
- **Domain-agnostic core reimplemented clean, with tests:** firewall, immutable-core guard,
  meta-tool CRUD discipline, hallucination defenses.
- **Per-role LLM** (`llm/config.py`): Agent=cheap, Refiner=Claude, **temp=0 for eval**.
- **Family-tagged seeds** (`family: runner|swing|event|meme`): one harness `H`; the family tag flows
  **seed → regime per-line filter → retrieval → agent prompt**; eval reports per-family so one
  family's signal isn't drowned (§5, §9). Per-narrative-line phase → eligible family set.
- **Daily cadence now, intraday-ready:** `MarketState.as_of` is a `datetime`; the source protocol
  leaves room for intraday bars/halts.
- **Lookahead firewall is law — incl. THREE new US surfaces** (beyond CN's date-guard): (1)
  split/adjustment vintage (use RAW point-in-time prices for price-level/float-sensitive features and
  entries; see §7), (2) windowed price-rank features (RVOL, 52w-distance, regime percentile must use
  **trailing-only** windows), (3) corporate-action ex-date (detect splits/reverse-splits by **PIT
  announcement date**, not the future ex-date row). Each gets a regression test.
- **SSOT:** regime/phase live on `s_t` (observation side), objective and oracle-auditable; `G_cycle`
  never writes phase back into `H`.

### 4.1 `DecisionPackage` schema (the action `a_t`)

Frozen (`state/decision.py`). The human-confirmation surface and DAgger label record.

```jsonc
{
  "date": "...", "as_of": "...",
  "regime_read": { "global_risk_gate": 0.4, "lines": [{"narrative":"AI","phase":"Trend","frontside":true,"confidence":0.7}] },
  "ranked_candidates": [
    { "ticker":"...", "name":"...", "family":"runner|swing|event|meme",
      "pattern":"gap-and-go", "skill_id":"...",
      "entry":"...", "exit_stop":"...",
      "size_tier":"flat|probe|core|heavy",                 // from sizing/ (L3)
      "fill_feasibility": {"buyable": true, "reason":"..."},// from eval/fill on inference path
      "taboo_check":[{"rule":"no-chase-in-risk-off","status":"pass"}],  // from guard/ (L4)
      "reason":"K skill + M analog", "confidence":0.62,
      "counterview":"if AI line flips to backside, drop" } ],
  "no_trade_reason": "...",
  "key_risks": ["..."],
  "portfolio": { "total_exposure_budget": 0.5, "correlated_groups":[["AAA","BBB"]] },  // from sizing/portfolio
  "human_confirm": null                                    // confirm | reject | modify(+reason)
}
```

## 5. US momentum regime machine

Two-level, like CN: **global mother-state** × **per-narrative lines**. The "轮回/reincarnation"
insight ports → drives **dormant-skill revival**.

**Refinements vs CN (US tape is narrative-fragmented and faster):**
1. **Global mother-state = risk-gate + size multiplier** (consumed by `sizing/portfolio.py`), not the
   primary regime; **per-line phase drives playbook/family selection**.
2. **Frontside / backside is a per-line attribute** (scalar), not a 7th state.
3. **Follow-through day is a transition event**, not a dwelt-in state.

| US state | CN analog | Observable daily criteria | Transition → |
|---|---|---|---|
| **Washout / Freeze** | 混沌/冰点 | few gainers, runners failing, IWM down, new-lows high, no follow-through | gappers hold + leader emerges → Recovery |
| **Recovery / First-Green** | 修复启动 | first clean gap-and-go survivors, a day-2 continuation, breadth ticking up | narrative gets multiple movers → Heating |
| **Heating / Ignition** | 情绪回暖/题材启动 | narrative ignites (many tickers up big same day), index FTD, RVOL spikes | lead runner + sympathy basket → Trend |
| **Trend / Momentum** | 主升 | leader new highs daily, sympathy runs, gap-and-go's work, low failed-breakout rate | first big distribution day + no next-day recovery → Distribution |
| **Distribution / Churn** | 震荡/补涨 | choppy, laggards run while leaders churn, failed-breakout rate climbing, risk-off spreading | leader breaks down on volume / blowoff → Exhaustion |
| **Exhaustion / Flush** | 退潮 | leaders + sympathy co-flush, hot ticker dumped, MWCB risk | breadth collapses, old leaders stop falling + new narrative stirs → Washout/Reset |

Output: continuous confidence per narrative line + global risk-gate scalar + per-line
frontside/backside. Criteria are objective and oracle-auditable (the *judgments* are calibratable;
they need not be frozen formulas — same posture as CN).

## 6. Four playbook seed families

All family-tagged inside one `H`. **Design bias: defense seeds (failure-detectors + taboos) richer
than offense seeds** — guardrails clear the capability floor faster and counter the CN failure mode
(Refiner over-pruning on tiny samples). **But defense-only would only demonstrate loss-prevention,
not alpha** (CN arch-review). So we also keep an explicit **alpha-production channel**: offense
skills can be created and **promoted via the incubation tournament**, and eval reports the
**offense-vs-defense contribution split** so US-2 can tell whether self-evolution adds edge or only
trims risk.

**Per-phase functional scope** (resolves the v1.0 "all four in US-1 but data deferred" tension):

| Family | US-1 (daily data only) | Full offense unlocked |
|---|---|---|
| **Swing** (mid/large) | **fully functional** — base breakout, pullback-to-MA, RS-leader continuation, sector rotation, earnings-gap continuation; failures: failed breakout, distribution cluster, leader breakdown | US-1 |
| **Runner** (low-float) | defense seeds + **daily proxies** (multi-day up-days, gap%, daily RVOL, gap-up-hold); failures: parabolic blowoff, first red day, dilution/ATM, reverse-split pump | halt-resumption / VWAP-reclaim / ORB / halt count → **US-3 intraday** |
| **Event/catalyst** | defense seeds + **news-tag** proxy (Alpaca news) | earnings-calendar proximity, surprise% vs whisper → **US-3** |
| **Meme/squeeze** | defense seeds only (squeeze offense needs short data) | short-interest%, days-to-cover, borrow, SSR, social → **US-3** |

**Features per family** as in v1.0, with the deferral table above. **Shared immutable-core doctrine**
(Refiner can never edit): respect the regime (no chasing in risk-off), **same-narrative = one
correlated bet** (enforced by `sizing/correlation.py`), stop discipline, fill-feasibility,
survivorship/PIT awareness, position/loss circuit-breakers. *"Don't fight SSR" is included as a
doctrine line but is **inert until SSR data lands in US-3*** (documented, not silently assumed live).

Seeds bootstrapped from this design + established US momentum knowledge (no US "轮回.docx" required).
User's personal trading notes are an optional high-value **later enrichment pass**.

## 7. Data, universe & eval oracle

- **AlpacaSource** implements `MarketDataSource`: daily bars, news, `/v2/calendar`, corporate
  actions. No "top gainers" endpoint → **build the universe** by scanning daily bars/snapshots and
  ranking. PIT: `capture_window` → `PITStore` (parquet, atomic) → `SnapshotSource` offline, behind
  `GuardedSource`.
- **Split/adjustment (lookahead fix, P1):** store **raw OHLCV + a PIT adjustment-factor table**.
  Price-level/float-sensitive features (price thresholds, RVOL denominators, penny/low-float screens)
  compute from **raw point-in-time** prices; the forward-return *ratio* is split-invariant within a
  contiguous slice (verified) so return labels are fine, but a stored single-vintage adjusted slice
  is **not** point-in-time for level features. Document that PITStore gives PIT *pool membership* and
  *raw* prices; adjusted-vintage levels are not PIT unless recomputed per date.
- **Reverse-split / delisting (PIT):** detect via `corp_actions.py` keyed on **announcement date**,
  not the future ex-date; flag reverse-split-pump as a failure-detector.
- **Universe (zt-pool analog):** screen for big % gainers, gap-ups, high RVOL, multi-day runners,
  near-52w-high — **all trailing-only windows** (≤t). `StockSnapshot` (frozen, PIT), honest `None`.
- **Eval oracles (firewall-clean — future labels only in relabel, never inference):**
  - **Forward-return oracle (PRIMARY, market-neutral):** next-open → t+N-close, **horizon ≥ 2
    enforced** (`entry == exit` raises) so no same-day round-trip inflation. Reimplemented-with-tests.
  - **Delisting/halt-to-zero = terminal loss (P0):** a candidate delisted/halted-to-zero between
    entry and exit is scored as a worst-case realized loss (return = −1.0 or documented haircut;
    pool-category = `nuked`) — **never discarded for missing OHLCV, never labeled `faded`**. The
    day-baseline includes these terminal losses. Distinguish "never captured" (drop) from "tradable
    at entry then delisted" (terminal loss) via the inactive/delist table.
  - **Pool-category oracle (DEMOTED to optional diagnostic; EXOGENOUS, P0):** if used, "continued/
    faded/nuked" membership uses a **fixed, exogenous threshold defined outside `H`** (not a
    Refiner-evolvable skill) so the oracle label cannot be gamed by editing `H`. Default: rely on the
    return oracle; pool-category is a coarse diagnostic only.
  - **Cost/slippage (P2):** eval expectancy is **GROSS** (no cost/slippage/borrow-fee) — stated, not
    assumed away. For US low-float runners spreads/slippage are first-order; a cost model is a US-3
    enrichment. Do **not** treat gross expectancy as a tradeable edge.
  - **Fill-feasibility runs on the inference path** (`eval/fill` → `DecisionPackage.fill_feasibility`)
    so unfillable candidates are de-ranked before a human sees them — not only as an eval penalty.
  - **Baselines (Hmin):** "chase the biggest gainer" + "no-trade".
  - **Alpha-decay monitor (`eval/alpha_decay.py`):** independent monitor of each active skill's
    recent-window OOS slope → Refiner retire/down-weight; consumes a crowding/reflexivity feature.

## 8. LLM (per-role)

`llm/config.py`: roles `{agent, refiner}` resolve provider+model from env (`ALPHA_AGENT_*`,
`ALPHA_REFINER_*`). Providers: `anthropic` (`ClaudeClient`, latest Claude, JSON via tool-use,
retry/backoff), `openai_compat` (DeepSeek/OpenAI base_url, cheap), `mock` (offline tests). Defaults:
Agent → cheap (Haiku 4.5 or DeepSeek); Refiner → Claude Opus/Sonnet. **`temperature=0` for all eval
runs** (the frozen-arm drift that makes the success bar untestable is LLM resampling noise — §9,
§12). Deterministic cache for offline tests. All behind `LLMClient`.

## 9. Phasing

Each phase = design spec + implementation plan + offline tests. Greenfield, daily-cadence first.

- **US-0 Foundations:** repo restructure (`reference/cn/` done), Alpaca daily source (raw +
  adjustment factors) + calendar + corp-actions + firewall (incl. the 3 new US surfaces) + `PITStore`
  + `SnapshotSource`, `MarketState`, US universe builder (trailing-only). Write the **English
  blueprint** (`docs/blueprint.md`). **Acceptance:** firewall regression tests (date + split-vintage
  + windowed-rank + corp-action ex-date) green; universe reproduces deterministically offline.
- **US-1 Harness + eval + sizing + guard:** `H=(p,G,K,M)` (containers, 9 meta-tools, persistence,
  immutable-core, snapshot/rollback), **seeds v1 (four families, per-phase scope per §6,
  defense-heavy + alpha-production channel)**, return oracle (horizon≥2, delist→terminal-loss) +
  optional exogenous pool-category, walk-forward, baselines, regime classifier + state machine,
  **`sizing/` (L3) + `guard/` (L4)**, `DecisionPackage` schema. **Acceptance is baseline-only**
  (no agent yet → walk-forward only the trivial NoTrade/chase baselines): firewall no-leak +
  baselines reproduce + sizing/guard unit-tested.
- **US-2 Agent + inner loop:** per-role LLM agent (+ Claude client, master-dispatch + G sub-agents),
  Refiner 4-pass CRUD + credit + signatures + retire-discipline, **scorer-aware capability-floor
  breaker** (daily advantage = score − same-day baseline; CN's resolved B2 form, not the stale
  `floor_abs=−0.2`), inner loop, three-way HCH/Hexpert/Hmin compare. **Acceptance = a statistical
  decision procedure** (§10), not a bare mean sign: multi-seed, paired HCH−Hexpert with CI, temp=0,
  over a window large enough that MDE < expected effect; report offense-vs-defense contribution.
- **US-3 Web + enrichment:** `alpha_web` cockpit (research + decision); then progressive enrichment
  unlocking full offense per §6: runner intraday/halts → meme short-interest/SSR/FINRA-short-volume →
  event earnings calendar/surprise → social sentiment; plus a cost/slippage model.

## 10. Testing & evaluation protocol

- **Code tests:** fully offline (`MockLLMClient` + `FakeSource`); port the market-neutral regression
  tests (firewall date-lookahead, immutable-core write-guard, hallucination defense) **and add** the
  3 new firewall-surface tests (§4). Smoke scripts hit Alpaca/LLM manually only. Tests mirror modules.
- **Eval methodology (carried from CN §6.9, restored from v1.0 omission):** strict OOS/walk-forward,
  **purged & embargoed CV** (prevent train/test leakage at window edges), **multi-seed**,
  **regime-stratified** evaluation (doubly important given the US narrative-fragmented regime, §5),
  and the **statistical decision procedure** for US-2 (paired CI, MDE check, temp=0). Report
  per-family metrics and offense-vs-defense contribution.

## 11. Documentation (first-class deliverable)

`docs/blueprint.md` (authoritative US architecture blueprint, written US-0), `docs/PROJECT_STATE.md`,
`docs/ROADMAP.md`, `docs/superpowers/specs/` + `plans/` per-phase, public `README.md`. **Knowledge
survives `reference/cn/` deletion.**

## 12. Risks & open questions

1. **Capability floor (honest):** even with a strong Refiner and retire-discipline, CN reached only
   **parity** with frozen-expert seeds (initially degraded 3/3 windows). Mitigation is *not* merely
   "use a strong Refiner" — it is: scorer-aware floor breaker + frozen-doctrine shadow + an explicit
   alpha-production channel + the statistical decision procedure. Beating frozen seeds remains the
   research frontier; "parity" is an honest, expected outcome.
2. **Alpha decay + reflexivity:** edges have half-lives; six non-stationarity gates carry over
   (regime labels, decay-weighted stats, dormant revival, **alpha-decay monitor `eval/alpha_decay.py`**,
   capability-floor fallback, OOS/shadow/PIT).
3. **Unfalsifiable success bar (P0, mitigated):** "HCH ≥ Hexpert" needs §10's statistical procedure;
   at ~30 trading days a bare mean sign is noise (MDE ≈ 0.26; frozen arm drifts on resampling).
   temp=0 + multi-seed + CI + larger window are the fix.
4. **US data realities:** survivorship → delist-as-terminal-loss (§7); reverse-split distortion →
   raw-PIT + announcement-date detection; no daily 龙虎榜 (FINRA short-volume/Reg-SHO are the daily
   substitutes, US-3); **free-tier limit is the IEX-only feed degrading full-market gainer-universe
   completeness — NOT daily history depth** (Alpaca daily history reaches ~2016). Universe
   completeness may need a broader snapshot source; logged as a US-3 risk.
5. **Narrative fragmentation:** global regime is weaker than CN; per-line classification may be noisy
   on small samples → fall back to global risk-gate + family priors.
6. **Greenfield re-derivation risk:** reimplementing firewall/immutable-core could reintroduce fixed
   CN bugs → port their regression tests verbatim (market-neutral) first.
7. **All-four-on-one-engine plumbing:** the family-tag flow (seed→regime filter→retrieval→prompt) and
   per-family eval separation are specified in §4/§6 but unproven until US-2; if cross-family
   interference appears, split retrieval/eval by family before sharing one `H`.

## 13. What "done" means for this spec's scope

This spec covers the **full target architecture**; implementation proceeds phase-by-phase (US-0 →
US-3), each with its own plan. The immediate next artifact is the **US-0 implementation plan**.

## 14. Changelog — v1.0 → v1.1 (adversarial self-review, 2026-06-13)

48 findings (5 lenses, per-finding verification); 41 confirmed, 7 rejected. Incorporated:

- **P0** — (1) Added L3 **`sizing/`** (position/correlation/portfolio) layer + size_tier/portfolio in
  `DecisionPackage`; (2) **delisting = terminal loss** in the oracle (no silent discard); (3)
  pool-category oracle made **exogenous** + **demoted** (return oracle primary) to kill the
  H-circular threshold; (4) **statistical decision procedure** for the US-2 success bar + temp=0.
- **P1** — added L4 **`guard/`** veto layer; fill-feasibility on the **inference path**; corrected
  **T+1→horizon≥2** (not PDT); corrected **一字板** fill analog; **split-vintage / windowed-rank /
  corp-action ex-date** firewall surfaces + tests; **scorer-aware floor breaker**; **per-phase family
  scope** (meme/runner/event offense deferred with their data); **purged/embargoed CV + multi-seed +
  regime-stratified** eval; **defense-vs-offense** contribution measurement + alpha-production channel.
- **P2** — corrected **SSR** (short-sale price test, not a halt), added **MWCB**, precise **LULD**
  mechanics, distinct **gap-and-go/VWAP-reclaim/ORB** definitions, **halt-type** distinctions, daily
  **FINRA short-volume/Reg-SHO** substitutes for 龙虎榜; defined **`DecisionPackage`** schema (§4.1);
  restored **master-dispatch + named G sub-agents**; homed the **alpha-decay monitor**; **cost/
  slippage gross** caveat; corrected the **Alpaca free-tier** characterization (IEX feed, not
  history); clarified **"ported from CN" = reimplemented-with-tests**; US-1 eval **baseline-only**.
- **Rejected (no change):** return-oracle split-rebasing (ratio is split-invariant — mathematically
  refuted); FTD/MWCB-as-frozen-formula (contradicts the calibratable-judgment principle);
  self-reflection sub-agent (CN entry was name-only; Refiner owns review); SSR-fill-feasibility
  (mis-modeled); §1-vs-body "all four" (already reconciled); no-LLM-until-US2 (matches CN MVP
  staging); outer-loop-claim (already caveated). Two were folded in anyway as clarifications.
