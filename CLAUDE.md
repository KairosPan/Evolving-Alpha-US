# CLAUDE.md

Orientation map, kept deliberately small: the spine, the red lines, and pointers. Detail lives
one level down and auto-loads when you work there (progressive disclosure): **`alpha/CLAUDE.md`**
(package map · name collisions · terminology bridge) · `alpha/arena/` · `alpha_web/` · `sonia/` ·
`workbench/` (each service's run/env/gotchas + scoped test command). If this file drifts from the
tree, trust the code and fix this file.

> **Freshness:** `main`, 963 tests · Owner: KairosPan · reviewed 2026-07-10.

## 1. Identity

**Sonia-Kairos-US-Stock** — a self-evolving US-stock decision-support co-pilot, built on the
轮回 doctrine (`../evolving-alpha/轮回.docx`, the CN methodology source) + the Continual Harness
two-loop architecture (paper 2605.09998). Daily: screen → regime read → LLM agent → ranked
`DecisionPackage`; a Refiner edits the playbook `H` overnight via meta-tool CRUD.
Two entities (names from the `../Sonia-Kairos/` design charter): **Sonia** = teacher
(`alpha/meta/` + `sonia/` :8810), **Kairos** = worker (`converse/` + `arena/` + `workbench/`
:8820); the trading decider and the perception/eval spine are their instruments.

**Co-pilot red line: it never submits live orders; every `DecisionPackage` requires explicit
human confirmation; not financial advice.** Eval is **gross** (stated, not assumed); a
delisting/halt-to-zero scores `return = −1.0`, never silently dropped.

Live governance follows the charter (converged 2026-07-09 — worker stage-only, self-study
forks + proposes packets, user direct hand, rollback reconciles both faces). The named
deviations that remain are **recorded and deliberate** — don't "fix" one casually; the ledger is
`docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md` §5.

## 2. The layer spine

Dependencies point **downward only** (an upper layer imports lower ones, never the reverse):

```
data → universe → features → state → regime      (L0/L1 perception: PIT-safe market read)
        ↘ harness ↙                                (H=(p,G,K,M) playbook — a DEPENDENCY-FREE root)
            agent                                  (L2 act: reads H + perception → DecisionPackage)
        eval / sizing / guard                      (L3/L4: score + size + veto the decision)
            refine                                 (inner loop: edits H via the one gate)
            loop                                    (orchestrates agent+eval+refine over time)
        meta / converse / arena                    (Sonia teaching + Kairos face + tool surface)
            apps                                    (alpha_web / sonia / workbench / scripts — HTTP, never imports)
```

**The one rule that prevents most architecture mistakes:** a shared value object goes in the
**lowest layer that needs it**; `harness/` imports nothing from other `alpha.*` packages — keep
it that way. First symbols you'll need: `eval/decision.py` (**the** data contract),
`refine/apply.py::try_apply_op` (**the** edit gate), `state/builder.py::build_market_state`
(the real assembler), `llm/config.py::make_client` / `data/registry.py::make_source`.

## 3. Traps — check before you edit (full tables: `alpha/CLAUDE.md`)

- **Bare filenames/symbols are ambiguous:** `agent.py` ×3 · `app.py` ×3 · `registry.py` ×3 ·
  `store.py` ×2 · `build_market_state` ×2 (different signatures — live code wants
  `state/builder.py`'s) · "regime" ×2 (vocabulary vs classifier).
- **"harness" is a cross-repo trap:** here (and in the paper) it = the evolvable playbook `H` =
  the charter's **Body**; the charter's "harness" = Kernel ∪ Body. And lowercase `kairos` in
  findings/donor notes = the sibling CN legal-agent repo, NOT the worker entity.
- `reference/cn/` + `spikes/` hold twins of core files (`decision.py`, `MarketState`…) that bare
  searches will hit — **read-only, never edit** (enforced by `.claude/settings.json`).

## 4. Load-bearing invariants — do NOT "simplify" these away

1. **PIT firewall.** No future leakage, ever. Corp actions key on **`announce_date`, never
   `ex_date`**; prices stored **raw/unadjusted**; windowed features trailing-only;
   episodes/lessons carry `learned_asof`. Four firewall-surface regression tests pin this.
2. **One write-waist.** *Every* brain mutation — Refiner, `forge`, Sonia teaching, converse, the
   user's direct hand — flows through `refine/apply.py::try_apply_op` → `MetaTools`, appending
   exactly one `EditRecord` to the append-only `EditLog`. The one sanctioned composite:
   `meta/evolution.py::adopt_proposal` lands a fork packet wholesale, but every edit in it
   passed the gate on a base the content hash proves byte-identical to the live brain. Don't
   add a side channel that mutates `H` directly.
3. **Immutable doctrine core.** Red-line `DoctrineEntry`s reject mutation via `__setattr__`;
   the edit path enforces this. Don't bypass it.
4. **Verdict symmetry.** In `compare_harnesses`, HCH gets a **read-only `recall_store`**, NEVER
   the `episode_store=` write handle — no self-writes mid-verdict; both arms read one fixed
   pool. Deliberate decoupling; don't "unify".
5. **Decorator order.** `SizingPolicy(GuardedPolicy(LLMAgentPolicy))` — guard inner (drops
   vetoed names), sizing outer (sizes survivors).
6. **Eval is verdict-neutral to sizing.** Scoring/breaker/stats never read
   `size_tier`/`portfolio`. Keep it that way.

**Known import cycles** (held by lazy imports + prose, *not* enforced): `state↔features`,
`eval↔sizing`, `refine↔memory`, `eval↔refine`. **Never convert a lazy/local import to top-level
or re-export across these edges** — it reintroduces an import-time crash no test names.

## 5. Commands

```bash
pip install -e ".[dev]"          # extras as needed: [live] [web] [sonia]
python -m pytest -q              # full suite — fully OFFLINE (FakeSource), 963 tests, no keys

# the four PIT firewall-surface acceptance tests:
python -m pytest tests/data/test_source.py::test_guarded_source_blocks_future_snapshot \
  tests/data/test_corp_actions.py::test_has_reverse_split_pending_pit \
  tests/data/test_snapshot_source.py::test_bars_are_raw_not_future_adjusted \
  tests/universe/test_build_universe.py::test_rvol_uses_only_trailing_bars -v

python -m alpha_web | sonia | workbench    # :8100 / :8810 / :8820 — run/env details, model-id
                                           #   gotchas, scoped tests: each service's CLAUDE.md
# producers (capture_window → save_decisions / run_verdict / refine_live …): README quickstart
```

## 6. Conventions

- **All English** — code, comments, docs. `reference/cn/` is read-only CN reference; `spikes/`
  is a gitignored vendor spike (edits denied via `.claude/settings.json`).
- **Branding vs code names:** product = Sonia-Kairos-US-Stock; import package `alpha`, env
  prefix `ALPHA_*`, repo name `Evolving-Alpha-US` all stay (decided 2026-07-10).
- **Frozen pydantic v2** value objects; new shared types go in the lowest layer (§2).
- **Tests mirror `alpha/`**, run fully offline (`FakeSource`/`MockLLMClient`, temp=0). Add a
  test next to the code you change.
- **Config is scattered** — ~31 `ALPHA_*`/`APCA_*` env vars read inline; grep for siblings
  before adding one (the `./state/brain` default is duplicated across files). Known backlog.
- `verdict_*`, `snap/`, `state/`, `decisions/` are run artifacts/scratch — not source.

## 7. Where to read more

- `alpha/CLAUDE.md` — package map · collisions · terminology bridge (loads with alpha/* work)
- `docs/blueprint.md` — perception/eval architecture (v1.0, predates harness/arena/services)
- `docs/PROJECT_STATE.md` — append-only what's-built log · `ROADMAP.md` — the single live backlog
- `docs/superpowers/specs/` + `plans/` — per-feature designs · `docs/findings/` — empirical results
- `MEMORY.md` — cross-session memory index
