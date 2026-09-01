import test from "node:test";
import assert from "node:assert/strict";
import { Readable } from "node:stream";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import {
  memoryListing, pluginListing, registerPanelRoutes, skillDetail, skillGroup,
  type PanelDeps, type SkillBody, type SkillRow,
} from "../src/panels.ts";

const CWD = "/repo";

function row(name: string, pack: string | null, extra: Partial<SkillRow> = {}): SkillRow {
  return {
    name,
    description: `${name} description`,
    invocation: { modelInvocable: true, userInvocable: true },
    source: "custom",
    ...(pack === null ? {} : { resourceBase: { kind: "directory", path: `/repo/dsh/skills/${pack}/${name}` } }),
    ...extra,
  };
}

/** A deps fake over fixed data; the loader tree mirrors the real shapes —
 * a group row, the root include, a disabled row, a failed row, the MCP row. */
function fakeDeps(): PanelDeps {
  const skills: SkillBody[] = [
    row("doctrine", "style-kairos"),
    row("backtest-rules", "mechanics"),
    row("alpaca-kit-guide", "mechanics"),
    { ...row("dsh-badge", null, { source: "bundled" }), content: "" },
  ];
  return {
    skills: {
      list: async () => skills,
      get: async (name) => {
        const hit = skills.find((skill) => skill.name === name);
        return hit === undefined ? undefined : { ...hit, content: `# ${name}\n\nbody`, path: `/x/${name}/SKILL.md` };
      },
    },
    toolSchemas: () => [
      { name: "mcp__alpaca-kit__screen", description: "Run the daily screen.\nSecond line." },
      { name: "mcp__alpaca-kit__breadth", description: "Market breadth." },
      { name: "mcp__other-server__thing", description: "not ours" },
      { name: "bash", description: "run a command" },
    ],
    loaderEntries: () => [
      { id: "include", options: { name: "cordis:include" } },
      { id: "include:group-core", options: { name: "cordis-plugin-group", group: true } },
      { id: "include:token-meter", options: { name: "@deepseek-ai/dsh-token-meter" }, fiber: { state: 2 } },
      { id: "include:hmr", options: { name: "@deepseek-ai/cordis-plugin-hmr" }, disabled: true },
      { id: "include:broken", options: { name: "@deepseek-ai/dsh-web" }, fiber: { state: 3 } },
      {
        id: "include:mcp-alpaca-kit",
        options: {
          name: "@deepseek-ai/dsh-mcp-client",
          config: { serverName: "alpaca-kit", env: { APCA_API_KEY_ID: "SECRET-KEY-VALUE" } },
        },
        fiber: { state: 2 },
      },
    ],
    cwd: CWD,
  };
}

test("skillGroup: pack directory wins, source is the fallback", () => {
  assert.equal(skillGroup(row("a", "mechanics")), "mechanics");
  assert.equal(skillGroup(row("b", "style-kairos")), "style-kairos");
  assert.equal(skillGroup(row("c", null, { source: "bundled" })), "bundled");
  assert.equal(skillGroup({ name: "d", description: "" }), "other");
});

test("memoryListing groups by pack, mechanics first, wire fields only", async () => {
  const listing = await memoryListing(fakeDeps());
  assert.deepEqual(listing.groups.map((group) => group.name), ["mechanics", "style-kairos", "bundled"]);
  const mechanics = listing.groups[0].skills as Record<string, unknown>[];
  assert.deepEqual(mechanics.map((skill) => skill.name), ["backtest-rules", "alpaca-kit-guide"]);
  assert.deepEqual(Object.keys(mechanics[0]).sort(),
    ["description", "modelInvocable", "name", "userInvocable", "whenToUse"]);
});

test("skillDetail: body through, bad name 400, unknown 404", async () => {
  const deps = fakeDeps();
  const detail = await skillDetail(deps, "doctrine") as Record<string, unknown>;
  assert.equal(detail.name, "doctrine");
  assert.equal(detail.group, "style-kairos");
  assert.match(String(detail.content), /^# doctrine/);
  await assert.rejects(skillDetail(deps, "../evil"), (err: { status?: number }) => err.status === 400);
  await assert.rejects(skillDetail(deps, "Not-Kebab"), (err: { status?: number }) => err.status === 400);
  await assert.rejects(skillDetail(deps, "absent-skill"), (err: { status?: number }) => err.status === 404);
});

test("pluginListing: rows projected, groups and root dropped, MCP paired with its tools", () => {
  const listing = pluginListing(fakeDeps());
  assert.deepEqual(listing.rows.map((entry) => entry.id), [
    "include:token-meter", "include:hmr", "include:broken", "include:mcp-alpaca-kit",
  ]);
  const byId = new Map(listing.rows.map((entry) => [entry.id, entry]));
  assert.deepEqual(byId.get("include:token-meter"), {
    id: "include:token-meter", module: "@deepseek-ai/dsh-token-meter", enabled: true, phase: "active",
  });
  assert.equal(byId.get("include:hmr")?.enabled, false);
  assert.equal(byId.get("include:hmr")?.phase, null);
  assert.equal(byId.get("include:broken")?.phase, "failed");

  assert.equal(listing.mcp.length, 1);
  assert.equal(listing.mcp[0].server, "alpaca-kit");
  assert.equal(listing.mcp[0].phase, "active");
  assert.deepEqual(listing.mcp[0].tools.map((tool) => tool.name),
    ["mcp__alpaca-kit__screen", "mcp__alpaca-kit__breadth"]);

  /* The MCP row's config holds the operator's keys; nothing but serverName
   * may survive into the payload. */
  assert.doesNotMatch(JSON.stringify(listing), /SECRET-KEY-VALUE|APCA_API_KEY_ID/);
});

/* ---------- the routes ---------- */

function fakeRes(): { out: { status: number; body: string }; res: ServerResponse } {
  const out = { status: 0, body: "" };
  const res = {
    writeHead(status: number) { out.status = status; return res; },
    end(body?: string | Buffer) { out.body = String(body ?? ""); return res; },
  };
  return { out, res: res as unknown as ServerResponse };
}

function getReq(host = "127.0.0.1:3090"): IncomingMessage {
  return { headers: { host }, method: "GET" } as unknown as IncomingMessage;
}

function postReq(body: string, host = "127.0.0.1:3090"): IncomingMessage {
  const req = Readable.from([Buffer.from(body)]) as unknown as IncomingMessage;
  (req as { headers: unknown }).headers = { host };
  (req as { method: string }).method = "POST";
  return req;
}

test("routes: register, fence, and answer", async () => {
  const routes: WebRoute[] = [];
  registerPanelRoutes({ register: (route) => routes.push(route) }, fakeDeps());
  const byPath = new Map(routes.map((r) => [r.path, r]));
  assert.deepEqual([...byPath.keys()].sort(),
    ["/data/memory.json", "/data/memory/skill", "/data/plugins.json"]);

  const memory = byPath.get("/data/memory.json")!;
  const forged = fakeRes();
  await memory.handler(getReq("evil.example.com"), forged.res);
  assert.equal(forged.out.status, 403);

  const listed = fakeRes();
  await memory.handler(getReq(), listed.res);
  assert.equal(listed.out.status, 200);
  const listing = JSON.parse(listed.out.body) as { ok: boolean; groups: { name: string }[] };
  assert.equal(listing.ok, true);
  assert.equal(listing.groups[0].name, "mechanics");

  const skill = byPath.get("/data/memory/skill")!;
  const detail = fakeRes();
  await skill.handler(postReq(JSON.stringify({ name: "doctrine" })), detail.res);
  assert.equal(detail.out.status, 200);
  assert.match(detail.out.body, /# doctrine/);
  const bad = fakeRes();
  await skill.handler(postReq("not json"), bad.res);
  assert.equal(bad.out.status, 400);
  const missing = fakeRes();
  await skill.handler(postReq(JSON.stringify({ name: "absent-skill" })), missing.res);
  assert.equal(missing.out.status, 404);
  const wrongMethod = fakeRes();
  await skill.handler(getReq(), wrongMethod.res);
  assert.equal(wrongMethod.out.status, 405);

  const plugins = byPath.get("/data/plugins.json")!;
  const answered = fakeRes();
  await plugins.handler(getReq(), answered.res);
  assert.equal(answered.out.status, 200);
  const body = JSON.parse(answered.out.body) as { ok: boolean; mcp: { server: string }[] };
  assert.equal(body.ok, true);
  assert.equal(body.mcp[0].server, "alpaca-kit");
});
