import test from "node:test";
import assert from "node:assert/strict";
import { ROOM_PROJECTION_KEY, ROOM_STATE_VERSION, applyRoomEvent, initRoomState, registerRoomProjection, roomStateSchema, type RoomState } from "../src/room-projection.ts";
import type { EventLike } from "../src/room-rules.ts";

let seq = 0;
const ev = (type: string, data: unknown): EventLike => ({ type, seq: seq++, data });
const user = (id: string, text: string, source: Record<string, unknown>): EventLike =>
  ev("user/message", { id, role: "user", content: [{ type: "text", text }], source });
const dispatchCall = (to: string[], mode: string, callId = "c1"): EventLike =>
  ev("tool/call", { turn: 1, step: 1, callId, name: "dispatch", arguments: JSON.stringify({ to, mode, brief: "b", reason: "r" }) });
/** dsh's own tool-result shape (dsh-llm `createToolResultMessage`). */
const dispatchResult = (callId: string, isError: boolean): EventLike =>
  ev("tool/result", { turn: 1, step: 1, message: { id: `r-${callId}`, role: "user", content: [{ type: "tool-result", toolCallId: callId, content: [], isError }], source: { kind: "tool", callId } } });
const answerMsg = (id: string, bot: string, sessionId: string, turn: number) => ({
  id, role: "user", content: [{ type: "text", text: "view" }], source: { kind: "room", form: "answer", bot, name: bot, sessionId, turn, round: 1 },
});
const fold = (events: EventLike[]): RoomState => events.reduce(applyRoomEvent, initRoomState());

test("a session that is not a room stays `none`, by the same reference, through ordinary traffic", () => {
  const s0 = initRoomState();
  const s1 = applyRoomEvent(s0, user("u1", "hi", { kind: "user" }));
  const s2 = applyRoomEvent(s1, ev("turn/start", { turn: 1 }));
  const s3 = applyRoomEvent(s2, ev("assistant/message", { turn: 1, step: 1, message: { id: "m", role: "assistant", content: [], source: { kind: "model", provider: "p", model: "m" } } }));
  assert.equal(s3, s0, "unrelated events return the same reference (the registry's change gate)");
  assert.deepEqual(s0, { kind: "none" });
});

test("a dispatch call makes the session a room: members called, round open, mode kept", () => {
  const s = fold([user("u1", "q", { kind: "user" }), dispatchCall(["buffett", "speculator"], "parallel")]);
  assert.equal(s.kind, "room");
  assert.deepEqual(s.round, { n: 1, mode: "parallel", open: true });
  assert.deepEqual(s.members, { buffett: { state: "called" }, speculator: { state: "called" } });
});

test("answers - pending in the inbox or claimed into the log - mark the member answered with its session", () => {
  const spliced = ev("agent/inbox/spliced", { target: "next-step", start: 0, inserted: [answerMsg("a1", "buffett", "s-b", 3)] });
  const s = fold([dispatchCall(["buffett", "speculator"], "serial"), spliced]);
  assert.deepEqual(s.members?.buffett, { sessionId: "s-b", name: "buffett", state: "answered", turn: 3 });
  assert.deepEqual(s.members?.speculator, { state: "called" });
  const s2 = applyRoomEvent(s, ev("user/message", answerMsg("a1", "buffett", "s-b", 3)));
  assert.deepEqual(s2.members?.buffett, s.members?.buffett, "the claim repeats the fact, idempotently");
});

test("the round-end message closes the round with its outcome and every turn's state", () => {
  const s = fold([
    dispatchCall(["buffett", "speculator", "macro-view"], "parallel"),
    user("re", "Round 1 ended", { kind: "room", form: "round-end", round: 1, outcome: "settled", turns: [
      { bot: "buffett", name: "巴菲特型", sessionId: "s-b", state: "answered", turn: 1 },
      { bot: "speculator", name: "投机型", sessionId: "s-s", state: "passed", turn: 1 },
      { bot: "macro-view", name: "Macro View", sessionId: "s-m", state: "timed-out", turn: 1 },
    ] }),
  ]);
  assert.deepEqual(s.round, { n: 1, mode: "parallel", open: false, outcome: "settled" });
  assert.equal(s.members?.buffett.state, "answered");
  assert.equal(s.members?.speculator.state, "passed");
  assert.equal(s.members?.["macro-view"].state, "timed-out");
  assert.equal(s.members?.["macro-view"].sessionId, "s-m");
});

test("a new operator message resets the members to idle and closes the round; an `@` calls whom it names", () => {
  const before = fold([dispatchCall(["buffett"], "parallel")]);
  const plain = applyRoomEvent(before, user("u2", "new topic", { kind: "user" }));
  assert.deepEqual(plain.members, {});
  assert.equal(plain.round?.open, false);
  const mention = applyRoomEvent(plain, user("u3", "@speculator 你呢", { kind: "user", mention: ["speculator"] }));
  assert.deepEqual(mention.members, { speculator: { state: "called" } });
  assert.deepEqual(mention.round, { n: 1, mode: "mention", open: true });
  const fromNone = applyRoomEvent(initRoomState(), user("u4", "@buffett hi", { kind: "user", mention: ["buffett"] }));
  assert.equal(fromNone.kind, "room", "an `@` on a plain channel session makes it a room too");
});

test("a REFUSED dispatch leaves the state exactly as it was; an accepted one keeps its round", () => {
  /* The tool/call opens the round before `execute` has run: the round cap, a
   * roster miss and "a round is still running" all refuse AFTER it is logged. */
  const running = fold([dispatchCall(["buffett", "speculator"], "parallel", "c1"), ev("user/message", answerMsg("a1", "buffett", "s-b", 1))]);
  const refused = [dispatchCall(["macro"], "serial", "c2"), dispatchResult("c2", true)].reduce(applyRoomEvent, running);
  assert.deepEqual(refused.round, { n: 1, mode: "parallel", open: true }, "the running round is not replaced by the refused one");
  assert.deepEqual(refused.members, running.members, "and its member states stand");
  assert.equal(refused.pending, undefined);
  const quiet = [dispatchCall(["macro"], "parallel", "c3"), dispatchResult("c3", true)].reduce(applyRoomEvent, initRoomState());
  assert.deepEqual(quiet, { kind: "none" }, "a refusal on a session that was never a room shows no phantom round");
  const accepted = [dispatchCall(["buffett"], "parallel", "c4"), dispatchResult("c4", false)].reduce(applyRoomEvent, initRoomState());
  assert.deepEqual(accepted, { kind: "room", organizing: false, members: { buffett: { state: "called" } }, round: { n: 1, mode: "parallel", open: true } });
  const unrelated = applyRoomEvent(running, dispatchResult("some-other-call", true));
  assert.equal(unrelated, running, "another tool's result is not this unit's event");
});

test("an `@` folded while a round is open joins that round instead of wiping it", () => {
  /* `say` posts the operator's message and it waits in the outbox while Kairos
   * is mid-turn, so the log can carry it AFTER a dispatch that came later in
   * wall time (room.ts holds the same twin on the bus). */
  const s = fold([
    dispatchCall(["buffett", "speculator"], "parallel"),
    ev("user/message", answerMsg("a1", "buffett", "s-b", 1)),
    user("u9", "@macro 你呢", { kind: "user", mention: ["macro"] }),
  ]);
  assert.equal(s.members?.buffett.state, "answered", "the running round's states stand");
  assert.deepEqual(s.members?.macro, { state: "called" });
  assert.deepEqual(s.round, { n: 1, mode: "parallel", open: true });
});

test("a second dispatch bumps the round and forgets who was in the last one", () => {
  const s = fold([dispatchCall(["buffett"], "parallel"), dispatchCall(["speculator"], "serial")]);
  assert.deepEqual(s.round, { n: 2, mode: "serial", open: true });
  assert.deepEqual(s.members, { speculator: { state: "called" } });
});

test("Kairos's own turn boundaries drive `organizing` only once the session is a room", () => {
  const room = fold([dispatchCall(["buffett"], "parallel"), ev("turn/end", { turn: 1, reason: { kind: "completed" } })]);
  assert.equal(room.organizing, false);
  const again = applyRoomEvent(room, ev("turn/start", { turn: 2 }));
  assert.equal(again.organizing, true);
});

test("a member session folds to `member` from its first delta prompt and ignores everything else", () => {
  const s = fold([
    ev("turn/start", { turn: 1 }),
    user("d1", "You are in the room …", { kind: "room", form: "delta", room: "session-room", bot: "buffett", messageIds: ["u1"], trigger: "dispatch" }),
    dispatchCall(["x"], "parallel"), // cannot happen (masked), and must not turn a member into a room
  ]);
  assert.deepEqual(s, { kind: "member", room: "session-room", bot: "buffett" });
});

test("the state schema accepts every state the fold produces and the unit registers with the key and version", () => {
  for (const s of [initRoomState(), fold([dispatchCall(["a"], "parallel")]), fold([user("d", "x", { kind: "room", form: "delta", room: "r", bot: "b", messageIds: [], trigger: "mention" })])]) {
    assert.deepEqual(roomStateSchema.parse(s), s);
  }
  const seen: unknown[] = [];
  const dispose = registerRoomProjection({ register(definition) { seen.push(definition); return () => { seen.length = 0; }; } });
  const def = seen[0] as { key: string; stateVersion: number; init(): unknown; apply: unknown; wire: { view(s: unknown): { kind: string } } };
  assert.equal(def.key, ROOM_PROJECTION_KEY);
  assert.equal(def.stateVersion, ROOM_STATE_VERSION);
  assert.deepEqual(def.init(), { kind: "none" });
  assert.equal(def.wire.view({ kind: "none" }).kind, "none");
  assert.deepEqual(
    def.wire.view({ kind: "room", members: { buffett: { state: "called" } }, pending: { callId: "c1", kind: "none" } }),
    { kind: "room", members: { buffett: { state: "called" } } },
    "the fold's own bookkeeping never rides the wire",
  );
  dispose();
  assert.equal(seen.length, 0);
});
