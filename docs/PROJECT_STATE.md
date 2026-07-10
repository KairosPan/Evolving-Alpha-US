# Sonia-Kairos-US-Stock — Project State

*(formerly Evolving-Alpha-US; project renamed 2026-07-09 — two named entities: **Sonia** the
teacher (`alpha/meta/` + `sonia/`), **Kairos** the worker (`converse/` + `arena/` + `workbench/`).
Doc/UI rebrand shipped 2026-07-09; import package stays `alpha`, env prefix stays `ALPHA_*`;
the repo name — GitHub remote and local folder — stays `Evolving-Alpha-US` by decision
2026-07-10: Sonia-Kairos-US-Stock is product/doc/UI branding only.)*

> **2026-07-09 — CHARTER-CONFORMANCE ARC SHIPPED (branch `feat/charter-conformance`, 962 tests; final 3-lens whole-branch review folded — adopt validates the RESULT not just the base, resolve validates decision, sweeps inside the flock, cross-face test isolation):**
> live governance converged to the `../Sonia-Kairos/` charter per its anti-donor list + the
> verified two-way-alignment findings. (1) Worker face **stage-only** — `write_mode="apply"` +
> `make_gated_write_tool` retired (raise, never silent-downgrade); bare `converse()` decide-only.
> (2) Live self-study **forks + proposes**: `refine_live`/`evolve_from_episodes` default to
> propose mode — full machine autonomy on a FORK (trial semantics; runner returns FINAL handles,
> the in-fork breaker-rollback rebind hazard), no live episode writes, surviving delta packaged
> as an `EvolutionProposal` (content-hash-pinned base) → user adopts/discards via sonia
> `/proposals`; `--autonomous` + `ALPHA_UNSAFE_AUTONOMOUS=1` = recorded pre-pivot escape hatch.
> (3) **Two hands with true provenance**: proposer += `kairos`/`user`, path += `user_direct`
> (`hermes` read-compat); `human_approver` populated at every human-approved landing; new sonia
> `POST /edit` = the user's direct hand (sample floors lifted; structure + red-lines still bind).
> (4) **Revert reconciles derived state ACROSS BOTH FACES** (applied_seqs/staged edits;
> the /propose-409 dead-end fixed) + new `GET /snapshots` / `POST /snapshots/{name}/restore`
> lever. (5) Serialization hardened: `to_dict` json-mode (a gate-landable `learned_asof` date
> crashed every json.dumps consumer — pre-existing latent bug, regression-pinned). Eval/verdict
> byte-neutral (InnerLoop/compare/Refiner untouched). Spec + as-built amendments:
> `docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md` (3-lens adversarial
> review, 2 blockers + 4 majors folded). Named deviations recorded in CLAUDE.md §1.

> **One-page compressed context for session restart.** This file is the append-only record of **what's
> built**; the forward-looking backlog of **what's left** lives in **`ROADMAP.md`** (repo root).
> Last updated: 2026-06-27 (US-0 + US-1 + US-2 complete; US-3a–US-3f shipped — the US-3 daily-cadence enrichment arc is complete; **richer-state perception wired into the live drivers + `LoopConfig.screen` now defaults ON** with a symmetric `compare_harnesses` guard; **`scripts/run_verdict.py` verdict harness built + offline-verified**; **L3 sizing wired into the live DecisionPackage** (size_tier + portfolio, verdict-neutral); **2026-06-22: Alpaca corp-actions data-source wiring — live-verified — + `ALPHA_DATA_SOURCE` multi-source switching + M1/M2 hardening shipped (`main` @ 7945672, 413 tests)**; **2026-06-22: `alpha_web/` "Regime Instrument" web console built** — FastAPI + Jinja2 + HTMX (the documented `alpha_web/` UI), read-only, offline (vendored htmx, no build step); reads the live seeds (doctrine/memory/skills) and renders a `DecisionPackage` + the HCH-vs-Hexpert verdict, real-artifact (`ALPHA_WEB_DECISION`/`ALPHA_WEB_VERDICT`) or a badged SAMPLE built from the real models; signature = the six-phase thermal regime ring; an adversarial 4-lens review (14 verified findings) was folded in (incl. two real `/decisions` 500s on no-trade/baseline packages, now guarded). **Then the entire ROADMAP §6 web-console follow-up arc shipped (every console page now reads real run artifacts): (1) DecisionStore (atomic by-date JSON) + `scripts/save_decisions.py` (act-only producer) + `/decisions` date-browse (`ALPHA_WEB_DECISIONS_DIR`); (2) `run_verdict.py --json` (`comparison_to_view` → console view dict) + VerdictStore + `/verdict` run-browse (`ALPHA_WEB_VERDICTS_DIR`) + null-CI/p/MDE guards; (3) `/evolution` edit-log timeline + `scripts/save_evolution.py` (InnerLoop edit-trajectory dump, `ALPHA_WEB_EVOLUTION`).** Then **ROADMAP §5: L3 correlation netting ACTIVATED (US-5)** — the agent emits a per-candidate `narrative` (sympathy/theme key, finer than `family`); `size_decision` nets same-narrative picks to one bet and surfaces `Portfolio.total_exposure`/`capped` (the "one correlated bet" doctrine is now executable + shown on the Decisions page); verdict-neutral (adversarial review = 0 findings). Per-narrative-line *regime* read still deferred (needs theme-level breadth). 477 tests; remaining/planned work now tracked in `ROADMAP.md`). **Then the §6 PIT episodic-memory arc shipped (specs/plans 2026-06-26/27): episodes written at the credit seam → `EpisodeStore` (SQLite brain.db, `learned_asof` PIT key), PIT-masked recall + episode-taboo capabilities, and the LLM-free `forge` auto-promote/soft-retire proposer (double-gated). Then 2026-06-27: the §6 READ-SIDE FLIPPED ON** (`docs/superpowers/plans/2026-06-27-episode-readside-on.md`, 693 tests) — recall + episode-taboo, both shipped default-off, are now wired into the live decide path (`save_decisions --brain`/`$ALPHA_EPISODES_DB`; `refine_live` reads its own growing brain) **and** the verdict harness via a **read-only `recall_store` threaded symmetrically into both arms** (HCH gets it as `recall_store=`, NEVER the `episode_store=` write handle → no self-write mid-verdict; Hexpert/Hmin via `GuardedPolicy`/`LLMAgentPolicy`). The `for_asof` default-50 cap was lifted (`limit=None`) at the two aggregation read sites so taboo/recall see full PIT history. Additive/default-off (no brain → byte-identical) + PIT-safe (adversarial 4-lens verify, incl. a caught vacuous-test fix). Then the **polish trio shipped (2026-06-27)**: (1) `for_asof` cap audit — only 3 production callers (recall/taboo/forge), all pass `limit=None`; convention documented (default-50 = ad-hoc/display only). (2) `run_conversation` returns a fallback `final_text` on `hit_max_iters` (no silent empty turn). (3) conftest DRY — one shared `brain_session_isolation` fixture (parent conftest) consumed by symmetric autouse fixtures in `tests/web`/`tests/sonia`. The **§8/Phase-1 Hermes-vendoring thread** stays in `ROADMAP.md`. **Then 2026-06-27 — two DESIGN specs (no code yet) for the receiving agent's "activity space" (the inner loop) landed:** `2026-06-27-activity-space-arena-design.md` (the `ActivitySpace` O/A/E/F contract + `ToolEnvironment` seam: `LocalEnv` now / kernel `SandboxedEnv` deferred + capability tiers + the 3-membrane safety model + broad experience coupling under the K/G-only separation invariant) and `2026-06-27-modification-ladder-and-body-axis-design.md` (the two-loop sandbox placement + the modification ladder R1–R6 + the **immutable TCB carve-out** = the moat). **Locked decisions:** the sandbox belongs to the activity loop (gate+TCB guard self-modification); build **NOW = Local, data rungs R1/R2 only**, code-level R3+ designed-for but **deferred** behind a kernel sandbox + immutable TCB + outer verifier + human approval (a gated scope-lift of parent §1.2, recorded there + §5.1). Grounded by a 10-agent adversarial panel (all 4 naive max-modifiability architectures broke at the same seam: a reshapeable gate is a self-amending gate). **Then the NOW phase (P-A) was BUILT + merged to local `main` 2026-06-27 (subagent-driven, 11 TDD tasks, per-task review + final opus whole-branch review = merge-ready; 736 tests = 733+arena, fast-forward `feat/arena-pa`→main @ `26077b2`, NOT pushed):** new `alpha/arena/` package — `contract.py` (`CapabilityTier` T0-T4 / `ExecResult` / `Feedback`), `environment.py` (`ToolEnvironment` seam + `InProcessEnv` + `LocalEnv` — workspace path-guard incl. relative-`../` block + hardline blocklist + `net` documented-no-op), `policy.py` (`ActivityPolicy.dispatch` — the single choke point: fail-closed on any untiered tool + autonomous-T4 block), `tools.py` (read/write/shell over the seam), `builder.py` (`build_arena` — decide T0/read T0/write T1/shell T2/propose_memory_edit T3, NO order tool). Plus: `run_conversation` gained a backward-compatible `dispatch` seam (arena injects its policy without converse importing arena); the two live-face build gaps closed (`make_gated_write_tool` now threads `conflict_queue`+provenance → held branch; `alpha/converse/approve.py::assert_approvable` enforces `StagedEdit.status` before the workbench live apply); and PIT-gated recall threaded into the conversational prompt (delegated to `select_for_prompt`, non-vacuous regression). Data rungs R1/R2 only; R3+ (code-level/body axis) remain deferred per the modification-ladder spec. All 6 safety invariants verified by the final review (single choke-point/fail-closed, one-write-waist, layer spine/no cycle, PIT mask, LocalEnv provisional posture, backward-compat). **Then the LIVE-FACE WIRING shipped + merged to local `main` 2026-06-28 (subagent-driven, 6 TDD tasks + final opus review = merge-ready; 749 tests; fast-forward `feat/arena-live-wiring`→main @ `cb66f3c`, NOT pushed; spec `2026-06-27-live-face-arena-wiring-design.md`):** the live conversational face (workbench → `converse_project`) now routes every tool call through `ActivityPolicy.dispatch` (the choke point is load-bearing on the live path) and exposes the full computer-use catalog (decide/read/write/shell) via a `LocalEnv` pointed at the project git workspace. Done by **dependency injection** — `converse_project` gained an optional `registry_factory` (default `None` = byte-identical old behavior); `build_arena` was generalized (optional workspace; reuses `build_converse_registry`; `write_mode`/`read_only`/`conflict_queue`/`provenance`; explicit tiers exactly mirroring what's registered); the **workbench** (apps layer, may import arena) injects the arena factory + asserts brain-dir-outside-workspace (fail-fast). **Layer spine held: `converse` never imports `arena` (AST guard test).** **USER-ACCEPTED operator-trust posture:** live shell on the non-kernel `LocalEnv` means the one-write-waist is enforced logically (the gate for tool calls) but the brain's *physical* integrity rests on operator-trust (a shell can reach the brain files around the gate) until the kernel `SandboxedEnv` (deferred, commercial). The arena package is no longer a dormant skeleton — it is the live tool surface. **Then P-B + P-C shipped + merged to local `main` 2026-06-28 (subagent-driven, 20 TDD tasks + final opus review = merge-ready; 882 tests; ff `feat/arena-pb-pc`→main @ `1109267`, NOT pushed; spec `2026-06-28-pb-pc-experience-fitness-design.md`, designed+adversarially-verified via an 11-agent workflow):** **P-B** = live-agent **task episodes** (`Episode.kind∈{trade,task}`; `alpha/arena/experience.py::record_task_episode` at the converse turn boundary, injected via `experience_writer` so converse stays arena-free; **observation-only** — never gated/in-`to_dict()`/in-rollback, never touches SkillStats; `for_asof(kind="trade")` default fences task rows from the verdict; verdict-neutral regression pins bit-identical HCH-vs-Hexpert numbers). **P-C** = the second-fitness coupling into **operational K**, behind the **trading-vs-operational classification**: a per-element `domain` tag (Skill/DoctrineEntry/Lesson, default `trading`=fail-closed); a domain-aware gate branch in `try_apply_op` (task-evidence may target ONLY operational H, else reject; set-once + create-path guards close relabel/mint cracks); a **read-side** domain filter so operational elements never enter the trading prompt; a **gate-side task floor** (fail-toward-strict 3-confirmed/0.5-rate, `task_stats=None` fails closed, producer-agnostic — Refiner/Sonia/forge all subject); **confirmed-positive** counting (only externally-confirmed successes promote — agent-authored default-pass never does); a deterministic `task_forge` proposer (promote operational only). **All evolution K + operational doctrine only — G stays a no-op; retire-on-task deferred (no confirmed-failure floor).** The whole feature is **additive/default-off/dormant** (nothing wires `experience_writer`/`task_forge`/`confirmed_ids` live yet) — trade path byte-identical; the merge activates nothing. **Pre-live-activation checklist** (logged): route operational task ops through `conflict_queue`; reject-or-amend operational-M scope; wire `confirmed_ids` resolution; switch the task-episode asof to the pinned logical date. **>>> ALL of the above (every "NOT pushed" item in this paragraph) was PUSHED to `origin/main` 2026-06-28 — `main` @ `23e0dbc`, in sync. The activity-space design specs, the P-A arena, the live-face wiring, and P-B+P-C are all on the remote. (Future pushes still need explicit user authorization.) <<<**

---

## Identity and Boundary

**What it is:** A self-evolving US speculative-momentum **decision-support co-pilot** built on
the Continual Harness `H=(p,G,K,M)` architecture (paper 2605.09998). It produces a
`DecisionPackage` (ranked candidates + plans + rationale + size tier + portfolio risk budget +
fill-feasibility). A human confirms. **No automatic live orders. No financial advice.**

**What it is not:** An order-execution engine, a financial advisor, a static screener, or a
straight copy of the CN system. It is a greenfield rebuild — clean US-native data model,
all-English code and docs.

**Repo:** `KairosPan/Evolving-Alpha-US` (the repo keeps this name — decided 2026-07-10;
`Sonia-Kairos-US-Stock` is product branding), public, clean-slate git history. Branch `main`.

---

## Locked Decisions (Spec §1)

| Decision | Choice |
|---|---|
| Strategy | Greenfield rebuild (US-first), English-only code and docs |
| Data | Alpaca (free key; daily bars + corp-actions now; intraday/halts US-3) |
| Broker | None at this stage (co-pilot only, human-confirmed) |
| LLM | Configurable per-role (Agent cheap, Refiner Claude); `temperature=0` for eval |
| Package name | `alpha` (was `youzi` in CN) |
| Domains | All four families (runner/swing/event/meme) on one engine; per-phase scope differs |
| Sequencing | Daily cadence first; intraday enrichment is US-3 |
| CN code | In `reference/cn/` — reference during rebuild, **deleted when done** |
| Docs | First-class deliverable; knowledge survives `reference/cn/` deletion |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python ≥ 3.11 |
| Data models | pydantic v2 (frozen models for value objects) |
| DataFrames | pandas ≥ 2.0 |
| Storage | pyarrow (parquet, atomic writes via PITStore) |
| Market data | alpaca-py (optional `live` extra; tests run offline) |
| Calendar | pandas-market-calendars (optional `live` extra) |
| Testing | pytest ≥ 8.0 |
| LLM (agent) | Cheap model (Haiku 4.5 or DeepSeek) via `ALPHA_AGENT_*` env vars |
| LLM (refiner) | Claude Opus/Sonnet via `ALPHA_REFINER_*` env vars |
| Web UI | FastAPI + Jinja2 + HTMX — `alpha_web/` "Regime Instrument" console (**built**; `pip install -e ".[web]"` then `python -m alpha_web`) |

---

## Current Milestone: US-0 Foundations

**Status:** Complete (all 14 tasks committed).

### Completed Tasks

| Task | Description | Status |
|---|---|---|
| 1 | Project scaffold (alpha package + pytest) | Done |
| 2 | AsOfGuard lookahead firewall | Done |
| 3 | US trading calendar helpers | Done |
| 4 | MarketDataSource protocol + FakeSource + GuardedSource (firewall surface 1: date-lookahead) | Done |
| 5 | Corporate actions PIT-by-announcement (firewall surface 2: corp-action ex-date) | Done |
| 6 | PITStore (atomic parquet: snapshots/bars/calendar/corp-actions) | Done |
| 7 | SnapshotSource offline source (firewall surface 3: split-vintage raw-PIT) | Done |
| 8 | StockSnapshot + CandidateUniverse | Done |
| 9 | build_universe with trailing-only RVOL (firewall surface 4: windowed-rank) | Done |
| 10 | MarketState + RunnerRung schema | Done |
| 11 | build_market_state (counts + runner echelon) | Done |
| 12 | AlpacaSource adapter + capture_window + smoke scripts | Done |
| 13 | English blueprint + project-state + roadmap + README | Done |
| 14 | US-0 acceptance gate — four firewall-surface tests green | Done |

### US-0 Acceptance Gates (All Green)

- **Surface 1 (date-lookahead):** `GuardedSource` raises `LookaheadError` on future requests.
- **Surface 2 (corp-action ex-date PIT):** split detection keys on `announce_date`, never `ex_date`.
- **Surface 3 (split-vintage raw-PIT):** stored prices are raw; $14 close stays $14, not $140.
- **Surface 4 (windowed-rank trailing-only):** RVOL window uses bars strictly before the request day.

---

## Repo Map

```
alpha/                  # Main package (Python, English, greenfield)
  __init__.py           # version 0.0.1
  data/
    firewall.py         # AsOfGuard, LookaheadError
    calendar.py         # trading_days_between, next/prev_trading_day
    source.py           # MarketDataSource protocol, FakeSource, GuardedSource
    corp_actions.py     # known_corporate_actions, has_reverse_split_pending
    pit_store.py        # PITStore (atomic parquet)
    snapshot_source.py  # SnapshotSource, SnapshotMissingError
    alpaca.py           # AlpacaSource, _normalize_bars, _normalize_snapshot
    capture.py          # capture_window (idempotent prefetch)
  state/
    market.py           # MarketState, RunnerRung
    builder.py          # build_market_state
  universe/
    stock.py            # StockSnapshot, StockStatus
    universe.py         # CandidateUniverse, build_universe, _trailing_rvol
tests/                  # Mirror of alpha/; fully offline (FakeSource)
  data/
    conftest.py         # fake_source fixture
    test_firewall.py    test_source.py    test_corp_actions.py
    test_pit_store.py   test_snapshot_source.py   test_alpaca_normalize.py
    test_calendar.py
  state/
    test_market.py      test_builder.py
  universe/
    test_universe.py    test_build_universe.py
  test_scaffold.py      test_us0_firewall_surfaces.py
docs/
  blueprint.md          # Authoritative US architecture (THIS repo's primary design doc)
  PROJECT_STATE.md      # This file
  ROADMAP.md            # Four-phase roadmap with acceptance gates
  superpowers/
    specs/              # Design spec (2026-06-13-us-market-adaptation-design.md)
    plans/              # Implementation plans per phase
scripts/
  smoke_alpaca.py       # Manual Alpaca probe (needs APCA_API_KEY_ID/SECRET)
  capture_window.py     # Build offline PIT snapshot DB from Alpaca
reference/cn/           # Copied CN system — reference only, DELETE when rebuild complete
pyproject.toml          # Package: alpha 0.0.1; extras: live=[alpaca-py,pandas-market-calendars,openai,anthropic]
README.md               # Public-facing project intro + quickstart
```

---

## US-1 Harness + Eval + Sizing + Guard (sub-plans 1a → 1g)

US-1 ships as a sequence of sub-plans (each its own plan + subagent-driven execution).

**US-1a Harness Core — Complete (2026-06-13).** `alpha/harness/`: Skill/SkillStats/GateSpec,
Lesson/Importance, Doctrine + immutable-core write-guard, SkillRegistry/MemoryStore (query by
phase/family/status/outcome), `HarnessState=(p,K,M)` with to_dict/from_dict round-trip, seed loader.
Read-only load + query. US 6-phase vocabulary (washout/recovery/ignition/trend/distribution/flush) +
family tag (runner/swing/event/meme). Immutable guard pre-verified in pydantic 2.11.7 + survives
round-trip. Adversarial 4-lens plan review folded in before execution. Full suite 70 tests green.

**US-1b Meta-tools + CRUD + EditLog — Complete (2026-06-13).** The harness is now **editable**:
registry/memory/doctrine CRUD + skill lifecycle (retire→dormant/revive/promote, no-op transitions
rejected), `EditLog` (append-only audit, serializable for US-1c), and the **9 meta-tools** (MetaTools
facade) — `write/patch/retire/revive/promote_skill`, `process/update/demote_memory`,
`rewrite_doctrine`. Hardening: rationale required; immutable-core enforced on the edit path;
**reject-don't-log** (rejected edits raise, leave H unchanged, add nothing to the log);
`write_skill` clamps status→incubating + resets stats (no minting active / injecting stats);
observation fields (stats/importance) and identity fields (skill_id/lesson_id, structurally via the
positional param) unpatchable. Full suite 107 tests green.

**US-1c Persistence + rollback — Complete (2026-06-13).** `SnapshotStore` (versioned JSON,
`snap_<NNNN>.json`, atomic temp+`os.replace`, corrupt-load guard, disk-monotonic versioning) +
`HarnessManager` (live `(harness, log, tools, store)`; `checkpoint`/`rollback_to`/`latest_version`;
rollback rebinds `MetaTools` to the restored state). Round-trips `(HarnessState, EditLog)` via the
existing `to_dict`/`from_dict`, so the immutable-core guard survives persistence and `cycle` will
auto-carry once US-1e adds it. Documented hazard: a `mgr.tools` reference cached before a rollback
operates on the discarded state (re-fetch after rollback). Full suite 119 tests green.

**US-1d Eval oracle + scoring — Complete (2026-06-13).** `alpha/eval/`: forward-return oracle
(next-open→t+N-close) with **delisting=terminal-loss** (−1.0, never discarded) + **horizon≥2** guard
(no same-day round-trip); **exogenous** pool-category oracle (fixed GAINER_PCT/LOSER_PCT, decoupled
from the H-evolvable universe screen — kills the circular-oracle bug); pluggable `ReturnScorer`
(primary) / `PoolScorer` (diagnostic) with cross-sectional `advantage` vs the decision-day
gainer-pool baseline; `ScoredCandidate`/`EvalReport`; baselines (NoTrade / ChaseBiggestGainer /
PoolAverage); `WalkForwardEval` (per-day GuardedSource + delayed scoring — firewall by construction).
Baseline-only (no agent yet). Full suite 149 tests green. *Fill-feasibility + cost model deferred to
US-3 (daily entries fill at next-open; hard halt-locked infeasibility needs intraday data).*

**US-1e Regime machine + features — Complete (2026-06-14).** `alpha/features/` (sentiment: raw
composite + regime-relative percentile `sentiment_norm`; breadth: counts / failed-breakout /
gap-and-go / follow-through; runner: trailing `consecutive_up_days` + echelon; full `build_market_state`
enriching the universe with runner depth + features) and `alpha/regime/` (the 6-state US momentum
`StateMachine` — washout/recovery/ignition/trend/distribution/flush; `G_cycle` classifier — **read-only
/ SSOT**, returns a `RegimeRead` of global phase + confidence + frontside/backside + risk-gate, size
multiplier capped when regime context is absent). Trailing-only (firewall-clean); MarketState extended
backward-compatibly. Full suite 174 tests green. *Per-narrative-line phases deferred to US-3 (need
theme tagging); LLM judge calibration → US-2; wiring the full builder into the eval loop → US-2.*

**US-1f Sizing (L3) + Guard (L4) — Complete (2026-06-14).** `alpha/sizing/` (position: confidence×
risk_gate → flat/probe/core/heavy tier; correlation: same-narrative = one bet; portfolio: net
correlated picks + cap total exposure at `risk_gate × max_total`, `total_exposure_budget` matching
DecisionPackage §4.1) and `alpha/guard/` (stops: form/regime/time; veto: no-chase in risk-off **and
on the backside** + reverse-split + data-flag dilution/halt/going-concern/regulatory/SSR; breaker:
single-name / single-day / consecutive-loss / MWCB). The §6 immutable-core rules made executable.
Data-dependent flags (dilution/SSR/halt/MWCB) are forward-plumbed; US-3 supplies them. Full suite
202 tests green.

**US-1g Seeds v1 + DecisionPackage — Complete (2026-06-14).** Enriched `alpha/eval/decision.py` to the
full §4.1 `DecisionPackage` (per-candidate skill_id/entry/exit_stop/size_tier/fill_feasibility/
taboo_check/counterview/family + structured `regime` (RegimeRead) + `as_of` + key_risks + portfolio +
human_confirm), backward-compatible with the US-1d eval contract. Authored `seeds/` v1: 16 skills
(4 families, **defense-heavy 10 detectors > 6 patterns**; squeezes incubating pending US-3 short
data), 8 memory lessons, 12 doctrine (7 immutable red-lines), loaded into `H` via `load_seeds`. Full
suite 216 tests green.

## ✅ US-1 COMPLETE (2026-06-14)

The entire **non-LLM substrate** is in place and tested (216 tests):
data → PIT/firewall (US-0) → harness `H=(p,K,M)` + 9 meta-tools + persistence/rollback (US-1a/b/c) →
eval oracle (return + delist=terminal-loss + exogenous pool, walk-forward) (US-1d) → L1 regime +
features (US-1e) → L3 sizing + L4 guard (US-1f) → full DecisionPackage + 4 defense-heavy seed packs
(US-1g). Firewall sound, immutable-core enforced, baseline-only eval reproduces.

---

## US-2 LLM Agent + Refiner inner loop (sub-plans 2a → 2d)

**US-2a LLM clients + Agent (the "act" half-loop) — Complete (2026-06-14).** `alpha/llm/`: a
provider-agnostic `LLMClient` protocol + `MockLLMClient` (offline replay/record) + `extract_json_object`
(balanced-brace JSON scanner tolerant of prose/markdown fences); `OpenAICompatClient` (DeepSeek/any
base_url) and `ClaudeClient` (Anthropic) — smoke-only real adapters with retry/backoff, lazy SDK
import, and **injectable transport so retry is tested offline** without keys/network; `make_client(role)`
per-role config from env (agent→cheap/deepseek, refiner→Claude; `mock` for tests; `temperature=0` for
eval determinism). `alpha/agent/`: budgeted `retrieval` (active skills phase-prior-hit-first then by
stats; incubating trial slots; lessons by importance weight), `prompt` rendering (doctrine + K + M +
6-state cycle + strict JSON output contract; `build_user_prompt` state+universe), `parse` with
**hallucination defense** (re-anchor every pick to the universe, drop hallucinated/duplicate symbols,
clamp confidence, malformed→no-trade, stamp `as_of`), and `LLMAgentPolicy` (implements `DecisionPolicy`;
**holds `H` and rebuilds the prompt from live `H` each `decide()`** so US-2b Refiner edits are visible
immediately; default budgeted `injection="retrieval"`; threads a **canonical** `phase_prior` extracted
from its prior multi-token `regime_read`). Drives `WalkForwardEval` end-to-end on MockLLM (firewall
holds: the agent only ever sees `(state, universe)`). Adversarial 4-lens plan review folded before
execution (caught: isinstance-vs-non-runtime_checkable Protocol; phase_prior dead under the output
contract; `as_of` never set; retrieval not the default). Full suite **246 tests green**. *Deferred:
record/replay `CachedLLMClient` → later US-2; sizing(L3)/guard(L4) wiring into the DecisionPackage
(size_tier/fill_feasibility/taboo_check) → US-2c; master-dispatch + named G sub-agents collapsed to one
orchestrating agent for v1 (a deliberate spec reduction).*

**US-2b Refiner + evidence substrate — Complete (2026-06-14).** `alpha/eval/trajectory.py` (`TrajectoryStep`/
`Trajectory`; `WalkForwardEval.walk()` captures per-day market+decision+entries+realized outcomes; `run()`
delegates to `walk()`+`report_from_trajectory`, behavior preserved) and `alpha/refine/`: `credit.py`
(`apply_credit` mutates matched skills' `SkillStats` **in place** — Welford running mean on **advantage**
for `expectancy` + raw for `expectancy_raw`, EWMA winrate, `nukes`; `__unattributed__` bucket; cumulative
once-per-trajectory; `merge_credit_reports` read-only; `resolve_skill` id→normalized→name cascade),
`signatures.py` (US-native `faded_miss`/`chased_blowoff`/`weak_laggard_nuke`/`generic_nuke`; degrades to
`generic_nuke` on live walks until runner-tier enrichment lands), `ops.py` (4-pass `('p','G','K','M')` +
per-pass tool whitelist, G reserved no-op; robust `parse_ops`), `refiner_prompt.py` (per-pass system w/
retire+promote discipline + immutable red-lines read-only + strict-JSON contract; shared-evidence user
prompt + edit-history feedback), `refiner.py` (`RefinerConfig` — caps 5/pass, 12/refine, min_retire=5,
min_promote=3; `Refiner.refine()` 4-pass driver, G no-op so exactly **3** live LLM calls; `_apply_op`
evidence gates [retire n≥5; promote n≥3 ∧ expectancy>0] + empty-patch + reject-don't-crash; edits H only
through `MetaTools`; `_recent_reports` deque). The observation/edit boundary holds: credit writes stats
directly (not logged), structural deltas go through the audited `MetaTools`. End-to-end acceptance: agent
walk → credit → signatures → Refiner edits the **seeded** H (mutable doctrine rewritten, immutable
red-line rejected) → audited in `EditLog` → reverted by `HarnessManager` rollback. Adversarial 4-lens
plan review folded (parse_ops non-list crash; inert-taxonomy deferral; empty-patch hardening). Full suite
**274 tests green**. *Edits in place — checkpoint/rollback-on-trip is US-2c.*

**US-2c InnerLoop — Complete (2026-06-15). The loop is alive.** `score_decision()` extracted from
`WalkForwardEval._score` (reusable scoring; behavior preserved). `alpha/loop/floor_breaker.py` — the
**scorer-aware capability-floor breaker** as pure functions (`_mad`, `_fallback_trip`: trip when
`mean(last k) < median − c·MAD` on the per-day **advantage** series, with `floor_abs` as the MAD≈0
backstop; distinct from the `alpha/guard/breaker.py` loss circuit-breaker). `alpha/loop/inner_loop.py` —
`LoopConfig`/`RefineEvent`/`BreakerEvent`/`LoopReport` + `InnerLoop`: one reset-free pass on a single
live `H` interleaving **act → delayed-score → online `apply_credit`** (once per newly-scored step,
cumulative) **→ checkpoint-before-refine → `Refiner.refine()` → breaker**. On a first trip with a
pre-degradation checkpoint → `rollback_to` + `_rebind` (rebuild agent+refiner on the restored `H`,
re-fetch `mgr.tools`/`mgr.harness` — the cached-handle hazard) + re-arm (clear evidence, advance the
refine watermark past the discarded window); second trip / no target → **freeze** (stops credit +
refine, keeps scoring/trajectory). The **fallback (no-shadow)** breaker path only. Adversarial 4-lens
plan review folded (rollback watermark-advance to avoid re-feeding degraded evidence; pass-count fix;
doc/scope clarifications). Full suite **285 tests green**.

**US-2d Compare + shadow breaker — Complete (2026-06-15). The measuring apparatus.** `alpha/loop/floor_breaker.py`
gained `_shadow_eps_abs`/`_shadow_trip` (paired-diff trip: `mean(diff) < −max(λ·σ, ε)` + a negative-day
direction gate). `InnerLoop` gained the **shadow path** (`shadow_daily` ctor param + `breaker_shadow_*`
config + anti-lookahead `d ≤ cur_max` filter; `shadow_daily=None` = the unchanged fallback path).
`alpha/loop/compare.py`: `compare_harnesses` runs the three TIERS HCH/Hexpert/Hmin via **factory injection**
(fresh `H`/client/store per arm — counts 2/2/1/1; Hmin = two floor arms so `len(arms)==4`); `ArmReport`/
`ComparisonReport` with the **excess** verdict `hch_beats_hexpert = (HCH.mean_excess − Hexpert.mean_excess) > 0`;
`daily_advantage` shadow-series helper; `multi_window` noise-aware aggregator (win-rate / sign across
windows). When `shadow=True`, Hexpert runs **first** and its series seeds HCH's paired breaker. Adversarial
4-lens plan review folded (spec-acceptance boundary framing; doc/scope clarifications). Full suite **299 tests green**.

**Honest bar (stated, not yet cleared):** **HCH ≥ Hexpert OOS** — parity is the honest expectation, beating
frozen seeds is the research frontier; a single short-window delta is NOISE (MDE ~0.26). **US-2d builds the
apparatus; the US-2 acceptance GATE remains OPEN** — spec §9/§10 *define* acceptance as the formal
statistical procedure, which US-2d defers.

**US-2e Statistical acceptance — Complete (2026-06-15). The §9/§10 acceptance PROCEDURE is built.**
`alpha/eval/stats.py` — `StatVerdict` + `daily_series`/`paired_daily_diff` + moving-block-bootstrap CI +
sign-permutation p-value + MDE + `verdict`, **deterministic** via local `random.Random(seed)` (CN-pinned
numbers reproduce). `alpha/eval/contribution.py` — offense (pattern/feature) / defense (failure_detector) /
unknown + per-family contribution split, resolved against the **evolved HCH H**. `ComparisonReport.stat_verdict`
+ `.contribution` computed inline in `compare_harnesses`; `multi_window` rolls up a per-window verdict tally
(the temp=0 multi-seed surrogate = multi-window). Adversarial 4-lens plan review folded (a float-equality
test bug; doc-consistency). Full suite **314 tests green**.

**What this does and does NOT mean:** US-2e **closes the §9/§10 acceptance-METHODOLOGY gate** — the formal
decision procedure (paired CI + permutation-p + MDE + offense/defense + per-family + multi-window) is built
and deterministically tested. **The empirical pass/fail verdict is NOT yet rendered** — that needs a **live
temp=0 LLM run on real Alpaca data** (the offline suite validates the *apparatus*; MockLLM ignores prompts).
The honest expectation stays **parity** (HCH ≈ Hexpert); beating frozen seeds is the research frontier.

## US-3 Data enrichment (sub-plans 3a → 3f)

**US-3a Runner-tier enrichment — Complete (2026-06-15). The runner machinery is live on the walk.**
`build_universe` (`alpha/universe/universe.py`) now populates `StockSnapshot.consecutive_up_days` at the
single chokepoint — gainers/gap_ups via a **day-anchored** trailing-bar probe (reusing the one RVOL fetch
per symbol; delegates to the already-tested `alpha/features/runner.py::consecutive_up_days`; returns `None`
when the current-day bar is absent rather than a stale-positive count); losers `0` by construction. This
lights up the whole forward-plumbed cascade on the **live walk** (all three `build_universe` consumers —
`walk_forward`, the US-2c `inner_loop`, and the richer `features/builder`): `MarketState.max_runner_tier`/
`echelon` (the minimal `state/builder.py`), the `chased_blowoff` / `weak_laggard_nuke` failure-signature
taxonomy (`refine/signatures.py` — was always `generic_nuke` on real walks), and the agent prompt's
`up_days` line (`agent/prompt.py` — was always `?`). DRY: the richer `features/builder.py` now reads cud
from the populated universe (dropped the throwaway `model_copy` enrichment + `_lookback_start`). Cascade +
acceptance locks prove it end-to-end (both nuke branches discriminated on populated data) on a seeded-harness
walk; stale "until US-3 enrichment" docstrings refreshed. Full suite **322 tests green**.

**US-3b SSR + reverse-split + guard-veto wiring — Complete (2026-06-15). The dormant L4 veto is live (opt-in).**
The guard `veto()` (zero production call sites until now) is wired via a composable `GuardedPolicy` decorator +
`alpha/guard/screen.py::screen_decision`, fed two PIT-computed flags: **SSR** (`ssr_active` — Reg SHO Rule 201:
a ≥10% prior-day close-to-close decline restricts chasing the name today) and **reverse_split_pending**
(`has_reverse_split_pending`). Resolved the corporate-actions firewall trap with a new PIT-by-announce source
primitive `corporate_actions_known(as_of)` (the ex_date-filtered accessor silently dropped pending future-ex
splits). `screen_decision` drops vetoed candidates (hard override → never entered/scored), surfaces reasons in
`DecisionPackage.key_risks`, and finally populates the structured `regime` (previously always `None` on the live
path). The immutable `dont_fight_ssr` doctrine is activated (seed parenthetical dropped; blueprint SSR row
reconciled to the long-only reading). **Wired OPT-IN, default OFF** (`LoopConfig.screen`): the regime risk-off/
backside arm over-fires on the *minimal* `state/builder` (it feeds `GCycle` `sentiment_norm=None`/
`follow_through=None` → every synthetic day reads backside), so global default-on enforcement waited on wiring the
richer `features/builder` into the live loop — **done 2026-06-16 (see "Richer-state perception wiring" below); `screen` now defaults ON.** The other four veto flags
(`dilution`/`halt_then_dump`/`going_concern`/`regulatory`) stay wired in `veto()` and default `False` (3d/3e/3f
add their data). Known limitation (**resolved 2026-06-16**): `screen` reached only the HCH `InnerLoop` arm — `compare_harnesses` built
Hexpert/Hmin outside `InnerLoop`, so a verdict run had to wrap all arms in `GuardedPolicy` symmetrically before
flipping the default ON; the richer-state slice does exactly this. SSR/reverse-split flags are exact + unit-tested; the full opt-in path is acceptance-
tested end-to-end on a frontside regime. Full suite **339 tests green**.

**US-3c Short-interest + short_squeeze activation — Complete (2026-06-15). The dormant squeeze seed is live.**
`StockSnapshot` gains `short_interest` (% of float) + `days_to_cover`, filled at the `build_universe` chokepoint
from the daily snapshot (the US-3a data-on-snapshot pattern; real FINRA ingestion via capture/Alpaca deferred —
the offline `FakeSource`/`SnapshotSource` mechanism + schema are in place). `build_user_prompt` renders
`si=…% dtc=…` per candidate when present. The activation makes the previously-**decorative** `Skill.depends_on`
**enforced**: `build_system_prompt` (on the live `decide` path, which now supplies `available_data_signals(universe)`
— optional enrichment fields only) surfaces a skill only when every name in its `depends_on` is a live data
signal. So `short_squeeze` (`depends_on=[short_interest, days_to_cover]`) appears to the agent exactly on
short-interest days, and `gamma_squeeze` (`depends_on=[options_flow]`) stays correctly hidden until US-3f.
Enforcement defaults OFF (`available_signals=None`) for non-decide callers, so the suite is untouched. `short_squeeze`
**stays `incubating`** — promotion to `active` is evidence-gated (Refiner on a live run), not declared (lifecycle
discipline; `test_squeeze_offense_is_incubating` pins it). GateSpec threshold gating + a deterministic
`HarnessRulePolicy` consumer are deferred (no live consumer yet). Full suite **351 tests green**.

**US-3d Float + dilution-veto activation — Complete (2026-06-15). The dormant dilution guard is live.**
`StockSnapshot` gains `free_float` (tradeable float, millions of shares), filled at the `build_universe`
chokepoint from the daily snapshot (US-3c data-on-snapshot pattern; real source deferred) and rendered as
`float=…M` in the agent prompt (low-float / dilution-pump context). The L4 `dilution` veto — present in
`veto()` but never set — is **activated**: a new `corp_actions.has_dilution_filing(corp, symbol, as_of)`
(the US-3b reverse-split pattern: PIT-by-announce over `kind ∈ {atm, shelf, offering}`, reusing
`known_corporate_actions`/`corporate_actions_known`) is computed in `screen_decision` from the corp frame it
already fetches, so a candidate with an announced ATM/shelf/offering is dropped with `"dilution / offering /
ATM-shelf"` surfaced in `key_risks`. Conservative MVP: any announced dilution filing vetoes (open-ended
overhang; ex_date/withdrawal lifecycle deferred to a real EDGAR feed). Enforcement stays opt-in via
`GuardedPolicy`/`LoopConfig.screen` (default-off), so the suite is untouched. Acceptance-tested end-to-end on
a frontside regime. Full suite **358 tests green**.

**US-3e Halt-then-dump veto (daily proxy) — Complete (2026-06-15). The last daily-cadence guard flag is live.**
The dormant L4 `halt_then_dump` veto is activated with a **daily-OHLC proxy** (`alpha/guard/screen.py::halt_then_dump_proxy`):
a name whose intraday high spiked ≥15% above its prior close (a likely LULD halt-up) but round-tripped to
close at/below the prior close is a failed spike → vetoed. `screen_decision` fetches the day's snapshot once
(guard-safe) and slots `halt_then_dump=…` into the `CandidateContext` — the US-3b/3d one-line pattern; `veto()`
already fires `"halt-then-dump"`. Distinct from `failed_breakout` (gap-at-open): this keys on the intraday HIGH
spike. Opt-in via `GuardedPolicy`/`LoopConfig.screen` (default-off); suite untouched. **Honestly deferred (need
an intraday feed / new architecture):** real LULD halts + halt-count (tick data); the **MWCB** market-wide
circuit breaker (`alpha/guard/breaker.py::Breaker.set_mwcb` has zero production callers — a portfolio-level loss
breaker needing a P&L state machine + index-crash monitor, not a per-candidate veto; market-wide risk-off is
already covered by the regime arm of `veto()`); and intraday **fill-feasibility**. Acceptance-tested end-to-end
on a frontside regime. Full suite **361 tests green**.

**US-3f Options-flow + social → gamma_squeeze activation — Complete (2026-06-16). The US-3 enrichment arc is closed.**
`StockSnapshot` gains `options_flow` (near-the-money call-flow score) + `social_sentiment`, filled at the
`build_universe` chokepoint from the daily snapshot (US-3c data-on-snapshot pattern; real feeds deferred) and
rendered as `optflow=…`/`social=…` in the agent prompt. Adding `options_flow` (a None-default field whose name
matches `gamma_squeeze.depends_on`) **auto-activates** the last incubating offense seed, `gamma_squeeze`,
through the **generic** `depends_on` enforcement built in US-3c (`available_data_signals` + `_depends_on_satisfied`
+ the `build_system_prompt` filter, fed by `decide`) — **no machinery or seed change**: on an options-flow day
`gamma_squeeze` surfaces to the agent; otherwise it stays hidden (as does `short_squeeze` without short data).
`social_euphoria_top` is `active`/no-`depends_on`, so `social_sentiment` is rendered context (US-3d `free_float`
pattern). `gamma_squeeze` **stays `incubating`** — promotion to `active` is evidence-gated (lifecycle discipline;
`test_squeeze_offense_is_incubating` pins it). With this, **every US-3 daily-cadence enrichment is live**:
runner-tier (3a), the four guard-veto data flags — SSR/reverse-split (3b), dilution (3d), halt-then-dump (3e) —
short_squeeze (3c) and gamma_squeeze (3f). Full suite **367 tests green**. **Honestly deferred:** real
options-flow / social feeds (offline mechanism + schema in place); per-narrative-line phase tagging (a separate
architecture piece — narrative clustering + a per-line regime read; today's `GCycle` returns one global phase).

**Richer-state perception wiring + screen-default-on — Complete (2026-06-16). The L4 guard is always live (and correct, not over-firing).**
The two live drivers (`WalkForwardEval.walk`, `InnerLoop.run`) used the *minimal* `state/builder` (which left
`sentiment_norm`/`follow_through_rate` `None`, so `GCycle` fell back to a low-confidence breadth proxy that read
even a genuine runner as **backside** — the reason US-3b kept `screen` opt-in/default-off). This slice **unifies**
the two builders: `state/builder.build_market_state(universe, day, *, as_of, history=(), prev_gainers=frozenset(),
min_samples=…)` now computes the full feature set (`follow_through` + `sentiment_raw`/`sentiment_norm` +
`gap_and_go`) from the **prebuilt** universe (back-compat defaults reproduce the old minimal output), and
`features/builder` becomes a thin delegating shim (`DEFAULT_MIN_SAMPLES` relocated to the leaf `features/sentiment`
to break the would-be shim cycle). Both drivers thread `history` (append `sentiment_raw`) and `prev_gainers` (prior
gainer set) forward, so a persistent runner gets `follow_through=1.0` ⇒ `GCycle` reads **trend/frontside** ⇒ the
regime veto no longer over-fires. With that fixed, **`LoopConfig.screen` defaults ON**, and `compare_harnesses`
wraps all four non-HCH arms (both Hexpert walks + both Hmin runs) in `GuardedPolicy` when `cfg.screen` — matching
HCH's auto-guard for a fair, symmetric comparison (the prior US-3b "known limitation"). The synthetic runner trips
no data veto (no prior drop → no SSR; close=high>prev → no halt-then-dump; no corp actions), so it is **kept**;
three orthogonal apparatus tests (credit / breaker-freeze / shadow-fallback, which calibrate on a scheduled
advantage series) are pinned `screen=False`. Bootstrap honesty: day 1 has `prev_gainers` empty ⇒ `ft=None` (reads
backside, like the minimal builder) ⇒ a runner reads frontside from **day 2** onward; `sentiment_norm` stays `None`
until `history` reaches `min_samples` (60) — synthetic windows keep the breadth proxy (correct, not a regression).
Adversarial 4-lens plan review folded (the `DEFAULT_MIN_SAMPLES` relocation/cycle; the `test_screen_wiring`
over-fire test breaks on Task 1 not Task 2; an SSR-calendar bug in the acceptance fixture caught during execution).
Acceptance: frontside **keeps** the clean runner AND still **drops** a real SSR name. Full suite **373 tests green**.

**Verdict runner built — Complete (2026-06-16). The harness for the empirical verdict is in place (run needs keys/data).**
`scripts/run_verdict.py` wires a captured PIT source (`SnapshotSource` over a `PITStore`) through
`compare_harnesses`/`multi_window` with per-role **temp=0** `make_client` clients (`ALPHA_LLM_TEMPERATURE`
default 0) and prints the `StatVerdict` + offense/defense/by-family `contribution` + per-arm report. The core
`run_verdict(source, …)` takes any source + injectable LLM factories (tests drive it with MockLLM);
`split_windows` is the temp=0 multi-seed surrogate (independent windows, each ≥ horizon+1 days). `screen`
defaults ON, so all four arms are guarded symmetrically (the production posture from the richer-state wiring).
Offline-verified 6 ways (in-memory, multi-window, on-disk capture→SnapshotSource round-trip, shadow path,
formatters, window-split edges) + a live CLI mock run; holistic review folded the shadow-path test gap. Full
suite **380 tests green**. (Run rendered live 2026-06-22 — next entry.)

**Empirical HCH-vs-Hexpert verdict RENDERED — Complete (2026-06-22). ROADMAP §1 closed.** First live,
deterministic (temp=0) run with **real DeepSeek driving both the agent and the Refiner** over a real Alpaca
**Q1-2026** PIT window (`2026-01-02..2026-03-27`). Universe = a **liquidity-ranked broad 800-name**
cross-section (`scripts/capture_broad.py`: batch multi-symbol bars → rank by dollar-volume → `capture_window`),
because a narrow hand-picked basket makes the breadth-based regime read meaningless. **Result = `flat`
(parity) in BOTH postures:** production (screen ON) HCH +0.0052 vs Hexpert −0.0055 → paired mean_diff +0.0005,
CI [−0.0001, +0.0014], `flat`; raw-skill (screen OFF, new `--no-screen` flag) HCH −0.0090 vs Hexpert −0.0168 →
paired mean_diff +0.0043, CI [−0.0027, +0.0085], `flat`. HCH ≈ Hexpert (leans marginally positive, inside
noise) — the CN §1 "self-evolution net-neutral, not harmful" conclusion reproduces on US data, and HCH never
degrades below frozen (the self-relative capability breaker froze HCH at 2026-02-10 in the screen-OFF run when
it began to slip). Surfaced an **A-share→US transfer gap**: GCycle's `follow_through_rate≥0.4` frontside test
is the 连板 signature (rare in the US) → 35/59 days read backside → the production posture trades thin (now a
ROADMAP §1 follow-up). Hmin_chase's screen-OFF +0.35 is one **reverse-split RAW-print artifact** (SOXS
2026-03-03 +1936%, median −0.005), which screen-ON's reverse-split veto correctly drops — agent arms
uncontaminated. Console JSON written (`verdict_screenON.json` / `verdict_screenOFF.json`). Full method +
numbers + caveats: **`docs/findings/2026-06-22-us-hch-vs-hexpert-verdict.md`**. (Keys live only in gitignored
`.env.alpaca` / `.env.deepseek`.)

**L3 sizing → live DecisionPackage — Complete (2026-06-16). The §4.1 decision surface is now sizing-complete.**
The built-but-unwired L3 sizing layer (`alpha/sizing/{position,correlation,portfolio}.py`, US-1f) is now on the
live path via a composable `SizingPolicy` decorator (`alpha/sizing/policy.py`) mirroring the L4 `GuardedPolicy`:
`size_decision(decision, *, state)` assigns each candidate a `size_tier` (`flat/probe/core/heavy` from
`confidence × (decision.regime or GCycle().read(state)).risk_gate`) and attaches the `Portfolio` plan
(`total_exposure_budget = risk_gate × max_total`, correlated groups). Composed `SizingPolicy(GuardedPolicy(base))`
in `InnerLoop._rebind` so it sizes the **post-veto survivors** (portfolio reflects only kept names); the
`compare_harnesses` `_guard` helper became `_wrap` (L4 guard inner, L3 sizing outer) across all four non-HCH
arms. `LoopConfig.size` defaults ON. **Verdict-NEUTRAL (independently verified):** the entire
scoring/breaker/stats/contribution path is equal-weighted and never reads `size_tier`/`portfolio`, so this
enriches the human-confirmation surface (+ the DAgger record) **without changing the HCH-vs-Hexpert numbers** —
acceptance proves the per-step advantages are identical with sizing on vs off; **zero existing tests changed**.
Firewall-clean (reads only the in-hand decision + state). **Honest deferrals:** correlation **netting** is
wired but dormant until narrative/theme tagging supplies the key (the narrative key is `candidate.family`,
which the agent does not set yet → `""` → each name is its own bet, `correlated_groups` empty — the US-3f
`depends_on` pattern); `fill_feasibility` (no `eval/fill` module — needs the intraday inference path) and
per-candidate `taboo_check` (the guard drops vetoed candidates rather than soft-annotating kept ones) stay
deferred. Adversarial 4-lens plan review (0 blocking architectural issues; folded the one real item — a
planted-broken acceptance `_run` helper). Full suite **387 tests green**.

**Phase-1 Hermes-vendoring completion (D1/D2/D3) — Complete (2026-06-27). The two named-open §8/Phase-1 follow-ups + the deferred SQLite session piece are closed.**
Three disjoint deliverables (spec `docs/superpowers/specs/2026-06-27-phase1-hermes-vendoring-completion-design.md`, plan
`docs/superpowers/plans/2026-06-27-phase1-hermes-vendoring-completion.md`). **D1 — reference-vendor the clean leaf:**
committed `third_party/hermes/{tools/registry.py, LICENSE, PROVENANCE.md}` — the Phase-0-proven clean eager leaf
(`tools/registry.py`, 589 LOC, no `agent/` drag), verbatim from pinned Hermes SHA `5add283ec8e7a33110a9051179208bd50bda427c`,
as the audited schema source-of-truth; the **active** path stays the 28-LOC `alpha/converse/registry.py` reimpl. A
`tests/converse/test_registry_parity.py` proves (a) the vendored leaf imports standalone with NO non-stdlib top-level import
(the narrow-waist claim) and (b) the reimpl honors the vendored registry's tool-calling schema contract (name-keyed register →
schema-by-name → dispatch-by-name). Not imported in production. **D2 — replace JSON `ProjectStore` with SQLite + FTS5:**
new `alpha/converse/sqlite_store.py::SqliteProjectStore` (`state.db` — relational `projects` envelope + normalized `messages`
rows + an `messages_fts` FTS5 **trigram** virtual table, with a runtime probe + `unicode61` fallback) behind the **identical**
`get/put/delete/list` interface, plus a new `search()` FTS message-search capability and a one-time
`scripts/migrate_projects_to_sqlite.py` (idempotent JSON→SQLite upsert). All seven `Project` fields round-trip; `list()` keeps
the JSON store's exact `ORDER BY project_id DESC`; `project_id` is now a bound SQL param (the JSON `_path` traversal guard
disappears). `converse_project` + `workbench` (`ALPHA_PROJECTS_DB`) + their tests rewired; the JSON `alpha/converse/store.py`
and its dedicated traversal test deleted. **The persistence backend swap is the ONLY existing-code behavior change** — the
converse/workbench/web suites pass unchanged against SQLite. **D3 — reframe the parent spec + record state:** parent spec
§8 table rows (registry → REFERENCE-VENDOR pinned `5add283e`; loop → REIMPLEMENTED `alpha/converse/loop.py`; SQLite sessions
→ REIMPLEMENTED SCHEMA `alpha/converse/sqlite_store.py`, not a code-level vendor of `hermes_state.py`) + the §8
upstream-tracking "Open" → **RESOLVED: hard-pin `5add283e`, do not track upstream** (re-run the spike's `coupling.py` as a
gate before any deliberate bump) + §9 Phase-1 done-criteria (messages persist to SQLite + FTS5; registry reimplemented with
the leaf reference-pinned) + the header §8 bullet + a §2.1 layer-diagram parenthetical, all reframed to the Phase-0
NUANCED-GO reality; the consistency pass also resolved the two stale §8-Open references in §10 (risks 10/11 + the consolidated
Open list). Full suite **704 tests green** (693 → +13 new [parity 3 + sqlite_store 8 + migrate 2] − 2 deleted JSON-store cases);
trigram tokenizer active on this runtime (sqlite 3.50.2), `unicode61` the documented fallback. The §8/Phase-1 Hermes thread is
now closed; remaining backlog stays in `ROADMAP.md`.

**Next (orthogonal)** — *the live, maintained backlog now lives in `ROADMAP.md`; the list below is the
2026-06-16 snapshot, kept as history*: execute the verdict run above once keys + a captured window are available (the only
remaining step to render the long-promised empirical HCH-vs-Hexpert number); then per-narrative-line phases.
**Deferred §10 methodology** (gate-non-blocking):
purged & embargoed CV; regime-stratified eval. **Other deferred:** real options-flow / social-sentiment feeds +
per-narrative-line phase tagging (narrative clustering + a per-line regime read; today's `GCycle` is global);
real LULD halts / halt-count (intraday tick
feed) + MWCB / `Breaker` portfolio wiring (P&L state machine + index-crash monitor) + intraday fill-feasibility
(size-at-offer); a real EDGAR/SEC offerings feed (the offline
corp-actions dilution mechanism + schema are in place) + the dilution-filing withdrawal/expiry lifecycle +
float-based L3 sizing (size_tier is wired; share-count sizing off float needs the float feed); Hcredit (C4)
ablation arm; master-dispatch G sub-agents (keeps the `G`-pass a reserved
no-op); keep-last-K checkpoint pruning.

---

## Common Commands

```bash
# Install (no venv needed; pytest/pandas/pydantic/pyarrow already present)
python -m pip install -e ".[dev]"

# Run all tests
python -m pytest -q

# Run only firewall-surface acceptance tests
python -m pytest tests/data/test_source.py::test_guarded_source_blocks_future_snapshot \
  tests/data/test_corp_actions.py::test_has_reverse_split_pending_pit \
  tests/data/test_snapshot_source.py::test_bars_are_raw_not_future_adjusted \
  tests/universe/test_build_universe.py::test_rvol_uses_only_trailing_bars -v

# Smoke Alpaca (needs APCA_API_KEY_ID + APCA_API_SECRET_KEY)
python scripts/smoke_alpaca.py AAPL 2026-06-01 2026-06-12

# Build offline PIT snapshot DB
python scripts/capture_window.py 2026-06-01 2026-06-12 snap AAPL MSFT NVDA

# Render the empirical HCH-vs-Hexpert verdict at temperature=0 (needs APCA + LLM keys + a captured PIT DB)
export ALPHA_AGENT_PROVIDER=openai_compat ALPHA_AGENT_MODEL=deepseek-chat        # + DEEPSEEK_API_KEY
export ALPHA_REFINER_PROVIDER=anthropic   ALPHA_REFINER_MODEL=claude-sonnet-4-6  # + ANTHROPIC_API_KEY
python scripts/run_verdict.py verdict_pit 2026-01-02 2026-03-31 --windows 3

# Serve the Regime Instrument web console (read-only; offline; http://127.0.0.1:8100)
python -m pip install -e ".[web]"
python -m alpha_web
# optionally render real artifacts instead of the SAMPLE:
ALPHA_WEB_DECISION=decision.json ALPHA_WEB_VERDICT=verdict.json python -m alpha_web

# Produce real console artifacts from a captured window, then browse them (needs LLM keys)
python scripts/save_decisions.py verdict_pit 2026-01-02 2026-01-31 decisions   # DecisionPackage per day
python scripts/run_verdict.py    verdict_pit 2026-01-02 2026-01-31 --json verdict.json   # verdict view dict
python scripts/save_evolution.py verdict_pit 2026-01-02 2026-01-31 evolution.json   # Refiner edit trajectory
ALPHA_WEB_DECISIONS_DIR=decisions ALPHA_WEB_VERDICT=verdict.json ALPHA_WEB_EVOLUTION=evolution.json python -m alpha_web
```
