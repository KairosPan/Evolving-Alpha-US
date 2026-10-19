import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, writeFile, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { ROLES_ROOT, readRoles, toolNameFor } from "../src/roles.ts";
import { makeRolesRoot } from "./bots-fixture.ts";

const FORBIDDEN = new Set(["ask_user_question", "web_search", "web_fetch", "subagent", "subagent_fork", "send_message", "interrupt_agent",
  "list_agents", "workflow", "ralph", "create_goal", "get_goal", "update_goal", "todo_write", "run_code",
  "dispatch", "exit_plan_mode", "mcp__alpaca-kit__account", "mcp__alpaca-kit__positions", "mcp__alpaca-kit__orders",
  "mcp__alpaca-kit__place_order", "mcp__alpaca-kit__cancel_order"]);
/** The account and order tools under ANY server name, matched by their raw suffix as src/orders.ts
 *  `isOrderTool` matches the order tools: an independent copy of the reader's rule. */
const ACCOUNT_OR_ORDER = /(^|__)(account|positions|orders|place_order|cancel_order)$/;
const JOB_TOOLS = ["job_output", "job_list", "job_kill"];

test("toolNameFor: role_ plus the id with dashes as underscores", () => {
  assert.equal(toolNameFor("screener"), "role_screener");
  assert.equal(toolNameFor("data-check"), "role_data_check");
});

test("the shipped roles: three, exact names only, skill on every list, nothing forbidden, the reviewer reads only, jobs only beside bash", () => {
  const roles = readRoles(ROLES_ROOT);
  assert.deepEqual(roles.map((r) => r.tool), ["role_backtester", "role_reviewer", "role_screener"]);
  for (const role of roles) {
    assert.ok(role.allow.includes("skill"), `${role.id} can load the mechanics skills`);
    assert.ok(role.description.length <= 300 && role.description.length > 0, role.id);
    for (const name of role.allow) {
      assert.equal(name.includes("*"), false, `${role.id}: ${name} is exact`);
      assert.equal(FORBIDDEN.has(name) || ACCOUNT_OR_ORDER.test(name) || name.startsWith("role_") || name.startsWith("mcp__akshare__") || name.startsWith("agent_"), false, `${role.id}: ${name} is never a role's`);
    }
    /* A bash command past the executor's default moves to a background job the child owns; the job tools
     * are how it reads and stops one, and they mean nothing to a role that cannot start a command. */
    if (JOB_TOOLS.some((job) => role.allow.includes(job))) assert.ok(role.allow.includes("bash"), `${role.id}: a job tool only beside bash`);
  }
  const reviewer = roles.find((r) => r.id === "reviewer")!;
  for (const hand of ["bash", "write", "edit", "str_replace_editor"]) assert.equal(reviewer.allow.includes(hand), false, `the reviewer has no ${hand}`);
  assert.ok(roles.find((r) => r.id === "screener")!.allow.includes("mcp__alpaca-kit__screen"));
  for (const id of ["screener", "backtester"]) {
    const role = roles.find((r) => r.id === id)!;
    assert.ok(role.allow.includes("bash"), `${id} runs commands`);
    for (const job of JOB_TOOLS) assert.ok(role.allow.includes(job), `${id} can read and stop its own background job: ${job}`);
  }
});

test("readRoles skips _template, hidden entries and plain files, and reads a valid role", async () => {
  const root = await makeRolesRoot();
  try {
    await mkdir(join(root, ".drafts"));
    await writeFile(join(root, "NOTES.md"), "not a role\n");
    const roles = readRoles(root);
    assert.deepEqual(roles.map((r) => r.id), ["probe"]);
    assert.deepEqual(roles[0], { id: "probe", tool: "role_probe", name: "Probe", description: "a test role", persona: "You are the probe, a test role.", allow: ["read", "mcp__alpaca-kit__earnings"] });
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("readRoles refuses, naming the file: braces, an empty persona, a wildcard, an empty allow list, a bad model, a missing root", async () => {
  const root = await makeRolesRoot();
  try {
    await writeFile(join(root, "probe", "ROLE.md"), "You are {{nobody}}.\n");
    assert.throws(() => readRoles(root), (e: Error) => e.message.startsWith(join(root, "probe", "ROLE.md")) && /\{\{/.test(e.message));
    await writeFile(join(root, "probe", "ROLE.md"), "\n");
    assert.throws(() => readRoles(root), /ROLE\.md.*empty/);
    await writeFile(join(root, "probe", "ROLE.md"), "You are the probe.\n");
    await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: x\nallow: [mcp__*__screen]\n");
    assert.throws(() => readRoles(root), /role\.yml.*wildcards are not accepted; name the exact tool, e\.g\. mcp__alpaca-kit__screen/);
    await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: x\nallow: []\n");
    assert.throws(() => readRoles(root), /allow/);
    await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: x\nallow: [read]\nmodel: nope\n");
    assert.throws(() => readRoles(root), /model/);
  } finally { await rm(root, { recursive: true, force: true }); }
  assert.throws(() => readRoles(join(tmpdir(), "no-such-roles-root")), /missing/);
});

import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { GRAVIT_PLUGIN_URL, GRAVIT_ROW_ID, gravitRows, renderGravitComposition, roleRowId } from "../src/roles.ts";
import { GRAVIT_PLUGIN_RELATIVE } from "../src/overlay.ts";
import { CYCLE_PATH, readCycle } from "../src/cycle.ts";

test("gravitRows: the gravit row carries the summaries; one one-shot spawn row per role with persona and an exact allow list", () => {
  const roles = readRoles(ROLES_ROOT);
  const rows = gravitRows(roles, { plugin: GRAVIT_PLUGIN_URL }) as Array<{ id: string; name: string; config: Record<string, unknown> }>;
  assert.equal(rows[0].id, GRAVIT_ROW_ID);
  assert.equal(rows[0].name, GRAVIT_PLUGIN_URL);
  assert.ok(GRAVIT_PLUGIN_URL.startsWith("file:") && GRAVIT_PLUGIN_URL.endsWith("/face/plugins/gravit.js"));
  assert.deepEqual(rows[0].config, { roles: roles.map((r) => ({ tool: r.tool, summary: r.description })) });
  assert.equal(rows.length, 1 + roles.length);
  for (const role of roles) {
    const row = rows.find((r) => r.id === roleRowId(role.id))!;
    assert.equal(row.name, "@deepseek-ai/dsh-tool-subagent");
    assert.deepEqual(Object.keys(row.config).sort(), ["backgroundMode", "persona", "provider", "toolFilter", "toolName"]);
    assert.deepEqual(row.config, { provider: "spawn", toolName: role.tool, backgroundMode: "one-shot", persona: role.persona, toolFilter: { allow: role.allow } });
  }
});

test("gravitRows: a role.yml model becomes the row's agentOptions, provider and model split; without one the key is absent", async () => {
  const root = await makeRolesRoot();
  try {
    const rowOf = () => (gravitRows(readRoles(root), { plugin: GRAVIT_PLUGIN_URL }) as Array<{ id: string; config: Record<string, unknown> }>)
      .find((r) => r.id === roleRowId("probe"))!;
    assert.equal("agentOptions" in rowOf().config, false, "a role.yml with no model has no agentOptions");
    await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: a test role\nallow:\n  - read\nmodel: deepseek-official/deepseek-v4-flash\n");
    const row = rowOf();
    assert.deepEqual(row.config.agentOptions, { provider: "deepseek-official", model: "deepseek-v4-flash" });
    assert.deepEqual(Object.keys(row.config).sort(), ["agentOptions", "backgroundMode", "persona", "provider", "toolFilter", "toolName"]);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("the committed mirror bots/gravit/agent.cordis.yml is exactly the render of roles/ (drift fails here)", () => {
  const mirror = readFileSync(new URL("../../bots/gravit/agent.cordis.yml", import.meta.url), "utf8");
  assert.equal(mirror, renderGravitComposition(readRoles(ROLES_ROOT), { cycle: readCycle(CYCLE_PATH) }), "run: cd face && npm run render:roles");
  assert.ok(mirror.includes(`name: ${GRAVIT_PLUGIN_RELATIVE}`), "the mirror names the plugin by the shipped relative path");
  assert.equal(mirror.includes("file:"), false, "and never by a machine-specific URL");
});

/* The refusals the tests above do not reach. A refusal is ONE line that opens with the
 * absolute path of the file (or directory) it is about, so the boot log points at the place
 * to fix. `files` edits the fresh root from makeRolesRoot (null removes a file); `links` adds
 * a symbolic link at a path, pointing at a target, both relative to that root; `read` is
 * what readRoles is given, relative to that root. */
const LONG_ID = "a".repeat(60);
const REFUSED: Array<{ label: string; files: Record<string, string | null>; links?: Record<string, string>; read?: string; path: string; reason: RegExp }> = [
  { label: "role.yml missing", files: { "probe/role.yml": null }, path: "probe/role.yml", reason: /missing/ },
  { label: "ROLE.md missing", files: { "probe/ROLE.md": null }, path: "probe/ROLE.md", reason: /missing/ },
  { label: "ROLE.md of 2,001 bytes", files: { "probe/ROLE.md": "x".repeat(2001) }, path: "probe/ROLE.md", reason: /is 2001 bytes; the limit is 2000/ },
  { label: "role.yml that is not YAML", files: { "probe/role.yml": "name: [\n" }, path: "probe/role.yml", reason: /is not valid YAML/ },
  { label: "role.yml that is a list", files: { "probe/role.yml": "- name: Probe\n" }, path: "probe/role.yml", reason: /must be a mapping/ },
  { label: "role.yml that is a scalar", files: { "probe/role.yml": "just text\n" }, path: "probe/role.yml", reason: /must be a mapping/ },
  { label: "role.yml that is empty", files: { "probe/role.yml": "" }, path: "probe/role.yml", reason: /must be a mapping/ },
  { label: "a blank name", files: { "probe/role.yml": "name: '  '\ndescription: x\nallow: [read]\n" }, path: "probe/role.yml", reason: /name is missing or blank/ },
  { label: "a blank description", files: { "probe/role.yml": "name: Probe\ndescription: '  '\nallow: [read]\n" }, path: "probe/role.yml", reason: /description is missing or blank/ },
  { label: "a description of 301 characters", files: { "probe/role.yml": `name: Probe\ndescription: ${"d".repeat(301)}\nallow: [read]\n` }, path: "probe/role.yml", reason: /description is 301 characters; the limit is 300/ },
  { label: "a description on two lines", files: { "probe/role.yml": "name: Probe\ndescription: |\n  first line\n  second line\nallow: [read]\n" }, path: "probe/role.yml", reason: /description must be one line/ },
  { label: "an allow entry that is not a string", files: { "probe/role.yml": "name: Probe\ndescription: x\nallow: [read, 5]\n" }, path: "probe/role.yml", reason: /allow entry 2 is not a string/ },
  { label: "an allow entry outside the tool-name grammar", files: { "probe/role.yml": "name: Probe\ndescription: x\nallow: ['a b']\n" }, path: "probe/role.yml", reason: /allow entry "a b" is not a tool name/ },
  { label: "an allow entry no role carries", files: { "probe/role.yml": "name: Probe\ndescription: x\nallow: [read, ask_user_question]\n" }, path: "probe/role.yml", reason: /allow entry "ask_user_question": a role never carries/ },
  { label: "an allow entry listed twice", files: { "probe/role.yml": "name: Probe\ndescription: x\nallow: [read, grep, read]\n" }, path: "probe/role.yml", reason: /allow entry "read" is listed twice/ },
  { label: "a role directory whose name is not an id", files: { "Probe_Two/ROLE.md": "You are two.\n", "Probe_Two/role.yml": "name: Two\ndescription: x\nallow: [read]\n" }, path: "Probe_Two", reason: /is not a role id/ },
  { label: "a role directory that is a symbolic link", files: {}, links: { linked: "probe" }, path: "linked", reason: /is a symbolic link/ },
  { label: "a model that is not a string", files: { "probe/role.yml": "name: Probe\ndescription: x\nallow: [read]\nmodel: 5\n" }, path: "probe/role.yml", reason: /model must be a <provider>\/<model> route.*\(got a non-string\)/ },
  { label: "a tool name over 64 characters", files: { [`${LONG_ID}/ROLE.md`]: "You are long.\n", [`${LONG_ID}/role.yml`]: "name: Long\ndescription: x\nallow: [read]\n" }, path: LONG_ID, reason: /role_a{60} is 65 characters; the limit is 64/ },
  { label: "a roles root that is a file", files: { "a-file": "not a directory\n" }, read: "a-file", path: "a-file", reason: /is not a directory/ },
  { label: "a roles root that is missing", files: {}, read: "no-such-dir", path: "no-such-dir", reason: /the roles directory is missing/ },
];

test("readRoles refuses every other malformed shape in one line that opens with the path it is about", async () => {
  for (const { label, files, links = {}, read = "", path, reason } of REFUSED) {
    const root = await makeRolesRoot();
    try {
      for (const [file, body] of Object.entries(files)) {
        const target = join(root, file);
        if (body === null) await rm(target);
        else {
          await mkdir(dirname(target), { recursive: true });
          await writeFile(target, body);
        }
      }
      for (const [link, target] of Object.entries(links)) await symlink(join(root, target), join(root, link));
      assert.throws(() => readRoles(join(root, read)), (e: Error) => {
        assert.ok(e.message.startsWith(`${join(root, path)}: `), `${label}: opens with the path it is about, got: ${e.message}`);
        assert.match(e.message, reason, label);
        assert.equal(e.message.includes("\n"), false, `${label}: one line`);
        return true;
      }, label);
    } finally { await rm(root, { recursive: true, force: true }); }
  }
});

/* The account and order names are refused under any server name, the way Gate 2 matches the order
 * tools by raw suffix (src/orders.ts `isOrderTool`): a server mounted as `broker` cannot slip them in. */
const RENAMED_SERVER = ["account", "positions", "orders", "place_order", "cancel_order"].map((raw) => `mcp__broker__${raw}`);

test("readRoles refuses every tool a role never carries, naming role.yml and why", async () => {
  const root = await makeRolesRoot();
  try {
    for (const entry of [...FORBIDDEN, ...RENAMED_SERVER, "role_screener", "agent_codex", "mcp__akshare__stock_zh_a_hist"]) {
      await writeFile(join(root, "probe", "role.yml"), `name: Probe\ndescription: x\nallow:\n  - read\n  - ${entry}\n`);
      assert.throws(() => readRoles(root), (e: Error) =>
        e.message.startsWith(`${join(root, "probe", "role.yml")}: allow entry ${JSON.stringify(entry)}: a role never carries `), entry);
    }
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("the limits are inclusive: 2,000 bytes of persona, 300 characters of description and a 64-character tool name are read", async () => {
  const root = await makeRolesRoot();
  try {
    const id = "b".repeat(59);
    await mkdir(join(root, id));
    await writeFile(join(root, id, "ROLE.md"), "y".repeat(2000));
    await writeFile(join(root, id, "role.yml"), `name: Edge\ndescription: ${"d".repeat(300)}\nallow: [read]\n`);
    const edge = readRoles(root).find((r) => r.id === id)!;
    assert.deepEqual([edge.tool.length, edge.persona.length, edge.description.length], [64, 2000, 300]);
  } finally { await rm(root, { recursive: true, force: true }); }
});
