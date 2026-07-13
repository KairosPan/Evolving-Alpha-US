# P0.5 — `prompt.py` isomorphism + production pack-wiring (design)

**Date:** 2026-07-13 · **Status:** built. **Mandate:** DEVELOPMENT-PLAN.md §1 P0.5.
**Builds on:** P0.1 (Option B, `2026-07-12-p01-phase-vocabulary-decision.md`), P0.3 (seeds v2 +
`load_pack`/`ALPHA_SEED_PACK`, `2026-07-12-p03-seeds-v2-design.md`), P0.4 (`ALPHA_UNIVERSE_SCREEN` +
`resolve_universe_screen`). This spec records key decisions only; the code is current.

P0.5 is the **program acceptance gate**: with the growth pack active, Kairos produces one growth
`DecisionPackage` offline; the momo path stays byte-identical throughout.

---

## 1. Pack-conditional prompt (`alpha/agent/prompt.py`)

`build_system_prompt` gains a keyword-only `pack: str | None = None`; when `None` it reads
`active_pack_name()` (env `ALPHA_SEED_PACK`, default `"momo"`). The momo branch is the **existing
code verbatim** — same persona, same `CANONICAL_PHASES` cycle line, same doctrine order (red-lines
then mutable, before skills), same `_OUTPUT_CONTRACT`. Byte-identical when the env is unset.

The growth branch is the **isomorphism** the manuscript's "structure = reasoning order" promise
requires (manuscript §0.7-3):

| Element | momo (unchanged) | growth |
|---|---|---|
| persona | speculative-momentum co-pilot | **sector-growth, thesis-first** co-pilot |
| clock line | `CANONICAL_PHASES` ring | growth **market clock** + theme lifecycle + stock stage |
| doctrine | red-lines **then** mutable, at the top | **mutable (thesis/cycle prose) at the top** |
| skills / memory / episodes | after doctrine | after the mutable doctrine prose |
| red-lines | at the top (interleaved) | **tail constraints only** ("override everything above") |
| output contract `regime_read` | "one of the 6 phases + frontside/backside" | **growth market-clock tokens** |

So growth reads: thesis/doctrine prose → quantitative skill panel → memory/episodes → hard
constraints (guard/limit red-lines) → output contract. This is exactly "thesis/doctrine material
before any quantitative panel; guard/limit state as tail constraints only".

**Binding = H, not env.** The pack rides WITH the harness: `HarnessState.vocabulary` (stamped by
`load_seeds`/`load_pack`, default `"momo"`, legacy dumps default `"momo"`) is what `build_system_prompt`
reads when `pack=None`. So a momo H always renders the momo persona and a growth H the growth persona —
even under a divergent (or mid-process flipped) `ALPHA_SEED_PACK`, which closes the chimera-prompt class.
An explicit `pack=` override keeps the growth unit tests deterministic without a fixture H stamp. (An
earlier draft bound the prompt to the env directly; the intrinsic H stamp replaced it.)

## 2. Production wiring — the 6 `load_seeds` call sites

Every production loader gains the same shape: keep the explicit `seeds_dir` override (back-compat,
tests), but the **default resolves the active pack** via `load_pack()` (env `ALPHA_SEED_PACK`).
Env unset → momo → `load_pack()` == `load_seeds(<root>/seeds)` byte-for-byte.

| Site | Change |
|---|---|
| `scripts/save_decisions.py::produce_decisions` | `seeds_dir=None` → `load_pack()` |
| `scripts/run_verdict.py::run_verdict` | `harness_factory` → `load_pack()` when `seeds_dir` unset |
| `scripts/save_evolution.py::run_evolution` | `seeds_dir=None` → `load_pack()` |
| `alpha_web/data_access.py::load_brain` | seed fallback → `load_pack()` when `seeds_dir` unset |
| `alpha/meta/store.py::LiveBrainStore` | seeds-on-empty → `load_pack()` when `seeds_dir` unset |
| `alpha/harness/loader.py::load_pack` | already the resolution seam (no change) |

**run_verdict joins the resolution (verdict symmetry preserved).** `harness_factory` is called fresh
for BOTH arms (HCH and Hexpert/Hmin) inside `compare_harnesses`/`multi_window`; a pack-aware factory
hands **both** arms the same active pack, so symmetry holds exactly as it did when both read momo
`seeds/`. A verdict run under `ALPHA_SEED_PACK=growth` measures growth-vs-growth, never a mixed pair.

## 3. Write-waist pack context (`alpha/refine/apply.py` — TCB)

`_dispatch`'s create paths call `Skill.from_seed(args)` / `Lesson.from_seed(args)` with the **momo**
normalizer, so a live growth-H edit would drop growth phase tokens (loudly, since P0.1 — but still
dropped). This is the P0.3 §5 known limitation.

**Fix (minimal, TCB-safe):** a keyword-only `normalize=None` seam on `try_apply_op` + `_dispatch`.
When `None`, `try_apply_op` resolves the normalizer FROM THE H being edited — `normalizer_for(harness.
vocabulary)`, never the process env — and threads it into the two `from_seed` create paths. This is the
class fix: pack identity rides with the harness, so a growth-H edit keeps its scale-typed tokens and a
momo-H edit stays momo even when a divergent env (cross-face `sonia`/`workbench`, or a flipped
`ALPHA_SEED_PACK`) would have mis-normalized the ONE shared brain. **No enforcement semantics change** —
red-line immutability, provenance stamping, all floors (retire/promote/task) are untouched; only the
create-path normalizer is picked. A momo H → momo normalizer → byte-identical to the old hardcoded default.

`normalizer_for(vocabulary)` is a helper in `loader.py` (non-TCB) mapping a vocabulary NAME to its phase
normalizer, so the TCB diff stays a resolution line + the unchanged threaded calls. `patch_skill`/
`update_memory` set `.phases` verbatim today (no normalizer) and are left unchanged.

## 4. `save_decisions` provenance home for `universe_screen`

`DecisionStore` writes the frozen package JSON with no wrapper, and `DecisionPackage` is read by eval
scoring — so `universe_screen` must NOT land on it (verdict-neutrality). `save_decisions` already
writes a per-day sidecar it owns (`<date>.prompt.json`). Provenance lands there as two top-level
keys, `universe_screen` (resolved via `resolve_universe_screen()`, mirroring `run_verdict`) and
`seed_pack` (sourced from the LOADED H's `vocabulary`, not a separate env read, so it can never diverge
from the H that produced the decisions), so a browsed growth decision is unambiguous about which
universe screen and which pack produced it. `run_verdict` mirrors this: its banner prints `seed_pack`
(warn when != momo) and the `--json` console artifact records it under `window.seed_pack`, sourced from
`load_pack().vocabulary`. Scoring never reads the sidecar → every eval/verdict test is byte-identical.

## 5. GCycle → growth market-clock bridge — DELETED (user adjudication 2026-07-13)

A `market_token_from_regime` adapter briefly existed here (momo phase → growth `market:` token fold).
The adversarial review flagged it as contradicting the user-ratified P0.1 memo (§4/§5: no runtime
mapping between the vocabularies — a mapping table is exactly how old-word semantics leak into the
new world). On adjudication the user chose deletion: it was dead code (doctrine injection does not
regime-match today), and the P2 three-clock classifier will read breadth / follow-through /
distribution-day counts natively rather than translating a miscalibrated momo read. The human-facing
fold remains documentation only (manuscript Appendix A; DEVELOPMENT-PLAN P2 note). The P0.1
no-runtime-bridge constraint STANDS.

## 6. Acceptance gate test

`tests/scripts/test_growth_decision_e2e.py::test_growth_pack_produces_growth_decision_package` —
`monkeypatch` sets `ALPHA_SEED_PACK=growth`, a `FakeSource` + `MockLLMClient` run the full
`save_decisions.produce_decisions` decide path (screen + sizing on), capturing the assembled prompt.
Asserts: the growth persona ("sector-growth") is in the assembled prompt; a growth doctrine entry is
present; the momo persona / `CANONICAL_PHASES` tokens are ABSENT; the produced `DecisionPackage`
validates; no network (offline clients only). This is the program's exit criterion.

## 7. `Candidate.action` — the shared-model half of P0.6 (folded in here)

P0.6 (guard/sizing trim-derisk) built the recommendation vocabulary `RecommendationAction =
Literal["enter","trim","exit"]` (`alpha/sizing/action.py`) and defensive `candidate_action(c) =
getattr(c, "action", "enter")` seams in the L4 guard (skip the new-entry veto for trim/exit) and L3
sizing (`derisk_tier`). The field itself lands on the shared `Candidate` model (this arc's
ownership): `action: RecommendationAction = "enter"`. Default `"enter"` = every existing construction
byte-identical; P0.6's seams activate the moment a producer sets it. `RecommendationAction` is
imported from `alpha.sizing.action` (a leaf — no import cycle: `action.py` depends only on
`sizing.position`). Pinned in `tests/eval/test_decision_full.py`.

## 8. Verdict/eval scoring fence for trim/exit (constraint pinned, NOT implemented)

`ReturnScorer`/`PoolScorer` (`alpha/eval/scorer.py`), `InnerLoop`, and `walk_forward` score **every**
`decision.candidates` entry as a forward-return **LONG** (entry_day → exit_day). A `trim`/`exit`
candidate is a derisk on a name we already HOLD, not a new long — scoring it as a fresh long would
corrupt the metric. Today no producer emits trim/exit (the field is always `"enter"`), so this is
inert; but the producer that FIRST emits one MUST fence trim/exit out of scoring — score
`action == "enter"` only, mirroring the verdict `for_asof(kind="trade")` fence pattern. Recorded here
and as a code comment at the two entries-building sites where the fence goes (`InnerLoop` +
`walk_forward`: `entries = {c.symbol: … for c in …candidates}`) plus the `ReturnScorer` scoring loop,
so the future editor sees it at the point of change. Do NOT implement the fence now (nothing to fence).
