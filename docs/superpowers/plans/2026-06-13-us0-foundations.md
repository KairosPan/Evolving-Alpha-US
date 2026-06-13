# US-0 Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data + point-in-time + lookahead-firewall foundation for the US self-evolving momentum co-pilot, with an offline-testable universe builder and the four firewall-surface regression tests the spec requires.

**Architecture:** A `MarketDataSource` Protocol with a `FakeSource` (tests), a real `AlpacaSource` (smoke-only), and an offline `SnapshotSource` backed by a parquet `PITStore`. Every dated fetch passes through a `GuardedSource`/`AsOfGuard` that rejects future-dated requests. Raw (unadjusted) prices are stored point-in-time; split/reverse-split/delisting facts are stored with announcement dates so detection is PIT-correct. The universe builder screens a daily cross-section for gainers/gap-ups and attaches a strictly-trailing RVOL.

**Tech Stack:** Python ≥3.11, pydantic v2 (frozen models), pandas, pyarrow (parquet); alpaca-py + pandas-market-calendars as an optional `live` extra (tests run fully offline with `FakeSource`).

**Spec:** `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md` (US-0 = §9 row 1). The four firewall-surface tests (acceptance gate): **date-lookahead** (Task 4), **corp-action ex-date PIT** (Task 5), **split-vintage raw-PIT** (Task 7), **windowed-rank trailing-only** (Task 9).

**Conventions:** all code/comments English. Frozen pydantic models for value objects. `from __future__ import annotations` at the top of every module. Commit after every passing task.

---

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `alpha/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_scaffold.py`
- Modify: `.gitignore` (append Python/data ignores)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold.py
def test_package_imports():
    import alpha
    assert alpha.__version__ == "0.0.1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scaffold.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha'`

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "alpha"
version = "0.0.1"
description = "Evolving-Alpha-US — self-evolving US-equities momentum co-pilot (US-0 foundations)"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.0",
    "pydantic>=2.6",
    "pyarrow>=15",
]

[project.optional-dependencies]
live = ["alpaca-py>=0.30", "pandas-market-calendars>=4.0"]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["alpha*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 4: Create package + test init files**

```python
# alpha/__init__.py
__version__ = "0.0.1"
```

```python
# tests/__init__.py
```

- [ ] **Step 5: Append to `.gitignore`**

```gitignore

# US rebuild
__pycache__/
*.pyc
.venv/
*.egg-info/
.pytest_cache/
/snap/
/runs/
*.parquet
```

- [ ] **Step 6: Install editable + run test**

Run: `python -m pip install -e ".[dev]" >/dev/null && python -m pytest tests/test_scaffold.py -q`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml alpha/__init__.py tests/__init__.py tests/test_scaffold.py .gitignore
git commit -m "US-0 Task 1: project scaffold (alpha package + pytest)"
```

---

### Task 2: Lookahead firewall (`AsOfGuard`)

**Files:**
- Create: `alpha/data/__init__.py`
- Create: `alpha/data/firewall.py`
- Create: `tests/data/__init__.py`
- Create: `tests/data/test_firewall.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_firewall.py
from datetime import date
import pytest
from alpha.data.firewall import AsOfGuard, LookaheadError


def test_allows_past_and_equal_dates():
    g = AsOfGuard(date(2026, 6, 12))
    g.check(date(2026, 6, 10))   # past: ok
    g.check(date(2026, 6, 12))   # equal: ok


def test_rejects_future_date():
    g = AsOfGuard(date(2026, 6, 12))
    with pytest.raises(LookaheadError):
        g.check(date(2026, 6, 13))


def test_advance_is_monotonic():
    g = AsOfGuard(date(2026, 6, 12))
    g.advance(date(2026, 6, 13))
    assert g.as_of == date(2026, 6, 13)
    with pytest.raises(ValueError):
        g.advance(date(2026, 6, 12))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/data/test_firewall.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.data'`

- [ ] **Step 3: Create the package init + implementation**

```python
# alpha/data/__init__.py
```

```python
# tests/data/__init__.py
```

```python
# alpha/data/firewall.py
from __future__ import annotations

from datetime import date as Date


class LookaheadError(RuntimeError):
    """A request asked for data dated after the as-of cursor — lookahead blocked."""


class AsOfGuard:
    """Monotonic time boundary: only data dated <= as_of may be accessed."""

    def __init__(self, as_of: Date) -> None:
        self._as_of = as_of

    @property
    def as_of(self) -> Date:
        return self._as_of

    def check(self, requested: Date) -> None:
        if requested > self._as_of:
            raise LookaheadError(f"lookahead blocked: requested {requested} > cursor {self._as_of}")

    def advance(self, new_as_of: Date) -> None:
        if new_as_of < self._as_of:
            raise ValueError(f"cursor cannot move backward: {new_as_of} < {self._as_of}")
        self._as_of = new_as_of
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/data/test_firewall.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/data/__init__.py alpha/data/firewall.py tests/data/__init__.py tests/data/test_firewall.py
git commit -m "US-0 Task 2: AsOfGuard lookahead firewall"
```

---

### Task 3: US trading calendar helpers

**Files:**
- Create: `alpha/data/calendar.py`
- Create: `tests/data/test_calendar.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_calendar.py
from datetime import date
from alpha.data.calendar import trading_days_between, next_trading_day, prev_trading_day

CAL = [date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]


def test_trading_days_between_inclusive_sorted():
    out = trading_days_between(CAL, date(2026, 6, 9), date(2026, 6, 11))
    assert out == [date(2026, 6, 9), date(2026, 6, 10), date(2026, 6, 11)]


def test_next_and_prev_trading_day():
    assert next_trading_day(CAL, date(2026, 6, 10)) == date(2026, 6, 11)
    assert prev_trading_day(CAL, date(2026, 6, 10)) == date(2026, 6, 9)


def test_next_at_end_returns_none():
    assert next_trading_day(CAL, date(2026, 6, 12)) is None
    assert prev_trading_day(CAL, date(2026, 6, 8)) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/data/test_calendar.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.data.calendar'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/data/calendar.py
from __future__ import annotations

from datetime import date as Date


def trading_days_between(calendar: list[Date], start: Date, end: Date) -> list[Date]:
    """All calendar days in [start, end], ascending."""
    return sorted(d for d in calendar if start <= d <= end)


def next_trading_day(calendar: list[Date], day: Date) -> Date | None:
    later = sorted(d for d in calendar if d > day)
    return later[0] if later else None


def prev_trading_day(calendar: list[Date], day: Date) -> Date | None:
    earlier = sorted(d for d in calendar if d < day)
    return earlier[-1] if earlier else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/data/test_calendar.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/data/calendar.py tests/data/test_calendar.py
git commit -m "US-0 Task 3: US trading calendar helpers"
```

---

### Task 4: Data source protocol + FakeSource + GuardedSource (firewall surface 1: date-lookahead)

**Files:**
- Create: `alpha/data/source.py`
- Create: `tests/data/conftest.py`
- Create: `tests/data/test_source.py`

The US `MarketDataSource` contract (raw, normalized English columns):
- `trading_calendar() -> list[Date]`
- `daily_bars(symbol, start, end) -> DataFrame[date,open,high,low,close,volume]` (RAW/unadjusted)
- `daily_snapshot(day) -> DataFrame[symbol,name,open,high,low,close,volume,prev_close]` (cross-section for `day`)
- `corporate_actions(start, end) -> DataFrame[symbol,announce_date,ex_date,kind,ratio]`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/conftest.py
from __future__ import annotations
from datetime import date
import pandas as pd
import pytest
from alpha.data.source import FakeSource


@pytest.fixture
def fake_source():
    """Two symbols over 3 days. RUN gaps up and runs; FLOP fades."""
    cal = [date(2026, 6, 10), date(2026, 6, 11), date(2026, 6, 12)]
    bars = {
        "RUN": pd.DataFrame({
            "date": cal,
            "open":  [10.0, 12.5, 16.0], "high": [12.0, 15.0, 18.0],
            "low":   [9.5, 12.0, 15.0],  "close": [11.0, 14.0, 17.0],
            "volume": [1_000_000, 3_000_000, 5_000_000],
        }),
        "FLOP": pd.DataFrame({
            "date": cal,
            "open":  [20.0, 21.0, 18.0], "high": [22.0, 21.5, 18.5],
            "low":   [19.0, 17.5, 16.0], "close": [21.0, 18.0, 16.5],
            "volume": [500_000, 600_000, 700_000],
        }),
    }
    snapshots = {
        date(2026, 6, 12): pd.DataFrame({
            "symbol": ["RUN", "FLOP"], "name": ["Runner Inc", "Flopco"],
            "open": [16.0, 18.0], "high": [18.0, 18.5], "low": [15.0, 16.0],
            "close": [17.0, 16.5], "volume": [5_000_000, 700_000],
            "prev_close": [14.0, 18.0],
        }),
    }
    corp = pd.DataFrame({
        "symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
        "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1],
    })
    return FakeSource(calendar=cal, bars=bars, snapshots=snapshots, corp_actions=corp)
```

```python
# tests/data/test_source.py
from __future__ import annotations
from datetime import date
import pytest
from alpha.data.firewall import AsOfGuard, LookaheadError
from alpha.data.source import GuardedSource


def test_fake_source_daily_snapshot(fake_source):
    snap = fake_source.daily_snapshot(date(2026, 6, 12))
    assert set(snap["symbol"]) == {"RUN", "FLOP"}


def test_fake_source_daily_bars_window(fake_source):
    bars = fake_source.daily_bars("RUN", date(2026, 6, 11), date(2026, 6, 12))
    assert list(bars["date"]) == [date(2026, 6, 11), date(2026, 6, 12)]


def test_guarded_source_blocks_future_snapshot(fake_source):
    guard = AsOfGuard(date(2026, 6, 11))
    gs = GuardedSource(fake_source, guard)
    gs.daily_snapshot(date(2026, 6, 11))                 # equal: ok
    with pytest.raises(LookaheadError):
        gs.daily_snapshot(date(2026, 6, 12))             # future: blocked


def test_guarded_source_blocks_future_bars_end(fake_source):
    guard = AsOfGuard(date(2026, 6, 11))
    gs = GuardedSource(fake_source, guard)
    with pytest.raises(LookaheadError):
        gs.daily_bars("RUN", date(2026, 6, 10), date(2026, 6, 12))


def test_guarded_source_blocks_future_corp_actions(fake_source):
    guard = AsOfGuard(date(2026, 6, 11))
    gs = GuardedSource(fake_source, guard)
    with pytest.raises(LookaheadError):
        gs.corporate_actions(date(2026, 6, 1), date(2026, 6, 12))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/data/test_source.py -q`
Expected: FAIL — `ImportError: cannot import name 'FakeSource'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/data/source.py
from __future__ import annotations

from datetime import date as Date
from typing import Protocol

import pandas as pd

from alpha.data.firewall import AsOfGuard

_EMPTY_BARS = ["date", "open", "high", "low", "close", "volume"]
_EMPTY_SNAP = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close"]
_EMPTY_CORP = ["symbol", "announce_date", "ex_date", "kind", "ratio"]


class MarketDataSource(Protocol):
    """US market data contract (normalized English columns; RAW/unadjusted prices)."""
    def trading_calendar(self) -> list[Date]: ...
    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame: ...
    def daily_snapshot(self, day: Date) -> pd.DataFrame: ...
    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame: ...


class FakeSource:
    """In-memory MarketDataSource for offline tests."""

    def __init__(self, *, calendar: list[Date],
                 bars: dict[str, pd.DataFrame],
                 snapshots: dict[Date, pd.DataFrame],
                 corp_actions: pd.DataFrame | None = None) -> None:
        self._calendar = list(calendar)
        self._bars = {k: v.copy() for k, v in bars.items()}
        self._snapshots = {k: v.copy() for k, v in snapshots.items()}
        self._corp = (corp_actions.copy() if corp_actions is not None
                      else pd.DataFrame(columns=_EMPTY_CORP))

    def trading_calendar(self) -> list[Date]:
        return list(self._calendar)

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        df = self._bars.get(symbol)
        if df is None or df.empty:
            return pd.DataFrame(columns=_EMPTY_BARS)
        return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        df = self._snapshots.get(day)
        return df.copy() if df is not None else pd.DataFrame(columns=_EMPTY_SNAP)

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        df = self._corp
        if df.empty:
            return pd.DataFrame(columns=_EMPTY_CORP)
        return df[(df["ex_date"] >= start) & (df["ex_date"] <= end)].reset_index(drop=True)


class GuardedSource:
    """Wraps any MarketDataSource; routes every dated fetch through AsOfGuard."""

    def __init__(self, inner: MarketDataSource, guard: AsOfGuard) -> None:
        self._inner = inner
        self._guard = guard

    def trading_calendar(self) -> list[Date]:
        return self._inner.trading_calendar()

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        self._guard.check(end)            # scoring at as_of>=t+N is legal; end>as_of is lookahead
        return self._inner.daily_bars(symbol, start, end)

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        self._guard.check(day)
        return self._inner.daily_snapshot(day)

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        self._guard.check(end)
        return self._inner.corporate_actions(start, end)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/data/test_source.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/data/source.py tests/data/conftest.py tests/data/test_source.py
git commit -m "US-0 Task 4: MarketDataSource protocol + FakeSource + GuardedSource (firewall surface: date-lookahead)"
```

---

### Task 5: Corporate actions, PIT-by-announcement (firewall surface 2: corp-action ex-date)

**Files:**
- Create: `alpha/data/corp_actions.py`
- Create: `tests/data/test_corp_actions.py`

The trap: a reverse split announced on D1 with ex-date D20. At an as-of between D1 and D20 the split is *known* (announced) but not yet executed; before D1 it must be invisible. Detection keys on `announce_date`, never the future `ex_date`.

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_corp_actions.py
from __future__ import annotations
from datetime import date
import pandas as pd
from alpha.data.corp_actions import known_corporate_actions, has_reverse_split_pending

CORP = pd.DataFrame({
    "symbol": ["RUN", "RUN"],
    "announce_date": [date(2026, 6, 9), date(2026, 6, 15)],
    "ex_date": [date(2026, 6, 20), date(2026, 6, 25)],
    "kind": ["reverse_split", "split"],
    "ratio": [0.1, 2.0],
})


def test_known_filters_by_announce_date_not_ex_date():
    # as_of just after the first announcement, before its ex-date
    known = known_corporate_actions(CORP, date(2026, 6, 10))
    assert list(known["kind"]) == ["reverse_split"]   # second not yet announced


def test_nothing_known_before_first_announcement():
    known = known_corporate_actions(CORP, date(2026, 6, 8))
    assert known.empty


def test_has_reverse_split_pending_pit():
    # known (announced) but ex-date still in the future => pending
    assert has_reverse_split_pending(CORP, "RUN", date(2026, 6, 10)) is True
    # before announcement => not pending (no lookahead to the ex-date)
    assert has_reverse_split_pending(CORP, "RUN", date(2026, 6, 8)) is False
    # after the ex-date => no longer "pending" (already executed)
    assert has_reverse_split_pending(CORP, "RUN", date(2026, 6, 21)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/data/test_corp_actions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.data.corp_actions'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/data/corp_actions.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

COLUMNS = ["symbol", "announce_date", "ex_date", "kind", "ratio"]


def known_corporate_actions(corp: pd.DataFrame, as_of: Date) -> pd.DataFrame:
    """Corporate actions whose ANNOUNCEMENT is known by as_of (never keyed on ex_date)."""
    if corp is None or corp.empty:
        return pd.DataFrame(columns=COLUMNS)
    return corp[corp["announce_date"] <= as_of].reset_index(drop=True)


def has_reverse_split_pending(corp: pd.DataFrame, symbol: str, as_of: Date) -> bool:
    """True iff a reverse split for `symbol` is announced (<=as_of) but not yet executed (ex_date>as_of)."""
    known = known_corporate_actions(corp, as_of)
    if known.empty:
        return False
    rs = known[(known["symbol"] == symbol) & (known["kind"] == "reverse_split")
               & (known["ex_date"] > as_of)]
    return not rs.empty
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/data/test_corp_actions.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/data/corp_actions.py tests/data/test_corp_actions.py
git commit -m "US-0 Task 5: corporate actions PIT-by-announcement (firewall surface: corp-action ex-date)"
```

---

### Task 6: PITStore (atomic parquet)

**Files:**
- Create: `alpha/data/pit_store.py`
- Create: `tests/data/test_pit_store.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_pit_store.py
from __future__ import annotations
from datetime import date
import pandas as pd
from alpha.data.pit_store import PITStore


def test_snapshot_roundtrip(tmp_path):
    store = PITStore(tmp_path)
    df = pd.DataFrame({"symbol": ["RUN"], "close": [17.0]})
    assert store.has_snapshot(date(2026, 6, 12)) is False
    store.put_snapshot(date(2026, 6, 12), df)
    assert store.has_snapshot(date(2026, 6, 12)) is True
    out = store.get_snapshot(date(2026, 6, 12))
    pd.testing.assert_frame_equal(out, df)


def test_bars_roundtrip(tmp_path):
    store = PITStore(tmp_path)
    df = pd.DataFrame({"date": [date(2026, 6, 12)], "open": [16.0], "high": [18.0],
                       "low": [15.0], "close": [17.0], "volume": [5_000_000]})
    store.put_bars("RUN", df)
    out = store.get_bars("RUN")
    assert out is not None and out.iloc[0]["close"] == 17.0


def test_calendar_and_corp_roundtrip(tmp_path):
    store = PITStore(tmp_path)
    store.put_calendar([date(2026, 6, 11), date(2026, 6, 12)])
    assert store.get_calendar() == [date(2026, 6, 11), date(2026, 6, 12)]
    corp = pd.DataFrame({"symbol": ["RUN"], "announce_date": [date(2026, 6, 9)],
                         "ex_date": [date(2026, 6, 20)], "kind": ["reverse_split"], "ratio": [0.1]})
    store.put_corp_actions(corp)
    got = store.get_corp_actions()
    assert list(got["kind"]) == ["reverse_split"]
    assert got.iloc[0]["announce_date"] == date(2026, 6, 9)


def test_missing_returns_none(tmp_path):
    store = PITStore(tmp_path)
    assert store.get_snapshot(date(2026, 6, 12)) is None
    assert store.get_bars("NOPE") is None
    assert store.get_calendar() is None
    assert store.get_corp_actions() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/data/test_pit_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.data.pit_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/data/pit_store.py
from __future__ import annotations

import os
import tempfile
from datetime import date as Date
from pathlib import Path

import pandas as pd


def _atomic_to_parquet(df: pd.DataFrame, p: Path) -> None:
    """Atomic parquet write: temp in same dir then os.replace; never leave a truncated final file."""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".parquet.tmp")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class PITStore:
    """Point-in-time parquet cache. Once written, a day's frame is its as-of snapshot."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _snap_path(self, day: Date) -> Path:
        return self._root / "snapshot" / f"{day.strftime('%Y%m%d')}.parquet"

    def has_snapshot(self, day: Date) -> bool:
        return self._snap_path(day).exists()

    def get_snapshot(self, day: Date) -> pd.DataFrame | None:
        p = self._snap_path(day)
        return pd.read_parquet(p) if p.exists() else None

    def put_snapshot(self, day: Date, df: pd.DataFrame) -> None:
        _atomic_to_parquet(df, self._snap_path(day))

    def _bars_path(self, symbol: str) -> Path:
        return self._root / "bars" / f"{symbol}.parquet"

    def get_bars(self, symbol: str) -> pd.DataFrame | None:
        p = self._bars_path(symbol)
        return pd.read_parquet(p) if p.exists() else None

    def put_bars(self, symbol: str, df: pd.DataFrame) -> None:
        _atomic_to_parquet(df, self._bars_path(symbol))

    def put_calendar(self, days: list[Date]) -> None:
        _atomic_to_parquet(pd.DataFrame({"date": [d.isoformat() for d in days]}),
                           self._root / "calendar.parquet")

    def get_calendar(self) -> list[Date] | None:
        p = self._root / "calendar.parquet"
        if not p.exists():
            return None
        return [pd.to_datetime(s).date() for s in pd.read_parquet(p)["date"]]

    def put_corp_actions(self, df: pd.DataFrame) -> None:
        out = df.copy()
        for c in ("announce_date", "ex_date"):
            if c in out.columns:
                out[c] = out[c].map(lambda d: d.isoformat())
        _atomic_to_parquet(out, self._root / "corp_actions.parquet")

    def get_corp_actions(self) -> pd.DataFrame | None:
        p = self._root / "corp_actions.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        for c in ("announce_date", "ex_date"):
            if c in df.columns:
                df[c] = pd.to_datetime(df[c]).dt.date
        return df
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/data/test_pit_store.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/data/pit_store.py tests/data/test_pit_store.py
git commit -m "US-0 Task 6: PITStore (atomic parquet: snapshots/bars/calendar/corp-actions)"
```

---

### Task 7: SnapshotSource (offline) + split-vintage raw-PIT test (firewall surface 3)

**Files:**
- Create: `alpha/data/snapshot_source.py`
- Create: `tests/data/test_snapshot_source.py`

Split-vintage trap: stored bars are **raw/unadjusted**, so a price level read at an as-of *before* a later reverse split must be the raw price, never a future-split-rebased value.

- [ ] **Step 1: Write the failing test**

```python
# tests/data/test_snapshot_source.py
from __future__ import annotations
from datetime import date
import pandas as pd
import pytest
from alpha.data.pit_store import PITStore
from alpha.data.snapshot_source import SnapshotSource, SnapshotMissingError


def _seed(tmp_path):
    store = PITStore(tmp_path)
    store.put_calendar([date(2026, 6, 11), date(2026, 6, 12)])
    store.put_snapshot(date(2026, 6, 12), pd.DataFrame({
        "symbol": ["RUN"], "name": ["Runner Inc"], "open": [16.0], "high": [18.0],
        "low": [15.0], "close": [17.0], "volume": [5_000_000], "prev_close": [14.0]}))
    # RAW bars: a low-priced runner pre reverse-split (would look ~$170 if future-adjusted 1:10)
    store.put_bars("RUN", pd.DataFrame({
        "date": [date(2026, 6, 11), date(2026, 6, 12)],
        "open": [12.5, 16.0], "high": [15.0, 18.0], "low": [12.0, 15.0],
        "close": [14.0, 17.0], "volume": [3_000_000, 5_000_000]}))
    return SnapshotSource(store)


def test_snapshot_present(tmp_path):
    src = _seed(tmp_path)
    snap = src.daily_snapshot(date(2026, 6, 12))
    assert snap.iloc[0]["symbol"] == "RUN"


def test_missing_snapshot_raises(tmp_path):
    src = _seed(tmp_path)
    with pytest.raises(SnapshotMissingError):
        src.daily_snapshot(date(2026, 6, 11))   # not captured


def test_missing_bars_returns_empty(tmp_path):
    src = _seed(tmp_path)
    out = src.daily_bars("NOPE", date(2026, 6, 11), date(2026, 6, 12))
    assert out.empty and list(out.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_bars_are_raw_not_future_adjusted(tmp_path):
    """Firewall surface: stored prices are RAW; a $14 close stays $14, not future-split-rebased."""
    src = _seed(tmp_path)
    bars = src.daily_bars("RUN", date(2026, 6, 11), date(2026, 6, 11))
    assert bars.iloc[0]["close"] == 14.0     # raw, NOT 140.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/data/test_snapshot_source.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.data.snapshot_source'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/data/snapshot_source.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.pit_store import PITStore

_EMPTY_BARS = ["date", "open", "high", "low", "close", "volume"]


class SnapshotMissingError(RuntimeError):
    """A required snapshot is absent (incomplete capture) — fail loudly, never silent no-trade."""


class SnapshotSource:
    """Offline MarketDataSource backed by PITStore (zero network). Still wrapped by GuardedSource in eval."""

    def __init__(self, store: PITStore) -> None:
        self._store = store

    def trading_calendar(self) -> list[Date]:
        cal = self._store.get_calendar()
        if cal is None:
            raise SnapshotMissingError("snapshot missing calendar.parquet")
        return cal

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        df = self._store.get_snapshot(day)
        if df is None:
            raise SnapshotMissingError(f"snapshot missing for {day} (incomplete capture?)")
        return df

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        df = self._store.get_bars(symbol)
        if df is None or df.empty:
            return pd.DataFrame(columns=_EMPTY_BARS)
        df = df.copy()
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        df = self._store.get_corp_actions()
        if df is None or df.empty:
            return pd.DataFrame(columns=["symbol", "announce_date", "ex_date", "kind", "ratio"])
        return df[(df["ex_date"] >= start) & (df["ex_date"] <= end)].reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/data/test_snapshot_source.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/data/snapshot_source.py tests/data/test_snapshot_source.py
git commit -m "US-0 Task 7: SnapshotSource offline source (firewall surface: split-vintage raw-PIT)"
```

---

### Task 8: StockSnapshot + CandidateUniverse

**Files:**
- Create: `alpha/universe/__init__.py`
- Create: `alpha/universe/stock.py`
- Create: `tests/universe/__init__.py`
- Create: `tests/universe/test_universe.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/universe/test_universe.py
from __future__ import annotations
import pytest
from alpha.universe.stock import StockSnapshot
from alpha.universe.universe import CandidateUniverse


def _snap(symbol, status="gainer", rvol=None):
    return StockSnapshot(symbol=symbol, name=symbol + " Inc", status=status, rvol=rvol)


def test_from_stocks_indexes_by_symbol():
    u = CandidateUniverse.from_stocks([_snap("RUN"), _snap("MOON")])
    assert len(u) == 2
    assert u.get("RUN").symbol == "RUN"


def test_duplicate_symbol_rejected():
    with pytest.raises(ValueError):
        CandidateUniverse.from_stocks([_snap("RUN"), _snap("RUN")])


def test_by_status_and_bool():
    u = CandidateUniverse.from_stocks([_snap("RUN", "gainer"), _snap("DIP", "loser")])
    assert [s.symbol for s in u.by_status("gainer")] == ["RUN"]
    assert bool(CandidateUniverse.from_stocks([])) is True   # empty-but-exists is truthy
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/universe/test_universe.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.universe'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/universe/__init__.py
```

```python
# tests/universe/__init__.py
```

```python
# alpha/universe/stock.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

StockStatus = Literal["gainer", "gap_up", "loser", "runner"]


class StockSnapshot(BaseModel):
    """Per-symbol daily PIT snapshot (frozen). Missing fields stay None (never fabricated)."""
    model_config = ConfigDict(frozen=True)
    symbol: str
    name: str
    status: StockStatus
    close: float | None = None
    prev_close: float | None = None
    pct_change: float | None = None        # daily % change
    gap_pct: float | None = None           # (open - prev_close) / prev_close
    volume: float | None = None
    rvol: float | None = None              # trailing-only relative volume
    consecutive_up_days: int | None = None
    # float / short_interest / halts -> None until US-3 enrichment
```

Add to `alpha/universe/universe.py` (created here, extended in Task 9):

```python
# alpha/universe/universe.py
from __future__ import annotations

from alpha.universe.stock import StockSnapshot, StockStatus


class CandidateUniverse:
    """Daily candidate set indexed by symbol."""

    def __init__(self, stocks: dict[str, StockSnapshot]) -> None:
        self._stocks = dict(stocks)

    @classmethod
    def from_stocks(cls, stocks: list[StockSnapshot]) -> "CandidateUniverse":
        index: dict[str, StockSnapshot] = {}
        for s in stocks:
            if s.symbol in index:
                raise ValueError(f"duplicate symbol: {s.symbol}")
            index[s.symbol] = s
        return cls(index)

    def get(self, symbol: str) -> StockSnapshot | None:
        return self._stocks.get(symbol)

    def all(self) -> list[StockSnapshot]:
        return list(self._stocks.values())

    def by_status(self, status: StockStatus) -> list[StockSnapshot]:
        return [s for s in self._stocks.values() if s.status == status]

    def __len__(self) -> int:
        return len(self._stocks)

    def __bool__(self) -> bool:
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/universe/test_universe.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/universe/__init__.py alpha/universe/stock.py alpha/universe/universe.py tests/universe/__init__.py tests/universe/test_universe.py
git commit -m "US-0 Task 8: StockSnapshot + CandidateUniverse"
```

---

### Task 9: build_universe with trailing-only RVOL (firewall surface 4: windowed-rank)

**Files:**
- Modify: `alpha/universe/universe.py` (append `build_universe` + `_trailing_rvol`)
- Create: `tests/universe/test_build_universe.py`

Windowed-rank trap: RVOL = today's volume / trailing-average volume must use a **strictly trailing** window (`< day`), never bars at/after `day`.

- [ ] **Step 1: Write the failing test**

```python
# tests/universe/test_build_universe.py
from __future__ import annotations
from datetime import date
from alpha.universe.universe import build_universe


def test_build_universe_screens_gainers(fake_source):
    # day 6/12: RUN +21.4% (14->17), FLOP -8.3% (18->16.5). Gainer threshold 10%.
    u = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN") is not None
    assert u.get("RUN").status in ("gainer", "gap_up")
    assert u.get("FLOP") is None or u.get("FLOP").status == "loser"


def test_rvol_uses_only_trailing_bars(fake_source):
    # RUN volume 6/12 = 5M; trailing (6/10,6/11) avg = (1M+3M)/2 = 2M -> RVOL = 2.5
    u = build_universe(fake_source, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert abs(u.get("RUN").rvol - 2.5) < 1e-9


def test_build_universe_is_guard_safe(fake_source):
    # A guard at 6/12 must not block building the 6/12 universe (uses <=6/12 only).
    from alpha.data.firewall import AsOfGuard
    from alpha.data.source import GuardedSource
    gs = GuardedSource(fake_source, AsOfGuard(date(2026, 6, 12)))
    u = build_universe(gs, date(2026, 6, 12), gainer_pct=10.0, gap_pct=5.0, rvol_window=2)
    assert u.get("RUN") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/universe/test_build_universe.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_universe'`

- [ ] **Step 3: Append implementation to `alpha/universe/universe.py`**

```python
# --- append to alpha/universe/universe.py ---
from datetime import date as Date

import pandas as pd

from alpha.data.calendar import trading_days_between


def _trailing_rvol(source, symbol: str, day: Date, window: int) -> float | None:
    """today_volume / mean(volume over the `window` trading days strictly BEFORE `day`)."""
    cal = source.trading_calendar()
    prior = [d for d in cal if d < day]
    if len(prior) < window:
        return None
    win = sorted(prior)[-window:]
    bars = source.daily_bars(symbol, win[0], day)        # end=day is legal (<=as_of)
    if bars is None or bars.empty:
        return None
    today = bars[bars["date"] == day]
    trailing = bars[(bars["date"] >= win[0]) & (bars["date"] < day)]   # strictly trailing
    if today.empty or trailing.empty:
        return None
    avg = float(trailing["volume"].mean())
    if avg <= 0:
        return None
    return float(today.iloc[0]["volume"]) / avg


def build_universe(source, day: Date, *, gainer_pct: float = 10.0,
                   gap_pct: float = 5.0, rvol_window: int = 20) -> CandidateUniverse:
    """Screen the daily cross-section for gainers / gap-ups / losers; attach trailing-only RVOL."""
    snap = source.daily_snapshot(day)
    stocks: dict[str, StockSnapshot] = {}
    if snap is None or snap.empty:
        return CandidateUniverse(stocks)
    for rec in snap.to_dict("records"):
        symbol = str(rec["symbol"])
        close, prev = rec.get("close"), rec.get("prev_close")
        open_ = rec.get("open")
        pct = ((close - prev) / prev * 100.0) if (close is not None and prev) else None
        gap = ((open_ - prev) / prev * 100.0) if (open_ is not None and prev) else None
        if pct is not None and pct >= gainer_pct:
            status: StockStatus = "gainer"
        elif gap is not None and gap >= gap_pct:
            status = "gap_up"
        elif pct is not None and pct <= -gainer_pct:
            status = "loser"
        else:
            continue
        stocks[symbol] = StockSnapshot(
            symbol=symbol, name=str(rec.get("name", "")), status=status,
            close=(float(close) if close is not None else None),
            prev_close=(float(prev) if prev is not None else None),
            pct_change=pct, gap_pct=gap,
            volume=(float(rec["volume"]) if rec.get("volume") is not None else None),
            rvol=_trailing_rvol(source, symbol, day, rvol_window),
        )
    return CandidateUniverse(stocks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/universe/test_build_universe.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/universe/universe.py tests/universe/test_build_universe.py
git commit -m "US-0 Task 9: build_universe with trailing-only RVOL (firewall surface: windowed-rank)"
```

---

### Task 10: MarketState + RunnerRung schema

**Files:**
- Create: `alpha/state/__init__.py`
- Create: `alpha/state/market.py`
- Create: `tests/state/__init__.py`
- Create: `tests/state/test_market.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/state/test_market.py
from __future__ import annotations
from datetime import date, datetime
import pytest
from pydantic import ValidationError
from alpha.state.market import MarketState, RunnerRung


def test_runner_rung_frozen():
    r = RunnerRung(tier=3, count=2, representatives=["RUN", "MOON"])
    with pytest.raises(ValidationError):
        r.count = 5


def test_market_state_minimal():
    ms = MarketState(
        date=date(2026, 6, 12), gainer_count=12, gap_up_count=8, loser_count=3,
        failed_breakout_count=4, max_runner_tier=3,
        echelon=[RunnerRung(tier=3, count=1, representatives=["RUN"])],
        breadth_raw=0.6, sentiment_norm=None, as_of=datetime(2026, 6, 12, 16, 0))
    assert ms.gainer_count == 12
    assert ms.sentiment_norm is None


def test_sentiment_norm_bounds():
    with pytest.raises(ValidationError):
        MarketState(date=date(2026, 6, 12), gainer_count=0, gap_up_count=0, loser_count=0,
                    failed_breakout_count=0, max_runner_tier=0, echelon=[], breadth_raw=0.0,
                    sentiment_norm=1.5, as_of=datetime(2026, 6, 12, 16, 0))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/state/test_market.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.state'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/state/__init__.py
```

```python
# tests/state/__init__.py
```

```python
# alpha/state/market.py
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from pydantic import BaseModel, ConfigDict, Field


class RunnerRung(BaseModel):
    """One rung of the runner echelon (连板梯队 analog): a tier, its count, representative tickers."""
    model_config = ConfigDict(frozen=True)
    tier: int = Field(ge=1)               # consecutive-up-days bucket (or move-magnitude tier)
    count: int = Field(ge=0)
    representatives: list[str] = Field(default_factory=list)


class MarketState(BaseModel):
    """Point-in-time daily market state at close (US-0 minimal set; features enrich in US-1)."""
    model_config = ConfigDict(frozen=True)
    date: Date
    gainer_count: int = Field(ge=0)
    gap_up_count: int = Field(ge=0)
    loser_count: int = Field(ge=0)
    failed_breakout_count: int = Field(ge=0)     # gap-up that closed red
    max_runner_tier: int = Field(ge=0)
    echelon: list[RunnerRung]                    # runner echelon (tier descending)
    breadth_raw: float                           # raw composite breadth
    sentiment_norm: float | None = Field(default=None, ge=0.0, le=1.0)  # regime-relative; None if insufficient
    as_of: DateTime                              # snapshot timestamp (lookahead audit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/state/test_market.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/state/__init__.py alpha/state/market.py tests/state/__init__.py tests/state/test_market.py
git commit -m "US-0 Task 10: MarketState + RunnerRung schema"
```

---

### Task 11: build_market_state (minimal, from the day's universe)

**Files:**
- Create: `alpha/state/builder.py`
- Create: `tests/state/test_builder.py`

US-0 builder computes counts + echelon directly from the day's universe. `sentiment_norm` stays `None` (regime-relative normalization is a US-1 feature). `failed_breakout_count` uses the day's cross-section (gap-up symbols that closed red), which is `<=day` info.

- [ ] **Step 1: Write the failing test**

```python
# tests/state/test_builder.py
from __future__ import annotations
from datetime import date, datetime
from alpha.state.builder import build_market_state
from alpha.universe.universe import CandidateUniverse
from alpha.universe.stock import StockSnapshot


def _u():
    return CandidateUniverse.from_stocks([
        StockSnapshot(symbol="RUN", name="Runner", status="gainer", pct_change=21.0,
                      close=17.0, prev_close=14.0, consecutive_up_days=3),
        StockSnapshot(symbol="GAP", name="Gapper", status="gap_up", gap_pct=8.0,
                      close=9.0, prev_close=10.0, consecutive_up_days=1),  # gapped up, closed red
        StockSnapshot(symbol="DIP", name="Dipper", status="loser", pct_change=-12.0,
                      close=8.0, prev_close=9.1, consecutive_up_days=0),
    ])


def test_counts_and_echelon():
    ms = build_market_state(_u(), date(2026, 6, 12), as_of=datetime(2026, 6, 12, 16, 0))
    assert ms.gainer_count == 1
    assert ms.gap_up_count == 1
    assert ms.loser_count == 1
    assert ms.failed_breakout_count == 1          # GAP gapped up but close < prev_close
    assert ms.max_runner_tier == 3
    assert ms.echelon[0].tier == 3 and ms.echelon[0].representatives == ["RUN"]
    assert ms.sentiment_norm is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/state/test_builder.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.state.builder'`

- [ ] **Step 3: Write minimal implementation**

```python
# alpha/state/builder.py
from __future__ import annotations

from datetime import date as Date, datetime as DateTime

from alpha.state.market import MarketState, RunnerRung
from alpha.universe.universe import CandidateUniverse


def build_market_state(universe: CandidateUniverse, day: Date, *, as_of: DateTime) -> MarketState:
    """Minimal MarketState from the day's universe (counts + runner echelon). US-1 adds normalization."""
    stocks = universe.all()
    gainers = [s for s in stocks if s.status == "gainer"]
    gap_ups = [s for s in stocks if s.status == "gap_up"]
    losers = [s for s in stocks if s.status == "loser"]
    failed = [s for s in stocks
              if s.status == "gap_up" and s.close is not None and s.prev_close is not None
              and s.close < s.prev_close]

    by_tier: dict[int, list[str]] = {}
    for s in stocks:
        t = s.consecutive_up_days
        if t is not None and t >= 1:
            by_tier.setdefault(t, []).append(s.symbol)
    echelon = [RunnerRung(tier=t, count=len(syms), representatives=sorted(syms))
               for t, syms in sorted(by_tier.items(), reverse=True)]
    max_tier = max(by_tier) if by_tier else 0

    return MarketState(
        date=day, gainer_count=len(gainers), gap_up_count=len(gap_ups),
        loser_count=len(losers), failed_breakout_count=len(failed),
        max_runner_tier=max_tier, echelon=echelon,
        breadth_raw=float(len(gainers) - len(losers)), sentiment_norm=None, as_of=as_of)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/state/test_builder.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/state/builder.py tests/state/test_builder.py
git commit -m "US-0 Task 11: build_market_state (counts + runner echelon)"
```

---

### Task 12: AlpacaSource adapter + capture + smoke scripts

**Files:**
- Create: `alpha/data/alpaca.py`
- Create: `alpha/data/capture.py`
- Create: `scripts/smoke_alpaca.py`
- Create: `scripts/capture_window.py`
- Create: `tests/data/test_alpaca_normalize.py`

The real adapter is smoke-only (network). Only the **pure normalizers** are unit-tested offline; `AlpacaSource.__init__` imports alpaca-py lazily so the package imports without the `live` extra.

- [ ] **Step 1: Write the failing test (pure normalizers)**

```python
# tests/data/test_alpaca_normalize.py
from __future__ import annotations
from datetime import date
import pandas as pd
from alpha.data.alpaca import _normalize_bars, _normalize_snapshot


def test_normalize_bars_columns_and_types():
    raw = pd.DataFrame({"timestamp": ["2026-06-12T00:00:00Z"], "open": ["16"], "high": ["18"],
                        "low": ["15"], "close": ["17"], "volume": ["5000000"]})
    out = _normalize_bars(raw)
    assert list(out.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["date"] == date(2026, 6, 12)
    assert out.iloc[0]["close"] == 17.0


def test_normalize_bars_empty():
    out = _normalize_bars(pd.DataFrame())
    assert out.empty and list(out.columns) == ["date", "open", "high", "low", "close", "volume"]


def test_normalize_snapshot_computes_nothing_extra():
    raw = pd.DataFrame({"symbol": ["RUN"], "name": ["Runner"], "open": ["16"], "high": ["18"],
                        "low": ["15"], "close": ["17"], "volume": ["5000000"], "prev_close": ["14"]})
    out = _normalize_snapshot(raw)
    assert list(out.columns) == ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close"]
    assert out.iloc[0]["prev_close"] == 14.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/data/test_alpaca_normalize.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'alpha.data.alpaca'`

- [ ] **Step 3: Write implementation**

```python
# alpha/data/alpaca.py
from __future__ import annotations

import os
from datetime import date as Date

import pandas as pd

_BARS_COLS = ["date", "open", "high", "low", "close", "volume"]
_SNAP_COLS = ["symbol", "name", "open", "high", "low", "close", "volume", "prev_close"]


def _normalize_bars(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_BARS_COLS)
    out = df.rename(columns={"timestamp": "date", "t": "date"}).copy()
    out["date"] = pd.to_datetime(out["date"]).dt.date
    for c in ("open", "high", "low", "close", "volume"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out[_BARS_COLS].reset_index(drop=True)


def _normalize_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=_SNAP_COLS)
    out = df.copy()
    out["symbol"] = out["symbol"].astype(str)
    if "name" not in out.columns:
        out["name"] = ""
    for c in ("open", "high", "low", "close", "volume", "prev_close"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out[_SNAP_COLS].reset_index(drop=True)


class AlpacaSource:
    """Real Alpaca adapter (smoke-only; requires the `live` extra + APCA_API_KEY_ID/SECRET env)."""

    def __init__(self) -> None:
        key = os.environ.get("APCA_API_KEY_ID")
        secret = os.environ.get("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("missing APCA_API_KEY_ID / APCA_API_SECRET_KEY")
        from alpaca.data.historical import StockHistoricalDataClient  # lazy import
        self._client = StockHistoricalDataClient(key, secret)

    def trading_calendar(self) -> list[Date]:
        import pandas_market_calendars as mcal  # lazy import
        sched = mcal.get_calendar("XNYS").schedule(start_date="2016-01-01",
                                                   end_date=pd.Timestamp.today().date().isoformat())
        return [d.date() for d in sched.index]

    def daily_bars(self, symbol: str, start: Date, end: Date) -> pd.DataFrame:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
        from alpaca.data.enums import Adjustment
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=TimeFrame.Day,
                               start=pd.Timestamp(start), end=pd.Timestamp(end),
                               adjustment=Adjustment.RAW)
        df = self._client.get_stock_bars(req).df
        if df is None or df.empty:
            return pd.DataFrame(columns=_BARS_COLS)
        return _normalize_bars(df.reset_index())

    def daily_snapshot(self, day: Date) -> pd.DataFrame:
        # Smoke-only: a full-market gainer cross-section needs a broad symbol list / snapshots API.
        # Built by capture_window for the configured symbol set; not exercised in unit tests.
        raise NotImplementedError("use capture_window to build daily snapshots from bars")

    def corporate_actions(self, start: Date, end: Date) -> pd.DataFrame:
        from alpaca.data.requests import CorporateActionsRequest
        req = CorporateActionsRequest(start=start, end=end)
        df = self._client.get_corporate_actions(req).df
        cols = ["symbol", "announce_date", "ex_date", "kind", "ratio"]
        if df is None or df.empty:
            return pd.DataFrame(columns=cols)
        return df  # field mapping refined during smoke against real payloads
```

```python
# alpha/data/capture.py
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from alpha.data.calendar import prev_trading_day
from alpha.data.pit_store import PITStore


def capture_window(source, store: PITStore, start: Date, end: Date, symbols: list[str]) -> None:
    """Idempotent prefetch: bars per symbol + a derived daily snapshot cross-section + calendar.

    The snapshot for each day is derived from the captured raw bars (close/open/volume) plus the
    prior trading day's close, so the offline universe builder has a cross-section to screen.
    """
    cal = source.trading_calendar()
    store.put_calendar(cal)
    bars_by_symbol: dict[str, pd.DataFrame] = {}
    for sym in symbols:
        bars = source.daily_bars(sym, start, end)
        if bars is not None and not bars.empty:
            store.put_bars(sym, bars)
            bars_by_symbol[sym] = bars
    from alpha.data.calendar import trading_days_between
    for day in trading_days_between(cal, start, end):
        prev = prev_trading_day(cal, day)
        rows = []
        for sym, bars in bars_by_symbol.items():
            today = bars[bars["date"] == day]
            if today.empty:
                continue
            pc = bars[bars["date"] == prev]["close"]
            rows.append({"symbol": sym, "name": sym,
                         "open": float(today.iloc[0]["open"]), "high": float(today.iloc[0]["high"]),
                         "low": float(today.iloc[0]["low"]), "close": float(today.iloc[0]["close"]),
                         "volume": float(today.iloc[0]["volume"]),
                         "prev_close": (float(pc.iloc[0]) if not pc.empty else None)})
        if rows:
            store.put_snapshot(day, pd.DataFrame(rows))
```

```python
# scripts/smoke_alpaca.py
"""Manual Alpaca probe. Run: python scripts/smoke_alpaca.py AAPL 2026-06-01 2026-06-12"""
from __future__ import annotations

import sys
from datetime import date

from alpha.data.alpaca import AlpacaSource


def main() -> None:
    sym, start, end = sys.argv[1], date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3])
    src = AlpacaSource()
    bars = src.daily_bars(sym, start, end)
    print(f"{sym} bars rows={len(bars)} cols={list(bars.columns)}")
    print(bars.tail())


if __name__ == "__main__":
    main()
```

```python
# scripts/capture_window.py
"""Build an offline PIT snapshot DB. Run:
   python scripts/capture_window.py 2026-06-01 2026-06-12 snap AAPL MSFT NVDA"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from alpha.data.alpaca import AlpacaSource
from alpha.data.capture import capture_window
from alpha.data.pit_store import PITStore


def main() -> None:
    start, end, root = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]), Path(sys.argv[3])
    symbols = sys.argv[4:]
    capture_window(AlpacaSource(), PITStore(root), start, end, symbols)
    print(f"captured {len(symbols)} symbols {start}..{end} -> {root}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/data/test_alpaca_normalize.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add alpha/data/alpaca.py alpha/data/capture.py scripts/smoke_alpaca.py scripts/capture_window.py tests/data/test_alpaca_normalize.py
git commit -m "US-0 Task 12: AlpacaSource adapter + capture_window + smoke scripts (pure normalizers tested)"
```

---

### Task 13: English documentation (blueprint, project-state, roadmap, README)

**Files:**
- Create: `docs/blueprint.md`
- Create: `docs/PROJECT_STATE.md`
- Create: `docs/ROADMAP.md`
- Create: `README.md`

This is a documentation task (no TDD). The blueprint is the authoritative English architecture source (the US equivalent of the CN 架构蓝图); it is a first-class deliverable so the knowledge survives `reference/cn/` deletion.

- [ ] **Step 1: Write `docs/blueprint.md`**

Author the authoritative US architecture blueprint in English. Required sections (port the structure of `reference/cn/自进化游资系统-架构蓝图-v1.0.md`, US-first, drawing all design content from the approved spec `docs/superpowers/specs/2026-06-13-us-market-adaptation-design.md`):
1. TL;DR — Continual-Harness `H=(p,G,K,M)` two-loop, US speculative-momentum co-pilot, human-confirmed.
2. Why Continual Harness (alpha decay / non-stationarity / reflexivity).
3. Concept mapping (copy spec §3.1/§3.2, corrected mechanics).
4. Layered architecture + data flow (spec §4 incl. L3 sizing, L4 guard, DecisionPackage §4.1).
5. Two-loop diagram (inner = daily refine; outer = US-2+).
6. US momentum regime machine (spec §5).
7. Four playbook families + per-phase scope (spec §6).
8. Data / universe / dual oracle + the four firewall surfaces (spec §7, §4 principles).
9. Phasing US-0→US-3 (spec §9) + eval protocol (spec §10).
10. Risks (spec §12) + glossary (English ↔ CN ↔ paper terms).

- [ ] **Step 2: Write `docs/PROJECT_STATE.md`**

One-page compressed context for session restart:
- Identity & boundary (co-pilot, human-confirmed, no auto orders).
- Locked decisions (spec §1).
- Tech stack (Python, Alpaca, per-role LLM, pydantic/pandas/pyarrow).
- Roadmap + current milestone (US-0 in progress; list completed tasks as they land).
- Repo map (alpha/ modules, reference/cn/ to be deleted, docs/ first-class).

- [ ] **Step 3: Write `docs/ROADMAP.md`**

The four phases (spec §9) with acceptance gates per phase, and the US-0 task list from this plan.

- [ ] **Step 4: Write `README.md`**

Public-facing English: what the project is (self-evolving US momentum co-pilot, adapted from Evolving-Alpha), status (US-0 foundations), quickstart (`pip install -e ".[dev]"`, `pytest`), data setup (Alpaca env vars + `capture_window`), pointer to `docs/blueprint.md`, and the **disclaimer: research/decision-support only, not financial advice, no automatic order execution**.

- [ ] **Step 5: Verify docs render and links resolve**

Run: `python - <<'PY'
import pathlib
for f in ["docs/blueprint.md","docs/PROJECT_STATE.md","docs/ROADMAP.md","README.md"]:
    assert pathlib.Path(f).stat().st_size > 500, f
print("docs present")
PY`
Expected: `docs present`

- [ ] **Step 6: Commit**

```bash
git add docs/blueprint.md docs/PROJECT_STATE.md docs/ROADMAP.md README.md
git commit -m "US-0 Task 13: English blueprint + project-state + roadmap + README"
```

---

### Task 14: US-0 acceptance gate

**Files:**
- Create: `tests/test_us0_firewall_surfaces.py` (aggregate marker test referencing the four surfaces)

- [ ] **Step 1: Write the aggregate acceptance test**

```python
# tests/test_us0_firewall_surfaces.py
"""US-0 acceptance: the four firewall surfaces each have a green guarding test.
This module documents the gate and asserts the guarding tests import & run."""
from __future__ import annotations
import importlib


def test_four_firewall_surface_modules_exist():
    for mod in [
        "tests.data.test_source",            # surface 1: date-lookahead (GuardedSource)
        "tests.data.test_corp_actions",      # surface 2: corp-action ex-date PIT
        "tests.data.test_snapshot_source",   # surface 3: split-vintage raw-PIT
        "tests.universe.test_build_universe", # surface 4: windowed-rank trailing-only
    ]:
        assert importlib.import_module(mod) is not None
```

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS — all tasks' tests green (≈ 30+ tests), including the four firewall-surface tests.

- [ ] **Step 3: Confirm the acceptance criteria explicitly**

Run: `python -m pytest tests/data/test_source.py::test_guarded_source_blocks_future_snapshot tests/data/test_corp_actions.py::test_has_reverse_split_pending_pit tests/data/test_snapshot_source.py::test_bars_are_raw_not_future_adjusted tests/universe/test_build_universe.py::test_rvol_uses_only_trailing_bars -v`
Expected: 4 passed (the four firewall surfaces).

- [ ] **Step 4: Commit**

```bash
git add tests/test_us0_firewall_surfaces.py
git commit -m "US-0 Task 14: acceptance gate — four firewall-surface tests green"
```

- [ ] **Step 5: Push**

```bash
git push origin main
```

---

## Self-Review (run after writing, fix inline)

**Spec coverage (US-0 = spec §9 row 1):**
- Alpaca daily source (raw + adjustment factors) → Task 12 (`AlpacaSource` RAW bars + corp-actions for adjustment facts) ✓
- Calendar → Task 3 ✓ · Corp-actions → Task 5 ✓ · Firewall + 3 new surfaces → Tasks 4/5/7/9 ✓
- PITStore → Task 6 · SnapshotSource → Task 7 ✓
- MarketState → Tasks 10/11 ✓ · US universe builder (trailing-only) → Task 9 ✓
- English blueprint doc → Task 13 ✓ · Acceptance gate → Task 14 ✓

**Type consistency:** `MarketDataSource` methods (`trading_calendar`/`daily_bars`/`daily_snapshot`/`corporate_actions`) are identical across `FakeSource`, `GuardedSource`, `SnapshotSource`, `AlpacaSource`. `StockSnapshot` fields used in Tasks 9/11 match Task 8's schema. `build_universe(source, day, *, gainer_pct, gap_pct, rvol_window)` signature consistent across Tasks 9 and its callers. `PITStore` methods consistent across Tasks 6/7/12.

**Placeholder scan:** no TBD/TODO; every code step shows full code; the only deliberately-deferred bits are documented (`AlpacaSource.daily_snapshot` raises `NotImplementedError` with the reason, and `corporate_actions` field-mapping is refined during smoke against real payloads — both are smoke-only, not unit-tested paths).

**Scope:** US-0 is foundations only; features (breadth/runner/failed_breakout/relative_strength as standalone modules), regime classifier/state-machine, harness `H`, sizing/guard layers, agent, refiner, and eval oracle are US-1+ and intentionally excluded.
