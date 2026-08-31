import test from "node:test";
import assert from "node:assert/strict";
import { join } from "node:path";
import { faceOverlay } from "../src/overlay.ts";

const HOME = "/tmp/face-home";

test("overlay inserts exactly the nine host rows with loopback config", () => {
  const patches = faceOverlay(3090, HOME);
  assert.equal(patches.length, 1);
  const rows = patches[0].insert!;
  const byId = new Map(rows.map(r => [r.id, r]));
  assert.deepEqual(
    [...byId.keys()].sort(),
    ["api-gateway", "connection", "cordis-host-runner", "directory-picker", "storage",
      "storage-domain", "storage-json", "webserver", "workspace"],
  );
  assert.equal(byId.get("webserver")!.name, "@deepseek-ai/dsh-host-webserver");
  assert.deepEqual(byId.get("webserver")!.config, { host: "127.0.0.1", port: 3090 });
  assert.equal(byId.get("api-gateway")!.name, "@deepseek-ai/dsh-host-apiproxy");
  assert.equal(byId.get("connection")!.name, "@deepseek-ai/dsh-client-connection");
  assert.deepEqual(byId.get("connection")!.config, { trustedHosts: [] });
  assert.equal(byId.get("directory-picker")!.name, "@deepseek-ai/dsh-host-directory-picker-auto");
  assert.equal(byId.get("cordis-host-runner")!.name, "@deepseek-ai/dsh-cordis-host-runner");
});

/* The api-gateway row injects `workspaceRegistry`; dsh-base mounts nothing that
 * provides it, so these four rows are what stands between the face and a boot
 * that fails the WHOLE tree with "pending (waiting for service: ...)". The
 * chain is asserted link by link because dropping any one of them reproduces
 * that failure, and only a live boot would otherwise say so. */
test("the storage chain the api-gateway needs is mounted end to end", () => {
  const byId = new Map(faceOverlay(3090, HOME)[0].insert!.map(r => [r.id, r]));
  assert.equal(byId.get("storage")!.name, "@deepseek-ai/dsh-storage");
  assert.equal(byId.get("storage-json")!.name, "@deepseek-ai/dsh-storage-json");
  assert.equal(byId.get("storage-domain")!.name, "@deepseek-ai/dsh-storage-domain");
  assert.deepEqual(byId.get("storage-domain")!.config, { backend: "json" });
  assert.equal(byId.get("workspace")!.name, "@deepseek-ai/dsh-workspace");
});

/* dsh-web-app writes this root as `!!js dshHomePath('storages')`, evaluated by
 * the tree. The face has no expression to evaluate, so the home is passed in —
 * and reading `$DSH_HOME` here instead would scatter a composition's unit files
 * into whichever home the ambient environment happened to name. */
test("the json storage root is derived from the home it was handed", () => {
  const byId = new Map(faceOverlay(3090, HOME)[0].insert!.map(r => [r.id, r]));
  assert.deepEqual(byId.get("storage-json")!.config, { root: join(HOME, "storages") });
});

// The absences are load-bearing, so they are asserted rather than assumed.
// dsh-web-app's connection row carries `inject: [webRuntime]`, but webRuntime is
// provided by the dsh-web-app row the face does NOT mount — inheriting that
// inject would leave the row unresolved forever, and the face never binds
// off-loopback anyway. The other rows take the plugins' own defaults;
// an empty `config: {}` is not the same thing to a patch, which replaces the
// targeted row's whole config.
test("the overlay carries no inject and no config it does not own", () => {
  const rows = faceOverlay(3090, HOME)[0].insert!;
  const byId = new Map(rows.map(r => [r.id, r]));
  assert.ok(!("inject" in byId.get("connection")!), "connection row must not inject");
  for (const id of ["directory-picker", "api-gateway", "cordis-host-runner", "storage", "workspace"]) {
    assert.equal(byId.get(id)!.config, undefined, `${id} must carry no config`);
  }
});
