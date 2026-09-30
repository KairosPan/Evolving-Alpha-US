// face/tests/bot-presets.test.ts
/** Bots as face-declared dsh presets (PLAN S6), offline.
 *
 * `definitionFor` is pure file reading, pinned against the registry's own
 * validator (`entryListProblem`, installed). `declareBots` runs on a REAL
 * cordis Context - the fiber semantics it leans on are cordis's, not a
 * fake's - with a stand-in `agentPresets` service that keeps the registry's
 * contract where it matters: a duplicate id throws (NEW
 * packages/preset/agent-preset-registry/src/index.ts:83) and `register`
 * resolves to the async disposer the declaring fiber owns (:80-100). The real
 * registry mounting a real bot is FACE_SMOKE territory (bots-smoke.test.ts).
 */
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { Context } from "@deepseek-ai/cordis";
import { entryListProblem, type PresetDefinition } from "@deepseek-ai/dsh-agent-preset-registry";
import { declareBots, definitionFor } from "../src/bot-presets.ts";
import { BOT_PLUGIN_RELATIVE, DEFAULT_ALLOW, createBot, isBotId, renderComposition, updateSoul } from "../src/bots.ts";
import { makeBotsRoot, PLUGIN_ABS, REPO } from "./bots-fixture.ts";

const SKILLS_PLUGIN = "@deepseek-ai/dsh-skill-filesystem";
type Row = { id?: string; name?: unknown; group?: boolean; config?: Record<string, unknown> };
const rowsOf = (definition: PresetDefinition): Row[] => definition.plugins as unknown as Row[];

/** The stand-in registry service; `events` records the order of registrations. */
function fakeRegistry() {
  const live = new Map<string, PresetDefinition>();
  const events: string[] = [];
  const service = {
    async register(definition: PresetDefinition): Promise<() => Promise<void>> {
      if (!definition.id.trim()) throw new Error("Preset id must not be empty");
      if (live.has(definition.id)) throw new Error(`Duplicate agent preset: ${definition.id}`);
      live.set(definition.id, definition);
      events.push(`register ${definition.id}`);
      let disposed = false;
      return async () => {
        if (disposed) return;
        disposed = true;
        live.delete(definition.id);
        events.push(`unregister ${definition.id}`);
      };
    },
  };
  return { live, events, service };
}

/** A root context the way declareBots meets one after boot: the service provided. */
function rootWith(service?: object): Context {
  const ctx = new Context();
  if (service !== undefined) (ctx as unknown as { provide(name: string, value: unknown): () => void }).provide("agentPresets", service);
  return ctx;
}

test("definitionFor rebases the shipped relative plugin row to a file URL and ./skills onto the bot, and changes nothing else", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", description: "a test voice", soul: "You are Probe." });
  const shipped = readFileSync(join(root, "probe", "agent.cordis.yml"), "utf8");
  assert.equal(shipped, renderComposition({ soul: "You are Probe.", allow: DEFAULT_ALLOW }), "the file on disk keeps the relative form");
  assert.deepEqual(definitionFor(root, "probe"), {
    id: "probe",
    name: "Probe",
    description: "a test voice",
    plugins: [
      { id: "bot", name: pathToFileURL(resolve(root, "probe", BOT_PLUGIN_RELATIVE)).href,
        config: { persona: "You are Probe.", allow: [...DEFAULT_ALLOW] } },
      { id: "skills", name: SKILLS_PLUGIN,
        config: { customSkillDirs: [join(root, "probe", "skills")], includeDefaultRoots: false } },
    ],
  });
  assert.equal(readFileSync(join(root, "probe", "agent.cordis.yml"), "utf8"), shipped, "reading never rewrites the bot's files");
});

/* The point of the rebase, on the repository's own bots: dsh would resolve
 * `../../face/plugins/bot.js` from the profile directory under $DSH_HOME
 * (NEW packages/boot/app-boot/src/index.ts:994), where no such file exists. */
test("every shipped bot's plugin row lands on the real face/plugins/bot.js, and its skill roots on its own directory", async () => {
  const botsRoot = join(REPO, "bots");
  const ids = (await readdir(botsRoot, { withFileTypes: true }))
    .filter((entry) => entry.isDirectory() && isBotId(entry.name)).map((entry) => entry.name);
  assert.ok(ids.length > 0, "the repository ships bots");
  for (const id of ids) {
    const rows = rowsOf(definitionFor(botsRoot, id));
    const bot = rows.find((row) => row.id === "bot");
    assert.ok(bot !== undefined && typeof bot.name === "string", `${id}: a bot row`);
    assert.equal(fileURLToPath(bot.name), PLUGIN_ABS, `${id}: the plugin URL is the face's own file`);
    assert.ok(existsSync(fileURLToPath(bot.name)));
    for (const row of rows.filter((candidate) => candidate.name === SKILLS_PLUGIN)) {
      for (const dir of row.config?.customSkillDirs as string[]) {
        assert.ok(dir.startsWith(join(botsRoot, id)), `${id}: ${dir} is inside the bot's own directory`);
      }
    }
  }
  const kairos = definitionFor(botsRoot, "kairos");
  assert.deepEqual(kairos.plugins, [], "the shipped default composes nothing: Kairos keeps the host's flat roster");
  assert.equal(typeof kairos.name, "string");
});

test("the kairos definition is exactly its id, published metadata and an empty plugin list", async () => {
  const root = await makeBotsRoot();
  assert.deepEqual(definitionFor(root, "kairos"), { id: "kairos", name: "Kairos", description: "the principal agent", plugins: [] });
});

test("preset.yml is read as 0.1.1's dsh read it: trimmed, blank omitted, order kept, model never published", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "buffet", name: "Buffet", soul: "You are Buffet." });
  await writeFile(join(root, "buffet", "preset.yml"), "name: '  Buffet  '\ndescription: ''\norder: 3\nmodel: stub/echo\n");
  const definition = definitionFor(root, "buffet");
  assert.equal(definition.name, "Buffet");
  assert.equal("description" in definition, false, "'' is omitted, not published as a blank (NEW registry index.ts:158-160)");
  assert.equal(definition.order, 3);
  assert.equal("model" in definition, false, "a preset carries no route");
  await writeFile(join(root, "buffet", "preset.yml"), "name: Buffet\ndescription: '   '\norder: .inf\n");
  const blank = definitionFor(root, "buffet");
  assert.equal("description" in blank, false, "whitespace is blank");
  assert.equal("order" in blank, false, "a non-finite order is no order");
});

test("a malformed or absent preset.yml is empty metadata - the composition still declares, as in 0.1.1", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", soul: "You are Probe." });
  await writeFile(join(root, "probe", "preset.yml"), "name: [\n");
  const malformed = definitionFor(root, "probe");
  assert.deepEqual(Object.keys(malformed).sort(), ["id", "plugins"]);
  assert.equal(rowsOf(malformed).length, 2);
  await rm(join(root, "probe", "preset.yml"));
  assert.deepEqual(Object.keys(definitionFor(root, "probe")).sort(), ["id", "plugins"]);
});

test("a composition that is not a list passes through untouched, for the registry to refuse in its own words", async () => {
  const root = await makeBotsRoot();
  await mkdir(join(root, "cracked"));
  await writeFile(join(root, "cracked", "agent.cordis.yml"), "not: a list\n");
  const definition = definitionFor(root, "cracked");
  assert.deepEqual(definition.plugins, { not: "a list" });
  assert.equal(entryListProblem(definition.plugins), "the composition must be a top-level list of plugin rows");
});

test("a YAML error or a missing composition throws with the composition file's path, on one line", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", soul: "You are Probe." });
  const path = join(root, "probe", "agent.cordis.yml");
  await writeFile(path, "- id: bot\n  config: [\n");
  assert.throws(() => definitionFor(root, "probe"), (error: Error) =>
    error.message.startsWith(path) && /not valid YAML/.test(error.message) && !error.message.includes("\n"));
  await rm(path);
  assert.throws(() => definitionFor(root, "probe"), (error: Error) => error.message.startsWith(path) && /missing/.test(error.message));
});

test("rows beyond the template: absolute paths become escaped file URLs, bare names and URLs pass, !!js and non-rows are untouched, groups rebase", async () => {
  const root = await makeBotsRoot();
  await mkdir(join(root, "custom"));
  await writeFile(join(root, "custom", "agent.cordis.yml"), [
    "- id: abs",
    "  name: '/opt/plug ins/with #hash/plugin.js'",
    "- id: skills",
    `  name: '${SKILLS_PLUGIN}'`,
    "  config:",
    "    customSkillDirs: ['./skills', '../shared-skills', '/already/absolute', !!js 'dynamicRoot']",
    "- id: url",
    "  name: file:///somewhere/x.js",
    "- id: expr",
    "  name: ./dyn.js",
    "  config: !!js '({ root: \"./left-alone\" })'",
    "- id: grp",
    "  name: cordis:group",
    "  group: true",
    "  config:",
    "    - name: ./nested.js",
    "    - name: '@deepseek-ai/dsh-tool-bash'",
    "- 42",
    "",
  ].join("\n"));
  const dir = join(root, "custom");
  assert.deepEqual(definitionFor(root, "custom").plugins, [
    { id: "abs", name: pathToFileURL("/opt/plug ins/with #hash/plugin.js").href },
    { id: "skills", name: SKILLS_PLUGIN, config: { customSkillDirs: [join(dir, "skills"), resolve(dir, "../shared-skills"), "/already/absolute", { __jsExpr: "dynamicRoot" }] } },
    { id: "url", name: "file:///somewhere/x.js" },
    { id: "expr", name: pathToFileURL(join(dir, "dyn.js")).href, config: { __jsExpr: "({ root: \"./left-alone\" })" } },
    { id: "grp", name: "cordis:group", group: true, config: [{ name: pathToFileURL(join(dir, "nested.js")).href }, { name: "@deepseek-ai/dsh-tool-bash" }] },
    42,
  ]);
  assert.match(pathToFileURL("/opt/plug ins/with #hash/plugin.js").href, /%23hash/, "a '#' in a directory name is escaped, never read as a URL fragment");
});

test("declareBots declares every bot directory - never _template, never the default, never a name outside the grammar", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", soul: "You are Probe." });
  await createBot(root, { id: "other", name: "Other", soul: "You are Other." });
  await mkdir(join(root, "Skipped"));
  await writeFile(join(root, "stray-file"), "not a directory\n");
  const registry = fakeRegistry();
  const presets = await declareBots(rootWith(registry.service), root, { log: () => undefined });
  assert.deepEqual([...registry.live.keys()].sort(), ["other", "probe"]);
  assert.deepEqual(presets.ids(), ["other", "probe"]);
  assert.equal(presets.errors.size, 0);
  assert.deepEqual(registry.live.get("probe"), definitionFor(root, "probe"), "the registry receives exactly the rebased definition");
  await presets.dispose();
  assert.deepEqual([...registry.live.keys()], [], "dispose unregisters every declaration");
  assert.deepEqual(presets.ids(), []);
  await presets.dispose();
});

test("a bot the face cannot read is recorded with its path and logged, and the others still declare", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", soul: "You are Probe." });
  await mkdir(join(root, "cracked"));
  await writeFile(join(root, "cracked", "agent.cordis.yml"), "- id: bot\n  config: [\n");
  await mkdir(join(root, "not-a-list"));
  await writeFile(join(root, "not-a-list", "agent.cordis.yml"), "not: a list\n");
  const registry = fakeRegistry();
  const lines: string[] = [];
  const presets = await declareBots(rootWith(registry.service), root, { log: (line) => { lines.push(line); } });
  assert.deepEqual([...registry.live.keys()].sort(), ["not-a-list", "probe"],
    "a readable non-list IS declared: the registry, not the face, lists it broken");
  assert.match(presets.errors.get("cracked") ?? "", /agent\.cordis\.yml is not valid YAML/);
  assert.ok((presets.errors.get("cracked") ?? "").includes(join(root, "cracked", "agent.cordis.yml")));
  assert.equal(lines.length, 1);
  assert.match(lines[0], /bot "cracked" is not declared/);
  await presets.dispose();
});

test("redeclare disposes the old declaration BEFORE registering the new one, so a saved soul reaches the registry", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", soul: "v1" });
  const registry = fakeRegistry();
  const presets = await declareBots(rootWith(registry.service), root, { log: () => undefined });
  await updateSoul(root, "probe", "v2");
  await presets.redeclare("probe");
  assert.deepEqual(registry.events, ["register probe", "unregister probe", "register probe"]);
  assert.equal(rowsOf(registry.live.get("probe")!)[0].config?.persona, "v2");
  await Promise.all([presets.redeclare("probe"), presets.redeclare("probe"), presets.redeclare("probe")]);
  assert.equal(presets.errors.size, 0, "concurrent re-declarations of one bot serialize - never a duplicate id");
  assert.deepEqual(registry.events.slice(3), ["unregister probe", "register probe", "unregister probe", "register probe", "unregister probe", "register probe"]);
  await presets.dispose();
});

test("redeclare follows the disk: a new bot is declared, a newly broken one is recorded and dropped, a removed one leaves quietly", async () => {
  const root = await makeBotsRoot();
  const registry = fakeRegistry();
  const lines: string[] = [];
  const presets = await declareBots(rootWith(registry.service), root, { log: (line) => { lines.push(line); } });
  assert.deepEqual(presets.ids(), []);
  await createBot(root, { id: "late", name: "Late", soul: "You are Late." });
  await presets.redeclare("late");
  assert.deepEqual(presets.ids(), ["late"]);
  await writeFile(join(root, "late", "agent.cordis.yml"), "- [\n");
  await presets.redeclare("late");
  assert.equal(registry.live.has("late"), false, "the saved files are the truth: the old declaration does not linger");
  assert.match(presets.errors.get("late") ?? "", /not valid YAML/);
  assert.equal(lines.length, 1);
  await updateSoul(root, "late", "You are Late, repaired.");
  await presets.redeclare("late");
  assert.equal(registry.live.has("late"), true);
  assert.equal(presets.errors.has("late"), false, "a repaired bot's reason clears");
  await rm(join(root, "late"), { recursive: true, force: true });
  await presets.redeclare("late");
  assert.equal(registry.live.has("late"), false);
  assert.equal(presets.errors.has("late"), false, "a deleted bot is not broken, just gone");
  await presets.dispose();
});

test("a refused registration is recorded, and redeclare refuses non-bot ids and anything after dispose", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", soul: "You are Probe." });
  const registry = fakeRegistry();
  registry.live.set("probe", { id: "probe", plugins: [] });           // someone else already declared it
  const presets = await declareBots(rootWith(registry.service), root, { log: () => undefined });
  assert.match(presets.errors.get("probe") ?? "", /registry refused it: Duplicate agent preset: probe/);
  assert.deepEqual(presets.ids(), []);
  await assert.rejects(presets.redeclare("kairos"), /not a bot id/);
  await assert.rejects(presets.redeclare("_template"), /not a bot id/);
  await assert.rejects(presets.redeclare("../escape"), /not a bot id/);
  await presets.dispose();
  await assert.rejects(presets.redeclare("probe"), /disposed/);
});

/* Measured on cordis 4.0.4: a fiber that injects an absent service stays
 * PENDING and awaiting it RESOLVES - it would "declare" every bot and
 * register none. */
test("without the agentPresets service declareBots refuses loudly instead of declaring nothing", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", soul: "You are Probe." });
  await assert.rejects(declareBots(rootWith(), root), /agentPresets is missing/);
});

test("disposing the root context disposes the declarations with it; an absent bots root declares nothing", async () => {
  const root = await makeBotsRoot();
  await createBot(root, { id: "probe", name: "Probe", soul: "You are Probe." });
  const registry = fakeRegistry();
  const ctx = rootWith(registry.service);
  await declareBots(ctx, root, { log: () => undefined });
  assert.equal(registry.live.has("probe"), true);
  await ctx.fiber.dispose();
  assert.equal(registry.live.has("probe"), false, "they are child fibers of the root");
  const empty = await declareBots(rootWith(fakeRegistry().service), join(root, "no-such-root"));
  assert.deepEqual(empty.ids(), []);
  assert.equal(empty.errors.size, 0);
});
