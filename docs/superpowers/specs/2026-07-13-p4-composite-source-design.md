# Design: `CompositeSource` — per-capability data-source composition

- **Date:** 2026-07-13
- **Status:** Draft (P4-narrowed substance; P5 prerequisite)
- **Scope:** small — a composition layer over the existing `MarketDataSource` Protocol; no new vendor,
  no firewall change.
- **Supersedes the "Future work → per-capability composition" bullet of**
  `docs/superpowers/specs/2026-06-22-multi-source-switching-design.md`.

## Context

The 2026-06-22 multi-source spec delivered **whole-source swap**: `make_source(name)` selects ONE vendor
that answers the entire `MarketDataSource` Protocol. Its explicit non-goal was *per-capability
composition* (bars from A, short-interest from FINRA, dilution from EDGAR…), deferred to "a
`CompositeSource` delegating each Protocol method to a different backend — the natural home for the
deferred FINRA / EDGAR / options-flow / social feeds."

P4 (narrowed, user decision 2026-07-13: no second vendor for now) makes that `CompositeSource` its whole
substance, ordered as **P5's prerequisite**: P5's enrichment feeds (earnings, short-interest,
EDGAR offerings, float, theme-breadth) each want to be a *per-capability backend* composed with the base
bars/snapshot vendor, not a whole replacement vendor. Composition is the seam that lets one feed land at a
time without touching the base source.

## The Protocol being composed

`alpha/data/source.py::MarketDataSource` (RAW/unadjusted, normalized English columns):

| Method | Capability group |
|---|---|
| `trading_calendar()` | `calendar` |
| `daily_bars(symbol, start, end)` | `bars` |
| `daily_snapshot(day)` | `snapshot` |
| `corporate_actions(start, end)` | `corp_actions` |
| `corporate_actions_known(as_of)` | `corp_actions` |
| `corp_actions_available()` | `corp_actions` |

## Goal

A `MarketDataSource` that routes **each capability** to a (possibly different) backend source, so P5 can
compose a base bars/snapshot vendor with one enrichment backend per feed — while preserving the two
data-layer contracts that everything downstream relies on: the **RAW-source contract** (returns raw,
caller wraps with `GuardedSource`+`AsOfGuard`) and the **pure-swap contract** (a backend implements a
capability or raises `NotImplementedError`).

## Non-goals

- **New vendors / new Protocol methods.** P5 adds the earnings/short-interest/etc. *methods* (and their
  capability groups) when each feed lands; this spec composes today's Protocol only.
- **Fallback / redundancy** (try backend A, fall back to B on error). Still out — a separate decorator.
- **Guarding inside the composite.** The firewall stays a caller-applied outer wrapper (see below).
- **A validated `DataConfig` object** (P4 (d), conditional; overlaps A1 Settings).

## Design

### Composition unit = capability GROUP, not individual method

The three corp-actions methods (`corporate_actions`, `corporate_actions_known`,
`corp_actions_available`) are **coupled**: `corp_actions_available()` reports whether *the corp backend*
can check reverse-split / dilution (the P3 tri-state guard-blind fix). Routing the probe to a different
backend than the corp data it describes would let the probe lie — report "checked" while a *different*
feed served the actual actions. So the routable unit is the **capability group** (`calendar`, `bars`,
`snapshot`, `corp_actions`), and overriding `corp_actions` moves all three coupled methods together as
one atom. Future P5 feeds each add their own group (`earnings`, `short_interest`, …) when their methods
land on the Protocol.

### API

```python
# alpha/data/composite.py
_CAPABILITIES = frozenset({"calendar", "bars", "snapshot", "corp_actions"})

class CompositeSource:
    def __init__(self, base: MarketDataSource,
                 overrides: Mapping[str, MarketDataSource] | None = None) -> None: ...
```

- **`base`** answers every capability with no override — the default backend.
- **`overrides`** maps a capability-group name → the backend that answers it. Unknown keys raise
  `ValueError` at construction (fail loud, mirrors `make_source`'s unknown-name `ValueError`; catches a
  `"corp_action"` typo before it silently falls through to base).
- Each Protocol method delegates to `overrides.get(capability, base).<method>(...)` and returns the
  result **unchanged** — a pure pass-through.

### The two contracts, preserved by delegation

- **RAW-source contract.** Every method returns the routed backend's RAW frame verbatim; the composite
  adds no guarding and no adjustment. A `CompositeSource` is therefore a RAW source and is wrapped by
  `GuardedSource`+`AsOfGuard` exactly like any other — the firewall composes cleanly on the *outside*
  (the guard checks the requested date, then calls one composite method, which routes to one backend).
  The composite cannot introduce lookahead because it never fabricates or shifts a date.
- **Pure-swap contract → "falls to base, base decides".** A capability with **no override** routes to
  `base`; if `base` itself does not implement it, `base`'s method raises `NotImplementedError` — which
  propagates unchanged. So "unsupported capability → `NotImplementedError`" holds *through* the composite
  by delegation, with no special-casing (e.g. `CompositeSource(AlpacaSource())` raises
  `NotImplementedError` on `daily_snapshot`, exactly as bare `AlpacaSource` does). This is the documented
  decision from the task's "raises `NotImplementedError` … or falls to base if base implements it": it
  **falls to base**, and base's own pure-swap behavior is what surfaces.
- **`corp_actions_available` routing.** Delegates to the `corp_actions`-routed backend directly (not a
  `getattr` default-True fallback like `GuardedSource` — the composite's backends are full
  `MarketDataSource`s by contract, with no legacy inners predating the capability). So a composite whose
  corp backend reports MISSING (`corp_actions_available() is False`) reports `False`, even if `base` would
  report `True` — the P3 probe routes faithfully to the backend that owns the corp data.

### Registry integration (`alpha/data/registry.py`)

Two additions, both RAW-returning, mirroring the existing `_build_<name>` idiom:

1. **`make_composite_source(base=None, overrides=None, *, pit_root=None)`** — the code-level constructor
   P5 calls directly. `base` and each override value may be a `MarketDataSource` **instance** (P5 wires a
   constructed feed backend — an EDGAR/FINRA client with its own params) **or** a registry **name string**
   (resolved via `make_source(name, pit_root=…)`). Returns a RAW `CompositeSource`.
2. **`"composite"` registered in `_SOURCES`** so `ALPHA_DATA_SOURCE=composite` works end-to-end and the
   P3 `corp_actions_available` conformance parametrization (`sorted(_SOURCES)`) auto-covers it. Env shape:
   - `ALPHA_DATA_COMPOSITE_BASE` (default `"alpaca"`) — the base backend name.
   - `ALPHA_DATA_COMPOSITE` — comma-separated `capability=source_name` overrides
     (e.g. `"corp_actions=snapshot"`). A malformed pair (no `=`, or empty name) raises `ValueError`.
   - **Recursion guard:** neither base nor an override backend may be `"composite"` (would recurse into
     `make_source("composite")` forever) → explicit `ValueError`.

`make_source`'s signature, default (`alpaca`), and RAW-return are unchanged; adding one `_SOURCES` entry
does not alter any existing dispatch path. **Default behavior is byte-identical when composite is unused**
(pinned by test).

### Home

New module `alpha/data/composite.py` — keeps `source.py` focused on the Protocol + its two canonical
implementations (`FakeSource` for tests, `GuardedSource` the firewall decorator). `CompositeSource` is a
sibling composition decorator with its own documented home, imported by `registry.py`.

## Testing (all offline, keyless)

- **Routing** — a two-backend composite (base with `bars`/`snapshot`, a distinct corp backend) proves
  `bars`/`snapshot`/`calendar` come from base and all three corp methods come from the corp backend; a
  misroute is caught (the corp backend has no bars → empty if bars wrongly routed there).
- **Fall-through** — an un-overridden capability routes to base.
- **`corp_actions_available` routing / P3 probe** — corp backend `corp_actions_available=False` while base
  `=True` → composite reports `False` (and the symmetric True case).
- **Pure-swap** — `CompositeSource(AlpacaSource())` (or a base whose `daily_snapshot` raises) propagates
  `NotImplementedError` for the un-overridden, base-unsupported capability.
- **Unknown capability key** → `ValueError` listing the valid capabilities.
- **PIT-firewall preservation** — `GuardedSource(CompositeSource(...), AsOfGuard(cursor))` blocks a
  future date and allows `as_of == cursor`; the composite adds no lookahead.
- **RAW pass-through** — a returned frame equals the backend's frame (no mutation/adjustment).
- **Registry** — `make_source("composite")` returns a `CompositeSource`; env base/overrides route
  correctly; malformed override and the recursion guard raise `ValueError`; `make_composite_source`
  accepts both instances and names; default path (`make_source()` with no composite env) still returns
  `AlpacaSource` (byte-identical pin).

## Consequences

- P5 lands each feed as one composite backend + one new capability group + delegating methods, without
  touching the base vendor or the firewall.
- The whole-source `make_source` seam and the composition seam share one mental model: a base selected by
  name, optionally recomposed per capability.

## Future work (unchanged from 2026-06-22, minus this item)

- A real second vendor (deferred to the §4 ledger; registry seam stays one line).
- Fallback/redundancy decorator.
- A validated `DataConfig` object if per-source params proliferate (P4 (d), overlaps A1 Settings).
