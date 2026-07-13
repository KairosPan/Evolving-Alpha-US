# P0.1 — Phase-vocabulary decision (three-clock vs `CANONICAL_PHASES`)

**Date:** 2026-07-12 · **Status:** **Option B RATIFIED by user 2026-07-12** — implementation lands
with P0.3/seeds-v2 (the `normalize_phases` warning half of P0.1 shipped independently, see §7).
**Mandate:** DEVELOPMENT-PLAN.md §1 P0.1 — decide how the growth manuscript's three-clock enums
(`docs/doctrine/2026-07-12-us-growth-doctrine-draft.md` §1) relate to the six-phase momo
`CANONICAL_PHASES`, before any phases-tagged distillation (P0.3) can proceed. Blocks P0.3, P0.5, P2.

---

## 0. The two vocabularies

**Momo (`CANONICAL_PHASES`, live today)** — one flat, single-scale enum in
`alpha/harness/regime.py`:
```
["washout", "recovery", "ignition", "trend", "distribution", "flush"]
```
plus `_PHASE_ALIASES` (alias → canonical), `normalize_phase` (one token → canonical | None),
`normalize_phases` (list → `(canonical_list, applies_all)`, **silently dropping** unknowns), and
`phase_from_read` (first canonical token out of a prose `regime_read`).

**Growth (manuscript §1, not yet in code)** — three scale-typed clocks, declared once as controlled
enums, each meaningless without its scale:
| Clock (scale) | Enum | Cross-cut |
|---|---|---|
| market | `confirmed_uptrend / under_pressure / correction` | `panic_state` (bool flag) |
| theme | `emerging / institutional / public_laggard / exhaustion` | — |
| stock | `base / advance / top / decline` | — |

The manuscript is explicit that these are **not** momo phases renamed: §0.4 bars co-residence
(momo H and growth H must not mix — the momo immutable red-lines have no delete op, so mixing
yields contradictory prompt doctrine); the whole doctrine distills to a **fresh seeds v2 pack**, a
new H, not an incremental edit of the momo H.

## 1. Call-site survey (every consumer of the momo vocabulary)

Producers — all in `alpha/harness/regime.py`: `CANONICAL_PHASES`, `_PHASE_ALIASES`,
`normalize_phase`, `normalize_phases`, `phase_from_read`, `is_family`/`FAMILIES` (family is a
separate axis, not touched by this decision).

Consumers:

| Site | Uses the vocabulary how | What a vocabulary change would touch |
|---|---|---|
| `alpha/harness/skill.py::Skill.from_seed` | `normalize_phases(phases\|applicable_regime)` → `.phases`, `.applies_all_phases` | the growth H's skill `.phases` must carry the growth vocabulary |
| `alpha/harness/memory.py::Lesson.from_seed` | same, on `phases\|regime` | growth lessons' `.phases` |
| `alpha/harness/doctrine.py::DoctrineEntry.from_seed` + `Doctrine.for_phase(phase)` | same; `for_phase` filters entries by phase membership | growth doctrine's `.phases` + phase-filtered injection |
| `alpha/regime/cycle.py` (`StateMachine`, `default_us_cycle`) | seeds the 6-node momo cycle; `phase_names()` returns the 6 in order | the growth "market clock" is a **different state machine** (3 states + panic), a P2 successor |
| `alpha/regime/classifier.py::GCycle` | emits `RegimeRead.phase ∈` the 6; `_FRONTSIDE = {recovery, ignition, trend}` | the growth read is market-three-state + `panic_state`; a separate classifier (P2) |
| `alpha/agent/prompt.py` | injects `" -> ".join(CANONICAL_PHASES)` as "MARKET REGIME CYCLE"; `_OUTPUT_CONTRACT` demands `regime_read` = "one of the 6 phases + frontside/backside"; `_skill_line` renders `phases[…]` | growth persona/prompt + output-contract enum is exactly P0.5 |
| `alpha/agent/agent.py` | `_phase_prior = phase_from_read(regime_read)` fed into next-day retrieval | growth prior extraction (scale-aware) |
| `alpha/agent/retrieval.py` | `select_for_prompt` ranks skills by `normalize_phase(phase_prior)` membership (`_hit`); `select_episodes_for_prompt` matches `phase_from_read` on prior vs `episode.phase` | growth recall/ranking on the growth vocabulary |
| `alpha_web/data_access.py` | duplicates `FAMILIES` only (no phase coupling) | none |

Tests that pin the momo vocabulary (a vocabulary change must keep these green for the momo H):
`tests/harness/test_regime.py` (exact `CANONICAL_PHASES` list, aliases, `normalize_phases`
dedup/all/string), `tests/seeds/test_seed_packs.py::test_phases_are_canonical` (+ it explicitly
pins the silent-drop contract via a `bogus_phase` probe) and
`test_seed_skills_carry_at_least_one_canonical_phase`, `tests/regime/test_cycle.py`
(`phase_names() == CANONICAL_PHASES`), `tests/regime/test_classifier.py` (`r.phase in
CANONICAL_PHASES`), `tests/agent/test_select_episodes.py` (`phase_from_read` vs `normalize_phase`).

**Two surprises found in the survey (load-bearing for the decision):**

1. **`exhaustion` is already a momo alias → `flush`** (`_PHASE_ALIASES["exhaustion"] = "flush"`).
   The growth **theme clock's** final stage is also named `exhaustion`. Any design that routes a
   growth token through the existing `_PHASE_ALIASES`/`normalize_phases` would silently rewrite the
   growth theme-`exhaustion` into momo `flush` — a scale-crossing corruption with a clean audit
   trail. This is the single strongest argument against sharing the namespace.
2. **Other near-collisions:** `distribution` is a momo phase and also live prose in the growth
   stock clock ("distribution day"); `top`/`advance`/`base`/`correction` are growth tokens with **no
   scale** attached. A bare token is unambiguous only inside one clock — the vocabulary is
   intrinsically scale-typed, which a flat enum cannot represent.

## 2. Option A — extend `CANONICAL_PHASES`

Add the growth tokens (and their aliases) to the one shared enum + alias map; every consumer then
accepts both vocabularies.

- **Co-residence bar:** VIOLATED. One shared namespace means a growth token validates inside the
  momo H and vice versa — the exact mixing §0.4 forbids. Nothing structural stops a momo
  `DoctrineEntry` from tagging `phases:["emerging"]`.
- **`exhaustion` collision:** UNRESOLVABLE without special-casing — the same token means two things
  at two scales in the same map.
- **Scale:** a flat enum cannot carry scale, so `top`/`exhaustion`/`correction` stay ambiguous;
  the three-clock design is not expressible.
- **Momo-path byte-identity (the P0 acceptance gate):** BROKEN — `test_regime.py`'s exact-list
  assert, `test_cycle.py`'s `phase_names()`, `test_classifier.py`'s "one of 6", and the prompt's
  injected cycle string all change the moment the enum grows; a momo prompt would advertise growth
  phases.
- **Seeds-v2 distillation:** the manuscript tags entries by scale; A flattens the scale away.

Verdict: **reject.** It is the one option that actively merges the two doctrines the plan requires
to stay apart.

## 3. Option B — parallel per-scale vocabularies

Leave `CANONICAL_PHASES` (and all momo consumers) untouched; give the growth H its own scale-typed
vocabulary — three enums (market/theme/stock) declared once, each with its own normalizer, and a
**scale-tagged** phase representation on the growth-tagged elements (the manuscript already tags
every entry by scale). The growth "market clock" read is a P2 successor classifier (three-state +
`panic_state`), separate from the momo `GCycle`; the growth prompt/output-contract enum is P0.5.

- **Co-residence bar:** SATISFIED structurally — the two token namespaces are physically disjoint,
  so accidental mixing is a construction-time error, not a silent semantic bleed. This is the only
  option under which the bar is enforced by types rather than by discipline.
- **`exhaustion` collision:** neutralized — the growth theme-`exhaustion` never passes through the
  momo `_PHASE_ALIASES`; it lives in the theme enum.
- **Scale:** first-class, exactly as the doctrine requires (`(scale, phase)` is the natural growth
  tag; a bare `top` is never interpreted without its clock).
- **Momo-path byte-identity:** PRESERVED — the momo path is not touched; every pinning test above
  stays green with zero diffs (satisfies the P0 acceptance gate).
- **Seeds-v2 distillation:** the scale-keyed representation IS the distillation target for the
  manuscript's scale/phase tags — no information is flattened.
- **Cost (honest):** more code, and one sub-decision deferred to the P0.3/seeds-v2 build (see §5) —
  *how* scale rides the growth H's tagged elements. P0.1 only needs the **relationship** decision;
  the schema is a build-time detail, not a ratification-time one.

Verdict: **recommended** (see §4).

## 4. Option C — explicit mapping table (momo ↔ growth)

A declared table relating momo tokens to growth tokens as one runtime SSOT (e.g. momo `flush` ↔
growth theme `exhaustion`, momo `washout` ↔ growth `correction`/panic).

- This mapping **already exists** — as the manuscript's **Appendix A** (轮回概念 × 相位判定表), a
  *human-facing docs* artifact, and Appendix B (the distillation-routing ledger). That is its
  correct home.
- As **runtime code** it is the wrong layer, and the manuscript forbids it twice:
  - §0.3 (轮回锚点规则): the only source of truth for old→new mapping is Appendix A; live entries
    carry at most a one-line `轮回锚 → A-xx` ID reference, **never inlined judgment**, and **at
    distillation the anchors are stripped** — "旧动作语义绝不进 Kairos 的上下文". A code-level
    momo→growth mapping table re-imports exactly the momo action-semantics the doctrine bans from
    the growth context.
  - §0.4: a live bridge between the two token spaces is itself a co-residence coupling — it lets
    each H reference the other's tokens, which the bar forbids.

Verdict: **reject as runtime code; keep as the human distillation artifact.** C is not an
alternative to B — it is the paper mapping (Appendix A/B) that guides B's one-time distillation.
Nothing to build.

## 5. Recommendation

**Adopt Option B (parallel per-scale vocabularies). Option C's mapping stays where it already is —
the manuscript's Appendix A/B, a human distillation aid, never runtime code. Option A is rejected.**

Rationale, in priority order:
1. **The co-residence bar is the hard P0 constraint.** Only B makes momo/growth mixing a
   type-level impossibility; A merges the namespaces, C bridges them. (manuscript §0.4;
   DEVELOPMENT-PLAN P0.3.)
2. **The three-clock vocabulary is intrinsically scale-typed, and `exhaustion` already collides**
   with a momo alias. A flat enum (A) can't carry scale and can't resolve the collision; a mapping
   table (C) relates two flat spaces without adding the scale dimension. Only B introduces it.
3. **The P0 acceptance gate demands the momo path stay byte-identical.** B touches nothing on it;
   A rewrites the shared enum and breaks four pinning tests + the injected prompt cycle.
4. **Seeds-v2 distillation consumes scale/phase tags.** B's scale-keyed tag is the natural target;
   A/C flatten the scale the manuscript deliberately encodes.
5. **§0.3 is a direct instruction against C-as-code** (strip anchors, never inline old action
   semantics into Kairos's context).

**Sub-decision deferred to P0.3/seeds-v2 build (NOT part of this ratification):** whether the growth
H expresses scale as (a) a `scale` field beside a per-clock `phase` on the existing
`Skill`/`Lesson`/`DoctrineEntry` models (add a growth-only normalizer trio; the momo `.phases`
stays valid for the momo H), or (b) a wholly separate growth model set. Both honor B; the choice is
a schema detail settled when the seeds-v2 pack is distilled, and should be re-confirmed with the
user then. P0.1 ratifies only the *relationship*: **disjoint, scale-typed, no runtime bridge.**

## 6. Downstream consequences of adopting B (for the blocked items)

- **P0.3 (seeds v2):** distills the manuscript into a growth pack whose tagged elements carry the
  growth scale-typed vocabulary; the momo pack/H is untouched (co-residence bar held by types).
- **P0.5 (`prompt.py` isomorphism):** the growth persona injects the growth market clock (not
  `CANONICAL_PHASES`) and the output-contract `regime_read` enum swaps to the growth market states +
  `panic_state`; selected per active H, so a momo prompt is unchanged.
- **P2 (GCycle recalibration → three-clock successor):** the growth market read is a *new*
  classifier over three states + the panic flag, living beside (not replacing) the momo `GCycle`;
  `phase_from_read`/`_FRONTSIDE`/the momo state machine stay as-is for the momo H.
- **Interaction with §7's warning:** once the loud drop-warning lands, feeding a growth token to the
  momo `normalize_phases` (the `exhaustion`→`flush` landmine) stops being silent — a free runtime
  tripwire for the co-residence bar. The warning is vocabulary-agnostic and ships regardless of A/B/C.

## 7. The `normalize_phases` warning (P0.1's code half — shipped independently of the vocab decision)

Independent of A/B/C, P0.1 also fixes `normalize_phases`' silent unknown-token drop → a loud
warning that names the dropped tokens (drop behavior preserved; return value byte-identical). It is
implemented in this same landing (matching the repo's only warning idiom — `print("warning: …")`,
per `alpha/data/integrity_check.py`; there is no `warnings`/`logging` use anywhere in `alpha/`). The
warning lives in `normalize_phases` (the plural, list-dropping function) and **not** in
`normalize_phase` — the singular's `None` return is a deliberate sentinel that `phase_from_read`
scans token-by-token, so warning there would fire on every non-phase prose word. See
`tests/harness/test_regime.py`.
