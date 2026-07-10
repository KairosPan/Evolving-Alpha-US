# CLAUDE.md

Descriptive, not prescriptive: when this file disagrees with the tree, the code is current and
this file gets updated. This is the only CLAUDE.md — depth lives in docstrings and `docs/`.

> Owner: KairosPan · reviewed 2026-07-10 · 963 offline tests.

## What this is

**Sonia-Kairos-US-Stock** — a self-evolving US-stock decision-support co-pilot: the 轮回
doctrine (`../evolving-alpha/轮回.docx`) on the Continual Harness two-loop architecture (paper
2605.09998). Daily: screen → regime read → LLM agent → ranked `DecisionPackage` for explicit
human confirmation — no order-submission path exists anywhere (the arena's no-order-tool rule
is test-pinned). A Refiner evolves the playbook `H` overnight. Two charter entities
(`../Sonia-Kairos/`): **Sonia** the teacher, **Kairos** the worker. Code, comments and docs are
English; the CN material is reference only.

## Map

| Where | What |
|---|---|
| `alpha/data`→`universe`→`state`→`regime` | perception: PIT-guarded sources → daily screen → `MarketState` → `GCycle` six-phase read |
| `alpha/harness` | the evolvable playbook `H` itself — doctrine/skills/memory, meta-tools, append-only edit log, snapshots. Not a test harness; the charter calls it the Body |
| `alpha/refine` | proposes and gates edits; `apply.py::try_apply_op` is THE write-waist |
| `alpha/agent` · `eval` · `sizing` · `guard` | decide & score: LLM policy → L4 hard veto → L3 sizing → honest walk-forward eval |
| `alpha/loop` | `InnerLoop` (live-H day driver, capability breaker) + the 4-arm HCH-vs-Hexpert verdict |
| `alpha/llm` | the LLM seam: `make_client(role)`, `MockLLMClient`; roles agent/refiner/sonia/converse |
| `alpha/memory` | PIT episodic memory (`EpisodeStore`, SQLite `brain.db`) — distinct from `alpha/harness/memory.py` (H's lessons) |
| `alpha/meta` + `sonia/` | **Sonia** teaching service :8810 — prose chat → explicit `extract_ops` → preview → gated apply |
| `alpha/converse` + `arena` + `workbench/` | **Kairos** worker face :8820 — tiered computer-use tools; the agent only stages edits, user approval lands them through the same gate |
| `alpha_web/` | read-only "Regime Instrument" console + teach cockpit :8100 |
| `scripts/` | CLI producers (capture → decisions/verdict/evolution artifacts) — usage: each script's docstring |
| `seeds/` | frozen expert packs loaded into the initial H |
| `reference/cn/`, `spikes/` | read-only reference full of look-alike twins searches WILL hit (edits denied via committed settings) |
| `third_party/hermes/` | hard-pinned reference vendor (`5add283e`, do-not-track); never imported by production |

The three services never import one another: `alpha_web` reaches the other two over HTTP
(`ALPHA_SONIA_URL`, `ALPHA_WORKBENCH_URL`); `sonia` and `workbench` mutate ONE shared live brain
through `LiveBrainStore` file locks plus a cross-face reconcile sweep.

## Commands

```bash
pip install -e ".[dev]"           # extras as needed: [live] [web] [sonia]
python -m pytest -q               # full suite, offline, no keys
python -m pytest tests/<pkg> -q   # scoped slice — tests/ mirrors the package tree
python -m alpha_web               # :8100 ─┐
python -m sonia                   # :8810  ├─ env vars: each service's __main__.py / app.py
python -m workbench               # :8820 ─┘
```

## Gotchas (facts a grep won't surface)

- **PIT firewall.** Corp actions key on `announce_date` (for Alpaca `:= process_date` — no true
  announce field exists), prices stored raw/unadjusted, windowed features trailing-only, learned
  artifacts carry `learned_asof` — pinned by name in the meta-gate
  `tests/test_us0_firewall_surfaces.py`. `make_source()` returns a RAW source by contract;
  wrapping in `GuardedSource` + `AsOfGuard` is the caller's job.
- **One write-waist, one observation channel.** Every H mutation from every face converges on
  `alpha/refine/apply.py::try_apply_op`; red-line doctrine entries are immutable objects. The
  deliberate bypasses — `apply_credit`'s in-place `SkillStats` and its ungated `EpisodeStore`
  writes — are the observation channel; do not route them through the gate.
- **Verdict symmetry (load-bearing).** Verdict paths thread a read-only `recall_store=` into
  `InnerLoop` — never `episode_store=` — so HCH cannot self-write mid-verdict;
  `scripts/refine_live.py` is the only intended same-store-for-both caller.
- **`H` in code is `(p, K, M)`.** `HarnessState` holds doctrine/skills/memory only;
  `PASS_TOOLS["G"]` is a reserved empty pass. Docs writing `H=(p,G,K,M)` describe pass order.
- **Governance (charter, 2026-07-09).** Worker-agent edits are stage-only (`write_mode="apply"`
  raises); live self-study forks-and-proposes (`EvolutionProposal`, user adopts in Sonia);
  in-place autonomy needs `--autonomous` **and** `ALPHA_UNSAFE_AUTONOMOUS=1`. Deviations ledger:
  `docs/superpowers/specs/2026-07-09-charter-conformance-live-governance.md` §5.
- **Names collide.** `agent.py` ×3, `registry.py` ×3, `store.py` ×2, `app.py` ×3, `tools.py`
  (converse vs arena), two `build_market_state` (canonical: `alpha/state/builder.py`) — qualify
  by package before editing. Lowercase `kairos` = the sibling CN legal-agent repo.
- **LLM defaults.** Per-role env `ALPHA_<ROLE>_{PROVIDER,MODEL}`; temperature defaults to 0; the
  default model id `deepseek-v4-pro` is not a valid live API id — override per role (e.g.
  `ALPHA_SONIA_MODEL=deepseek-chat`).
- **Tests.** Fully offline (`FakeSource`/`MockLLMClient`); `tests/web|sonia|workbench`
  importorskip their extras and autouse `brain_session_isolation`; face-touching tests anywhere
  ELSE must request that fixture explicitly, or the cross-face sweep can rewrite the operator's
  real `./state/`.
- **Honest eval.** Returns are gross (stated, not assumed); a delisting scores −1.0, never
  dropped; the guard DROPS vetoed candidates; sizing is verdict-neutral; decorator order
  `SizingPolicy(GuardedPolicy(…))` is load-bearing.
- **`LocalEnv` is not a security boundary** — the compensating control is workbench's boot
  assert that the brain lives outside the workspace.

Backlog: `ROADMAP.md` (the single live backlog) · built log: `docs/PROJECT_STATE.md` ·
`docs/blueprint.md` is stale on structure (perception/eval reference only).
