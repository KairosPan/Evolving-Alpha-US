# P0.3 — seeds v2 pack + re-init path (design)

**Date:** 2026-07-12 · **Status:** built. **Mandate:** DEVELOPMENT-PLAN.md §1 P0.3.
**Builds on:** the ratified Option B (`docs/superpowers/specs/2026-07-12-p01-phase-vocabulary-decision.md`).
**Source of content:** `docs/doctrine/2026-07-12-us-growth-doctrine-draft.md` (manuscript v0.1), routed by its
Appendix B distillation ledger and §4.8 red-line set.

This spec records the key decisions only. The manuscript is the content source; the code is current.

---

## 1. Growth-entry schema under Option B (the P0.1 sub-decision, settled here)

P0.1 ratified the *relationship* (disjoint, scale-typed, no runtime bridge) and deferred *how* scale
rides the growth H's tagged elements to this build. **Decision: scale rides inside the phase token as
`"<scale>:<phase>"`** — e.g. `"market:confirmed_uptrend"`, `"theme:emerging"`, `"stock:advance"`.

Why this over a new `scale` field or a separate growth model set (the two options P0.1 §5 floated):

1. **Zero change to the momo model dumps.** `DoctrineEntry` / `Skill` / `Lesson` keep every field
   they have; `.phases` is already `list[str]`, and a scale-prefixed token is just a string. The
   momo H serialization is byte-for-byte unchanged (the P0 acceptance gate). A new `scale` field
   would add `"scale": null` to every momo entry dump; a separate model set is far more code.
2. **The token *is* the scale-typed tag the manuscript requires.** `(scale, phase)` is encoded
   literally and recoverable by a single `str.split(":")`.
3. **The co-residence bar is enforced by types, not discipline.** Momo tokens are bare (`trend`);
   growth tokens are prefixed (`stock:top`). The two namespaces are physically disjoint. Each
   vocabulary has its own normalizer, and **each normalizer drops the other's tokens** (loudly, via
   the existing repo warning idiom) — so mixing is a construction-time error, not a silent bleed.
   This neutralizes the `exhaustion`→`flush` landmine P0.1 §1 named: the growth theme token is
   `theme:exhaustion`, which never resolves through the momo `_PHASE_ALIASES`.

**Consumers are unchanged.** `Doctrine.for_phase`, `SkillRegistry.by_phase`, `MemoryStore.by_phase`
do string membership on `.phases`; the P0.5 prompt / P2 classifier will query with growth tokens
(`for_phase("market:confirmed_uptrend")`). No consumer needs to learn about scale to load the pack.

### The growth vocabulary (declared once, `alpha/harness/growth_regime.py`)

| Scale | Legal phases |
|---|---|
| `market` | `confirmed_uptrend`, `under_pressure`, `correction`, `panic_state` |
| `theme` | `emerging`, `institutional`, `public_laggard`, `exhaustion` |
| `stock` | `base`, `advance`, `top`, `decline` |

`panic_state` is the manuscript's cross-cut market *flag* (§1.1), admitted as a legal `market:` token
so panic doctrine can be tagged; it is not a mutually-exclusive fourth state. `normalize_growth_phases`
mirrors `normalize_phases`' signature `(raw) -> (list[str], applies_all)` exactly, so it is a drop-in.
`"all"` (any case) still sets `applies_all` — cross-scale red-lines and always-on devices use it.

## 2. Pack location + selection mechanism

- **Location:** `seeds_v2/{doctrine,skills,memory}.json` — sibling of `seeds/`, same three-file shape,
  so `load_seeds` reads it with no new file-format code.
- **Selection:** a two-level split so momo stays literally untouched by default.
  - `load_seeds(seeds_dir, *, vocabulary="momo")` — the low-level primitive gains one keyword-only
    param selecting the normalizer (`{"momo": normalize_phases, "growth": normalize_growth_phases}`).
    Default `"momo"` → the exact code path as before. The three `from_seed` classmethods and
    `Doctrine.from_seed_list` gain a `*, normalize=normalize_phases` keyword; the default reproduces
    today's behavior, so every existing caller is byte-identical.
  - A pack registry + resolver in `loader.py`: `SEED_PACKS = {"momo": (<root>/seeds, "momo"),
    "growth": (<root>/seeds_v2, "growth")}`; `active_pack_name()` reads env **`ALPHA_SEED_PACK`**
    (default `"momo"`); `resolve_pack(name=None)` and `load_pack(name=None)` dispatch. Unknown pack
    name raises (fail-loud).
- **Default = momo, byte-identical when unset.** With `ALPHA_SEED_PACK` unset, `load_pack()` resolves
  to `load_seeds(<root>/seeds, vocabulary="momo")`, which is `load_seeds(<root>/seeds)` unchanged.
  Pinned by a regression test comparing `.to_dict()`.

**Scope note (deliberate):** the six production `load_seeds` callers are **not** rewired here — the
env switch is available but wiring the live faces/producers onto it belongs with the P0.5 prompt
isomorphism (persona + output contract are the same activation). P0.3 delivers the pack and a proven
init path; nothing live changes when the switch is unset.

## 3. Distillation — what's in v1, what's out

Routed per Appendix B. Content is **English** (seeds are code artifacts; the Chinese manuscript stays
the source document), each entry 1–2 sentences like the momo seeds.

**Doctrine (`seeds_v2/doctrine.json`):** all §1–§3 道条 (Appendix B row 1) + the §4 rules that route
to doctrine (`stop_discipline`, `portfolio_structure`, `market_state_actions`, `derisk_on_breakdown`,
`earnings_gap_discipline`, `thesis_price_matrix`) + the §4.8 immutable red-line set. Red-lines whose
real enforcement is 待前置工程 (`panic_state_ban`, `earnings_checklist_gate`) or whose landing point
does not yet exist (`derisk_on_breakdown` trim vocabulary) distill as **prose doctrine, honestly
worded** that guard/sizing enforcement is pending — matching how the manuscript marks execution status.

**Immutable red-lines (9)** = the §4.8 set: 5 存续 rewritten in growth terms (`stop_discipline`,
`one_correlated_bet`, `loss_circuit_breaker`, `survivorship_pit`, `fill_feasibility`) + 4 新增
(`panic_state_ban`, `thesis_first`, `earnings_checklist_gate`, `scale_disambiguation`). The two 墓碑
(`no_chase_risk_off` frontside wording, `dont_fight_ssr` intraday semantics) are **not** migrated —
replaced by the three-state action semantics (`market_state_actions`).

**Skills (`seeds_v2/skills.json`):** the executable patterns/detectors with clear triggers in the
manuscript — `breakout_entry` (Appendix B → skills), plus the market/leader/theme detectors
(`follow_through_day`, `distribution_day_cluster`, `leader_breakdown`, `laggard_launch`, `climax_run`).
Defense-heavy (detectors > patterns), like momo. `laggard_launch` ships `incubating` on a
`theme_breadth` dependency (P5); the rest compute from existing bars.

**Memory (`seeds_v2/memory.json`):** the Appendix A concept ledger as `Lesson`s carrying the analog in
`named_analog` (English label; §0.3 forbids inlining old *action* semantics, so the 反转★ lessons name
the reflex only to invert it, and the 墓碑 rows — 连板/打板/卡位/竞价/妖股 — are **excluded** to keep
A-share action recipes out of Kairos's context). Plus the §L-001 Peloton failure card and the §2.3
thesis-card template as a recallable scaffold.

**Explicitly out of v1:**
- `liquidity_floor.rule`, `single_name_cap.rule` — deferred/暂定不设; no numbers invented (§0.2,
  Appendix B 暂不蒸馏). Executability is carried qualitatively by the `fill_feasibility` red-line;
  single-name risk by the honest note in `earnings_gap_discipline` (user-approved per package).
- `trend_template.rule` — routes to `alpha/universe` (P0.4, owned by a parallel agent); the 道
  `rs_as_jury` is distilled, the screen feature is not built here.
- The three-clock **classifier** (market three-state + panic) — a P2 successor; seeds only carry the
  scale-typed *tags*, not the state machine.

## 4. Two presets

- **`scale_disambiguation`** — an immutable doctrine entry in `seeds_v2/doctrine.json` (§0.5, §4.8):
  confirm which clock (market/theme/stock) a cycle word means before interpreting.
- **extract_ops nearest-neighbor guard** — a prompt rule, not a doctrine entry. Added additively to
  `alpha/meta/prompts.py::_EXTRACTION_INSTRUCTION` (the system prompt `extract_ops` builds): if the
  target section/skill/lesson does not exist, return `no_edit` + reason; never rewrite the
  nearest-similar entry. Offline-testable via `render_extraction_system`. Applies to both packs.

## 5. Known limitation (flagged, not fixed here)

`alpha/refine/apply.py::try_apply_op` (the write-waist) calls `Skill.from_seed(args)` /
`Lesson.from_seed(args)` with the **momo** normalizer. When a growth H is live and edited through the
waist, growth phase tokens would be dropped (now loudly, via the normalize warning) rather than kept.
Making the waist vocabulary-aware needs the live-H pack context threaded in; that lands when the growth
H is activated as an editable brain (P0.5 / an A-track wiring), not in P0.3. The seed init path
(`load_seeds`) is fully vocabulary-aware; only the edit path is not yet.
