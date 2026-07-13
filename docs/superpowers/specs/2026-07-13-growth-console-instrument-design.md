# Growth console instrument — three-state market-clock dial

> §3 SMALL POOL item (P2 carry-forward). Scope: `alpha_web/*` + `tests/web/*` only.
> Baseline: main @ c3ca5e3. Nothing here is in `tcb.lock`.

## Problem

After P2 the growth pack speaks a three-state MARKET clock instead of the momo six-phase `GCycle`:
the regime read carries `phase ∈ {"market:confirmed_uptrend", "market:under_pressure",
"market:correction"}` (see `alpha/regime/growth_clock.py`), cross-cut by a `market:panic_state`
flag. The console signature — the six-phase thermal ring (`phase_ring`) and the `phase_pill` — is
momo-shaped. P2 stopped these from 500-ing on the unknown tokens by degrading to the **raw token**
(e.g. the pill literally reads `market:confirmed_uptrend`). That is legible-to-a-developer, not to
an operator. This item gives growth packages a real, legible instrument.

## The three-state metaphor: a semicircular "market-clock" dial

Distinct from the six-phase thermal ring (a full 360° cycle) but built from the same SVG-arc +
legend vocabulary so it stays visually coherent: a **top-semicircle dial** split into three 60°
arcs, read left→right as **rising risk appetite** — the spatial axis literally mirrors `risk_gate`
(correction 0.15 → under_pressure 0.35 → confirmed_uptrend 0.60):

```
        caution
   stop  ╱‾‾‾╲  go
  ╱                ╲
 correction    confirmed_uptrend
```

The active arc brightens and gets a pulsing marker dot (same mechanic as the ring's active
segment); the active state's **label** reads out below (never colour-only), then a legend names all
three states with a tagline each. Semantic, not decorative colour — go/caution/stop, never the
brass accent:

| state (token)              | tone class      | hue (reused, zero new tokens)     | frontside | tagline |
|----------------------------|-----------------|-----------------------------------|-----------|---------|
| `market:confirmed_uptrend` | `.tone--go`     | `--recovery` green (risk-on)      | yes       | A follow-through day confirmed the uptrend. New buys allowed — trade the frontside. |
| `market:under_pressure`    | `.tone--caution`| `--ignition` amber (distribution) | no        | Distribution-day cluster. No new positions; halve adds, raise cash. |
| `market:correction`        | `.tone--stop`   | `--washout` cool blue (cash)      | no        | Deep breadth weakness. Cash is a position — no new buys, no adds. |

Colour reuses three existing spectrum hues that already carry the right semantic (recovery = risk-on
green, ignition = heating/caution amber, washout = "cash is a position" cool), via **new tone
classes** (`.tone--go/caution/stop`) so the growth vocabulary (go/caution/stop) stays its own thing
rather than being conflated with the momo phase names. No new colour token, all AA-clearing (the
reused `-text` variants). "Stop" is cool, not red — red would collide with the `--down` P&L red and
read as a loss; the label text disambiguates.

## Detection at render (the fallback chain)

The **`"market:"` phase prefix** is the cleanest signal and is always present exactly where a regime
is rendered (`pkg.regime.phase` / `regime.phase`). Momo tokens have no `:` (per
`alpha/harness/growth_regime.py` — the two namespaces are disjoint by construction), so:

1. `is_growth_phase(token)` → `token.startswith("market:")` → route to the growth dial.
2. else → the momo `phase_ring` / `phase_pill`, **byte-identical** to today.
3. a `market:*` token whose bare state isn't one of the three (e.g. `market:panic_state`, or a
   future scale) → the dial renders no active arc and shows the raw token; still 200 (defensive).

`seed_pack`/`h.vocabulary` were considered but the regime token is more local and always available
at the render site (no extra context threading), so the prefix is the detection mechanism.

## Panic — the cross-cut flag

`panic_state` is an orthogonal market FLAG (`alpha/guard/panic.py`), not one of the three states. It
surfaces two ways: the guard's veto reason lands in `pkg.key_risks` ("panic-state rebound: leaders
systematically underperform …"), and `market:panic_state` is an admitted phase token. So
`detect_panic(phase, key_risks)` fires when the phase IS the panic token OR any key-risk mentions
"panic". When it fires, a **panic badge** ("⚠ panic-state — leaders systematically underperform")
renders alongside the dial — it does not replace the three-state read (the two are orthogonal).

## Routes

Only two console routes render a regime read; both get the dial for growth packages and stay 200:

- **`/deck`** (dashboard.html): growth → dial (replaces the ring) + panic badge; momo → the ring,
  byte-identical.
- **`/decisions`** (decisions.html regime panel): growth → dial + a labelled growth-state pill +
  panic badge; momo → the existing compact pill, byte-identical.
- **`/verdict`** renders NO regime today (the view dict has window/arms/headline/stat_verdict/
  contribution only) — nothing to change; noted so the "third route" is accounted for.

`phase_pill` is shared by the omnipresent tape pill (base.html) and the skill/lesson/doctrine phase
tags, which can themselves be growth tokens — those keep P2's graceful raw-token degrade untouched.
The instrument is scoped to the **regime read**, not every phase tag.

## Files

- `alpha_web/data_access.py` — `GrowthState` dataclass + `GROWTH_STATES`/`GROWTH_STATE_BY_KEY`
  table, `growth_dial_arcs()` geometry (mirrors `ring_segments`; Jinja has no trig),
  `is_growth_phase`/`growth_state_key`/`detect_panic` helpers.
- `alpha_web/app.py` — register the above as Jinja globals (next to `ring`/`phases`).
- `alpha_web/templates/_macros.html` — `growth_clock(token)`, `growth_pill(token)`, `panic_badge()`.
- `alpha_web/templates/dashboard.html` + `decisions.html` — the `is_growth_phase` branch (momo
  `{% else %}` byte-identical, whitespace-trimmed).
- `alpha_web/static/app.css` — `.tone--go/caution/stop` bindings + dial/legend/panic-badge styles
  (offline, no external assets; reuses `@keyframes pulse`; reduced-motion already globally handled).
- `tests/web/test_app.py` — growth-dial render + state tagline + panic badge; momo byte-identity
  pins for /deck and /decisions.

## Constraints held

Offline, keyless; no new deps; no external fonts/CDN/images (self-contained SVG + CSS). Momo render
byte-identical (diff-proven against a captured baseline). Nothing touched is in `tcb.lock`.
