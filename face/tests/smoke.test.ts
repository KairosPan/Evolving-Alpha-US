/** The face's one end-to-end proof: a REAL dsh tree, booted in-process, probed
 * over a real socket. Every other test in this directory works on a seam — a
 * composed patch list, a recorder standing in for the webserver, a fixture
 * stream. This one boots the actual harness, so it is the only place where a
 * composition that typechecks but does not MOUNT gets caught.
 *
 * Gated behind `FACE_SMOKE=1` because it is slow (a full plugin tree), writes a
 * throwaway `$DSH_HOME`, and binds a port — none of which belongs in the
 * default `npm test`. Gated off it must skip instantly, which is why the boot
 * lives inside the test body and not at module scope.
 *
 * ONE BOOT PER PROCESS, and it must stay that way: `bootFace` sets
 * `process.env.DSH_HOME` permanently (boot.ts, the deliberate materialization
 * that keeps the composed home and the running tree's own `resolveDshHome()`
 * agreeing). A second boot in the same process would compose against the FIRST
 * test's scratch home unless it happened to pass `dshHome` too, and would in
 * any case re-mount a second full tree beside the first. A second smoke case
 * therefore belongs in a second FILE — `node --test` gives each file its own
 * process — never in a second `test()` here.
 *
 * The scratch home is a `mkdtemp` directory, never `~/.dsh`: the smoke must not
 * touch the operator's profiles, sessions, or credentials. (The first boot on a
 * home writes the browser-session signing secret into its
 * `.credentials.yaml` — exactly why this must never be the operator's.)
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { execFile } from "node:child_process";
import { randomBytes } from "node:crypto";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { request } from "node:http";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { registerStatic, type IndexAuth } from "../src/static.ts";
import { registerDataRoutes } from "../src/data.ts";
import { hasApprovalGrant, type ApprovalEventLike } from "../src/orders.ts";
import { remote, signIn } from "./remote.ts";

const gated = process.env.FACE_SMOKE !== "1";

/** One request sent with a chosen `Host` header, via `node:http`. POST when a
 * body is given (the `/api` envelope), GET when it is not (a `/data` read).
 *
 * `fetch` cannot do this and does not say so: undici silently DROPS a `host`
 * entry in `headers` and writes the connect authority instead (measured on
 * node v22 — the probe got `127.0.0.1:<port>` back, not the forged name). A
 * fetch-based fence drill would therefore pass the loopback check and answer
 * 200, which is exactly the "the fence is off" reading it exists to rule out.
 * `node:http` honours an explicit `headers.host` over the connect target, so
 * the forged request reaches the server with the attacker's authority on it.
 * @param port - the face's bound port; the socket always goes to 127.0.0.1.
 * @param path - request path, e.g. `/api/session/list`.
 * @param host - the `Host` header value to put on the wire, verbatim.
 * @param body - the request body, already serialized; omitted for a GET.
 * @param extra - further headers (a cookie, for the fence-before-auth drill).
 * @returns the response status code.
 */
function sendWithHost(port: number, path: string, host: string, body?: string, extra: Record<string, string> = {}): Promise<number> {
  return new Promise((resolve, reject) => {
    const req = request(
      {
        host: "127.0.0.1",
        port,
        path,
        method: body === undefined ? "GET" : "POST",
        headers: body === undefined
          ? { host, ...extra }
          : { "content-type": "application/json", host, "content-length": Buffer.byteLength(body), ...extra },
      },
      (res) => {
        res.resume(); // drain, or the socket keeps the process alive
        res.on("end", () => resolve(res.statusCode ?? 0));
      },
    );
    req.on("error", reject);
    req.end(body);
  });
}

/** What a raw WebSocket upgrade request got back. */
type UpgradeOutcome = { status: number } | { error: string };

/**
 * Send a bare WebSocket upgrade to `/api/remote.mux` and report the answer's
 * status line — `node:http`, not a WebSocket client, because the point is the
 * HTTP answer to the upgrade itself:
 * - `101` — the gateway admitted the stream (then the socket is dropped);
 * - `401`/`403` — Connection's admission refused it before the upgrade, a raw
 *   `HTTP/1.1 401 Unauthorized` the gateway writes itself (NEW packages/api/
 *   gateway/src/stream-server.ts:433-444);
 * - an `error` — nobody owns the path: the webserver destroys an unmatched
 *   upgrade's socket without a word (NEW packages/host/webserver/src/
 *   index.ts:258, 277-280). That is what the route looks like before `appReady`
 *   commits, because the gateway registers it only on commit (NEW
 *   packages/api/gateway/src/index.ts:265-276).
 * @param port - the face's bound port.
 * @param cookie - the browser-session cookie, or nothing.
 */
function upgradeMux(port: number, cookie?: string): Promise<UpgradeOutcome> {
  return new Promise((resolve) => {
    const req = request({
      host: "127.0.0.1",
      port,
      path: "/api/remote.mux",
      method: "GET",
      headers: {
        connection: "Upgrade",
        upgrade: "websocket",
        "sec-websocket-key": randomBytes(16).toString("base64"),
        "sec-websocket-version": "13",
        ...(cookie === undefined ? {} : { cookie }),
      },
    });
    req.on("upgrade", (res, socket) => {
      socket.destroy();
      resolve({ status: res.statusCode ?? 0 });
    });
    req.on("response", (res) => {
      res.resume();
      resolve({ status: res.statusCode ?? 0 });
    });
    req.on("error", (err) => resolve({ error: err.message }));
    req.end();
  });
}

/** One `$events` generation over a real WebSocket, as a browser tab holds it. */
interface EventsClient {
  /** From the `ready` frame: the identity `$events/result` must quote. */
  clientId: string;
  /** The next `$events` item (`emit`s skipped - this smoke waits on gates). */
  next(): Promise<Record<string, unknown>>;
  close(): void;
}

/**
 * Open `/api/remote.mux` with the browser cookie and one `$events` logical
 * stream on it, and wait for its `ready`. Node's built-in WebSocket (undici)
 * takes a `headers` init and sends no `Origin`, so the fence and the cookie
 * are exactly a signed-in tab's. Frames: client `{type:'open', streamId,
 * endpoint, payload:{args:{}}}`; host `{type:'item', streamId, value}` with
 * `ready` first, then `waterfall`/`cancel`/`emit` values (NEW
 * packages/api/gateway/src/stream-protocol.ts:7-71, 235-315; `$events` wants
 * exactly `{args:{}}`, index.ts:482-494).
 * @throws when the stream fails, ends, or a frame does not arrive within 5 s.
 */
async function openEvents(port: number, cookie: string): Promise<EventsClient> {
  const socket = new WebSocket(
    `ws://127.0.0.1:${port}/api/remote.mux`,
    // undici's non-standard WebSocketInit; the DOM typing knows only `protocols`.
    { headers: { cookie } } as unknown as string[],
  );
  const items: Record<string, unknown>[] = [];
  const waiting: ((item: Record<string, unknown>) => void)[] = [];
  let failure: string | undefined;
  const deliver = (item: Record<string, unknown>): void => {
    const waiter = waiting.shift();
    if (waiter === undefined) items.push(item);
    else waiter(item);
  };
  socket.addEventListener("message", (event) => {
    const frame = JSON.parse(String(event.data)) as { type: string; streamId: string; value?: Record<string, unknown>; error?: unknown };
    if (frame.streamId !== "events") return;
    if (frame.type === "item" && frame.value !== undefined) {
      if (frame.value.type !== "emit") deliver(frame.value);
      return;
    }
    failure = `$events ${frame.type}: ${JSON.stringify(frame.error ?? null)}`;
    deliver({ type: "failed", failure });
  });
  socket.addEventListener("close", () => {
    failure ??= "the mux socket closed";
    deliver({ type: "failed", failure });
  });
  const next = (): Promise<Record<string, unknown>> => {
    const queued = items.shift();
    if (queued !== undefined) return Promise.resolve(queued);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error(`no $events frame within 5 s${failure === undefined ? "" : ` (${failure})`}`)), 5_000);
      waiting.push((item) => { clearTimeout(timer); resolve(item); });
    });
  };
  await new Promise<void>((resolve, reject) => {
    socket.addEventListener("open", () => resolve(), { once: true });
    socket.addEventListener("error", () => reject(new Error("the mux WebSocket did not open")), { once: true });
  });
  socket.send(JSON.stringify({ type: "open", streamId: "events", endpoint: "$events", payload: { args: {} } }));
  const ready = await next();
  assert.equal(ready.type, "ready", `the first $events item must be ready, got ${JSON.stringify(ready)}`);
  return { clientId: String(ready.clientId), next, close: () => socket.close() };
}

test("boot smoke: sign-in gates /api and the mux, the pages and /data answer, Kairos can ask, both fences hold", { skip: gated && "set FACE_SMOKE=1" }, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-smoke-"));
  setupFaceProfile(home);
  const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
  const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
  // This smoke owns a scratch profile and must not start the operator's data server.
  writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
  /* Booted the way main.ts boots: `deferReady`, so the browser streams open
   * only when `commitReady()` runs after the face's own routes (step 7 below
   * drills both sides of that commit). Every other smoke takes the default,
   * where bootFace commits itself - order-gate-smoke's real `$events` channel
   * is the proof of that path. */
  const { ctx, dispose, commitReady } = await bootFace({ profileName: "face", port: 0, dshHome: home, deferReady: true });
  try {
    const clientDir = join(dirname(fileURLToPath(import.meta.url)), "..", "client");
    registerStatic(ctx.webServer, clientDir, ctx.get("connection") as IndexAuth);
    const port = ctx.webServer.port;
    const base = `http://127.0.0.1:${port}`;

    /* Kairos's VOICE, drilled. `bootFace` already refuses a tree missing the
     * `userQuestions` SERVICE; this is its model-facing half, and the two fail
     * INDEPENDENTLY - dsh-base mounts the service and no tool row for it, so
     * the face booted healthy, offered the model its whole toolset, and could
     * never ask the operator anything. `schemas()` with no scope is the global
     * view the agent is served from, and it is the ONLY place the difference
     * shows: a row can be ACTIVE and still register nothing a model can call,
     * and `/data/plugins.json` cannot stand in either (pluginListing projects
     * tool names only for the `mcp__*` and `agent_*` prefixes, so that payload
     * is byte-identical with the tool and without it). Mutation-proven in both
     * directions on 2026-09-03: 25 tools and no `ask_user_question` before the
     * `tool-ask-user` row, 26 with it. */
    const tools = ctx.get("tools") as { schemas(): { name: string }[] } | undefined;
    assert.ok(tools !== undefined, "the tools service must be in the composed tree");
    const toolNames = tools.schemas().map((schema) => schema.name).sort();
    assert.ok(
      toolNames.includes("ask_user_question"),
      `ask_user_question must be registered; saw ${toolNames.length}: ${toolNames.join(", ")}`,
    );
    /* The policy layer (src/policy.ts), live: the composition tests prove the
     * rows compose; only the running registry proves they register - or, for
     * the disabled ones, that nothing else put the tool back. D9 keeps the two
     * tools 0.1.1 had; D6 and D7 keep out the three that 0.2.0's dsh-base
     * would add (NEW packages/web/tool-web/src/index.ts:83-95;
     * packages/mcp/mcp-resources/src/tools.ts:31-64). */
    for (const kept of ["str_replace_editor", "ralph"]) {
      assert.ok(toolNames.includes(kept), `${kept} must be registered (policy D9); saw ${toolNames.join(", ")}`);
    }
    for (const withheld of ["web_fetch", "list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"]) {
      assert.equal(toolNames.includes(withheld), false, `${withheld} must not be registered (policy D6/D7)`);
    }
    /* The services the overlay's Remote rows exist to provide, by the keys the
     * rest of the face reads them under: the room engine resumes cold sessions
     * through `sessionController`, Gate 2's answerer rides `typertGateway`, and
     * every session composes through `agentPresets`. (bootFace's strict row
     * audit already refused any enabled row that did not activate.) */
    for (const service of ["sessionController", "typertGateway", "agentPresets"]) {
      assert.ok(ctx.get(service) !== undefined, `${service} must be provided`);
    }
    /* Zero inactive entries, asserted HERE as well as refused by bootFace's
     * strict row audit (boot.ts), so a later edit that weakens that audit
     * cannot pass this smoke on a half-mounted tree: dsh 0.2's own boot only
     * WARNS about a failed non-required row (NEW packages/boot/app-boot/src/
     * index.ts:925-939). */
    type LoaderEntry = { options: { id: string; name: string }; readonly disabled: boolean; fiber?: { state: number } };
    const entries = [...(ctx.get("loader") as { entries(): Iterable<LoaderEntry> }).entries()];
    const inactive = entries
      .filter((entry) => !entry.disabled && entry.fiber?.state !== 2 /* FiberState.ACTIVE */)
      .map((entry) => `${entry.options.id} (${entry.options.name}): ${entry.fiber?.state ?? "no fiber"}`);
    assert.deepEqual(inactive, [], "every enabled Loader entry must be ACTIVE");
    assert.ok(entries.some((entry) => entry.options.name === "@deepseek-ai/dsh-api-remotes" && !entry.disabled),
      "the approval answerer row must be mounted");

    /* 1. `/` without a cookie is the sign-in's refusal, not the page: dsh 0.2
     * serves the index only past `authorizeIndex` (static.ts). */
    const anonymous = await fetch(`${base}/`, { redirect: "manual" });
    assert.equal(anonymous.status, 401, "/ must refuse a browser that never signed in");
    await anonymous.body?.cancel();

    /* 2. The printed URL's token mints the cookie: `303 ./` + Set-Cookie. */
    const cookie = await signIn(ctx, base);
    assert.match(cookie, /^dsh-auth-[A-Za-z0-9_-]+=v1\./, "the browser-session cookie");

    /* 3. With it, the `exact /` route serves the page the operator opens. */
    const index = await fetch(`${base}/`, { headers: { cookie }, redirect: "manual" });
    assert.equal(index.status, 200);
    assert.equal(index.headers.get("content-type"), "text/html; charset=utf-8");
    assert.match(await index.text(), /KAIROS/);

    // the `prefix /client` route - registerStatic's other half, and the only
    // place it is exercised against a real webserver rather than a recorder.
    // Deliberately WITHOUT the cookie: assets stay public (PLAN D8).
    const asset = await fetch(`${base}/client/chat.css`);
    assert.equal(asset.status, 200);
    assert.equal(asset.headers.get("content-type"), "text/css; charset=utf-8");
    await asset.body?.cancel();

    /* 4. A Remote call over the NEW wire: `POST /api/session/list` with
     * `{args:{_request:{}}}`. `items` (not just `ok`) proves the gateway reached
     * the session-controller row and the session store behind it. */
    const list = await remote<{ items?: unknown }>(base, cookie, "session/list", { _request: {} });
    assert.ok(Array.isArray(list.items), "session/list must return an items array");

    /* 5. The same call without the cookie is refused at admission (401), before
     * any Remote runs (NEW packages/client/connection/src/rpc-host.ts:104-113). */
    const envelope = JSON.stringify({ type: "client-request", rpcId: "no-cookie", method: "session/list", payload: { args: { _request: {} } } });
    const unauthenticated = await fetch(`${base}/api/session/list`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: envelope,
    });
    assert.equal(unauthenticated.status, 401, "/api must refuse a request without the browser session");
    await unauthenticated.body?.cancel();

    /* 6. The Host fence, drilled: same request, attacker authority - WITH the
     * valid cookie. This is the DNS-rebinding defense, the one header a rebound
     * browser cannot forge, and the reason the face binds 127.0.0.1 with an
     * empty `trustedHosts`. 403 (not 401) proves the fence runs BEFORE
     * authentication (rpc-host.ts:105): a cookie never walks a forged Host in. */
    const forged = await sendWithHost(port, "/api/session/list", "evil.example.com", envelope, { cookie });
    assert.equal(forged, 403);

    /* 7. The stream carrier, `/api/remote.mux` (it replaced `/api/events.mux`).
     * Admission is the same cookie. And the route EXISTS only once `appReady`
     * committed (boot.ts, divergence 5; NEW packages/api/gateway/src/
     * index.ts:265-276): before that the webserver destroys an unmatched
     * upgrade. This boot deferred the commit as main.ts does, so FIRST the
     * route must be absent even for a signed-in tab - while the unary `/api`
     * calls above already answered, since only the upgrade waits on
     * readiness - and only `commitReady()` opens it. After the commit, a 401
     * as much as a 101 proves the route exists; a socket error there would be
     * the silent all-streams-dead failure. */
    const early = await upgradeMux(port, cookie);
    assert.ok("error" in early, `before commitReady the mux must have no route (the gateway waits on appReady), got ${JSON.stringify(early)}`);
    commitReady();
    const muxAnonymous = await upgradeMux(port);
    assert.deepEqual(muxAnonymous, { status: 401 }, "the mux upgrade must answer 401 without the cookie (an error means no route: commitReady did not commit)");
    const muxSignedIn = await upgradeMux(port, cookie);
    assert.deepEqual(muxSignedIn, { status: 101 }, "the mux upgrade must switch protocols with the cookie");

    /* 7b. Gate 2's ANSWER CHANNEL, end to end, over the real wire. Everything
     * else about Gate 2 can be green while this is dead: without the overlay's
     * `api-remotes` row every ask resolves 'unavailable' and every order is
     * denied at once (NEW packages/interaction/user-approval/src/index.ts:
     * 280-284). So: two signed-in `$events` generations (two tabs); a live root
     * session from `session/create`; an approval raised the way dsh-tools raises
     * one for an order - `approval.request` inside an open turn, which it
     * requires (user-approval/src/index.ts:84-92, 215-234). The pending ask
     * must reach BOTH tabs as the same `waterfall` (api-remotes → gateway,
     * NEW packages/api/remotes/src/index.ts:57-75; gateway index.ts:549-612);
     * tab A's `$events/result` must settle it with its value; tab B must get
     * `cancel` (index.ts:646-668); and the `allowed-once` grant must land in
     * the session log where Gate 2's guard reads it (`hasApprovalGrant` over
     * `snapshotEvents()`, orders.ts). This is the path the in-process answerer
     * of order-gate-smoke deliberately bypasses (critique G1). */
    const tabA = await openEvents(port, cookie);
    const tabB = await openEvents(port, cookie);
    try {
      const created = await remote<{ sessionId: string }>(base, cookie, "session/create", { request: { cwd: home } });
      type SmokeSession = { append(type: string, data: object): unknown; snapshotEvents(): readonly ApprovalEventLike[] };
      const agent = (ctx.get("agents") as { get(id: string): { session: SmokeSession } | undefined }).get(created.sessionId);
      assert.ok(agent !== undefined, "session/create must leave a live root agent");
      agent.session.append("turn/start", { turn: 1 });
      const toolName = "mcp__drill__place_order";
      const callId = "smoke-call-1";
      const approval = ctx.get("approval") as {
        request(req: { agent: object; toolName: string; callId: string; reason: string }): Promise<string>;
      };
      const decided = approval.request({ agent, toolName, callId, reason: "PAPER order - smoke" });
      const gateA = await tabA.next();
      const gateB = await tabB.next();
      assert.equal(gateA.type, "waterfall", `tab A must receive the pending approval, got ${JSON.stringify(gateA)}` +
        " (DSH_PERMISSION_MODE=danger-full-access would reject before any answerer)");
      assert.equal(gateA.event, "approval/request");
      assert.equal(gateA.agentId, created.sessionId, "a waterfall names its session as agentId");
      assert.deepEqual(gateA.request, { toolName, callId, reason: "PAPER order - smoke" });
      assert.equal(gateB.eventId, gateA.eventId, "every tab receives the same pending event");
      await remote(base, cookie, "$events/result", {
        clientId: tabA.clientId,
        eventId: gateA.eventId,
        outcome: { kind: "result", value: "allowed-once" },
      });
      assert.equal(await decided, "allowed-once", "tab A's answer must settle the host's ask");
      assert.deepEqual(await tabB.next(), { type: "cancel", eventId: gateA.eventId }, "the other tab's card is withdrawn");
      assert.ok(
        hasApprovalGrant(agent.session.snapshotEvents(), callId, toolName),
        "the allowed-once grant must be in the session log, where Gate 2's guard looks for it",
      );
    } finally {
      tabA.close();
      tabB.close();
    }

    // The other two pages registerStatic mounts. Static documents, so what is
    // proven here is the MOUNT — an exact route answering with the right file —
    // and not what they render, which is the client's own to test. No cookie:
    // only `/` is behind the sign-in (D8).
    for (const path of ["/market", "/account"]) {
      const page = await fetch(`${base}${path}`);
      assert.equal(page.status, 200, path);
      assert.match(await page.text(), /KAIROS/);
    }

    /* 8. The data plumbing, end to end through a STUB producer: route → cache →
     * spawn → JSON on the wire, with everything but Python real. The producer
     * itself is exercised by the python suite; running it here would make the
     * smoke depend on a captured bed and pay a bed walk. `/data` is unchanged
     * by 0.2.0: still fence-only, no cookie (PLAN D8).
     *
     * Registered HERE and nowhere else in this file: `registerDataRoutes`
     * throws on a duplicate (kind, path), which is the guard, so the smoke
     * must claim the two `/data` paths exactly once. */
    const stub = join(home, "stub.sh");
    writeFileSync(stub, `#!/bin/sh\necho '{"ok":true,"stub":true,"generated_at":"x"}'\n`, { mode: 0o755 });
    registerDataRoutes(ctx.webServer, {
      // The injected seam's real shape: `argv` arrives as [script, mode] with
      // the script path fixed by the route, so only the mode word is passed
      // on, and `timeoutMs` is honoured rather than dropped.
      spawn: (argv, timeoutMs) => new Promise((resolve, reject) => {
        execFile(stub, argv.slice(1), { timeout: timeoutMs }, (err, stdout) =>
          err ? reject(err) : resolve({ stdout: String(stdout), code: 0 }));
      }),
    });
    const dataRes = await fetch(`${base}/data/market.json`);
    assert.equal(dataRes.status, 200);
    assert.equal(((await dataRes.json()) as { stub?: boolean }).stub, true);

    // And the SAME fence over `/data`. It is a second implementation
    // (data.ts's own `isLoopbackHost`, not dsh-client-connection's) guarding a
    // route that carries the operator's positions and orders, so it is drilled
    // separately rather than assumed to ride along with the `/api` one above.
    const forgedData = await sendWithHost(port, "/data/market.json", "evil.example.com");
    assert.equal(forgedData, 403);
  } finally {
    await dispose();
  }
});
