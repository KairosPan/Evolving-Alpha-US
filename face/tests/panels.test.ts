import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import {
  agentsListing, authFromProbe, connectLocalAgent, defaultAgentProber, defaultAuthProber,
  disconnectLocalAgent, hasExec, isAgentBin, memoryListing, parseClaudeRun, parseCodexRun, pluginListing,
  readAgentsMeta, registerPanelRoutes, scrubbedEnv, skillDetail, skillGroup,
  syncAgentTools, toolNameFor,
  type AgentToolDefinition, type AgentToolRegistry, type PanelDeps, type SkillBody, type SkillRow,
} from "../src/panels.ts";
import { DSH_PIN } from "../src/version.ts";

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
 * a group row, the root include, a disabled row, a failed row, the MCP row.
 * @param home - a real directory only for tests that touch the roster file. */
function fakeDeps(home = "/face-panels-nowhere"): PanelDeps {
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
      { name: "agent_claude", description: "Ask the operator's locally installed Claude Code…" },
      { name: "bash", description: "run a command" },
    ],
    registerTool: () => () => {},
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
    home,
    /* no channel by default — the roster check (agents.test.ts) is the one
     * place that cares; every other test here exercises code the roster
     * check never gates, so "no channel" (fail open) is the right default. */
    channelFor: async () => null,
    /* claude answers, gemini answers (installed, no exec recipe), zed answers
     * (installed, not on the known list), hermes throws (a prober crash reads
     * as absent), the rest are not installed. */
    probeAgent: async (bin) => {
      if (bin === "claude") return "2.1.251 (Claude Code)";
      if (bin === "gemini") return "gemini 0.9.0";
      if (bin === "zed") return "zed 0.200.0";
      if (bin === "hermes") throw new Error("spawn blew up");
      return null;
    },
    /* claude is signed in; every other auth probe CRASHES — which must fold
     * to "unknown", never fail a connect or a listing. */
    probeAuth: async (bin) => {
      if (bin === "claude") return { state: "ok", detail: "claude.ai", account: "op@example.com" };
      throw new Error("auth probe blew up");
    },
    /* no run should ever reach the default fake; tests that run inject a recorder */
    runAgent: async () => { throw new Error("runAgent not injected"); },
  };
}

/** A roster home of its own per test. */
const freshHome = (): Promise<string> => mkdtemp(join(tmpdir(), "face-agents-"));

/* ====================================================================== */
/* detection: names, probes, candidates, hide/show, refresh                */
/* ====================================================================== */

test("isAgentBin: one bare PATH token, nothing that could be a path or a flag", () => {
  for (const good of ["claude", "codex", "cursor-agent", "a.b", "x+y", "Z9", "a".repeat(64)]) {
    assert.equal(isAgentBin(good), true, good);
  }
  for (const bad of ["", " ", "../evil", "a/b", "a\\b", "a b", "-x", ".hidden", "a".repeat(65), 42, null, undefined, ["claude"]]) {
    assert.equal(isAgentBin(bad), false, String(bad));
  }
});

test("toolNameFor: agent_<bin>, with characters a tool name cannot carry folded", () => {
  assert.equal(toolNameFor("claude"), "agent_claude");
  assert.equal(toolNameFor("cursor-agent"), "agent_cursor-agent");
  assert.equal(toolNameFor("a.b+c"), "agent_a_b_c");
});

test("defaultAgentProber: a real binary answers with its first line; absence and silence read as null", async () => {
  const probe = defaultAgentProber();
  const node = await probe("node");
  assert.match(node ?? "", /^v\d+\./, "node --version's first line");
  assert.equal(await probe("no-such-binary-face-test-9f3a"), null, "ENOENT");
  assert.equal(await probe("true"), null, "exits 0 with no output — nothing to show");
});

test("defaultAuthProber: no status recipe means unknown without spawning anything", async () => {
  assert.deepEqual(await defaultAuthProber()("node"), { state: "unknown" });
});

test("authFromProbe folds each CLI's real status output", () => {
  // Real shapes captured 2026-09-01 on this machine.
  assert.deepEqual(
    authFromProbe("claude", { code: 0, stdout: '{"loggedIn":true,"authMethod":"claude.ai","apiProvider":"firstParty","email":"op@example.com"}' }),
    { state: "ok", detail: "claude.ai", account: "op@example.com" });
  assert.deepEqual(authFromProbe("claude", { code: 0, stdout: '{"loggedIn":false}' }), { state: "none" });
  assert.deepEqual(authFromProbe("claude", { code: 1, stdout: "boom" }), { state: "unknown" });
  assert.deepEqual(
    authFromProbe("codex", { code: 0, stdout: "Logged in using ChatGPT\n" }),
    { state: "ok", detail: "Logged in using ChatGPT" });
  assert.deepEqual(authFromProbe("codex", { code: 1, stdout: "Not logged in\n" }), { state: "none" });
  assert.deepEqual(
    authFromProbe("hermes", { code: 0, stdout: "◆ Environment\n  Model:  x\n  Provider:     DeepSeek\n" }),
    { state: "ok", detail: "provider DeepSeek" });
  assert.deepEqual(authFromProbe("gemini", { code: 0, stdout: "whatever" }), { state: "unknown" });
  assert.deepEqual(authFromProbe("claude", null), { state: "unknown" });
});

test("detection: candidates are the known list, in its order, that answer and are neither connected nor hidden", async () => {
  const deps = fakeDeps(await freshHome());
  const probed: string[] = [];
  deps.probeAgent = async (bin) => {
    probed.push(bin);
    if (bin === "claude") return "2.1.251 (Claude Code)";
    if (bin === "gemini") return "gemini 0.9.0";
    if (bin === "auggie") return "auggie 1.2.3";
    if (bin === "hermes") throw new Error("spawn blew up");
    return null;
  };
  const listing = await agentsListing(deps);
  assert.deepEqual(listing.main, { name: "Kairos", runtime: `dsh ${DSH_PIN}` });
  assert.deepEqual(listing.local, [], "nothing is fixed in place — the roster starts empty");
  assert.deepEqual(listing.candidates, [
    { bin: "claude", label: "Claude Code", version: "2.1.251 (Claude Code)" },
    { bin: "gemini", label: "Gemini CLI", version: "gemini 0.9.0" },
    { bin: "auggie", label: "Auggie", version: "auggie 1.2.3" },
  ], "known-list order, absent and crashing probes dropped");
  assert.equal(probed.length, 15, "every known name probed exactly once");
  assert.ok(!probed.includes("zed"), "an unknown-but-installed binary is never probed for detection");
});

test("detection: a disconnected agent is a candidate again", async () => {
  const deps = fakeDeps(await freshHome());
  await connectLocalAgent(deps, "claude");
  assert.deepEqual((await agentsListing(deps)).candidates.map((c) => c.bin), ["gemini"]);
  await disconnectLocalAgent(deps, "claude");
  assert.deepEqual((await agentsListing(deps)).candidates.map((c) => c.bin), ["claude", "gemini"], "back in known-list order");
});

test("roster: connect is a verifying handshake, disconnect removes, both refuse malformed names", async () => {
  const deps = fakeDeps(await freshHome());
  const row = await connectLocalAgent(deps, "claude");
  assert.deepEqual(row, {
    bin: "claude", label: "Claude Code", found: true, version: "2.1.251 (Claude Code)",
    auth: { state: "ok", detail: "claude.ai", account: "op@example.com" }, tool: "agent_claude",
  });
  await connectLocalAgent(deps, "claude"); // idempotent, not a duplicate
  const listing = await agentsListing(deps);
  assert.deepEqual(listing.local, [row]);
  assert.deepEqual(listing.candidates.map((c) => c.bin), ["gemini"], "a connected agent leaves the candidate pool");

  const zed = await connectLocalAgent(deps, "zed");
  assert.equal(zed.label, "zed", "an unknown binary's label is its own name");
  assert.equal(zed.tool, undefined, "no recipe → not callable");
  assert.deepEqual(zed.auth, { state: "unknown" }, "a crashing auth probe reads as unknown");

  // Refusals: a malformed name never reaches the prober; silence is a 404.
  await assert.rejects(connectLocalAgent(deps, "../evil"), (err: { status?: number }) => err.status === 400);
  await assert.rejects(connectLocalAgent(deps, "a/b"), (err: { status?: number }) => err.status === 400);
  await assert.rejects(connectLocalAgent(deps, "openclaw"), (err: { status?: number }) => err.status === 404);
  await assert.rejects(connectLocalAgent(deps, "hermes"), (err: { status?: number }) => err.status === 404);

  assert.deepEqual((await disconnectLocalAgent(deps, "claude")).connected.map((c) => c.bin), ["zed"]);
  await assert.rejects(disconnectLocalAgent(deps, "claude"), (err: { status?: number }) => err.status === 404);
  await assert.rejects(disconnectLocalAgent(deps, "bad/name"), (err: { status?: number }) => err.status === 400);
});

test("roster file: a hand-mangled or legacy file reads as best it can", async () => {
  const home = await freshHome();
  await mkdir(join(home, "face"), { recursive: true });
  await writeFile(join(home, "face", "agents.json"), JSON.stringify({
    connected: [{ bin: "claude" }, { bin: "../evil", label: "x" }, "junk", { label: "nobin" }, { bin: "claude", label: "dup" }],
    ignored: ["a stray field from a retracted feature is simply not read"],
  }));
  assert.deepEqual(await readAgentsMeta(home), { connected: [{ bin: "claude", label: "claude" }] });
  await writeFile(join(home, "face", "agents.json"), "not json");
  assert.deepEqual(await readAgentsMeta(home), { connected: [] });
});

/* ====================================================================== */
/* the recipes and the runner seams                                        */
/* ====================================================================== */

test("scrubbedEnv drops credential overrides, endpoint redirects and workbench secrets; keeps the operator's own sign-in", () => {
  assert.deepEqual(
    scrubbedEnv({
      PATH: "/bin", HOME: "/h", CLAUDE_CODE_OAUTH_TOKEN: "keep", CLAUDE_CONFIG_DIR: "/c", CODEX_HOME: "/x",
      ANTHROPIC_API_KEY: "a", ANTHROPIC_AUTH_TOKEN: "t", ANTHROPIC_BASE_URL: "u", ANTHROPIC_CUSTOM_HEADERS: "h",
      OPENAI_API_KEY: "o", CODEX_API_KEY: "c", OPENAI_BASE_URL: "ou",
      CLAUDE_CODE_USE_BEDROCK: "1", CLAUDE_CODE_USE_VERTEX: "1", CLAUDE_CODE_USE_FOUNDRY: "1",
      APCA_API_KEY_ID: "k", APCA_API_SECRET_KEY: "s", DEEPSEEK_API_KEY: "d",
    }),
    { PATH: "/bin", HOME: "/h", CLAUDE_CODE_OAUTH_TOKEN: "keep", CLAUDE_CONFIG_DIR: "/c", CODEX_HOME: "/x" });
});

test("parseClaudeRun / parseCodexRun fold the documented shapes and degrade to raw text", () => {
  assert.deepEqual(
    parseClaudeRun('{"type":"result","subtype":"success","is_error":false,"duration_ms":4200,"num_turns":1,"result":"**ok**","session_id":"11111111-2222-4333-8444-555555555555","total_cost_usd":0.0123}'),
    { text: "**ok**", session: "11111111-2222-4333-8444-555555555555", isError: false, cost: 0.0123, turns: 1 });
  assert.deepEqual(parseClaudeRun("not json at all"), { text: "not json at all", isError: false });
  assert.equal(parseClaudeRun('{"type":"result","is_error":true,"result":"boom"}').isError, true);
  // The error variant carries no `result` — its cause must still reach the caller.
  const failed = parseClaudeRun('{"type":"result","subtype":"error_during_execution","is_error":true,"errors":["boom"],"num_turns":2,"session_id":"11111111-2222-4333-8444-555555555555","total_cost_usd":0.01}');
  assert.equal(failed.text, "boom");
  assert.equal(failed.isError, true);
  assert.equal(failed.turns, 2);

  const events = [
    '{"type":"thread.started","thread_id":"aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}',
    "some non-json noise line",
    '{"type":"item.completed","item":{"type":"agent_message","text":"from the events"}}',
    '{"type":"turn.completed","usage":{"input_tokens":10}}',
  ].join("\n");
  assert.deepEqual(parseCodexRun(events, "from the file\n"),
    { text: "from the file", session: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", isError: false });
  assert.equal(parseCodexRun(events, undefined).text, "from the events", "no scratch file → the events' message");
  assert.deepEqual(parseCodexRun("", undefined), { text: "", session: undefined, isError: false });
});

/* ====================================================================== */
/* connected ⇒ callable: the agent tools                                   */
/* ====================================================================== */

/** A tool registry fake: records definitions, counts disposals. */
function fakeRegistry(): { defs: Map<string, AgentToolDefinition>; disposed: string[]; registerTool: PanelDeps["registerTool"] } {
  const defs = new Map<string, AgentToolDefinition>();
  const disposed: string[] = [];
  return {
    defs, disposed,
    registerTool: (def) => {
      if (defs.has(def.name)) throw new Error(`duplicate tool ${def.name}`);
      defs.set(def.name, def);
      return () => { defs.delete(def.name); disposed.push(def.name); };
    },
  };
}

test("syncAgentTools: registered tools follow the roster — at boot, on connect, on disconnect; no recipe, no tool", async () => {
  const home = await freshHome();
  const reg = fakeRegistry();
  const deps: PanelDeps = { ...fakeDeps(home), registerTool: reg.registerTool };
  const registry: AgentToolRegistry = new Map();

  assert.deepEqual(await syncAgentTools(deps, registry), { added: [], removed: [] });
  await connectLocalAgent(deps, "claude");
  await connectLocalAgent(deps, "gemini"); // installed, no recipe
  assert.deepEqual(await syncAgentTools(deps, registry), { added: ["claude"], removed: [] });
  assert.deepEqual([...reg.defs.keys()], ["agent_claude"], "gemini has no recipe and gets no tool");
  assert.deepEqual(await syncAgentTools(deps, registry), { added: [], removed: [] }, "idempotent");

  await disconnectLocalAgent(deps, "claude");
  assert.deepEqual(await syncAgentTools(deps, registry), { added: [], removed: ["claude"] });
  assert.deepEqual(reg.disposed, ["agent_claude"], "the exact disposer ran");
  assert.equal(reg.defs.size, 0);

  /* a fresh process over an existing roster registers at boot */
  await connectLocalAgent(deps, "claude");
  const boot: AgentToolRegistry = new Map();
  assert.deepEqual(await syncAgentTools(deps, boot), { added: ["claude"], removed: [] });
  assert.equal(hasExec("claude") && hasExec("codex") && !hasExec("gemini") && !hasExec("constructor"), true);
});

/* ====================================================================== */
/* memory and plugin listings                                              */
/* ====================================================================== */

test("skillGroup: pack directory wins, source is the fallback", () => {
  assert.equal(skillGroup(row("a", "mechanics")), "mechanics");
  assert.equal(skillGroup(row("b", "style-kairos")), "style-kairos");
  assert.equal(skillGroup(row("c", null, { source: "bundled" })), "bundled");
  assert.equal(skillGroup({ name: "d", description: "" }), "other");
});

test("memoryListing groups by pack, mechanics first, wire fields only", async () => {
  const listing = await memoryListing(fakeDeps());
  assert.deepEqual(listing.groups.map((group) => group.name), ["mechanics", "style-kairos", "bundled"]);
  const mechanics = listing.groups[0]!.skills as Record<string, unknown>[];
  assert.deepEqual(mechanics.map((skill) => skill.name), ["backtest-rules", "alpaca-kit-guide"]);
  assert.deepEqual(Object.keys(mechanics[0]!).sort(),
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

test("pluginListing: rows projected, groups and root dropped, MCP paired with its tools, agent tools listed", () => {
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
  assert.equal(listing.mcp[0]!.server, "alpaca-kit");
  assert.equal(listing.mcp[0]!.phase, "active");
  assert.deepEqual(listing.mcp[0]!.tools.map((tool) => tool.name),
    ["mcp__alpaca-kit__screen", "mcp__alpaca-kit__breadth"]);
  assert.deepEqual(listing.agentTools.map((tool) => tool.name), ["agent_claude"]);

  /* The MCP row's config holds the operator's keys; nothing but serverName
   * may survive into the payload. */
  assert.doesNotMatch(JSON.stringify(listing), /SECRET-KEY-VALUE|APCA_API_KEY_ID/);
});

/* ====================================================================== */
/* the routes                                                              */
/* ====================================================================== */

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

/** A POST as the face's own client sends it: JSON content-type, loopback
 * Host, no Origin (which is how curl and older same-origin browsers arrive).
 * `headers` overrides or adds — the fence tests forge Origin / Fetch-Metadata
 * / content-type through it. */
function postReq(body: string, host = "127.0.0.1:3090", headers: Record<string, string> = {}): IncomingMessage {
  const req = Readable.from([Buffer.from(body)]) as unknown as IncomingMessage;
  (req as { headers: unknown }).headers = { host, "content-type": "application/json", ...headers };
  (req as { method: string }).method = "POST";
  return req;
}

test("routes: register, boot-sync, fence, and the roster round-trip with its tools", async () => {
  const home = await freshHome();
  await mkdir(join(home, "face"), { recursive: true });
  await writeFile(join(home, "face", "agents.json"), JSON.stringify({ connected: [{ bin: "codex", label: "Codex" }] }));
  const reg = fakeRegistry();
  const probes: string[] = [];
  const base = fakeDeps(home);
  const deps: PanelDeps = {
    ...base,
    registerTool: reg.registerTool,
    probeAgent: async (bin) => { probes.push(bin); return base.probeAgent(bin); },
  };
  const routes: WebRoute[] = [];
  await registerPanelRoutes({ register: (route) => routes.push(route) }, deps);
  const byPath = new Map(routes.map((r) => [r.path, r]));
  assert.deepEqual([...byPath.keys()].sort(), [
    "/data/agents.json", "/data/agents/connect", "/data/agents/disconnect", "/data/agents/rescan",
    "/data/memory.json", "/data/memory/skill", "/data/plugins.json",
  ]);
  assert.deepEqual([...reg.defs.keys()], ["agent_codex"], "an agent already on the roster is callable from boot");

  /* the browser fence and the media-type gate, on a side-effectful route */
  const connect = byPath.get("/data/agents/connect")!;
  const task = JSON.stringify({ bin: "claude" });
  const cases: [IncomingMessage, number, string][] = [
    [postReq(task, "evil.example.com"), 403, "forged Host"],
    [postReq(task, "127.0.0.1:3090", { origin: "http://evil.example.com" }), 403, "cross-origin page, loopback Host"],
    [postReq(task, "127.0.0.1:3090", { "sec-fetch-site": "cross-site" }), 403, "Fetch-Metadata cross-site"],
    [postReq(task, "127.0.0.1:3090", { "content-type": "text/plain" }), 415, "a no-preflight simple POST"],
    [getReq(), 405, "GET"],
  ];
  for (const [req, status, label] of cases) {
    const out = fakeRes();
    await connect.handler(req, out.res);
    assert.equal(out.out.status, status, label);
  }
  assert.deepEqual([...reg.defs.keys()], ["agent_codex"], "no refused request changed anything");

  /* connect → listed, tool registered; the probe cache answers the listing without re-probing */
  const made = fakeRes();
  await connect.handler(postReq(task, "127.0.0.1:3090", { origin: "http://127.0.0.1:3090" }), made.res);
  assert.equal(made.out.status, 200, "the face's own page: same-origin, JSON");
  assert.equal((JSON.parse(made.out.body) as { agent: { tool: string } }).agent.tool, "agent_claude");
  assert.deepEqual([...reg.defs.keys()].sort(), ["agent_claude", "agent_codex"]);
  const refused = fakeRes();
  await connect.handler(postReq(JSON.stringify({ bin: "openclaw" })), refused.res);
  assert.equal(refused.out.status, 404);

  const agents = byPath.get("/data/agents.json")!;
  const before = probes.length;
  const roster = fakeRes();
  await agents.handler(getReq(), roster.res);
  assert.equal(roster.out.status, 200);
  const listing = JSON.parse(roster.out.body) as { ok: boolean; local: { bin: string; found: boolean }[]; candidates: { bin: string }[] };
  assert.equal(listing.ok, true);
  assert.deepEqual(listing.local.map((a) => [a.bin, a.found]), [["codex", false], ["claude", true]], "codex is on the roster but not installed here");
  assert.deepEqual(listing.candidates.map((c) => c.bin), ["gemini"]);
  const afterFirst = probes.length;
  assert.ok(afterFirst > before, "the first listing probes");
  await agents.handler(getReq(), fakeRes().res);
  assert.equal(probes.length, afterFirst, "a second listing inside the minute probes nothing");

  /* the refresh forgets the cache and re-probes */
  const rescan = byPath.get("/data/agents/rescan")!;
  const fresh = fakeRes();
  await rescan.handler(postReq("{}"), fresh.res);
  assert.equal(fresh.out.status, 200);
  assert.ok(probes.length > afterFirst, "refresh re-probes");
  assert.deepEqual((JSON.parse(fresh.out.body) as { candidates: { bin: string }[] }).candidates.map((c) => c.bin), ["gemini"]);

  /* disconnect → tool disposed */
  const disconnect = byPath.get("/data/agents/disconnect")!;
  const dropped = fakeRes();
  await disconnect.handler(postReq(JSON.stringify({ bin: "claude" })), dropped.res);
  assert.equal(dropped.out.status, 200);
  assert.deepEqual(reg.disposed, ["agent_claude"]);
  assert.deepEqual([...reg.defs.keys()], ["agent_codex"]);

  /* the memory routes, unchanged */
  const memory = byPath.get("/data/memory.json")!;
  const forged = fakeRes();
  await memory.handler(getReq("evil.example.com"), forged.res);
  assert.equal(forged.out.status, 403);
  const listed = fakeRes();
  await memory.handler(getReq(), listed.res);
  assert.equal((JSON.parse(listed.out.body) as { groups: { name: string }[] }).groups[0]!.name, "mechanics");
  const skill = byPath.get("/data/memory/skill")!;
  const detail = fakeRes();
  await skill.handler(postReq(JSON.stringify({ name: "doctrine" })), detail.res);
  assert.match(detail.out.body, /# doctrine/);
  const missing = fakeRes();
  await skill.handler(postReq(JSON.stringify({ name: "absent-skill" })), missing.res);
  assert.equal(missing.out.status, 404);
  const wrongMethod = fakeRes();
  await skill.handler(getReq(), wrongMethod.res);
  assert.equal(wrongMethod.out.status, 405);
  const plugins = fakeRes();
  await byPath.get("/data/plugins.json")!.handler(getReq(), plugins.res);
  assert.equal((JSON.parse(plugins.out.body) as { mcp: { server: string }[] }).mcp[0]!.server, "alpaca-kit");
});
