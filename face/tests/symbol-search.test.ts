import test from "node:test";
import assert from "node:assert/strict";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { isTrustedDataRequest } from "../src/data.ts";
import { HttpError } from "../src/http.ts";
import {
  createSymbolSearch, parseSearchRequest, parseTencentSearch, parseYahooSearch, registerSymbolSearchRoutes,
  SEARCH_CACHE_LIMIT, SEARCH_FLIGHT_LIMIT, SEARCH_RESPONSE_LIMIT, SEARCH_TTL_MS, type SearchFetch,
} from "../src/symbol-search.ts";

const TENCENT = 'v_hint="sh~603986~\\u5146\\u6613\\u521b\\u65b0~zycx~GP-A";';
const YAHOO = JSON.stringify({ quotes: [
  { symbol: "NVDA", shortname: "NVIDIA Corporation", exchange: "NMS", exchDisp: "NASDAQ", quoteType: "EQUITY" },
  { symbol: "SPY", longname: "SPDR S&P 500 ETF Trust", exchange: "PCX", quoteType: "ETF" },
  { symbol: "BTC-USD", shortname: "Bitcoin USD", exchange: "CCC", quoteType: "CRYPTOCURRENCY" },
  { symbol: "BTC-EUR", shortname: "Bitcoin EUR", exchange: "CCC", quoteType: "CRYPTOCURRENCY" },
  { symbol: "NVDA.DE", shortname: "NVIDIA Frankfurt", exchange: "GER", quoteType: "EQUITY" },
  { symbol: "^GSPC", shortname: "S&P 500", exchange: "SNP", quoteType: "INDEX" },
  { symbol: "BAD^SYMBOL", shortname: "Unsupported", exchange: "NMS", quoteType: "EQUITY" },
  { symbol: "BAD.BASE-USD", shortname: "Unsupported crypto", exchange: "CCC", quoteType: "CRYPTOCURRENCY" },
] });

test("Tencent decodes Chinese suggestions, retains stable ids and excludes non-A listings", () => {
  const parsed = parseTencentSearch(TENCENT);
  assert.deepEqual(parsed.assets, [{ id: "cn:603986", market: "cn", symbol: "603986", name: "兆易创新",
    currency: "CNY", exchange: "SH", aliases: ["zycx"] }]);
  assert.equal(parsed.truncated, false);
  const mixed = 'v_hint="hk~03986~GigaDevice~zycx~GP^sh~900901~B share~b~GP-B^sh~603986~兆易创新~zycx~GP-A^sh~603986~兆易创新~zycx~GP-A^bj~920185~贝特瑞~btr~GP-A";';
  assert.deepEqual(parseTencentSearch(mixed).assets.map((asset) => asset.id), ["cn:603986", "cn:920185"]);
  assert.deepEqual(parseTencentSearch('v_hint="";').assets, []);
  assert.deepEqual(parseTencentSearch('v_hint="N";').assets, []);
  assert.throws(() => parseTencentSearch('v_hint="unexpected shape";'));
  assert.throws(() => parseTencentSearch('v_hint=""; globalThis.compromised=true;'));
  assert.throws(() => parseTencentSearch("<html>temporarily unavailable</html>"));
});

test("Yahoo filters by listing market/type and normalizes only USD crypto pair ids", () => {
  assert.deepEqual(parseYahooSearch(YAHOO, "us").assets.map((asset) => asset.id), ["us:NVDA", "us:SPY"]);
  const crypto = parseYahooSearch(YAHOO, "crypto").assets;
  assert.equal(crypto.length, 1);
  assert.equal(crypto[0]?.id, "crypto:BTC/USD");
  assert.equal(crypto[0]?.currency, "USD");
  assert.deepEqual(parseYahooSearch(YAHOO, "all").assets.map((asset) => asset.market), ["us", "us", "crypto"]);
  assert.throws(() => parseYahooSearch('{"finance":{"error":"rate limit"}}', "all"));
});

test("suggestion limits are disclosed even when excluded markets reduce visible results", () => {
  const rows = Array.from({ length: 10 }, (_, index) => `hk~${index}~HK~hk~GP`).join("^");
  assert.equal(parseTencentSearch(`v_hint=${JSON.stringify(rows)};`).truncated, true);
  assert.equal(parseYahooSearch(JSON.stringify({ quotes: Array(20).fill({ symbol: "^INDEX" }) }), "us").truncated, true);
});

test("request validation bounds query size and rejects invalid/ambiguous inputs", () => {
  assert.deepEqual(parseSearchRequest("/data/symbols/search?q=%20%EF%BC%A1%EF%BC%A1%EF%BC%B0%EF%BC%AC%20&market=us"), { query: "AAPL", market: "us" });
  assert.deepEqual(parseSearchRequest("/data/symbols/search?q=兆易创新"), { query: "兆易创新", market: "all" });
  for (const suffix of ["", "?q=", "?q=%20", "?q=a&q=b", "?q=a&market=cn&market=us", "?q=a&market=hk", "?q=%ZZ", "?q=%FF", "?q=a%00b", `?q=${"x".repeat(81)}`, `?q=${"x".repeat(2049)}`]) {
    assert.throws(() => parseSearchRequest(`/data/symbols/search${suffix}`), (error: unknown) => error instanceof HttpError && error.status === 400, suffix);
  }
});

test("query requests use fixed HTTPS hosts and encoded parameters without directory downloads", async () => {
  const seen: { url: URL; options: RequestInit }[] = [];
  const search = createSymbolSearch({ fetch: async (url, options) => {
    seen.push({ url, options });
    return new Response(url.hostname === "smartbox.gtimg.cn" ? TENCENT : YAHOO);
  } });
  const query = "https://evil.example/a?q=x&secret=yes";
  const result = await search(query, "all");
  assert.equal(result.ok, true);
  assert.deepEqual(seen.map(({ url }) => url.origin), ["https://smartbox.gtimg.cn", "https://query1.finance.yahoo.com"]);
  for (const request of seen) {
    assert.equal(request.url.searchParams.get("q"), query);
    assert.equal(request.options.redirect, "error");
    assert.ok(request.options.signal instanceof AbortSignal);
  }
  assert.equal(result.assets.length, 4);
  assert.equal(result.assets.some((asset) => "price" in asset), false);
  assert.deepEqual(result.providers, [{ id: "tencent", status: "ok" }, { id: "yahoo", status: "ok" }]);
});

test("per-query cache shares concurrent misses, distinguishes market, expires and evicts", async () => {
  let calls = 0;
  let clock = 0;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const search = createSymbolSearch({ now: () => clock, fetch: async () => {
    calls++;
    await gate;
    return new Response(TENCENT);
  } });
  const first = search("兆易创新", "cn");
  const second = search("兆易创新", "cn");
  assert.equal(calls, 1);
  release();
  assert.deepEqual(await first, await second);
  await search("兆易创新", "cn");
  assert.equal(calls, 1);
  clock = SEARCH_TTL_MS;
  await search("兆易创新", "cn");
  assert.equal(calls, 2);
  for (let index = 0; index < SEARCH_CACHE_LIMIT; index++) await search(`other${index}`, "cn");
  const before = calls;
  await search("兆易创新", "cn");
  assert.equal(calls, before + 1);
});

test("market selection reaches only necessary providers and uses separate cache entries", async () => {
  const seen: string[] = [];
  const search = createSymbolSearch({ fetch: async (url) => {
    seen.push(url.hostname);
    return new Response(url.hostname === "smartbox.gtimg.cn" ? TENCENT : YAHOO);
  } });
  const cn = await search("same", "cn");
  const us = await search("same", "us");
  const crypto = await search("same", "crypto");
  assert.deepEqual(seen, ["smartbox.gtimg.cn", "query1.finance.yahoo.com", "query1.finance.yahoo.com"]);
  assert.deepEqual(cn.assets.map((asset) => asset.market), ["cn"]);
  assert.ok(us.assets.every((asset) => asset.market === "us"));
  assert.ok(crypto.assets.every((asset) => asset.market === "crypto"));
});

test("crypto pair searches use Yahoo's dash spelling while returning watchlist slash ids", async () => {
  let query = "";
  const search = createSymbolSearch({ fetch: async (url) => {
    query = url.searchParams.get("q")!;
    return new Response(YAHOO);
  } });
  const result = await search("btc/usd", "crypto");
  assert.equal(query, "BTC-USD");
  assert.equal(result.assets[0]?.symbol, "BTC/USD");
});

test("partial outages retain available results, label failures and retry without cached errors", async () => {
  let calls = 0;
  let fail = true;
  const search = createSymbolSearch({ fetch: async (url) => {
    calls++;
    if (url.hostname.includes("yahoo") && fail) throw new Error("upstream secret diagnostic");
    return new Response(url.hostname === "smartbox.gtimg.cn" ? TENCENT : YAHOO);
  } });
  const partial = await search("GigaDevice", "all");
  assert.equal(partial.ok, true);
  assert.equal(partial.partial, true);
  assert.equal(partial.assets[0]?.id, "cn:603986");
  assert.equal(partial.providers[1]?.status, "error");
  assert.ok(!JSON.stringify(partial).includes("secret"));
  fail = false;
  assert.equal((await search("GigaDevice", "all")).partial, false);
  assert.equal(calls, 4);
});

test("upstream oversized content and malformed payloads are failures, never empty successes", async () => {
  for (const response of [
    () => new Response("x".repeat(SEARCH_RESPONSE_LIMIT + 1)),
    () => new Response("x", { headers: { "content-length": String(SEARCH_RESPONSE_LIMIT + 1) } }),
    () => new Response("<html>blocked</html>"),
    () => new Response("{}", { status: 429 }),
  ]) {
    const result = await createSymbolSearch({ fetch: async () => response() })("603986", "cn");
    assert.equal(result.ok, false);
    assert.equal(result.providers[0]?.status, "error");
    assert.equal(result.partial, false);
  }
  const empty = await createSymbolSearch({ fetch: async () => new Response('v_hint="";') })("no-match", "cn");
  assert.equal(empty.ok, true);
  assert.deepEqual(empty.assets, []);
});

test("outstanding unique queries are bounded while identical requests may join an existing flight", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const search = createSymbolSearch({ fetch: async () => { await gate; return new Response(TENCENT); } });
  const running = Array.from({ length: SEARCH_FLIGHT_LIMIT }, (_, index) => search(`q${index}`, "cn"));
  const shared = search("q0", "cn");
  await assert.rejects(search("overflow", "cn"), (error: unknown) => error instanceof HttpError && error.status === 429);
  release();
  await Promise.all([...running, shared]);
  assert.equal((await search("overflow", "cn")).ok, true);
});

test("deadline covers both a hanging fetch and a hanging response body", async () => {
  for (const fetch of [
    async () => new Promise<Response>(() => undefined),
    async () => new Response(new ReadableStream<Uint8Array>({ start() { /* deliberately never finishes */ } })),
  ]) {
    const search = createSymbolSearch({ fetch, timeoutMs: 5 });
    const result = await search("603986", "cn");
    assert.equal(result.ok, false);
    assert.equal(result.providers[0]?.status, "error");
  }
});

function routeWith(fetch: SearchFetch): WebRoute {
  const routes: WebRoute[] = [];
  registerSymbolSearchRoutes({ register: (route) => routes.push(route) }, { fetch, isTrusted: isTrustedDataRequest });
  assert.equal(routes.length, 1);
  assert.equal(routes[0]?.path, "/data/symbols/search");
  return routes[0]!;
}
async function call(route: WebRoute, overrides: Partial<IncomingMessage> = {}): Promise<{ status: number; body: string }> {
  const out = { status: 0, body: "" };
  const res = { writeHead(status: number) { out.status = status; }, end(body: string) { out.body = body; } } as unknown as ServerResponse;
  const req = { method: "GET", url: "/data/symbols/search?q=603986&market=cn", headers: { host: "127.0.0.1:3090" }, ...overrides } as IncomingMessage;
  await route.handler(req, res);
  return out;
}

test("search route enforces loopback/browser fence, GET and query bounds before any network call", async () => {
  let calls = 0;
  const route = routeWith(async () => { calls++; return new Response(TENCENT); });
  for (const headers of [{}, { host: "evil.example" }, { host: "localhost:3090", origin: "https://evil.example" }, { host: "localhost:3090", "sec-fetch-site": "cross-site" }]) {
    assert.equal((await call(route, { headers })).status, 403);
  }
  assert.equal((await call(route, { method: "POST" })).status, 405);
  assert.equal((await call(route, { url: "/data/symbols/search?q=" })).status, 400);
  assert.equal(calls, 0);
  const success = await call(route);
  assert.equal(success.status, 200);
  assert.equal(JSON.parse(success.body).assets[0].name, "兆易创新");
  assert.equal(calls, 1);
});

test("route returns 503 for provider failure and 200 for a true no-match", async () => {
  let calls = 0;
  const unavailable = routeWith(async () => { calls++; throw new Error("private provider detail"); });
  const failed = await call(unavailable);
  assert.equal(failed.status, 503);
  assert.equal(JSON.parse(failed.body).ok, false);
  assert.ok(!failed.body.includes("private"));
  await call(unavailable);
  assert.equal(calls, 2);
  const empty = await call(routeWith(async () => new Response('v_hint="";')));
  assert.equal(empty.status, 200);
  assert.deepEqual(JSON.parse(empty.body).assets, []);
});
