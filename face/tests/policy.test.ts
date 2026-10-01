/** The face's policy layer (src/policy.ts, PLAN S4): the 0.1.1 tool roster,
 * egress and telemetry posture, restored over dsh-base 0.2.0-rc.2 and
 * overridable by the operator. Composition-level, against the INSTALLED
 * dsh-base: every assertion here is about the entry list boot will mount. */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { composeEntries } from "@deepseek-ai/dsh-app-boot";
import { setupFaceProfile } from "../src/setup.ts";
import { composeFace } from "../src/boot.ts";
import { POLICY_ID_PATCHES, POLICY_INSERTS, facePolicyPatches } from "../src/policy.ts";

/** A throwaway $DSH_HOME with the face profile already laid out in it. */
function freshHome(): string {
  const home = mkdtempSync(join(tmpdir(), "face-policy-"));
  setupFaceProfile(home);
  return home;
}

/** The row ids the BUNDLE layer alone composes to - what the policy may target. */
function bundleRowsOf(home: string): Set<string> {
  const { profile } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const rows = composeEntries([profile.layers.flatMap((layer) => layer.patches)]);
  return new Set(rows.flatMap((row) => (typeof row.id === "string" ? [row.id] : [])));
}

/** The composed entry list for a home, as boot would mount it. */
function composedRows(home: string) {
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  return composeEntries([patches]);
}

/* Group 1 - the targets exist. A patch aimed at an absent row is SILENT (the
 * include's warn sink reaches nothing in a booted face), and a guard that skips
 * it would be silent too: a row renamed upstream would carry its new default
 * straight past this layer. So every target is pinned against the installed
 * dsh-base, and the one insert is pinned ABSENT from it - were base to ship
 * the row again, the insert would be skipped and this must say so. */
test("every policy target is a row dsh-base composes, and the insert is one it does not", () => {
  const base = bundleRowsOf(freshHome());
  for (const { decision, patch } of POLICY_ID_PATCHES) {
    assert.ok(base.has(patch.id), `${decision}: dsh-base composes no "${patch.id}" row`);
  }
  for (const { decision, row } of POLICY_INSERTS) {
    assert.equal(base.has(row.id), false, `${decision}: dsh-base mounts "${row.id}" again - revisit the insert`);
  }
  // Every entry names the PLAN §6 decision it implements.
  for (const { decision } of [...POLICY_ID_PATCHES, ...POLICY_INSERTS]) assert.match(decision, /^D\d+ /);
});

/* Group 2 - the composed tree carries 0.1.1's posture. Asserted on the COMPOSED
 * rows, not on the patch list: that is the only place a lost layer, a patch
 * that replaced too much, or a duplicate row would show. */
test("the composed tree keeps the 0.1.1 roster, egress and telemetry posture", () => {
  const rows = composedRows(freshHome());
  const one = (id: string) => {
    const matches = rows.filter((row) => row.id === id);
    assert.equal(matches.length, 1, `${id} should compose once, saw ${matches.length}`);
    return matches[0]!;
  };
  // D6: no web_fetch - the tool, its provider and the runtime's provider id, all 0.1.1's.
  assert.deepEqual(one("tool-web").config, { fetch: false, searchTimeoutMs: 60000 });
  assert.deepEqual(one("web").config, { searchProvider: "deepseek-official" }, "no fetchProvider");
  // D3-D7: the new egress and the new tools, off.
  for (const id of ["web-fetch-http", "mcp-resources", "session-log-deepseek",
    "plugin-package-inventory-deepseek", "session-telemetry-otel"]) {
    assert.equal(one(id).disabled, true, `${id} must be disabled`);
  }
  // D9: ralph back on WITH its base config (a disabled-only patch keeps the config) ...
  const ralph = one("tool-ralph");
  assert.equal(ralph.disabled, false);
  assert.deepEqual(ralph.config, { subagentProvider: "spawn", maxRounds: 64 });
  // ... and str_replace_editor inserted once, configless (16000 is the schema default now).
  const editor = one("tool-str-replace-editor");
  assert.equal(editor.name, "@deepseek-ai/dsh-tool-str-replace-editor");
  assert.equal(editor.config, undefined);
});

/* Group 3 - operator override wins. The layer sits BELOW the profile's patch
 * file on purpose: each restoration is a default the operator can reverse with
 * one row, never a contract the face imposes. */
test("an operator row overrides a policy default", () => {
  const home = freshHome();
  writeFileSync(join(home, "profiles", "face", "cordis.patch.yml"), [
    "- id: tool-web",
    "  config: { fetch: true, searchTimeoutMs: 60000 }",
    "- id: session-log-deepseek",
    "  disabled: false",
    "",
  ].join("\n"));
  const rows = composedRows(home);
  assert.deepEqual(rows.find((row) => row.id === "tool-web")?.config, { fetch: true, searchTimeoutMs: 60000 });
  assert.equal(rows.find((row) => row.id === "session-log-deepseek")?.disabled, false);
  // An override is per row: the neighbouring defaults are untouched.
  assert.equal(rows.find((row) => row.id === "web-fetch-http")?.disabled, true);
});

/* The telemetry opt-out keeps working on top of the policy, and still wins over
 * an operator who re-enabled the row: a privacy switch outranks a default. */
test("DSH_TELEMETRY_DISABLED still wins over an operator re-enable", () => {
  const home = freshHome();
  writeFileSync(join(home, "profiles", "face", "cordis.patch.yml"), "- id: session-telemetry-otel\n  disabled: false\n");
  const previous = process.env.DSH_TELEMETRY_DISABLED;
  try {
    delete process.env.DSH_TELEMETRY_DISABLED;
    assert.equal(composedRows(home).find((row) => row.id === "session-telemetry-otel")?.disabled, false);
    process.env.DSH_TELEMETRY_DISABLED = "1";
    assert.equal(composedRows(home).find((row) => row.id === "session-telemetry-otel")?.disabled, true);
  } finally {
    if (previous === undefined) delete process.env.DSH_TELEMETRY_DISABLED;
    else process.env.DSH_TELEMETRY_DISABLED = previous;
  }
});

/* The guard, unit-level: a target missing from the bundle composition yields
 * no patch AND one reported line (never silence), a present insert target
 * yields no duplicate insert, and what comes back is a fresh copy - composing
 * or mutating it can never edit the module's own table. */
test("facePolicyPatches guards on the bundle rows, reports misses, and hands out copies", () => {
  const missing: string[] = [];
  const bare = facePolicyPatches(new Set(), (line) => missing.push(line));
  assert.deepEqual(bare, [{ insert: [{ id: "tool-str-replace-editor", name: "@deepseek-ai/dsh-tool-str-replace-editor" }] }]);
  assert.equal(missing.length, POLICY_ID_PATCHES.length, "every absent target is reported");
  assert.match(missing[0]!, /session-telemetry-otel/);

  const all = new Set([...POLICY_ID_PATCHES.map(({ patch }) => patch.id), "tool-str-replace-editor"]);
  const full = facePolicyPatches(all, () => assert.fail("nothing is missing"));
  assert.equal(full.length, POLICY_ID_PATCHES.length, "no insert when base already mounts the row");
  const toolWeb = full.find((p) => p.id === "tool-web")!;
  toolWeb.config.fetch = true;
  assert.deepEqual(POLICY_ID_PATCHES.find(({ patch }) => patch.id === "tool-web")!.patch.config, { fetch: false, searchTimeoutMs: 60000 });
});
