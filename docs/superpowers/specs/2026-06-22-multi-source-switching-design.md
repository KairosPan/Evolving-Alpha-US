# Design: pluggable market-data source switching

- **Date:** 2026-06-22
- **Status:** Draft (awaiting user review)
- **Scope:** small — a selection mechanism only; no new vendor integration

## Context

Every data consumer (universe builder, return oracle, screen, capture, verdict runner) already talks to
the `MarketDataSource` Protocol (`alpha/data/source.py`), not to Alpaca directly. Implementations today:
`AlpacaSource` (live REST/urllib + lazy alpaca-py bars), `SnapshotSource` (offline PIT store), `FakeSource`
(tests), all composable behind the `GuardedSource` firewall decorator.

The one thing missing is **selection**: `AlpacaSource()` is hard-coded at the call sites
(`scripts/capture_window.py`, `scripts/smoke_alpaca.py`). A concrete motivation to swap vendors already
exists — Alpaca's free IEX feed only serves bars from ~2021, so a future Polygon/Tiingo source would be
wanted for longer history.

## Goal

Make the active data source selectable by name/config so the same system can run against different
vendors, **one at a time**, and so a future vendor plugs in by implementing the Protocol and registering
one line.

## Non-goals (explicitly out of scope)

- **Per-capability composition** (bars from A, short-interest from FINRA, dilution from EDGAR…). This is
  *whole-source swap*, not composition. Confirmed with the user.
- **Fallback / redundancy** (primary + backup auto-failover). Out.
- **A real second vendor** (Polygon/Tiingo/etc.). Out — gets its own spec when a vendor is chosen.
- **A structured config object / DI container** (`DataConfig` pydantic). Deferred; per-source constructor
  params differ enough that it's not worth it yet.

## Design

### `alpha/data/registry.py` — a source factory (mirrors `alpha/llm/config.py::make_client`)

The codebase already has this exact pattern for LLM clients: a registry keyed by name, an `ALPHA_<X>`
env override, and a clear error on an unknown name. We reuse it verbatim for data sources.

Reference shape (final code is the plan's job; this pins the contract):

```python
# alpha/data/registry.py
import os
from pathlib import Path

from alpha.data.alpaca import AlpacaSource
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.data.source import MarketDataSource


def _build_alpaca(*, pit_root: str | None = None) -> MarketDataSource:
    return AlpacaSource()                       # reads APCA_* + ALPHA_DATA_FEED itself


def _build_snapshot(*, pit_root: str | None = None) -> MarketDataSource:
    root = pit_root or os.environ.get("ALPHA_PIT_ROOT")
    if not root:
        raise ValueError("snapshot source requires pit_root or ALPHA_PIT_ROOT")
    return SnapshotSource(PITStore(Path(root)))


_SOURCES = {"alpaca": _build_alpaca, "snapshot": _build_snapshot}


def make_source(name: str | None = None, *, pit_root: str | None = None) -> MarketDataSource:
    """Build the active data source. name precedence: explicit arg > ALPHA_DATA_SOURCE env > 'alpaca'.
    Returns a RAW source (callers wrap with GuardedSource at the eval/loop layer)."""
    name = (name or os.environ.get("ALPHA_DATA_SOURCE", "alpaca")).strip().lower()
    if name not in _SOURCES:
        raise ValueError(f"unknown data source: {name!r} (expected one of {sorted(_SOURCES)})")
    return _SOURCES[name](pit_root=pit_root)
```

### Decisions

- **Selection key:** `ALPHA_DATA_SOURCE` (default `"alpaca"`), overridable by the explicit `name` arg for
  CLI/tests. Aligns with the `ALPHA_*` env family.
- **Registered sources:** `alpaca` + `snapshot` — the two real sources that exist, proving swap works
  end-to-end with no new vendor. `FakeSource` stays test-only (needs constructor data; not name-buildable).
- **Pure-swap contract:** a registered source implements the *whole* `MarketDataSource` Protocol; a vendor
  lacking a capability raises `NotImplementedError` in that method (as `AlpacaSource.daily_snapshot`
  already does). This is what keeps "swap" from silently becoming "composition".
- **Factory returns a raw source** (no `GuardedSource` wrap) — the firewall stays where it is, applied per
  as-of by `screen_decision` / `compare_harnesses` / the loops.
- **Unknown name → `ValueError`** listing the available names (fail loud, mirrors `make_client`).
- **Imports are cheap at module load** — `AlpacaSource.__init__` only reads env (alpaca-py is lazy), so
  importing the registry pulls in no heavy optional deps.

### Call-site changes

- `scripts/capture_window.py`: `AlpacaSource()` → `make_source()` (generic capture; defaults to alpaca).
- `scripts/smoke_alpaca.py`: **unchanged** — it is an Alpaca-specific probe by definition.
- `scripts/run_verdict.py`: optional — it already builds `SnapshotSource(PITStore(root))` explicitly; may
  later read `make_source("snapshot", pit_root=root)`, but no change is required for this spec.

### Testing (all offline)

- `make_source()` / `make_source("alpaca")` returns an `AlpacaSource` (constructed with dummy APCA env).
- `ALPHA_DATA_SOURCE=snapshot` + `pit_root` (or `ALPHA_PIT_ROOT`) returns a `SnapshotSource`.
- explicit `name` arg overrides the env var.
- unknown name raises `ValueError` whose message lists the available sources.
- `snapshot` without a pit_root raises a clear `ValueError`.

### Adding a new source later (documentation)

1. Implement the `MarketDataSource` Protocol in `alpha/data/<vendor>.py` (raise `NotImplementedError` for
   any capability the vendor lacks).
2. Add a `_build_<vendor>` function in `registry.py`.
3. Register one line in `_SOURCES`.
4. Select it with `ALPHA_DATA_SOURCE=<vendor>`.

## Consistency note

This is the data-layer twin of `alpha/llm/config.py::make_client(role)` (registry dict + `ALPHA_<X>` env
override + dispatch + `ValueError` on unknown). Keeping the two factories shaped identically means one
mental model for "how this project selects a pluggable backend".

## Future work (when needed, each its own spec)

- A real second vendor (Polygon/Tiingo) for 2016+ history.
- Per-capability composition (a `CompositeSource` delegating each Protocol method to a different backend) —
  the natural home for the deferred FINRA / EDGAR / options-flow / social feeds.
- Fallback/redundancy decorator.
- A validated `DataConfig` object if per-source params proliferate.
