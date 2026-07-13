# Three-clock activation — §1.4 clock_cadence authority into the decide path

**Status:** DESIGN (2026-07-13). Grounded by the 2yr-bed literature calibration (market+stock SANE;
theme sane-but-sector-map-limited — `08715d0` diagnostics on `verdict_pit_2yr`). Additive/default-off:
the trade path is byte-identical until the activation flag is set.

## What already exists (do not rebuild)

The growth doctrine (§1) fractals the sentiment cycle into three scale-typed clocks, each a pure
`s_t`-side READ (never written into H):

| Clock | Read | Consumed live today? |
|---|---|---|
| market (§1.1) | `GrowthMarketClock.read(history, today) -> RegimeRead(phase, frontside, risk_gate)` | **YES** — `alpha/guard/screen.py:136` for `vocabulary=="growth"`; drives `veto.py` (risk_gate<0.2 no-chase, backside no-new-entry) + `sizing/position.py::size_tier(confidence, risk_gate)`. |
| theme (§1.2) | `GrowthThemeClock.read(...)` per sector-map group → `theme:{emerging,institutional,public_laggard,exhaustion}` | NO — pure read, unconsumed. |
| stock (§1.3) | `classify_stock_stage(history, today)` per symbol → `stock:{base,advance,top,decline}` + `climax_run` | NO — pure read, unconsumed. |

So the **market clock is already the top-authority regime read on the live growth path** (via the
`RegimeRead` frontside/risk_gate surface). Activation = compose the theme + stock reads INTO that
surface under the §1.4 authority rule, WITHOUT perturbing the current market-only behavior unless the
activation flag is set.

## §1.4 authority composition (the doctrine rule — user-specified, threshold-independent)

> 高尺度**否决**低尺度的动作（权威向下），低尺度**不给高尺度打分**。 + `event_reread` intra-cadence override.

Compose as a **downward veto cascade** over the existing `RegimeRead` + a new per-candidate stage gate:

1. **market → theme → stock authority (downward-only).**
   - market `correction`/`under_pressure` already tightens `frontside`/`risk_gate` (existing) — this is the
     top gate; nothing below can loosen it (low-scale never scores high-scale).
   - theme phase modulates APPETITE for candidates in that theme/narrative: `exhaustion` → tighten
     (no new entries in that theme, trim); `public_laggard` → the `laggard_timer` (no chasing laggards);
     `institutional` → the main battlefield (full appetite); `emerging` → probe-only. Modulation can only
     TIGHTEN vs the market gate, never loosen it (safety-only-tightens, mirrors the offerings swap).
   - stock stage is a per-candidate LONG-ELIGIBILITY gate (§1.3 只在 advance 做多): only `stock:advance`
     is long-eligible; `base` → watch (no entry); `top`/`decline` → veto/trim; `climax_run` → reduce
     flag (never an add). This is the finest gate and is dominated by both above.
2. **event_reread (§1.4 intra-cadence override).** `detect_stock_reread_events` (already built) fires a
   forced high-scale re-read on: leader breakdown / laggard batch / breadth collapse / earnings-gap-no-fill
   reversal — overriding the cadence (market daily / theme weekly / stock weekly). Wire it so a trigger
   forces the market+theme clocks to re-read same-day rather than waiting for the cadence.

## Consume points (all additive/default-off behind one flag)

- `alpha/guard/screen.py` — already reads the market clock; extend the growth branch to ALSO compute
  the theme read (per candidate's narrative/sector) + the stock stage (per candidate) and fold them into
  the per-candidate veto/appetite **only when `clock_authority` is enabled** (else byte-identical).
- `alpha/guard/veto.py` — the immutable veto surface stays; the stage/theme gates enter as ADDITIONAL
  veto reasons (tighten-only), never removing an existing veto (mirrors the L4 immutability posture).
- `alpha/sizing/` — theme appetite + stock stage cap the size tier (tighten-only, verdict-neutral scoring).
- `alpha/state/` — thread the theme read (per narrative-line) + stock stage into the per-candidate state
  so the agent prompt + guard can see them.

## Narrative clustering (theme's dynamic half)

The theme clock reads per SECTOR-MAP group. The doctrine's per-narrative-line read (§1.2) clusters the
day's candidates by the agent's `narrative` key (already emitted for L3 netting) and runs the theme phase
logic per cluster. **CAVEAT (calibration-confirmed):** a narrative line is 3-5 names (§2.5), so per-cluster
breadth is statistically thin — AND the bootstrap sector map is sparse (657/800 unmapped). Narrative
clustering needs a min-cluster-size floor + is gated on a richer sector map; ships behind the same flag,
default-off, with the thin-N limit documented.

## Posture / calibration status (why default-off)

- Market + stock thresholds are 2yr-bed literature-window SANE (all phases fire, low flicker, `top`
  reachable). One mild flag: the MARKET clock shows ~3.4% ABAB day-parity flicker over 526 days — a
  candidate for a stronger confirmed↔under_pressure hysteresis (tune deferred, tracked; it propagates as
  the top authority so worth smoothing before a live flip-on).
- THEME calibration is limited by the sparse bootstrap sector map (not the thresholds) — a richer GICS/IBD
  sector feed is the real unblock for the theme leg + narrative clustering.
- Therefore: build the whole composition **additive/default-off behind a `clock_authority` flag**. Flag
  OFF → the live growth path is byte-identical (market-clock-only, as today). Flag ON → the full cascade.
  Flip-on waits on (a) the market-clock ABAB tune, (b) a richer sector map for the theme leg. Verdict-
  symmetric (both arms wrap the same reads), PIT-safe (all three clocks are trailing-only reads).

## Acceptance

- Flag OFF: full offline suite byte-identical (the 1883+ trade path unchanged).
- Flag ON: theme tightens appetite in exhaustion/laggard, stock gates long-eligibility to advance,
  market still dominates (downward-only, safety-only-tightens — no gate loosens a higher gate), event_reread
  forces a same-day high-scale re-read on its triggers. Verdict-neutral scoring; PIT-safe; arm-symmetric.
- Own build → adversarial review round (write-path-adjacent: the veto/sizing composition).
