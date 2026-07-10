# alpha/ — package map, collisions, current-architecture guards

The detail layer under the root CLAUDE.md (which holds identity + the standing properties).
Everything below describes the CURRENT architecture — when a big refactor lands, rewrite this
file wholesale rather than patching it. Packages are small (~60 lines/file avg).

## How the current shape holds together

- **Dependencies point downward only**: `data→universe→features→state→regime` (perception) →
  `agent` → `eval/sizing/guard` → `refine/loop`, with `harness/` a dependency-free root and
  `meta/converse/arena` above. A shared value object goes in the **lowest layer that needs it**.
- **Known import cycles** (held by lazy imports, *not* enforced): `state↔features`,
  `eval↔sizing`, `refine↔memory`, `eval↔refine`. Never convert a lazy/local import to top-level
  or re-export across these edges — import-time crash no test names.
- **Verdict symmetry**: in `compare_harnesses`, HCH gets a read-only `recall_store`, NEVER the
  `episode_store=` write handle — both arms read one fixed pool; don't "unify".
- **Decorator order**: `SizingPolicy(GuardedPolicy(LLMAgentPolicy))` — guard inner, sizing outer.
- **Eval is verdict-neutral to sizing**: scoring/breaker/stats never read
  `size_tier`/`portfolio`.
- **Fork packets**: `meta/evolution.py::adopt_proposal` lands a fork wholesale only because
  every edit in it passed the gate on a hash-pinned identical base — keep that proof intact.
- First symbols you'll need: `eval/decision.py` (**the** data contract),
  `refine/apply.py::try_apply_op` (**the** edit gate), `state/builder.py::build_market_state`
  (the real assembler), `llm/config.py::make_client` / `data/registry.py::make_source`.

## Package map

**Perception (L0/L1)**

| Package | Owns |
|---|---|
| `data/` | The PIT firewall + sources. `firewall.py` (`AsOfGuard`/`LookaheadError`), `source.py` (`MarketDataSource` Protocol + `FakeSource`/`GuardedSource`), `alpaca.py`, `snapshot_source.py`, `pit_store.py` (atomic parquet), `corp_actions.py` (announce-keyed PIT helpers), `capture.py`, `calendar.py`, `registry.py` (`make_source`). |
| `universe/` | `stock.py` (`StockSnapshot`), `universe.py` (`build_universe` screen + `CandidateUniverse`). |
| `features/` | Breadth/runner/sentiment math. `builder.py` here is a **thin back-compat shim** — the real assembler is `state/builder.py`. |
| `state/` | `market.py` (`MarketState`/`RunnerRung`), `builder.py` (`build_market_state` — the real L1 assembler). |
| `regime/` | `classifier.py` (`GCycle.read` → `RegimeRead`, the read-only `G_cycle`), `cycle.py` (6-phase state-machine seed). |

**The harness (the evolving playbook — a dependency-free root)**

| Package | Owns |
|---|---|
| `harness/` | `H=(p,G,K,M)`: `doctrine.py` (`p`, immutable red-lines), `skill.py`+`registry.py` (`K`), `memory.py` (`M`, lessons w/ `learned_asof`), `state.py` (`HarnessState`), `metatools.py` (**the edit API**), `edit_log.py` (append-only audit + `EditProvenance`), `snapshot.py`+`manager.py` (checkpoint/rollback), `loader.py` (`load_seeds`), `errors.py`, `regime.py` (**phase/family vocabulary** — `CANONICAL_PHASES`). |

**Act + score (L2/L3/L4)**

| Package | Owns |
|---|---|
| `agent/` | `agent.py` (`LLMAgentPolicy.decide` — the act entry), `prompt.py` (render H→prompt), `parse.py` (hallucination defense), `retrieval.py` (budgeted PIT-masked injection). |
| `llm/` | `client.py`/`chat.py` (Protocols + `MockLLMClient`), `config.py` (`make_client(role)`), `anthropic.py`/`openai_compat.py`, `extract.py`. |
| `memory/` | Episodic memory: `episodes.py` (`Episode`, `learned_asof`), `store.py` (`EpisodeStore`, SQLite+FTS5, PIT `for_asof`), `aggregate.py` (`is_episode_taboo`, `TaskStats`). |
| `eval/` | The schema + engine hub. `decision.py` (`Candidate`/`Portfolio`/`DecisionPackage` + `DecisionPolicy` Protocol — **the core data contract**), `walk_forward.py` (engine + `score_decision`), `oracle.py`/`return_oracle.py`/`scorer.py`/`metrics.py`/`trajectory.py`/`contribution.py`/`stats.py`/`baselines.py`, `decision_store.py`/`verdict_store.py`. |
| `sizing/` | L3: `position.py` (`SizeTier`/`size_tier`), `correlation.py`, `portfolio.py`, `policy.py` (`SizingPolicy` decorator). |
| `guard/` | L4: `veto.py` (pure hard-veto rules), `screen.py` (`GuardedPolicy` decorator + data-flag wiring), `stops.py`, `breaker.py`. |

**Self-evolution**

| Package | Owns |
|---|---|
| `refine/` | `apply.py` (`try_apply_op` — **the single edit gate**), `ops.py`, `refiner.py` (4-pass LLM Refiner) + `refiner_prompt.py`, `credit.py`, `signatures.py`, `forge.py` (LLM-free proposer) + `task_forge.py` (operational-K), `conflict.py`. |
| `loop/` | `inner_loop.py` (`InnerLoop` — the self-evolution driver), `compare.py` (`compare_harnesses` verdict harness), `floor_breaker.py` (pure breaker math). |

**Faces**

| Package | Owns |
|---|---|
| `meta/` | The teaching (**Sonia**) side: `sonia_agent.py` (`SoniaAgent.respond`), `agent.py` (`MetaAgent.apply`), `extractor.py` (`extract_ops` — enforced-JSON crystallization, ops-or-`{no_edit,reason}`, never silent), `evolution.py` (fork-and-propose: `run_forked_evolution`/`adopt_proposal`, hash-pinned packets) + `proposal_store.py` (`ProposalQueue`), `reconcile.py` (post-restore derived-state sweep, both faces), `models.py`, `store.py` (`LiveBrainStore`+`SessionStore`), `conflict_store.py`, `prompts.py`, `ingest.py`. |
| `converse/` | The persisted conversational (**Kairos**) side: `session.py` (`converse_project`), `loop.py` (`run_conversation`), `agent.py`, `tools.py`, `approve.py` (`StagedEdit` + `assert_approvable` — the status gate on the live apply path), `registry.py` (`ToolRegistry`), `project.py`, `sqlite_store.py`, `workspace.py`. |
| `arena/` | Kairos's tiered tool surface — see `alpha/arena/CLAUDE.md`. |

(Apps — `alpha_web/` :8100 · `sonia/` :8810 · `workbench/` :8820 · `scripts/` — live at the repo
top, talk over HTTP never imports, and carry their own CLAUDE.mds.)

## Name collisions — disambiguate before you edit

- `agent.py` ×3 — `alpha/agent/` (`LLMAgentPolicy`, the trading act) · `alpha/meta/`
  (`MetaAgent`, gated apply) · `alpha/converse/` (`converse`/`build_converse_registry`).
- `app.py` ×3 — `alpha_web/` · `sonia/` · `workbench/`; each defines `create_app()` + `app`.
- `registry.py` ×3 — `harness/` (`SkillRegistry`/`MemoryStore`) · `data/` (`make_source`) ·
  `converse/` (`ToolRegistry`). Unrelated concepts.
- `store.py` ×2 — `memory/` (`EpisodeStore`) · `meta/` (`LiveBrainStore`+`SessionStore`).
- `build_market_state` ×2 **with different signatures** — `state/builder.py::(universe, day, …)`
  is the real assembler; `features/builder.py::(day, source, …)` is a shim that builds the
  universe then delegates. Live code wants the `state/` one.
- "regime" ×2 — `alpha/harness/regime.py` = phase/family *vocabulary* (`CANONICAL_PHASES`);
  `alpha/regime/` = the *classifier*. The classifier imports the vocabulary, never re-spells
  phase strings.
- reference/spike twins — `reference/cn/` and `spikes/…/_hermes/` contain their own
  `decision.py`/`trajectory.py`/`MarketState`; bare symbol searches hit them. Read-only.

## Terminology bridge (↔ the `../Sonia-Kairos/` design repo)

- **"harness" is a trap.** Here (and in paper 2605.09998) *harness* = the evolvable playbook
  `H` — what the design charter calls the **Body**. The charter's "harness" = Kernel ∪ Body.
  Never mix the senses when reading across repos.
- **Sonia / Kairos are roles:** Sonia = teacher (`meta/` + `sonia/`), Kairos = worker
  (`converse/` + `arena/` + `workbench/`). `LLMAgentPolicy` is an instrument inside the
  co-pilot, not "Kairos" by itself.
- **lowercase `kairos`** in `docs/findings/` and design-repo donor notes = the sibling CN
  legal-agent repo `~/Desktop/self-evolve/kairos` — a different product sharing the name.

*Owner: KairosPan · reviewed 2026-07-10.*
