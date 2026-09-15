import test from "node:test";
import assert from "node:assert/strict";
import { createQuoteSnapshots, QUOTE_RESPONSE_LIMIT, type QuoteFetch } from "../src/quote-snapshots.ts";
import type { QuoteIdentity } from "../src/quote-types.ts";
const NOW = Date.parse("2026-09-15T14:30:00Z");
const us: QuoteIdentity = { id: "us:AAPL", market: "us", symbol: "AAPL" };
const cn: QuoteIdentity = { id: "cn:603986", market: "cn", symbol: "603986" };
const btc: QuoteIdentity = { id: "crypto:BTC/USD", market: "crypto", symbol: "BTC/USD" };
const credentials = { APCA_API_KEY_ID: "test-key", APCA_API_SECRET_KEY: "test-secret" };
const json = (value: unknown) => new Response(JSON.stringify(value));
const snapshot = { latestTrade: { p: 225.2, t: "2026-09-15T14:29:58.123456789Z" },
  dailyBar: { c: 225, v: 19000, t: "2026-09-15T04:00:00Z" }, prevDailyBar: { c: 220, t: "2026-09-14T04:00:00Z" } };
const ticker = { price: "6268.48", time: "2026-09-15T14:29:57.833Z", volume: "53602.03940154" };

test("unconfigured private providers do not make network requests or create fake quotes", async () => {
  let calls = 0;
  const result = await createQuoteSnapshots({ env: {}, fetcher: async () => { calls++; return json({}); } }).load([us, cn]);
  assert.equal(calls, 0);
  assert.deepEqual(result.providers.map((provider) => provider.status), ["unconfigured", "unconfigured"]);
  assert.match(result.providers[1]!.message, /开通 iFinD/);
  assert.ok(result.updates.every((update) => update.price === undefined && update.as_of === undefined));
});

test("Alpaca batches selected symbols, authenticates fixed hosts, preserves event precision and clock", async () => {
  const seen: { url: URL; options: RequestInit }[] = [];
  const result = await createQuoteSnapshots({ env: credentials, now: () => NOW, fetcher: async (url, options) => {
    seen.push({ url, options });
    return json(url.pathname === "/v2/clock" ? { is_open: true, timestamp: new Date(NOW).toISOString() } : { AAPL: snapshot });
  } }).load([us, us]);
  assert.equal(seen.length, 2);
  const request = seen.find(({ url }) => url.pathname.endsWith("snapshots"))!;
  assert.equal(request.url.origin, "https://data.alpaca.markets");
  assert.equal(request.url.searchParams.get("symbols"), "AAPL");
  assert.equal(request.url.searchParams.get("feed"), "iex");
  assert.equal(new Headers(request.options.headers).get("APCA-API-SECRET-KEY"), "test-secret");
  assert.equal(request.options.redirect, "error");
  assert.deepEqual(result.updates, [{ id: us.id, source: "Alpaca", feed: "iex", basis: "previous_close", price: 225.2,
    prev_close: 220, volume: 19000, as_of: snapshot.latestTrade.t, volume_as_of: snapshot.dailyBar.t, market_status: "open", message: "" }]);
  assert.equal(result.providers[0]!.status, "connected");
  assert.match(result.providers[0]!.message, /单交易所/);
});

test("Alpaca premarket uses completed session close without presenting yesterday's volume as current", async () => {
  const result = await createQuoteSnapshots({ env: { ...credentials, ALPHA_DATA_FEED: "SIP" }, fetcher: async (url) => {
    if (url.pathname === "/v2/clock") throw new Error("private diagnostic");
    return json({ AAPL: { ...snapshot, dailyBar: { c: 223, v: 2000, t: "2026-09-14T04:00:00Z" } } });
  } }).load([us]);
  assert.equal(result.updates[0]!.prev_close, 223);
  assert.equal(result.updates[0]!.volume, null);
  assert.equal(result.updates[0]!.market_status, "unknown");
  assert.equal(result.updates[0]!.feed, "sip");
  assert.equal(JSON.stringify(result).includes("diagnostic"), false);
});

test("arbitrary account hosts and unsupported feeds never receive credentials", async () => {
  const seen: string[] = [];
  const result = await createQuoteSnapshots({ env: { ...credentials, APCA_API_BASE_URL: "https://evil.invalid" }, fetcher: async (url) => {
    seen.push(url.origin); return json({ AAPL: snapshot });
  } }).load([us]);
  assert.deepEqual(seen, ["https://data.alpaca.markets"]);
  assert.equal(result.updates[0]!.market_status, "unknown");
  const bad = await createQuoteSnapshots({ env: { ...credentials, ALPHA_DATA_FEED: "https://evil.invalid" }, fetcher: async () => { throw new Error("must not fetch"); } }).load([us]);
  assert.equal(bad.providers[0]!.status, "unconfigured");
});

test("missing trades do not borrow daily closes or invent zeros", async () => {
  const missing: QuoteIdentity = { id: "us:MISSING", market: "us", symbol: "MISSING" };
  const result = await createQuoteSnapshots({ env: credentials, fetcher: async (url) => json(url.pathname === "/v2/clock" ? {} : {
    AAPL: { latestTrade: { p: 0, t: "bad" }, dailyBar: { c: 100, v: null }, prevDailyBar: { c: "" } }, MISSING: null,
  }) }).load([us, missing]);
  assert.equal(result.providers[0]!.status, "limited");
  assert.equal(result.updates[0]!.price, null);
  assert.equal(result.updates[0]!.volume, null);
  assert.equal(result.updates[0]!.prev_close, null);
  assert.equal(result.updates[1]!.price, undefined);
});

test("Coinbase uses exact selected USD pair, 24h baseline and actual ticker timestamp", async () => {
  const seen: string[] = [];
  const result = await createQuoteSnapshots({ env: {}, coinbaseSpacingMs: 0, fetcher: async (url, options) => {
    seen.push(url.href);
    assert.equal(new Headers(options.headers).has("APCA-API-KEY-ID"), false);
    return json(url.pathname.endsWith("ticker") ? ticker : { open: "6000", volume: "99999" });
  } }).load([btc]);
  assert.deepEqual(seen, ["https://api.exchange.coinbase.com/products/BTC-USD/ticker", "https://api.exchange.coinbase.com/products/BTC-USD/stats"]);
  assert.deepEqual(result.updates, [{ id: btc.id, source: "Coinbase", feed: "exchange", basis: "24h", price: 6268.48,
    prev_close: 6000, volume: 53602.03940154, as_of: ticker.time, volume_as_of: null, market_status: "open", message: "" }]);
});

test("unsupported pairs and failed stats are explicit while a valid Coinbase ticker remains usable", async () => {
  const seen: string[] = [];
  const coins: QuoteIdentity[] = [btc, { id: "crypto:BTC/EUR", market: "crypto", symbol: "BTC/EUR" }, { id: "crypto:FAKE/USD", market: "crypto", symbol: "FAKE/USD" }];
  const result = await createQuoteSnapshots({ env: {}, coinbaseSpacingMs: 0, fetcher: async (url) => {
    seen.push(url.pathname);
    if (url.pathname.includes("FAKE")) return new Response("private vendor text", { status: 404 });
    if (url.pathname.endsWith("stats")) return new Response("private vendor text", { status: 500 });
    return json(ticker);
  } }).load(coins);
  assert.equal(result.updates[0]!.price, 6268.48);
  assert.equal(result.updates[0]!.prev_close, null);
  assert.match(result.updates[0]!.message!, /24 小时/);
  assert.match(result.updates[1]!.message!, /不支持/);
  assert.match(result.updates[2]!.message!, /不支持/);
  assert.equal(seen.some((path) => path.includes("EUR")), false);
  assert.equal(result.providers[0]!.status, "limited");
  assert.equal(JSON.stringify(result).includes("private"), false);
});

test("one provider outage is isolated from other markets and errors are sanitized", async () => {
  const result = await createQuoteSnapshots({ env: credentials, coinbaseSpacingMs: 0, fetcher: async (url) => {
    if (url.hostname.includes("alpaca")) return new Response("API-key: private", { status: 403 });
    return json(url.pathname.endsWith("ticker") ? ticker : { open: "6000" });
  } }).load([us, cn, btc]);
  assert.deepEqual(result.providers.map((provider) => provider.status), ["error", "unconfigured", "connected"]);
  assert.match(result.providers[0]!.message, /凭据或行情权限/);
  assert.equal(JSON.stringify(result).includes("private"), false);
  assert.equal(result.updates.find((update) => update.id === btc.id)!.price, 6268.48);
});

test("iFinD sends requested exchange codes and converts supplied Beijing event time", async () => {
  const seen: { url: URL; options: RequestInit }[] = [];
  const more: QuoteIdentity[] = [cn, { id: "cn:300750", market: "cn", symbol: "300750" }, { id: "cn:920185", market: "cn", symbol: "920185" }];
  const result = await createQuoteSnapshots({ env: { IFIND_ACCESS_TOKEN: "test-access" }, fetcher: async (url, options) => {
    seen.push({ url, options });
    return json({ errorcode: 0, tables: [{ thscode: "603986.SH", time: ["2026-09-15 15:00:03"], table: {
      latest: [165.5], preClose: [160], volume: [0], tradeDate: [20260915], tradeTime: [150000],
    } }] });
  } }).load(more);
  assert.equal(seen.length, 1);
  assert.equal(seen[0]!.url.href, "https://quantapi.51ifind.com/api/v1/real_time_quotation");
  assert.equal(new Headers(seen[0]!.options.headers).get("access_token"), "test-access");
  assert.deepEqual(JSON.parse(String(seen[0]!.options.body)), { codes: "603986.SH,300750.SZ,920185.BJ", indicators: "latest,preClose,tradeDate,tradeTime" });
  assert.equal(result.updates[0]!.price, 165.5);
  assert.equal(result.updates[0]!.volume, null);
  assert.equal(Date.parse(result.updates[0]!.as_of!), Date.parse("2026-09-15T07:00:00Z"));
  assert.equal(result.updates[0]!.market_status, "unknown");
  assert.equal(result.providers[0]!.status, "limited");
});

test("iFinD missing event times remain missing and returned errors never reveal tokens", async () => {
  for (const time of ["2026-09-15", "", null]) {
    const result = await createQuoteSnapshots({ env: { IFIND_ACCESS_TOKEN: "private" }, fetcher: async () => json({ errorcode: 0, tables: [
      { thscode: "603986.SH", time: [time], table: { latest: [165.5], preClose: [160] } },
    ] }) }).load([cn]);
    assert.equal(result.updates[0]!.as_of, null);
    assert.equal(result.updates[0]!.volume, null);
    assert.equal(result.providers[0]!.status, "limited");
  }
  const result = await createQuoteSnapshots({ env: { IFIND_ACCESS_TOKEN: "private" }, fetcher: async () => json({ errorcode: -102, errmsg: "bad token private", tables: [] }) }).load([cn]);
  assert.equal(result.providers[0]!.status, "error");
  assert.equal(JSON.stringify(result).includes("private"), false);
});

test("iFinD refresh-token acquisition is shared only in memory and never rotates tokens", async () => {
  const seen: string[] = [];
  const source = createQuoteSnapshots({ env: { IFIND_REFRESH_TOKEN: "test-refresh" }, now: () => NOW, fetcher: async (url, options) => {
    seen.push(url.pathname);
    if (url.pathname.endsWith("get_access_token")) {
      assert.equal(new Headers(options.headers).get("refresh_token"), "test-refresh");
      return json({ errorcode: 0, data: { access_token: "test-acquired" } });
    }
    assert.equal(new Headers(options.headers).get("access_token"), "test-acquired");
    return json({ errorcode: 0, tables: [] });
  } });
  await Promise.all([source.load([cn]), source.load([cn])]);
  await source.load([cn]);
  assert.equal(seen.filter((path) => path.endsWith("get_access_token")).length, 1);
  assert.equal(seen.filter((path) => path.endsWith("real_time_quotation")).length, 3);
});

test("timeouts cover ignored cancellation and stalled response bodies", async () => {
  const handlers: QuoteFetch[] = [async () => new Promise<Response>(() => {}), async () => new Response(new ReadableStream<Uint8Array>({ start(controller) {
    controller.enqueue(new TextEncoder().encode('{"price":'));
  } }))];
  for (const fetcher of handlers) {
    const result = await createQuoteSnapshots({ env: {}, timeoutMs: 15, coinbaseSpacingMs: 0, fetcher }).load([btc]);
    assert.equal(result.providers[0]!.status, "error");
    assert.match(result.updates[0]!.message!, /超时/);
  }
});

test("oversized, malformed, zero and timestamp-free payloads never become live quotes", async () => {
  const responses = [() => new Response("x", { headers: { "Content-Length": String(QUOTE_RESPONSE_LIMIT + 1) } }),
    () => new Response("x".repeat(QUOTE_RESPONSE_LIMIT + 1)), () => new Response("<html>blocked</html>"),
    () => json({ price: 0, time: ticker.time }), () => json({ price: 12, time: "2026-09-15" }), () => json({})];
  for (const response of responses) {
    const result = await createQuoteSnapshots({ env: {}, coinbaseSpacingMs: 0, fetcher: async () => response() }).load([btc]);
    assert.equal(result.updates[0]!.price, undefined);
    assert.equal(result.providers[0]!.status, "error");
  }
});

test("aborted loads skip all requests and Coinbase concurrency stays bounded", async () => {
  const controller = new AbortController(); controller.abort();
  let calls = 0;
  await createQuoteSnapshots({ env: credentials, coinbaseSpacingMs: 0, fetcher: async () => { calls++; return json({}); } }).load([us, cn, btc], controller.signal);
  assert.equal(calls, 0);
  let active = 0, maximum = 0;
  const coins: QuoteIdentity[] = ["BTC", "ETH", "SOL", "DOGE", "ADA"].map((coin) => ({ id: `crypto:${coin}/USD`, market: "crypto", symbol: `${coin}/USD` }));
  await createQuoteSnapshots({ env: {}, coinbaseSpacingMs: 0, fetcher: async (url) => {
    active++; maximum = Math.max(maximum, active);
    await new Promise((resolve) => setTimeout(resolve, 3)); active--;
    return json(url.pathname.endsWith("ticker") ? ticker : { open: "6000" });
  } }).load(coins);
  assert.ok(maximum <= 3);
});

test("canceling a large Coinbase load abandons queued requests without long future reservations", async () => {
  const controller = new AbortController();
  let calls = 0;
  const coins: QuoteIdentity[] = Array.from({ length: 100 }, (_, i) => ({ id: `crypto:C${i}/USD`, market: "crypto", symbol: `C${i}/USD` }));
  const source = createQuoteSnapshots({ env: {}, coinbaseSpacingMs: 2, timeoutMs: 100, fetcher: async (url) => {
    calls++;
    if (calls === 1) controller.abort();
    return json(url.pathname.endsWith("ticker") ? ticker : { open: "6000" });
  } });
  await source.load(coins, controller.signal);
  assert.equal(calls, 1);
  await source.load([btc]);
  assert.equal(calls, 3);
});
