import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { RoomEngine, dispatchToolDefinition, gatePending, installRoom, isQuiet, registerRoomRoutes, type RoomDeps } from "../src/room.ts";
import { ROOM_CAPS, type EventLike, type RosterBot } from "../src/room-rules.ts";
import { setBots } from "../src/roster.ts";
import { makeFakeTree, type FakeTree } from "./room-fake.ts";
import { recorder } from "./route-recorder.ts";

const CHANNEL = { workspaceId: "ws-1", name: "storage-chain", dir: "/repo/strategies/storage-chain" };
const roster: RosterBot[] = [
  { id: "buffett", name: "巴菲特型", model: "stub/echo" },
  { id: "speculator", name: "投机型" },
  { id: "macro", name: "Macro View" },
];

function engineOn(tree: FakeTree, over: Partial<RoomDeps> = {}): RoomEngine {
  return new RoomEngine({
    ctx: tree.ctx as unknown as RoomDeps["ctx"],
    home: "/nowhere",
    channelFor: async (cwd) => (cwd === CHANNEL.dir ? CHANNEL : null),
    listBots: async () => roster.map((b) => ({ ...b })),
    clock: tree.clock,
    installModelSelection: (agentCtx, ref) => { tree.selections.push({ agent: (agentCtx as { agent: { id: string } }).agent.id, selection: ref.current }); return () => {}; },
    log: () => {},
    ...over,
  });
}
const sources = (events: readonly EventLike[]) => events.filter((e) => e.type === "user/message").map((e) => (e.data as { source: Record<string, unknown> }).source);

test("ensureMember creates a member once: root-created, parented, preset-joined, read-only before publish, attached to the channel, model from preset.yml", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const [a, b] = await Promise.all([engine.ensureMember(room, roster[0]), engine.ensureMember(room, roster[0])]);
  assert.equal(a, b, "concurrent ensures share one creation");
  assert.equal(tree.agentsCreated.length, 1);
  const created = tree.agentsCreated[0] as { sessionId: string; meta: Record<string, unknown>; agentOptions: unknown };
  assert.match(created.sessionId, /^session-[0-9a-f-]{36}$/);
  assert.deepEqual(created.meta, { cwd: CHANNEL.dir, parentSession: "session-room", agentPreset: "buffett" });
  assert.deepEqual(created.agentOptions, { provider: "stub", model: "echo" }, "preset.yml's route, served, is the member's");
  assert.deepEqual(tree.mounts, [{ agent: created.sessionId, preset: "buffett" }]);
  assert.deepEqual(tree.selections[0].selection, { provider: "stub", model: "echo" });
  assert.equal(tree.ctx.permissionPresets.current(a.agent.session.events), "read-only");
  assert.equal(a.agent.session.events[0].type, "permission/preset", "the pin is the session's first fact - inside setup, before publish (a fresh session has no end-seed marker)");
  assert.deepEqual(tree.attached, [created.sessionId]);
});

test("an unserved preset.yml route falls back to the default with a note; no route at all is the default silently", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const odd = await engine.ensureMember(room, { id: "speculator", name: "投机型", model: "nope/x" });
  assert.deepEqual((tree.agentsCreated[0] as { agentOptions: unknown }).agentOptions, { provider: "deepseek-official", model: "deepseek-v4-flash" });
  assert.match(engine.noteFor(room, "speculator") ?? "", /nope\/x is not served/);
  await engine.ensureMember(room, roster[2]);
  assert.equal(engine.noteFor(room, "macro"), undefined);
  assert.ok(odd);
});

test("a member that already exists on disk is RESUMED, never recreated - by the answer in the room log, else by its header", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  tree.persistMember("session-old", "session-room", "buffett", CHANNEL.dir);
  tree.persistMember("session-fork", "session-room", "kairos", CHANNEL.dir); // a fork of the room: kairos preset, never a member
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const m = await engine.ensureMember(room, roster[0]);
  assert.equal(m.agent.id, "session-old");
  assert.equal(tree.agentsCreated.length, 0);
  assert.equal(tree.resumed.length, 1);
  assert.deepEqual(tree.mounts, [{ agent: "session-old", preset: "buffett" }], "a resume joins the preset again in its own setup");
  // a second room-runtime (say, after the engine was rebuilt) finds the same session through the log
  const engine2 = engineOn(tree);
  kairos.session.append("user/message", { id: "a1", role: "user", content: [{ type: "text", text: "view" }], source: { kind: "room", form: "answer", bot: "buffett", name: "巴菲特型", sessionId: "session-old", turn: 1, round: 1 } }, { surfaceOp: "append" });
  const again = await engine2.ensureMember(engine2.roomOf("session-room", CHANNEL), roster[0]);
  assert.equal(again.agent.id, "session-old", "already live: neither created nor resumed");
  assert.equal(tree.resumed.length, 1);
});

test("a member whose preset is gone fails visibly at ensure, with dsh's reason", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  tree.brokenPresets.add("buffett");
  const engine = engineOn(tree);
  await assert.rejects(engine.ensureMember(engine.roomOf("session-room", CHANNEL), roster[0]), /broken: not a list/);
});

test("one driven turn: the member gets the attributed delta with the rules, its final text comes back, and its own log carries the cursor", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  kairos.session.append("user/message", { id: "u1", role: "user", content: [{ type: "text", text: "SanDisk 值得买吗" }], source: { kind: "user" } }, { surfaceOp: "append" });
  tree.script("buffett", (message) => ({ kind: "answer", text: `I read: ${message.content[0].text?.includes("SanDisk 值得买吗") ? "yes" : "no"}. 买` }));
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const member = await engine.ensureMember(room, roster[0]);
  const turn = engine.runMemberTurn(room, member, roster, "dispatch", "state a view");
  await tree.clock.advance(50);
  const result = await turn;
  assert.equal(result.record.state, "answered");
  assert.equal(result.text, "I read: yes. 买");
  assert.equal(result.record.turn, 1);
  const prompt = member.agent.session.events.find((e) => e.type === "user/message")!.data as { content: { text: string }[]; source: Record<string, unknown> };
  assert.match(prompt.content[0].text, /操作员: SanDisk 值得买吗/);
  assert.match(prompt.content[0].text, /Kairos asks this batch: state a view/);
  assert.match(prompt.content[0].text, /exactly \(pass\)/);
  assert.deepEqual(prompt.source, { kind: "room", form: "delta", room: "session-room", bot: "buffett", messageIds: ["u1"], trigger: "dispatch", brief: "state a view" });
  // the cursor: a second turn with nothing new says so
  const second = engine.runMemberTurn(room, member, roster, "mention");
  await tree.clock.advance(50);
  const prompt2 = member.agent.session.events.filter((e) => e.type === "user/message")[1].data as { content: { text: string }[]; source: { messageIds: string[] } };
  assert.match(prompt2.content[0].text, /\(nothing new\)/);
  assert.deepEqual(prompt2.source.messageIds, []);
  await second;
});

test("final-text rule on a tool-using turn; an empty or (pass) text is passed; an error turn is failed and the round goes on", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "after the tool", toolFirst: true }));
  tree.script("speculator", () => ({ kind: "answer", text: "(pass)" }));
  tree.script("macro", () => ({ kind: "error", message: "NO_ADAPTER" }));
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const results = Promise.all(roster.map(async (b) => engine.runMemberTurn(room, await engine.ensureMember(room, b), roster, "dispatch", "q")));
  await tree.clock.advance(50);
  const [a, s, m] = await results;
  assert.equal(a.text, "after the tool");
  assert.equal(s.record.state, "passed");
  assert.equal(m.record.state, "failed");
  assert.match(m.record.reason ?? "", /NO_ADAPTER/);
});

test("deadlines: the base timeout extends while the member runs or has a gate pending, and the hard cap cancels with keepInbox", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "hang" }));
  tree.script("speculator", () => ({ kind: "gate" }));
  tree.script("macro", () => ({ kind: "answer", text: "slow but fine", afterMs: ROOM_CAPS.turnTimeoutMs * 2 + 5 }));
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const hang = engine.runMemberTurn(room, await engine.ensureMember(room, roster[0]), roster, "dispatch", "q");
  const gate = engine.runMemberTurn(room, await engine.ensureMember(room, roster[1]), roster, "dispatch", "q");
  const slow = engine.runMemberTurn(room, await engine.ensureMember(room, roster[2]), roster, "dispatch", "q");
  await tree.clock.advance(ROOM_CAPS.turnTimeoutMs + 10);
  assert.equal(tree.agents.get(tree.agentsCreated.map((c) => (c as { sessionId: string }).sessionId)[0])!.cancelled.length, 0, "still running at the base timeout: extended, not cancelled");
  await tree.clock.advance(ROOM_CAPS.turnTimeoutMs + 10);
  const slowResult = await slow;
  assert.equal(slowResult.record.state, "answered", "a running member that answers inside the hard cap is answered");
  await tree.clock.advance(ROOM_CAPS.turnHardCapMs);
  const [h, g] = await Promise.all([hang, gate]);
  assert.equal(h.record.state, "timed-out");
  assert.equal(g.record.state, "timed-out", "a pending gate extends the base timeout but never the hard cap (R6)");
  for (const id of tree.agentsCreated.slice(0, 2).map((c) => (c as { sessionId: string }).sessionId)) {
    const agent = tree.agents.get(id)!;
    assert.equal(agent.cancelled.length, 1);
    assert.deepEqual(agent.cancelled[0].cause, { kind: "hook", reason: "room: turn hard cap reached" });
    assert.deepEqual(agent.cancelled[0].options, { keepInbox: true });
  }
});

test("post: an answer is appended to the room log at once while no Kairos turn is open, and held until turn/end otherwise", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  const engine = engineOn(tree);
  const room = engine.roomOf("session-room", CHANNEL);
  const msg = (id: string) => ({ id, role: "user" as const, content: [{ type: "text", text: "v" }], source: { kind: "room", form: "answer", bot: "buffett", name: "巴菲特型", sessionId: "s", turn: 1, round: 1 } });
  engine.post(room, msg("a1"));
  assert.deepEqual(sources(kairos.session.events).map((s) => s.form), ["answer"], "quiet room: appended now");
  kairos.wake(); // Kairos opens a turn
  engine.post(room, msg("a2"));
  assert.equal(sources(kairos.session.events).length, 1, "a turn is open: held");
  kairos.sleep();
  await tree.clock.flush();
  assert.equal(sources(kairos.session.events).length, 2, "flushed on turn/end");
  assert.equal(kairos.session.events.at(-1)!.type, "user/message");
});

test("gatePending reads an open ask or an undecided approval from the member's own log; isQuiet reads the last turn boundary", () => {
  const events: EventLike[] = [
    { type: "turn/start", seq: 0, data: { turn: 1 } },
    { type: "tool/call", seq: 1, data: { turn: 1, step: 1, callId: "q1", name: "ask_user_question", arguments: "{}" } },
  ];
  assert.equal(gatePending(events, 1), true);
  assert.equal(gatePending(events, 2), false);
  events.push({ type: "tool/result", seq: 2, data: { turn: 1, step: 1, message: { id: "r", role: "user", content: [{ type: "tool-result", toolCallId: "q1", content: [] }], source: { kind: "tool", callId: "q1" } } } });
  assert.equal(gatePending(events, 1), false);
  events.push({ type: "approval/asked", seq: 3, data: { id: "ap1", toolName: "bash" } });
  assert.equal(gatePending(events, 1), true);
  events.push({ type: "approval/decided", seq: 4, data: { id: "ap1", outcome: "rejected" } });
  assert.equal(gatePending(events, 1), false);
  const session = { id: "s", header: {}, events, seq: events.length, append: () => undefined };
  assert.equal(isQuiet(session), false, "turn 1 is still open");
  events.push({ type: "turn/end", seq: 5, data: { turn: 1, reason: { kind: "completed" } } });
  assert.equal(isQuiet(session), true);
  assert.equal(isQuiet({ ...session, events: [] }), true, "an empty log is quiet");
});

const answers = (events: readonly EventLike[]) => sources(events).filter((s) => s.kind === "room" && s.form === "answer").map((s) => s.bot);
const roundEnds = (events: readonly EventLike[]) => sources(events).filter((s) => s.kind === "room" && s.form === "round-end");

test("a parallel round: every member gets the same delta and sees no peer this round; answers land in the room log; Kairos is woken once with who spoke and who passed", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  kairos.session.append("user/message", { id: "u1", role: "user", content: [{ type: "text", text: "开会" }], source: { kind: "user" } }, { surfaceOp: "append" });
  const prompts: Record<string, string> = {};
  tree.script("buffett", (m) => { prompts.buffett = m.content[0].text ?? ""; return { kind: "answer", text: "买", afterMs: 20 }; });
  tree.script("speculator", (m) => { prompts.speculator = m.content[0].text ?? ""; return { kind: "answer", text: "(pass)", afterMs: 5 }; });
  const engine = engineOn(tree);
  const out = await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "parallel", brief: "各说各的", reason: "first views" }, roster);
  assert.deepEqual(out, { round: 1, remainingRounds: 2, notCalled: ["macro"], notes: [] });
  await tree.clock.advance(100);
  assert.doesNotMatch(prompts.buffett, /投机型:/, "parallel: no peer answer this round");
  assert.doesNotMatch(prompts.speculator, /巴菲特型:/);
  assert.deepEqual(answers(kairos.session.events), ["buffett"], "a pass is not an answer");
  assert.equal(kairos.inbox.nextTurn.length, 1, "woken exactly once");
  const end = kairos.inbox.nextTurn[0];
  assert.deepEqual(end.source.form, "round-end");
  assert.equal((end.source as unknown as { outcome: string }).outcome, "settled");
  assert.deepEqual((end.source as unknown as { turns: { bot: string; state: string }[] }).turns.map((t) => `${t.bot}:${t.state}`), ["speculator:passed", "buffett:answered"]);
  assert.match(end.content[0].text ?? "", /Answered: 巴菲特型\. Passed: 投机型\./);
  assert.ok(kairos.session.events.findIndex((e) => (e.data as { source?: { form?: string } })?.source?.form === "answer") >= 0, "the answer is in the log BEFORE the wake is queued");
});

test("a serial round: the later member's delta carries the earlier answer", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  const prompts: Record<string, string> = {};
  tree.script("buffett", () => ({ kind: "answer", text: "买" }));
  tree.script("speculator", (m) => { prompts.speculator = m.content[0].text ?? ""; return { kind: "answer", text: "卖" }; });
  const engine = engineOn(tree);
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "serial", brief: "q", reason: "r" }, roster);
  await tree.clock.advance(100);
  assert.match(prompts.speculator, /巴菲特型: 买/);
});

test("a serial round: a peer @ in the first answer never gives an already-dispatched voice a second turn", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  const turns: string[] = [];
  tree.script("buffett", (m, turn) => { turns.push(`buffett:${turn}`); return { kind: "answer", text: "@speculator 你呢" }; });
  tree.script("speculator", (m, turn) => { turns.push(`speculator:${turn}`); return { kind: "answer", text: "卖" }; });
  const engine = engineOn(tree);
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "serial", brief: "q", reason: "r" }, roster);
  await tree.clock.advance(200);
  assert.deepEqual(turns, ["buffett:1", "speculator:1"], "the peer's own dispatched turn is its one turn this round");
  assert.deepEqual(answers(kairos.session.events), ["buffett", "speculator"]);
  const end = kairos.inbox.nextTurn[0];
  assert.equal((end.source as unknown as { turns: unknown[] }).turns.length, 2);
  assert.match(end.content[0].text ?? "", /Answered: 巴菲特型, 投机型\./);
});

test("a peer @ queues one continuation after the dispatched turns, bounded, and Kairos is woken after it", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  let macroTurns = 0;
  tree.script("buffett", () => ({ kind: "answer", text: "@macro 你怎么看 @macro 再说一次" }));
  tree.script("speculator", () => ({ kind: "answer", text: "@macro @buffett @speculator" }));
  tree.script("macro", (m, turn) => { macroTurns = turn; return { kind: "answer", text: `macro turn ${turn}: ${m.content[0].text?.includes("continuation") ? "cont" : "plain"}` }; });
  const engine = engineOn(tree);
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "parallel", brief: "q", reason: "r" }, roster);
  await tree.clock.advance(200);
  assert.equal(macroTurns, 1, "one continuation for macro however many peers named it");
  assert.deepEqual(answers(kairos.session.events).sort(), ["buffett", "macro", "speculator"]);
  const end = kairos.inbox.nextTurn[0];
  assert.equal((end.source as unknown as { turns: unknown[] }).turns.length, 3);
  assert.ok(kairos.session.events.filter((e) => (e.data as { source?: { form?: string } })?.source?.form === "answer").length === 3, "all three answers precede the wake");
});

test("a round that runs while Kairos is mid-turn: the answers are held, and they are all in the log before the one wake", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  kairos.wake(); // Kairos is mid-turn: the room log is not quiet
  tree.script("buffett", () => ({ kind: "answer", text: "买", afterMs: 10 }));
  tree.script("speculator", () => ({ kind: "answer", text: "卖", afterMs: 5 }));
  const engine = engineOn(tree);
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "parallel", brief: "q", reason: "r" }, roster);
  await tree.clock.advance(100);
  assert.deepEqual(answers(kairos.session.events), [], "held while a turn is open");
  assert.equal(kairos.inbox.nextTurn.length, 0, "and no wake while the round cannot land its answers");
  kairos.sleep();
  await tree.clock.advance(10);
  assert.deepEqual(answers(kairos.session.events).sort(), ["buffett", "speculator"], "flushed on turn/end");
  assert.equal(kairos.inbox.nextTurn.length, 1, "then woken once");
  assert.equal((kairos.inbox.nextTurn[0].source as unknown as { outcome: string }).outcome, "settled");
});

test("caps: the round cap refuses a fourth dispatch; the bot-message cap ends a round capped; a new operator send resets both", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  for (const b of roster) tree.script(b.id, () => ({ kind: "answer", text: "v" }));
  const engine = engineOn(tree, { caps: { maxBotMessages: 4, maxRounds: 2 } });
  const args = { to: ["buffett", "speculator", "macro"], mode: "parallel" as const, brief: "q", reason: "r" };
  await engine.dispatch("session-room", CHANNEL, args, roster);
  await tree.clock.advance(100);
  await engine.dispatch("session-room", CHANNEL, args, roster);
  await tree.clock.advance(100);
  const ends = roundEnds(kairos.session.events.concat(kairos.inbox.nextTurn.map((m, i) => ({ type: "user/message", seq: 1000 + i, data: m }))));
  assert.deepEqual(ends.map((e) => e.outcome), ["settled", "capped"], "round 2 ran one turn of three before the message cap");
  await assert.rejects(engine.dispatch("session-room", CHANNEL, args, roster), /round cap/);
  // the operator speaks: the gateway logs a user message on the room
  kairos.session.append("user/message", { id: "u2", role: "user", content: [{ type: "text", text: "再来" }], source: { kind: "user" } }, { surfaceOp: "append" });
  await tree.clock.flush();
  const out = await engine.dispatch("session-room", CHANNEL, args, roster);
  assert.equal(out.round, 1);
});

test("a dispatch while a round is running is refused; an operator message mid-round supersedes it - running turns finish, nothing further starts", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "slow", afterMs: 50 }));
  tree.script("speculator", () => ({ kind: "answer", text: "@macro", afterMs: 10 }));
  tree.script("macro", () => ({ kind: "answer", text: "never" }));
  const engine = engineOn(tree);
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett", "speculator"], mode: "parallel", brief: "q", reason: "r" }, roster);
  await assert.rejects(engine.dispatch("session-room", CHANNEL, { to: ["macro"], mode: "parallel", brief: "q", reason: "r" }, roster), /still running|not settled/);
  await tree.clock.advance(20);
  kairos.session.append("user/message", { id: "u2", role: "user", content: [{ type: "text", text: "换个话题" }], source: { kind: "user" } }, { surfaceOp: "append" });
  await tree.clock.advance(200);
  assert.deepEqual(answers(kairos.session.events).sort(), ["buffett", "speculator"], "the running turn finished and landed; the continuation never started");
  const end = kairos.inbox.nextTurn[0];
  assert.equal((end.source as unknown as { outcome: string }).outcome, "superseded");
});

test("say: an @ is the operator's message, appended to the room, not a prompt; the named members turn; an @ to a running member is queued", async () => {
  const tree = makeFakeTree();
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  const turns: string[] = [];
  tree.script("buffett", (m, turn) => { turns.push(`buffett:${turn}`); return { kind: "answer", text: "b", afterMs: 30 }; });
  tree.script("speculator", (m, turn) => { turns.push(`speculator:${turn}`); return { kind: "answer", text: "s" }; });
  const engine = engineOn(tree);
  engine.rosterFor = async () => roster; // the roster read is the file's; stub it here
  const first = await engine.say("session-room", "@buffett @speculator 你们怎么看");
  assert.deepEqual(first.addressed, ["buffett", "speculator"]);
  assert.deepEqual(sources(kairos.session.events).at(-1), { kind: "user", mention: ["buffett", "speculator"] }, "in the room log as the operator's, with whom it addressed");
  assert.equal(kairos.inbox.nextTurn.length, 0, "Kairos is not prompted");
  const second = await engine.say("session-room", "@buffett 补一句");
  assert.deepEqual(second.addressed, ["buffett"]);
  await tree.clock.advance(100);
  assert.deepEqual(turns, ["buffett:1", "speculator:1", "buffett:2"], "the second @ ran after the first turn, never refused");
  assert.deepEqual(answers(kairos.session.events), ["speculator", "buffett", "buffett"]);
  assert.equal(kairos.inbox.nextTurn.length, 0, "no round-end for @ turns");
  const none = await engine.say("session-room", "no mention at all");
  assert.deepEqual(none, { addressed: [] });
  assert.equal(tree.modelsCalls.length, 0, "a live room needs no resume");
});

test("say on a cold room resumes it through the gateway's own composition before touching it", async () => {
  const tree = makeFakeTree();
  const engine = engineOn(tree);
  engine.rosterFor = async () => roster;
  tree.persisted.push({ id: "session-cold", cwd: CHANNEL.dir, agentPreset: "kairos", createdAt: 1 });
  tree.ctx.apiProxy.sessions.models = async (request: { payload: { sessionId: string } }) => { tree.modelsCalls.push(request.payload.sessionId); tree.newRoom(request.payload.sessionId, CHANNEL.dir); return { ok: true }; };
  tree.script("buffett", () => ({ kind: "answer", text: "b" }));
  const out = await engine.say("session-cold", "@buffett hi");
  assert.deepEqual(out.addressed, ["buffett"]);
  assert.deepEqual(tree.modelsCalls, ["session-cold"]);
});

test("rosterFor refuses a channel with no roster row and an unreadable roster file, each with the repair the operator needs", async () => {
  const tree = makeFakeTree();
  await assert.rejects(engineOn(tree).rosterFor(CHANNEL), /has no roster yet/, "an absent file is not corrupt - the channel simply has no row");
  const home = mkdtempSync(join(tmpdir(), "room-roster-"));
  mkdirSync(join(home, "face"), { recursive: true });
  writeFileSync(join(home, "face", "channels.json"), "{not json", "utf8");
  await assert.rejects(engineOn(tree, { home }).rosterFor(CHANNEL), /roster is unreadable/);
  writeFileSync(join(home, "face", "channels.json"), JSON.stringify({ channels: { "ws-1": { agents: [], bots: ["buffett", "macro"] } } }), "utf8");
  assert.deepEqual((await engineOn(tree, { home }).rosterFor(CHANNEL)).map((b) => `${b.id}:${b.name}`), ["buffett:巴菲特型", "macro:Macro View"], "the file's ids, named by the bot roster");
});

test("say refuses when the gateway's resume leaves the room session cold", async () => {
  const tree = makeFakeTree();
  const engine = engineOn(tree);
  engine.rosterFor = async () => roster;
  tree.persisted.push({ id: "session-cold", cwd: CHANNEL.dir, agentPreset: "kairos", createdAt: 1 });
  tree.ctx.apiProxy.sessions.models = async (request: { payload: { sessionId: string } }) => { tree.modelsCalls.push(request.payload.sessionId); return { ok: true }; };
  await assert.rejects(engine.say("session-cold", "@buffett hi"), /no such session/);
  assert.deepEqual(tree.modelsCalls, ["session-cold"], "the resume was attempted, once");
});

test("describe reports the roster, the runtime members and the caps left", async () => {
  const tree = makeFakeTree();
  tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "b" }));
  const engine = engineOn(tree);
  engine.rosterFor = async () => roster;
  await engine.dispatch("session-room", CHANNEL, { to: ["buffett"], mode: "parallel", brief: "q", reason: "r" }, roster);
  await tree.clock.advance(50);
  const d = await engine.describe("session-room");
  assert.deepEqual(d.roster.map((b) => b.id), ["buffett", "speculator", "macro"]);
  assert.equal(Object.keys(d.members).length, 1);
  assert.match(d.members.buffett.sessionId, /^session-/);
  assert.deepEqual(d.caps, { roundsLeft: 2, messagesLeft: 9, maxRounds: 3, maxBotMessages: 10 });
});

/* ---------- the tool, the install and the two routes (Task 8) ---------- */

/** A room session id the face's own `SESSION_ID_RE` accepts (the routes check it). */
const ROOM_ID = "session-2f0f4e2c-9d61-4c0e-8b7a-3f8a1c2d4e5f";
const NO_CHANNEL_ID = "session-11111111-2222-4333-8444-555555555555";

test("the dispatch tool: global, Kairos-only, channel-only, roster-checked; validates, starts the round and names who was not called", async () => {
  const tree = makeFakeTree();
  const home = await mkdtemp(join(tmpdir(), "face-room-"));
  await setBots(home, CHANNEL.workspaceId, ["buffett", "speculator"]);
  const kairos = tree.newRoom("session-room", CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "b" }));
  const engine = installRoom({
    ctx: tree.ctx as unknown as RoomDeps["ctx"], home,
    channelFor: async (cwd) => (cwd === CHANNEL.dir ? CHANNEL : null),
    listBots: async () => roster, clock: tree.clock, installModelSelection: () => () => {}, log: () => {},
  });
  assert.deepEqual(tree.registeredTools.map((t) => t.name), ["dispatch"]);
  const tool = tree.registeredTools[0] as unknown as ReturnType<typeof dispatchToolDefinition>;
  assert.match(tool.description, /roster/);
  assert.match(tool.description, /end your turn/i);
  const exec = (agent: unknown) => ({ agent, signal: new AbortController().signal }) as never;

  await assert.rejects(tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "r" }, exec(undefined)), /needs a session/);
  const bot = { id: "session-bot", status: "idle", session: { id: "session-bot", header: { cwd: CHANNEL.dir, agentPreset: "buffett" }, events: [], seq: 0 } };
  await assert.rejects(tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "r" }, exec(bot)), /Kairos's tool/);
  const nowhere = { ...kairos, session: { ...kairos.session, header: { cwd: "/elsewhere", agentPreset: "kairos" } } };
  await assert.rejects(tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "r" }, exec(nowhere)), /in no channel/);
  await assert.rejects(tool.execute({ to: ["macro"], mode: "parallel", brief: "q", reason: "r" }, exec(kairos)), /macro is not on this channel's roster.*buffett, speculator/);

  const value = await tool.execute({ to: ["buffett"], mode: "parallel", brief: "q", reason: "first" }, exec(kairos)) as { text: string; round: number; notCalled: string[] };
  assert.equal(value.round, 1);
  assert.deepEqual(value.notCalled, ["speculator"]);
  const rendered = tool.output.render({}, value)[0].text;
  assert.match(rendered, /Dispatched 巴菲特型 \(parallel\)/);
  assert.match(rendered, /Not called: 投机型\./);
  assert.deepEqual(tool.presentCall({ to: ["buffett"], mode: "parallel", brief: "q", reason: "first" }), { card: "generic", title: "dispatch buffett (parallel)", kind: "read", rawInput: "first" });
  await tree.clock.advance(100);
  assert.equal(kairos.inbox.nextTurn.length, 1);
  engine.dispose();
  assert.equal(tree.registeredTools.length, 0, "dispose unregisters the tool");
  assert.equal(tree.listeners.length, 0, "and the bus listener");
});

test("the two routes: say and state, fenced like every /data route", async () => {
  const tree = makeFakeTree();
  const home = await mkdtemp(join(tmpdir(), "face-room-"));
  await setBots(home, CHANNEL.workspaceId, ["buffett"]);
  tree.newRoom(ROOM_ID, CHANNEL.dir);
  tree.script("buffett", () => ({ kind: "answer", text: "b" }));
  const engine = installRoom({
    ctx: tree.ctx as unknown as RoomDeps["ctx"], home,
    channelFor: async (cwd) => (cwd === CHANNEL.dir ? CHANNEL : null),
    listBots: async () => roster, clock: tree.clock, installModelSelection: () => () => {}, log: () => {},
  });
  const routes = recorder();
  registerRoomRoutes(routes, engine);
  assert.deepEqual(routes.paths(), ["/data/rooms/say", "/data/rooms/state"]);
  const forged = JSON.parse(await routes.call("/data/rooms/say", { method: "POST", json: { sessionId: ROOM_ID, text: "@buffett" }, host: "evil.example.com" }));
  assert.equal(forged.status, 403);
  const bad = JSON.parse(await routes.call("/data/rooms/say", { method: "POST", json: { sessionId: "nope", text: "@buffett" } }));
  assert.equal(bad.status, 400);
  const said = JSON.parse(await routes.call("/data/rooms/say", { method: "POST", json: { sessionId: ROOM_ID, text: "@buffett hi" } }));
  assert.equal(said.status, 200);
  assert.deepEqual(said.body.addressed, ["buffett"]);
  await tree.clock.advance(50);
  const state = JSON.parse(await routes.call("/data/rooms/state", { method: "POST", json: { sessionId: ROOM_ID } }));
  assert.equal(state.status, 200);
  assert.deepEqual(state.body.roster.map((b: { id: string }) => b.id), ["buffett"]);
  assert.ok(state.body.members.buffett.sessionId);
  const nowhere = JSON.parse(await routes.call("/data/rooms/state", { method: "POST", json: { sessionId: NO_CHANNEL_ID } }));
  assert.equal(nowhere.status, 404);
});
