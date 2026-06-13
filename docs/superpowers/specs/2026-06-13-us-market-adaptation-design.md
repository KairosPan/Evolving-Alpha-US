# Evolving-Alpha-US — Design Spec

> **Date:** 2026-06-13
> **Status:** Design (awaiting user review → implementation plan)
> **Scope:** Greenfield, US-first rebuild of the self-evolving "hot-money"/speculative-momentum
> trading co-pilot, adapting the A-share `Evolving-Alpha` system to US equities.

---

## 0. One-paragraph summary

Port the *Continual Harness* `H=(p,G,K,M)` two-loop self-evolving agent (paper 2605.09998) from
A-share 游资/超短 trading to **US speculative-momentum trading**. The engine self-improves: an
inner loop (daily close review) edits the harness via meta-tool CRUD; an outer loop (replay +
process-reward + realized-future oracle relabel + soft-SFT) co-adapts a policy. It is a
**decision-support co-pilot** — it produces ranked candidates + plans + rationale; a human
confirms. **No automatic live orders.** This is a **greenfield rebuild** (not an edit of the CN
code): clean US-native data model, all-English code and docs, with the genuinely market-neutral,
hard-to-get-right safety mechanisms (lookahead firewall, immutable-core write-guard, hallucination
defenses, meta-tool CRUD discipline) **reimplemented cleanly with their tests**, using the proven
CN versions in `reference/cn/` as algorithmic reference.

## 1. Locked decisions

| Decision | Choice | Rationale |
|---|---|---|
| Repo | `KairosPan/Evolving-Alpha-US`, **public**, clean-slate git history | User choice; no secrets (key via env). |
| Strategy | **Greenfield rebuild** (US-first) | User choice; clean US data model, English, public repo. |
| Domains | **All four**, as family-tagged seed packs on **one** engine | Runner / Swing / Event / Meme — one `H`, regime+retrieval filter by family. |
| Sequencing | **Unified daily-cadence engine first** | Keeps the engine's daily two-loop intact; fastest validation of the self-evolution thesis on free data. Intraday/halts/short/social are later enrichments. |
| Data | **Alpaca** (free key; daily + news now, intraday/halts later) | Keyed but free; scales to runner intraday without swapping providers. |
| LLM | **Configurable per-role** (Agent cheap, Refiner Claude), via env | Agent does many rollouts (cost); Refiner edits `H` (capability). Both behind `LLMClient`. |
| Package | `youzi` → **`alpha`** | English, market-neutral name (Evolving-**Alpha**-US). |
| Docs/comments | **All English**; documentation is a **first-class deliverable** | Public, US-facing; knowledge survives when `reference/cn/` is deleted. |
| CN code | Moved to **`reference/cn/`**, deleted when rebuild is done | Reference during rebuild; permanent copy lives in the `Evolving-Alpha` repo. |

## 2. Positioning & non-goals

- **Co-pilot, human-confirmed.** Output is a `DecisionPackage`; the human confirms/rejects/modifies
  (which doubles as DAgger expert labeling for the outer loop). **No auto live orders.**
- **Non-goals (now):** intraday execution, real brokerage order routing, options/derivatives
  modeling, social-sentiment ingestion (later enrichment), the outer-loop LoRA training (Phase US-2+
  after the inner loop is validated), multi-market abstraction (CN is reference-only here).

## 3. Concept mapping (A-share 游资 → US speculative momentum)

The structural key: **US has no daily price limits, but it has LULD halts** — low-float runners get
*halted-up* repeatedly, the genuine analog of 连板. For the **daily-cadence first slice**, intraday
halt details collapse into daily proxies (big-gainer / gap / failed-follow-through); halts become an
enrichment later.

### 3.1 High-fidelity (core port)

| A-share | US analog | Daily-cadence proxy (slice-1) |
|---|---|---|
| 涨停 limit-up | LULD halt-up + extreme % gainer | top % gainer / large up-close |
| 跌停 limit-down | LULD halt-down / extreme loser / **SSR triggered** | large down-close, SSR flag |
| 连板 N consecutive boards | multi-day runner (repeated halts / consecutive large up-days) | N consecutive up-days with size |
| 炸板 failed board | failed breakout / halt-and-crack / first red day | gap-up→red-close, fade-from-high |
| 一字板 gap-locked (unbuyable) | gap-and-halt / unfillable gap-up open | gap% beyond entry → fill-infeasible |
| 封单 seal-order size | resting size at offer / halt-resumption imbalance | (intraday enrichment) |
| 弱转强 weak-to-strong | gap-and-go / premarket strength / VWAP reclaim / ORB hold | gap-up holding vs prior close |
| 龙头 dragon-head | lead runner / relative-strength leader | strongest ticker in a theme |
| 接力 relay | continuation chase on day N+1 | buy yesterday's leader's follow-through |
| 题材 / 概念 | sectors + narratives (AI, quantum, nuclear, biotech, crypto-adj, defense) | catalyst/theme tag |
| 题材轮动 / sympathy | narrative rotation / sympathy plays | co-movement with leader |
| 情绪值 / 情绪周期 | risk-on momentum regime (gainer breadth, # halts, follow-through, failed-breakout rate) | daily breadth scalars |
| 赚钱/亏钱效应 | risk-on / risk-off effect (do yesterday's runners follow through or get sold) | next-day runner survival rate |
| 预期差 / 预期链 | catalyst surprise (earnings vs whisper, FDA, guidance, contract) | event tag + gap reaction |
| 核按钮 dump | parabolic blowoff / max-pain flush | large reversal day |
| 880005 / 大盘结构 | index & breadth (SPY/QQQ/IWM trend, % above MA, A/D, new-highs/lows) | daily index/breadth |
| 容量行情 | liquidity/volume regime (small-cap & IWM turnover) | daily volume regime |
| T+1 | PDT rule (<$25k day-trade limit) — different mechanism, similar friction | account-policy constraint |
| 幸存者偏差 / PIT (退市/ST/改名) | survivorship/PIT (delistings, ticker changes, **reverse splits**, halts) | PIT universe snapshots |

### 3.2 Weak / no direct analog (optional enrichment, not core)

- **龙虎榜** (Dragon-Tiger top-trader disclosure) has no daily US equivalent. Nearest substitutes
  (short interest, FTDs, Reg SHO threshold list, dark-pool prints, options flow, Form 4) are delayed
  or different in kind. **Dropped from core**; short-interest/SSR/short-data added later as a
  **meme/squeeze** enrichment.

## 4. Architecture & module layout (greenfield `alpha/`)

```
alpha/
  data/         # L0 — sources + PIT + lookahead firewall
    source.py            # MarketDataSource protocol (+ GuardedSource wrapper)
    alpaca.py            # AlpacaSource: daily bars + news (intraday/halts later)
    calendar.py          # US market calendar (NYSE/Nasdaq)
    firewall.py          # AsOfGuard / LookaheadError (reimplement, market-neutral)
    pit_store.py         # PIT snapshot store (parquet, atomic writes)
    snapshot_source.py   # offline PIT source
    capture.py           # window prefetch → store
  state/market.py        # MarketState, RunnerRung (连板梯队 analog), as-of timestamp
  features/     # L0→L1 — US momentum features (all regime-relative normalized)
    breadth.py           # gainer breadth, halt count, follow-through, risk-on/off effect
    runner.py            # multi-day runner / consecutive up-days / RVOL
    failed_breakout.py   # 炸板 analog (gap-up→red close, fade-from-high)
    relative_strength.py # 弱转强 analog (gap-and-go, VWAP reclaim, ORB hold)
    builder.py           # assemble MarketState
  regime/       # US momentum sentiment-cycle
    cycle.py             # state-machine engine (market-neutral)
    classifier.py        # G_cycle: regime read (per-narrative line + global mother-state)
  universe/     # candidate universe (gainers / gap-ups / high-RVOL / runners), PIT
    stock.py             # StockSnapshot (frozen, PIT)
    universe.py          # build_universe (family-specialized screens)
  harness/      # H=(p,G,K,M) — reimplement clean
    skill.py memory.py doctrine.py
    registry.py store.py snapshot.py manager.py
    metatools.py edit_log.py errors.py regime_label.py   # + immutable-core guard
  agent/        # L2 decision: agent, prompt, parse (hallucination defense), retrieval
  refine/       # inner-loop Refiner: refiner, refiner_prompt, credit, signatures, ops (+ retire-discipline)
  eval/         # walk_forward, trajectory, oracle, return_oracle, scorer, metrics, baselines, decision, fill
  loop/         # inner_loop, compare (HCH/Hexpert/Hmin), run_store
  llm/          # client (protocol + MockLLMClient), anthropic.py (Claude), openai_compat.py (cheap),
                #   config.py (per-role provider selection via env), cache, extract
  config.py
alpha_web/      # FastAPI + HTMX cockpit (research + decision), domain-isolated, single-way dependency
seeds/          # four US playbook families, family-tagged: runner / swing / event / meme
docs/           # FIRST-CLASS English docs: blueprint.md, PROJECT_STATE.md, ROADMAP.md, specs/, plans/
scripts/        # capture_window, smoke_alpaca, smoke_agent, serve_web, sample_run
tests/          # mirror modules, offline (MockLLM + FakeSource)
reference/cn/   # copied CN system — reference during rebuild, DELETED when done
```

**Principles:**
- **Domain-agnostic core reimplemented clean, with tests:** firewall, immutable-core guard,
  meta-tool CRUD discipline, hallucination defenses — proven algorithms, fresh code.
- **Per-role LLM** (`llm/config.py`): Agent=cheap, Refiner=Claude, both behind `LLMClient`.
- **Family-tagged seeds** (`family: runner|swing|event|meme`): all four families in one harness `H`;
  regime classifier + retrieval filter by family. This is how "all four on one engine" works.
- **Daily cadence now, intraday-ready:** `MarketState.as_of` is a `datetime`; the source protocol
  leaves room for intraday bars/halts — no rework to add runner enrichment.
- **Lookahead firewall is law:** inference path (L0–L4) uses only `≤t` info; realized-future oracle
  labels appear **only** in outer-loop relabel and never enter the inference path.
- **SSOT:** regime/phase live on the `s_t` (observation) side, objective and oracle-auditable, never
  written back into `H` by the classifier (avoids the confirmation-bias loop).

## 5. US momentum regime machine

Two-level, like CN: **global mother-state** (speculative risk-appetite) × **per-narrative lines**
(each theme has its own phase). The "轮回/reincarnation" insight ports: washed-out narratives revive
when the cycle turns → drives **dormant-skill revival**.

**Design refinements vs CN (US tape is narrative-fragmented and faster, not market-synchronized):**
1. **Global mother-state is a risk-gate + size multiplier**, not the primary regime; **per-line
   phase drives playbook selection**.
2. **Frontside / backside is a per-line attribute** (scalar), not a 7th state — central to US runner
   trading (on the backside every pop gets sold); coexists with any global state.
3. **Follow-through day is a transition event**, not a dwelt-in state.

| US state | CN analog | Observable daily criteria | Transition → |
|---|---|---|---|
| **Washout / Freeze** | 混沌/冰点 | few gainers, runners failing, IWM down, new-lows high, no follow-through | gappers hold + leader emerges → Recovery |
| **Recovery / First-Green** | 修复启动 | first clean gap-and-go survivors, a day-2 continuation, breadth ticking up | narrative gets multiple movers → Heating |
| **Heating / Ignition** | 情绪回暖/题材启动 | narrative ignites (many tickers up big same day), index FTD, RVOL spikes | lead runner + sympathy basket → Trend |
| **Trend / Momentum** | 主升 | leader new highs daily, sympathy runs, gap-and-go's work, low failed-breakout rate | first big distribution day + no next-day recovery → Distribution |
| **Distribution / Churn** | 震荡/补涨 | choppy, laggards run while leaders churn, failed-breakout rate climbing, risk-off spreading | leader breaks down on volume / blowoff → Exhaustion |
| **Exhaustion / Flush** | 退潮 | leaders + sympathy co-flush, hot ticker dumped, SSR broad | breadth collapses, old leaders stop falling + new narrative stirs → Washout/Reset |

Output: continuous confidence per narrative line + a global risk-gate scalar + per-line
frontside/backside. All criteria objective and oracle-auditable.

## 6. Four playbook seed families

All family-tagged inside one `H`. **Design bias: defense seeds (failure-detectors + taboos) richer
than offense seeds (entry patterns)** — guardrails clear the capability floor faster and are more
durable than entry signals (which decay via alpha-decay), and they counter the CN failure mode where
the Refiner over-pruned on tiny samples.

- **Runner** (low-float, intraday-flavored, daily-proxied now): gap-and-go, first-green-day, day-2
  continuation, halt-resumption momentum, VWAP reclaim, ORB hold, backside/failed-breakout fade.
  *Failures:* parabolic blowoff (黄昏之星 analog), first red day, lower-high-after-halt,
  dilution/offering risk (ATM/shelf), reverse-split pump. *Features:* float, RVOL, gap%,
  consecutive-up-days, halt count.
- **Swing** (mid/large): base breakout (flat/cup), pullback-to-MA (10/20 EMA), RS-leader
  continuation, sector-rotation entry, earnings-gap continuation. *Failures:* failed
  breakout/undercut, distribution-day cluster, leader breakdown. *Features:* RS rank, % from
  52w-high, sector RS.
- **Event/catalyst:** earnings-beat gap continuation, FDA/PDUFA binary, M&A/contract spike, guidance
  raise. **预期差 = surprise vs whisper/consensus.** *Failures:* sell-the-news fade, halt-then-dump.
  *Features:* earnings-calendar proximity, surprise%, catalyst-type tag.
- **Meme/squeeze:** short squeeze (high SI + catalyst), gamma squeeze (options), low-float social
  runner, SSR-day squeeze. *Features:* short-interest%, days-to-cover, borrow fee/availability,
  float, social sentiment (later). *Failures:* squeeze exhaustion, dilution dump, social-euphoria top.

**Shared immutable-core doctrine** (Refiner can never edit): respect the regime (no chasing in
risk-off), same-narrative = one correlated bet (sizing), stop discipline, fill-feasibility, don't
fight SSR, survivorship/PIT awareness, position/loss circuit-breakers.

Seeds bootstrapped from this design + established US momentum knowledge (no US "轮回.docx" required).
User's personal trading notes are an optional high-value **later enrichment pass** (the one thing a
frontier LLM genuinely lacks).

## 7. Data, universe & eval oracle

- **AlpacaSource** implements `MarketDataSource`: daily bars (split-adjusted), news, `/v2/calendar`.
  No ready-made "top gainers" endpoint → **build the universe** by scanning daily bars/snapshots
  across the tradable asset list and ranking. PIT: `capture_window` → `PITStore` (parquet, atomic) →
  `SnapshotSource` offline, all behind `GuardedSource`.
- **Data realities handled explicitly:** reverse splits (store adjusted + raw, detect via corporate
  actions, flag reverse-split-pump); survivorship (delisted tickers only partially available — same
  honest caveat as CN: PIT defends date-lookahead, not survivorship).
- **US universe** (zt-pool analog): screen for big % gainers (regime-relative threshold = a skill),
  gap-ups, high RVOL, multi-day runners, near-52w-high; then family-specialize. `StockSnapshot`
  (frozen, PIT) with honest `None` for missing fields.
- **Features:** regime-relative normalized (no absolute thresholds). `RunnerRung` = (move-tier /
  consecutive-up-days) × count × representative ticker (连板梯队 analog).
- **Eval oracle (firewall-clean — future labels only in relabel, never inference):**
  - **Forward-return oracle** (primary, market-neutral): next-open → t+N-close. Ported from CN.
  - **Pool-category oracle** (US continued/faded/nuked): at t+N, candidate continued (still big
    gainer / new high) / faded (no follow-through) / nuked (failed/crashed below entry), defined on
    the US gainer-universe.
  - **Baselines (Hmin):** "chase the biggest gainer" + "no-trade".
  - **Fill-feasibility:** next-open gapping beyond entry → unfillable (一字板 analog), penalized;
    halt/SSR infeasibility with intraday enrichment.

## 8. LLM (per-role)

`llm/config.py`: roles `{agent, refiner}` resolve provider+model from env (`ALPHA_AGENT_*`,
`ALPHA_REFINER_*`). Providers: `anthropic` (new `ClaudeClient`, latest Claude, JSON via tool-use,
retry/backoff), `openai_compat` (DeepSeek/OpenAI base_url, cheap), `mock` (offline tests). Defaults:
Agent → cheap (Haiku 4.5 or DeepSeek); Refiner → Claude Opus/Sonnet. Deterministic cache for offline
tests. All behind the `LLMClient` protocol.

## 9. Phasing

Each phase = design spec + implementation plan + offline tests, mirroring the CN superpowers
workflow. Greenfield, daily-cadence first.

- **US-0 Foundations:** repo restructure (`reference/cn/` done), Alpaca daily source + calendar +
  firewall + `PITStore` + `SnapshotSource`, `MarketState`, US universe builder. Write the **English
  blueprint** (`docs/blueprint.md`).
- **US-1 Harness + eval:** `H=(p,G,K,M)` reimplemented (containers, 9 meta-tools, persistence,
  immutable-core guard, snapshot/rollback), **seeds v1 (four families, defense-heavy)**, return +
  pool-category oracle, walk-forward, baselines, regime classifier + state machine.
- **US-2 Agent + inner loop:** per-role LLM agent (+ Claude client), Refiner 4-pass CRUD + credit +
  signatures + retire-discipline, inner loop, three-way HCH/Hexpert/Hmin compare. **→ validate HCH
  vs Hexpert on real Alpaca data.**
- **US-3 Web + enrichment:** `alpha_web` cockpit (research + decision); then progressive enrichment:
  runner intraday/halts → meme short-interest/SSR → event earnings calendar → social sentiment.

## 10. Testing

Fully offline (`MockLLMClient` + `FakeSource`). Port the market-neutral regression tests (firewall
lookahead, immutable-core write-guard, hallucination defense). Smoke scripts (`smoke_alpaca`,
`smoke_agent`) hit Alpaca/LLM manually only. Tests mirror modules 1:1.

## 11. Documentation (first-class deliverable)

- `docs/blueprint.md` — authoritative US architecture blueprint (English; the equivalent of the CN
  `架构蓝图`), written in US-0.
- `docs/PROJECT_STATE.md`, `docs/ROADMAP.md` — running state + roadmap.
- `docs/superpowers/specs/` + `plans/` — per-phase.
- `README.md` — public-facing English.
- **Knowledge survives `reference/cn/` deletion:** all design rationale captured in English docs.

## 12. Risks & open questions

1. **Capability floor:** if the base model is too weak, self-evolution adds negative value (CN proof).
   → validate Phase US-2 with a strong Refiner; keep frozen-doctrine shadow + floor-breaker.
2. **Alpha decay + reflexivity:** edges have half-lives; six non-stationarity gates (regime labels,
   decay-weighted stats, dormant revival, alpha-decay monitor, capability-floor fallback,
   OOS/shadow/PIT) carry over.
3. **Self-evolution may only reach parity, not alpha** (CN result). The honest bar for US-2 success is
   "HCH ≥ Hexpert on OOS"; beating frozen seeds is the research frontier.
4. **US data gaps:** survivorship (delisted tickers), reverse-split distortion, no daily 龙虎榜
   analog, free-tier intraday limits. Documented, not silently assumed away.
5. **Narrative fragmentation:** the global regime is a weaker signal than in CN; if per-line
   classification proves noisy on small samples, fall back to global risk-gate + family priors.
6. **Greenfield re-derivation risk:** reimplementing the firewall/immutable-core could reintroduce
   bugs the CN system already fixed → port their regression tests verbatim (market-neutral) first.

## 13. What "done" means for this spec's scope

This spec covers the **full target architecture**; implementation proceeds phase-by-phase (US-0 →
US-3), each with its own plan. The immediate next artifact is the **US-0 implementation plan**.
