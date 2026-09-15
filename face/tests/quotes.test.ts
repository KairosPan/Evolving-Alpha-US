import test from "node:test";
import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { createQuoteHub, parseQuoteRequest, registerQuoteRoutes, QUOTE_CLIENT_LIMIT } from "../src/quotes.ts";
import { isTrustedDataRequest } from "../src/data.ts";
import type { ProviderState, QuoteIdentity, QuotePayload, QuoteUpdate, SnapshotResult, StreamCallbacks } from "../src/quote-types.ts";

const US: QuoteIdentity = { id: "us:AAPL", market: "us", symbol: "AAPL" };
const BTC: QuoteIdentity = { id: "crypto:BTC/USD", market: "crypto", symbol: "BTC/USD" };
const CN: QuoteIdentity = { id: "cn:603986", market: "cn", symbol: "603986" };
const DAY = Date.parse("2026-09-15T15:00:00Z");
const usState: ProviderState = { id: "alpaca", market: "us", status: "connected", source: "Alpaca", feed: "iex", transport: "poll", message: "IEX 单交易所行情" };
const update = (extra: Partial<QuoteUpdate> = {}): QuoteUpdate => ({ id: US.id, source: "Alpaca", feed: "iex", basis: "previous_close",
  price: 100, prev_close: 80, volume: 1000, as_of: new Date(DAY).toISOString(), volume_as_of: "2026-09-15T04:00:00Z", market_status: "open", ...extra });
const empty = (): SnapshotResult => ({ updates: [], providers: [] });

test("quote requests accept only bounded canonical watchlist identities", () => {
  assert.deepEqual(parseQuoteRequest("/data/quotes?ids=us:AAPL,cn:603986,crypto:BTC%2FUSD,us:AAPL"), [US, CN, BTC]);
  assert.deepEqual(parseQuoteRequest("/data/quotes?ids="), []);
  for (const suffix of ["", "?ids=us:AAPL&ids=us:MSFT", "?ids=https://evil.example", "?ids=cn:603986:extra", "?ids=cn:123", "?ids=us:aapl", "?ids=us:AA%00", "?ids=%ZZ", "?ids=" + Array(101).fill("us:AAPL").join(",")]) {
    assert.throws(() => parseQuoteRequest(`/data/quotes${suffix}`), suffix);
  }
});

test("hub shares overlapping browser subscriptions and removes unused upstream identities", async () => {
  const subscriptions: string[][] = [];
  const requests: string[][] = [];
  const hub = createQuoteHub({ now: () => DAY, snapshots: { async load(assets) { requests.push(assets.map((a) => a.id)); return empty(); } },
    streams: () => ({ setAssets: (assets) => subscriptions.push(assets.map((a) => a.id)), close() {} }) });
  try {
    const received: QuotePayload[] = [];
    const a = hub.subscribe([US, BTC], (payload) => received.push(payload));
    const b = hub.subscribe([US, CN], () => {});
    await hub.snapshot([US, CN, BTC]);
    assert.deepEqual(subscriptions.at(-1), [US.id, BTC.id, CN.id]);
    assert.deepEqual(received[0]!.quotes.map((quote) => quote.id), [US.id, BTC.id]);
    assert.deepEqual(requests.flat().sort(), [US.id, BTC.id, CN.id].sort());
    a(); assert.deepEqual(subscriptions.at(-1), [US.id, CN.id]);
    b(); assert.deepEqual(subscriptions.at(-1), []);
    await hub.snapshot([]);
    assert.equal(requests.flat().length, 3);
  } finally { hub.close(); }
});

test("unconfigured markets carry messages and null values, while other markets keep real quotes", async () => {
  const hub = createQuoteHub({ now: () => DAY, snapshots: { async load() { return { updates: [update(),
    { id: CN.id, source: "iFinD", feed: "realtime", basis: "previous_close", message: "A 股行情待配置 iFinD" }], providers: [usState,
    { id: "ifind", market: "cn", status: "unconfigured", source: "iFinD", feed: "realtime", transport: "poll", message: "A 股行情待配置 iFinD" }] }; } },
    streams: () => ({ setAssets() {}, close() {} }) });
  try {
    const result = await hub.snapshot([US, CN]);
    assert.equal(result.quotes[0]!.change, 20);
    assert.equal(result.quotes[0]!.change_pct, 25);
    assert.equal(result.quotes[0]!.quote_status, "live");
    assert.equal(result.quotes[1]!.price, null);
    assert.equal(result.quotes[1]!.change_pct, null);
    assert.equal(result.quotes[1]!.quote_status, "unavailable");
    assert.match(result.quotes[1]!.message, /iFinD/);
  } finally { hub.close(); }
});

test("late REST results cannot overwrite a newer stream trade or same-day cumulative volume", async () => {
  let callbacks!: StreamCallbacks;
  let release!: (result: SnapshotResult) => void;
  const gate = new Promise<SnapshotResult>((resolve) => { release = resolve; });
  const hub = createQuoteHub({ now: () => DAY, snapshots: { load: () => gate }, streams: (handlers) => {
    callbacks = handlers; return { setAssets() {}, close() {} };
  } });
  try {
    const pending = hub.snapshot([US]);
    callbacks.onStatus({ ...usState, transport: "stream" });
    callbacks.onQuote(update({ price: 105, volume: 2000, as_of: "2026-09-15T15:00:00.123456789Z" }));
    release({ updates: [update({ price: 101, volume: 1500, as_of: "2026-09-15T15:00:00.123123123Z" })], providers: [usState] });
    const quote = (await pending).quotes[0]!;
    assert.equal(quote.price, 105);
    assert.equal(quote.volume, 2000);
    assert.equal(quote.as_of, "2026-09-15T15:00:00.123456789Z");
    callbacks.onQuote(update({ price: 106, volume: 2200, as_of: "2026-09-15T15:00:01Z" }));
    assert.equal((await hub.snapshot([US])).quotes[0]!.price, 106);
  } finally { hub.close(); }
});

test("a failed refresh keeps the last price and flags it stale; delayed SIP and old trades stay explicit", async () => {
  let clock = DAY;
  let failing = false;
  const hub = createQuoteHub({ now: () => clock, snapshots: { async load() {
    return failing ? { updates: [], providers: [{ ...usState, status: "error", message: "连接失败" }] }
      : { updates: [update()], providers: [usState] };
  } }, streams: () => ({ setAssets() {}, close() {} }) });
  try {
    await hub.snapshot([US]); failing = true; clock += 6000;
    const result = await hub.snapshot([US]);
    assert.equal(result.quotes[0]!.price, 100);
    assert.equal(result.quotes[0]!.quote_status, "stale");
    assert.equal(result.quotes[0]!.as_of, new Date(DAY).toISOString());
  } finally { hub.close(); }
  const delayed = createQuoteHub({ now: () => DAY, snapshots: { async load() { return {
    updates: [update({ feed: "delayed_sip", as_of: new Date(DAY - 15 * 60_000).toISOString() })],
    providers: [{ ...usState, feed: "delayed_sip" }],
  }; } }, streams: () => ({ setAssets() {}, close() {} }) });
  try { assert.equal((await delayed.snapshot([US])).quotes[0]!.quote_status, "delayed"); }
  finally { delayed.close(); }
});

test("snapshot cache coalesces concurrent reads and connection limits do not start extra streams", async () => {
  let calls = 0;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const hub = createQuoteHub({ now: () => DAY, snapshots: { async load() { calls++; await gate; return empty(); } },
    streams: () => ({ setAssets() {}, close() {} }) });
  try {
    const first = hub.snapshot([US]), second = hub.snapshot([US]);
    release(); await Promise.all([first, second]); assert.equal(calls, 1);
    const stops = Array.from({ length: QUOTE_CLIENT_LIMIT }, () => hub.subscribe([US], () => {}));
    assert.throws(() => hub.subscribe([US], () => {}), /连接过多/);
    stops.forEach((stop) => stop());
  } finally { hub.close(); }
});

class ResponseMock extends EventEmitter {
  status = 0;
  headers: Record<string, string> = {};
  chunks: string[] = [];
  destroyed = false;
  writableLength = 0;
  hardClosed = false;
  writeHead(status: number, headers: Record<string, string>) { this.status = status; this.headers = headers; }
  write(chunk: string) { this.chunks.push(chunk); return true; }
  end(chunk?: string) { if (chunk) this.chunks.push(chunk); if (!this.destroyed) { this.destroyed = true; this.emit("close"); } }
  destroy() { this.hardClosed = true; this.end(); return this; }
}
test("quote routes fence requests before reads, emit named SSE updates/heartbeats, and release on close", async (t) => {
  t.mock.timers.enable({ apis: ["setInterval"] });
  const routes: WebRoute[] = [];
  let calls = 0, stops = 0;
  const example: QuotePayload = { ok: true, generated_at: new Date(DAY).toISOString(), quotes: [], providers: [] };
  const dispose = registerQuoteRoutes({ register: (route) => routes.push(route) }, { isTrusted: isTrustedDataRequest,
    hub: { async snapshot() { calls++; return example; }, subscribe(_assets, listener) { calls++; listener(example); return () => { stops++; }; }, close() {} } });
  const invoke = async (stream: boolean, url: string, method = "GET", host = "localhost:3090") => {
    const res = new ResponseMock();
    await routes[stream ? 1 : 0]!.handler({ url, method, headers: { host } } as IncomingMessage, res as unknown as ServerResponse);
    return res;
  };
  assert.equal((await invoke(false, "/data/quotes?ids=us:AAPL", "GET", "evil.example")).status, 403);
  assert.equal((await invoke(false, "/data/quotes?ids=us:AAPL", "POST")).status, 405);
  assert.equal((await invoke(false, "/data/quotes?ids=us:*", "GET")).status, 400);
  assert.equal(calls, 0);
  const res = await invoke(true, "/data/quotes/stream?ids=us:AAPL");
  assert.equal(res.status, 200);
  assert.match(res.headers["content-type"]!, /text\/event-stream/);
  assert.match(res.chunks.join(""), /event: quotes/);
  t.mock.timers.tick(15_000);
  assert.match(res.chunks.join(""), /event: heartbeat/);
  res.end(); assert.equal(stops, 1);
  const size = res.chunks.length;
  t.mock.timers.tick(30_000); assert.equal(res.chunks.length, size);
  const slow = await invoke(true, "/data/quotes/stream?ids=us:AAPL");
  slow.writableLength = 300 * 1024;
  t.mock.timers.tick(15_000);
  assert.equal(slow.hardClosed, true);
  assert.equal(stops, 2);
  const open = await invoke(true, "/data/quotes/stream?ids=us:AAPL");
  dispose();
  assert.equal(open.destroyed, true);
  assert.equal(stops, 3);
});

test("concurrent distinct snapshots are pinned until delivered and excess work is rejected", async () => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const hub = createQuoteHub({ now: () => DAY, snapshots: { async load(assets) {
    await gate; return { updates: assets.map((asset) => update({ id: asset.id })), providers: [usState] };
  } }, streams: () => ({ setAssets() {}, close() {} }) });
  try {
    const promises = Array.from({ length: 7 }, (_, batch) => hub.snapshot(Array.from({ length: 100 }, (_, index) => ({
      id: `us:A${batch}B${index}`, market: "us" as const, symbol: `A${batch}B${index}`,
    }))));
    const resultPromise = Promise.allSettled(promises);
    release();
    const results = await resultPromise;
    assert.equal(results.filter((result) => result.status === "rejected").length, 2);
    for (const result of results) if (result.status === "fulfilled") assert.equal(result.value.quotes.filter((quote) => quote.price === 100).length, 100);
  } finally { hub.close(); }
});

test("a new trading day clears old volume and baseline until current-session data arrives", async () => {
  let clock = DAY;
  let callbacks!: StreamCallbacks;
  const hub = createQuoteHub({ now: () => clock, snapshots: { async load() { return { updates: [update()], providers: [usState] }; } },
    streams: (handlers) => { callbacks = handlers; return { setAssets() {}, close() {} }; } });
  try {
    await hub.snapshot([US]);
    clock += 86_400_000;
    callbacks.onQuote({ id: US.id, source: "Alpaca", feed: "iex", basis: "previous_close", price: 120, as_of: new Date(clock).toISOString() });
    // The next REST response is deliberately yesterday's snapshot; it cannot
    // repopulate yesterday's cumulative volume or price-change baseline.
    const quote = (await hub.snapshot([US])).quotes[0]!;
    assert.equal(quote.price, 120);
    assert.equal(quote.prev_close, null);
    assert.equal(quote.change_pct, null);
    assert.equal(quote.volume, null);
  } finally { hub.close(); }
});

test("an explicit missing current-session volume clears it without erasing the valid price", async () => {
  let callbacks!: StreamCallbacks;
  const hub = createQuoteHub({ now: () => DAY, snapshots: { async load() { return { updates: [update()], providers: [usState] }; } },
    streams: (handlers) => { callbacks = handlers; return { setAssets() {}, close() {} }; } });
  try {
    await hub.snapshot([US]);
    callbacks.onQuote(update({ price: 110, as_of: "2026-09-15T15:00:01Z", volume: null, volume_as_of: null }));
    const quote = (await hub.snapshot([US])).quotes[0]!;
    assert.equal(quote.volume, null);
    assert.equal(quote.price, 110);
  } finally { hub.close(); }
});

test("IEX marks only the first 30 active US symbols as streamed, keeping other quotes explicitly polled", async () => {
  let callbacks!: StreamCallbacks;
  const assets = Array.from({ length: 31 }, (_, i) => ({ id: `us:A${i}`, market: "us" as const, symbol: `A${i}` }));
  const hub = createQuoteHub({ now: () => DAY, snapshots: { async load(selected) { return {
    updates: selected.map((asset) => update({ id: asset.id })), providers: [usState],
  }; } }, streams: (handlers) => { callbacks = handlers; return { setAssets() {}, close() {} }; } });
  try {
    const stop = hub.subscribe(assets, () => {});
    callbacks.onStatus({ ...usState, status: "limited", transport: "stream" });
    const result = await hub.snapshot(assets);
    assert.equal(result.quotes.filter((quote) => quote.transport === "stream").length, 30);
    assert.equal(result.quotes.filter((quote) => quote.transport === "poll").length, 1);
    stop();
    assert.equal((await hub.snapshot(assets)).quotes.filter((quote) => quote.transport === "poll").length, 31);
  } finally { hub.close(); }
});
