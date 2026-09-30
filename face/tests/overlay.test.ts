import test from "node:test";
import assert from "node:assert/strict";
import type { Config as AgentPresetConfig } from "@deepseek-ai/dsh-agent-preset";
import { AGENT_PRESET_REGISTRY_ROW_ID, DEFAULT_PRESET, faceOverlay, presetRowId } from "../src/overlay.ts";

/** The default preset a composition hands the overlay: `bots/kairos` as a definition. */
const KAIROS: AgentPresetConfig = {
  id: "kairos",
  name: "Kairos",
  description: "the principal agent",
  plugins: [],
};

/** The twelve host rows, in the order the overlay inserts them, with the
 * package each must name (PLAN S2's table). The order is not load semantics -
 * activation is service-driven - but it is the reviewable contract, and a
 * silently re-ordered or re-named row is exactly the drift this pins. */
const ROWS: ReadonlyArray<readonly [id: string, pkg: string]> = [
  ["webserver", "@deepseek-ai/dsh-host-webserver"],
  ["connection", "@deepseek-ai/dsh-client-connection"],
  ["api-remotes", "@deepseek-ai/dsh-api-remotes"],
  ["file-upload", "@deepseek-ai/dsh-client-file-upload"],
  ["workspace", "@deepseek-ai/dsh-workspace"],
  ["session-controller", "@deepseek-ai/dsh-api-session-controller"],
  ["workspace-controller", "@deepseek-ai/dsh-api-workspace-controller"],
  ["settings-controller", "@deepseek-ai/dsh-api-settings-controller"],
  ["directory-picker", "@deepseek-ai/dsh-host-directory-picker-auto"],
  ["tool-ask-user", "@deepseek-ai/dsh-tool-ask-user"],
  ["agent-preset-registry", "@deepseek-ai/dsh-agent-preset-registry"],
  ["preset-kairos", "@deepseek-ai/dsh-agent-preset"],
];

function rowsById() {
  const patches = faceOverlay(3090, KAIROS);
  assert.equal(patches.length, 1, "the overlay is ONE insert patch");
  return new Map(patches[0]!.insert!.map((r) => [r.id, r]));
}

test("overlay inserts exactly the twelve host rows, in order, each naming its package", () => {
  const rows = faceOverlay(3090, KAIROS)[0]!.insert!;
  assert.deepEqual(rows.map((r) => [r.id, r.name]), ROWS.map(([id, pkg]) => [id, pkg]));
});

/* `compression` is optional upstream and defaults to 'none'; it is written so
 * the choice is explicit. dsh-web-app runs gzip, which here would also wrap the
 * face's own /data JSON - a change nobody asked for arriving through a mirror. */
test("the webserver binds loopback on the requested port, uncompressed", () => {
  assert.deepEqual(rowsById().get("webserver")!.config, { host: "127.0.0.1", port: 3090, compression: "none" });
});

// The absences are load-bearing, so they are asserted rather than assumed.
// dsh-web-app's connection row carries `inject: [webRuntime]`, but webRuntime is
// provided by the dsh-web-app row the face does NOT mount — inheriting that
// inject would leave the row unresolved forever, and the face never binds
// off-loopback anyway.
test("connection trusts no extra host and injects nothing", () => {
  const connection = rowsById().get("connection")!;
  assert.deepEqual(connection.config, { trustedHosts: [] });
  assert.ok(!("inject" in connection), "connection row must not inject");
});

/* `default` is the registry's only required key, and the row id doubles as its
 * settings namespace upstream - both pinned. The `roots`/`trust`/
 * `includeUserRoot` keys of the retired dsh-agent-presets row must not come
 * back: the registry scans nothing, and a stray key is a dead config. */
test("the preset registry defaults to kairos and carries nothing else", () => {
  const byId = rowsById();
  assert.equal(AGENT_PRESET_REGISTRY_ROW_ID, "agent-preset-registry");
  assert.equal(DEFAULT_PRESET, "kairos");
  assert.deepEqual(byId.get(AGENT_PRESET_REGISTRY_ROW_ID)!.config, { default: "kairos" });
});

/* The default preset is declared statically so it exists before the first
 * session/create, whose preset-less path resolves `defaultId`. The row carries
 * the definition it was handed - a COPY, so the composed tree never aliases the
 * caller's object - under `preset-<config.id>`. */
test("preset-kairos declares exactly the definition it was handed", () => {
  const row = rowsById().get(presetRowId("kairos"))!;
  assert.equal(presetRowId("kairos"), "preset-kairos");
  assert.deepEqual(row.config, KAIROS);
  assert.notEqual(row.config, KAIROS, "the overlay must not alias the caller's definition");
});

/* These rows take the plugins' own defaults. An empty `config: {}` is not the
 * same thing to a patch, which replaces the targeted row's whole config. For
 * `tool-ask-user` configless means `mode: legacy`, the blocking
 * `ask_user_question` bootFace asserts by name. */
test("the controller, workspace, picker and ask-user rows carry no config", () => {
  const byId = rowsById();
  for (const id of ["api-remotes", "file-upload", "workspace", "session-controller", "workspace-controller",
    "settings-controller", "directory-picker", "tool-ask-user"]) {
    assert.ok(byId.has(id), `${id} must be inserted`);
    assert.equal(byId.get(id)!.config, undefined, `${id} must carry no config`);
  }
});

/* Every one of these was a face row at 0.1.1-rc.2 and must NOT be one now:
 * - storage, storage-json, storage-domain, session-projection-cache: dsh-base
 *   mounts them itself at 0.2.0; a same-id insert silently REPLACES base's row
 *   and swallows every operator patch aimed at it;
 * - api-gateway (dsh-host-apiproxy) and agent-presets (dsh-agent-presets): the
 *   packages were deleted upstream;
 * - cordis-host-runner: no consumer, and it publishes Remotes on /api;
 * - typert-gateway: dsh-base's; a second gateway throws on the second /api
 *   interceptor. */
test("the rows dsh-base owns now, and the retired ones, are not inserted", () => {
  const byId = rowsById();
  for (const id of ["storage", "storage-json", "storage-domain", "session-projection-cache", "api-gateway",
    "cordis-host-runner", "agent-presets", "typert-gateway"]) {
    assert.equal(byId.has(id), false, `${id} must not be a face row`);
  }
});
