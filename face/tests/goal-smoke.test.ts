/** The goal loop `dsh/profile/cycle.md` rests on, on a real tree (docs/dsh-upgrade-guide.md C21;
 * DEVELOPMENT.md R30): dsh-base's `goal`, `goal-round-driver`, `tool-goal` and `command-goal`
 * rows, driven the way the face drives them - prompts over the browser's wire, the face's Stop as
 * `session/cancel`, a slash line as `commands/execute` - with a stub model. The contract tells
 * Gravit only what these packages let it do, and any dsh pin can move them, so each fact it
 * relies on is pinned here:
 * - create_goal in a human turn returns the goal's id and revision 1, active and armed;
 * - each round arrives at idle as a user message whose source is `goal`, its text `<goal_round>`,
 *   the objective and `Round: n/N`;
 * - the model's `blocked` in round 1 is refused ("blocked requires at least 3 consecutive goal
 *   rounds"); in round 3 it is accepted with the code `model-reported` and the `<goal_blocked>`
 *   wrap-up follows; while that goal is blocked a second create_goal is refused (one cycle per
 *   session);
 * - at the cap the driver blocks the goal with `round-limit` and asks the model nothing more;
 * - the face's Stop mid-round PAUSES the goal; the model's resume of it is refused
 *   (`GOAL_TOOL_RESUME_PAUSED`) and the operator's `/goal resume` re-arms it;
 * - a face stopped mid-round and booted again on the same home leaves the goal active and
 *   disarmed, asking the model nothing until the operator's "continue", whose update_goal resume
 *   bumps the revision and re-arms the rounds.
 * Own file, gated; the restart step boots the same home a second time, as subagents-smoke does. */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { Agent } from "@deepseek-ai/dsh-agent";
import type { GenerateOptions } from "@deepseek-ai/dsh-llm";
import { SessionId } from "@deepseek-ai/dsh-session";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { makeBotsRoot } from "./bots-fixture.ts";
import { mountClient, remote, signIn } from "./remote.ts";
import { StubAdapter, type StubReply } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";

/** The goal service's view of one session (`ctx.get("goals").get(agent)`). dsh-goal is a dsh-base
 *  row, not a face dependency, so the shape is restated from its installed lib. */
type GoalView = {
  id: string; revision: number; objective: string; phase: "active" | "paused" | "blocked" | "complete";
  maxGoalRounds: number; roundsStarted: number; activation: "armed" | "disarmed"; blockedReason?: { code: string; message: string };
};
/** What one model request was driven by: the last message the stub decides on. */
type Seen = { boot: string; sessionId: string; kind: string; text: string; source: Record<string, unknown> };
/** One tool call in a session's log, with the result the model got back and the code dsh recorded. */
type Call = { name: string; isError: boolean; text: string; code?: string };
type Scenario = "cycle" | "cap" | "stop" | "restart";

const OBJECTIVE: Record<Scenario, string> = {
  cycle: "goal smoke: block in round 3",
  cap: "goal smoke: run to the cap",
  stop: "goal smoke: stopped mid-round",
  restart: "goal smoke: restarted mid-round",
};
const BLOCKED_REASON = "data-missing: the fixture bed holds no window";
/** A tool that runs until its call is cancelled: a round that is still working when the operator
 *  presses Stop, or when the face goes down. */
const WAIT_TOOL = "smoke_wait";

const sourceOf = (m: { source?: unknown }) => (m.source ?? {}) as Record<string, unknown>;
const textOf = (m: GenerateOptions["messages"][number]) => m.content.map((b) => "text" in b ? b.text : "").join("\n");
/** The message a request answers: the operator's, a tool result, a goal round, or the goal tool's wrap-up. */
const lastOf = (r: GenerateOptions) => [...r.messages].reverse().find((m) => ["user", "tool", "goal", "tool-goal"].includes(String(sourceOf(m).kind)));
const roundOf = (text: string) => Number(/Round: (\d+)\/\d+/.exec(text)?.[1]);
const parse = (text: string): { goal?: { id: string; revision: number } } | undefined => { try { return JSON.parse(text); } catch { return undefined; } };
const settle = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
async function waitFor(label: string, check: () => boolean, ms = 30_000) {
  const until = Date.now() + ms;
  while (!check()) { if (Date.now() >= until) throw new Error(`timed out: ${label}`); await settle(20); }
}

/** A session's tool calls, each paired with its result, from the durable log. */
function callsOf(agent: Agent): Call[] {
  const events = agent.session.snapshotEvents() as unknown as readonly { type: string; data: Record<string, any> }[];
  const names = new Map(events.filter((e) => e.type === "tool/call").map((e) => [String(e.data.callId), String(e.data.name)]));
  return events.filter((e) => e.type === "tool/result").map((e) => ({
    name: names.get(String(e.data.message.toolCallId)) ?? "?",
    isError: e.data.message.isError === true,
    text: (e.data.message.content as { text?: string }[]).map((b) => b.text ?? "").join("\n"),
    ...e.data.error?.code === undefined ? {} : { code: String(e.data.error.code) },
  }));
}

test("goal smoke: create in a human turn, the round message, the round-3 block, the silent cap, Stop pauses, a restart disarms until continue", {
  skip: gated && "set FACE_SMOKE=1", timeout: 240_000,
}, async () => {
  const bots = await makeBotsRoot();
  const root = await realpath(await mkdtemp(join(tmpdir(), "face-goal-root-")));
  const home = await mkdtemp(join(tmpdir(), "face-goal-home-"));
  let dispose: (() => Promise<void>) | undefined;
  try {
    await mkdir(join(root, ".git"));
    await writeFile(join(root, "GRAVIT.md"), "# fixture\n");
    setupFaceProfile(home);
    const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
    const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n- id: agent-default-model\n  config:\n    provider: stub\n    model: echo\n`);

    const scenario = new Map<string, Scenario>();
    const seen: Seen[] = [];
    /** The tool each session's model called last: what it does with the result depends on it. */
    const pending = new Map<string, string>();
    /** The goal ref each session's model holds, from the last result that carried one. */
    const refs = new Map<string, { goal_id: string; revision: number }>();
    /** Sessions whose WAIT_TOOL call is running now. */
    const waiting = new Set<string>();
    const scriptFor = (boot: string) => (request: GenerateOptions): StubReply => {
      if (request.purpose !== undefined) return { kind: "text", text: "fixture" };
      const sessionId = String(request.sessionId);
      const last = lastOf(request);
      const kind = last === undefined ? "none" : String(sourceOf(last).kind);
      const text = last === undefined ? "" : textOf(last);
      seen.push({ boot, sessionId, kind, text, source: last === undefined ? {} : sourceOf(last) });
      const play = scenario.get(sessionId);
      const call = (name: string, args: unknown): StubReply => { pending.set(sessionId, name); return { kind: "tool", name, args }; };
      if (kind === "tool") {
        const answered = pending.get(sessionId);
        pending.delete(sessionId);
        const value = parse(text);
        if (value?.goal !== undefined) refs.set(sessionId, { goal_id: value.goal.id, revision: value.goal.revision });
        /* "continue": the ref comes from get_goal, as cycle.md says, then the resume. */
        if (answered === "get_goal") return call("update_goal", { ...refs.get(sessionId)!, action: "resume" });
        return { kind: "text", text: `${answered}_SEEN` };
      }
      if (kind === "tool-goal") { pending.delete(sessionId); return { kind: "text", text: "CLOSING_MESSAGE" }; }
      if (kind === "user" && text === "OPEN") return call("create_goal", { objective: OBJECTIVE[play!], max_goal_rounds: play === "cap" ? 2 : 4 });
      if (kind === "user" && text === "OPEN_AGAIN") return call("create_goal", { objective: "goal smoke: a second idea", max_goal_rounds: 4 });
      if (kind === "user" && text === "continue") return call("get_goal", {});
      if (kind === "goal") {
        const round = roundOf(text);
        if (play === "cycle" && (round === 1 || round === 3)) return call("update_goal", { ...refs.get(sessionId)!, action: "blocked", blocked_reason: BLOCKED_REASON });
        if ((play === "stop" || play === "restart") && round === 1) return call(WAIT_TOOL, {});
        return { kind: "text", text: `ROUND_${round}_DONE` };
      }
      return { kind: "text", text: "OK" };
    };
    const boot = async (label: string) => {
      const booted = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
      const { ctx } = booted;
      (ctx.get("tools") as { register(d: unknown): () => void }).register({
        name: WAIT_TOOL, description: "waits until its call is cancelled", parameters: {},
        output: { schema: { type: "object" }, render: () => [{ type: "text", text: "waited" }] },
        execute: (_args: unknown, exec: { agent?: Agent; signal?: AbortSignal }) => new Promise((resolve) => {
          const id = String(exec.agent?.id);
          waiting.add(id);
          exec.signal?.addEventListener("abort", () => { waiting.delete(id); resolve({}); }, { once: true });
        }),
      });
      ctx.llm.registerAdapter(["stub"], new StubAdapter(scriptFor(label)));
      const base = `http://127.0.0.1:${ctx.webServer.port}`;
      mountClient(ctx);
      const cookie = await signIn(ctx, base);
      const rpc = <T = unknown>(endpoint: string, args: object) => remote<T>(base, cookie, endpoint, args);
      return { booted, ctx, rpc, goals: ctx.get("goals") as { get(agent: Agent): GoalView | undefined } };
    };
    let b = await boot("boot1");
    dispose = b.booted.dispose;
    const agentOf = (id: string): Agent => {
      const agent = b.ctx.agents.get(SessionId(id));
      assert.ok(agent, `session ${id} is live`);
      return agent;
    };
    const goalOf = (id: string) => b.goals.get(agentOf(id));
    const open = async (play: Scenario) => {
      const { sessionId } = await b.rpc<{ sessionId: string }>("session/create", { request: { cwd: root } });
      scenario.set(sessionId, play);
      return sessionId;
    };
    const say = (sessionId: string, value: string) => b.rpc("session/prompt", {
      request: { requestId: `goal-${crypto.randomUUID()}`, sessionId, mode: "queue", content: [{ type: "text", text: value }] },
    });
    const roundsSeen = (id: string, boot?: string) => seen.filter((s) => s.sessionId === id && s.kind === "goal" && (boot === undefined || s.boot === boot));

    /* 1 - the goal opens in a human turn; rounds arrive at idle; blocked is refused in round 1 and
     * accepted in round 3; a second goal is refused while this one is blocked. */
    const cycle = await open("cycle");
    await say(cycle, "OPEN");
    await waitFor("the cycle's goal blocked", () => goalOf(cycle)?.phase === "blocked");
    await agentOf(cycle).whenIdle();
    await settle(300);
    const [created, early, accepted] = callsOf(agentOf(cycle));
    assert.equal(created.name, "create_goal");
    assert.equal(created.isError, false, `create_goal in a human turn succeeds: ${created.text}`);
    const opened = JSON.parse(created.text) as { goal: GoalView; activation: string };
    assert.match(opened.goal.id, /^goal-/);
    assert.deepEqual({ revision: opened.goal.revision, phase: opened.goal.phase, roundsStarted: opened.goal.roundsStarted, maxGoalRounds: opened.goal.maxGoalRounds, activation: opened.activation },
      { revision: 1, phase: "active", roundsStarted: 0, maxGoalRounds: 4, activation: "armed" }, "the result carries the id and revision update_goal needs");
    const rounds = roundsSeen(cycle);
    assert.deepEqual(rounds.map((r) => roundOf(r.text)), [1, 2, 3], "one round per idle, none after the block");
    for (const [index, round] of rounds.entries()) {
      assert.deepEqual({ kind: round.source.kind, goalId: round.source.goalId, revision: round.source.revision, round: round.source.round },
        { kind: "goal", goalId: opened.goal.id, revision: 1, round: index + 1 }, "a round is a user message whose source is the goal");
      assert.ok(round.text.startsWith("<goal_round>\n"), round.text);
      assert.ok(round.text.includes(`Objective: ${JSON.stringify(OBJECTIVE.cycle)}`) && round.text.includes(`Round: ${index + 1}/4`), round.text);
    }
    assert.equal(early.name, "update_goal");
    assert.deepEqual({ isError: early.isError, code: early.code, text: early.text },
      { isError: true, code: "GOAL_TOOL_BLOCK_THRESHOLD", text: "Error: blocked requires at least 3 consecutive goal rounds; current round is 1" }, "an automatic round may not block before its third");
    assert.equal(accepted.name, "update_goal");
    assert.equal(accepted.isError, false, `blocked in round 3 is accepted: ${accepted.text}`);
    const blocked = goalOf(cycle)!;
    assert.deepEqual({ phase: blocked.phase, roundsStarted: blocked.roundsStarted, activation: blocked.activation, blockedReason: blocked.blockedReason },
      { phase: "blocked", roundsStarted: 3, activation: "disarmed", blockedReason: { code: "model-reported", message: BLOCKED_REASON } }, "the model's reason is kept whole, under the code model-reported");
    const wrapup = seen.find((s) => s.sessionId === cycle && s.kind === "tool-goal");
    assert.ok(wrapup !== undefined, "the block in a round is followed by the goal tool's wrap-up");
    assert.ok(wrapup.text.startsWith("<goal_blocked>\n") && wrapup.text.includes(`Blocked: ${JSON.stringify(BLOCKED_REASON)}`), wrapup.text);
    await say(cycle, "OPEN_AGAIN");
    await waitFor("the second create_goal answered", () => callsOf(agentOf(cycle)).length === 4);
    await agentOf(cycle).whenIdle();
    const again = callsOf(agentOf(cycle))[3];
    assert.equal(again.name, "create_goal");
    assert.equal(again.isError, true);
    assert.equal(again.code, "GOAL_ALREADY_EXISTS");
    assert.ok(again.text.includes(`goal "${opened.goal.id}" already exists with phase "blocked"`), again.text);
    assert.equal(goalOf(cycle)?.id, opened.goal.id, "one cycle per session: the blocked goal stays the record");

    /* 2 - at the cap the driver blocks with round-limit and prompts the model no more. */
    const cap = await open("cap");
    await say(cap, "OPEN");
    await waitFor("the capped goal blocked", () => goalOf(cap)?.phase === "blocked");
    await agentOf(cap).whenIdle();
    const requestsAtCap = seen.filter((s) => s.sessionId === cap).length;
    await settle(500);
    assert.equal(seen.filter((s) => s.sessionId === cap).length, requestsAtCap, "no request after the cap: no wrap-up, no round");
    assert.deepEqual(roundsSeen(cap).map((r) => r.text.includes(`Round: ${roundOf(r.text)}/2`) && roundOf(r.text)), [1, 2]);
    assert.equal(seen.filter((s) => s.sessionId === cap).at(-1)?.kind, "goal", "the last thing the model saw is the last round");
    const capped = goalOf(cap)!;
    assert.deepEqual({ roundsStarted: capped.roundsStarted, blockedReason: capped.blockedReason },
      { roundsStarted: 2, blockedReason: { code: "round-limit", message: "Goal reached its configured limit of 2 rounds." } });

    /* 3 - the face's Stop mid-round pauses the goal; the model cannot resume it; /goal resume can. */
    const stop = await open("stop");
    await say(stop, "OPEN");
    await waitFor("round 1 working", () => waiting.has(stop));
    await b.rpc("session/cancel", { request: { sessionId: stop } });
    await waitFor("the stopped goal paused", () => goalOf(stop)?.phase === "paused");
    await agentOf(stop).whenIdle();
    const paused = goalOf(stop)!;
    assert.deepEqual({ revision: paused.revision, roundsStarted: paused.roundsStarted, activation: paused.activation },
      { revision: 2, roundsStarted: 1, activation: "disarmed" }, "Stop during a round pauses the goal (a new revision)");
    await say(stop, "continue");
    await waitFor("the model's resume answered", () => callsOf(agentOf(stop)).some((c) => c.name === "update_goal"));
    await agentOf(stop).whenIdle();
    const stopCalls = callsOf(agentOf(stop));
    const read = stopCalls.find((c) => c.name === "get_goal")!;
    assert.deepEqual({ phase: (JSON.parse(read.text) as { goal: GoalView }).goal.phase, revision: (JSON.parse(read.text) as { goal: GoalView }).goal.revision }, { phase: "paused", revision: 2 }, "get_goal gives the current revision");
    const refusedResume = stopCalls.find((c) => c.name === "update_goal")!;
    assert.deepEqual({ isError: refusedResume.isError, code: refusedResume.code, text: refusedResume.text },
      { isError: true, code: "GOAL_TOOL_RESUME_PAUSED", text: "Error: the model cannot resume a paused goal; the user must resume it" });
    assert.equal(goalOf(stop)?.phase, "paused", "the goal stays paused");
    const executed = await b.rpc<{ result?: { kind?: string; text?: string } }>("commands/execute", { agentId: stop, line: "/goal resume", submittedAttachments: [] });
    assert.equal(executed?.result?.kind, "success", JSON.stringify(executed));
    assert.ok(executed?.result?.text?.startsWith("Goal resumed\nStatus: active\n") && executed.result.text.includes("Activation: armed"), executed?.result?.text);
    await waitFor("a round after /goal resume", () => roundsSeen(stop).some((r) => roundOf(r.text) === 2));
    assert.equal(roundsSeen(stop).find((r) => roundOf(r.text) === 2)?.source.revision, 3, "the resumed revision drives the next round");
    await waitFor("the resumed goal at its cap", () => goalOf(stop)?.phase === "blocked");
    await agentOf(stop).whenIdle();

    /* 4 - the face goes down mid-round; booted again, the goal is active and disarmed and nothing runs
     * until the operator's "continue". */
    const restart = await open("restart");
    await say(restart, "OPEN");
    await waitFor("round 1 working before the restart", () => waiting.has(restart));
    const running = goalOf(restart)!;
    assert.deepEqual({ phase: running.phase, revision: running.revision, roundsStarted: running.roundsStarted, activation: running.activation },
      { phase: "active", revision: 1, roundsStarted: 1, activation: "armed" });
    await b.booted.dispose();
    dispose = undefined;
    b = await boot("boot2");
    dispose = b.booted.dispose;
    await settle(1000);
    assert.equal(seen.filter((s) => s.boot === "boot2").length, 0, "after the restart nothing asks the model anything");
    const cold = await b.rpc<{ values: Record<string, unknown> } | null>("session/projections", { request: { sessionId: restart } });
    const coldGoal = cold?.values.goal as { goal: { phase: string; revision: number }; roundsStarted: number } | null | undefined;
    assert.deepEqual({ phase: coldGoal?.goal.phase, revision: coldGoal?.goal.revision, roundsStarted: coldGoal?.roundsStarted },
      { phase: "active", revision: 1, roundsStarted: 1 }, "the goal survived the restart, still active");
    await say(restart, "continue");
    await waitFor("a round after continue", () => roundsSeen(restart, "boot2").some((r) => roundOf(r.text) === 2));
    const restartCalls = callsOf(agentOf(restart));
    const reread = JSON.parse(restartCalls.find((c) => c.name === "get_goal")!.text) as { goal: GoalView; activation: string };
    assert.deepEqual({ phase: reread.goal.phase, revision: reread.goal.revision, activation: reread.activation },
      { phase: "active", revision: 1, activation: "disarmed" }, "get_goal after the restart: active, disarmed");
    const resumed = restartCalls.find((c) => c.name === "update_goal")!;
    assert.equal(resumed.isError, false, `the model's resume of an active, disarmed goal is accepted: ${resumed.text}`);
    const rearmed = JSON.parse(resumed.text) as { goal: GoalView; activation: string };
    assert.deepEqual({ phase: rearmed.goal.phase, revision: rearmed.goal.revision, activation: rearmed.activation },
      { phase: "active", revision: 2, activation: "armed" }, "resume bumps the revision and re-arms the goal");
    assert.equal(roundsSeen(restart, "boot2").find((r) => roundOf(r.text) === 2)?.source.revision, 2, "and the rounds go on under it");
    await waitFor("the restarted goal at its cap", () => goalOf(restart)?.phase === "blocked");
    await agentOf(restart).whenIdle();
    assert.equal(goalOf(restart)?.blockedReason?.code, "round-limit");
  } finally {
    await dispose?.();
    await Promise.all([rm(bots, { recursive: true, force: true }), rm(root, { recursive: true, force: true }), rm(home, { recursive: true, force: true })]);
  }
});
