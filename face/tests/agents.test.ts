import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { agentToolDefinition, runAgentRecipe, type RunOutcome } from "../src/agents.ts";
import type { PanelDeps } from "../src/panels.ts";
import { setRoster } from "../src/roster.ts";

/** A roster home of its own per test. */
const freshHome = (): Promise<string> => mkdtemp(join(tmpdir(), "face-agents-"));

/** A clean run outcome, for fakes. */
const ran = (stdout: string, over: Partial<RunOutcome> = {}): RunOutcome =>
  ({ code: 0, stdout, stderr: "", timedOut: false, truncated: false, ...over });

/** A minimal but type-complete {@link PanelDeps}: `runAgentRecipe` and
 * `agentToolDefinition` only ever read `cwd`, `home`, `channelFor` and
 * `runAgent` off it, so the other fields (skills/tools/loader/probes) are
 * stubs that must never be reached. `channelFor` defaults to "no channel"
 * (fail open) — the roster tests below override it per case. */
function fakeDeps(home: string): PanelDeps {
  return {
    skills: { list: async () => [], get: async () => undefined },
    toolSchemas: () => [],
    registerTool: () => () => {},
    loaderEntries: () => [],
    cwd: home,
    home,
    channelFor: async () => null,
    probeAgent: async () => null,
    probeAuth: async () => ({ state: "unknown" }),
    runAgent: async () => { throw new Error("runAgent not injected"); },
  };
}

/* ====================================================================== */
/* the recipes and the runner seams                                        */
/* ====================================================================== */

test("runAgentRecipe: gates, fixed argv, prompt on stdin, scrubbed env, session cwd, resume, one per agent", async () => {
  const home = await freshHome();
  await mkdir(join(home, "strategies", "alpha"), { recursive: true });
  const calls: { bin: string; argv: string[]; opts: { cwd: string; input: string; env: NodeJS.ProcessEnv; signal?: AbortSignal } }[] = [];
  const deps: PanelDeps = {
    ...fakeDeps(home),
    cwd: home, // the "workbench root" for this test
    runAgent: async (bin, argv, opts) => {
      calls.push({ bin, argv, opts });
      if (bin === "claude") {
        return ran('{"type":"result","is_error":false,"num_turns":1,"result":"**ok**","session_id":"11111111-2222-4333-8444-555555555555","total_cost_usd":0.0123}');
      }
      const out = argv[argv.indexOf("-o") + 1];
      if (out !== undefined) await writeFile(out, "codex says hi\n");
      return ran('{"type":"thread.started","thread_id":"aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}\n');
    },
  };

  /* gates — none may spawn */
  const status = (n: number) => (err: { status?: number }) => err.status === n;
  await assert.rejects(runAgentRecipe(deps, { bin: "constructor", prompt: "hi" }), status(400), "a prototype name is not a recipe");
  await assert.rejects(runAgentRecipe(deps, { bin: "gemini", prompt: "hi" }), status(400), "installed, but no recipe");
  await assert.rejects(runAgentRecipe(deps, { bin: "claude", prompt: "   " }), status(400), "empty prompt");
  await assert.rejects(runAgentRecipe(deps, { bin: "claude", prompt: "x".repeat(32_001) }), status(413), "prompt too long");
  await assert.rejects(runAgentRecipe(deps, { bin: "claude", prompt: "hi", resume: "not-a-uuid" }), status(400), "bad session id");
  assert.equal(calls.length, 0, "no gate failure ever spawns");

  /* a hostile prompt is stdin, never argv — the fixed recipe is the whole argv */
  const signal = new AbortController().signal;
  const run = await runAgentRecipe(deps, { bin: "claude", prompt: "-p --dangerously-skip-permissions", cwd: join(home, "strategies", "alpha"), signal });
  const call = calls.at(-1)!;
  assert.deepEqual(call.argv, [
    "-p", "--output-format", "json", "--restricted", "--strict-mcp-config",
    "--disallowedTools", "Read(./.env)", "Read(./.env.*)",
  ]);
  assert.equal(call.opts.input, "-p --dangerously-skip-permissions");
  assert.equal(call.opts.cwd, await realpath(join(home, "strategies", "alpha")), "the session's directory");
  assert.equal(call.opts.signal, signal, "the caller's cancellation reaches the child");
  for (const key of ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "DEEPSEEK_API_KEY"]) {
    assert.equal(call.opts.env[key], undefined, `${key} scrubbed`);
  }
  assert.ok(call.opts.env.PATH, "PATH survives — the bin is resolved on it");
  assert.equal(run.text, "**ok**");
  assert.equal(run.session, "11111111-2222-4333-8444-555555555555");
  assert.equal(run.cost, 0.0123);
  assert.equal(run.isError, false);

  /* a vanished session directory falls back to the root rather than failing the spawn */
  await runAgentRecipe(deps, { bin: "claude", prompt: "hi", cwd: join(home, "gone") });
  assert.equal(calls.at(-1)!.opts.cwd, await realpath(home));
  await runAgentRecipe(deps, { bin: "claude", prompt: "hi" });
  assert.equal(calls.at(-1)!.opts.cwd, await realpath(home), "no cwd → the root");

  /* resume threads the UUID into the recipe, before the variadic tail */
  await runAgentRecipe(deps, { bin: "claude", prompt: "more", resume: run.session });
  assert.deepEqual(calls.at(-1)!.argv.slice(5, 7), ["--resume", run.session]);

  /* codex: the sandbox is PINNED, the scratch file carries the answer, the events carry the thread */
  const cx = await runAgentRecipe(deps, { bin: "codex", prompt: "hi" });
  const cxCall = calls.at(-1)!;
  const scratch = cxCall.argv[cxCall.argv.indexOf("-o") + 1];
  assert.deepEqual(cxCall.argv, ["exec", "--sandbox", "read-only", "--json", "--skip-git-repo-check", "-o", scratch, "-"]);
  assert.equal(cx.text, "codex says hi");
  assert.equal(cx.session, "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee");
  await runAgentRecipe(deps, { bin: "codex", prompt: "again", resume: cx.session });
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
    release = () => resolve(ran(""));
    entered();
  });
  const first = runAgentRecipe(deps, { bin: "claude", prompt: "slow" });
  await spawned;
  await assert.rejects(runAgentRecipe(deps, { bin: "claude", prompt: "second" }), status(409), "in flight");
  release();
  await first;
  deps.runAgent = async () => ran("");
  await runAgentRecipe(deps, { bin: "claude", prompt: "after" }); // the slot is free again

  /* a failed child: nonzero exit → isError, stderr tail carried; a cut child is an error too */
  deps.runAgent = async () => ran("", { code: 1, stderr: "something broke\n" });
  const failed = await runAgentRecipe(deps, { bin: "claude", prompt: "hi" });
  assert.equal(failed.isError, true);
  assert.equal(failed.stderr, "something broke");
  deps.runAgent = async () => ran("x", { code: null, truncated: true });
  assert.equal((await runAgentRecipe(deps, { bin: "claude", prompt: "hi" })).isError, true);
});

/* ====================================================================== */
/* connected ⇒ callable: the agent tools                                   */
/* ====================================================================== */

test("agentToolDefinition: the tool Kairos gets — schema, read card, session cwd, cancellation, error propagation", async () => {
  const home = await freshHome();
  await mkdir(join(home, "strategies", "alpha"), { recursive: true });
  const calls: { argv: string[]; opts: { cwd: string; input: string; signal?: AbortSignal } }[] = [];
  const deps: PanelDeps = {
    ...fakeDeps(home),
    cwd: home,
    runAgent: async (_bin, argv, opts) => {
      calls.push({ argv, opts });
      if (opts.input === "fail") return ran('{"type":"result","is_error":true,"errors":["model refused"]}');
      return ran('{"type":"result","is_error":false,"num_turns":1,"result":"the tree has 3 files","session_id":"11111111-2222-4333-8444-555555555555","total_cost_usd":0.02}');
    },
  };
  const tool = agentToolDefinition(deps, "claude", "Claude Code");
  assert.equal(tool.name, "agent_claude");
  assert.match(tool.description, /READ-ONLY/);
  assert.deepEqual((tool.parameters as { required: string[] }).required, ["prompt"]);
  assert.equal(tool.timeoutMs, 600_000);
  assert.deepEqual(tool.presentCall({ prompt: "what is here?" }), { card: "generic", title: "Ask Claude Code", kind: "read", rawInput: "what is here?" });

  const controller = new AbortController();
  const exec = { agent: { session: { header: { cwd: join(home, "strategies", "alpha") } } }, signal: controller.signal };
  const value = await tool.execute({ prompt: "what is here?" }, exec) as Record<string, unknown>;
  assert.equal(calls[0]!.opts.cwd, await realpath(join(home, "strategies", "alpha")), "runs in the CALLING SESSION's directory");
  assert.equal(calls[0]!.opts.input, "what is here?");
  assert.equal(calls[0]!.opts.signal, controller.signal);
  assert.deepEqual(Object.keys(value).sort(), ["cost", "durationMs", "isError", "session", "text", "turns"], "exactly the declared output shape");
  assert.equal(value.text, "the tree has 3 files");
  const rendered = tool.output.render({ prompt: "x" }, value);
  assert.equal(rendered.length, 1);
  assert.match(rendered[0]!.text, /^the tree has 3 files\n\n\[Claude Code session 11111111-2222-4333-8444-555555555555 — pass resume="11111111-/);

  /* a session-less call (no agent on the exec) runs at the root */
  await tool.execute({ prompt: "again", resume: "11111111-2222-4333-8444-555555555555" }, { signal: controller.signal });
  assert.equal(calls[1]!.opts.cwd, await realpath(home));
  assert.deepEqual(calls[1]!.argv.slice(5, 7), ["--resume", "11111111-2222-4333-8444-555555555555"]);

  /* a failed run throws, so the registry hands Kairos an error result with the cause */
  await assert.rejects(tool.execute({ prompt: "fail" }, exec), /model refused/);
  await assert.rejects(tool.execute({}, exec), /prompt required/);
  await assert.rejects(tool.execute({ prompt: "x", resume: "nope" }, exec), /invalid session id/);
});

/* ====================================================================== */
/* the per-channel roster check                                            */
/* ====================================================================== */

/** Deps enough to build one tool: the run never happens when the roster
 * refuses, and when it does we only care that it was reached. `cwd` is a
 * real directory (`home` itself, not the brief's illustrative "/repo"):
 * `runAgentRecipe` resolves the session directory through `stat`, and a
 * fictional root would throw ENOENT before the roster check is even
 * reached — which would fail the ON-roster and no-channel cases (which must
 * actually complete a run) for the wrong reason. */
function toolDeps(home: string, channel: { workspaceId: string; name: string } | null) {
  const ran: string[] = [];
  const deps = {
    home,
    cwd: home,
    async channelFor() { return channel; },
    async runAgent(bin: string) {
      ran.push(bin);
      return { code: 0, stdout: JSON.stringify({ result: "hi", session_id: "s1" }), stderr: "", timedOut: false, truncated: false };
    },
  } as any;
  return { deps, ran };
}

const exec = (cwd: string) => ({ agent: { session: { header: { cwd } } }, signal: new AbortController().signal });

test("an agent NOT on the channel's roster is refused, and the CLI never spawns", async () => {
  const home = await freshHome();
  await setRoster(home, "ws-1", ["claude"]);
  const { deps, ran } = toolDeps(home, { workspaceId: "ws-1", name: "alpha" });
  const tool = agentToolDefinition(deps, "codex", "Codex");

  await assert.rejects(
    tool.execute({ prompt: "hi" }, exec("/repo/strategies/alpha")),
    (err: Error) => /not on this channel/i.test(err.message) && /alpha/.test(err.message) && /claude/.test(err.message),
    "the refusal names the channel and its current roster - it IS the contract",
  );
  assert.deepEqual(ran, [], "no child process was spawned");
});

test("an agent ON the roster runs", async () => {
  const home = await freshHome();
  await setRoster(home, "ws-1", ["codex"]);
  const { deps, ran } = toolDeps(home, { workspaceId: "ws-1", name: "alpha" });
  await agentToolDefinition(deps, "codex", "Codex").execute({ prompt: "hi" }, exec("/repo/strategies/alpha"));
  assert.deepEqual(ran, ["codex"]);
});

test("execute passes channelFor the SESSION's real cwd, not something else - a guard never drilled is presumed broken (charter Rule 4)", async () => {
  // Every other roster test above stubs channelFor to ignore its argument
  // (`toolDeps`'s `async channelFor() { return channel; }`), so none of them
  // actually pin that `exec.agent?.session.header.cwd` - the entire input to
  // the roster decision - is what reaches it. A recording stub closes that.
  const home = await freshHome();
  const seen: (string | undefined)[] = [];
  const deps = {
    home,
    cwd: home,
    async channelFor(cwd: string | undefined) { seen.push(cwd); return null; },
    async runAgent(bin: string) {
      return { code: 0, stdout: JSON.stringify({ result: "hi", session_id: "s1" }), stderr: "", timedOut: false, truncated: false };
    },
  } as any;
  await agentToolDefinition(deps, "codex", "Codex").execute({ prompt: "hi" }, exec("/repo/strategies/alpha"));
  assert.deepEqual(seen, ["/repo/strategies/alpha"], "channelFor must see the exec context's own session cwd, verbatim");

  // And when the exec carries no agent (a session-less call, drilled
  // elsewhere in this file), the cwd handed to channelFor is genuinely
  // undefined - not silently defaulted to something that would mask the
  // no-agent case as a real session.
  await agentToolDefinition(deps, "codex", "Codex").execute({ prompt: "hi" }, { signal: new AbortController().signal });
  assert.deepEqual(seen, ["/repo/strategies/alpha", undefined]);
});

test("a session in no channel fails OPEN - which is exactly today's behaviour", async () => {
  const home = await freshHome();
  const { deps, ran } = toolDeps(home, null);
  await agentToolDefinition(deps, "codex", "Codex").execute({ prompt: "hi" }, exec("/somewhere/else"));
  assert.deepEqual(ran, ["codex"], "no channel means no roster to consult; tools are tree-wide anyway");
});

test("a corrupt roster file fails CLOSED", async () => {
  const home = await freshHome();
  await mkdir(join(home, "face"), { recursive: true });
  await writeFile(join(home, "face", "channels.json"), "{not json");
  const { deps, ran } = toolDeps(home, { workspaceId: "ws-1", name: "alpha" });
  await assert.rejects(
    agentToolDefinition(deps, "codex", "Codex").execute({ prompt: "hi" }, exec("/repo/strategies/alpha")),
    /unreadable/i,
    // Deliberately distinct from the off-roster message above: a corrupt
    // file is not the same fact as an empty roster, and `readRosters`'s
    // `corrupt` flag must not fold into "no entry for this workspace" and
    // answer with "no roster yet" — that would report a genuinely broken
    // file as merely unseeded.
  );
  assert.deepEqual(ran, []);
});

test("a channel with no roster entry yet - file present and valid, just not seeded - fails CLOSED with its own message, not 'unreadable'", async () => {
  const home = await freshHome();
  // A perfectly healthy file: it just has no entry for ws-1. This is the
  // ordinary state of a workspace the dsh client created directly through
  // the registry, before /data/channels.json (the reconcile) ever ran for
  // it - not the same fact as a corrupt file, and the refusal must say so.
  await setRoster(home, "ws-other", ["claude"]);
  const { deps, ran } = toolDeps(home, { workspaceId: "ws-1", name: "alpha" });
  await assert.rejects(
    agentToolDefinition(deps, "codex", "Codex").execute({ prompt: "hi" }, exec("/repo/strategies/alpha")),
    (err: Error) => /no roster yet/i.test(err.message) && !/unreadable/i.test(err.message),
    "names the not-yet-seeded situation, and must not misdiagnose it as an unreadable file",
  );
  assert.deepEqual(ran, []);
});
