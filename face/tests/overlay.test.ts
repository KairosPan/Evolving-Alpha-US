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
