import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { composeEntries } from "@deepseek-ai/dsh-app-boot";
import { setupFaceProfile } from "../src/setup.ts";
import { composeFace } from "../src/boot.ts";
import { AKSHARE_MCP_ROW_ID } from "../src/akshare.ts";
import { PERSONA_PATH, readPersona } from "../src/persona.ts";
import { CYCLE_PATH, readCycle } from "../src/cycle.ts";
import { AGENT_INSTRUCTIONS_ROW_ID, INSTRUCTIONS_CONFIG, instructionsPatch } from "../src/instructions.ts";
import { facePolicyPatches } from "../src/policy.ts";
import { definitionFor } from "../src/bot-presets.ts";
import { LEGACY_PRESET_DESCRIPTION } from "../src/overlay.ts";
import { GRAVIT_PLUGIN_URL, gravitRows, readRoles } from "../src/roles.ts";
import { makeBotsRoot, makeRolesRoot } from "./bots-fixture.ts";

/** Every row id {@link faceOverlay} owns, as the composed tree should show them. */
const OVERLAY_ROW_IDS = [
  "agent-preset-registry", "api-remotes", "connection", "directory-picker", "file-upload", "preset-gravit",
  "session-controller", "settings-controller", "tool-ask-user", "webserver", "workspace", "workspace-controller",
] as const;

/** The rows the face inserted at 0.1.1 and dsh-base mounts itself at 0.2.0
 * (NEW packages/bundle/base/cordis.patch.yml:165-186): they must compose
 * exactly once, and FROM dsh-base. */
const BASE_OWNED_STORAGE_ROWS = [
  ["storage", "@deepseek-ai/dsh-storage"],
  ["storage-json", "@deepseek-ai/dsh-storage-json"],
  ["storage-domain", "@deepseek-ai/dsh-storage-domain"],
  ["session-projection-cache", "@deepseek-ai/dsh-session-projection-cache"],
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
 * dsh-base insert + the policy layer (src/policy.ts) + AKShare insert + hmr
 * disable + system-prompt persona + agent-instructions + face overlay. The
 * policy layer is pinned both by size (8 id patches + 1 insert against
 * 0.2.0-rc.2's dsh-base) and by POSITION - directly after the bundle layer,
 * below the operator's. */
test("composeFace stacks exactly the layers it means to", () => {
  const home = freshHome();
  const previous = process.env.DSH_TELEMETRY_DISABLED;
  try {
    delete process.env.DSH_TELEMETRY_DISABLED;
    const { patches, profile } = composeFace({ profileName: "face", port: 3090, dshHome: home });
    const baseRows = new Set(
      composeEntries([profile.layers.flatMap((layer) => layer.patches)])
        .flatMap((row) => (typeof row.id === "string" ? [row.id] : [])),
    );
    const policy = facePolicyPatches(baseRows);
    assert.equal(policy.length, 9, "8 id patches + 1 insert at dsh-base 0.2.0-rc.2");
    assert.equal(patches.length, 6 + policy.length, patches.map((p) => p.id ?? "insert").join(","));
    assert.deepEqual(patches.slice(1, 1 + policy.length), policy, "the policy layer sits right above the bundle layer");
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
  assert.equal(counts.get(AKSHARE_MCP_ROW_ID), 1, "AKShare must be registered exactly once");
  // dsh-base's own gateway: the face must not have added a second one.
  assert.equal(counts.get("typert-gateway"), 1);
});

/* The duplicate-id trap, closed. At 0.1.1 the face inserted the storage chain
 * and the projection cache itself; at 0.2.0 dsh-base does, and a same-id insert
 * is not an error - the include appends it and the Loader keeps the LAST row per
 * id (NEW vendor/include/src/index.ts:93-100; vendor/loader/src/config/
 * group.ts:48-65), silently replacing base's row. Counting ids alone would not
 * see that, so the package name is pinned too: each row must be base's. */
test("the storage chain and projection cache compose once, from dsh-base", () => {
  const home = freshHome();
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const rows = composeEntries([patches]);
  for (const [id, pkg] of BASE_OWNED_STORAGE_ROWS) {
    const matches = rows.filter((row) => row.id === id);
    assert.equal(matches.length, 1, `${id} should compose once, saw ${matches.length}`);
    assert.equal(matches[0]!.name, pkg, `${id} must be dsh-base's row`);
  }
  // Positional proof it is base's copy: the only insert carrying it is patches[0], the bundle layer.
  const inserters = patches.filter((p) => (p.insert ?? []).some((r: { id?: string }) => r.id === "storage-json"));
  assert.equal(inserters.length, 1);
  assert.equal(inserters[0], patches[0]);
});

/* The payoff of dropping the duplicates: an operator patch aimed at a base-owned
 * storage row takes effect again. At 0.1.1 it reached base's copy, which the
 * face's own insert then replaced - accepted, discarded, never reported. */
test("an operator patch now reaches the base-owned storage rows", () => {
  const home = freshHome();
  writeFileSync(join(home, "profiles", "face", "cordis.patch.yml"), "- id: storage-json\n  config: { root: /tmp/x }\n");
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const row = composeEntries([patches]).find((r) => r.id === "storage-json");
  assert.deepEqual(row?.config, { root: "/tmp/x" });
});

test("composeFace mounts AKShare with the requested command", () => {
  const home = freshHome();
  const previous = process.env.FACE_AKSHARE_MCP_COMMAND;
  try {
    process.env.FACE_AKSHARE_MCP_COMMAND = "/tmp/face-test-akshare-mcp";
    const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
    const row = composeEntries([patches]).find((r) => r.id === AKSHARE_MCP_ROW_ID);
    assert.ok(row);
    assert.equal(row.name, "@deepseek-ai/dsh-mcp-client");
    const config = row.config as { serverName?: string; transport?: string; command?: string };
    assert.equal(config.serverName, "akshare");
    assert.equal(config.transport, "stdio");
    assert.equal(config.command, "/tmp/face-test-akshare-mcp");
  } finally {
    if (previous === undefined) delete process.env.FACE_AKSHARE_MCP_COMMAND;
    else process.env.FACE_AKSHARE_MCP_COMMAND = previous;
  }
});

test("the profile can override or disable the repo's AKShare row", () => {
  const home = freshHome();
  const profilePatch = join(home, "profiles", "face", "cordis.patch.yml");
  writeFileSync(profilePatch, [
    `- id: ${AKSHARE_MCP_ROW_ID}`,
    "  config:",
    "    transport: stdio",
    "    serverName: akshare",
    "    command: /tmp/profile-akshare-mcp",
    "    args: [--profile-test]",
    "",
  ].join("\n"));
  const overridden = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const rows = composeEntries([overridden.patches]).filter((r) => r.id === AKSHARE_MCP_ROW_ID);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].config, {
    transport: "stdio",
    serverName: "akshare",
    command: "/tmp/profile-akshare-mcp",
    args: ["--profile-test"],
  });

  writeFileSync(profilePatch, `- id: ${AKSHARE_MCP_ROW_ID}\n  disabled: true\n`);
  const disabled = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const disabledRows = composeEntries([disabled.patches]).filter((r) => r.id === AKSHARE_MCP_ROW_ID);
  assert.equal(disabledRows.length, 1);
  assert.equal(disabledRows[0].disabled, true, "the default must not re-enable an operator-disabled row");
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
 * would keep running with the switch set and nothing would say so.
 *
 * Since the policy layer (src/policy.ts, D3) the row is disabled by DEFAULT,
 * below the operator's layers - so "an unset switch generates no telemetry
 * patch" (this test's 0.1.1 assertion) no longer holds and was replaced: the
 * contract now is that the SWITCH's patch is absent when unset and, when set,
 * lands AFTER the operator's layers (past AKShare, profile and home), where it
 * outranks an operator re-enable. policy.test.ts drills that override. */
test("DSH_TELEMETRY_DISABLED disables dsh-base's session-telemetry-otel row", () => {
  const home = freshHome();
  const previous = process.env.DSH_TELEMETRY_DISABLED;
  const telemetryIndices = (patches: readonly { id?: string }[]) =>
    patches.flatMap((p, i) => (p.id === "session-telemetry-otel" ? [i] : []));
  try {
    delete process.env.DSH_TELEMETRY_DISABLED;
    const off = composeFace({ profileName: "face", port: 3090, dshHome: home });
    const policyEnd = 1 + facePolicyPatches(new Set(
      composeEntries([off.profile.layers.flatMap((layer) => layer.patches)])
        .flatMap((row) => (typeof row.id === "string" ? [row.id] : [])),
    )).length;
    const offAt = telemetryIndices(off.patches);
    assert.equal(offAt.length, 1, "unset switch generates no patch of its own - only the policy default");
    assert.ok(offAt[0]! >= 1 && offAt[0]! < policyEnd, "that one patch is the policy layer's (D3)");
    // '0' is deliberate: a privacy switch prefers off-by-mistake over on-by-mistake.
    process.env.DSH_TELEMETRY_DISABLED = "0";
    const on = composeFace({ profileName: "face", port: 3090, dshHome: home });
    const onAt = telemetryIndices(on.patches);
    assert.equal(onAt.length, 2, "the switch adds its own patch beside the policy default");
    const switchPatch = on.patches[onAt[1]!]!;
    assert.equal(switchPatch.disabled, true);
    assert.ok(onAt[1]! > policyEnd, "the switch composes after the AKShare, profile and home layers");
  } finally {
    if (previous === undefined) delete process.env.DSH_TELEMETRY_DISABLED;
    else process.env.DSH_TELEMETRY_DISABLED = previous;
  }
});

/* Defence in depth, kept on purpose. dsh-base's `hmr` row is now
 * `@deepseek-ai/dsh-hmr`, disabled by its own `!ctx.get('profileContext')`
 * expression (NEW packages/bundle/base/cordis.patch.yml:27-32), and the face
 * provides no profileContext - so the row is off either way today. But were
 * anything ever to provide one, dsh-hmr would throw without --expose-internals
 * or appReady and, worse, reconcile the live tree from files that do not carry
 * the face's layers (MAP boot-mirror §6). The face's own switch keeps it off
 * whatever the expression evaluates to. */
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

/* D11, asserted where it is composable: dsh-base ships `personaPrefix: ''` and
 * the face is the deployment that fills it in. An id-targeted patch that matched
 * nothing would be SILENT, so the check is on the COMPOSED row rather than on
 * the patch list - the same reason the hmr and telemetry switches are guarded.
 * The key is the 0.2.0 one: `persona` is gone (commit 40792330c0), and a patch
 * still writing it would compose "fine" and leave Gravit nameless - so the old
 * key is asserted ABSENT, not merely the new one present. */
test("composeFace sets Gravit's persona on dsh-base's system-prompt row", () => {
  const home = freshHome();
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const row = composeEntries([patches]).find((r) => r.id === "system-prompt");
  assert.ok(row, "system-prompt row present");
  const config = row!.config as { personaPrefix?: string; persona?: string; personaSuffix?: string };
  const persona = config.personaPrefix ?? "";
  assert.match(persona, /^You are Gravit/);
  assert.equal(persona, readPersona(PERSONA_PATH));
  assert.equal(config.persona, undefined, "the 0.1.1 key must not be written");
  assert.equal(config.personaSuffix, undefined, "no suffix: 0.1.1 had none, and it defaults to ''");
});

/* ONLY the persona is the face's on this row. The patch composes after the
 * operator's layers and a patch replaces the row's whole config, so a
 * `{ personaPrefix }`-only patch would silently drop every other key the
 * operator set - `includeRuntimeContext: false`, their knob for 0.2.0's
 * runtime-context prefix churn, among them (critique-boot-and-composition W3).
 * The persona still wins over an operator `personaPrefix`: that key IS the
 * face's. */
test("the persona patch keeps the operator's other system-prompt keys", () => {
  const home = freshHome();
  writeFileSync(join(home, "profiles", "face", "cordis.patch.yml"), [
    "- id: system-prompt",
    "  config:",
    "    includeRuntimeContext: false",
    "    personaSuffix: 'Operator suffix.'",
    "    personaPrefix: 'Operator prefix that must lose.'",
    "",
  ].join("\n"));
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const rows = composeEntries([patches]).filter((r) => r.id === "system-prompt");
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0]!.config, {
    includeRuntimeContext: false,
    personaSuffix: "Operator suffix.",
    personaPrefix: readPersona(PERSONA_PATH),
  });
});

/* `loadProfile` no longer throws on a bundle it cannot load: it lists it in
 * `skippedBundles` and hands back a profile WITHOUT that layer (NEW
 * packages/boot/app-boot/src/profile.ts:655-689; commit c8b10a16be). For the
 * face that is a tree with no approval, no tools, no session store - so the
 * compose must refuse, naming the bundle, instead of letting a Gate-2 check
 * three screens later be the first to notice. */
test("composeFace refuses a profile whose bundle was skipped", () => {
  const home = freshHome();
  const manifestPath = join(home, "profiles", "face", "package.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as { dsh: { profile: { bundles: string[] } } };
  manifest.dsh.profile.bundles = ["@deepseek-ai/dsh-no-such-bundle"];
  writeFileSync(manifestPath, JSON.stringify(manifest));
  assert.throws(
    () => composeFace({ profileName: "face", port: 3090, dshHome: home }),
    /skipped bundle\(s\) @deepseek-ai\/dsh-no-such-bundle/,
  );
});

/* bootFace feeds this profile to `createRuntimeResolution`, whose profile scope
 * is the closure of the profile's bundles - so the compose must hand back the
 * profile it actually loaded (dsh-base's layer and all), not a re-read. */
test("composeFace returns the loaded profile the runtime resolution needs", () => {
  const home = freshHome();
  const { profile, rootConfig } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  assert.deepEqual(profile.layers.map((layer) => layer.packageName), ["@deepseek-ai/dsh-base"]);
  assert.deepEqual(profile.skippedBundles, []);
  assert.equal(join(profile.dir, "cordis.yml"), rootConfig);
});

/* The static `preset-gravit` row is RENDERED from `roles/` in memory at compose
 * time (src/boot.ts; src/roles.ts `gravitRows`): the gravit plugin row, named
 * by an absolute `file:` URL, then one `dsh-tool-subagent` row per role. dsh 0.2
 * reads no bot directory itself, and `bots/gravit` supplies only the display
 * metadata - its `agent.cordis.yml` is a mirror for readers that roles.test.ts
 * holds to the render. A regression back to reading that file, to a hard-coded
 * literal or to a silently empty default fails here. The `preset-kairos` alias
 * carries the very same definition under the id archived sessions persist. The
 * gravit row also carries `dsh/profile/cycle.md` as its `cycle` key (src/cycle.ts),
 * read by `composeFace` beside the roles. */
test("composeFace builds preset-gravit from roles/ in memory: the gravit row by absolute URL, one spawn row per role", async () => {
  const home = freshHome();
  const bots = await makeBotsRoot();
  const rolesRoot = await makeRolesRoot();
  try {
    const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home, botsRoot: bots, rolesRoot });
    const row = composeEntries([patches]).find((entry) => entry.id === "preset-gravit");
    const expected = definitionFor(bots, "gravit", gravitRows(readRoles(rolesRoot), { plugin: GRAVIT_PLUGIN_URL, cycle: readCycle(CYCLE_PATH) }));
    assert.deepEqual(row?.config, expected);
    const plugins = (row?.config as unknown as { plugins: Array<{ id: string; name: string; config: unknown }> }).plugins;
    assert.deepEqual(plugins.map((p) => p.id), ["gravit", "role-probe"]);
    assert.equal(plugins[0].name, GRAVIT_PLUGIN_URL);
    assert.equal((plugins[0].config as { cycle: string }).cycle, readCycle(CYCLE_PATH));

    const legacy = composeEntries([patches]).find((entry) => entry.id === "preset-kairos");
    assert.deepEqual(legacy?.config, { ...expected, id: "kairos", description: LEGACY_PRESET_DESCRIPTION });
  } finally { await rm(rolesRoot, { recursive: true, force: true }); }
});

/* Spec §5.1, fail loud: a role the compose cannot read refuses it, with the
 * file's path - the registry would otherwise mount a default the operator never
 * wrote. (The default's mirror file is not read at all, so its absence or its
 * drift is no longer a compose-time matter.) */
test("composeFace refuses a roles root with a bad role, naming the file", async () => {
  const home = freshHome();
  const rolesRoot = await makeRolesRoot();
  try {
    await writeFile(join(rolesRoot, "probe", "ROLE.md"), "You are {{nobody}}.\n");
    assert.throws(() => composeFace({ profileName: "face", port: 3090, dshHome: home, rolesRoot }), (e: Error) => e.message.includes(join(rolesRoot, "probe", "ROLE.md")));
  } finally { await rm(rolesRoot, { recursive: true, force: true }); }
});

/* The same contract one step earlier: no roles directory at all refuses the compose, naming it, so a
 * deploy that ships `bots/` without `roles/` never boots a default preset with no roles in it. */
test("composeFace refuses a missing roles directory, naming it", () => {
  const home = freshHome();
  const rolesRoot = join(tmpdir(), "no-such-roles");
  assert.throws(() => composeFace({ profileName: "face", port: 3090, dshHome: home, rolesRoot }),
    (e: Error) => e.message.startsWith(`${rolesRoot}: `) && /the roles directory is missing/.test(e.message));
});

/* The cycle contract is read where the roles are and refused the same way: an empty `cycle.md` (or an
 * oversized one) refuses the compose with its path, so Gravit never boots with a silently blank
 * contract - the section would just not exist, and nothing else would say so. `cyclePath` points the
 * read at a fixture; the roles root is a valid fixture, so the cycle is the only thing that can fail. */
test("composeFace refuses an empty cycle file, naming it", async () => {
  const home = freshHome();
  const rolesRoot = await makeRolesRoot();
  const dir = mkdtempSync(join(tmpdir(), "face-cycle-"));
  try {
    const cyclePath = join(dir, "empty.md");
    await writeFile(cyclePath, "  \n");
    assert.throws(() => composeFace({ profileName: "face", port: 3090, dshHome: home, rolesRoot, cyclePath }),
      (e: Error) => e.message.includes(cyclePath) && /empty/.test(e.message));
  } finally {
    await rm(rolesRoot, { recursive: true, force: true });
    await rm(dir, { recursive: true, force: true });
  }
});

/* A cycle file that is not there is refused the same way, path-first: the message OPENS with the file,
 * as every refusal above does and as `composeFace`'s `@throws` promises, not with Node's own
 * `ENOENT: no such file or directory, open '...'`, which names the path last. */
test("composeFace refuses a missing cycle file, its message opening with the path", async () => {
  const home = freshHome();
  const rolesRoot = await makeRolesRoot();
  const dir = mkdtempSync(join(tmpdir(), "face-cycle-"));
  try {
    const cyclePath = join(dir, "no-such-cycle.md");
    assert.throws(() => composeFace({ profileName: "face", port: 3090, dshHome: home, rolesRoot, cyclePath }),
      (e: Error) => e.message.startsWith(`${cyclePath}: `) && /the cycle file is missing/.test(e.message));
  } finally {
    await rm(rolesRoot, { recursive: true, force: true });
    await rm(dir, { recursive: true, force: true });
  }
});

/* Spec §4.1 L3: dsh-base's default candidates are AGENTS.md and CLAUDE.md; the
 * face sets the row's two candidate lists (the patch carries dsh-base's
 * `maxBytes` beside them, a named config replaces the row's) so Gravit reads
 * GRAVIT.md and its local twin and nothing else. Composed AFTER the operator
 * layers, like the persona patch, and guarded like it. */
test("composeFace patches agent-instructions to GRAVIT.md and GRAVIT.local.md, after the operator layers", () => {
  const home = freshHome();
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  const row = composeEntries([patches]).find((entry) => entry.id === AGENT_INSTRUCTIONS_ROW_ID);
  assert.equal(row?.name, "@deepseek-ai/dsh-agent-instructions");
  assert.deepEqual(row?.config, { maxBytes: 65536, instructionFileCandidates: ["GRAVIT.md"], localInstructionFileCandidates: ["GRAVIT.local.md"] });
  assert.deepEqual(row?.config, INSTRUCTIONS_CONFIG);
  const index = patches.findIndex((patch) => (patch as { id?: string }).id === AGENT_INSTRUCTIONS_ROW_ID);
  const persona = patches.findIndex((patch) => (patch as { id?: string }).id === "system-prompt");
  assert.ok(index > persona, "the instructions patch follows the persona patch");
  assert.equal(index, patches.length - 2, "and precedes only the face overlay");
});

/* The face owns the row's two candidate lists and nothing else. The patch
 * composes after the operator's layers and a patch replaces the row's whole
 * config, so - like the persona patch above - it spreads what the layers below
 * left and applies the lists last. A patch carrying only the face's own keys
 * would discard `projectRootMarkers` (on a checkout with no `.git` an operator's
 * fix for it is what lets a channel session read the root GRAVIT.md at all),
 * `maxSourceBytes` and `dshHome`; `disabled` was never touched, the include
 * assigns only the keys the patch carries. */
test("the instructions patch keeps the operator's other agent-instructions keys and disabled; only the two candidate lists are the face's", () => {
  const home = freshHome();
  const { patches } = composeFace({
    profileName: "face", port: 3090, dshHome: home,
    extraPatches: [{
      id: AGENT_INSTRUCTIONS_ROW_ID,
      config: { maxBytes: 1, projectRootMarkers: [".hg"], instructionFileCandidates: ["X.md"] },
      disabled: true,
    }],
  });
  const row = composeEntries([patches]).find((entry) => entry.id === AGENT_INSTRUCTIONS_ROW_ID);
  assert.deepEqual(row?.config, {
    maxBytes: 1,
    projectRootMarkers: [".hg"],
    instructionFileCandidates: ["GRAVIT.md"],
    localInstructionFileCandidates: ["GRAVIT.local.md"],
  });
  assert.equal(row?.disabled, true);
});

/* The branches composeFace does not reach with dsh-base's own `{ maxBytes }`
 * row: nothing inherited, or something that is not a plain object, and the
 * rule that the patch shares no object with its input or with its next call. */
test("instructionsPatch: an absent or non-object inherited config leaves the defaults, and nothing is shared", () => {
  for (const inherited of [undefined, null, "x", ["a"]]) {
    assert.deepEqual(instructionsPatch(inherited).config, INSTRUCTIONS_CONFIG);
  }
  const inherited = { projectRootMarkers: [".hg"] };
  const patch = instructionsPatch(inherited);
  patch.config.projectRootMarkers?.push(".git");
  patch.config.instructionFileCandidates.push("X.md");
  assert.deepEqual(inherited, { projectRootMarkers: [".hg"] }, "the caller's config is cloned, not rewritten");
  assert.deepEqual(instructionsPatch().config, { maxBytes: 65536, instructionFileCandidates: ["GRAVIT.md"], localInstructionFileCandidates: ["GRAVIT.local.md"] },
    "the next call starts from the constants - compared against literals, so an aliased constant cannot hide a leak");
});

/* Spec §9: a composition without the row gets no patch and boot says nothing.
 * An id patch that matches nothing is inert and silent, so the `rows.has(...)`
 * guard in composeFace is all that stops the face claiming "GRAVIT.md only" for
 * a row that is not there. A profile that bundles nothing composes without any
 * of dsh-base's rows (its policy warnings, on stderr, name other rows). */
test("a composition without an agent-instructions row gets no instructions patch, and boot prints nothing about it", () => {
  const home = freshHome();
  const manifestPath = join(home, "profiles", "face", "package.json");
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8")) as { dsh: { profile: { bundles: string[] } } };
  manifest.dsh.profile.bundles = [];
  writeFileSync(manifestPath, JSON.stringify(manifest));
  const printed: string[] = [];
  const stderrWrite = process.stderr.write;
  process.stderr.write = ((chunk: unknown) => { printed.push(String(chunk)); return true; }) as typeof process.stderr.write;
  try {
    const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home });
    assert.equal(patches.some((patch) => (patch as { id?: string }).id === AGENT_INSTRUCTIONS_ROW_ID), false);
    assert.equal(composeEntries([patches]).some((entry) => entry.id === AGENT_INSTRUCTIONS_ROW_ID), false);
  } finally {
    process.stderr.write = stderrWrite;
  }
  assert.ok(printed.length > 0, "the stderr hook is live: the policy layer warns about each of its missing targets");
  assert.deepEqual(printed.filter((line) => line.includes(AGENT_INSTRUCTIONS_ROW_ID) || line.includes("GRAVIT")), []);
});
