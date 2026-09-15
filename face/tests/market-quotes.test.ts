import assert from "node:assert/strict";
import test from "node:test";
import { createLiveQuotes, describeQuote, quoteConnectionLabel, quoteSource, type QuoteState } from "../client/market-quotes.js";
import type { LiveQuote, ProviderState, QuotePayload } from "../src/quote-types.js";

const aapl = { id: "us:AAPL", market: "us", symbol: "AAPL" };
const btc = { id: "crypto:BTC/USD", market: "crypto", symbol: "BTC/USD" };
const cn = { id: "cn:603986", market: "cn", symbol: "603986" };
const received = "2026-09-15T15:00:00.000Z";
function quote(asset = aapl, extra: Partial<LiveQuote> = {}): LiveQuote {
  return { ...asset, market: asset.market as LiveQuote["market"], price: 120, prev_close: 100, change: 20, change_pct: 20,
    volume: 1000, as_of: "2026-09-15T14:59:58.123Z", received_at: received, volume_as_of: received,
    source: "Alpaca", feed: "iex", basis: "previous_close", quote_status: "live", market_status: "open", message: "", ...extra };
}
function provider(extra: Partial<ProviderState> = {}): ProviderState {
  return { id: "alpaca", market: "us", status: "connected", source: "Alpaca", feed: "iex", transport: "stream", message: "", ...extra };
}
function payload(quotes = [quote()], extra: Partial<QuotePayload> = {}): QuotePayload {
  return { ok: true, generated_at: received, quotes, providers: [provider()], ...extra };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
async function settle() { for (let count = 0; count < 16; count += 1) await Promise.resolve(); }

class Clock {
  now = 0;
  serial = 0;
  tasks = new Map<number, { at: number; callback: () => void }>();
  schedule = (callback: () => void, delay: number) => { const id = ++this.serial; this.tasks.set(id, { at: this.now + delay, callback }); return id; };
  cancel = (id: number) => { this.tasks.delete(id); };
  tick(ms: number) {
    const end = this.now + ms;
    for (;;) {
      const first = [...this.tasks].filter(([, task]) => task.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!first) break;
      this.tasks.delete(first[0]); this.now = first[1].at; first[1].callback();
    }
    this.now = end;
  }
}
class Stream {
  closed = false;
  listeners = new Map<string, ((event: { data?: string }) => void)[]>();
  constructor(readonly url: string) {}
  addEventListener(name: string, handler: (event: { data?: string }) => void) { this.listeners.set(name, [...(this.listeners.get(name) || []), handler]); }
  close() { this.closed = true; }
  // Late callbacks remain deliverable to verify revision guards after close().
  emit(name: string, data?: unknown) { for (const listener of this.listeners.get(name) || []) listener({ data: JSON.stringify(data) }); }
}
function harness(extra: Parameters<typeof createLiveQuotes>[1] = {}) {
  const clock = new Clock();
  const states: QuoteState[] = [];
  const streams: Stream[] = [];
  const calls: { url: string; signal: AbortSignal; result: ReturnType<typeof deferred<Response>> }[] = [];
  const client = createLiveQuotes((state) => states.push(state), {
    schedule: clock.schedule, cancelTimer: clock.cancel,
    createEventSource: (url) => { const stream = new Stream(url); streams.push(stream); return stream; },
    fetcher: async (url, init) => { const result = deferred<Response>(); calls.push({ url: String(url), signal: init!.signal!, result }); return result.promise; },
    ...extra,
  });
  return { client, clock, states, streams, calls, latest: () => states.at(-1)! };
}

test("empty watchlists do no network work; only unique selected IDs are subscribed, capped at 100", () => {
  const h = harness();
  h.client.setAssets([]); h.client.refresh(); h.client.setVisible(false); h.client.setVisible(true);
  assert.equal(h.streams.length, 0); assert.equal(h.calls.length, 0); assert.equal(h.clock.tasks.size, 0);
  h.client.setAssets([aapl, aapl, btc, { symbol: "invalid" }]);
  assert.equal(new URL(h.streams[0].url, "http://local").searchParams.get("ids"), "us:AAPL,crypto:BTC/USD");
  assert.equal(h.calls.length, 0, "the initial SSE snapshot needs no duplicate REST request");
  h.client.setAssets([btc, aapl]);
  assert.equal(h.streams.length, 1, "reordering identical subscriptions does not reconnect");
  h.client.setAssets(Array.from({ length: 101 }, (_, i) => ({ market: "us", symbol: `A${i}` })));
  assert.equal(h.streams[0].closed, true);
  assert.equal(new URL(h.streams[1].url, "http://local").searchParams.get("ids")!.split(",").length, 100);
  assert.equal(h.latest().limited, 1);
  h.client.close(); assert.equal(h.clock.tasks.size, 0);
});

test("full stream snapshots preserve event time, quote status, provider limits and percentage points", () => {
  const h = harness(); h.client.setAssets([aapl, btc, cn]);
  const missing = quote(cn, { price: null, prev_close: null, change: null, change_pct: null, volume: null, as_of: null,
    received_at: null, volume_as_of: null, source: "iFinD", feed: "", quote_status: "unavailable", market_status: "unknown", message: "行情待配置 iFinD" });
  h.streams[0].emit("quotes", payload([quote(aapl, { change_pct: 2.3, quote_status: "delayed" }), quote(btc, { source: "Coinbase", feed: "ticker", basis: "24h" }), missing], {
    providers: [provider({ status: "limited", message: "IEX single venue" }), provider({ id: "ifind", market: "cn", status: "unconfigured", source: "iFinD", feed: "", transport: "poll" })],
  }));
  assert.equal(h.latest().status, "streaming");
  assert.equal(h.latest().quotes[aapl.id].change_pct, 2.3);
  assert.equal(h.latest().quotes[aapl.id].as_of, "2026-09-15T14:59:58.123Z");
  assert.equal(h.latest().quotes[aapl.id].quote_status, "delayed");
  assert.equal(h.latest().quotes[btc.id].basis, "24h");
  assert.equal(h.latest().quotes[cn.id].price, null);
  assert.equal(h.latest().providers[1].status, "unconfigured");
  h.client.close();
});

test("selection changes reject late stream events and ignored-abort REST responses", async () => {
  const h = harness(); h.client.setAssets([aapl]);
  h.streams[0].emit("quotes", payload());
  h.client.refresh();
  assert.equal(h.calls.length, 1);
  h.client.setAssets([btc]);
  assert.equal(h.calls[0].signal.aborted, true); assert.equal(h.streams[0].closed, true);
  h.streams[1].emit("quotes", payload([quote(btc)]));
  const newest = h.latest();
  h.streams[0].emit("quotes", payload([quote(aapl, { price: 999 })]));
  h.streams[0].emit("error");
  h.calls[0].result.resolve(Response.json(payload([quote(aapl, { price: 888 })])));
  await settle();
  assert.equal(h.latest(), newest);
  assert.deepEqual(Object.keys(h.latest().quotes), [btc.id]);
  assert.equal(h.streams.length, 2); h.client.close();
});

test("disconnect keeps good prices stale, falls back immediately, then a stream update beats older REST JSON", async () => {
  const h = harness(); h.client.setAssets([aapl]); h.streams[0].emit("quotes", payload());
  h.streams[0].emit("error");
  assert.equal(h.streams[0].closed, true);
  assert.equal(h.latest().quotes[aapl.id].price, 120);
  assert.equal(h.latest().quotes[aapl.id].quote_status, "stale");
  assert.equal(h.latest().quotes[aapl.id].as_of, "2026-09-15T14:59:58.123Z");
  assert.equal(h.calls.length, 1);
  const json = deferred<QuotePayload>();
  h.calls[0].result.resolve({ ok: true, json: () => json.promise } as Response);
  await settle();
  h.clock.tick(1_000);
  h.streams[1].emit("quotes", payload([quote(aapl, { price: 123 })], { generated_at: "2026-09-15T15:00:01Z" }));
  assert.equal(h.calls[0].signal.aborted, true);
  json.resolve(payload([quote(aapl, { price: 99 })])); await settle();
  assert.equal(h.latest().quotes[aapl.id].price, 123);
  assert.equal(h.latest().status, "streaming");
  h.clock.tick(15_000);
  assert.equal(h.calls.length, 1, "successful stream cancels polling"); h.client.close();
});

test("REST fallback has a hard deadline even if fetch ignores abort, then polls at 15 seconds", async () => {
  const h = harness({ createEventSource: null }); h.client.setAssets([aapl]);
  h.clock.tick(10_000);
  assert.equal(h.calls[0].signal.aborted, true);
  assert.equal(h.latest().refreshing, false); assert.equal(h.latest().status, "error"); assert.match(h.latest().note, /超时/);
  const timedOut = h.latest(); h.calls[0].result.resolve(Response.json(payload())); await settle();
  assert.equal(h.latest(), timedOut);
  h.clock.tick(14_999); assert.equal(h.calls.length, 1);
  h.clock.tick(1); assert.equal(h.calls.length, 2);
  h.calls[1].result.resolve(Response.json(payload())); await settle();
  assert.equal(h.latest().status, "polling"); assert.equal(h.latest().quotes[aapl.id].price, 120);
  h.clock.tick(15_000); assert.equal(h.calls.length, 3); h.client.close();
});

test("stream retries are bounded, REST continues after exhaustion, and refresh explicitly retries streaming", async () => {
  const h = harness({ fetcher: async () => Response.json(payload()) }); h.client.setAssets([aapl]);
  for (const [index, delay] of [1_000, 3_000, 10_000].entries()) {
    h.streams[index].emit("error"); await settle(); h.clock.tick(delay);
  }
  assert.equal(h.streams.length, 4);
  h.streams[3].emit("error"); await settle();
  h.clock.tick(15_000); await settle();
  assert.equal(h.streams.length, 4); assert.equal(h.latest().status, "polling");
  h.client.refresh(); assert.equal(h.streams.length, 5); h.client.close();
});

test("heartbeat prolongs a healthy stream, missing heartbeat and missing initial snapshot trigger fallback", () => {
  const h = harness(); h.client.setAssets([aapl]); h.streams[0].emit("quotes", payload());
  h.clock.tick(30_000); h.streams[0].emit("heartbeat", { generated_at: received });
  h.clock.tick(34_999); assert.equal(h.calls.length, 0);
  h.clock.tick(1); assert.equal(h.calls.length, 1); assert.equal(h.streams[0].closed, true); h.client.close();
  const cold = harness(); cold.client.setAssets([aapl]);
  cold.clock.tick(10_000); assert.equal(cold.streams[0].closed, true); assert.equal(cold.calls.length, 1); cold.client.close();
});

test("hiding, emptying and closing cancel every timer and request; resuming reconnects only current IDs", async () => {
  const h = harness(); h.client.setAssets([aapl]); h.streams[0].emit("quotes", payload()); h.client.refresh();
  h.client.setVisible(false);
  assert.equal(h.streams[0].closed, true); assert.equal(h.calls[0].signal.aborted, true); assert.equal(h.clock.tasks.size, 0);
  assert.equal(h.latest().status, "paused"); assert.equal(h.latest().quotes[aapl.id].quote_status, "stale");
  h.client.setAssets([btc]); h.clock.tick(120_000); assert.equal(h.streams.length, 1);
  h.client.setVisible(true); assert.equal(h.streams.length, 2); assert.match(decodeURIComponent(h.streams[1].url), /crypto:BTC\/USD/);
  h.client.setAssets([]); assert.equal(h.clock.tasks.size, 0); assert.equal(h.streams[1].closed, true); assert.equal(h.latest().status, "idle");
  const empty = h.latest(); h.calls[0].result.resolve(Response.json(payload())); await settle(); assert.equal(h.latest(), empty);
  h.client.close(); h.client.setAssets([aapl]); h.client.refresh(); h.client.setVisible(true); assert.equal(h.streams.length, 2);
});

test("malformed snapshots and provider failures never clear good prices or invent successful updates", async () => {
  const h = harness({ createEventSource: null }); h.client.setAssets([aapl]); h.calls[0].result.resolve(Response.json(payload())); await settle();
  const good = h.latest().quotes[aapl.id];
  for (const invalid of [{ ok: true, quotes: [] }, payload([quote(aapl, { price: "bad" as unknown as number })]), payload([], { providers: [{} as ProviderState] })]) {
    h.client.refresh(); h.calls.at(-1)!.result.resolve(Response.json(invalid)); await settle();
    assert.equal(h.latest().status, "error"); assert.equal(h.latest().quotes[aapl.id].price, good.price); assert.equal(h.latest().quotes[aapl.id].quote_status, "stale");
  }
  h.client.refresh();
  h.calls.at(-1)!.result.resolve(Response.json(payload([quote(aapl, { price: null, quote_status: "unavailable", message: "provider unavailable" })])));
  await settle();
  assert.equal(h.latest().quotes[aapl.id].price, 120); assert.equal(h.latest().quotes[aapl.id].quote_status, "stale");
  assert.equal(h.latest().quotes[aapl.id].as_of, good.as_of); assert.equal(h.latest().quotes[aapl.id].message, "provider unavailable"); h.client.close();
});

test("a failed manual REST refresh does not relabel a still-healthy live stream as disconnected", async () => {
  const h = harness(); h.client.setAssets([aapl]); h.streams[0].emit("quotes", payload());
  h.client.refresh(); h.calls[0].result.reject(new Error("REST unavailable")); await settle();
  assert.equal(h.latest().status, "streaming"); assert.equal(h.latest().refreshing, false);
  assert.equal(h.latest().quotes[aapl.id].quote_status, "live"); assert.equal(h.streams[0].closed, false);
  h.client.close();
});

test("connected SSE never implies usable quotes when market providers are unconfigured or failing", () => {
  const ifind = provider({ id: "ifind", market: "cn", status: "unconfigured", source: "iFinD", feed: "realtime", transport: "poll" });
  assert.equal(quoteConnectionLabel("streaming", [ifind], ["cn"]), "A 股行情待配置 iFinD");
  assert.equal(quoteConnectionLabel("streaming", [ifind, provider({ status: "unconfigured" })], ["us", "cn"]), "行情源待配置");
  assert.equal(quoteConnectionLabel("streaming", [ifind, provider({ status: "error" })], ["us", "cn"]), "行情源暂不可用");
  assert.equal(quoteConnectionLabel("streaming", [ifind, provider()], ["us", "cn"]), "部分市场行情可用");
  assert.equal(quoteConnectionLabel("streaming", [provider({ transport: "poll" })], ["us"]), "行情定时更新");
  assert.equal(quoteConnectionLabel("polling", [provider()], ["us"]), "备用行情 · 每 15 秒更新");
  assert.equal(quoteConnectionLabel("paused", [provider()], ["us"]), "行情连接已暂停");
});

test("quote labels distinguish regular sessions, polling, feed coverage and volume units", () => {
  const closed = describeQuote(aapl, quote(aapl, { market_status: "closed" }), [provider()], "streaming");
  assert.equal(closed.status, "实时 · 常规交易休市");
  assert.equal(closed.source, "Alpaca · IEX 单一交易所");
  assert.equal(closed.volumeUnit, "股");
  assert.equal(describeQuote(aapl, quote(), [provider({ transport: "poll" })], "streaming").status, "定时更新");
  assert.equal(describeQuote(aapl, quote(), [provider()], "polling").status, "定时更新");
  assert.equal(describeQuote(aapl, quote(aapl, { quote_status: "stale" }), [provider()], "polling").status, "上次报价 · 待更新");
  assert.equal(describeQuote(btc, quote(btc), [], "streaming").volumeUnit, "24h · BTC");
  assert.equal(describeQuote(cn, {}, [], "streaming").status, "行情待配置 iFinD");
  assert.equal(describeQuote(cn, {}, [], "streaming").volumeUnit, "");
  assert.equal(quoteSource("Coinbase", "exchange"), "Coinbase · 现货");
  assert.equal(quoteSource("iFinD", "realtime"), "iFinD · 定时行情");
  assert.equal(quoteSource("Provider", "future_internal_enum"), "Provider");
});
