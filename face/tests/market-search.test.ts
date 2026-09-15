import assert from "node:assert/strict";
import test from "node:test";
import { createSymbolSearch, type SearchState } from "../client/market-search.js";

const cn = { market: "cn", symbol: "603986", name: "兆易创新", exchange: "SSE" };
const us = { market: "us", symbol: "AAPL", name: "Apple" };

function result(assets: unknown[] = [cn], extra: Record<string, unknown> = {}) {
  return Response.json({ ok: true, assets, providers: [{ id: "test", status: "ok" }], partial: false, truncated: false, note: "", ...extra });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

// Flush both fetch and JSON parsing promise continuations without advancing timers.
async function settle() {
  for (let step = 0; step < 12; step += 1) await Promise.resolve();
}

test("rapid typing publishes loading immediately and sends only the debounced query", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: SearchState[] = [];
  const urls: string[] = [];
  const search = createSymbolSearch((state) => states.push(state), {
    fetcher: async (url) => { urls.push(String(url)); return result(); },
  });
  search.search("兆", "cn");
  assert.equal(states.at(-1)?.status, "loading");
  t.mock.timers.tick(200);
  search.search("兆易创新", "cn");
  t.mock.timers.tick(249);
  assert.deepEqual(urls, []);
  t.mock.timers.tick(1);
  await settle();
  assert.deepEqual(urls, ["/data/symbols/search?q=%E5%85%86%E6%98%93%E5%88%9B%E6%96%B0&market=cn"]);
  assert.equal(states.at(-1)?.status, "success");
  assert.equal(states.at(-1)?.assets[0].id, "cn:603986");
  assert.equal(states.at(-1)?.assets[0].currency, "CNY");
});

test("market changes abort previous requests and out-of-order responses cannot overwrite the latest result", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: SearchState[] = [];
  const calls: { url: string; signal: AbortSignal; response: ReturnType<typeof deferred<Response>> }[] = [];
  const search = createSymbolSearch((state) => states.push(state), {
    delayMs: 0,
    fetcher: async (url, init) => {
      const response = deferred<Response>();
      calls.push({ url: String(url), signal: init!.signal!, response });
      return response.promise; // Deliberately ignores abort.
    },
  });
  search.search("apple");
  t.mock.timers.tick(0);
  search.search("apple", "us");
  assert.equal(calls[0].signal.aborted, true);
  assert.equal(states.at(-1)?.market, "us");
  assert.deepEqual(states.at(-1)?.assets, []);
  t.mock.timers.tick(0);
  calls[1].response.resolve(result([us]));
  await settle();
  const latest = states.at(-1);
  calls[0].response.resolve(result([cn]));
  await settle();
  assert.equal(states.at(-1), latest);
  assert.equal(latest?.assets[0].id, "us:AAPL");
  assert.equal(calls[1].url, "/data/symbols/search?q=apple&market=us");
});

test("blank search cancels pending debounce and active requests without querying the catalog", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: SearchState[] = [];
  let calls = 0;
  const response = deferred<Response>();
  const search = createSymbolSearch((state) => states.push(state), {
    fetcher: async () => { calls += 1; return response.promise; },
  });
  search.search("603986", "cn");
  search.search("   ", "cn");
  t.mock.timers.tick(300);
  assert.equal(calls, 0);
  assert.deepEqual(states.at(-1), { query: "", market: "cn", status: "idle", assets: [], partial: false, truncated: false, note: "" });
  search.search("603986", "cn");
  t.mock.timers.tick(250);
  search.search("", "crypto");
  response.resolve(result());
  await settle();
  assert.equal(calls, 1);
  assert.equal(states.at(-1)?.status, "idle");
  assert.equal(states.at(-1)?.market, "crypto");
});

test("closing search cancels both debounce and active work, including stale errors", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: SearchState[] = [];
  let calls = 0;
  let signal: AbortSignal | undefined;
  const response = deferred<Response>();
  const search = createSymbolSearch((state) => states.push(state), {
    fetcher: async (_url, init) => { calls += 1; signal = init!.signal!; return response.promise; },
  });
  search.search("603986", "cn");
  search.cancel();
  t.mock.timers.tick(500);
  assert.equal(calls, 0);
  search.search("603986", "cn");
  t.mock.timers.tick(250);
  search.cancel();
  assert.equal(signal?.aborted, true);
  const count = states.length;
  response.reject(new Error("late provider failure"));
  await settle();
  t.mock.timers.tick(10_000);
  assert.equal(states.length, count);
  assert.equal(states.at(-1)?.status, "idle");
});

test("service, network and malformed responses show an error instead of an empty result", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const failures = [
    () => new Response("unavailable", { status: 503 }),
    () => { throw new Error("network lost"); },
    () => new Response("<html>Proxy error</html>"),
    () => Response.json({ ok: true, assets: [] }),
    () => result([cn, { market: "cn", symbol: "invalid" }]),
    () => result([], { ok: false }),
    () => result([], { providers: [{}] }),
    () => result([], { partial: "yes" }),
  ];
  for (const failure of failures) {
    const states: SearchState[] = [];
    const search = createSymbolSearch((state) => states.push(state), { delayMs: 0, fetcher: async () => failure() });
    search.search("兆易创新", "cn");
    t.mock.timers.tick(0);
    await settle();
    assert.equal(states.at(-1)?.status, "error");
    assert.ok(states.at(-1)?.note);
    assert.deepEqual(states.at(-1)?.assets, []);
    search.cancel();
  }
});

test("verified empty and partial results remain successful with their coverage notes", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: SearchState[] = [];
  const search = createSymbolSearch((state) => states.push(state), {
    delayMs: 0,
    fetcher: async () => result([], { partial: true, truncated: true, note: "部分市场暂不可用" }),
  });
  search.search("nothing");
  t.mock.timers.tick(0);
  await settle();
  assert.deepEqual(states.at(-1), {
    query: "nothing", market: "all", status: "success", assets: [], partial: true, truncated: true, note: "部分市场暂不可用",
  });
});

test("a response without an optional note still explains partial provider coverage", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: SearchState[] = [];
  const search = createSymbolSearch((state) => states.push(state), {
    delayMs: 0,
    fetcher: async () => Response.json({ ok: true, assets: [cn], providers: [{ id: "test", status: "ok" }], partial: true, truncated: false }),
  });
  search.search("兆易创新");
  t.mock.timers.tick(0);
  await settle();
  assert.equal(states.at(-1)?.status, "success");
  assert.match(states.at(-1)!.note, /部分市场/);
});

test("hard timeout ends loading even when a provider ignores abort and resolves late", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const states: SearchState[] = [];
  const response = deferred<Response>();
  let signal: AbortSignal | undefined;
  const search = createSymbolSearch((state) => states.push(state), {
    delayMs: 0,
    fetcher: async (_url, init) => { signal = init!.signal!; return response.promise; },
  });
  search.search("603986", "cn");
  t.mock.timers.tick(0);
  t.mock.timers.tick(10_000);
  assert.equal(signal?.aborted, true);
  assert.equal(states.at(-1)?.status, "error");
  assert.match(states.at(-1)!.note, /超时/);
  const count = states.length;
  response.resolve(result());
  await settle();
  assert.equal(states.length, count);
});
