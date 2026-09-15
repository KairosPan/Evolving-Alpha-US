import assert from "node:assert/strict";
import test from "node:test";
import {
  STORAGE_KEY, filterWatchlist, normalizeAsset, number, percent, price, quoteTime,
  readWatchlist, saveWatchlist, signed, sortWatchlist,
} from "../client/market-model.js";

const us = normalizeAsset({ market: "us", symbol: "BTC", name: "Bitcoin ETF", exchange: "NYSE" })!;
const cn = normalizeAsset({ market: "cn", symbol: "000001", name: "平安银行", aliases: ["Ping An Bank"] })!;
const crypto = normalizeAsset({ market: "crypto", symbol: "BTC/USD", name: "比特币", aliases: ["Bitcoin"] })!;

function memory(initial: string | null = null) {
  let value = initial;
  let writes = 0;
  return {
    get value() { return value; },
    get writes() { return writes; },
    getItem(key: string) { assert.equal(key, STORAGE_KEY); return value; },
    setItem(key: string, next: string) { assert.equal(key, STORAGE_KEY); value = next; writes += 1; },
  };
}

test("assets retain market-qualified identities and A-share leading zeroes", () => {
  assert.equal(us.id, "us:BTC");
  assert.equal(crypto.id, "crypto:BTC/USD");
  assert.equal(cn.id, "cn:000001");
  assert.equal(cn.currency, "CNY");
  assert.deepEqual(normalizeAsset({ market: "US", symbol: " aapl ", name: " Apple ", aliases: [" 苹果 ", "苹果", 7, ""] }), {
    id: "us:AAPL", market: "us", symbol: "AAPL", name: "Apple", exchange: "", currency: "USD", aliases: ["苹果"],
  });
  assert.equal(normalizeAsset({ id: "us:BRK.B" })?.symbol, "BRK.B");
  assert.equal(normalizeAsset({ market: "cn", symbol: "sz000001" })?.id, cn.id);
  assert.equal(normalizeAsset({ market: "cn", symbol: "600519.SH" })?.id, "cn:600519");
  assert.equal(normalizeAsset({ market: "crypto", symbol: "btc-usd" })?.id, crypto.id);
  for (const input of [null, [], "AAPL", { symbol: "AAPL" }, { market: "other", symbol: "AAPL" },
    { market: "cn", symbol: 1 }, { market: "cn", symbol: "1" }, { market: "crypto", symbol: "BTCUSD" },
    { market: "us", symbol: "A APL" }, { id: "us:BTC", market: "crypto", symbol: "BTC/USD" },
    { id: "us:AAPL", market: "us", symbol: "MSFT" }]) {
    assert.equal(normalizeAsset(input), null);
  }
});

test("a new watchlist starts empty and persists a versioned mixed-market list", () => {
  const storage = memory();
  assert.deepEqual(readWatchlist(storage), { items: [], error: null });
  assert.equal(storage.writes, 0);
  assert.equal(saveWatchlist(storage, [us, cn, crypto, us]), null);
  assert.deepEqual(JSON.parse(storage.value!), { version: 1, items: [us, cn, crypto] });
  assert.deepEqual(readWatchlist(storage), { items: [us, cn, crypto], error: null });
  assert.equal(saveWatchlist(storage, []), null);
  assert.deepEqual(readWatchlist(storage), { items: [], error: null });
});

test("malformed storage is reported without rewriting original data; usable entries survive", () => {
  for (const raw of ["", "invalid JSON", "null", "[]", '{"version":2,"items":[]}', '{"version":1,"items":{}}']) {
    const storage = memory(raw);
    const loaded = readWatchlist(storage);
    assert.deepEqual(loaded.items, []);
    assert.ok(loaded.error);
    assert.equal(storage.value, raw);
    assert.equal(storage.writes, 0);
  }
  const raw = JSON.stringify({ version: 1, items: [us, null, cn, { market: "cn", symbol: "bad" }, crypto, us] });
  const storage = memory(raw);
  const loaded = readWatchlist(storage);
  assert.deepEqual(loaded.items, [us, cn, crypto]);
  assert.match(loaded.error!, /2 项/);
  assert.equal(storage.value, raw);
  assert.equal(storage.writes, 0);
});

test("unavailable storage and failed or invalid saves do not claim success", () => {
  assert.ok(readWatchlist(null).error);
  assert.ok(readWatchlist({ getItem() { throw new Error("denied"); } }).error);
  assert.ok(saveWatchlist(null, [us]));
  assert.ok(saveWatchlist({ setItem() { throw new Error("quota"); } }, [us]));
  const storage = memory("original data");
  for (const value of [null, {}, [us, {}], [us, { market: "us", symbol: "" }]]) {
    assert.ok(saveWatchlist(storage, value));
    assert.equal(storage.value, "original data");
    assert.equal(storage.writes, 0);
  }
});

test("search combines market filters, native names, codes, aliases and multiple terms", () => {
  const items = [us, cn, crypto];
  assert.deepEqual(filterWatchlist(items), items);
  assert.deepEqual(filterWatchlist(items, "cn", "平安"), [cn]);
  assert.deepEqual(filterWatchlist(items, "all", "000001"), [cn]);
  assert.deepEqual(filterWatchlist(items, "all", "ping an"), [cn]);
  assert.deepEqual(filterWatchlist(items, "all", "bitcoin"), [us, crypto]);
  assert.deepEqual(filterWatchlist(items, "crypto", " btc "), [crypto]);
  assert.deepEqual(filterWatchlist(items, "all", "BTC NYSE"), [us]);
  assert.deepEqual(filterWatchlist(items, "cn", "bitcoin"), []);
});

test("numeric sorting keeps missing quotes last, handles zero, and does not mutate user order", () => {
  const items = [crypto, cn, us];
  const quotes = { [us.id]: { price: "12", change_pct: "-0.5" }, [crypto.id]: { price: 0, change_pct: 2.3 }, [cn.id]: { price: "", change_pct: null } };
  assert.deepEqual(sortWatchlist(items, quotes, { key: "price", direction: "asc" }), [crypto, us, cn]);
  assert.deepEqual(sortWatchlist(items, quotes, { key: "price", direction: "desc" }), [us, crypto, cn]);
  assert.deepEqual(sortWatchlist(items, quotes, { key: "change_pct", direction: "desc" }), [crypto, us, cn]);
  assert.deepEqual(sortWatchlist(items, quotes, { key: "change_pct", direction: "asc" }), [us, crypto, cn]);
  assert.deepEqual(sortWatchlist(items, quotes, { key: "symbol", direction: "asc" }), [cn, us, crypto]);
  assert.deepEqual(sortWatchlist(items, quotes, { key: "default", direction: "desc" }), [crypto, cn, us]);
  assert.deepEqual(items, [crypto, cn, us]);
  assert.notEqual(sortWatchlist(items, quotes), items);
  assert.deepEqual(sortWatchlist(items, {}, { key: "price", direction: "desc" }), items);
});

test("financial formatters reject coercions and preserve percentage-point and small-token precision", () => {
  for (const value of [undefined, null, "", " ", true, false, [], [2], {}, NaN, Infinity, "Infinity", "NaN", "0x10", "1,200", "2USD", "--1"]) {
    assert.equal(number(value), null);
    assert.equal(price(value), "—");
    assert.equal(signed(value), "—");
    assert.equal(percent(value), "—");
  }
  assert.equal(number(" -1.25e2 "), -125);
  assert.equal(number(".5"), 0.5);
  assert.equal(number(-0), 0);
  assert.equal(price(1234.5), "$1,234.50");
  assert.equal(price(1234.5, "cny"), "¥1,234.50");
  assert.equal(price(-1.2, "EUR"), "-EUR 1.20");
  assert.equal(price(0.00001234), "$0.00001234");
  assert.equal(price(1e-10), "$1e-10");
  assert.equal(price(0), "$0.00");
  assert.equal(percent(2.3), "+2.30%");
  assert.equal(percent(-0.5), "-0.50%");
  assert.equal(percent(-0), "0.00%");
  assert.equal(signed(12.5), "+12.50");
});

test("quote timestamps distinguish instants, dates and unspecified timezone without invented times", () => {
  for (const value of [null, "", "bad", "1700000000", "2026-99-99", "2026-02-30"]) assert.equal(quoteTime(value), "—");
  assert.equal(quoteTime("2026-07-09"), "2026/07/09");
  assert.equal(quoteTime("2026-09-15T10:30:00"), "2026-09-15 10:30:00（时区未注明）");
  const local = quoteTime("2026-09-15T14:30:00Z");
  assert.match(local, /2026/);
  assert.match(local, /GMT/);
  assert.match(local, /（本地）$/);
  assert.equal(quoteTime("2026-09-15T10:30:00-04:00"), local);
});
