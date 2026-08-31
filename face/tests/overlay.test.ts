import test from "node:test";
import assert from "node:assert/strict";
import { faceOverlay } from "../src/overlay.ts";

test("overlay inserts exactly the five host rows with loopback config", () => {
  const patches = faceOverlay(3090);
  assert.equal(patches.length, 1);
  const rows = patches[0].insert!;
  const byId = new Map(rows.map(r => [r.id, r]));
  assert.deepEqual(
    [...byId.keys()].sort(),
    ["api-gateway", "connection", "cordis-host-runner", "directory-picker", "webserver"],
  );
  assert.equal(byId.get("webserver")!.name, "@deepseek-ai/dsh-host-webserver");
  assert.deepEqual(byId.get("webserver")!.config, { host: "127.0.0.1", port: 3090 });
  assert.equal(byId.get("api-gateway")!.name, "@deepseek-ai/dsh-host-apiproxy");
  assert.equal(byId.get("connection")!.name, "@deepseek-ai/dsh-client-connection");
  assert.deepEqual(byId.get("connection")!.config, { trustedHosts: [] });
  assert.equal(byId.get("directory-picker")!.name, "@deepseek-ai/dsh-host-directory-picker-auto");
  assert.equal(byId.get("cordis-host-runner")!.name, "@deepseek-ai/dsh-cordis-host-runner");
});

// The absences are load-bearing, so they are asserted rather than assumed.
// dsh-web-app's connection row carries `inject: [webRuntime]`, but webRuntime is
// provided by the dsh-web-app row the face does NOT mount — inheriting that
// inject would leave the row unresolved forever, and the face never binds
// off-loopback anyway. The other three rows take the plugins' own defaults;
// an empty `config: {}` is not the same thing to a patch, which replaces the
// targeted row's whole config.
test("the overlay carries no inject and no config it does not own", () => {
  const rows = faceOverlay(3090)[0].insert!;
  const byId = new Map(rows.map(r => [r.id, r]));
  assert.ok(!("inject" in byId.get("connection")!), "connection row must not inject");
  for (const id of ["directory-picker", "api-gateway", "cordis-host-runner"]) {
    assert.equal(byId.get(id)!.config, undefined, `${id} must carry no config`);
  }
});
