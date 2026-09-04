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
 * touch the operator's profiles, sessions, or credentials.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { execFile } from "node:child_process";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { request } from "node:http";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { registerStatic } from "../src/static.ts";
import { registerDataRoutes } from "../src/data.ts";

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
 * @param path - request path, e.g. `/api/session.list`.
 * @param host - the `Host` header value to put on the wire, verbatim.
 * @param body - the request body, already serialized; omitted for a GET.
 * @returns the response status code.
 */
function sendWithHost(port: number, path: string, host: string, body?: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const req = request(
      {
        host: "127.0.0.1",
        port,
        path,
        method: body === undefined ? "GET" : "POST",
        headers: body === undefined
          ? { host }
          : { "content-type": "application/json", host, "content-length": Buffer.byteLength(body) },
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

test("boot smoke: face serves its pages, /api and /data answer, Kairos can ask, both fences hold", { skip: gated && "set FACE_SMOKE=1" }, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-smoke-"));
  setupFaceProfile(home);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home });
  try {
    const clientDir = join(dirname(fileURLToPath(import.meta.url)), "..", "client");
    registerStatic(ctx.webServer, clientDir);
    const base = `http://127.0.0.1:${ctx.webServer.port}`;

    /* Kairos's VOICE, drilled. `bootFace` already refuses a tree missing the
     * `userQuestions` SERVICE; this is its model-facing half, and the two fail
     * INDEPENDENTLY - dsh-base mounts the service and no tool row for it, so
     * the face booted healthy, offered the model its whole toolset, and could
     * never ask the operator anything. `schemas()` with no scope is the global
     * view the agent is served from, and it is the ONLY place the difference
     * shows: an unsatisfied inject leaves the row pending with the composed
     * entry list unchanged, and `/data/plugins.json` cannot stand in either
     * (pluginListing projects tool names only for the `mcp__*` and `agent_*`
     * prefixes, so that payload is byte-identical with the tool and without
     * it). Mutation-proven in both directions on 2026-09-03: 25 tools and no
     * `ask_user_question` before the `tool-ask-user` row, 26 with it. */
    const tools = ctx.get("tools") as { schemas(): { name: string }[] } | undefined;
    assert.ok(tools !== undefined, "the tools service must be in the composed tree");
    const toolNames = tools.schemas().map((schema) => schema.name).sort();
    assert.ok(
      toolNames.includes("ask_user_question"),
      `ask_user_question must be registered; saw ${toolNames.length}: ${toolNames.join(", ")}`,
    );

    // the `exact /` route: the page the operator actually opens
    const index = await fetch(`${base}/`);
    assert.equal(index.status, 200);
    assert.match(await index.text(), /KAIROS/);

    // the `prefix /client` route - registerStatic's other half, and the only
    // place it is exercised against a real webserver rather than a recorder
    const asset = await fetch(`${base}/client/chat.css`);
    assert.equal(asset.status, 200);
    assert.equal(asset.headers.get("content-type"), "text/css; charset=utf-8");

    const list = await fetch(`${base}/api/session.list`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "client-request", rpcId: "1", method: "session.list", payload: {} }),
    });
    assert.equal(list.status, 200);
    const body = (await list.json()) as { result?: { ok?: boolean; value?: { items?: unknown } } };
    // `ok` alone only proves the carrier answered; `items` proves the api
    // gateway really reached the session store behind it (the whole storage →
    // domain → workspace chain the overlay mounts for exactly this).
    assert.equal(body?.result?.ok, true);
    assert.ok(Array.isArray(body?.result?.value?.items), "session.list must return an items array");

    // A plain GET on the mux path: the connection plugin answers 426 with an
    // `upgrade: websocket` hint rather than opening an SSE fallback, because
    // the browser downlink here is WebSocket-only (dsh-client-connection
    // 0.1.1-rc.2, lib/index.js:539-545). Asserting the header too keeps this
    // honest - a bare 426 could come from anywhere, the hint names the reason.
    const mux = await fetch(`${base}/api/events.mux`);
    assert.equal(mux.status, 426);
    assert.equal(mux.headers.get("upgrade"), "websocket");

    // The Host fence, drilled: same request, same socket, attacker authority.
    // This is the DNS-rebinding defense - the one header a rebound browser
    // cannot forge - and the reason the face binds 127.0.0.1 with an empty
    // `trustedHosts`. 200 here would mean any page on the internet can drive
    // the harness through the operator's own browser.
    const forged = await sendWithHost(
      ctx.webServer.port,
      "/api/session.list",
      "evil.example.com",
      JSON.stringify({ type: "client-request", rpcId: "2", method: "session.list", payload: {} }),
    );
    assert.equal(forged, 403);

    // The other two pages registerStatic mounts. Static documents, so what is
    // proven here is the MOUNT — an exact route answering with the right file —
    // and not what they render, which is the client's own to test.
    for (const path of ["/market", "/account"]) {
      const page = await fetch(`${base}${path}`);
      assert.equal(page.status, 200, path);
      assert.match(await page.text(), /KAIROS/);
    }

    // The data plumbing, end to end through a STUB producer: route → cache →
    // spawn → JSON on the wire, with everything but Python real. The producer
    // itself is exercised by the python suite; running it here would make the
    // smoke depend on a captured bed and pay a bed walk.
    //
    // Registered HERE and nowhere else in this file: `registerDataRoutes`
    // throws on a duplicate (kind, path), which is the guard, so the smoke
    // must claim the two `/data` paths exactly once.
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
    const forgedData = await sendWithHost(ctx.webServer.port, "/data/market.json", "evil.example.com");
    assert.equal(forgedData, 403);
  } finally {
    await dispose();
  }
});
