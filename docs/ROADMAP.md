# Evolving-Alpha-US — Roadmap

> **Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md`
> **Blueprint:** `docs/blueprint.md`
> **Updated:** 2026-06-13

---

## Overview

Four phases, each with an implementation plan, offline tests, and explicit acceptance gate. Each
phase is strictly OOS: what US-2 validates is the inner loop only (not the outer loop); what US-1
validates is baselines + infrastructure (not the agent). The scope boundary is real; passing a
phase gate does not imply the next phase's claims.

| Phase | Status | Key deliverables | Acceptance gate |
|---|---|---|---|
| **US-0** Foundations | **Complete** | Data layer, firewall, PITStore, universe builder, MarketState, English docs | Four firewall-surface tests green; universe reproduces offline |
| **US-1** Harness + eval + sizing + guard | Planned | H=(p,G,K,M), seeds v1, return oracle, walk-forward, baselines, sizing, guard | Firewall no-leak + baselines reproduce + sizing/guard unit-tested |
| **US-2** Agent + inner loop | Planned | LLM agent, Refiner 4-pass CRUD, inner loop, three-way compare | Statistical decision procedure: HCH vs Hexpert, CI, temp=0 |
| **US-3** Web + enrichment | Planned | alpha_web cockpit, intraday, short data, social, cost model | Enrichment gates per-family |

---

## Phase US-0: Foundations

**Status: Complete.** All 14 tasks committed on branch `us-0-foundations`.

### Goals

Build the data + point-in-time + lookahead-firewall foundation with an offline-testable universe
builder and the four firewall-surface regression tests.

### Task List

| Task | Description | Commit |
|---|---|---|
| 1 | Project scaffold (alpha package + pytest) | `US-0 Task 1: project scaffold (alpha package + pytest)` |
| 2 | AsOfGuard lookahead firewall | `US-0 Task 2: AsOfGuard lookahead firewall` |
| 3 | US trading calendar helpers | `US-0 Task 3: US trading calendar helpers` |
| 4 | MarketDataSource protocol + FakeSource + GuardedSource | `US-0 Task 4: MarketDataSource protocol + FakeSource + GuardedSource (firewall surface: date-lookahead)` |
| 5 | Corporate actions PIT-by-announcement | `US-0 Task 5: corporate actions PIT-by-announcement (firewall surface: corp-action ex-date)` |
| 6 | PITStore (atomic parquet) | `US-0 Task 6: PITStore (atomic parquet: snapshots/bars/calendar/corp-actions)` |
| 7 | SnapshotSource + split-vintage raw-PIT test | `US-0 Task 7: SnapshotSource offline source (firewall surface: split-vintage raw-PIT)` |
| 8 | StockSnapshot + CandidateUniverse | `US-0 Task 8: StockSnapshot + CandidateUniverse` |
| 9 | build_universe with trailing-only RVOL | `US-0 Task 9: build_universe with trailing-only RVOL (firewall surface: windowed-rank)` |
| 10 | MarketState + RunnerRung schema | `US-0 Task 10: MarketState + RunnerRung schema` |
| 11 | build_market_state | `US-0 Task 11: build_market_state (counts + runner echelon)` |
| 12 | AlpacaSource adapter + capture + smoke scripts | `US-0 Task 12: AlpacaSource adapter + capture_window + smoke scripts (pure normalizers tested)` |
| 13 | English blueprint + project-state + roadmap + README | `US-0 Task 13: English blueprint + project-state + roadmap + README` |
| 14 | US-0 acceptance gate | `US-0 Task 14: acceptance gate — four firewall-surface tests green` |

### Acceptance Gates (All Met)

1. **Date-lookahead firewall:** `GuardedSource` raises `LookaheadError` when requested date >
   as-of cursor. Test: `tests/data/test_source.py::test_guarded_source_blocks_future_snapshot`.
2. **Corp-action ex-date PIT:** `has_reverse_split_pending` detects by `announce_date ≤ as_of`,
   never by the future `ex_date`. Test: `tests/data/test_corp_actions.py::test_has_reverse_split_pending_pit`.
3. **Split-vintage raw-PIT:** bars returned from `PITStore` are raw/unadjusted — $14 stays $14,
   not future-split-rebased to $140. Test: `tests/data/test_snapshot_source.py::test_bars_are_raw_not_future_adjusted`.
4. **Windowed-rank trailing-only:** RVOL denominator uses only bars strictly before the target
   day (calendar days `< day`); today's volume never enters the denominator.
   Test: `tests/universe/test_build_universe.py::test_rvol_uses_only_trailing_bars`.

---

## Phase US-1: Harness + Eval + Sizing + Guard

**Status: Planned.**

### Goals

Ship the infrastructure for strategy self-evolution without yet running an agent. Validate that the
data/eval/guard pipeline is sound against baselines before adding LLM-powered decisions.

### Key Deliverables

- **`harness/`:** `H=(p,G,K,M)` containers, 9 meta-tools (create/read/update/delete/list for each
  of p/G/K/M), persistence (JSON + parquet), immutable-core guard (Refiner cannot edit the
  hard-veto doctrine / firewall / immutable-core itself / oracle interface), snapshot/rollback,
  registry, store, regime_label, edit_log.
- **Seeds v1 (four families):** defense-heavy (failure-detectors + taboos richer than offense seeds)
  + alpha-production channel (offense seeds can be promoted via incubation tournament). Per-phase
  scope per spec §6: Swing fully functional; Runner/Event/Meme defense + daily proxies.
- **Return oracle:** `eval/return_oracle.py` — next-open → t+N-close, horizon ≥ 2 enforced
  (`entry == exit` raises). Delist/halt-to-zero → terminal loss (return = −1.0, never dropped).
- **Walk-forward + baselines:** `eval/walk_forward.py`, baselines `Hmin` ("chase biggest gainer")
  and "no-trade".
- **Regime classifier + state machine:** `regime/cycle.py`, `regime/classifier.py`. G_cycle is
  read-only (SSOT); phase lives on `s_t`, never written back into `H`.
- **`sizing/` (L3):** `position.py` (confidence → size-tier: flat/probe/core/heavy + single-name
  risk budget), `correlation.py` (same-narrative = ONE correlated bet; exposure netting),
  `portfolio.py` (total exposure vs global risk-gate; batching/scale-in).
- **`guard/` (L4):** `stops.py` (form/regime/time stop-loss with veto power), `veto.py`
  (dilution/offering/ATM-shelf, halt-then-dump, going-concern, regulatory hard veto), `breaker.py`
  (single-name/single-day/consecutive-loss circuit breaker; MWCB awareness).
- **`DecisionPackage` schema:** `state/decision.py` (frozen; includes size_tier, fill_feasibility,
  taboo_check, portfolio fields).

### Acceptance Gate

- All existing firewall-surface regression tests still green.
- Baselines reproduce deterministically (multi-seed, temp=0 equivalent for baselines).
- Sizing/guard unit-tested (position sizing math, correlation grouping, veto conditions).
- Walk-forward runs end-to-end on `FakeSource` and emits per-family metrics.
- No agent yet — US-1 acceptance is infrastructure-only.

---

## Phase US-2: Agent + Inner Loop

**Status: Planned.**

### Goals

Add the LLM-powered agent and Refiner. Validate that the inner loop (self-editing harness)
demonstrably improves over a frozen-expert harness on out-of-sample data, using a rigorous
statistical decision procedure.

### Key Deliverables

- **`llm/`:** `LLMClient` protocol, `MockLLMClient` (offline tests), `AnthropicClient` (Claude,
  JSON via tool-use, retry/backoff), `OpenAICompatClient` (DeepSeek/OpenAI base_url, cheap),
  `config.py` (per-role provider + model; `temperature=0` for eval), deterministic cache.
- **`agent/`:** master-dispatch orchestrator + named G sub-agents (leader/relay identifier,
  theme/narrative miner, expectation-gap evaluator, `G_risk` dispatch, fill-feasibility dispatch).
- **`refine/`:** Refiner 4-pass CRUD (`p → G → K → M`), credit assignment, failure-signature
  detection, retire-discipline (alpha-decay monitor → downweight/retire underperforming skills).
- **`loop/`:** inner loop (scorer-aware capability-floor breaker), three-way HCH/Hexpert/Hmin
  compare, run_store.
- **`eval/`:** fill-feasibility on inference path (`eval/fill`), alpha-decay monitor
  (`eval/alpha_decay.py`), full scorer, decision-eval, per-family reporting.

### Acceptance Gate

**Statistical decision procedure (not a bare mean sign):**
- Multi-seed runs (≥ N seeds per arm, N determined by MDE analysis).
- Paired HCH − Hexpert with confidence interval; MDE < expected effect.
- `temperature=0` throughout for eval reproducibility.
- Report offense-vs-defense contribution split.
- Passing this gate means: "self-editing harness ≥ frozen-expert harness on OOS". It does **not**
  mean the outer loop (θ training) converges — that is US-3 scope.

---

## Phase US-3: Web + Enrichment

**Status: Planned.**

### Goals

Ship the `alpha_web` decision cockpit and progressively unlock full offense for each family as
their specific data sources become available.

### Key Deliverables

- **`alpha_web/`:** FastAPI + HTMX cockpit. Two surfaces: research (explore universe, regime,
  skill library) and decision (view `DecisionPackage`, confirm/reject/modify, DAgger label).
  Domain-isolated from `alpha/` (single-way dependency). `scripts/serve_web.py` entry point.
- **Runner intraday:** halt-resumption auction data, VWAP-reclaim exact mechanics, ORB (first-N-min
  range break), real-time halt count per session.
- **Meme/squeeze data:** FINRA daily short-sale volume files (next-morning, free, per-symbol),
  Reg SHO daily threshold-securities list, short interest (bi-monthly), borrow rate, SSR flag.
- **Event/catalyst full:** earnings calendar proximity, consensus/whisper estimates, FDA calendar,
  surprise% vs consensus.
- **Social sentiment:** social data ingestion pipeline (US-3 enrichment, not core).
- **Cost/slippage model:** `eval/cost.py` — net expectancy = gross − estimated cost/slippage.
  For low-float runners, spreads are first-order; stated as an assumption, not ignored.

### Acceptance Gate

Per-enrichment gates; each family's full offense is gated on its data source being available and
tested offline. The web cockpit ships independently of the enrichment gates.

---

## Design Principles (Invariant Across All Phases)

1. **Lookahead firewall is law.** `GuardedSource` wraps every dated fetch. Four regression tests
   must stay green. No exceptions.
2. **Immutable-core guard.** The Refiner can never edit: hard-veto doctrine, the firewall, the
   immutable-core guard itself, or the oracle interface. These are the survival constraints.
3. **SSOT for regime.** `G_cycle` is read-only. Phase lives on `s_t` (observation side), never
   written back into `H`.
4. **Raw/PIT prices.** `PITStore` stores raw OHLCV. Level features use point-in-time raw prices.
   Return ratios are split-invariant within a slice (no rebasing needed for labels).
5. **Delist = terminal loss.** Never dropped from eval, never labeled `faded`. Scored as −1.0 (or
   documented haircut).
6. **Gross expectancy is not tradeable edge.** Cost/slippage model is a US-3 enrichment; all
   pre-US-3 eval is clearly marked GROSS.
7. **Human confirmed.** `DecisionPackage` requires explicit human confirm/reject/modify. No
   automatic order submission at any phase.
8. **All English.** Code, comments, and documentation are English. `reference/cn/` is read-only
   reference, not production code.
