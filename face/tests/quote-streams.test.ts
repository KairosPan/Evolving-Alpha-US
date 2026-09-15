import test from "node:test";
import assert from "node:assert/strict";
import { createQuoteStreams, type QuoteSocket, type QuoteStreamOptions } from "../src/quote-streams.ts";
import type { ProviderState, QuoteIdentity, QuoteUpdate } from "../src/quote-types.ts";

const us = (symbol: string): QuoteIdentity => ({ id: `us:${symbol}`, market: "us", symbol });
const crypto = (symbol: string): QuoteIdentity => ({ id: `crypto:${symbol}/USD`, market: "crypto", symbol: `${symbol}/USD` });
const credentials = { APCA_API_KEY_ID: "test-key", APCA_API_SECRET_KEY: "test-secret" };
const T = "2026-09-15T14:30:00.123456789Z";

class FakeSocket extends EventTarget implements QuoteSocket {
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  closed = 0;
  handlers = new Map<string, EventListenerOrEventListenerObject>();
  override addEventListener(type: string, callback: EventListenerOrEventListenerObject | null, options?: AddEventListenerOptions | boolean) {
    if (callback) this.handlers.set(type, callback);
    super.addEventListener(type, callback, options);
  }
  override removeEventListener(type: string, callback: EventListenerOrEventListenerObject | null, options?: EventListenerOptions | boolean) {
    this.handlers.delete(type);
    super.removeEventListener(type, callback, options);
  }
  send(data: string | ArrayBufferLike | Blob | ArrayBufferView) {
    assert.equal(this.readyState, 1);
    assert.equal(typeof data, "string");
    this.sent.push(JSON.parse(data as string));
  }
  close() { this.closed++; this.readyState = 3; }
  open() { this.readyState = 1; this.dispatchEvent(new Event("open")); }
  message(value: unknown) { this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify(value) })); }
  raw(data: unknown) { this.dispatchEvent(new MessageEvent("message", { data })); }
  disconnect() { this.readyState = 3; this.dispatchEvent(new Event("close")); }
}
function harness(extra: QuoteStreamOptions = {}) {
  let tick = 0;
  let nextTimer = 0;
  const timers = new Map<number, { at: number; run: () => void }>();
  const sockets: FakeSocket[] = [];
  const urls: string[] = [];
  const quotes: QuoteUpdate[] = [];
  const statuses: ProviderState[] = [];
  const streams = createQuoteStreams({ onQuote: (quote) => quotes.push(quote), onStatus: (status) => statuses.push(status) }, {
    env: credentials,
    now: () => tick,
    socketFactory: (url) => { const socket = new FakeSocket(); sockets.push(socket); urls.push(url); return socket; },
    setTimeout: (run, delay) => { const id = ++nextTimer; timers.set(id, { at: tick + delay, run }); return id as unknown as ReturnType<typeof setTimeout>; },
    clearTimeout: (timer) => { timers.delete(timer as unknown as number); },
    ...extra,
  });
  function advance(milliseconds: number) {
    const end = tick + milliseconds;
    for (let limit = 0; limit < 10_000; limit++) {
      const next = [...timers].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0];
      if (!next) { tick = end; return; }
      tick = next[1].at; timers.delete(next[0]); next[1].run();
    }
    throw new Error("Timer loop");
  }
  return { streams, sockets, urls, quotes, statuses, advance, timers };
}
function alpacaAck(socket: FakeSocket, symbols: string[]) {
  socket.message([{ T: "subscription", trades: symbols, dailyBars: symbols }]);
}
function authenticate(socket: FakeSocket, symbols: string[]) {
  socket.open(); socket.message([{ T: "success", msg: "authenticated" }]); alpacaAck(socket, symbols);
}
function coinbaseAck(socket: FakeSocket, symbols: string[]) {
  socket.message({ type: "subscriptions", channels: [
    { name: "ticker", product_ids: symbols }, { name: "heartbeat", product_ids: symbols },
  ] });
}

test("streams are lazy and missing Alpaca credentials do not block public crypto", () => {
  const h = harness({ env: {} });
  assert.equal(h.sockets.length, 0);
  h.streams.setAssets([]);
  assert.equal(h.timers.size, 0);
  h.streams.setAssets([us("AAPL"), crypto("BTC"), { id: "cn:603986", market: "cn", symbol: "603986" }]);
  assert.equal(h.sockets.length, 1);
  assert.equal(h.urls[0], "wss://ws-feed.exchange.coinbase.com");
  assert.equal(h.statuses.find((status) => status.id === "alpaca")?.status, "unconfigured");
  assert.deepEqual(h.quotes, []);
  h.streams.close();
  assert.equal(h.timers.size, 0);
});

test("Alpaca authenticates before subscribing to the latest desired assets and waits for acknowledgement", () => {
  const h = harness();
  h.streams.setAssets([us("AAPL")]);
  const socket = h.sockets[0]!;
  assert.equal(h.urls[0], "wss://stream.data.alpaca.markets/v2/iex");
  assert.deepEqual(socket.sent, []);
  socket.open();
  assert.deepEqual(socket.sent, [{ action: "auth", key: "test-key", secret: "test-secret" }]);
  h.streams.setAssets([us("MSFT")]);
  socket.message([{ T: "success", msg: "connected" }]);
  assert.equal(socket.sent.length, 1);
  socket.message([{ T: "success", msg: "authenticated" }]);
  assert.deepEqual(socket.sent[1], { action: "subscribe", trades: ["MSFT"], dailyBars: ["MSFT"] });
  assert.equal(h.statuses.at(-1)?.status, "connecting");
  alpacaAck(socket, ["MSFT"]);
  assert.equal(h.statuses.at(-1)?.status, "connected");
  assert.doesNotMatch(JSON.stringify(h.statuses), /test-key|test-secret/);
  h.streams.close();
});

test("subscriptions remove old symbols before adding and release connections when the union is empty", () => {
  const h = harness();
  h.streams.setAssets([us("AAPL"), us("MSFT")]);
  const socket = h.sockets[0]!;
  authenticate(socket, ["AAPL", "MSFT"]);
  h.streams.setAssets([us("MSFT"), us("NVDA")]);
  assert.deepEqual(socket.sent.at(-1), { action: "unsubscribe", trades: ["AAPL"], dailyBars: ["AAPL"] });
  alpacaAck(socket, ["MSFT"]);
  assert.deepEqual(socket.sent.at(-1), { action: "subscribe", trades: ["NVDA"], dailyBars: ["NVDA"] });
  alpacaAck(socket, ["MSFT", "NVDA"]);
  const sends = socket.sent.length;
  h.streams.setAssets([us("NVDA"), us("MSFT")]);
  assert.equal(socket.sent.length, sends);
  h.streams.setAssets([]);
  assert.equal(socket.closed, 1);
  assert.equal(socket.handlers.size, 0);
  assert.equal(h.timers.size, 0);
  h.advance(300_000);
  assert.equal(h.sockets.length, 1);
  h.streams.close();
});

test("IEX picks a deterministic 30-symbol subset and discloses limited coverage", () => {
  const assets = Array.from({ length: 32 }, (_, i) => us(`S${String(i).padStart(2, "0")}`));
  const h = harness();
  h.streams.setAssets([...assets].reverse().concat(assets[0]!));
  const socket = h.sockets[0]!;
  socket.open(); socket.message([{ T: "success", msg: "authenticated" }]);
  const expected = assets.slice(0, 30).map((asset) => asset.symbol);
  assert.deepEqual(socket.sent.at(-1)?.trades, expected);
  alpacaAck(socket, expected);
  assert.equal(h.statuses.at(-1)?.status, "limited");
  assert.match(h.statuses.at(-1)!.message, /30/);
  h.streams.close();
});

test("feeds use a fixed allowlist and symbols cannot introduce wildcard subscriptions", () => {
  for (const feed of ["sip", "delayed_sip"]) {
    const h = harness({ env: { ...credentials, ALPHA_DATA_FEED: feed } });
    h.streams.setAssets([us("AAPL"), us("*"), us("AAPL,MSFT"), { ...us("MSFT"), id: "us:OTHER" }]);
    authenticate(h.sockets[0]!, ["AAPL"]);
    assert.equal(h.urls[0], `wss://stream.data.alpaca.markets/v2/${feed}`);
    assert.deepEqual(h.sockets[0]!.sent[1]?.trades, ["AAPL"]);
    assert.equal(h.statuses.at(-1)?.feed, feed);
    h.streams.close();
  }
  const h = harness({ env: { ...credentials, ALPHA_DATA_FEED: "https://example.com" } });
  h.streams.setAssets([us("AAPL")]);
  assert.equal(h.sockets.length, 0);
  assert.equal(h.statuses.at(-1)?.status, "error");
  h.streams.close();
});

test("stock events keep trade time and daily volume separate and reject late, invalid or excluded trades", () => {
  const h = harness(); h.streams.setAssets([us("AAPL")]);
  const socket = h.sockets[0]!; authenticate(socket, ["AAPL"]);
  const trade = { T: "t", S: "AAPL", p: 123.45, t: T, c: ["@"], z: "C" };
  socket.message([trade]);
  assert.deepEqual(h.quotes[0], { id: "us:AAPL", source: "Alpaca", feed: "iex", basis: "previous_close", price: 123.45, as_of: T, message: "" });
  socket.message([
    { ...trade, p: 100, t: "2026-09-15T14:30:00.123456788Z" },
    { ...trade, p: 0 }, { ...trade, p: null }, { ...trade, p: "" }, { ...trade, p: "NaN" },
    { ...trade, p: 999, c: ["@", "I"] }, { ...trade, p: 999, c: ["W"] },
    { ...trade, c: null }, { ...trade, S: "OTHER" }, { ...trade, t: "invalid" },
  ]);
  assert.equal(h.quotes.length, 1);
  socket.message([{ T: "d", S: "AAPL", c: 333, v: 20000, t: "2026-09-15T04:00:00Z" }]);
  assert.deepEqual(h.quotes[1], { id: "us:AAPL", source: "Alpaca", feed: "iex", basis: "previous_close", volume: 20000, volume_as_of: "2026-09-15T04:00:00Z" });
  socket.message([{ T: "d", S: "AAPL", v: 0, t: "2026-09-16T04:00:00Z" }]);
  assert.equal(h.quotes.at(-1)?.volume, 0);
  socket.message([{ T: "d", S: "AAPL", v: 999, t: "2026-09-15T04:00:00Z" }]);
  assert.equal(h.quotes.length, 3);
  for (const type of ["c", "x"]) socket.message([{ T: type, S: "AAPL", cp: 999, t: T }]);
  assert.equal(h.quotes.at(-1)?.price, undefined);
  assert.equal(h.quotes.at(-1)?.as_of, undefined);
  assert.match(h.quotes.at(-1)!.message!, /更正或撤销/);
  const count = h.quotes.length;
  socket.raw("{malformed"); socket.raw("x".repeat(600_000)); socket.raw(new Uint8Array([1, 2]));
  socket.message([null, 1, {}, { T: "unknown" }]);
  assert.equal(h.quotes.length, count);
  h.streams.close();
});

test("Coinbase isolates products, paces subscriptions and continues after one unsupported product", () => {
  const h = harness(); h.streams.setAssets([crypto("BTC"), crypto("AAA"), crypto("ETH")]);
  const socket = h.sockets[0]!; socket.open();
  assert.deepEqual(socket.sent, [{ type: "subscribe", product_ids: ["AAA-USD"], channels: ["ticker", "heartbeat"] }]);
  socket.message({ type: "error", message: "test-secret reflected upstream", reason: "Invalid product" });
  assert.equal(h.statuses.at(-1)?.status, "limited");
  assert.doesNotMatch(JSON.stringify(h.statuses), /test-secret/);
  h.advance(249); assert.equal(socket.sent.length, 1);
  h.advance(1); assert.deepEqual(socket.sent[1]?.product_ids, ["BTC-USD"]);
  coinbaseAck(socket, ["BTC-USD"]);
  h.advance(250); assert.deepEqual(socket.sent[2]?.product_ids, ["ETH-USD"]);
  coinbaseAck(socket, ["BTC-USD", "ETH-USD"]); h.advance(250);
  assert.equal(socket.sent.length, 3);
  assert.equal(h.statuses.at(-1)?.status, "limited");
  h.streams.setAssets([crypto("ETH")]);
  assert.deepEqual(socket.sent.at(-1), { type: "unsubscribe", product_ids: ["BTC-USD"], channels: ["ticker", "heartbeat"] });
  coinbaseAck(socket, ["ETH-USD"]); h.advance(250);
  assert.equal(h.statuses.at(-1)?.status, "connected");
  h.streams.close(); assert.equal(h.timers.size, 0);
});

test("Coinbase ticker uses provider time, 24-hour baseline and cumulative volume without invented zeroes", () => {
  const h = harness(); h.streams.setAssets([crypto("BTC")]);
  const socket = h.sockets[0]!; socket.open(); coinbaseAck(socket, ["BTC-USD"]);
  const ticker = { type: "ticker", product_id: "BTC-USD", sequence: 42, time: T,
    price: "60000.50", open_24h: "59000", volume_24h: "125.45" };
  socket.message(ticker);
  assert.deepEqual(h.quotes[0], { id: "crypto:BTC/USD", source: "Coinbase", feed: "exchange", basis: "24h",
    price: 60000.5, prev_close: 59000, volume: 125.45, as_of: T, volume_as_of: T, market_status: "open", message: "" });
  socket.message({ ...ticker, sequence: 41, price: "100" });
  socket.message({ ...ticker, sequence: 43, time: "2026-09-15T14:30:00.123456788Z", price: "100" });
  socket.message({ ...ticker, sequence: 43, price: "" });
  socket.message({ ...ticker, sequence: 43, time: null });
  socket.message({ ...ticker, product_id: "ETH-USD" });
  socket.message({ type: "heartbeat", product_id: "BTC-USD", time: "2026-09-15T14:31:00Z", sequence: 100 });
  assert.equal(h.quotes.length, 1);
  socket.message({ ...ticker, sequence: 43, open_24h: null, volume_24h: "" });
  assert.equal(h.quotes[1]?.prev_close, undefined);
  assert.equal(h.quotes[1]?.volume, undefined);
  assert.equal(h.quotes[1]?.as_of, T);
  h.streams.close();
});

test("reconnect uses new subscriptions and ignores captured callbacks from an old socket", () => {
  const h = harness(); h.streams.setAssets([us("AAPL")]);
  const old = h.sockets[0]!; authenticate(old, ["AAPL"]);
  const oldMessage = old.handlers.get("message") as EventListener;
  old.disconnect();
  assert.equal(old.handlers.size, 0);
  h.streams.setAssets([us("NVDA")]);
  h.advance(999); assert.equal(h.sockets.length, 1);
  h.advance(1); assert.equal(h.sockets.length, 2);
  oldMessage(new MessageEvent("message", { data: JSON.stringify([{ T: "t", S: "NVDA", p: 200, t: T, c: ["@"] }]) }));
  assert.equal(h.quotes.length, 0);
  const next = h.sockets[1]!; authenticate(next, ["NVDA"]);
  assert.deepEqual(next.sent[1]?.trades, ["NVDA"]);
  h.streams.close();
  oldMessage(new MessageEvent("message", { data: "[]" }));
  h.streams.setAssets([us("MSFT")]); h.advance(300_000);
  assert.equal(h.sockets.length, 2);
  assert.equal(h.timers.size, 0);
});

test("handshake timeout reconnects with capped exponential delay and close cancels every timer", () => {
  let calls = 0;
  const h = harness({ socketFactory: () => { calls++; throw new Error("test-secret network error"); } });
  h.streams.setAssets([us("AAPL")]);
  assert.equal(calls, 1);
  for (const delay of [1000, 2000, 4000, 8000, 16000, 30000, 30000]) {
    const before: number = calls;
    h.advance(delay - 1); assert.equal(calls, before);
    h.advance(1); assert.equal(calls, before + 1);
  }
  assert.doesNotMatch(JSON.stringify(h.statuses), /test-secret/);
  h.streams.close(); assert.equal(h.timers.size, 0);
  h.advance(300_000);
  assert.equal(calls, 8);

  const timeout = harness(); timeout.streams.setAssets([us("AAPL")]);
  timeout.advance(10_000);
  assert.equal(timeout.sockets[0]!.closed, 1);
  assert.match(timeout.statuses.at(-1)!.message, /超时/);
  timeout.advance(1000); assert.equal(timeout.sockets.length, 2);
  timeout.streams.setAssets([]); assert.equal(timeout.timers.size, 0);
});

test("Alpaca probes idle sessions without fabricating a tick; a missing probe ack reconnects", () => {
  const h = harness(); h.streams.setAssets([us("AAPL")]);
  const socket = h.sockets[0]!; authenticate(socket, ["AAPL"]);
  h.advance(60_000);
  assert.deepEqual(socket.sent.at(-1), { action: "subscribe", trades: ["AAPL"], dailyBars: ["AAPL"] });
  assert.equal(socket.sent.length, 3);
  assert.equal(h.quotes.length, 0);
  h.advance(10_000); assert.equal(socket.closed, 1);
  h.advance(1000); assert.equal(h.sockets.length, 2);
  h.streams.close(); assert.equal(h.timers.size, 0);
});

test("Coinbase heartbeats keep the socket healthy without altering quote freshness", () => {
  const h = harness(); h.streams.setAssets([crypto("BTC")]);
  const socket = h.sockets[0]!; socket.open(); coinbaseAck(socket, ["BTC-USD"]);
  h.advance(29_000); socket.message({ type: "heartbeat", product_id: "BTC-USD", time: T });
  h.advance(29_000); socket.message({ type: "heartbeat", product_id: "BTC-USD", time: T });
  h.advance(29_000); socket.message({ type: "heartbeat", product_id: "BTC-USD", time: T });
  assert.equal(socket.closed, 0); assert.equal(h.quotes.length, 0);
  h.advance(63_000); assert.equal(socket.closed, 1);
  h.advance(1000); assert.equal(h.sockets.length, 2);
  h.streams.close();
});

test("Alpaca permission errors stop retrying and subscription limit errors stay visibly limited", () => {
  for (const code of [402, 409]) {
    const h = harness(); h.streams.setAssets([us("AAPL")]);
    h.sockets[0]!.open();
    h.sockets[0]!.message([{ T: "error", code, msg: "test-secret" }]);
    h.streams.setAssets([us("NVDA")]); h.advance(300_000);
    assert.equal(h.sockets.length, 1); assert.equal(h.timers.size, 0);
    assert.equal(h.statuses.at(-1)?.status, "error");
    assert.doesNotMatch(JSON.stringify(h.statuses), /test-secret/);
    h.streams.close();
  }
  const h = harness(); h.streams.setAssets([us("AAPL")]);
  const socket = h.sockets[0]!; socket.open(); socket.message([{ T: "success", msg: "authenticated" }]);
  socket.message([{ T: "error", code: 405 }]);
  assert.equal(h.statuses.at(-1)?.status, "limited");
  h.advance(120_000); assert.equal(h.sockets.length, 1);
  h.streams.close(); assert.equal(h.timers.size, 0);
});
