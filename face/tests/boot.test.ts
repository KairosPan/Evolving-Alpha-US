import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { composeEntries } from "@deepseek-ai/dsh-app-boot";
import { setupFaceProfile } from "../src/setup.ts";
import { composeFace } from "../src/boot.ts";

/** Every row id {@link faceOverlay} owns, as the composed tree should show them. */
const OVERLAY_ROW_IDS = [
  "api-gateway", "connection", "cordis-host-runner", "directory-picker",
  "storage", "storage-domain", "storage-json", "webserver", "workspace",
] as const;

/** A throwaway $DSH_HOME with the face profile already laid out in it. */
function freshHome(): string {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  setupFaceProfile(home);
  return home;
}

/** The webserver row carries the only value the caller passes in, so it is the
 * cheapest proof that OUR layer is the one that survived the composition. */
type InsertPatch = { insert?: Array<{ id: string; config?: { port?: number } }> };

test("composeFace: patch order ends with the face overlay; root is rewritten empty", () => {
  const home = freshHome();
  const { patches, rootConfig } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  // the profile root file was rewritten to the empty include root (the
  // write-back guard - skipping this corrupts subsequent boots)
  assert.match(readFileSync(rootConfig, "utf8"), /\[\]/);
  // last layer is ours: find the webserver row in the final insert patch
  const last = patches.at(-1) as InsertPatch;
  const ws = last.insert?.find((r) => r.id === "webserver");
  assert.equal(ws?.config?.port, 3090);

  // The bundle layer really is first, identified by rows only dsh-base brings -
  // "more than one layer" would also pass on a stack that had lost it.
  const first = patches[0] as InsertPatch;
  const baseRows = new Set(first.insert?.map((r) => r.id));
  for (const id of ["approval", "user-questions", "llm", "session"]) {
    assert.ok(baseRows.has(id), `patches[0] must be the dsh-base layer (missing ${id})`);
  }
});

/* The exact layer count, so a lost or duplicated layer is a failure rather
 * than a silent change of shape. With the telemetry switch unset the stack is:
 * dsh-base's one insert + the (empty) profile layer + the (absent) home layer
 * + the hmr disable + the face overlay = 3 entries. */
test("composeFace stacks exactly the layers it means to", () => {
  const home = freshHome();
  const previous = process.env.DSH_TELEMETRY_DISABLED;
  try {
    delete process.env.DSH_TELEMETRY_DISABLED;
    const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
    assert.equal(patches.length, 3, patches.map((p) => p.id ?? "insert").join(","));
  } finally {
    if (previous === undefined) delete process.env.DSH_TELEMETRY_DISABLED;
    else process.env.DSH_TELEMETRY_DISABLED = previous;
  }
});

/* The stack is a list of patches; what BOOTS is the entry list they compose
 * to, and only that list can answer "does every face row actually land, and
 * exactly once?". An overlay id that collided with a dsh-base row would append
 * a SECOND row under the same id here - two webservers racing for one port,
 * with the patch algorithm none the wiser. composeEntries is dsh's own
 * composition, called the way boot calls it (one flattened list). */
test("every face row lands in the composed tree exactly once", () => {
  const home = freshHome();
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const counts = new Map<string, number>();
  for (const row of composeEntries([patches])) {
    if (typeof row.id === "string") counts.set(row.id, (counts.get(row.id) ?? 0) + 1);
  }
  for (const id of OVERLAY_ROW_IDS) {
    assert.equal(counts.get(id), 1, `${id} should appear once, saw ${counts.get(id) ?? 0}`);
  }
  // And the rows the face patches rather than inserts are still single rows the
  // patch could reach - a duplicate there would mean one copy stayed enabled.
  assert.equal(counts.get("hmr"), 1);
  assert.equal(counts.get("approval"), 1);
});

/* The guard is "ALWAYS rewrite", not "create if missing": the vendored Loader
 * persists the settled tree back into its include root when a plugin disposes
 * itself, which bakes every composed row into cordis.yml. The next boot would
 * then patch the bundle inserts on top of those baked rows and mount each row
 * twice. A test that only ever sees a fresh profile cannot tell the two
 * behaviours apart, so this one hands composeFace an already-poisoned root. */
test("composeFace rewrites a root the loader baked composed rows into", () => {
  const home = freshHome();
  const root = join(home, "profiles", "face", "cordis.yml");
  writeFileSync(root, "- id: webserver\n  name: '@deepseek-ai/dsh-host-webserver'\n");
  composeFace({ profileName: "face", port: 3090, dshHome: home });
  const rewritten = readFileSync(root, "utf8");
  assert.doesNotMatch(rewritten, /dsh-host-webserver/, "baked rows must not survive");
  assert.match(rewritten, /\[\]/);
});

/* Mirrors the CLI's resolveTelemetryPatch: ANY non-empty value disables, and
 * the row id is dsh-base's real one. The id is the whole point of the test - a
 * patch aimed at a row that does not exist is silently inert, so telemetry
 * would keep running with the switch set and nothing would say so. */
test("DSH_TELEMETRY_DISABLED disables dsh-base's session-telemetry-otel row", () => {
  const home = freshHome();
  const previous = process.env.DSH_TELEMETRY_DISABLED;
  try {
    delete process.env.DSH_TELEMETRY_DISABLED;
    const off = composeFace({ profileName: "face", port: 3090, dshHome: home });
    assert.equal(
      off.patches.some((p) => p.id === "session-telemetry-otel"),
      false,
      "unset switch generates no patch",
    );
    // '0' is deliberate: a privacy switch prefers off-by-mistake over on-by-mistake.
    process.env.DSH_TELEMETRY_DISABLED = "0";
    const on = composeFace({ profileName: "face", port: 3090, dshHome: home });
    const patch = on.patches.find((p) => p.id === "session-telemetry-otel");
    assert.equal(patch?.disabled, true);
  } finally {
    if (previous === undefined) delete process.env.DSH_TELEMETRY_DISABLED;
    else process.env.DSH_TELEMETRY_DISABLED = previous;
  }
});

/* Not cosmetic and not optional: @deepseek-ai/cordis-plugin-hmr throws
 * "--expose-internals is required for HMR service" under any ordinary node, so
 * a composition that leaves dsh-base's dev-mode `hmr` row enabled cannot boot
 * AT ALL from `npm start` or from the Task 8 smoke - the whole tree fails to
 * load. Both shipped mode bundles (dsh-web-app, dsh-headless) open their patch
 * layer with this same disable; the face is its own mode bundle. */
test("dsh-base's dev-mode hmr row is disabled - it cannot boot under plain node", () => {
  const home = freshHome();
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const patch = patches.find((p) => p.id === "hmr");
  assert.equal(patch?.disabled, true, "hmr must be disabled by the face's own layer");
});

/* composeFace threads the home through every dsh-app-boot call instead of
 * materializing $DSH_HOME, so composing for one home cannot silently retarget
 * an unrelated boot in the same process (bootFace materializes it on purpose,
 * because the booted tree resolves its own home from the environment). */
test("composeFace resolves the home explicitly and leaves $DSH_HOME alone", () => {
  const home = freshHome();
  const previous = process.env.DSH_HOME;
  try {
    delete process.env.DSH_HOME;
    const { rootConfig } = composeFace({ profileName: "face", port: 3090, dshHome: home });
    assert.equal(rootConfig, join(home, "profiles", "face", "cordis.yml"));
    assert.equal(process.env.DSH_HOME, undefined);
  } finally {
    if (previous === undefined) delete process.env.DSH_HOME;
    else process.env.DSH_HOME = previous;
  }
});
