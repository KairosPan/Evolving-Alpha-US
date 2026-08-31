import test from "node:test";
import assert from "node:assert/strict";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { isLoopbackHost, registerDataRoutes, SPAWN_TIMEOUT_MS, TTL_MS, type Spawner } from "../src/data.ts";

/** Captured status/body from one handler call. Same structural stand-in as
 * static.test.ts uses: the handler owns the whole response, so what it wrote IS
 * its observable behaviour. */
function fakeRes(): { out: { status: number; body: string; headers: Record<string, string> }; res: ServerResponse } {
  const out = { status: 0, body: "", headers: {} as Record<string, string> };
  const res = {
    writeHead(status: number, headers?: Record<string, string>) {
      out.status = status;
      Object.assign(out.headers, headers ?? {});
      return res;
    },
    end(body?: string | Buffer) {
      out.body = String(body ?? "");
      return res;
    },
  };
  return { out, res: res as unknown as ServerResponse };
}

/** A request from the face's own page: the ONLY thing these handlers read off
 * it is the Host header, and nothing from it ever reaches the spawn. */
const REQ = { headers: { host: "127.0.0.1:3090" } } as unknown as IncomingMessage;

/** Register with an injected spawner + clock and index the routes by path. */
function routesWith(spawn: Spawner, now: () => number): Map<string, WebRoute> {
  const routes: WebRoute[] = [];
  registerDataRoutes({ register: (route) => routes.push(route) }, { spawn, now });
  return new Map(routes.map((r) => [r.path, r]));
}

/** Call one route and return what it wrote. */
async function call(route: WebRoute, req: IncomingMessage = REQ): Promise<{ status: number; body: string; headers: Record<string, string> }> {
  const { out, res } = fakeRes();
  await route.handler(req, res);
  return out;
}

/** A request carrying `host` verbatim, or none at all. */
function reqWithHost(host?: string): IncomingMessage {
  return { headers: host === undefined ? {} : { host } } as unknown as IncomingMessage;
}

/* The route SHAPE is the contract with the host webserver, exactly as in
 * static.test.ts: two EXACT paths, and no prefix or fallback claim. */
test("registerDataRoutes mounts exactly the two exact routes it claims", () => {
  const routes: WebRoute[] = [];
  registerDataRoutes({ register: (route) => routes.push(route) }, { spawn: async () => ({ stdout: "{}", code: 0 }), now: () => 0 });
  assert.deepEqual(
    routes.map((r) => `${r.kind} ${r.path}`).sort(),
    ["exact /data/account.json", "exact /data/market.json"],
  );
});

test("happy path: spawns once, caches within TTL, spawns again after expiry", async () => {
  let calls = 0;
  let clock = 0;
  const byPath = routesWith(async () => { calls++; return { stdout: '{"ok":true,"n":1}', code: 0 }; }, () => clock);
  const route = byPath.get("/data/market.json")!;

  const a = await call(route);
  assert.equal(a.status, 200);
  assert.equal(a.headers["content-type"], "application/json; charset=utf-8");
  assert.equal(JSON.parse(a.body).ok, true);

  await call(route);
  assert.equal(calls, 1); // cached

  clock = TTL_MS.market + 1;
  await call(route);
  assert.equal(calls, 2); // expired -> respawn
});

test("single-flight: concurrent requests share one spawn", async () => {
  let calls = 0;
  let release!: (v: { stdout: string; code: number }) => void;
  const gate = new Promise<{ stdout: string; code: number }>((r) => { release = r; });
  const byPath = routesWith(() => { calls++; return gate; }, () => 0);
  const route = byPath.get("/data/account.json")!;

  const a = fakeRes();
  const b = fakeRes();
  const p = Promise.all([route.handler(REQ, a.res), route.handler(REQ, b.res)]);
  release({ stdout: '{"ok":true}', code: 0 });
  await p;

  assert.equal(calls, 1);
  assert.equal(a.out.status, 200);
  assert.equal(b.out.status, 200);
});

test("stale-on-error: a thrown spawn after a good cache serves cache with stale:true", async () => {
  let clock = 0;
  let fail = false;
  const byPath = routesWith(async () => {
    if (fail) throw new Error("boom");
    return { stdout: '{"ok":true,"v":7}', code: 0 };
  }, () => clock);
  const route = byPath.get("/data/market.json")!;

  await call(route);
  fail = true;
  clock = TTL_MS.market + 1;
  const b = await call(route);

  assert.equal(b.status, 200);
  const body = JSON.parse(b.body);
  assert.equal(body.v, 7);
  assert.equal(body.stale, true);
});

/* The producer's OTHER failure channel: it exits nonzero with an honest error
 * payload rather than crashing. A cache present makes that stale too - the
 * operator keeps an instrument that reads "as of 15 minutes ago" instead of
 * losing the panel to a transient bed/key failure. */
test("stale-on-error: a nonzero exit after a good cache is stale too, and never overwrites the cache", async () => {
  let clock = 0;
  let fail = false;
  const byPath = routesWith(async () => (fail
    ? { stdout: '{"ok":false,"error":"no keys"}', code: 1 }
    : { stdout: '{"ok":true,"v":7}', code: 0 }), () => clock);
  const route = byPath.get("/data/account.json")!;

  await call(route);
  fail = true;
  clock = TTL_MS.account + 1;
  const b = await call(route);
  assert.equal(b.status, 200);
  assert.deepEqual(JSON.parse(b.body), { ok: true, v: 7, stale: true });

  /* The good body is still the cached one: a served-stale response must not
   * have written the error payload back into the cache. */
  fail = false;
  const c = await call(route);
  assert.deepEqual(JSON.parse(c.body), { ok: true, v: 7 });
});

test("503 with error JSON when no cache and the producer fails", async () => {
  const byPath = routesWith(async () => ({ stdout: '{"ok":false,"error":"no bed"}', code: 1 }), () => 0);
  const a = await call(byPath.get("/data/market.json")!);
  assert.equal(a.status, 503);
  assert.equal(JSON.parse(a.body).ok, false);
  assert.equal(JSON.parse(a.body).error, "no bed");
});

/* The spawn-failure body is FIXED text plus the error's code. Node's execFile
 * error MESSAGE carries the child's whole stderr (measured), so a producer
 * traceback that printed an APCA_* value would be echoed to the browser by a
 * `String(err)` body - the one thing the module header promises never happens.
 * The sentinel stands in for that secret. */
test("503 body on a thrown spawn is a fixed message and the error code - never the error text", async () => {
  const byPath = routesWith(async () => {
    const err = new Error("Command failed: python3\nTraceback: APCA_API_KEY_ID=SECRETVALUE\n") as Error & { code?: string };
    err.code = "ENOENT";
    throw err;
  }, () => 0);
  const a = await call(byPath.get("/data/market.json")!);
  assert.equal(a.status, 503);
  assert.ok(!a.body.includes("SECRETVALUE"), `leaked the child's stderr: ${a.body}`);
  assert.deepEqual(JSON.parse(a.body), { ok: false, error: "producer spawn failed", code: "ENOENT" });
});

/* A non-Error rejection, or one with no code, still may not stringify. */
test("503 body carries a null code when the rejection has none", async () => {
  const byPath = routesWith(async () => { throw "SECRETVALUE"; }, () => 0);
  const a = await call(byPath.get("/data/account.json")!);
  assert.equal(a.status, 503);
  assert.ok(!a.body.includes("SECRETVALUE"), a.body);
  assert.deepEqual(JSON.parse(a.body), { ok: false, error: "producer spawn failed", code: null });
});

/* Exit 0 with nothing on stdout is a broken producer, not a payload: caching it
 * would serve an EMPTY 200 body for a full TTL - a blank instrument that the
 * client cannot even tell apart from a parse failure. */
test("exit 0 with empty stdout is a 503 and is never cached", async () => {
  let calls = 0;
  const byPath = routesWith(async () => { calls++; return { stdout: "", code: 0 }; }, () => 0);
  const route = byPath.get("/data/market.json")!;
  const a = await call(route);
  assert.equal(a.status, 503);
  assert.deepEqual(JSON.parse(a.body), { ok: false, error: "producer failed" });
  await call(route);
  assert.equal(calls, 2); // not cached
});

test("a nonzero exit is never cached", async () => {
  let calls = 0;
  const byPath = routesWith(async () => { calls++; return { stdout: '{"ok":false,"error":"x"}', code: 1 }; }, () => 0);
  const route = byPath.get("/data/account.json")!;
  await call(route);
  await call(route);
  assert.equal(calls, 2);
});

/* A COLD market assembly is minutes, an account read is seconds; one shared
 * timeout would either kill the market walk or hide an account hang. The test
 * pins both the wiring (each handler passes ITS mode's budget) and the numbers,
 * because a market timeout under ~284s would make the first-ever request fail
 * for everyone forever after a code change invalidates the producer's cache. */
test("each mode is spawned with its own timeout and a fixed argv", async () => {
  const seen: Array<{ argv: string[]; timeoutMs: number }> = [];
  const spawn: Spawner = async (argv, timeoutMs) => {
    seen.push({ argv, timeoutMs });
    return { stdout: '{"ok":true}', code: 0 };
  };
  const byPath = routesWith(spawn, () => 0);
  await call(byPath.get("/data/market.json")!);
  await call(byPath.get("/data/account.json")!);

  assert.equal(SPAWN_TIMEOUT_MS.market, 600_000);
  assert.equal(SPAWN_TIMEOUT_MS.account, 30_000);
  assert.equal(TTL_MS.market, 900_000);
  assert.equal(TTL_MS.account, 60_000);
  assert.deepEqual(seen.map((s) => s.timeoutMs), [SPAWN_TIMEOUT_MS.market, SPAWN_TIMEOUT_MS.account]);

  /* No request data ever reaches the child: the argv is the script path and the
   * mode word, nothing else (spec v2 section 3.1). */
  assert.deepEqual(seen.map((s) => s.argv.length), [2, 2]);
  assert.ok(seen[0]!.argv[0]!.endsWith(join("scripts", "face_data.py")), seen[0]!.argv[0]);
  assert.deepEqual(seen.map((s) => s.argv[1]), ["market", "account"]);
});

/* The DNS-rebinding fence, the same one dsh-client-connection puts in front of
 * `/api` (its `isLoopbackHostname`, lib/index.js:100-104) - and the reason the
 * face binds 127.0.0.1 with an empty `trustedHosts`. A rebound page reaches
 * this socket while its Host header still names the ATTACKER's domain, and
 * `/data/account.json` carries the operator's positions and orders. Host is
 * the one header rebinding cannot forge. */
test("isLoopbackHost accepts the loopback spellings and nothing else", () => {
  for (const good of ["127.0.0.1", "127.0.0.1:3090", "localhost", "localhost:3090", "LocalHost:3090", "[::1]", "[::1]:3090", "::1", "127.0.0.53:3090"]) {
    assert.equal(isLoopbackHost(good), true, good);
  }
  for (const bad of [undefined, "", "evil.example.com", "evil.example.com:3090", "127.0.0.1.evil.example.com", "localhost.evil.example.com", "0.0.0.0", "192.168.1.4:3090", "[::2]", "not a host"]) {
    assert.equal(isLoopbackHost(bad), false, String(bad));
  }
});

test("the fence 403s a foreign Host and serves a loopback one", async () => {
  const byPath = routesWith(async () => ({ stdout: '{"ok":true}', code: 0 }), () => 0);
  for (const path of ["/data/market.json", "/data/account.json"]) {
    const route = byPath.get(path)!;
    const forged = await call(route, reqWithHost("evil.example.com"));
    assert.equal(forged.status, 403, path);
    assert.deepEqual(JSON.parse(forged.body), { ok: false, error: "forbidden" });
    /* Fixed body: the refused Host is attacker-controlled text and is never
     * echoed back into the response. */
    assert.ok(!forged.body.includes("evil"), forged.body);

    const missing = await call(route, reqWithHost(undefined));
    assert.equal(missing.status, 403, `${path} must fail closed with no Host`);

    const ok = await call(route, reqWithHost("127.0.0.1:3090"));
    assert.equal(ok.status, 200, path);
  }
});

/* The fence has to be the FIRST thing the handler does: a 403 that still
 * spawned the producer would leave the whole point of the fence - the child
 * process, its Alpaca calls, its minutes of CPU - reachable by any rebound
 * page, even with the payload withheld. */
test("a fenced request never reaches the spawn", async () => {
  let calls = 0;
  const byPath = routesWith(async () => { calls++; return { stdout: '{"ok":true}', code: 0 }; }, () => 0);
  await call(byPath.get("/data/market.json")!, reqWithHost("evil.example.com"));
  await call(byPath.get("/data/account.json")!, reqWithHost(undefined));
  assert.equal(calls, 0);
});

/* main.ts turns ANY unhandled rejection into a process shutdown. The in-flight
 * map's cleanup therefore may not derive an unhandled promise from a rejecting
 * spawn - `void flight.finally(...)` does exactly that, and would take the
 * whole face down the first time python3 is missing. */
test("a rejecting spawn leaves no unhandled rejection behind", async () => {
  const seen: unknown[] = [];
  const onUnhandled = (reason: unknown): void => void seen.push(reason);
  process.on("unhandledRejection", onUnhandled);
  try {
    const byPath = routesWith(async () => { throw new Error("boom"); }, () => 0);
    await call(byPath.get("/data/market.json")!);
    await new Promise((r) => setTimeout(r, 20)); // let the rejection settle
    assert.deepEqual(seen, []);
  } finally {
    process.off("unhandledRejection", onUnhandled);
  }
});
