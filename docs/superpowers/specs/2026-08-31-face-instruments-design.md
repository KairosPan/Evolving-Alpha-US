# face v2 — /market and /account instrument pages (real data, light minimal)

**Date:** 2026-08-31 · **Status:** approved direction, spec for implementation
**Authority:** mechanism authority for this increment; `Kairos-Design.md` outranks on intent;
the v1 face spec (`2026-08-30-face-chat-light-design.md`) governs everything it already covers.
Design lineage: the R2 instrument prototypes (`docs/design/prototypes/r2/{market,account}.html`)
are the content architecture; the operator chose **light-minimal unified** (chat-light tokens)
over the Observatory dark skin for these pages.

## 1. What this adds

Two read-only instrument pages served by the existing face process:

- **`/market`** — the 2yr PIT bed rendered live: equal-weight tape composite (~250 sessions)
  with the bed-window maturity rail, the breadth series (~60 sessions: %>200DMA, net new
  highs, advances/declines), and the daily screens (trend_template + gainer) with sparklines.
- **`/account`** — the paper account: account summary, open positions, recent orders
  (read-only), and the double order gate displayed as computed fact.

Data comes from a Python producer the face spawns on demand — the face stays a Node process;
`alpaca_kit` stays the only reader of the bed and the trading host.

## 2. The producer — `scripts/face_data.py`

One script, two modes, JSON to stdout:

- `python3 scripts/face_data.py market` — no keys needed. Reads the bed at
  `ALPHA_PIT_ROOT` (default `data/pit/2yr`) through the production code paths
  (`SnapshotSource`/`GuardedSource`/`market_breadth`/`build_universe`) — the same assembly the
  round-1 design extractor used, now a maintained script. Payload mirrors the R2 mock's shape
  (`bed` + warmup constants, `as_of`, `breadth.series`, `tape.series`,
  `screens.{trend_template,gainer}.rows` with `spark`), plus `generated_at` (UTC ISO). A
  missing/empty bed exits nonzero with a one-line JSON error on stdout
  (`{"ok": false, "error": ...}`).
- `python3 scripts/face_data.py account` — reads `APCA_*` from the environment.
  `TradingClient.get_account/get_positions/get_orders` ONLY — the script never imports or
  reaches a code path that could place or cancel; grep-level absence is a test. Payload:
  `account`, `positions`, `orders` (most recent, capped), `orders_gate` computed the way
  `build_tools` gates registration (`ALPACA_KIT_ENABLE_ORDERS` set AND keys present —
  honest fact, not mock), `generated_at`. Missing keys is NOT an error:
  `{"ok": true, "available": false, "reason": "no APCA keys in the environment"}` — the page
  renders the absence.

Structure: pure assembly functions (`market_payload(source, store, ...)`,
`account_payload(client_factory, env)`) + a thin CLI. The pure functions are unit-tested
offline with the existing fake/fixture machinery (FakeSource, tmp PITStore beds, a fake
trading client); the real-bed/real-keys paths are operator-run. Tests live in `tests/`
(the Python suite grows past 324).

## 3. The face side

### 3.1 Data endpoints (`face/src/data.ts`)

`GET /data/market.json` and `GET /data/account.json`, registered on `ctx.webServer` beside
the static routes:

- Spawns `FACE_PYTHON` (env, default `python3`) with `[scripts/face_data.py, <mode>]`,
  cwd = process cwd (the repo root — v1's chdir guarantees the script path resolves), env
  inherited (that is how APCA keys reach the account mode: the operator sources `.env.alpaca`
  before `npm start`, same trust posture as dsh spawning the MCP server).
- TTL cache per mode: market 15 min, account 60 s (constants; no config surface in v2).
- Single-flight: concurrent requests during a spawn share one child.
- On spawn failure/timeout (30 s cap) with a cached payload present: serve the cache with
  `stale: true` added. With no cache: 503 with the error JSON. Never crash the face.
- The spawner is injected (`(argv) => Promise<{stdout, code}>`) so cache/TTL/single-flight/
  stale logic is unit-tested without Python.
- Security: fixed script path, fixed mode strings — no request data ever reaches the spawn.
  Child stderr is logged to the face's stderr, never sent to the browser.

### 3.2 The pages (`face/client/market.html|js`, `face/client/account.html|js`)

Light-minimal unified: the pages `<link>` the existing `chat.css` and compose in its
vocabulary (flat cards one notch quieter than bubbles, mono numerics, quiet raw pointers) —
page-local additions appended under the existing `/* live additions */` convention (a new
`/* instruments */` block). The R2 prototypes donate CONTENT architecture, not their skin:

- `/market`: as-of + bed facts header; tape chart (hand-rolled SVG) with the full bed-window
  maturity rail (warmup spans hatched, "immature, not missing"); breadth panel; screens
  table with tabs, spark polylines, `rs_percentile`, null → em-dash; every panel keeps a
  quiet raw pointer (producing function / bed path).
- `/account`: account summary card (equity/cash/buying power, paper host stated); positions
  table; recent orders table (read-only); the **double gate** as a compact severed-circuit
  strip driven by the REAL `orders_gate` payload (Gate 1 computed; Gate 2 stays
  intent-until-drilled wording pointing at the README drill). `available: false` renders as
  an honest empty state naming the missing keys — never fake shape.
- Both: `generated_at` + `stale` stamp rendered; a manual refresh control re-fetches (the
  only interaction; still zero write affordances); no frameworks, no new deps.

### 3.3 Navigation

The chat sidebar footer gains two quiet links (`Market · Account`); both instrument pages
carry a small wordmark link back to `/`. No shell rebuild — three pages, one voice.

## 4. Non-goals (v2)

Strategy shelf page · closed-trades/activities history beyond `get_orders` · live streaming
for instrument data (fetch + manual refresh only) · charts libraries · any order action ·
configurable TTLs · dark skin (the Observatory grammar stays in the design reservoir).

## 5. Testing

- Python: pure-function tests for both payload assemblers (fixture bed + fake client),
  including the no-keys account path, the gate computation truth table, and the
  no-order-code-path grep test.
- Face: `data.ts` unit tests with an injected fake spawner (TTL expiry, single-flight,
  stale-on-error, 503-no-cache, timeout). Existing suites stay green.
- Smoke (`FACE_SMOKE=1`) extends: `/market` and `/account` pages serve 200; the data
  endpoints answer (real Python spawn in the scratch boot — market may legitimately return
  the no-bed error JSON in a scratch home: assert the honest-error shape, not success).

## 6. Risks

Python-from-Node coupling (interpreter discovery via `FACE_PYTHON`, import failures surface
as the 503 JSON — the README documents the `pip install -e .` prerequisite) · bed staleness
(the bed ends 2026-07-09; the page shows `as_of`, no pretense of live market data) · account
mode inherits whatever env the operator started with (documented; keys never logged).
