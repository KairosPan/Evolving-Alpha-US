# CLAUDE.md

Orientation map for AI agents (and humans) working in this repo. Auto-loaded every session,
so it is kept **terse and high-signal** — it states what you must know to edit the right place
safely, and links out for depth instead of duplicating. When the structure below stops matching
reality, update this file (and bump the freshness marker).

> **Freshness:** verified against `main` @ `13ef5ab`, 962 tests. `alpha` v0.0.1.
> Owner: KairosPan · last reviewed 2026-07-09.
> If this drifts from the tree, trust the code and fix this file.

---

## 1. Identity

**Sonia-Kairos-US-Stock** (renamed 2026-07-09; formerly *Evolving-Alpha-US*) — a **self-evolving
US speculative-momentum decision-support co-pilot**, built on the Continual Harness `H=(p,G,K,M)`
two-loop architecture (paper 2605.09998). Each day it screens the market, reads the regime, runs
an LLM agent to produce a ranked `DecisionPackage`, and a Refiner edits the harness's own playbook
(`p`/`K`/`M`) overnight via meta-tool CRUD.

Two named entities (names from the sibling design repo `../Sonia-Kairos/`):
- **Sonia** — the teacher/meta-agent: `alpha/meta/` + the `sonia/` service (:8810). Prose chat;
  edits crystallize only via explicit `extract_ops` and land through the gate after user accept.
- **Kairos** — the worker: the conversational face `alpha/converse/` + its tool surface
  `alpha/arena/`, served by `workbench/` (:8820). The trading decider (`alpha/agent/`) and the
  perception/eval spine are instruments the daily loop and Kairos drive.

**Relationship to the design repo:** live governance CONVERGED to the charter 2026-07-09
(spec `docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md`): the worker
face is **stage-only** (`write_mode="apply"` retired — raises), live self-study
(`refine_live`/`evolve_from_episodes`) **forks + proposes packets** the user adopts/discards in
Sonia (`/proposals`, hash-pinned staleness), rollback **reconciles derived state across BOTH
faces**, and the user holds the charter's second hand (`sonia POST /edit`, `path="user_direct"`).
**Named deviations that remain (recorded, deliberate):** the worker still *proposes* (charter-
Kairos proposes nothing — needs a Sonia-side proposer over worker traces, out of scope);
approvals ride unauthenticated localhost HTTP (single-operator posture; see ROADMAP SSRF item);
`--autonomous` + `ALPHA_UNSAFE_AUTONOMOUS=1` restores pre-pivot in-place evolution (experiments
only); the offline eval harness keeps full machine autonomy inside its trial forks (= the
charter's trial semantics, not a violation). This repo remains the charter's *studied
implementation / donor organ bank*.

**It is a co-pilot. It never submits live orders at any phase. Every `DecisionPackage` requires
explicit human confirmation. Not financial advice.** All eval is **gross** (no cost/slippage,
stated not assumed); a delisting/halt-to-zero scores `return = −1.0`, never silently dropped.

---

## 2. Mental model — the layer spine

Code is organized as a one-directional spine. **Dependencies point downward** (an upper layer
imports lower ones, never the reverse):

```
data → universe → features → state → regime      (L0/L1 perception: PIT-safe market read)
        ↘ harness ↙                                (the H=(p,G,K,M) playbook — a DEPENDENCY-FREE root)
            agent                                  (L2 act: reads H + perception → DecisionPackage)
        eval / sizing / guard                      (L3/L4: score + size + veto the decision)
            refine                                 (inner loop: reads eval evidence, edits H via MetaTools)
            loop                                    (orchestrates agent+eval+refine over time)
        meta / converse / arena                    (Sonia teaching + Kairos face + its tool surface over H)
            apps                                    (alpha_web / sonia / workbench / scripts)
```

**The one rule that prevents most architecture mistakes:** a shared value object goes in the
**lowest layer that needs it**. Putting it in the higher layer is exactly what created the 4 known
import cycles (§5). `harness` imports nothing from other `alpha.*` subpackages — **keep it that way.**

---

## 3. Package map

Everything is under `alpha/` unless noted. All packages are small (~60 lines/file avg).

**Perception (L0/L1)**
| Package | Owns |
|---|---|
| `data/` | The PIT firewall + sources. `firewall.py` (`AsOfGuard`/`LookaheadError`), `source.py` (`MarketDataSource` Protocol + `FakeSource`/`GuardedSource`), `alpaca.py`, `snapshot_source.py`, `pit_store.py` (atomic parquet), `corp_actions.py` (announce-keyed PIT helpers), `capture.py`, `calendar.py`, `registry.py` (`make_source`). |
| `universe/` | `stock.py` (`StockSnapshot` value object), `universe.py` (`build_universe` screen + `CandidateUniverse`). |
| `features/` | Breadth/runner/sentiment math. `builder.py` here is a **thin back-compat shim** — the real assembler is `state/builder.py`. |
| `state/` | `market.py` (`MarketState`/`RunnerRung` value objects), `builder.py` (`build_market_state` — the real L1 assembler). |
| `regime/` | `classifier.py` (`GCycle.read` → `RegimeRead`, the read-only `G_cycle`), `cycle.py` (the 6-phase state-machine seed). |

**The harness (the evolving playbook)**
| Package | Owns |
|---|---|
| `harness/` | `H=(p,G,K,M)`: `doctrine.py` (`p`, immutable red-lines), `skill.py`+`registry.py` (`K`), `memory.py` (`M`, lessons w/ `learned_asof`), `state.py` (`HarnessState`), `metatools.py` (**the edit API**), `edit_log.py` (append-only audit), `snapshot.py`+`manager.py` (checkpoint/rollback), `loader.py` (`load_seeds`), `errors.py`, `regime.py` (**phase/family vocabulary** — `CANONICAL_PHASES`). |

**Act + score (L2/L3/L4)**
| Package | Owns |
|---|---|
| `agent/` | `agent.py` (`LLMAgentPolicy.decide` — the act entry), `prompt.py` (render H→prompt), `parse.py` (hallucination defense), `retrieval.py` (budgeted PIT-masked injection). |
| `llm/` | `client.py`/`chat.py` (Protocols + `MockLLMClient`), `config.py` (`make_client(role)`), `anthropic.py`/`openai_compat.py`, `extract.py`. |
| `memory/` | Episodic memory: `episodes.py` (`Episode`, `learned_asof`), `store.py` (`EpisodeStore`, SQLite+FTS5, PIT `for_asof`), `aggregate.py` (`is_episode_taboo`). |
| `eval/` | The schema + engine hub. `decision.py` (`Candidate`/`Portfolio`/`DecisionPackage` + `DecisionPolicy` Protocol — **the core data contract**), `walk_forward.py` (engine + `score_decision`), `oracle.py`/`return_oracle.py`/`scorer.py`/`metrics.py`/`trajectory.py`/`contribution.py`/`stats.py`/`baselines.py`, `decision_store.py`/`verdict_store.py`. |
| `sizing/` | L3: `position.py` (`SizeTier`/`size_tier`), `correlation.py`, `portfolio.py`, `policy.py` (`SizingPolicy` decorator). |
| `guard/` | L4: `veto.py` (pure hard-veto rules), `screen.py` (`GuardedPolicy` decorator + data-flag wiring), `stops.py`, `breaker.py`. |

**Self-evolution**
| Package | Owns |
|---|---|
| `refine/` | `apply.py` (`try_apply_op` — **the single edit gate**), `ops.py`, `refiner.py` (4-pass LLM Refiner) + `refiner_prompt.py`, `credit.py`, `signatures.py`, `forge.py` (LLM-free proposer) + `task_forge.py` (operational-K proposer), `conflict.py`. |
| `loop/` | `inner_loop.py` (`InnerLoop` — the live self-evolution driver), `compare.py` (`compare_harnesses` verdict harness), `floor_breaker.py` (pure breaker math). |

**Faces**
| Package | Owns |
|---|---|
| `meta/` | The teaching (**Sonia**) side: `sonia_agent.py` (`SoniaAgent.respond`), `agent.py` (`MetaAgent.apply`), `extractor.py` (`extract_ops` — enforced-JSON crystallization, ops-or-`{no_edit,reason}`, never silent), `evolution.py` (fork-and-propose: `run_forked_evolution`/`adopt_proposal` — hash-pinned packets) + `proposal_store.py` (`ProposalQueue`), `reconcile.py` (post-restore derived-state sweep, both faces), `models.py`, `store.py` (`LiveBrainStore`+`SessionStore`), `conflict_store.py`, `prompts.py`, `ingest.py`. |
| `converse/` | The persisted conversational (**Kairos**) side: `session.py` (`converse_project`), `loop.py` (`run_conversation`), `agent.py`, `tools.py`, `approve.py` (`StagedEdit` + `assert_approvable` — the status gate on the live apply path), `registry.py` (`ToolRegistry`), `project.py`, `sqlite_store.py`, `workspace.py`. |
| `arena/` | Kairos's live tool surface (the "activity space"): `contract.py` (`CapabilityTier` T0–T4), `policy.py` (`ActivityPolicy.dispatch` — the single tool choke point, fail-closed), `environment.py` (`InProcessEnv`/`LocalEnv` — advisory, not a kernel boundary), `tools.py`, `builder.py` (`build_arena` — decide/read/write/shell, **no order tool**), `experience.py` (observation-only task episodes). `converse` never imports `arena` (AST-guarded); the workbench injects it via `registry_factory`. |

**Apps (top of repo, not under `alpha/`)** — these talk to each other over **HTTP, not imports**.
| Package | Owns |
|---|---|
| `alpha_web/` | The read-only "Regime Instrument" console (FastAPI+HTMX). `app.py` (`create_app`, ~25 routes), `data_access.py` (brain read + `PHASES`), `sample.py`, `sonia_client.py`/`workbench_client.py`. `python -m alpha_web` → :8100. |
| `sonia/` | The Sonia meta-agent service — owns the **live brain** + gated apply/rollback. `python -m sonia` → :8810. |
| `workbench/` | Kairos's conversational staging service. `python -m workbench` → :8820. |
| `scripts/` | Producers/probes: `capture_window.py`, `capture_broad.py`, `run_verdict.py`, `save_decisions.py`, `save_evolution.py`, `refine_live.py`, `evolve_from_episodes.py`, `scan_tradeable.py`, `smoke_alpaca.py`, `migrate_projects_to_sqlite.py`. |

---

## 4. Name collisions — disambiguate before you edit

A bare filename/symbol is **ambiguous**; always qualify by package:

- **`agent.py` ×3** — `alpha/agent/agent.py` (`LLMAgentPolicy`, the trading act) · `alpha/meta/agent.py` (`MetaAgent`, gated apply) · `alpha/converse/agent.py` (`converse`/`build_converse_registry`).
- **`app.py` ×3** — `alpha_web/` · `sonia/` · `workbench/`. Each defines `create_app()` + `app`.
- **`registry.py` ×3** — `harness/` (`SkillRegistry`/`MemoryStore`) · `data/` (`make_source`) · `converse/` (`ToolRegistry`). Unrelated concepts.
- **`store.py` ×2** — `memory/` (`EpisodeStore`) · `meta/` (`LiveBrainStore`+`SessionStore`).
- **`build_market_state` ×2 (different signatures!)** — `state/builder.py::build_market_state(universe, day, ...)` is the **real assembler**; `features/builder.py::build_market_state(day, source, ...)` is a thin shim that builds the universe then delegates. Live code wants the `state` one.
- **`regime` means two things** — `alpha/harness/regime.py` (phase/family *vocabulary*, owns `CANONICAL_PHASES`) vs the `alpha/regime/` subpackage (the *classifier*). The classifier should import the vocabulary, not re-spell phase strings.
- **reference/spike twins** — `reference/cn/` and `spikes/.../​_hermes/` contain their own `decision.py`/`trajectory.py`/`MarketState` etc. A bare symbol/basename search will hit these. They are **read-only reference; never edit them** (see §7).

**Terminology bridge (↔ the `../Sonia-Kairos/` design repo):**
- **"harness" is a trap.** Here (and in paper 2605.09998) *harness* = the evolvable playbook `H` — what the design charter calls the **Body**. The charter's "harness" = Kernel ∪ Body. Never mix the two senses when reading across repos.
- **Sonia / Kairos** = roles: Sonia = teacher (`alpha/meta/` + `sonia/`), Kairos = worker (`converse/` + `arena/` + `workbench/`). `LLMAgentPolicy` is an instrument inside the co-pilot, not "Kairos" by itself.
- **lowercase `kairos`** in `docs/findings/` and design-repo donor notes = the sibling CN legal-agent repo `~/Desktop/self-evolve/kairos` — a different product that shares the name.

---

## 5. Load-bearing invariants — do NOT "simplify" these away

These rules live in scattered comments; an agent breaks them by "tidying up". They are the
system's crown jewels.

1. **PIT firewall.** No future leakage, ever. Corp actions key on **`announce_date`, never `ex_date`**. Prices are stored **raw/unadjusted**. Windowed features (RVOL, runner) use **trailing-only** bars. Episodes/lessons carry a `learned_asof` PIT key. Four firewall-surface regression tests pin this.
2. **One write-waist.** *Every* brain mutation — LLM Refiner, deterministic `forge`, Sonia teaching, converse, the user's direct hand — flows through `refine/apply.py::try_apply_op` → `harness/metatools.py::MetaTools`, appending exactly one `EditRecord` to the append-only `EditLog`. The one sanctioned composite: `meta/evolution.py::adopt_proposal` lands a fork packet wholesale, but every edit in it passed the gate on a base the content-hash staleness check proves byte-identical to the live brain. Don't add a side channel that mutates `H` directly.
3. **Immutable doctrine core.** Red-line `DoctrineEntry`s reject mutation via `__setattr__`. The edit path enforces this. Don't bypass it.
4. **Read vs write episode handle (verdict symmetry).** In `compare_harnesses`, HCH gets a **read-only `recall_store`**, NEVER the `episode_store=` write handle — so it can't self-write mid-verdict and both arms read the same fixed pool symmetrically. This decoupling is deliberate; don't "unify" them.
5. **Decorator stacking order.** Policies compose as `SizingPolicy(GuardedPolicy(LLMAgentPolicy))` — L4 guard inner (drops vetoed names), L3 sizing outer (sizes the survivors). Order matters.
6. **Eval is verdict-neutral to sizing.** The scoring/breaker/stats path is equal-weighted and never reads `size_tier`/`portfolio`. Sizing enriches the human surface without moving the HCH-vs-Hexpert numbers. Keep it that way.

**Known import cycles** (held together by lazy imports + prose, *not* enforced): `state↔features`,
`eval↔sizing` (a `SizeTier` Literal in the wrong package), `refine↔memory`, `eval↔refine`. **Do not
convert a lazy/local import to top-level, and do not re-export a symbol across one of these edges** —
it reintroduces an import-time crash that no test names.

---

## 6. Commands

```bash
pip install -e ".[dev]"          # base deps; add extras as needed: [live] [web] [sonia]
python -m pytest -q              # full suite — fully OFFLINE (FakeSource), 962 tests, no network/keys

# the four PIT firewall-surface acceptance tests:
python -m pytest tests/data/test_source.py::test_guarded_source_blocks_future_snapshot \
  tests/data/test_corp_actions.py::test_has_reverse_split_pending_pit \
  tests/data/test_snapshot_source.py::test_bars_are_raw_not_future_adjusted \
  tests/universe/test_build_universe.py::test_rvol_uses_only_trailing_bars -v

python -m alpha_web              # read-only console  :8100
python -m sonia                  # meta-agent service :8810  (needs DEEPSEEK_API_KEY, or ALPHA_SONIA_PROVIDER=mock)
python -m workbench              # conversational svc :8820

# producers (need a captured PIT window + LLM keys):
python scripts/capture_window.py 2026-01-02 2026-01-31 snap AAPL MSFT NVDA   # offline PIT snapshot DB
python scripts/run_verdict.py    snap 2026-01-02 2026-03-31 --windows 3      # HCH-vs-Hexpert verdict (temp=0)
```

---

## 7. Conventions & gotchas

- **All English** — code, comments, docs. `reference/cn/` is read-only CN algorithmic reference (deleted when the rebuild is done); `spikes/.../​_hermes/` is a gitignored vendor spike. **Never edit either** — they only exist to read from.
- **Branding vs code names.** Product/doc/UI branding = **Sonia-Kairos-US-Stock**; the import package stays `alpha`, the env prefix stays `ALPHA_*`, pyproject `name` stays `alpha`, and the repo name (GitHub remote + local folder) stays `Evolving-Alpha-US` (decided 2026-07-10 — so the design repo's `../evolving-alpha-us/` pointers stay correct).
- **Frozen pydantic v2** for all value objects. New shared types: pick the lowest layer (§2).
- **Tests mirror `alpha/`** (`tests/<package>/...`) and run fully offline via `FakeSource`/`MockLLMClient`. Eval determinism uses `temperature=0`. Add a test next to the code you change.
- **Config is currently scattered** — ~31 `ALPHA_*`/`APCA_*` env vars are read inline via `os.environ.get(...)` (no central settings module yet). When adding one, grep for siblings; the `./state/brain` default in particular is duplicated across several files. (Centralizing this is a known backlog item.)
- **`reference/cn/`, `spikes/`, `verdict_*`, `snap/`, `state/`, `decisions/`** are reference/scratch/gitignored — not the source you edit.

---

## 8. Where to read more (don't duplicate here)

| Doc | Contents |
|---|---|
| `docs/blueprint.md` | Architecture reference for the perception/eval layers (v1.0, 2026-06-13 — predates the harness/agent build-out, arena, and the three services; `docs/PROJECT_STATE.md` + this file are more current). |
| `docs/PROJECT_STATE.md` | Append-only "what's built" log + locked decisions. |
| `ROADMAP.md` (repo root) | The single live backlog of "what's left". |
| `docs/superpowers/specs/` | Per-feature design specs. `plans/` has the matching implementation plans. |
| `docs/findings/` | Empirical results (e.g. the HCH-vs-Hexpert verdict). |
| memory (`MEMORY.md`) | Cross-session project memory index. |
