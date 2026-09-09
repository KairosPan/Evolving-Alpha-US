import test from "node:test";
import assert from "node:assert/strict";
import { RoomEngine, gatePending, isQuiet, type RoomDeps } from "../src/room.ts";
import { ROOM_CAPS, type EventLike, type RosterBot } from "../src/room-rules.ts";
import { makeFakeTree, type FakeTree } from "./room-fake.ts";

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
