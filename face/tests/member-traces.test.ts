import assert from "node:assert/strict";
import test from "node:test";
import { loadMemberTrace } from "../client/member-traces.js";

type Entry = { event: { seq: number; type: string; data: Record<string, unknown>; surfaceOp?: unknown }; view?: unknown };
const ev = (seq: number, type: string, data: Record<string, unknown>): Entry => ({ event: { seq, type, data } });
const start = (seq: number, turn: number) => ev(seq, "turn/start", { turn });
const end = (seq: number, turn: number) => ev(seq, "turn/end", { turn, reason: { kind: "completed" } });
const context = (seq: number, text: string, source = "plugin") => ev(seq, "user/message", {
  role: "user", content: [{ type: "text", text }], source: { kind: source },
});
const assistant = (seq: number, turn: number, thinking: string, text = "final answer") => ev(seq, "assistant/message", {
  turn, step: 1, message: { role: "assistant", content: [{ type: "reasoning", text: thinking }, { type: "text", text }], source: { kind: "model" } },
});
const call = (seq: number, turn: number, callId: string) => ev(seq, "tool/call", { turn, step: 1, callId, name: "bash", arguments: "{}" });
const result = (seq: number, turn: number, callId: string) => ev(seq, "tool/result", {
  turn, step: 1, message: { role: "user", content: [{ type: "tool-result", toolCallId: callId, content: [{ type: "text", text: "done" }] }], source: { kind: "tool", callId } },
});
const ref = { sessionId: "member-bear", turn: 2 };
const onePage = (events: Entry[]) => async () => ({ events, hasMore: false });

test("loads only the exact member turn's context, reasoning and tools, including final reasoning", async () => {
  const tool = call(7, 2, "c1");
  tool.view = { for: "call", view: { title: "Read company data" } };
  const rows = await loadMemberTrace(onePage([
    start(0, 1), context(1, "old context"), assistant(2, 1, "old reasoning"), end(3, 1),
    start(4, 2), context(5, "room delta", "room"), context(6, "current context"), tool, result(8, 2, "c1"),
    context(9, "human prompt", "user"), assistant(10, 2, "final reasoning"), end(11, 2),
    context(12, "between turns"), start(13, 3), context(14, "new context"), assistant(15, 3, "new reasoning"), end(16, 3),
  ]), ref);
  assert.deepEqual(rows.map((row) => row.seq), [5, 6, 7, 8, 10]);
  assert.ok(rows.every((row) => row.sessionId === "member-bear"));
  assert.equal(rows[2].card?.title, "Read company data");
  assert.equal(rows[3].card?.text, "done");
  assert.equal(rows[4].thinking, "final reasoning");
  assert.equal(rows[4].text, "");
  assert.ok(!JSON.stringify(rows).includes("final answer"));
});

test("pages backwards past whole-message boundaries until turn/start and deduplicates overlapping entries", async () => {
  const events = [start(0, 1), assistant(1, 1, "old"), end(2, 1), start(3, 2), context(4, "context"),
    assistant(5, 2, "first step"), assistant(6, 2, "last step"), end(7, 2), start(8, 3), assistant(9, 3, "new"), end(10, 3)];
  const pages = [events.slice(8), events.slice(5, 9), events.slice(3, 6)];
  const requests: Record<string, unknown>[] = [];
  const rows = await loadMemberTrace(async (method, payload) => {
    assert.equal(method, "session.history");
    requests.push(payload);
    return { events: pages.shift(), hasMore: true };
  }, ref);
  assert.deepEqual(requests, [
    { sessionId: "member-bear", maxMessages: 100 },
    { sessionId: "member-bear", maxMessages: 100, beforeSeq: 8 },
    { sessionId: "member-bear", maxMessages: 100, beforeSeq: 5 },
  ]);
  assert.deepEqual(rows.map((row) => row.seq), [4, 5, 6]);
});

test("folds inclusive replacements, including textless replacements and paired tool cards", async () => {
  const replacement = context(9, "checkpoint");
  replacement.event.surfaceOp = { op: "replace", start: 4, end: 7 };
  const empty = context(11, "");
  empty.event.surfaceOp = { op: "replace", start: 9, end: 9 };
  const rows = await loadMemberTrace(onePage([
    start(2, 2), call(3, 2, "c1"), result(4, 2, "c1"), context(5, "old"), assistant(7, 2, "shadowed"),
    context(8, "retained"), replacement, assistant(10, 2, "final thinking"), empty, end(12, 2),
  ]), ref);
  assert.deepEqual(rows.map((row) => row.seq), [8, 10]);
  assert.ok(rows.every((row) => row.surfaceOp === "append"));
});

test("later replacements remove shadowed process without attributing later context to an old answer", async () => {
  const replacement = context(7, "new turn checkpoint");
  replacement.event.surfaceOp = { op: "replace", start: 2, end: 3 };
  const rows = await loadMemberTrace(onePage([
    start(1, 2), context(2, "old context"), assistant(3, 2, "old reasoning"), end(4, 2),
    start(5, 3), replacement, assistant(8, 3, "new reasoning"), end(9, 3),
  ]), ref);
  assert.deepEqual(rows, []);
});

test("an answer with no recorded process returns an empty list", async () => {
  assert.deepEqual(await loadMemberTrace(onePage([start(0, 2), assistant(1, 2, ""), end(2, 2)]), ref), []);
});

test("excludes events explicitly tagged with another turn even inside the requested bracket", async () => {
  const rows = await loadMemberTrace(onePage([start(0, 2), assistant(1, 1, "wrong turn"), call(2, 3, "wrong"), end(3, 2)]), ref);
  assert.deepEqual(rows, []);
});

test("missing or incomplete exact turns never fall back to the newest member trace", async () => {
  await assert.rejects(loadMemberTrace(onePage([start(0, 3), assistant(1, 3, "new"), end(2, 3)]), ref), /未找到/);
  await assert.rejects(loadMemberTrace(onePage([assistant(1, 2, "partial"), end(2, 2)]), ref), /未找到/);
  await assert.rejects(loadMemberTrace(onePage([start(0, 2), assistant(1, 2, "partial")]), ref), /不完整/);
  await assert.rejects(loadMemberTrace(onePage([start(0, 2), start(1, 3), end(2, 2)]), ref), /不完整/);
});

test("rejects absent turn references without calling the host and propagates history failures", async () => {
  let calls = 0;
  const rpc = async () => { calls++; throw new Error("history unavailable"); };
  await assert.rejects(loadMemberTrace(rpc, { ...ref, turn: 0 }), /未记录/);
  await assert.rejects(loadMemberTrace(rpc, { ...ref, sessionId: "" }), /未记录/);
  assert.equal(calls, 0);
  await assert.rejects(loadMemberTrace(rpc, ref), /history unavailable/);
  assert.equal(calls, 1);
});

test("malformed and stalled pagination reject instead of silently returning partial data or looping", async () => {
  await assert.rejects(loadMemberTrace(async () => ({}), ref), /格式无效/);
  await assert.rejects(loadMemberTrace(async () => ({ events: [{ event: { seq: "1" } }], hasMore: true }), ref), /格式无效/);
  await assert.rejects(loadMemberTrace(async () => ({ events: [], hasMore: true }), ref), /未能继续加载/);
  let calls = 0;
  await assert.rejects(loadMemberTrace(async () => {
    calls++;
    return { events: [assistant(5, 3, "unchanged page")], hasMore: true };
  }, ref), /未能继续加载/);
  assert.equal(calls, 2);
});
