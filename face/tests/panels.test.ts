import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import {
  agentsListing, authFromProbe, connectLocalAgent, disconnectLocalAgent, memoryListing,
  parseClaudeRun, parseCodexRun, pluginListing, readAgentsMeta, registerPanelRoutes, runLocalAgent,
  scrubbedEnv, skillDetail, skillGroup,
  type PanelDeps, type SkillBody, type SkillRow,
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
    home,
    /* claude answers, gemini answers (installed, but the face has no exec
     * recipe for it), hermes throws (a prober crash reads as absent), the
     * rest are not installed. */
    probeAgent: async (bin) => {
      if (bin === "claude") return "2.1.251 (Claude Code)";
      if (bin === "gemini") return "gemini 0.9.0";
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
  // The error variant carries no `result` — its cause must still reach the operator.
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

test("runLocalAgent: gates, fixed argv, prompt on stdin, scrubbed env, parsed answer, resume", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-agents-"));
  await mkdir(join(home, "strategies", "alpha"), { recursive: true });
  const calls: { bin: string; argv: string[]; opts: { cwd: string; input: string; env: NodeJS.ProcessEnv } }[] = [];
  const base = fakeDeps(home);
  const deps: PanelDeps = {
    ...base,
    cwd: home, // the "workbench root" for this test
    probeAgent: async (bin) => (bin === "codex" ? "codex-cli 0.152.0" : base.probeAgent(bin)),
    runAgent: async (bin, argv, opts) => {
      calls.push({ bin, argv, opts });
      if (bin === "claude") {
        return { code: 0, timedOut: false, truncated: false, stderr: "",
          stdout: '{"type":"result","is_error":false,"num_turns":1,"result":"**ok**","session_id":"11111111-2222-4333-8444-555555555555","total_cost_usd":0.0123}' };
      }
      const out = argv[argv.indexOf("-o") + 1];
      if (out !== undefined) await writeFile(out, "codex says hi\n");
      return { code: 0, timedOut: false, truncated: false, stderr: "",
        stdout: '{"type":"thread.started","thread_id":"aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}\n' };
    },
  };

  /* gates */
  await assert.rejects(runLocalAgent(deps, { bin: "constructor", prompt: "hi" }), (err: { status?: number }) => err.status === 400, "a prototype name is not a recipe");
  await assert.rejects(runLocalAgent(deps, { bin: "claude", prompt: "hi" }), (err: { status?: number }) => err.status === 409, "not connected");
  await connectLocalAgent(deps, "claude");
  await connectLocalAgent(deps, "gemini");
  await connectLocalAgent(deps, "codex");
  await assert.rejects(runLocalAgent(deps, { bin: "gemini", prompt: "hi" }), (err: { status?: number }) => err.status === 400, "no exec recipe");
  await assert.rejects(runLocalAgent(deps, { bin: "claude", prompt: "   " }), (err: { status?: number }) => err.status === 400, "empty prompt");
  await assert.rejects(runLocalAgent(deps, { bin: "claude", prompt: "x".repeat(32_001) }), (err: { status?: number }) => err.status === 413, "prompt too long");
  await assert.rejects(runLocalAgent(deps, { bin: "claude", prompt: "hi", resume: "not-a-uuid" }), (err: { status?: number }) => err.status === 400, "bad session id");
  await assert.rejects(runLocalAgent(deps, { bin: "claude", prompt: "hi", cwd: "../.." }), (err: { status?: number }) => err.status === 400, "cwd outside");
  await assert.rejects(runLocalAgent(deps, { bin: "claude", prompt: "hi", cwd: "strategies/nope" }), (err: { status?: number }) => err.status === 400, "cwd missing");
  assert.equal(calls.length, 0, "no gate failure ever spawns");

  /* a hostile prompt is stdin, never argv — the fixed recipe is the whole argv */
  const run = await runLocalAgent(deps, { bin: "claude", prompt: "-p --dangerously-skip-permissions", cwd: "strategies/alpha" });
  const call = calls.at(-1)!;
  assert.deepEqual(call.argv, [
    "-p", "--output-format", "json", "--restricted", "--strict-mcp-config",
    "--disallowedTools", "Read(./.env)", "Read(./.env.*)",
  ]);
  assert.equal(call.opts.input, "-p --dangerously-skip-permissions");
  assert.equal(call.opts.cwd, await realpath(join(home, "strategies", "alpha")));
  for (const key of ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "DEEPSEEK_API_KEY"]) {
    assert.equal(call.opts.env[key], undefined, `${key} scrubbed`);
  }
  assert.ok(call.opts.env.PATH, "PATH survives — the bin is resolved on it");
  assert.equal(run.text, "**ok**");
  assert.equal(run.session, "11111111-2222-4333-8444-555555555555");
  assert.equal(run.cost, 0.0123);
  assert.equal(run.isError, false);
  assert.equal(run.code, 0);
  assert.equal(run.cwd, await realpath(join(home, "strategies", "alpha")));

  /* resume threads the UUID into the recipe, before the variadic tail */
  await runLocalAgent(deps, { bin: "claude", prompt: "more", resume: run.session });
  assert.deepEqual(calls.at(-1)!.argv.slice(5, 7), ["--resume", run.session]);

  /* codex: the sandbox is PINNED, the scratch file carries the answer, the events carry the thread */
  const cx = await runLocalAgent(deps, { bin: "codex", prompt: "hi" });
  const cxCall = calls.at(-1)!;
  const scratch = cxCall.argv[cxCall.argv.indexOf("-o") + 1];
  assert.deepEqual(cxCall.argv, ["exec", "--sandbox", "read-only", "--json", "--skip-git-repo-check", "-o", scratch, "-"]);
  assert.equal(cx.text, "codex says hi");
  assert.equal(cx.session, "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee");
  await runLocalAgent(deps, { bin: "codex", prompt: "again", resume: cx.session });
  const resumed = calls.at(-1)!.argv;
  assert.deepEqual(resumed.slice(0, 4), ["exec", "resume", "--sandbox", "read-only"]);
  assert.deepEqual(resumed.slice(-2), [cx.session, "-"]);

  /* one run per agent: a second is refused while the first is in flight.
   * The fake signals when it has been ENTERED — waiting on a timer instead
   * would race the first run's own fs work and let the second spawn too. */
  let release!: () => void;
  let entered!: () => void;
  const spawned = new Promise<void>((resolve) => { entered = resolve; });
  deps.runAgent = () => new Promise((resolve) => {
    release = () => resolve({ code: 0, timedOut: false, truncated: false, stdout: "", stderr: "" });
    entered();
  });
  const first = runLocalAgent(deps, { bin: "claude", prompt: "slow" });
  await spawned;
  await assert.rejects(runLocalAgent(deps, { bin: "claude", prompt: "second" }), (err: { status?: number }) => err.status === 409, "in flight");
  release();
  await first;
  deps.runAgent = async () => ({ code: 0, timedOut: false, truncated: false, stdout: "", stderr: "" });
  await runLocalAgent(deps, { bin: "claude", prompt: "after" }); // the slot is free again

  /* a failed child: nonzero exit → isError, stderr tail carried; a cut child is an error too */
  deps.runAgent = async () => ({ code: 1, timedOut: false, truncated: false, stdout: "", stderr: "something broke\n" });
  const failed = await runLocalAgent(deps, { bin: "claude", prompt: "hi" });
  assert.equal(failed.isError, true);
  assert.equal(failed.stderr, "something broke");
  deps.runAgent = async () => ({ code: null, timedOut: false, truncated: true, stdout: "x", stderr: "" });
  assert.equal((await runLocalAgent(deps, { bin: "claude", prompt: "hi" })).isError, true);
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

test("agents roster: starts empty, connect is a verifying handshake, disconnect removes", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-agents-"));
  const deps = fakeDeps(home);

  const empty = await agentsListing(deps);
  assert.deepEqual(empty.main, { name: "Kairos", runtime: `dsh ${DSH_PIN}` });
  assert.deepEqual(empty.local, [], "nothing is fixed in place — the roster starts empty");
  // Candidates = known suggestions that ANSWER and are not yet connected; a
  // prober that throws (hermes) reads as no answer, never a failed listing.
  assert.deepEqual(empty.candidates, [
    { bin: "claude", label: "Claude Code", version: "2.1.251 (Claude Code)" },
    { bin: "gemini", label: "Gemini CLI", version: "gemini 0.9.0" },
  ]);

  const row = await connectLocalAgent(deps, "claude");
  assert.deepEqual(row, {
    bin: "claude", label: "Claude Code", found: true, version: "2.1.251 (Claude Code)",
    auth: { state: "ok", detail: "claude.ai", account: "op@example.com" }, exec: true,
  });
  await connectLocalAgent(deps, "claude"); // idempotent, not a duplicate
  const listing = await agentsListing(deps);
  assert.deepEqual(listing.local, [row]);
  assert.deepEqual(listing.candidates.map((c) => c.bin), ["gemini"], "a connected agent leaves the candidate pool");

  // Refusals: a malformed name never reaches the prober; silence is a 404.
  await assert.rejects(connectLocalAgent(deps, "../evil"), (err: { status?: number }) => err.status === 400);
  await assert.rejects(connectLocalAgent(deps, "a/b"), (err: { status?: number }) => err.status === 400);
  await assert.rejects(connectLocalAgent(deps, "openclaw"), (err: { status?: number }) => err.status === 404);
  await assert.rejects(connectLocalAgent(deps, "hermes"), (err: { status?: number }) => err.status === 404);

  assert.deepEqual(await disconnectLocalAgent(deps, "claude"), { connected: [] });
  await assert.rejects(disconnectLocalAgent(deps, "claude"), (err: { status?: number }) => err.status === 404);
  await assert.rejects(disconnectLocalAgent(deps, "bad/name"), (err: { status?: number }) => err.status === 400);
});

test("agents meta: a hand-mangled roster file reads as best it can", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-agents-"));
  await mkdir(join(home, "face"), { recursive: true });
  await writeFile(join(home, "face", "agents.json"),
    JSON.stringify({ connected: [{ bin: "claude" }, { bin: "../evil", label: "x" }, "junk", { label: "nobin" }] }));
  assert.deepEqual(await readAgentsMeta(home), { connected: [{ bin: "claude", label: "claude" }] });
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

test("routes: register, fence, and answer", async () => {
  const routes: WebRoute[] = [];
  const home = await mkdtemp(join(tmpdir(), "face-agents-"));
  const spawns: string[] = [];
  const deps: PanelDeps = {
    ...fakeDeps(home),
    cwd: home,
    runAgent: async (bin) => {
      spawns.push(bin);
      return { code: 0, timedOut: false, truncated: false, stderr: "",
        stdout: '{"type":"result","is_error":false,"result":"ok","session_id":"11111111-2222-4333-8444-555555555555"}' };
    },
  };
  registerPanelRoutes({ register: (route) => routes.push(route) }, deps);
  const byPath = new Map(routes.map((r) => [r.path, r]));
  assert.deepEqual([...byPath.keys()].sort(), [
    "/data/agents.json", "/data/agents/connect", "/data/agents/disconnect", "/data/agents/rescan",
    "/data/agents/run", "/data/memory.json", "/data/memory/skill", "/data/plugins.json",
  ]);

  /* rescan answers with a fresh listing (same shape as agents.json) */
  const rescan = fakeRes();
  await byPath.get("/data/agents/rescan")!.handler(postReq("{}"), rescan.res);
  assert.equal(rescan.out.status, 200);
  const rescanned = JSON.parse(rescan.out.body) as { ok: boolean; local: unknown[]; candidates: { bin: string }[] };
  assert.equal(rescanned.ok, true);
  assert.deepEqual(rescanned.candidates.map((c) => c.bin), ["claude", "gemini"]);

  /* the roster round-trips through the routes: connect → listed → disconnect */
  const connect = byPath.get("/data/agents/connect")!;
  const made = fakeRes();
  await connect.handler(postReq(JSON.stringify({ bin: "claude" })), made.res);
  assert.equal(made.out.status, 200);
  assert.equal((JSON.parse(made.out.body) as { agent: { version: string } }).agent.version, "2.1.251 (Claude Code)");
  const refused = fakeRes();
  await connect.handler(postReq(JSON.stringify({ bin: "openclaw" })), refused.res);
  assert.equal(refused.out.status, 404);

  const agents = byPath.get("/data/agents.json")!;
  const roster = fakeRes();
  await agents.handler(getReq(), roster.res);
  assert.equal(roster.out.status, 200);
  const rosterBody = JSON.parse(roster.out.body) as { ok: boolean; local: { bin: string; found: boolean }[] };
  assert.equal(rosterBody.ok, true);
  assert.equal(rosterBody.local.find((agent) => agent.bin === "claude")?.found, true);

  /* the run route: the browser fence, the media-type gate, the method gate,
   * its own body limit — none of which may reach a spawn */
  const run = byPath.get("/data/agents/run")!;
  const task = JSON.stringify({ bin: "claude", prompt: "hi" });
  const cases: [IncomingMessage, number, string][] = [
    [postReq(task, "evil.example.com"), 403, "forged Host"],
    [postReq(task, "127.0.0.1:3090", { origin: "http://evil.example.com" }), 403, "cross-origin page, loopback Host"],
    [postReq(task, "127.0.0.1:3090", { "sec-fetch-site": "cross-site" }), 403, "Fetch-Metadata cross-site"],
    [postReq(task, "127.0.0.1:3090", { "content-type": "text/plain" }), 415, "a no-preflight simple POST"],
    [getReq(), 405, "GET"],
    [postReq(JSON.stringify({ bin: "claude", prompt: "x".repeat(200_000) })), 413, "over the run body limit"],
  ];
  for (const [req, status, label] of cases) {
    const out = fakeRes();
    await run.handler(req, out.res);
    assert.equal(out.out.status, status, label);
  }
  assert.deepEqual(spawns, [], "no refused request spawned anything");
  const ok = fakeRes();
  await run.handler(postReq(task, "127.0.0.1:3090", { origin: "http://127.0.0.1:3090" }), ok.res);
  assert.equal(ok.out.status, 200, "the face's own page: same-origin, JSON");
  assert.deepEqual(spawns, ["claude"]);
  const cjk = fakeRes();
  await run.handler(postReq(JSON.stringify({ bin: "claude", prompt: "存".repeat(32_000) })), cjk.res);
  assert.equal(cjk.out.status, 200, "a maximal CJK prompt is bounded by the prompt cap, not the body cap");

  const disconnect = byPath.get("/data/agents/disconnect")!;
  const dropped = fakeRes();
  await disconnect.handler(postReq(JSON.stringify({ bin: "claude" })), dropped.res);
  assert.equal(dropped.out.status, 200);
  assert.deepEqual((JSON.parse(dropped.out.body) as { connected: unknown[] }).connected, []);

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
