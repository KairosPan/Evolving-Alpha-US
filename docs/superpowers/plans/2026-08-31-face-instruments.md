# face v2 — Instruments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only `/market` and `/account` instrument pages to the face, fed by a Python producer the face spawns on demand, styled light-minimal in the chat-light vocabulary.

**Architecture:** `scripts/face_data.py` holds two pure payload assemblers (unit-tested with fakes) plus a thin CLI; `face/src/data.ts` caches/spawns it behind two `/data/*.json` routes with an injected spawner (unit-tested without Python); two static pages fetch and render. No new dependencies on either side.

**Tech Stack:** Python (alpaca_kit, pandas — already deps), Node 22 TS (existing face toolchain), hand-rolled SVG, no frameworks.

**Spec:** `docs/superpowers/specs/2026-08-31-face-instruments-design.md` (read first) — the v1 face spec `docs/superpowers/specs/2026-08-30-face-chat-light-design.md` still governs everything it covers.

## Global Constraints

- Read-only everywhere: no order code path in the producer (grep-tested), no write affordance on the pages beyond the refresh control.
- The producer's account mode reads `APCA_API_KEY_ID`/`APCA_API_SECRET_KEY` from the environment; missing keys → `{"ok": true, "available": false, "reason": "no APCA keys in the environment"}` — never an exception, never fake shape.
- Gate 1 computed honestly, the registration way: `ALPACA_KIT_ENABLE_ORDERS == "1"` AND both keys present. Gate 2 stays intent wording pointing at `face/README.md`'s drill.
- Face endpoints: TTL market 900_000 ms, account 60_000 ms; spawn timeout 30_000 ms; single-flight per mode; stale-cache-on-error with `stale: true`; 503 + error JSON with no cache. No request data ever reaches the spawn (fixed argv).
- Pages: chat-light tokens only (link `/client/chat.css`); page CSS appended to `chat.css` under a new `/* instruments */` block; null → em-dash `—`; warmup regions rendered "immature, not missing"; `generated_at` + `stale` always rendered; no external hosts.
- Suites: `python -m pytest` (grows past 324) and `cd face && npm test && npm run typecheck` green at every commit that touches their side.
- All commands run from the repo root `/Users/pan/Desktop/self-evolve/evolving-alpha-us` unless the step says otherwise.
- The installed packages outrank this plan's sketches; deviations documented in commit message + report. Python interpreter for manual probes: `python3` (imports alpaca_kit on this machine).

---

### Task 1: `market_payload` — the bed assembler (pure, tested)

**Files:**
- Create: `scripts/face_data.py`
- Test: `tests/test_face_data_market.py`

**Interfaces:**
- Produces: `market_payload(source, days, end, *, breadth_days=60, tape_days=250, screen_limit=40) -> dict` — `source` implements `daily_snapshot(day)` + `daily_bars(symbol, start, end)`; `days` is the ascending list of captured trading days ≤ `end`. Returns the R2-mock-shaped dict (see Step 3) WITHOUT `generated_at` (the CLI adds it in Task 2). Also `BED_INFO: dict` (module constant describing the shipped 2yr bed).

- [ ] **Step 1: Write the failing test**

`tests/test_face_data_market.py`:
```python
"""market_payload assembles the /market payload from any Protocol-shaped source."""
from datetime import date, timedelta

import pandas as pd

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from face_data import market_payload  # noqa: E402


class _TinySource:
    """Three symbols, ~30 ascending days of bars, one snapshot on the end day."""

    def __init__(self, days):
        self.days = days
        self.syms = ["AAA", "BBB", "CCC"]

    def daily_snapshot(self, day):
        rows = []
        for i, s in enumerate(self.syms):
            close = 10.0 + i + self.days.index(day) * 0.1
            rows.append({"symbol": s, "close": close, "prev_close": close - 0.1,
                         "open": close - 0.05, "high": close + 0.1, "low": close - 0.2,
                         "volume": 1000.0 + i})
        return pd.DataFrame(rows)

    def daily_bars(self, symbol, start, end):
        i = self.syms.index(symbol)
        rows = [{"date": d, "open": 10.0 + i, "high": 11.0 + i, "low": 9.0 + i,
                 "close": 10.0 + i + n * 0.1, "volume": 1000.0}
                for n, d in enumerate(self.days) if start <= d <= end]
        return pd.DataFrame(rows)


def _days(n=30):
    d0 = date(2026, 6, 1)
    return [d0 + timedelta(days=k) for k in range(n)]


def test_market_payload_shape_and_honesty():
    days = _days()
    payload = market_payload(_TinySource(days), days, days[-1],
                             breadth_days=5, tape_days=10, screen_limit=5)
    assert payload["ok"] is True
    assert payload["as_of"] == days[-1].isoformat()
    assert "bed" in payload and "warmup" in payload["bed"]
    b = payload["breadth"]["series"]
    assert len(b) == 5
    assert {"date", "pct_above_200dma", "net_new_highs", "advances", "declines"} <= set(b[0])
    t = payload["tape"]["series"]
    assert len(t) == 10
    assert t[0]["level"] == 100.0  # normalized to window start
    scr = payload["screens"]
    assert set(scr) == {"trend_template", "gainer"}
    for kind in scr.values():
        assert "rows" in kind and "raw" in kind
        for row in kind["rows"]:
            assert "spark" in row and len(row["spark"]) <= 60


def test_market_payload_short_history_never_fabricates():
    # only 3 days of history: 200DMA/52wk readings must be None, not 0
    days = _days(3)
    payload = market_payload(_TinySource(days), days, days[-1],
                             breadth_days=3, tape_days=3, screen_limit=5)
    assert payload["breadth"]["series"][-1]["pct_above_200dma"] is None
```

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/test_face_data_market.py -v` — FAIL (no module `face_data`)

- [ ] **Step 3: Implement `market_payload` in `scripts/face_data.py`**

```python
"""face_data - the face's instrument-data producer.

Two modes, JSON to stdout: `market` (the PIT bed through production code
paths) and `account` (TradingClient read-only). Spawned by face/src/data.ts;
also runnable by hand. Read-only by construction: this module must never
import or call an order-placing code path (tests grep for it).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date as Date, datetime, timezone

from alpaca_kit.features.breadth import market_breadth
from alpaca_kit.firewall import AsOfGuard
from alpaca_kit.source import GuardedSource
from alpaca_kit.universe import build_universe

# Facts about the SHIPPED 2yr bed (window + maturity boundaries). Constants,
# not measurements: they describe the capture, and the page renders them as
# the maturity rail. A different bed needs different values.
BED_INFO = {
    "root": "data/pit/2yr",
    "window": {"start": "2024-06-03", "end": "2026-07-09"},
    "warmup": {
        "sma200_valid_from": "2025-03-20",
        "week52_valid_from": "2025-06-04",
        "trend_template_valid_from": "2025-06-05",
        "note": "bars start AT the window start; long-indicator readings "
                "before these dates are immature, not missing",
    },
}


def market_payload(source, days, end, *, breadth_days=60, tape_days=250,
                   screen_limit=40):
    """Assemble the /market payload. `source` implements daily_snapshot +
    daily_bars; `days` = ascending captured trading days <= end. Pure w.r.t.
    its inputs; the CLI supplies the real bed."""
    guard = GuardedSource(source, AsOfGuard(end))
    snap = guard.daily_snapshot(end)
    symbols = snap["symbol"].tolist()

    bars = {}
    for sym in symbols:
        df = source.daily_bars(sym, Date(1990, 1, 1), end)
        if df is not None and not df.empty:
            df = df.copy()
            import pandas as pd
            df["date"] = pd.to_datetime(df["date"]).dt.date
            bars[sym] = df.sort_values("date").reset_index(drop=True)

    breadth_series = []
    for day in days[-breadth_days:]:
        sliced = {s: df[df["date"] <= day] for s, df in bars.items()}
        r = market_breadth(sliced, day)
        breadth_series.append({"date": day.isoformat(),
                               "pct_above_200dma": r.pct_above_200dma,
                               "net_new_highs": r.net_new_highs,
                               "advances": r.advances, "declines": r.declines})

    tape_days_list = days[-tape_days:]
    start_day = tape_days_list[0]
    base = {}
    for s, df in bars.items():
        d0 = df[df["date"] >= start_day]
        if not d0.empty and float(d0.iloc[0]["close"]) > 0:
            base[s] = float(d0.iloc[0]["close"])
    tape = []
    for day in tape_days_list:
        vals = []
        for s, df in bars.items():
            if s not in base:
                continue
            rows = df[df["date"] == day]
            if not rows.empty:
                vals.append(float(rows.iloc[0]["close"]) / base[s])
        tape.append({"date": day.isoformat(),
                     "level": round(100 * sum(vals) / len(vals), 2) if vals else None,
                     "n": len(vals)})

    def screen_rows(kind):
        uni = build_universe(guard, end, screen=kind)
        out = []
        for s in uni.all()[:screen_limit]:
            d = s.model_dump(mode="json")
            df = bars.get(s.symbol)
            if df is not None:
                closes = df[df["date"] <= end].tail(60)["close"].tolist()
                c0 = closes[0] if closes else 1.0
                d["spark"] = [round(c / c0, 4) for c in closes]
            out.append(d)
        return out

    return {
        "ok": True,
        "bed": BED_INFO,
        "as_of": end.isoformat(),
        "breadth": {"series": breadth_series,
                    "raw": "alpaca_kit.features.breadth.market_breadth"},
        "tape": {"series": tape,
                 "note": "equal-weight composite, 100 = window start",
                 "raw": "derived from the bed's bars"},
        "screens": {
            kind: {"rows": screen_rows(kind),
                   "raw": f"alpaca_kit.universe.build_universe(screen='{kind}')"}
            for kind in ("trend_template", "gainer")
        },
    }
```
NOTE: `build_universe(guard, end, screen=kind)` on the tiny fixture returns whatever the
production screens yield (possibly zero rows) — the test asserts shape, not counts. If
`build_universe` requires source methods the fixture lacks (check the failure mode), extend
`_TinySource` with no-op implementations returning empty frames rather than weakening the
assertions; document what was added.

- [ ] **Step 4: Run to verify pass** — `python -m pytest tests/test_face_data_market.py -v` — PASS; then the whole suite: `python -m pytest` — all green.

- [ ] **Step 5: Commit**

```bash
git add scripts/face_data.py tests/test_face_data_market.py
git commit -m "feat(face-data): market payload assembler - bed through production code paths"
```

---

### Task 2: `account_payload` + gate truth + CLI (both modes)

**Files:**
- Modify: `scripts/face_data.py` (append)
- Test: `tests/test_face_data_account.py`

**Interfaces:**
- Consumes: `market_payload`, `BED_INFO` (Task 1).
- Produces: `account_payload(client_factory, env) -> dict` (client has `get_account()`, `get_positions()`, `get_orders(status=None)`); `gate_state(env) -> dict`; CLI `python3 scripts/face_data.py market|account` printing JSON with `generated_at` added, exit 0 on `ok` payloads (including `available:false`), exit 1 with `{"ok": false, "error": ...}` on failure.

- [ ] **Step 1: Write the failing tests**

`tests/test_face_data_account.py`:
```python
"""account_payload: read-only, honest about missing keys, gate computed truthfully."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from face_data import account_payload, gate_state  # noqa: E402

KEYS = {"APCA_API_KEY_ID": "k", "APCA_API_SECRET_KEY": "s"}


class _FakeClient:
    def get_account(self):
        return {"status": "ACTIVE", "equity": "1000.5", "cash": "900.1",
                "buying_power": "2000.2"}

    def get_positions(self):
        return [{"symbol": "AAA", "qty": "10", "avg_entry_price": "9.5",
                 "market_value": "100.0", "unrealized_plpc": "0.05"}]

    def get_orders(self, status=None):
        return [{"symbol": "AAA", "side": "buy", "qty": "10",
                 "status": "filled", "submitted_at": "2026-07-01T13:30:00Z"}]


def test_no_keys_is_honest_absence_and_never_builds_a_client():
    calls = []
    payload = account_payload(lambda: calls.append(1), env={})
    assert payload == {"ok": True, "available": False,
                       "reason": "no APCA keys in the environment"}
    assert calls == []


def test_with_keys_assembles_read_only_payload():
    payload = account_payload(_FakeClient, env=KEYS)
    assert payload["ok"] is True and payload["available"] is True
    assert payload["account"]["status"] == "ACTIVE"
    assert payload["positions"][0]["symbol"] == "AAA"
    assert len(payload["orders"]) <= 50
    assert payload["orders_gate"]["gate1_registered"] is False  # flag unset


def test_gate_truth_table():
    assert gate_state({})["gate1_registered"] is False
    assert gate_state(KEYS)["gate1_registered"] is False
    assert gate_state({**KEYS, "ALPACA_KIT_ENABLE_ORDERS": "1"})["gate1_registered"] is True
    assert gate_state({"ALPACA_KIT_ENABLE_ORDERS": "1"})["gate1_registered"] is False
    g = gate_state({})
    assert g["gate2_validated"] is False and "face/README.md" in g["gate2_note"]


def test_no_order_code_path_in_producer():
    src = (Path(__file__).resolve().parents[1] / "scripts" / "face_data.py").read_text()
    assert "place_order" not in src
    assert "cancel_order" not in src
```

- [ ] **Step 2: Run to verify fail** — `python -m pytest tests/test_face_data_account.py -v` — FAIL (no `account_payload`)

- [ ] **Step 3: Append implementation + CLI to `scripts/face_data.py`**

```python
ORDERS_CAP = 50


def gate_state(env) -> dict:
    """Gate 1 the registration way (alpaca_kit.mcp.tools gates on flag AND
    keys); Gate 2 is intent-until-drilled and lives in face/README.md."""
    has_keys = bool(env.get("APCA_API_KEY_ID")) and bool(env.get("APCA_API_SECRET_KEY"))
    return {
        "gate1_registered": env.get("ALPACA_KIT_ENABLE_ORDERS") == "1" and has_keys,
        "gate1_rule": "ALPACA_KIT_ENABLE_ORDERS=1 AND APCA keys present",
        "gate2_validated": False,
        "gate2_note": "per-order human approval - intent until the drill in "
                      "face/README.md passes on a live face",
        "paper_pin": "hostname == paper-api.alpaca.markets enforced in code",
    }


def account_payload(client_factory, env) -> dict:
    """Read-only account view. Missing keys is an honest absence, not an
    error; the client is never constructed without keys."""
    has_keys = bool(env.get("APCA_API_KEY_ID")) and bool(env.get("APCA_API_SECRET_KEY"))
    if not has_keys:
        return {"ok": True, "available": False,
                "reason": "no APCA keys in the environment"}
    client = client_factory()
    return {
        "ok": True,
        "available": True,
        "account": client.get_account() or {},
        "positions": client.get_positions() or [],
        "orders": (client.get_orders() or [])[:ORDERS_CAP],
        "orders_gate": gate_state(env),
        "raw": "alpaca_kit.account.TradingClient - read methods only",
    }


def _real_market():
    """CLI assembly for the real bed. Kept out of the pure functions."""
    import pandas as pd
    from alpaca_kit.pit.pit_store import PITStore
    from alpaca_kit.pit.snapshot_source import SnapshotSource

    pit_root = os.environ.get("ALPHA_PIT_ROOT", BED_INFO["root"])
    store = PITStore(pit_root)
    src = SnapshotSource(store)
    cal = pd.read_parquet(os.path.join(pit_root, "calendar.parquet"))
    cal_days = [d.date() for d in pd.to_datetime(cal[cal.columns[0]]).tolist()]
    end_bound = Date.fromisoformat(BED_INFO["window"]["end"])
    days = sorted(d for d in cal_days if d <= end_bound and store.has_snapshot(d))
    if not days:
        raise RuntimeError(f"no captured snapshots under {pit_root}")
    return market_payload(src, days, days[-1])


def main(argv) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    try:
        if mode == "market":
            payload = _real_market()
        elif mode == "account":
            from alpaca_kit.account import TradingClient
            payload = account_payload(TradingClient, os.environ)
        else:
            raise RuntimeError("usage: face_data.py market|account")
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        json.dump(payload, sys.stdout, default=str)
        return 0
    except Exception as exc:  # the face renders this JSON as the 503 body
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```
Before finalizing, open `alpaca_kit/account.py:30-70` and confirm `TradingClient()` constructs
from env without arguments (adjust the factory call if it takes explicit keys — deviations
documented). Confirm `PITStore.has_snapshot` exists (it does; used by mcp/tools.py).

- [ ] **Step 4: Verify pass + whole suite** — `python -m pytest tests/test_face_data_account.py -v` then `python -m pytest` — green. Optional manual probe (bed present locally): `python3 scripts/face_data.py market | head -c 300`.

- [ ] **Step 5: Commit**

```bash
git add scripts/face_data.py tests/test_face_data_account.py
git commit -m "feat(face-data): account payload, honest gate state, CLI for both modes"
```

---

### Task 3: `face/src/data.ts` — cached spawning endpoints + wiring

**Files:**
- Create: `face/src/data.ts`
- Modify: `face/src/main.ts` (register after `registerStatic`)
- Test: `face/tests/data.test.ts`

**Interfaces:**
- Consumes: `ctx.webServer.register({kind:"exact", path, handler})` (same registrar shape as `static.ts`).
- Produces: `registerDataRoutes(webServer, opts)` where `opts = { spawn?: Spawner, now?: () => number, python?: string }`; `type Spawner = (argv: string[]) => Promise<{ stdout: string; code: number }>`; exported constants `TTL_MS = { market: 900_000, account: 60_000 }`, `SPAWN_TIMEOUT_MS = 30_000`; exported `defaultSpawner(python: string): Spawner` (execFile-based). Routes: exact `/data/market.json`, `/data/account.json`.

- [ ] **Step 1: Write the failing tests**

`face/tests/data.test.ts`:
```typescript
import test from "node:test";
import assert from "node:assert/strict";
import type { IncomingMessage, ServerResponse } from "node:http";
import { registerDataRoutes, TTL_MS } from "../src/data.ts";

type Route = { kind: string; path: string; handler: (req: IncomingMessage, res: ServerResponse) => void | Promise<void> };

function recorder() {
  const routes: Route[] = [];
  return { routes, register: (r: Route) => void routes.push(r) };
}

function fakeRes() {
  const out = { status: 0, body: "", headers: {} as Record<string, string> };
  return {
    out,
    res: {
      writeHead: (s: number, h?: Record<string, string>) => { out.status = s; Object.assign(out.headers, h ?? {}); },
      end: (b?: string | Buffer) => { out.body = String(b ?? ""); },
    } as unknown as ServerResponse,
  };
}

const REQ = {} as IncomingMessage;

function routesWith(spawn: (argv: string[]) => Promise<{ stdout: string; code: number }>, now: () => number) {
  const rec = recorder();
  registerDataRoutes(rec, { spawn, now });
  const byPath = new Map(rec.routes.map(r => [r.path, r]));
  return byPath;
}

test("happy path: spawns once, caches within TTL, spawns again after expiry", async () => {
  let calls = 0;
  let clock = 0;
  const byPath = routesWith(async () => { calls++; return { stdout: '{"ok":true,"n":1}', code: 0 }; }, () => clock);
  const route = byPath.get("/data/market.json")!;
  const a = fakeRes(); await route.handler(REQ, a.res);
  assert.equal(a.out.status, 200);
  assert.equal(JSON.parse(a.out.body).ok, true);
  const b = fakeRes(); await route.handler(REQ, b.res);
  assert.equal(calls, 1); // cached
  clock = TTL_MS.market + 1;
  const c = fakeRes(); await route.handler(REQ, c.res);
  assert.equal(calls, 2); // expired -> respawn
});

test("single-flight: concurrent requests share one spawn", async () => {
  let calls = 0;
  let release!: (v: { stdout: string; code: number }) => void;
  const gate = new Promise<{ stdout: string; code: number }>(r => { release = r; });
  const byPath = routesWith(() => { calls++; return gate; }, () => 0);
  const route = byPath.get("/data/account.json")!;
  const a = fakeRes(); const b = fakeRes();
  const p = Promise.all([route.handler(REQ, a.res), route.handler(REQ, b.res)]);
  release({ stdout: '{"ok":true}', code: 0 });
  await p;
  assert.equal(calls, 1);
  assert.equal(a.out.status, 200); assert.equal(b.out.status, 200);
});

test("stale-on-error: failure after a good cache serves cache with stale:true", async () => {
  let clock = 0; let fail = false;
  const byPath = routesWith(async () => {
    if (fail) throw new Error("boom");
    return { stdout: '{"ok":true,"v":7}', code: 0 };
  }, () => clock);
  const route = byPath.get("/data/market.json")!;
  const a = fakeRes(); await route.handler(REQ, a.res);
  fail = true; clock = TTL_MS.market + 1;
  const b = fakeRes(); await route.handler(REQ, b.res);
  assert.equal(b.out.status, 200);
  const body = JSON.parse(b.out.body);
  assert.equal(body.v, 7); assert.equal(body.stale, true);
});

test("503 with error JSON when no cache and the producer fails", async () => {
  const byPath = routesWith(async () => ({ stdout: '{"ok":false,"error":"no bed"}', code: 1 }), () => 0);
  const route = byPath.get("/data/market.json")!;
  const a = fakeRes(); await route.handler(REQ, a.res);
  assert.equal(a.out.status, 503);
  assert.equal(JSON.parse(a.out.body).ok, false);
});

test("a nonzero exit is never cached", async () => {
  let calls = 0;
  const byPath = routesWith(async () => { calls++; return { stdout: '{"ok":false,"error":"x"}', code: 1 }; }, () => 0);
  const route = byPath.get("/data/account.json")!;
  await route.handler(REQ, fakeRes().res);
  await route.handler(REQ, fakeRes().res);
  assert.equal(calls, 2);
});
```

- [ ] **Step 2: Verify fail** — `cd face && npm test` — FAIL (no `src/data.ts`)

- [ ] **Step 3: Implement `face/src/data.ts`**

```typescript
/** /data/market.json + /data/account.json - cached, single-flight spawns of
 * scripts/face_data.py. The spawner is injected for tests; the real one
 * (defaultSpawner) execFiles FACE_PYTHON with a FIXED argv - no request data
 * ever reaches the child (spec v2 section 3.1). Child stderr goes to the
 * face's stderr only. */
import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { IncomingMessage, ServerResponse } from "node:http";

export type Spawner = (argv: string[]) => Promise<{ stdout: string; code: number }>;

export const TTL_MS = { market: 900_000, account: 60_000 } as const;
export const SPAWN_TIMEOUT_MS = 30_000;

const moduleDir = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(moduleDir, "..", "..");
const SCRIPT = join(REPO_ROOT, "scripts", "face_data.py");

export function defaultSpawner(python: string): Spawner {
  return (argv) => new Promise((resolve, reject) => {
    execFile(python, argv, { cwd: REPO_ROOT, timeout: SPAWN_TIMEOUT_MS, maxBuffer: 32 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (stderr) process.stderr.write(`face-data: ${stderr}`);
        if (err && stdout === "") return reject(err); // timeout/ENOENT etc.
        const code = err && typeof (err as { code?: unknown }).code === "number"
          ? (err as { code: number }).code : err ? 1 : 0;
        resolve({ stdout: String(stdout), code });
      });
  });
}

type Mode = keyof typeof TTL_MS;
interface Entry { body: string; at: number }

export function registerDataRoutes(
  webServer: { register(route: { kind: "exact"; path: string; handler(req: IncomingMessage, res: ServerResponse): void | Promise<void> }): unknown },
  opts: { spawn?: Spawner; now?: () => number; python?: string } = {},
): void {
  const spawn = opts.spawn ?? defaultSpawner(opts.python ?? process.env.FACE_PYTHON ?? "python3");
  const now = opts.now ?? Date.now;
  const cache = new Map<Mode, Entry>();
  const inflight = new Map<Mode, Promise<{ stdout: string; code: number }>>();

  const send = (res: ServerResponse, status: number, body: string) => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(body);
  };

  const handler = (mode: Mode) => async (_req: IncomingMessage, res: ServerResponse) => {
    const hit = cache.get(mode);
    if (hit && now() - hit.at < TTL_MS[mode]) return send(res, 200, hit.body);
    let flight = inflight.get(mode);
    if (!flight) {
      flight = spawn([SCRIPT, mode]);
      inflight.set(mode, flight);
      void flight.finally(() => inflight.delete(mode));
    }
    try {
      const { stdout, code } = await flight;
      if (code === 0) {
        cache.set(mode, { body: stdout, at: now() });
        return send(res, 200, stdout);
      }
      // honest producer error: never cached
      if (hit) return send(res, 200, markStale(hit.body));
      return send(res, 503, stdout || '{"ok":false,"error":"producer failed"}');
    } catch (err) {
      if (hit) return send(res, 200, markStale(hit.body));
      return send(res, 503, JSON.stringify({ ok: false, error: String(err) }));
    }
  };

  webServer.register({ kind: "exact", path: "/data/market.json", handler: handler("market") });
  webServer.register({ kind: "exact", path: "/data/account.json", handler: handler("account") });
}

function markStale(body: string): string {
  try {
    const parsed = JSON.parse(body) as Record<string, unknown>;
    parsed.stale = true;
    return JSON.stringify(parsed);
  } catch {
    return body;
  }
}
```

- [ ] **Step 4: Wire into `face/src/main.ts`** — after the `registerStatic(...)` call add:

```typescript
import { registerDataRoutes } from "./data.ts";
// ...after registerStatic(booted.ctx.webServer, clientDir):
registerDataRoutes(booted.ctx.webServer);
```
(Adapt the exact variable names to main.ts's current code — read it first; keep the call
immediately after registerStatic.)

- [ ] **Step 5: Verify** — `cd face && npm test && npm run typecheck` — all green (data tests + all prior).

- [ ] **Step 6: Commit**

```bash
git add face/src/data.ts face/src/main.ts face/tests/data.test.ts
git commit -m "feat(face): /data endpoints - cached single-flight spawns of face_data.py"
```

---

### Task 4: the `/market` page

**Files:**
- Create: `face/client/market.html`, `face/client/market.js`
- Modify: `face/src/static.ts` (two new exact routes), `face/client/chat.css` (append `/* instruments */` block)
- Test: `face/tests/static.test.ts` (extend)

**Interfaces:**
- Consumes: `GET /data/market.json` (Task 3's payload = Task 1's shape + `generated_at`, maybe `stale`).
- Produces: route `exact /market` → `client/market.html`; the `/* instruments */` css block (shared with Task 5): `.inst-wrap`, `.inst-head`, `.inst-card`, `.inst-grid`, `.inst-note`, `.inst-stale`, `.inst-refresh`, `.inst-table`, `.spark`.

- [ ] **Step 1: Extend the static tests (failing first)**

Append to `face/tests/static.test.ts`:
```typescript
test("instrument pages are registered as exact routes", () => {
  const routes: Array<{ kind: string; path: string }> = [];
  registerStatic({ register: (r: { kind: string; path: string }) => void routes.push(r) }, "/srv/client");
  const paths = routes.map(r => `${r.kind}:${r.path}`);
  assert.ok(paths.includes("exact:/market"));
  assert.ok(paths.includes("exact:/account"));
});
```
(Adapt the recorder to the file's existing test helpers — reuse them; run `cd face && npm test` — the new test FAILS.)

- [ ] **Step 2: Register the routes in `face/src/static.ts`** — inside `registerStatic`, after the existing `/` route, add two exact routes serving `join(clientDir, "market.html")` and `join(clientDir, "account.html")` through the existing `serveFile` helper. Run the test — PASS. (`/account` 404s until Task 5 writes the file — the route may exist now; `serveFile` already answers 404 for a missing file.)

- [ ] **Step 3: Write `face/client/market.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Market — KAIROS</title>
<link rel="stylesheet" href="/client/chat.css">
</head>
<body class="inst-body">
<main class="inst-wrap">
  <header class="inst-head">
    <a class="inst-mark" href="/">KAIROS</a>
    <span class="inst-title">Market</span>
    <span id="asof" class="inst-note"></span>
    <span id="stamp" class="inst-note"></span>
    <button id="refresh" class="inst-refresh" title="re-fetch">refresh</button>
  </header>
  <div id="root"><p class="inst-note">loading…</p></div>
</main>
<script type="module" src="/client/market.js"></script>
</body>
</html>
```

- [ ] **Step 4: Write `face/client/market.js`** — plain browser ESM, no imports needed beyond fetch. Structure (write it fully; this is the render contract, not a sketch to trim):

```javascript
/** /market - the bed rendered live. Data: /data/market.json (Task 1 shape).
 * Honesty: warmup rail on the full bed window; null -> em-dash; stale stamp;
 * every panel keeps its raw pointer. No frameworks, hand-rolled SVG. */
const $ = (s) => document.querySelector(s);
const EM = "—";
const fmt = (v, f = (x) => String(x)) => (v === null || v === undefined ? EM : f(v));

function svgLine(points, w, h, cls) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  el.setAttribute("viewBox", `0 0 ${w} ${h}`);
  el.setAttribute("class", cls);
  const poly = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  poly.setAttribute("fill", "none");
  poly.setAttribute("stroke", "currentColor");
  poly.setAttribute("stroke-width", "1.5");
  poly.setAttribute("points", points.map(([x, y]) => `${x},${y}`).join(" "));
  el.append(poly);
  return el;
}

function tapeCard(tape, bed) {
  // pen-lift on null levels: build segments, skip nulls
  const s = tape.series;
  const levels = s.map(r => r.level).filter(v => v !== null);
  const lo = Math.min(...levels), hi = Math.max(...levels);
  const w = 720, h = 160;
  const pts = [];
  s.forEach((r, i) => {
    if (r.level === null) return;
    pts.push([(i / (s.length - 1)) * w, h - ((r.level - lo) / (hi - lo || 1)) * (h - 10) - 5]);
  });
  const card = el("section", "inst-card");
  card.append(el("h2", "inst-card-title", "The tape"),
              el("div", "inst-note", `equal-weight composite · ${s.length} sessions · 100 = ${s[0]?.date ?? EM}`));
  card.append(svgLine(pts, w, h, "spark tape"));
  card.append(maturityRail(bed, s[0]?.date, s[s.length - 1]?.date));
  card.append(el("div", "inst-note inst-raw", `raw · ${tape.raw}`));
  return card;
}

function maturityRail(bed, chartStart, chartEnd) {
  // the full bed window with warmup spans hatched - immature, not missing
  const rail = el("div", "inst-rail");
  const t0 = Date.parse(bed.window.start), t1 = Date.parse(bed.window.end);
  const pct = (d) => `${(((Date.parse(d) - t0) / (t1 - t0)) * 100).toFixed(1)}%`;
  for (const [key, label] of [["sma200_valid_from", "200DMA"], ["week52_valid_from", "52wk"], ["trend_template_valid_from", "trend-t"]]) {
    const lane = el("div", "inst-lane");
    const hatch = el("div", "inst-lane-immature");
    hatch.style.width = pct(bed.warmup[key]);
    hatch.title = `${label} immature before ${bed.warmup[key]} - immature, not missing`;
    lane.append(hatch, el("span", "inst-lane-label", label));
    rail.append(lane);
  }
  if (chartStart) {
    const bracket = el("div", "inst-lane-bracket");
    bracket.style.left = pct(chartStart);
    bracket.style.width = `calc(${pct(chartEnd)} - ${pct(chartStart)})`;
    bracket.title = "charted span";
    rail.append(bracket);
  }
  rail.append(el("div", "inst-note", bed.warmup.note));
  return rail;
}

function breadthCard(breadth) {
  const s = breadth.series;
  const last = s[s.length - 1] ?? {};
  const card = el("section", "inst-card");
  card.append(el("h2", "inst-card-title", "Breadth"));
  const grid = el("div", "inst-grid");
  grid.append(stat("% > 200DMA", fmt(last.pct_above_200dma, v => `${(v * 100).toFixed(1)}%`)),
              stat("net new highs", fmt(last.net_new_highs)),
              stat("adv / decl", `${fmt(last.advances)} / ${fmt(last.declines)}`));
  card.append(grid);
  const pctPts = [];
  s.forEach((r, i) => { if (r.pct_above_200dma !== null) pctPts.push([(i / (s.length - 1)) * 720, 60 - r.pct_above_200dma * 55]); });
  card.append(svgLine(pctPts, 720, 64, "spark"));
  card.append(el("div", "inst-note inst-raw", `raw · ${breadth.raw}`));
  return card;
}

function screensCard(screens) {
  const card = el("section", "inst-card");
  card.append(el("h2", "inst-card-title", "Screens"));
  for (const [kind, data] of Object.entries(screens)) {
    card.append(el("h3", "inst-sub", `${kind} · ${data.rows.length}`));
    const t = el("table", "inst-table");
    const head = el("tr", "");
    for (const c of ["symbol", "close", "Δ%", "gap%", "rs", "last 60"]) head.append(el("th", "", c));
    t.append(head);
    for (const r of data.rows) {
      const row = el("tr", "");
      row.append(el("td", "mono", r.symbol),
                 el("td", "mono", fmt(r.close, v => Number(v).toFixed(2))),
                 el("td", "mono", fmt(r.pct_change, v => `${Number(v).toFixed(2)}%`)),
                 el("td", "mono", fmt(r.gap_pct, v => `${Number(v).toFixed(2)}%`)),
                 el("td", "mono", fmt(r.rs_percentile, v => Number(v).toFixed(1))));
      const cell = el("td", "");
      if (Array.isArray(r.spark) && r.spark.length > 1) {
        const lo = Math.min(...r.spark), hi = Math.max(...r.spark);
        cell.append(svgLine(r.spark.map((v, i) => [(i / (r.spark.length - 1)) * 80, 18 - ((v - lo) / (hi - lo || 1)) * 16]), 80, 20, "spark row"));
      } else cell.textContent = EM;
      row.append(cell);
      t.append(row);
    }
    const scroller = el("div", "inst-scroll");
    scroller.append(t);
    card.append(scroller, el("div", "inst-note inst-raw", `raw · ${data.raw}`));
  }
  return card;
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
function stat(label, value) {
  const s = el("div", "inst-stat");
  s.append(el("div", "inst-stat-label", label), el("div", "inst-stat-value mono", value));
  return s;
}

async function load() {
  const root = $("#root");
  root.replaceChildren(el("p", "inst-note", "loading…"));
  try {
    const res = await fetch("/data/market.json");
    const data = await res.json();
    if (!data.ok) {
      root.replaceChildren(el("p", "inst-note", `no reading — ${data.error ?? "producer failed"}`));
      return;
    }
    $("#asof").textContent = `as of ${data.as_of} · bed ${data.bed.root}`;
    $("#stamp").textContent = `${data.stale ? "STALE · " : ""}generated ${data.generated_at ?? EM}`;
    $("#stamp").classList.toggle("inst-stale", Boolean(data.stale));
    root.replaceChildren(tapeCard(data.tape, data.bed), breadthCard(data.breadth), screensCard(data.screens));
  } catch (err) {
    root.replaceChildren(el("p", "inst-note", `no reading — ${err}`));
  }
}
$("#refresh").onclick = () => void load();
void load();
```

- [ ] **Step 5: Append the `/* instruments */` block to `face/client/chat.css`** — light tokens consistent with the existing file (read its custom properties first and reuse them): `.inst-body` (page background = the chat page's ground), `.inst-wrap` (max-width 960px, centered), `.inst-head` (flex row, wordmark link, mono notes), `.inst-card` (the flat-card idiom the chat's tool cards use: 1px border, subtle radius, padding), `.inst-grid`/`.inst-stat` (label small caps, value mono large), `.inst-table` (mono cells, header small caps, row borders), `.inst-scroll { overflow-x: auto }`, `.spark { color: <the accent or a neutral>; width: 100%; height: auto }`, `.inst-rail`/`.inst-lane`/`.inst-lane-immature` (thin lanes, hatched immature spans via `repeating-linear-gradient`, positioned bracket), `.inst-stale` (amber tint — reuse the css's existing warn color if one exists), `.inst-refresh` (quiet button), `.inst-raw` (dotted underline, small). Write real CSS — no framework, ~80 lines.

- [ ] **Step 6: Verify** — `cd face && npm test && npm run typecheck` green; `node --check client/market.js` clean. Manual probe (best-effort): `npm start`, open `http://127.0.0.1:3090/market` — first load spawns the real producer (~1-2 min for the bed; the fetch waits or times out at 30 s and the page shows the honest error; a later refresh hits the cache). Record what happened.

- [ ] **Step 7: Commit**

```bash
git add face/client/market.html face/client/market.js face/client/chat.css face/src/static.ts face/tests/static.test.ts
git commit -m "feat(face): /market instrument page - tape, maturity rail, breadth, screens"
```

---

### Task 5: the `/account` page

**Files:**
- Create: `face/client/account.html`, `face/client/account.js`
- Modify: `face/client/chat.css` (extend the `/* instruments */` block only if a needed class is missing)

**Interfaces:**
- Consumes: `GET /data/account.json` (Task 2 shape), the `/* instruments */` css (Task 4), the `/account` route (registered in Task 4).

- [ ] **Step 1: Write `face/client/account.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Account — KAIROS</title>
<link rel="stylesheet" href="/client/chat.css">
</head>
<body class="inst-body">
<main class="inst-wrap">
  <header class="inst-head">
    <a class="inst-mark" href="/">KAIROS</a>
    <span class="inst-title">Account</span>
    <span id="stamp" class="inst-note"></span>
    <button id="refresh" class="inst-refresh" title="re-fetch">refresh</button>
  </header>
  <div id="root"><p class="inst-note">loading…</p></div>
</main>
<script type="module" src="/client/account.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `face/client/account.js`**

```javascript
/** /account - paper account, read-only. Data: /data/account.json.
 * available:false renders an honest empty state; the double gate renders as
 * a compact severed-circuit strip from the REAL orders_gate payload. */
const $ = (s) => document.querySelector(s);
const EM = "—";
const money = (v) => (v === null || v === undefined ? EM : `$${Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}
function stat(label, value) {
  const s = el("div", "inst-stat");
  s.append(el("div", "inst-stat-label", label), el("div", "inst-stat-value mono", value));
  return s;
}

function summaryCard(account) {
  const card = el("section", "inst-card");
  card.append(el("h2", "inst-card-title", "Paper account"),
              el("div", "inst-note", `host · paper-api.alpaca.markets · status ${account.status ?? EM}`));
  const grid = el("div", "inst-grid");
  grid.append(stat("equity", money(account.equity)), stat("cash", money(account.cash)),
              stat("buying power", money(account.buying_power)));
  card.append(grid);
  return card;
}

function tableCard(title, rows, cols) {
  const card = el("section", "inst-card");
  card.append(el("h2", "inst-card-title", title));
  if (!rows.length) { card.append(el("p", "inst-note", `none ${EM} nothing held back`)); return card; }
  const t = el("table", "inst-table");
  const head = el("tr", "");
  for (const [label] of cols) head.append(el("th", "", label));
  t.append(head);
  for (const r of rows) {
    const tr = el("tr", "");
    for (const [, render] of cols) tr.append(el("td", "mono", render(r)));
    t.append(tr);
  }
  const scroller = el("div", "inst-scroll");
  scroller.append(t);
  card.append(scroller);
  return card;
}

function gateCard(gate) {
  const card = el("section", "inst-card inst-gate");
  card.append(el("h2", "inst-card-title", "The order gates"));
  const strip = el("div", "inst-circuit");
  const seg = (label, on, note) => {
    const s = el("div", `inst-gate-node${on ? " on" : " off"}`);
    s.append(el("div", "inst-gate-glyph", on ? "◈" : "⊘"), el("div", "inst-gate-label", label));
    s.title = note;
    return s;
  };
  strip.append(el("div", "inst-gate-node src", "order intent"),
               cut(!gate.gate1_registered),
               seg("GATE 1 · registration", gate.gate1_registered, gate.gate1_rule),
               cut(!gate.gate1_registered || !gate.gate2_validated),
               seg("GATE 2 · human approval", gate.gate2_validated, gate.gate2_note),
               cut(!gate.gate1_registered || !gate.gate2_validated),
               el("div", "inst-gate-node host mono", "paper-api.alpaca.markets"));
  card.append(strip);
  card.append(el("p", "inst-note", gate.gate2_validated ? "" :
    "Gate 2 is intent until the drill in face/README.md passes on a live face."));
  card.append(el("div", "inst-note inst-raw", `raw · ${gate.paper_pin}`));
  return card;

  function cut(severed) {
    return el("div", `inst-gate-wire${severed ? " severed" : ""}`, severed ? "⊘" : "");
  }
}

async function load() {
  const root = $("#root");
  root.replaceChildren(el("p", "inst-note", "loading…"));
  try {
    const res = await fetch("/data/account.json");
    const data = await res.json();
    if (!data.ok) { root.replaceChildren(el("p", "inst-note", `no reading — ${data.error ?? "producer failed"}`)); return; }
    $("#stamp").textContent = `${data.stale ? "STALE · " : ""}generated ${data.generated_at ?? EM}`;
    $("#stamp").classList.toggle("inst-stale", Boolean(data.stale));
    if (data.available === false) {
      root.replaceChildren(el("p", "inst-note", `not available — ${data.reason}`),
                           gateCard({ gate1_registered: false, gate1_rule: "ALPACA_KIT_ENABLE_ORDERS=1 AND APCA keys present", gate2_validated: false, gate2_note: "per-order human approval - intent until drilled", paper_pin: "hostname == paper-api.alpaca.markets enforced in code" }));
      return;
    }
    root.replaceChildren(
      summaryCard(data.account),
      tableCard("Positions", data.positions ?? [], [
        ["symbol", r => r.symbol ?? EM], ["qty", r => r.qty ?? EM],
        ["avg entry", r => money(r.avg_entry_price)], ["value", r => money(r.market_value)],
        ["unrl %", r => r.unrealized_plpc === undefined ? EM : `${(Number(r.unrealized_plpc) * 100).toFixed(2)}%`],
      ]),
      tableCard("Recent orders (read-only)", data.orders ?? [], [
        ["symbol", r => r.symbol ?? EM], ["side", r => r.side ?? EM], ["qty", r => r.qty ?? EM],
        ["status", r => r.status ?? EM], ["submitted", r => r.submitted_at ?? EM],
      ]),
      gateCard(data.orders_gate),
    );
  } catch (err) {
    root.replaceChildren(el("p", "inst-note", `no reading — ${err}`));
  }
}
$("#refresh").onclick = () => void load();
void load();
```

- [ ] **Step 3: Extend the `/* instruments */` css** with the gate-strip classes if not present: `.inst-circuit` (flex row, centered, gap), `.inst-gate-node` (small bordered chip; `.on` = normal ink, `.off` = dimmed), `.inst-gate-glyph` (mono), `.inst-gate-wire` (a 24-40px horizontal rule; `.severed` = dashed with the ⊘ centered, dimmed). Keep it quiet — this is the light translation of R2's severed circuit, not a replica.

- [ ] **Step 4: Verify** — `cd face && npm test && npm run typecheck`; `node --check client/account.js`. Manual probe: with no APCA env, `/account` renders the honest not-available state + the unarmed gate strip.

- [ ] **Step 5: Commit**

```bash
git add face/client/account.html face/client/account.js face/client/chat.css
git commit -m "feat(face): /account instrument page - summary, positions, orders, gate circuit"
```

---

### Task 6: nav, smoke extension, docs, suites

**Files:**
- Modify: `face/client/index.html` (sidebar footer links), `face/tests/smoke.test.ts` (page + plumbing asserts), `face/README.md` (instruments section), `CLAUDE.md` (face row mention)

**Interfaces:**
- Consumes: everything prior.

- [ ] **Step 1: Nav** — in `face/client/index.html`, the sidebar footer (the element carrying "live · loopback only") gains two quiet links: `<a href="/market">Market</a> · <a href="/account">Account</a>` (style with an existing quiet class or one small `/* instruments */` rule). Both instrument pages already link back via the wordmark.

- [ ] **Step 2: Smoke extension (failing first, then green)** — in `face/tests/smoke.test.ts`, inside the existing single boot test (ONE boot per process — do not add a second `test()` with a boot), after the existing asserts add:

```typescript
    // instrument pages serve
    for (const path of ["/market", "/account"]) {
      const page = await fetch(`${base}${path}`);
      assert.equal(page.status, 200, path);
      assert.match(await page.text(), /KAIROS/);
    }
    // data plumbing through a stub producer - fast, deterministic, no bed
    const stub = join(home, "stub.sh");
    writeFileSync(stub, `#!/bin/sh\necho '{"ok":true,"stub":true,"generated_at":"x"}'\n`, { mode: 0o755 });
    registerDataRoutes(ctx.webServer, { spawn: (argv) => new Promise((resolve, reject) => {
      execFile(stub, argv.slice(1), (err, stdout) => err ? reject(err) : resolve({ stdout: String(stdout), code: 0 }));
    }) });
    const dataRes = await fetch(`${base}/data/market.json`);
    assert.equal(dataRes.status, 200);
    assert.equal((await dataRes.json()).stub, true);
```
NOTE: `registerDataRoutes` must be called here for the first time in the smoke (do NOT also
register the default routes in the smoke path — the smoke builds its server by hand via
`bootFace` + `registerStatic`; duplicate (kind,path) registration throws, which is exactly the
guard). Imports to add: `registerDataRoutes` from `../src/data.ts`, `execFile` from
`node:child_process`, `writeFileSync` already or from `node:fs`. Run gated-off (skip clean),
then `FACE_SMOKE=1 npm test` — green.

- [ ] **Step 3: README** — `face/README.md` gains an "Instruments" section: the two pages, the producer (`scripts/face_data.py`, spawned with `FACE_PYTHON`, default `python3`, must import `alpaca_kit` — `pip install -e .` at the repo root is the prerequisite), market needs the bed (`ALPHA_PIT_ROOT`, default `data/pit/2yr`), account needs `source .env.alpaca` BEFORE `npm start` (same trust posture as the dsh MCP mount) and renders an honest not-available state without it; TTLs (market 15 min / account 60 s), stale stamp semantics, first market load can take ~1-2 min (bed walk) — the page shows the honest timeout error and a later refresh hits the cache. One sentence: the pages are read-only; the gate strip displays computed fact, operates nothing.

- [ ] **Step 4: CLAUDE.md** — extend the existing `face/` Map row with "+ read-only /market and /account instrument pages fed by scripts/face_data.py". Keep the row one line.

- [ ] **Step 5: Both suites** — `python -m pytest` (expect > 324, all green) and `cd face && npm test && npm run typecheck` and `FACE_SMOKE=1 npm test` — report exact counts.

- [ ] **Step 6: Commit**

```bash
git add face/client/index.html face/tests/smoke.test.ts face/README.md CLAUDE.md
git commit -m "feat(face): instruments nav, smoke coverage, docs"
```
