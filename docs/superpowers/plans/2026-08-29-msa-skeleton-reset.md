# Market-Strategy-Account Skeleton Reset — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reset this repo to the market-strategy-account skeleton: one Python package `alpaca_kit` (importable lib + MCP server) carrying the old `alpha/data` island plus a new Alpaca paper-account client, with `strategies/` and `dsh/` scaffolding around it.

**Architecture:** Approach A ("one package, two faces") per the spec. Old code is first pruned to the migration island (still green), then renamed wholesale to `alpaca_kit`, then new modules (account, replay, MCP tools/server) are TDD'd on top. dsh is the agent runtime; this repo ships only data/account code, strategy scaffolding, and dsh config/skills.

**Tech Stack:** Python 3.11+, pandas/pydantic/pyarrow, official `mcp` SDK (FastMCP), pytest (fully offline, no keys).

**Spec:** `docs/superpowers/specs/2026-08-29-market-strategy-account-skeleton-design.md`

## Global Constraints

- Everything happens on branch `reset/market-strategy-account`; `main` is never touched.
- Full suite `python -m pytest -q` must be green at the end of EVERY task; each task ends in a commit.
- Tests stay fully offline: no network, no keys (FakeSource + monkeypatched `_get_json` / injected factories).
- macOS: in-place sed is `sed -i '' -e ...` (empty-string backup arg).
- Commit messages: plain text only, NO backticks/`$()`/parens-with-commands (shell eats them); when in doubt write the message to a file and `git commit -F <file>`.
- PIT conventions carried verbatim: prices RAW/unadjusted; corp actions keyed on `announce_date`; registry/lib return RAW sources — wrapping in `GuardedSource(AsOfGuard(...))` is the caller's job; the MCP tool layer IS that caller.
- Paper-only pin: `TradingClient.place_order` refuses a non-paper base URL at code level (test-pinned).
- `data/pit/` and `.env.*` are gitignored; backups live at `~/Desktop/self-evolve/alpha-us-backup-20260829/`.

---

### Task 1: Reset branch + green baseline

**Files:**
- No file changes; branch + baseline only.

**Interfaces:**
- Consumes: current `feat/body-six-components` HEAD (411d195 or later).
- Produces: branch `reset/market-strategy-account` with a recorded green baseline.

- [ ] **Step 1: Create the reset branch**

```bash
cd /Users/pan/Desktop/self-evolve/evolving-alpha-us
git checkout -b reset/market-strategy-account
```

- [ ] **Step 2: Verify the backup exists (abort if not)**

```bash
ls ~/Desktop/self-evolve/alpha-us-backup-20260829/verdict_pit_2yr/CHECKSUMS \
   ~/Desktop/self-evolve/alpha-us-backup-20260829/.env.alpaca
```
Expected: both paths print. If either is missing, STOP — restore the backup before any deletion.

- [ ] **Step 3: Record the green baseline**

Run: `python -m pytest -q`
Expected: full suite passes (~2046 tests). Note the count.

- [ ] **Step 4: Commit checkpoint (empty commit marking the reset start)**

```bash
git commit --allow-empty -m "chore: begin market-strategy-account reset from green baseline"
```

---

### Task 2: Prune to the migration island (old paths, reduced suite green)

Delete everything that is not a migration source, while all kept code still lives at its OLD import paths. This keeps "green at every commit" honest: the reduced suite passes before any renaming starts.

**Files:**
- Keep (code): `alpha/__init__.py`, `alpha/integrity.py`, `alpha/data/` (minus `sector_map.py`), `alpha/universe/` (all), `alpha/features/{__init__,breadth,trend_template,runner,short_squeeze}.py`
- Keep (tests): `tests/__init__.py`, `tests/conftest.py` (trimmed), `tests/test_us0_firewall_surfaces.py`, `tests/data/` (minus `test_sector_map.py`), `tests/universe/` (minus `test_short_squeeze_activation.py`), `tests/features/{__init__,test_breadth,test_breadth_family,test_trend_template,test_short_squeeze,test_runner}.py` (test_runner trimmed)
- Keep (other): `pyproject.toml`, `.gitignore`, `docs/superpowers/`, `docs/research/`, `scripts/{capture_window,capture_broad,smoke_alpaca}.py`, `seeds_v2/` (consumed by Task 10), `.claude/`
- Delete: everything else (exact commands below)
- Modify: `alpha/features/runner.py` (trim), `tests/features/test_runner.py` (trim), `tests/conftest.py` (trim), `.claude/settings.json` (drop stale deny rules)

**Interfaces:**
- Consumes: nothing new.
- Produces: a repo whose ONLY Python code is the migration island at old paths; reduced suite green.

- [ ] **Step 1: Delete the old product code trees**

```bash
git rm -r -q alpha/agent alpha/arena alpha/converse alpha/eval alpha/guard alpha/harness \
  alpha/llm alpha/loop alpha/mcp alpha/memory alpha/meta alpha/refine alpha/regime \
  alpha/sizing alpha/state
git rm -q alpha/redact.py alpha/settings.py alpha/trace.py
git rm -r -q alpha_web sonia workbench seeds reference spikes third_party
git rm -q alpha/data/sector_map.py
git rm -q alpha/features/builder.py alpha/features/earnings.py alpha/features/sentiment.py \
  alpha/features/theme_breadth.py alpha/features/theme_breadth_types.py
```

- [ ] **Step 2: Delete old scripts (keep the three data producers)**

```bash
cd scripts && git rm -q calibrate_growth_clock.py calibrate_stock_clock.py calibrate_theme_clock.py \
  daily_loop.py evolve_from_episodes.py gen_tcb_lock.py inspect_episodes.py lint_doctrine.py \
  migrate_projects_to_sqlite.py refine_live.py reflect_from_tasks.py render_prompt.py \
  run_verdict.py save_decisions.py save_evolution.py scan_tradeable.py && cd ..
```

- [ ] **Step 3: Delete old tests (keep the island's tests)**

```bash
git rm -r -q tests/agent tests/arena tests/converse tests/eval tests/guard tests/harness \
  tests/llm tests/loop tests/mcp tests/memory tests/meta tests/refine tests/regime \
  tests/sizing tests/sonia tests/state tests/web tests/workbench 2>/dev/null
git rm -q tests/data/test_sector_map.py tests/universe/test_short_squeeze_activation.py
git rm -q tests/features/test_builder.py tests/features/test_earnings.py \
  tests/features/test_sentiment.py tests/features/test_theme_breadth.py
# remove any remaining top-level old-concept test modules except the firewall gate:
ls tests/*.py   # inspect: keep __init__.py, conftest.py, test_us0_firewall_surfaces.py; git rm the rest
```

- [ ] **Step 4: Delete old-concept top-level docs and artifacts**

```bash
git rm -q tcb.lock Backend-Design.md Evolving-Agent-Design-SoniaKairos.md ROADMAP.md CLAUDE.md
git rm -q docs/blueprint.md
git rm -r -q docs/doctrine docs/findings 2>/dev/null
```
(CLAUDE.md/ROADMAP.md get fresh replacements in Task 9; git history keeps the old ones.)

- [ ] **Step 5: Trim runner.py to consecutive_up_days only**

Open `alpha/features/runner.py`: delete everything from the line `def runner_echelon(` to end of file, and delete the now-unused imports that referenced `StockSnapshot`/`RunnerRung`/`alpha.state`. The file keeps only its header, the pandas/date imports it still needs, and `consecutive_up_days`.

Verify: `grep -n "runner_echelon\|alpha.state\|RunnerRung" alpha/features/runner.py` prints nothing.

- [ ] **Step 6: Trim tests/features/test_runner.py the same way**

Keep only the test functions whose names mention `consecutive_up_days` (and the imports they need: pandas, date, `consecutive_up_days`). Delete every `runner_echelon`/`StockSnapshot` test.

- [ ] **Step 7: Trim tests/conftest.py**

Keep the module header, imports, and the `fake_source` fixture EXACTLY as-is. Delete the `brain_session_isolation` fixture (and anything after it).

- [ ] **Step 8: Drop stale deny rules from .claude/settings.json**

Open `.claude/settings.json` and remove permission-deny entries that reference `reference/`, `spikes/`, or the sibling `Sonia-Kairos` repo (those trees are gone). Keep the file valid JSON; if nothing else remains, leave `{}`-level structure intact.

- [ ] **Step 9: Run the reduced suite**

Run: `python -m pytest -q`
Expected: PASS. Roughly 300–400 tests remain (tests/data 21 modules + universe 3 + features 5 + the firewall gate). If a kept test fails on an import of a deleted module, that test belongs to the old concept — `git rm` it and note it in the commit message.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "chore: prune to the migration island - data/universe/screens plus their offline tests"
```

---

### Task 3: Rename the island to alpaca_kit (+ pyproject rewrite)

One atomic rename: `git mv` every kept module into the new package layout, sed every import (code, tests, scripts), rewrite pyproject, reinstall, green.

**Files:**
- Create: `alpaca_kit/__init__.py`, `alpaca_kit/pit/__init__.py`, `alpaca_kit/feeds/__init__.py`, `alpaca_kit/features/__init__.py` (all empty)
- Move: see Step 1 mapping (module names unchanged; only package paths change)
- Modify: every `.py` under `alpaca_kit/`, `tests/`, `scripts/` (imports); `pyproject.toml`
- Test: the whole migrated suite

**Interfaces:**
- Consumes: the island at old paths (Task 2).
- Produces: the import surface every later task uses —
  `alpaca_kit.source` (MarketDataSource, FakeSource, GuardedSource), `alpaca_kit.firewall` (AsOfGuard, LookaheadError), `alpaca_kit.alpaca` (AlpacaSource), `alpaca_kit.registry` (make_source), `alpaca_kit.composite` (CompositeSource), `alpaca_kit.pit.{pit_store,snapshot_source,capture,integrity_check,calendar}` (PITStore, SnapshotSource, SnapshotMissingError, capture_window, write_checksums, verify_checksums, trading_days_between), `alpaca_kit.feeds.{edgar,finra,float_feed,earnings,short_interest,offerings,float_shares,corp_actions}`, `alpaca_kit.stock` (StockSnapshot, StockStatus), `alpaca_kit.universe` (CandidateUniverse, build_universe, build_trend_template_universe, tape_breadth, resolve_universe_screen), `alpaca_kit.features.{trend_template,breadth,runner,short_squeeze}`, `alpaca_kit.integrity` (sha256_file, sha256_canonical_json).

- [ ] **Step 1: git mv into the new layout**

```bash
mkdir -p alpaca_kit/pit alpaca_kit/feeds alpaca_kit/features
touch alpaca_kit/__init__.py alpaca_kit/pit/__init__.py alpaca_kit/feeds/__init__.py alpaca_kit/features/__init__.py
git mv alpha/data/source.py alpha/data/firewall.py alpha/data/alpaca.py \
       alpha/data/registry.py alpha/data/composite.py alpaca_kit/
git mv alpha/data/pit_store.py alpha/data/snapshot_source.py alpha/data/capture.py \
       alpha/data/integrity_check.py alpha/data/calendar.py alpaca_kit/pit/
git mv alpha/data/edgar.py alpha/data/finra.py alpha/data/float_feed.py alpha/data/earnings.py \
       alpha/data/short_interest.py alpha/data/offerings.py alpha/data/float_shares.py \
       alpha/data/corp_actions.py alpaca_kit/feeds/
git mv alpha/integrity.py alpaca_kit/integrity.py
git mv alpha/universe/stock.py alpaca_kit/stock.py
git mv alpha/universe/universe.py alpaca_kit/universe.py
git mv alpha/features/trend_template.py alpha/features/breadth.py \
       alpha/features/runner.py alpha/features/short_squeeze.py alpaca_kit/features/
git rm -r -q alpha
git add alpaca_kit
```

- [ ] **Step 2: Rewrite imports everywhere (longest-prefix first)**

```bash
PAIRS='
alpha.data.pit_store=alpaca_kit.pit.pit_store
alpha.data.snapshot_source=alpaca_kit.pit.snapshot_source
alpha.data.capture=alpaca_kit.pit.capture
alpha.data.integrity_check=alpaca_kit.pit.integrity_check
alpha.data.calendar=alpaca_kit.pit.calendar
alpha.data.edgar=alpaca_kit.feeds.edgar
alpha.data.finra=alpaca_kit.feeds.finra
alpha.data.float_feed=alpaca_kit.feeds.float_feed
alpha.data.earnings=alpaca_kit.feeds.earnings
alpha.data.short_interest=alpaca_kit.feeds.short_interest
alpha.data.offerings=alpaca_kit.feeds.offerings
alpha.data.float_shares=alpaca_kit.feeds.float_shares
alpha.data.corp_actions=alpaca_kit.feeds.corp_actions
alpha.data.source=alpaca_kit.source
alpha.data.firewall=alpaca_kit.firewall
alpha.data.alpaca=alpaca_kit.alpaca
alpha.data.registry=alpaca_kit.registry
alpha.data.composite=alpaca_kit.composite
alpha.universe.stock=alpaca_kit.stock
alpha.universe.universe=alpaca_kit.universe
alpha.features.trend_template=alpaca_kit.features.trend_template
alpha.features.breadth=alpaca_kit.features.breadth
alpha.features.runner=alpaca_kit.features.runner
alpha.features.short_squeeze=alpaca_kit.features.short_squeeze
alpha.integrity=alpaca_kit.integrity
'
for pair in $PAIRS; do
  old="${pair%%=*}"; new="${pair##*=}"
  grep -rl "$old" alpaca_kit tests scripts --include='*.py' | while read -r f; do
    sed -i '' -e "s/${old}/${new}/g" "$f"
  done
done
grep -rn "alpha\." alpaca_kit tests scripts --include='*.py' | grep -v alpaca_kit
```
Expected: the final grep prints NOTHING (no stale `alpha.` imports). If it prints, fix each hit by hand.

- [ ] **Step 3: Drop source_names() from registry**

Open `alpaca_kit/registry.py`: delete the `source_names()` function (its only consumers — the old connector lint and MCP gate — are gone). Delete its test in `tests/data/test_registry.py` if one exists (grep for `source_names`).

- [ ] **Step 4: Rewrite pyproject.toml**

Replace the whole file with:

```toml
[project]
name = "alpaca-kit"
version = "0.1.0"
description = "alpaca_kit - PIT-guarded US market data + Alpaca paper account, as a library and an MCP server"
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
include = ["alpaca_kit*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 5: Update the firewall meta-gate module paths**

`tests/test_us0_firewall_surfaces.py` pins tests by (module, function). The test FILES did not move, so only verify: run `python -m pytest tests/test_us0_firewall_surfaces.py -v` after Step 6. The four pinned functions (`test_guarded_source_blocks_future_snapshot`, `test_has_reverse_split_pending_pit`, `test_bars_are_raw_not_future_adjusted`, `test_rvol_uses_only_trailing_bars`) must still exist in `tests.data.*` / `tests.universe.*`.

- [ ] **Step 6: Reinstall and run the full suite**

```bash
pip install -e ".[dev]"
python -m pytest -q
```
Expected: PASS, same test count as end of Task 2.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: rename migration island to alpaca_kit and rewrite pyproject"
```

---

### Task 4: account.py — Alpaca paper trading client

**Files:**
- Create: `alpaca_kit/account.py`
- Test: `tests/kit/test_account.py` (create `tests/kit/__init__.py` too)

**Interfaces:**
- Consumes: env `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, optional `APCA_API_BASE_URL`.
- Produces: `TradingClient` with `get_account() -> dict`, `get_positions() -> list[dict]`, `get_orders(status: str | None = None) -> list[dict]`, `place_order(symbol, qty, side, order_type="market", time_in_force="day", limit_price=None) -> dict`, `cancel_order(order_id: str) -> dict`; `TradingAPIError`. Task 6 registers these as MCP tools.

- [ ] **Step 1: Write the failing tests**

```python
# tests/kit/test_account.py
from __future__ import annotations

import pytest

from alpaca_kit.account import TradingAPIError, TradingClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")
    return TradingClient()


def test_requires_keys(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="APCA_API_KEY_ID"):
        TradingClient()


def test_defaults_to_paper_host(client):
    assert client.base_url == "https://paper-api.alpaca.markets"


def test_get_account_hits_v2_account(client, monkeypatch):
    calls = []
    monkeypatch.setattr(client, "_request",
                        lambda method, path, **kw: calls.append((method, path)) or {"cash": "100"})
    assert client.get_account() == {"cash": "100"}
    assert calls == [("GET", "/v2/account")]


def test_get_orders_passes_status(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(client, "_request",
                        lambda method, path, params=None, **kw: seen.update(params or {}) or [])
    client.get_orders(status="open")
    assert seen["status"] == "open"


def test_place_order_posts_v2_orders(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(client, "_request",
                        lambda method, path, body=None, **kw: captured.update(
                            {"method": method, "path": path, **(body or {})}) or {"id": "1"})
    client.place_order("AAPL", 1, "buy")
    assert captured["method"] == "POST" and captured["path"] == "/v2/orders"
    assert captured["symbol"] == "AAPL" and captured["side"] == "buy"


def test_place_order_refuses_non_paper_host(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "k")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "s")
    monkeypatch.setenv("APCA_API_BASE_URL", "https://api.alpaca.markets")
    c = TradingClient()
    with pytest.raises(RuntimeError, match="paper"):
        c.place_order("AAPL", 1, "buy")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/kit/test_account.py -v`
Expected: FAIL with ModuleNotFoundError (alpaca_kit.account).

- [ ] **Step 3: Implement alpaca_kit/account.py**

```python
"""Alpaca TRADING-host client (paper account): /v2/account, /v2/positions, /v2/orders.

Same seam pattern as alpaca_kit.alpaca._get_json: stdlib urllib, offline-testable by
monkeypatching _request, actionable error hints. place_order is code-level pinned to the
paper host - a non-paper base URL refuses to place orders (the reset's safety line).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

PAPER_HOST = "https://paper-api.alpaca.markets"
_HINTS = {
    401: "check APCA_API_KEY_ID / APCA_API_SECRET_KEY (source .env.alpaca first)",
    403: "endpoint not entitled for these keys",
    429: "rate limited - back off and retry",
}


class TradingAPIError(RuntimeError):
    """Trading API returned an error status; message carries an actionable hint."""


class TradingClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.environ.get("APCA_API_BASE_URL") or PAPER_HOST).rstrip("/")
        key = os.environ.get("APCA_API_KEY_ID")
        secret = os.environ.get("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("APCA_API_KEY_ID / APCA_API_SECRET_KEY not set (source .env.alpaca first)")
        self._headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                         "Content-Type": "application/json"}

    # -- transport seam (monkeypatched in tests) --------------------------------
    def _request(self, method: str, path: str, params: dict | None = None,
                 body: dict | None = None, timeout: int = 30):
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as e:
            hint = _HINTS.get(e.code, "")
            raise TradingAPIError(f"{method} {path} -> HTTP {e.code}. {hint}".strip()) from e
        except urllib.error.URLError as e:
            raise TradingAPIError(f"{method} {path} -> network error: {e.reason}") from e

    # -- read-only ---------------------------------------------------------------
    def get_account(self) -> dict:
        return self._request("GET", "/v2/account")

    def get_positions(self) -> list[dict]:
        return self._request("GET", "/v2/positions") or []

    def get_orders(self, status: str | None = None) -> list[dict]:
        return self._request("GET", "/v2/orders", params={"status": status}) or []

    # -- mutating (registered as MCP tools only behind the operator gate) --------
    def place_order(self, symbol: str, qty: float, side: str, order_type: str = "market",
                    time_in_force: str = "day", limit_price: float | None = None) -> dict:
        if "paper-api" not in self.base_url:
            raise RuntimeError(f"refusing to place an order against non-paper host {self.base_url}")
        body = {"symbol": symbol, "qty": str(qty), "side": side, "type": order_type,
                "time_in_force": time_in_force}
        if limit_price is not None:
            body["limit_price"] = str(limit_price)
        return self._request("POST", "/v2/orders", body=body)

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/v2/orders/{order_id}") or {"status": "canceled"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/kit/test_account.py -v` → PASS. Then `python -m pytest -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add alpaca_kit/account.py tests/kit/
git commit -m "feat: TradingClient for the Alpaca paper account, code-level paper-only pin"
```

---

### Task 5: replay.py — PIT backtest day iterator

**Files:**
- Create: `alpaca_kit/replay.py`
- Test: `tests/kit/test_replay.py`

**Interfaces:**
- Consumes: `alpaca_kit.source.GuardedSource`, `alpaca_kit.firewall.AsOfGuard`, `alpaca_kit.pit.pit_store.PITStore`, `alpaca_kit.pit.snapshot_source.SnapshotSource`.
- Produces: `replay_days(source=None, *, pit_root=None, start=None, end=None) -> Iterator[tuple[Date, GuardedSource]]` — the one function strategy backtests loop over. Task 9's template backtest.py and the backtest-rules doc reference it by this exact name.

- [ ] **Step 1: Write the failing tests**

```python
# tests/kit/test_replay.py
from __future__ import annotations

from datetime import date

import pytest

from alpaca_kit.firewall import LookaheadError
from alpaca_kit.replay import replay_days


def test_yields_every_calendar_day_guarded(fake_source):
    out = list(replay_days(fake_source))
    assert [d for d, _ in out] == fake_source.trading_calendar()
    first_day, guarded = out[0]
    last_day = out[-1][0]
    with pytest.raises(LookaheadError):
        guarded.daily_snapshot(last_day)          # day-0 guard blocks a later date


def test_range_filter(fake_source):
    cal = fake_source.trading_calendar()
    out = list(replay_days(fake_source, start=cal[1], end=cal[1]))
    assert [d for d, _ in out] == [cal[1]]


def test_requires_source_or_pit_root():
    with pytest.raises(ValueError, match="source or pit_root"):
        list(replay_days())
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/kit/test_replay.py -v` → FAIL (module not found).

- [ ] **Step 3: Implement alpaca_kit/replay.py**

```python
"""PIT backtest day iterator: for each trading day, a source that cannot see past it.

Makes the lookahead-safe backtest the path of least resistance: strategies loop over
replay_days(...) and use the yielded GuardedSource exactly like the live source.
Honest-eval rules live in docs/backtest-rules.md.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import date as Date

from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.source import GuardedSource


def replay_days(source=None, *, pit_root: str | None = None,
                start: Date | None = None, end: Date | None = None,
                ) -> Iterator[tuple[Date, GuardedSource]]:
    if source is None:
        if pit_root is None:
            raise ValueError("pass a source or pit_root")
        from alpaca_kit.pit.pit_store import PITStore
        from alpaca_kit.pit.snapshot_source import SnapshotSource
        source = SnapshotSource(PITStore(pit_root))
    for day in source.trading_calendar():
        if start is not None and day < start:
            continue
        if end is not None and day > end:
            break
        yield day, GuardedSource(source, AsOfGuard(day))
```

- [ ] **Step 4: Run tests** → `python -m pytest tests/kit/test_replay.py -v` PASS; full `python -m pytest -q` PASS.

- [ ] **Step 5: Commit**

```bash
git add alpaca_kit/replay.py tests/kit/test_replay.py
git commit -m "feat: replay_days PIT day iterator for strategy backtests"
```

---

### Task 6: MCP toolset (pure, SDK-free) + read-only meta-gate

The registration rules and tool bodies, testable without the mcp SDK. `build_tools` returns plain `Tool` records; Task 7 adapts them onto FastMCP.

**Files:**
- Create: `alpaca_kit/mcp/__init__.py` (empty), `alpaca_kit/mcp/tools.py`
- Test: `tests/kit/test_mcp_tools.py`

**Interfaces:**
- Consumes: `make_source` (registry), `GuardedSource`/`AsOfGuard`, `build_universe`/`build_trend_template_universe` (universe), `market_breadth` (features.breadth), `EdgarSource` (feeds.edgar), `TradingClient` (account).
- Produces: `Tool` dataclass `(name, description, fn)`; `READ_ONLY_TOOLS: frozenset[str]`; `build_tools(env=None, *, source_factory=None, trading_factory=None, edgar_factory=None) -> dict[str, Tool]`. Registration rules (spec §4/§5):
  - `earnings` — always (EDGAR is keyless).
  - market tools (`daily_bars`, `market_snapshot`, `calendar`, `corp_actions`, `screen`) — need APCA keys, OR `ALPHA_PIT_ROOT` set (offline replay).
  - `breadth` — needs `ALPHA_PIT_ROOT` (bars must be local; live per-symbol fetch is out of MVP scope).
  - `account`, `positions`, `orders` — need APCA keys.
  - `place_order`, `cancel_order` — need APCA keys AND `ALPACA_KIT_ENABLE_ORDERS == "1"`.
  - Every fn is wrapped fail-soft: exceptions become `{"ok": False, "error": str(e)}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/kit/test_mcp_tools.py
from __future__ import annotations

from alpaca_kit.mcp.tools import READ_ONLY_TOOLS, build_tools

KEYS = {"APCA_API_KEY_ID": "k", "APCA_API_SECRET_KEY": "s"}


def test_no_env_registers_only_keyless_tools():
    tools = build_tools(env={})
    assert set(tools) == {"earnings"}


def test_keys_register_market_and_account_but_never_orders():
    tools = build_tools(env=dict(KEYS))
    assert {"daily_bars", "market_snapshot", "calendar", "corp_actions",
            "screen", "account", "positions", "orders", "earnings"} <= set(tools)
    assert "place_order" not in tools and "cancel_order" not in tools


def test_default_registration_is_read_only():          # capability-absence meta-gate
    for env in ({}, dict(KEYS), {**KEYS, "ALPHA_PIT_ROOT": "/tmp/x"}):
        assert set(build_tools(env=env)) <= READ_ONLY_TOOLS


def test_order_tools_need_flag_and_keys():
    flagged = {**KEYS, "ALPACA_KIT_ENABLE_ORDERS": "1"}
    assert {"place_order", "cancel_order"} <= set(build_tools(env=flagged))
    assert "place_order" not in build_tools(env={"ALPACA_KIT_ENABLE_ORDERS": "1"})  # flag w/o keys


def test_breadth_needs_pit_root():
    assert "breadth" not in build_tools(env=dict(KEYS))
    assert "breadth" in build_tools(env={**KEYS, "ALPHA_PIT_ROOT": "/tmp/x"})


def test_tool_calls_are_fail_soft(fake_source):
    tools = build_tools(env=dict(KEYS), source_factory=lambda: fake_source)
    out = tools["daily_bars"].fn(symbol="RUN", start="not-a-date", end="2026-06-12")
    assert out["ok"] is False and "error" in out


def test_daily_bars_happy_path_over_fake_source(fake_source):
    tools = build_tools(env=dict(KEYS), source_factory=lambda: fake_source)
    out = tools["daily_bars"].fn(symbol="RUN", start="2026-06-10", end="2026-06-12")
    assert out["ok"] is True and len(out["rows"]) == 3


def test_pit_guard_blocks_future_as_of(fake_source):
    tools = build_tools(env=dict(KEYS), source_factory=lambda: fake_source)
    out = tools["market_snapshot"].fn(date="2026-06-12", as_of="2026-06-10")
    assert out["ok"] is False and "lookahead" in out["error"].lower()
```

- [ ] **Step 2: Run to verify failure** → `python -m pytest tests/kit/test_mcp_tools.py -v` FAILs (module not found).

- [ ] **Step 3: Implement alpaca_kit/mcp/tools.py**

```python
"""The MCP toolset, SDK-free and fully offline-testable.

Registration rules (spec section 4/5): keyless EDGAR always; market tools behind APCA keys
or an offline PIT root; account queries behind keys; order tools behind keys AND the
operator-only ALPACA_KIT_ENABLE_ORDERS flag (set in the dsh profile, outside the agent's
workspace). Every tool body is fail-soft: exceptions return ok=False with an actionable
message, never raise into the harness.

PIT: every dated call wraps the RAW source in GuardedSource(AsOfGuard(as_of)) - the tool
layer is the guard-wrapping caller the data-layer contract demands.
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from datetime import date as Date

from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.source import GuardedSource

MAX_ROWS = 2000

READ_ONLY_TOOLS = frozenset({
    "daily_bars", "market_snapshot", "calendar", "corp_actions",
    "screen", "breadth", "earnings", "account", "positions", "orders",
})


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    fn: object  # callable(**kwargs) -> dict


def _soft(fn):
    @functools.wraps(fn)
    def inner(**kw):
        try:
            return fn(**kw)
        except Exception as e:  # fail-soft by contract: the loop never sees a raise
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return inner


def _d(s: str) -> Date:
    return Date.fromisoformat(s)


def _frame(df) -> dict:
    rows = df.to_dict(orient="records")
    out = {"ok": True, "rows": rows[:MAX_ROWS]}
    if len(rows) > MAX_ROWS:
        out["truncated"] = f"{len(rows)} rows, first {MAX_ROWS} shown"
    return out


def _guarded(source_factory, as_of: Date) -> GuardedSource:
    return GuardedSource(source_factory(), AsOfGuard(as_of))


def build_tools(env=None, *, source_factory=None, trading_factory=None,
                edgar_factory=None) -> dict[str, Tool]:
    env = os.environ if env is None else env
    has_keys = bool(env.get("APCA_API_KEY_ID")) and bool(env.get("APCA_API_SECRET_KEY"))
    pit_root = env.get("ALPHA_PIT_ROOT")
    orders_on = env.get("ALPACA_KIT_ENABLE_ORDERS") == "1"

    if source_factory is None:
        from alpaca_kit.registry import make_source
        if has_keys:
            source_factory = lambda: make_source("alpaca")            # noqa: E731
        elif pit_root:
            source_factory = lambda: make_source("snapshot", pit_root=pit_root)  # noqa: E731
    if edgar_factory is None:
        from alpaca_kit.feeds.edgar import EdgarSource
        edgar_factory = EdgarSource
    if trading_factory is None and has_keys:
        from alpaca_kit.account import TradingClient
        trading_factory = TradingClient

    tools: dict[str, Tool] = {}

    def add(name: str, description: str, fn) -> None:
        tools[name] = Tool(name=name, description=description, fn=_soft(fn))

    # ---- always: keyless EDGAR ------------------------------------------------
    def earnings(symbol: str, as_of: str | None = None):
        src = edgar_factory()
        facts = src.earnings_known(symbol, _d(as_of) if as_of else Date.today())
        return {"ok": True, "rows": [f.model_dump(mode="json") for f in facts][:MAX_ROWS]}
    add("earnings", "EDGAR XBRL earnings facts for a symbol, PIT-filtered by filing date", earnings)

    # ---- market (keys or offline pit root) -------------------------------------
    if source_factory is not None:
        def daily_bars(symbol: str, start: str, end: str, as_of: str | None = None):
            g = _guarded(source_factory, _d(as_of) if as_of else Date.today())
            return _frame(g.daily_bars(symbol, _d(start), _d(end)))
        add("daily_bars", "RAW unadjusted daily bars for a symbol", daily_bars)

        def market_snapshot(date: str | None = None, as_of: str | None = None):
            day = _d(date) if date else Date.today()
            g = _guarded(source_factory, _d(as_of) if as_of else day)
            return _frame(g.daily_snapshot(day))
        add("market_snapshot", "full-market daily cross-section for a date", market_snapshot)

        def calendar(start: str, end: str):
            cal = source_factory().trading_calendar()
            return {"ok": True, "days": [d.isoformat() for d in cal
                                         if _d(start) <= d <= _d(end)]}
        add("calendar", "trading days in a date range", calendar)

        def corp_actions(as_of: str | None = None):
            day = _d(as_of) if as_of else Date.today()
            g = _guarded(source_factory, day)
            return _frame(g.corporate_actions_known(day))
        add("corp_actions", "corporate actions known as of a date (announce-date keyed)", corp_actions)

        def screen(date: str, kind: str = "gainer", as_of: str | None = None):
            from alpaca_kit.universe import build_trend_template_universe, build_universe
            day = _d(date)
            g = _guarded(source_factory, _d(as_of) if as_of else day)
            uni = (build_trend_template_universe(g, day) if kind == "trend_template"
                   else build_universe(g, day))
            return {"ok": True, "rows": [s.model_dump(mode="json") for s in uni.stocks][:MAX_ROWS]}
        add("screen", "daily screen: kind=gainer or trend_template", screen)

    # ---- breadth (offline bed only: bars must be local) -------------------------
    if pit_root:
        def breadth(date: str):
            from alpaca_kit.features.breadth import market_breadth
            from alpaca_kit.pit.pit_store import PITStore
            from alpaca_kit.pit.snapshot_source import SnapshotSource
            day = _d(date)
            store = PITStore(pit_root)
            src = SnapshotSource(store)
            snap = GuardedSource(src, AsOfGuard(day)).daily_snapshot(day)
            bars = {sym: src.daily_bars(sym, Date(1990, 1, 1), day)
                    for sym in snap["symbol"].tolist()}
            reading = market_breadth(bars, day)
            return {"ok": True, **reading.model_dump(mode="json")}
        add("breadth", "market breadth for a date (offline PIT bed)", breadth)

    # ---- account (keys) ---------------------------------------------------------
    if trading_factory is not None:
        add("account", "paper account summary", lambda: {"ok": True, **trading_factory().get_account()})
        add("positions", "open positions", lambda: {"ok": True, "rows": trading_factory().get_positions()})

        def orders(status: str | None = None):
            return {"ok": True, "rows": trading_factory().get_orders(status=status)}
        add("orders", "order list, optionally filtered by status", orders)

        # ---- reserved: operator gate (spec section 5, Gate 1) -------------------
        if orders_on:
            def place_order(symbol: str, qty: float, side: str, order_type: str = "market",
                            limit_price: float | None = None):
                return {"ok": True, **trading_factory().place_order(
                    symbol, qty, side, order_type=order_type, limit_price=limit_price)}
            add("place_order", "submit a PAPER order (operator-gated)", place_order)

            def cancel_order(order_id: str):
                return {"ok": True, **trading_factory().cancel_order(order_id)}
            add("cancel_order", "cancel a paper order by id (operator-gated)", cancel_order)

    return tools
```

- [ ] **Step 4: Run tests** → `python -m pytest tests/kit/test_mcp_tools.py -v` PASS; full suite PASS.

- [ ] **Step 5: Commit**

```bash
git add alpaca_kit/mcp tests/kit/test_mcp_tools.py
git commit -m "feat: MCP toolset with keyed/flagged registration rules and read-only meta-gate"
```

---

### Task 7: FastMCP server adapter + entry point

**Files:**
- Create: `alpaca_kit/mcp/server.py`, `alpaca_kit/mcp/__main__.py`
- Modify: `pyproject.toml` (add mcp dependency)
- Test: `tests/kit/test_mcp_server.py`

**Interfaces:**
- Consumes: `build_tools` from Task 6.
- Produces: `build_server(tools: dict[str, Tool] | None = None) -> FastMCP`; `python -m alpaca_kit.mcp` runs a stdio MCP server. The dsh profile (Task 10) mounts exactly this command.

- [ ] **Step 1: Add the mcp dependency**

In `pyproject.toml` dependencies add: `"mcp>=1.2"`. Run `pip install -e ".[dev]"`.

- [ ] **Step 2: Write the failing test**

```python
# tests/kit/test_mcp_server.py
from __future__ import annotations

import pytest

mcp_sdk = pytest.importorskip("mcp", reason="install: pip install -e . (mcp SDK)")

from alpaca_kit.mcp.tools import Tool
from alpaca_kit.mcp.server import build_server


def test_build_server_registers_every_tool():
    canned = {
        "ping": Tool(name="ping", description="pong", fn=lambda: {"ok": True}),
        "echo": Tool(name="echo", description="echo x", fn=lambda x: {"ok": True, "x": x}),
    }
    server = build_server(canned)
    # FastMCP exposes registered tools; the exact accessor is pinned against the installed
    # SDK version at implementation time. Contract under test: both names are registered.
    import anyio
    listed = anyio.run(server.list_tools)
    names = {t.name for t in listed}
    assert names == {"ping", "echo"}
```

If the installed SDK's `list_tools` accessor differs, adapt the accessor in this test (NOT the contract: every Tool in the dict is registered by name).

- [ ] **Step 3: Run to verify failure** → FAIL (no server module).

- [ ] **Step 4: Implement server.py and __main__.py**

```python
# alpaca_kit/mcp/server.py
"""FastMCP adapter: register the pure toolset onto a stdio MCP server."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from alpaca_kit.mcp.tools import Tool, build_tools


def build_server(tools: dict[str, Tool] | None = None) -> FastMCP:
    server = FastMCP("alpaca-kit")
    for t in (build_tools() if tools is None else tools).values():
        server.add_tool(t.fn, name=t.name, description=t.description)
    return server
```

```python
# alpaca_kit/mcp/__main__.py
"""Run the alpaca-kit MCP server on stdio: python -m alpaca_kit.mcp"""
from alpaca_kit.mcp.server import build_server

if __name__ == "__main__":
    build_server().run()
```

If the installed FastMCP's registration method is not `add_tool(fn, name=, description=)`, check `python -c "from mcp.server.fastmcp import FastMCP; help(FastMCP.add_tool)"` and adapt — the contract (register each Tool under its name) stays.

- [ ] **Step 5: Run tests** → `python -m pytest tests/kit/test_mcp_server.py -v` PASS; full suite PASS.

- [ ] **Step 6: Manual stdio smoke (no keys: expect the keyless toolset)**

```bash
timeout 5 python -m alpaca_kit.mcp < /dev/null; echo "exit=$?"
```
Expected: the process starts and waits on stdio (timeout kills it); no traceback.

- [ ] **Step 7: Commit**

```bash
git add alpaca_kit/mcp pyproject.toml tests/kit/test_mcp_server.py
git commit -m "feat: FastMCP stdio server entry for the alpaca-kit toolset"
```

---

### Task 8: Scripts + PIT beds remount

**Files:**
- Modify: `scripts/capture_window.py`, `scripts/capture_broad.py`, `scripts/smoke_alpaca.py` (imports were already sed-renamed in Task 3 — verify), `.gitignore`
- Create: `data/pit/` (remounted beds, gitignored)

**Interfaces:**
- Consumes: the backup at `~/Desktop/self-evolve/alpha-us-backup-20260829/`.
- Produces: `data/pit/2yr` and `data/pit/broad` beds; `ALPHA_PIT_ROOT=data/pit/2yr` becomes the documented default for replay/breadth.

- [ ] **Step 1: Verify script imports survived the rename**

```bash
python -c "import ast,sys
for f in ['scripts/capture_window.py','scripts/capture_broad.py','scripts/smoke_alpaca.py']:
    ast.parse(open(f).read())
print('parse ok')"
grep -n "^from \|^import " scripts/*.py | grep -v alpaca_kit | grep alpha && echo STALE || echo clean
```
Expected: `parse ok` and `clean`.

- [ ] **Step 2: Remount the PIT beds from backup**

```bash
mkdir -p data/pit
cp -Rp ~/Desktop/self-evolve/alpha-us-backup-20260829/verdict_pit_2yr data/pit/2yr
cp -Rp ~/Desktop/self-evolve/alpha-us-backup-20260829/verdict_pit_broad data/pit/broad
grep -q "^/data/pit/" .gitignore || printf '/data/pit/\n' >> .gitignore
```

- [ ] **Step 3: Checksum + replay smoke over the remounted bed**

```bash
python - <<'EOF'
from alpaca_kit.pit.integrity_check import verify_checksums
from pathlib import Path
print("2yr discrepancies:", verify_checksums(Path("data/pit/2yr"), fail_closed=False)[:3])
from alpaca_kit.replay import replay_days
days = list(replay_days(pit_root="data/pit/2yr"))
print("replay days:", len(days), days[0][0], "->", days[-1][0])
day, g = days[10]
print("snapshot rows on", day, ":", len(g.daily_snapshot(day)))
EOF
```
Expected: no discrepancies (or explained warnings), ~526 replay days spanning 2024-06 → 2026-07, and a non-empty snapshot.

- [ ] **Step 4: Commit**

```bash
git add .gitignore scripts/
git commit -m "chore: verify producer scripts post-rename and remount PIT beds under data/pit"
```

---

### Task 9: strategies/ scaffold + backtest rules + repo docs

**Files:**
- Create: `strategies/_template/{THESIS.md,screen.py,backtest.py,journal.md,status.yaml}`, `docs/backtest-rules.md`, `AGENTS.md`, `CLAUDE.md`, `ROADMAP.md`

**Interfaces:**
- Consumes: `alpaca_kit.replay.replay_days` (Task 5).
- Produces: the strategy-directory convention every future strategy copies; the four honest-eval rules by name.

- [ ] **Step 1: Write docs/backtest-rules.md**

```markdown
# Backtest Rules (honest-eval, carried from the old product)

Every backtest in strategies/ MUST follow these. They exist because each one was a real
bug class once.

1. **PIT channel only.** Iterate days with alpaca_kit.replay.replay_days and use the
   yielded GuardedSource. Never open the parquet files directly in a backtest loop.
2. **Delisting is a terminal loss.** A symbol that delists or halts to zero during a hold
   scores -1.0. It is NEVER dropped from the sample (survivorship laundering).
3. **Returns are gross.** No fee/slippage model unless the strategy adds one explicitly —
   and then it says so in THESIS.md.
4. **No same-day round trip.** Decide on day t → enter at t+1 open → exit at t+N close
   (N >= 1). Prices are RAW/unadjusted; splits inside a window distort naive returns —
   check corp_actions before trusting a large move.
5. **Missing data is discarded, never fabricated.** A day without a bar is skipped and
   counted, not interpolated.

Results land in backtests/YYYY-MM-DD-<label>.json and record: window, parameters,
sample size, hit rate, mean/median return, worst case, and the count of discarded days.
```

- [ ] **Step 2: Write the strategy template**

`strategies/_template/THESIS.md`:
```markdown
# <strategy name>

**Status:** idea · **Owner:** agent + operator

## Thesis
What market behavior does this capture, and why does it exist?

## Rules
- Universe / screen:
- Entry:
- Exit / stop:
- Position notes:

## Falsification
What result would prove this thesis wrong? (Be specific: metric + threshold + window.)
```

`strategies/_template/screen.py`:
```python
"""Screen for <strategy>: emits candidate symbols for a given day.

Usage: python screen.py 2026-03-02   (uses ALPHA_PIT_ROOT or live keys via registry)
"""
from __future__ import annotations

import sys
from datetime import date

from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.registry import make_source
from alpaca_kit.source import GuardedSource
from alpaca_kit.universe import build_universe


def screen(day: date):
    src = GuardedSource(make_source(), AsOfGuard(day))
    return [s.symbol for s in build_universe(src, day).stocks]


if __name__ == "__main__":
    print(screen(date.fromisoformat(sys.argv[1])))
```

`strategies/_template/backtest.py`:
```python
"""Backtest skeleton for <strategy>. Follows docs/backtest-rules.md - all five rules."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from alpaca_kit.replay import replay_days

PIT_ROOT = "data/pit/2yr"


def run(start: date | None = None, end: date | None = None) -> dict:
    picks = []
    for day, source in replay_days(pit_root=PIT_ROOT, start=start, end=end):
        # rule 1: use `source` (guarded) for every read on this day
        ...
    return {"window": [str(start), str(end)], "n": len(picks)}


if __name__ == "__main__":
    result = run()
    out = Path("backtests") / f"{date.today()}-run.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(out)
```

`strategies/_template/journal.md`: `# Journal\n\n- YYYY-MM-DD: created from _template.`
`strategies/_template/status.yaml`: `status: idea   # idea | researching | validated | paper | retired`

- [ ] **Step 3: Write AGENTS.md (workspace map for the dsh agent)**

```markdown
# AGENTS.md — Evolving-Alpha-US workspace

Three layers: MARKET + ACCOUNT live in the alpaca_kit package; STRATEGY (you) works in
strategies/.

- alpaca_kit/ — data + account library AND the MCP server you already have tools from.
  For backtests, import it directly (alpaca_kit.replay.replay_days); MCP tools are for
  interactive queries only. RAW prices; PIT guard is mandatory (the lib enforces it).
- strategies/<name>/ — one directory per strategy: THESIS.md, screen.py, backtest.py,
  backtests/, journal.md, status.yaml. Copy strategies/_template to start one. Commit
  your own iterations; git log is the audit trail.
- data/pit/2yr — offline PIT bed (526 trading days, 2024-06 → 2026-07, ~800 symbols).
  Set ALPHA_PIT_ROOT=data/pit/2yr for offline work.
- docs/backtest-rules.md — the five honest-eval rules. Every backtest follows them.
- Tests: python -m pytest -q (offline, no keys). Keep it green.

Never edit: data/pit/ contents, dsh/profile installed copies, or anything under docs/research/.
```

- [ ] **Step 4: Write the fresh minimal CLAUDE.md (~25 lines: what/map/commands/gotchas — model on AGENTS.md but for Claude Code sessions; include the four PIT gotchas: announce_date:=process_date, IEX feed default, RAW prices, replay-only backtests) and a ROADMAP.md stub:**

```markdown
# ROADMAP.md

Part I — forward: (1) first real strategy directory through a full research cycle;
(2) daily-run cadence via dsh schedule (deferred); (3) paper forward-testing behind the
order gate (deferred); (4) FINRA/float live endpoints; (5) second data vendor.

Part II — built log: 2026-08-29 skeleton reset (spec docs/superpowers/specs/
2026-08-29-market-strategy-account-skeleton-design.md).
```

- [ ] **Step 5: Full suite still green** → `python -m pytest -q` PASS.

- [ ] **Step 6: Commit**

```bash
git add strategies docs/backtest-rules.md AGENTS.md CLAUDE.md ROADMAP.md
git commit -m "feat: strategy template, backtest rules, workspace docs"
```

---

### Task 10: dsh/ config + skills (mechanics + style-kairos from seeds_v2)

**Files:**
- Create: `dsh/README.md`, `dsh/profile/cordis.yml`, `dsh/skills/mechanics/backtest-rules/SKILL.md`, `dsh/skills/mechanics/alpaca-kit-guide/SKILL.md`, `dsh/skills/style-kairos/{doctrine,signals,lessons}/SKILL.md`, `scripts/convert_seeds.py`
- Delete: `seeds_v2/` (after conversion)

**Interfaces:**
- Consumes: `seeds_v2/{doctrine,skills,memory}.json`; the MCP entry `python -m alpaca_kit.mcp` (Task 7).
- Produces: installable dsh config. NOTE (spec §7 caveat): dsh is developer preview — cordis.yml keys and the skill discovery format are pinned against the LIVE dsh docs at install time; content here is the deliverable, the container format may need one adaptation pass.

- [ ] **Step 1: Write scripts/convert_seeds.py**

```python
"""One-shot: convert seeds_v2 JSON packs into style-kairos SKILL.md files."""
from __future__ import annotations

import json
from pathlib import Path

STYLE_HEADER = """> **Scope: operator style, not market law.** These are the operator's personal
> investment rules and preferences. Follow them by default — but when research findings
> conflict with an entry here, REPORT the conflict; do not silently defer.

"""
ROOT = Path("dsh/skills/style-kairos")


def main() -> None:
    doctrine = json.loads(Path("seeds_v2/doctrine.json").read_text())
    skills = json.loads(Path("seeds_v2/skills.json").read_text())
    memory = json.loads(Path("seeds_v2/memory.json").read_text())

    d = ["# Doctrine — operator trading rules\n", STYLE_HEADER]
    for e in doctrine:
        tag = " (red-line)" if e.get("immutable") else ""
        d.append(f"## {e['section']}{tag}\n{e['guidance']}\n")
    (ROOT / "doctrine").mkdir(parents=True, exist_ok=True)
    (ROOT / "doctrine" / "SKILL.md").write_text("\n".join(d))

    s = ["# Signals — operator setups\n", STYLE_HEADER]
    for e in skills:
        s.append(f"## {e['skill_id']}\n- **Trigger:** {e.get('trigger','')}\n"
                 f"- **Entry:** {e.get('entry','')}\n- **Exit/stop:** {e.get('exit_stop','')}\n"
                 f"- **Taboo:** {e.get('taboo','')}\n")
    (ROOT / "signals").mkdir(parents=True, exist_ok=True)
    (ROOT / "signals" / "SKILL.md").write_text("\n".join(s))

    m = ["# Lessons — operator failure signatures\n", STYLE_HEADER]
    for e in memory:
        m.append(f"## {e.get('lesson_id','lesson')}\n- **Failure:** {e.get('failure_signature','')}\n"
                 f"- **Analog:** {e.get('named_analog','')}\n- **Phases:** {', '.join(e.get('phases', []))}\n")
    (ROOT / "lessons").mkdir(parents=True, exist_ok=True)
    (ROOT / "lessons" / "SKILL.md").write_text("\n".join(m))
    print("wrote", *[p.name for p in ROOT.iterdir()])


if __name__ == "__main__":
    main()
```

If a JSON field name differs (inspect the files first: `python -c "import json; print(json.loads(open('seeds_v2/skills.json').read())[0].keys())"`), adapt the accessor — content fidelity beats schema assumptions.

- [ ] **Step 2: Run it and eyeball the output**

```bash
python scripts/convert_seeds.py
head -30 dsh/skills/style-kairos/doctrine/SKILL.md
```
Expected: 39 doctrine sections, 6 signals, 21 lessons, each file opening with the style-scope header.

- [ ] **Step 3: Write the two mechanics skills**

`dsh/skills/mechanics/backtest-rules/SKILL.md`: title + "Always applies (neutral mechanics, not style)." + the five rules copied verbatim from `docs/backtest-rules.md` + "Full text: docs/backtest-rules.md".

`dsh/skills/mechanics/alpaca-kit-guide/SKILL.md`:
```markdown
# alpaca-kit guide (neutral mechanics)

- Interactive queries: use the MCP tools (daily_bars, market_snapshot, screen, breadth,
  earnings, account, positions, orders). Backtests: import alpaca_kit directly and loop
  alpaca_kit.replay.replay_days — never hammer MCP in a loop.
- Prices are RAW/unadjusted everywhere. A split inside a trailing window fabricates fake
  RS leaders — check corp_actions before trusting a big move.
- Corporate actions are keyed on announce_date := Alpaca process_date (no true announce
  field exists; this is the lookahead-safe key — it lags reality, never leads).
- Bars feed is IEX on free/paper keys (SIP returns 403). History reaches ~2021 only.
- Offline bed: ALPHA_PIT_ROOT=data/pit/2yr (526 days, 2024-06→2026-07, ~800 symbols).
- Tools are fail-soft: {"ok": false, "error": ...} means fix the call or the env, not retry loops.
- EDGAR earnings are keyed on the FILING date, never the period end.
```

- [ ] **Step 4: Write dsh/profile/cordis.yml (template) and dsh/README.md**

`cordis.yml` (indicative — pin keys against live dsh docs at install):
```yaml
# alpaca-kit profile template - verify key names against current dsh docs before install
llm:
  provider: deepseek          # first-party llm-deepseek adapter; DEEPSEEK_API_KEY from env
mcp:
  servers:
    alpaca-kit:
      command: [python, -m, alpaca_kit.mcp]
      cwd: <ABSOLUTE PATH TO THIS REPO>
      env:
        APCA_API_KEY_ID: ${APCA_API_KEY_ID}
        APCA_API_SECRET_KEY: ${APCA_API_SECRET_KEY}
        ALPHA_PIT_ROOT: data/pit/2yr
        # ALPACA_KIT_ENABLE_ORDERS: "1"   # operator-only; NEVER set in the repo copy
skills:
  paths: [dsh/skills]
permissions:
  always_ask: [place_order, cancel_order]
workspace: <ABSOLUTE PATH TO THIS REPO>
```

`dsh/README.md`: install steps — (1) `npx @deepseek-ai/dsh web` once to create harness home; (2) copy `dsh/profile/cordis.yml` into the harness home profile location per current dsh docs, filling absolute paths; (3) `source .env.alpaca` and `source .env.deepseek` in the shell that launches dsh (or put the vars in the home profile env); (4) the ORDERS flag lives ONLY in the home copy; (5) dsh is developer preview — re-check config key names against the live docs (survey frozen 2026-08-22).

- [ ] **Step 5: Remove seeds_v2 (content now lives in dsh/skills)**

```bash
git rm -r -q seeds_v2
```

- [ ] **Step 6: Full suite green; commit**

```bash
python -m pytest -q
git add dsh scripts/convert_seeds.py
git commit -m "feat: dsh profile template and skills - mechanics plus style-kairos from seeds_v2"
```

---

### Task 11: End-to-end smoke + wrap-up

**Files:**
- No new code; verification + docs touch-ups only.

**Interfaces:**
- Consumes: everything above.
- Produces: a verified skeleton and the final reset commit.

- [ ] **Step 1: Offline E2E (no keys) — replay + screen over the bed**

```bash
python - <<'EOF'
from datetime import date
from alpaca_kit.replay import replay_days
from alpaca_kit.universe import build_universe
n = 0
for day, src in replay_days(pit_root="data/pit/2yr", start=date(2026, 3, 2), end=date(2026, 3, 6)):
    uni = build_universe(src, day)
    print(day, "candidates:", len(uni.stocks)); n += 1
assert n > 0
EOF
```
Expected: one line per trading day with candidate counts, no exceptions.

- [ ] **Step 2: Keyed smoke (needs .env.alpaca; skip if offline)**

```bash
source ~/Desktop/self-evolve/alpha-us-backup-20260829/.env.alpaca
python scripts/smoke_alpaca.py
python - <<'EOF'
from alpaca_kit.account import TradingClient
c = TradingClient()
acct = c.get_account()
print("paper account ok - equity:", acct.get("equity"))
EOF
```
Expected: bars + corp actions print; account equity prints. (These hit the network — run manually, never in pytest.)

- [ ] **Step 3: MCP registration smoke with keys**

```bash
python - <<'EOF'
import os
from alpaca_kit.mcp.tools import build_tools
tools = build_tools()
print(sorted(tools))
assert "place_order" not in tools, "order gate must be closed by default"
EOF
```
Expected: market+account+earnings (+breadth if ALPHA_PIT_ROOT set) listed; no order tools.

- [ ] **Step 4: dsh live smoke (manual, operator-driven)**

Per `dsh/README.md`: install the profile, launch `npx @deepseek-ai/dsh web`, and in the web UI ask the agent to (a) call `screen` for a bed date, (b) copy `strategies/_template` to a first strategy and fill THESIS.md. Record any dsh config-format fixes back into `dsh/README.md`.

- [ ] **Step 5: Final full suite + commit**

```bash
python -m pytest -q
git add -A
git commit -m "chore: skeleton reset complete - offline E2E verified"
git log --oneline main..HEAD | head -20
```

Merging `reset/market-strategy-account` into `main` (and pushing) is the operator's explicit call — do not merge or push without it.

---

## Self-review notes

- Spec coverage: §2 layout → Tasks 2-3; §3 carried/dropped → Tasks 2-3; §4 tools + rules → Task 6; §5 double gate → Task 6 (Gate 1) + Task 10 preset (Gate 2); §6 strategies → Task 9 (+ replay Task 5); §7 dsh → Task 10; §8 tests → Tasks 3-7 (meta-gates: firewall in Task 3 Step 5, read-only in Task 6); §9 order → Tasks 1-11 in that order; §10/§11 → deferred/risks respected (no daily loop, no live endpoints, formats pinned at install).
- Deviations from the spec's illustrative tree, all noted inline: `firewall.py` stays its own module (not merged into source.py); `composite.py` stays its own module; `settings.py` skipped (YAGNI — env reads stay local to the modules that need them, documented in the guide skill); breadth tool is pit-root-only (live per-symbol bars fetch is out of MVP scope).
- The `orders` (read) tool means the old "no tool name contains order" pin becomes the stronger READ_ONLY_TOOLS subset gate (Task 6 test_default_registration_is_read_only).
