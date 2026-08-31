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
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { request } from "node:http";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { registerStatic } from "../src/static.ts";

const gated = process.env.FACE_SMOKE !== "1";

/** One RPC envelope POSTed with a chosen `Host` header, via `node:http`.
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
 * @param body - the request body, already serialized.
 * @returns the response status code.
 */
function postWithHost(port: number, path: string, host: string, body: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const req = request(
      {
        host: "127.0.0.1",
        port,
        path,
        method: "POST",
        headers: { "content-type": "application/json", host, "content-length": Buffer.byteLength(body) },
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

test("boot smoke: face serves /, /api answers, fence holds", { skip: gated && "set FACE_SMOKE=1" }, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-smoke-"));
  setupFaceProfile(home);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home });
  try {
    const clientDir = join(dirname(fileURLToPath(import.meta.url)), "..", "client");
    registerStatic(ctx.webServer, clientDir);
    const base = `http://127.0.0.1:${ctx.webServer.port}`;

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
    const forged = await postWithHost(
      ctx.webServer.port,
      "/api/session.list",
      "evil.example.com",
      JSON.stringify({ type: "client-request", rpcId: "2", method: "session.list", payload: {} }),
    );
    assert.equal(forged, 403);
  } finally {
    await dispose();
  }
});
