import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ROLES_ROOT, ROLE_TEMPLATE, readRoles, toolNameFor } from "../src/roles.ts";

/** A throwaway roles root with one valid role; the caller breaks it. */
async function makeRolesRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "face-roles-"));
  await mkdir(join(root, ROLE_TEMPLATE));
  await writeFile(join(root, ROLE_TEMPLATE, "ROLE.md"), "You are <role name>.\n");
  await mkdir(join(root, "probe"));
  await writeFile(join(root, "probe", "ROLE.md"), "You are the probe, a test role.\n");
  await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: a test role\nallow:\n  - read\n  - mcp__alpaca-kit__earnings\n");
  return root;
}

const FORBIDDEN = new Set(["ask_user_question", "web_search", "web_fetch", "subagent", "subagent_fork", "send_message", "interrupt_agent",
  "list_agents", "workflow", "ralph", "create_goal", "get_goal", "update_goal", "todo_write", "job_output", "job_list", "job_kill",
  "dispatch", "exit_plan_mode", "mcp__alpaca-kit__account", "mcp__alpaca-kit__positions", "mcp__alpaca-kit__orders",
  "mcp__alpaca-kit__place_order", "mcp__alpaca-kit__cancel_order"]);

test("toolNameFor: role_ plus the id with dashes as underscores", () => {
  assert.equal(toolNameFor("screener"), "role_screener");
  assert.equal(toolNameFor("data-check"), "role_data_check");
});

test("the shipped roles: three, exact names only, skill on every list, nothing forbidden, the reviewer reads only", () => {
  const roles = readRoles(ROLES_ROOT);
  assert.deepEqual(roles.map((r) => r.tool), ["role_backtester", "role_reviewer", "role_screener"]);
  for (const role of roles) {
    assert.ok(role.allow.includes("skill"), `${role.id} can load the mechanics skills`);
    assert.ok(role.description.length <= 300 && role.description.length > 0, role.id);
    for (const name of role.allow) {
      assert.equal(name.includes("*"), false, `${role.id}: ${name} is exact`);
      assert.equal(FORBIDDEN.has(name) || name.startsWith("role_") || name.startsWith("mcp__akshare__") || name.startsWith("agent_"), false, `${role.id}: ${name} is never a role's`);
    }
  }
  const reviewer = roles.find((r) => r.id === "reviewer")!;
  for (const hand of ["bash", "write", "edit", "str_replace_editor"]) assert.equal(reviewer.allow.includes(hand), false, `the reviewer has no ${hand}`);
  assert.ok(roles.find((r) => r.id === "screener")!.allow.includes("mcp__alpaca-kit__screen"));
});

test("readRoles skips _template and reads a valid role", async () => {
  const root = await makeRolesRoot();
  try {
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
