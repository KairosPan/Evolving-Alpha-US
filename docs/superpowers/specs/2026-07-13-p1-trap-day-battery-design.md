# P1 — Adversarial trap-day battery + panic-state L4 veto (design)

> Spec for DEVELOPMENT-PLAN §1 P1 (incl. the 2026-07-12 panic-state pivot addition).
> Sources: kairos-mining §2.5 (CONFIRMED, value 3), §6 order-4; manuscript
> `docs/doctrine/2026-07-12-us-growth-doctrine-draft.md` §1.1 `panic_state`, §4.3
> `panic_state_ban.rule`, Appendix B (`panic_state_ban.rule → L4 guard veto, alpha/guard, 待前置工程`).

## 1. Goal

A `tests/` battery of **synthetic trap days** — days built so that ANY new long = fail — run through
the FULL production decision stack `SizingPolicy(GuardedPolicy(LLMAgentPolicy(H, mock)))` with a
scripted `MockLLMClient` that aggressively proposes buys. The battery asserts **zero new longs
survive** on every trap day. Trap days live ONLY in tests (`FakeSource` / directly-built
`MarketState`); they never touch live eval/verdict scoring (kairos-mining §2.5: "regression/promotion
preconditions, never training signal"). This is the guardrail that lets P2's GCycle recalibration
proceed without silently re-opening chase-risk entries.

Style: the PIT-firewall-quartet meta-gate (`tests/test_us0_firewall_surfaces.py`) — a meta-test
asserts the battery's named test FUNCTIONS exist, so deleting one fails the suite the way deleting a
firewall guard does.

## 2. What the guard path can see (verified)

`GuardedPolicy.decide(state, universe)` → `screen_decision(decision, *, source, state, episode_store)`
→ `GCycle().read(state)` → `RegimeRead(phase, frontside, risk_gate, confidence)`. The veto
(`alpha/guard/veto.py::veto`) reads a single `RegimeRead` plus per-candidate PIT flags (SSR /
reverse-split / dilution / halt-then-dump / episode-taboo). **It sees only today's `MarketState` — no
multi-day history is threaded to the guard today.** The `veto` fires a regime block when
`risk_gate < 0.2` (risk-off) OR `not frontside` (backside).

`GCycle.read` (momo classifier, `alpha/regime/classifier.py`) with `sentiment_norm` unset (the offline
short-window default) uses `proxy = gainer/(gainer+loser)`:

| proxy band | phase | frontside |
|---|---|---|
| `< 0.2` | washout | ✗ (also risk-off: risk_gate<0.2) |
| `[0.2, 0.4)` | **recovery** | **✓** |
| `[0.4, 0.6)` | **ignition** (fb_rate<0.4) / distribution | ignition ✓ / distribution ✗ |
| `≥ 0.6` | **trend** (fb<0.4 ∧ ft≥0.4) / distribution / flush | trend ✓ / else ✗ |

## 3. THE DEEP FINDING (confirmed at code level)

A sharp panic rebound (gainers strongly dominate) → high `proxy` → phase **`trend`** with
`frontside=True` and `risk_gate ≥ 0.2`. **Neither veto branch fires. The current stack does NOT veto
buying leaders into a panic rebound.** Empirically (probed against `GCycle().read`):

- `g8 l2 fb0 ft0.5` → `trend`, frontside=**True**, risk_gate 0.50 — NOT vetoed.
- `g5 l4 fb0` → `ignition`, frontside=**True** — NOT vetoed.
- `g3 l7 fb0` → `recovery`, frontside=**True** — NOT vetoed (this band is the literal momo analog of
  轮回's 冰点抢修复龙头 "grab the recovery leaders after the freeze" — exactly the reflex the growth
  doctrine's `panic_state` says is systematically wrong).

The momo classifier reads a single day's breadth; it has NO way to distinguish a genuine trend from a
bear-market rally, because that distinction lives in the **preceding context** (a bear-market decline
with high volatility), not in the rebound day itself. That is the momentum-crash blind spot, and it is
why prose cannot fix it — the veto must be code AND it must see history. → **Implement the minimal
panic-state L4 veto** (manuscript acceptance condition + Appendix B routing).

## 4. The panic-state veto (minimal, P1)

New pure detector `alpha/guard/panic.py::detect_panic_state(history, today) -> bool`, deterministic,
computed only from `MarketState` counts already on the guard path. Three co-occurring proxies (AND),
where the volatility proxy is itself an OR (dispersion OR a deep-bear mean):

| proxy | 文献 concept | computation | constant (待P2校准) |
|---|---|---|---|
| bear backdrop | 熊市标志 | mean gainer-share over trailing window ≤ `BEAR_SHARE_MAX` **or** fraction of down-breadth days ≥ `BEAR_DOWN_DAY_FRAC` | 0.35 / 0.60 |
| volatility evidence | 高波动 **或** 深熊 | population stdev of daily gainer-share ≥ `VOL_SHARE_STD_MIN` **or** trailing mean ≤ `DEEP_BEAR_SHARE_MAX` | 0.15 / 0.25 |
| sharp rebound | 指数急反弹 | today's gainer-share ≥ `REBOUND_SHARE_MIN` AND (today − trailing-mean) ≥ `REBOUND_JUMP_MIN` | 0.60 / 0.20 |

Window: last `PANIC_LOOKBACK` (15) prior states; requires ≥ `PANIC_MIN_HISTORY` (5) **non-empty** days
of context. `gainer_share = gainer/(gainer+loser)`, `0.0` when the denominator is 0.

**Deep-bear OR-leg (waterfall).** A uniform crash (e.g. gainer-share 0.10 every day) minimises breadth
dispersion **exactly when the bear is most severe**, so it slips a dispersion-only volatility proxy. The
`DEEP_BEAR_SHARE_MAX` OR-leg catches it: a trailing mean at/below 0.25 is a severe bear even at zero
stdev. Probe: history `10×(g=1,l=9)`, today `(g=8,l=2)` → panic. (`BEAR_SHARE_MAX` was tightened 0.45 →
0.35 so an ordinary correction — see §5.3 — no longer trips the bear leg on its mean.)

**Empty-tape exclusion.** A `0/0` day (feed outage) is *insufficient evidence*, not maximally-bearish
evidence, so empty days are excluded from every proxy; if fewer than `PANIC_MIN_HISTORY` non-empty days
remain, the detector abstains (returns False, the warm-up posture).

**The latch (persistence).** The manuscript §4.3 ban spans the whole crash window, but a memoryless
detector re-derives daily and only fires on days that themselves clear `REBOUND_SHARE_MIN` — so a
0.545-share continuation the day after a trigger would be KEPT, and a bear rally would release after a
few days with no base formed. The detector therefore LATCHES: once a trigger day co-fires, panic
persists while the bear backdrop still holds over the trailing window **or** for at least
`PANIC_LATCH_MIN_DAYS` (10), whichever is longer. The latch is a **pure function of history** — a trigger
day still visible in the trailing window (recomputed from its own prefix) keeps the state latched; there
is no hidden mutable state, so `(history, today)` always yields the same answer. Release requires BOTH
the bear backdrop cleared AND the last trigger older than `PANIC_LATCH_MIN_DAYS`.

**Honest limit (documented in code + here).** The true doctrine release condition — a new base + a
follow-through day + a fresh leader list — is **not computable pre-P2** (no base/FTD/leader-list signal
exists yet). `PANIC_LATCH_MIN_DAYS` is its deliberately-conservative proxy; P2's regime successor owns
the real release and the constant's calibration.

**Scope (fail-toward-strict, Fix).** Manuscript §4.3 scopes `panic_state_ban` to strong-list (leader)
names. **No strong-list / leader-membership signal exists pre-P2**, so the implemented veto blocks ALL
new entries on a latched panic day rather than a subset. That broadening is fail-toward-strict and
deliberate: on a genuine momentum crash the reflex to chase is exactly the error the ban targets, and a
blocked new entry is never worse than holding. P2 **MAY** narrow the scope to the leader list once it
exists; it must NOT be narrowed before then. Documented in `panic.py`'s module docstring.

**Fail-closed / fail-toward-strict:** all comparisons are inclusive (`≤`/`≥`) so a borderline day rounds
toward firing; once the proxies hold (or the latch is active) the veto is unconditional (no soft-pass).
It is **targeted**, not "block all frontside": the same sharp rebound after a healthy uptrend (high mean
share, low vol) → bear=False → no veto, and — the depth/severity separation added in this revision — a
follow-through day out of an ordinary choppy correction (mean well above `DEEP_BEAR_SHARE_MAX`, down-day
fraction below `BEAR_DOWN_DAY_FRAC`) → bear=False → no veto. Genuine ignition/trend is never blocked; the
AND-with-bear+vol gate plus the two negative controls are load-bearing.

Wiring (additive, default-None — byte-identical to every existing caller, like the P0.4 breadth thread):
- `CandidateContext` gains `panic_state: bool = False`; `veto()` appends a self-describing reason:
  `"panic-state rebound: leaders systematically underperform — wait for new base + FTD + new leader list"`.
- `screen_decision(..., history: Sequence[MarketState] | None = None)` computes the flag once and passes
  it into every candidate's context. `history=None` → detector never invoked → byte-identical.
- `GuardedPolicy(inner, source, *, episode_store=None, state_history=None)` holds the driver's growing
  prior-state list (mirrors `episode_store`); `decide` forwards it as `history=`.

**Live activation is P2's job** (manuscript routes `panic_state` detection to the "GCycle 后继" three-clock
regime reader; Appendix B marks the rule 待前置工程). P1 delivers the veto CODE + the additive thread; the
battery exercises it end-to-end through the full stack by supplying the context history directly. No live
driver (`save_decisions` / `InnerLoop` / `compare`) is rewired in P1, so all existing tests stay
byte-identical (none pass `state_history`). P2 threads real market-context history into the two verdict
arms symmetrically (like the `screen` flag) to flip it on. TCB: `alpha/guard/*` is NOT in `TCB_FILES`
(re-verified) — no manifest change.

## 5. Trap-day classes (each asserts its intended GCycle read — a mis-constructed fixture is a bug)

All fixtures build the `MarketState` directly (like the existing guard acceptance tests) so the regime
read is precise and asserted per day. `FakeSource` carries a calendar + empty snapshots + empty
corp-actions ⇒ SSR / dilution / reverse-split / halt flags all compute False, isolating the REGIME veto
as the sole cause.

1. **Blowoff-top (climax → distribution).** Extended leaders, breadth narrowing, failed-breakout rate
   climbing → `distribution`, frontside=False, even with a HIGH `risk_gate` (0.5–0.7). Vetoed by the
   EXISTING backside branch. Days: `sn0.7 g8 l2 fb5`, `sn0.65 g10 l3 fb4`, `sn0.5 g5 l5 fb3`.
2. **Backside (every pop sold).** `washout` (risk-off, g1 l9), `distribution` (mid-band g5 l6 fb4),
   `flush` (elevated trailing-percentile sentiment meeting a flushing tape: sn0.65 g3 l8 fb2). All
   frontside=False. Vetoed by the EXISTING risk-off / backside branch.
3. **Panic-state (pivot).** Sharp broad rebounds after a bear backdrop, across **three diversified
   backdrop shapes** (so the class does not all share one context): `g7 l3` / `g8 l2` after the
   interspersed bear+high-vol `_PANIC_CTX`; `g9 l1` after a deep interspersed bear `_DEEP_CTX`; and
   `g8 l2` after a **waterfall** `_WATERFALL_CTX` (uniform crash, ~zero dispersion — caught by the
   deep-bear OR-leg, not the dispersion leg). All read `trend`, **frontside=True**, risk_gate 0.5. The
   existing guard KEEPS them (asserted, with `history=None`); the panic veto (with the context threaded)
   DROPS them. Plus **two negative controls**: the same `g8 l2` rebound after a HEALTHY uptrend, and after
   an **ordinary choppy correction** (mean ~0.38, down-frac 0.5) → the panic veto does NOT fire → still
   frontside/kept (proving the veto is targeted and depth-separated, not "block all frontside").

## 6. Battery discipline (acceptance-gate requirements)

- **No vacuous pass:** the meta-gate asserts the battery test functions exist; a parametrized test
  asserts each trap day loads AND reads its intended phase/frontside; `assert len(ALL_TRAP_DAYS) > 0`.
- **Zero new longs through the full decorator stack**, with the mock proposing multiple aggressive buys
  each day. Anti-silent-pass: assert the mock was called AND each proposed symbol appears in a
  `"vetoed <SYM>"` `key_risks` note (proves candidates reached the guard and were dropped, not
  re-anchored away or silently absent).
- **Pack-parameterized:** run under BOTH seed packs (`load_pack("momo")` + `load_pack("growth")`) and
  assert identical veto outcomes — the guard is pack-independent (reads `MarketState`/regime, not H);
  pin that fact.
- **Decorator order is load-bearing and pinned two ways.** `SizingPolicy(GuardedPolicy(...))` sizes the
  POST-veto survivors. A behavioural test (`test_decorator_order_sizes_post_veto_not_pre_veto`) shows the
  observable difference on a trap day — the correct order sizes an empty book (`total_exposure 0`); the
  inverted order sizes the aggressive buys first and the guard then drops the candidates, leaving a
  phantom portfolio exposure. A source meta-gate (`test_production_sites_size_outside_guard`) AST-checks
  the three production composition sites (`inner_loop.py::_rebind`, `compare.py::_wrap`,
  `save_decisions.py`) so inverting the order at any of them trips the suite.
- **Offline, keyless, fast.** Fixtures named `trap_*` / in `tests/guard/test_trap_day_battery.py` so
  they can never be mistaken for eval data.

## 7. Files

- `alpha/guard/panic.py` (new) — `detect_panic_state` (proxies + deep-bear OR-leg + latch + empty-tape
  exclusion + scope docstring) + named constants (`BEAR_SHARE_MAX 0.35`, `DEEP_BEAR_SHARE_MAX 0.25`,
  `PANIC_LATCH_MIN_DAYS 10`, …, 待P2校准).
- `alpha/guard/veto.py` — `CandidateContext.panic_state` + veto reason.
- `alpha/guard/screen.py` — `screen_decision(history=)` + `GuardedPolicy(state_history=)`.
- `tests/guard/test_panic_state_veto.py` — detector truth table, thresholds, insufficient/empty history,
  waterfall, latch (hold/release), correction control, per-leg boundary probes, byte-identical default.
- `tests/guard/test_trap_day_battery.py` — the full-stack battery (3 classes incl. diversified panic
  backdrops + two negative controls, pack-parameterized, per-day phase assertions, decorator-order).
- `tests/guard/test_trap_battery_surfaces.py` — us0-style meta-gate + the composition-order source gate.

## 8. Known limits (P2 must revisit)

- **Live release condition.** `PANIC_LATCH_MIN_DAYS` is a conservative proxy for the true doctrine
  release (new base + follow-through day + fresh leader list), which is not computable pre-P2. P2's
  regime successor owns the real release and re-calibrates the latch.
- **Veto scope.** The veto blocks ALL new entries on a latched panic day because no strong-list / leader
  signal exists yet (§4.3 scopes the ban to strong-list names). P2 MAY narrow it to the leader list once
  that exists — deliberately NOT narrowed now (fail-toward-strict).
- **Constant calibration.** Every threshold is 文献值待P2校准 (`BEAR_SHARE_MAX`, `DEEP_BEAR_SHARE_MAX`,
  `BEAR_DOWN_DAY_FRAC`, `VOL_SHARE_STD_MIN`, `REBOUND_SHARE_MIN`, `REBOUND_JUMP_MIN`,
  `PANIC_LATCH_MIN_DAYS`, `PANIC_LOOKBACK`, `PANIC_MIN_HISTORY`); the boundary probes pin the *current*
  values so a re-calibration is a deliberate, test-visible edit.
- **Live wiring.** The detector stays DORMANT in P1 — no live driver threads `state_history` /
  `history`. P2 threads real market-context history into the two verdict arms symmetrically (like the
  `screen` flag) to activate it.
