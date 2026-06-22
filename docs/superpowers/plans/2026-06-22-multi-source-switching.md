# Multi-Source Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the active `MarketDataSource` selectable by name/env so the same system can run against different vendors one at a time, with a future vendor plugging in by implementing the Protocol and registering one line.

**Architecture:** A small registry factory `alpha/data/registry.py::make_source(name=None, *, pit_root=None)` — the data-layer twin of the existing `alpha/llm/config.py::make_client(role)` (registry dict + `ALPHA_<X>` env override + `ValueError` on unknown). It returns a RAW source (the firewall stays at the eval/loop layer). The two existing real sources (`alpaca`, `snapshot`) are registered; the only call-site change is `scripts/capture_window.py`'s thin `main()`.

**Tech Stack:** Python ≥3.11, stdlib only for the new module (`os`, `pathlib`), pytest. No new dependencies.

## Global Constraints

- **Whole-source swap only** — NOT per-capability composition, NOT fallback/redundancy, NO new vendor. Those are deferred (each its own future spec).
- **Mirror `make_client`** — same shape: registry dict, `ALPHA_<X>` env override, explicit arg wins, `ValueError` listing available names on unknown.
- **Selection key:** `ALPHA_DATA_SOURCE`, default `"alpaca"`. Name is normalized `.strip().lower()`.
- **Factory returns a RAW source** — never wrap in `GuardedSource` (callers guard per as-of).
- **Pure-swap contract:** a registered source implements the whole `MarketDataSource` Protocol; an unsupported capability raises `NotImplementedError` in that method (as `AlpacaSource.daily_snapshot` already does).
- **Registered sources:** `alpaca`, `snapshot` only. `FakeSource` stays test-only (needs constructor data; not name-buildable).
- **Commits:** repo is on `main`; per the owner's rule, branch first and only commit/push on explicit authorization. The commit steps below are written for execution time — run them on a feature branch.

---

### Task 1: Source registry factory

**Files:**
- Create: `alpha/data/registry.py`
- Test: `tests/data/test_registry.py`

**Interfaces:**
- Consumes: `AlpacaSource` (`alpha/data/alpaca.py`, `__init__()` reads `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY`, raises `RuntimeError` if missing); `SnapshotSource(store)` (`alpha/data/snapshot_source.py`); `PITStore(root: Path)` (`alpha/data/pit_store.py`); `MarketDataSource` Protocol (`alpha/data/source.py`).
- Produces: `make_source(name: str | None = None, *, pit_root: str | None = None) -> MarketDataSource`.

- [ ] **Step 1: Write the failing tests**

Create `tests/data/test_registry.py`:

```python
# tests/data/test_registry.py
from __future__ import annotations

import pytest

from alpha.data.alpaca import AlpacaSource
from alpha.data.registry import make_source
from alpha.data.snapshot_source import SnapshotSource


@pytest.fixture
def apca(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")


def test_default_is_alpaca(apca, monkeypatch):
    monkeypatch.delenv("ALPHA_DATA_SOURCE", raising=False)
    assert isinstance(make_source(), AlpacaSource)


def test_env_selects_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("ALPHA_DATA_SOURCE", "snapshot")
    monkeypatch.setenv("ALPHA_PIT_ROOT", str(tmp_path))
    assert isinstance(make_source(), SnapshotSource)


def test_explicit_name_overrides_env(apca, monkeypatch):
    monkeypatch.setenv("ALPHA_DATA_SOURCE", "snapshot")     # env says snapshot...
    assert isinstance(make_source("alpaca"), AlpacaSource)  # ...explicit arg wins


def test_snapshot_via_kwarg(tmp_path):
    assert isinstance(make_source("snapshot", pit_root=str(tmp_path)), SnapshotSource)


def test_name_is_normalized(apca, monkeypatch):
    monkeypatch.delenv("ALPHA_DATA_SOURCE", raising=False)
    assert isinstance(make_source("  ALPACA "), AlpacaSource)   # strip + lowercase


def test_unknown_source_raises_listing_available(monkeypatch):
    monkeypatch.delenv("ALPHA_DATA_SOURCE", raising=False)
    with pytest.raises(ValueError, match="unknown data source"):
        make_source("polygon")


def test_snapshot_requires_pit_root(monkeypatch):
    monkeypatch.setenv("ALPHA_DATA_SOURCE", "snapshot")
    monkeypatch.delenv("ALPHA_PIT_ROOT", raising=False)
    with pytest.raises(ValueError, match="pit_root"):
        make_source()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/data/test_registry.py -q`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'alpha.data.registry'`.

- [ ] **Step 3: Write minimal implementation**

Create `alpha/data/registry.py`:

```python
# alpha/data/registry.py
#
# Select the active MarketDataSource by name/env — the data-layer twin of alpha/llm/config.py::make_client.
# Whole-source swap only: each registered source implements the full MarketDataSource Protocol (an
# unsupported capability raises NotImplementedError in that method). Returns a RAW source; callers wrap it
# in GuardedSource at the eval/loop layer.
#
# Add a new vendor:
#   1. Implement the MarketDataSource Protocol in alpha/data/<vendor>.py.
#   2. Add a _build_<vendor>(*, pit_root=None) -> MarketDataSource here.
#   3. Register one line in _SOURCES.
#   4. Select it with ALPHA_DATA_SOURCE=<vendor>.
from __future__ import annotations

import os
from pathlib import Path

from alpha.data.alpaca import AlpacaSource
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource
from alpha.data.source import MarketDataSource


def _build_alpaca(*, pit_root: str | None = None) -> MarketDataSource:
    return AlpacaSource()                       # reads APCA_* + ALPHA_DATA_FEED from env itself


def _build_snapshot(*, pit_root: str | None = None) -> MarketDataSource:
    root = pit_root or os.environ.get("ALPHA_PIT_ROOT")
    if not root:
        raise ValueError("snapshot source requires pit_root or ALPHA_PIT_ROOT")
    return SnapshotSource(PITStore(Path(root)))


_SOURCES = {"alpaca": _build_alpaca, "snapshot": _build_snapshot}


def make_source(name: str | None = None, *, pit_root: str | None = None) -> MarketDataSource:
    """Build the active data source. Name precedence: explicit arg > ALPHA_DATA_SOURCE env > 'alpaca'.
    Returns a RAW source (callers wrap with GuardedSource at the eval/loop layer)."""
    name = (name or os.environ.get("ALPHA_DATA_SOURCE", "alpaca")).strip().lower()
    if name not in _SOURCES:
        raise ValueError(f"unknown data source: {name!r} (expected one of {sorted(_SOURCES)})")
    return _SOURCES[name](pit_root=pit_root)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/data/test_registry.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `python -m pytest -q`
Expected: PASS — prior total + 7.

- [ ] **Step 6: Commit**

```bash
git add alpha/data/registry.py tests/data/test_registry.py
git commit -m "feat(data): make_source registry factory for pluggable data sources"
```

---

### Task 2: Wire capture_window to the registry

**Files:**
- Modify: `scripts/capture_window.py` (the `import` line + the `AlpacaSource()` call in `main()`)
- Test: `tests/scripts/test_capture_window_wiring.py`

**Interfaces:**
- Consumes: `make_source` (Task 1); `capture_window(source, store, start, end, symbols)` (`alpha/data/capture.py`, already persists bars + snapshots + corp actions); the `fake_source` fixture (`tests/conftest.py`: calendar 6/10–6/12, RUN/FLOP bars, snapshot 6/12, RUN reverse_split corp action).
- Produces: a generic `scripts/capture_window.py` whose `main()` builds its source via `make_source()` (selectable with `ALPHA_DATA_SOURCE`).

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_capture_window_wiring.py`:

```python
# tests/scripts/test_capture_window_wiring.py
"""capture_window's main() must build its source via the registry (make_source), so ALPHA_DATA_SOURCE
selects the vendor — verified offline by patching make_source to a FakeSource."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import capture_window as cw  # noqa: E402

from alpha.data.pit_store import PITStore  # noqa: E402


def test_main_builds_source_via_make_source(monkeypatch, tmp_path, fake_source):
    monkeypatch.setattr(cw, "make_source", lambda *a, **k: fake_source)
    monkeypatch.setattr(sys, "argv",
                        ["capture_window.py", "2026-06-10", "2026-06-12", str(tmp_path), "RUN", "FLOP"])
    cw.main()
    store = PITStore(tmp_path)
    assert store.get_bars("RUN") is not None                       # capture ran through the patched source
    assert list(store.get_corp_actions()["symbol"]) == ["RUN"]     # incl. the corp-action wiring
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/test_capture_window_wiring.py -q`
Expected: FAIL — `AttributeError: <module 'capture_window'> has no attribute 'make_source'` (the script still imports `AlpacaSource`).

- [ ] **Step 3: Modify the script**

In `scripts/capture_window.py`, change the import and the `main()` body.

Replace this import line:
```python
from alpha.data.alpaca import AlpacaSource
```
with:
```python
from alpha.data.registry import make_source
```

Replace this line in `main()`:
```python
    capture_window(AlpacaSource(), PITStore(root), start, end, symbols)
```
with:
```python
    capture_window(make_source(), PITStore(root), start, end, symbols)
```

Also update the module docstring's first line to note the source is selectable:
```python
"""Build an offline PIT snapshot DB from the configured data source (ALPHA_DATA_SOURCE, default alpaca). Run:
   python scripts/capture_window.py 2026-06-01 2026-06-12 snap AAPL MSFT NVDA"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/scripts/test_capture_window_wiring.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `python -m pytest -q`
Expected: PASS — prior total + 8 (7 from Task 1, 1 here).

- [ ] **Step 6: Commit**

```bash
git add scripts/capture_window.py tests/scripts/test_capture_window_wiring.py
git commit -m "feat(scripts): capture_window selects its source via make_source (ALPHA_DATA_SOURCE)"
```

---

## Notes for the executor

- Do NOT change `scripts/smoke_alpaca.py` (Alpaca-specific probe) or `scripts/run_verdict.py` (already builds `SnapshotSource` explicitly) — out of scope per the spec.
- The "how to add a vendor" documentation lives in the `registry.py` module docstring (Task 1, Step 3). No separate docs file is required; the design spec at `docs/superpowers/specs/2026-06-22-multi-source-switching-design.md` is the companion.
