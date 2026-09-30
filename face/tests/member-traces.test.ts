import assert from "node:assert/strict";
import test from "node:test";
import { loadMemberTrace } from "../client/member-traces.js";

/* The dsh 0.2.0-rc.2 wire (NEW packages/api/session-controller/src/types.ts):
 * a history record is `{type:'event', event}` (:425-429), a page is
 * `{records, hasMore}` (:546-549), a replacement names `startSeq`/`endSeq`
 * (:446-448), and a tool result is a `role:'tool'` message carrying its own
 * `toolCallId`/`isError` (NEW packages/llm/llm/src/message.ts:173-180). */
type Record_ = { type: "event"; event: { seq: number; type: string; data: Record<string, unknown>; surfaceOp?: unknown } };
const ev = (seq: number, type: string, data: Record<string, unknown>): Record_ => ({ type: "event", event: { seq, type, data } });
const start = (seq: number, turn: number) => ev(seq, "turn/start", { turn });
const end = (seq: number, turn: number) => ev(seq, "turn/end", { turn, reason: { kind: "completed" } });
const context = (seq: number, text: string, source = "plugin:fs-observation") => ev(seq, "user/message", {
  role: "user", content: [{ type: "text", text }], source: { kind: source },
});
const assistant = (seq: number, turn: number, thinking: string, text = "final answer") => ev(seq, "assistant/message", {
  turn, step: 1, message: { role: "assistant", content: [{ type: "reasoning", text: thinking }, { type: "text", text }], source: { kind: "model" } },
});
const call = (seq: number, turn: number, callId: string) => ev(seq, "tool/call", { turn, step: 1, callId, name: "bash", arguments: "{\"command\":\"cat report.csv\"}" });
const result = (seq: number, turn: number, callId: string) => ev(seq, "tool/result", {
  turn, step: 1,
  message: { id: `msg-${seq}`, role: "tool", toolCallId: callId, content: [{ type: "text", text: "done" }], isError: false, source: { kind: "tool", callId } },
});
const ref = { sessionId: "member-bear", turn: 2 };

type Call = { endpoint: string; args: Record<string, unknown> };
/** A host answering the cut read with the last seq of `records`, and one page. */
function onePage(records: Record_[], calls: Call[] = []) {
  const asOfSeq = records.reduce((max, r) => Math.max(max, r.event.seq), -1);
  return async (endpoint: string, args: Record<string, unknown>) => {
    calls.push({ endpoint, args });
    if (endpoint === "session/projections") return { asOfSeq, values: {} };
    if (endpoint === "session/page") return { records, hasMore: false };
    throw new Error(`unexpected endpoint ${endpoint}`);
  };
}

test("loads only the exact member turn's context, reasoning and tools, including final reasoning", async () => {
  const rows = await loadMemberTrace(onePage([
    start(0, 1), context(1, "old context"), assistant(2, 1, "old reasoning"), end(3, 1),
    start(4, 2), context(5, "room delta", "room"), context(6, "current context"), call(7, 2, "c1"), result(8, 2, "c1"),
    context(9, "human prompt", "user"), assistant(10, 2, "final reasoning"), end(11, 2),
    context(12, "between turns"), start(13, 3), context(14, "new context"), assistant(15, 3, "new reasoning"), end(16, 3),
  ]), ref);
  assert.deepEqual(rows.map((row) => row.seq), [5, 6, 7, 8, 10]);
  assert.ok(rows.every((row) => row.sessionId === "member-bear"));
  // No host presenter reaches the client any more (NEW packages/client/ui-tool/README.md:52):
  // the call card is identified by its own tool/call fields, not a render intent.
  assert.equal(rows[2].card?.phase, "call");
  assert.equal(rows[2].card?.name, "bash");
  assert.equal(rows[2].card?.callId, "c1");
  // The 0.2 tool result: callId and text read off the role:'tool' message itself.
  assert.equal(rows[3].card?.phase, "result");
  assert.equal(rows[3].card?.callId, "c1");
  assert.equal(rows[3].card?.text, "done");
  assert.equal(rows[4].thinking, "final reasoning");
  assert.equal(rows[4].text, "");
  assert.ok(!JSON.stringify(rows).includes("final answer"));
});

test("the read never activates the member: one projections cut, then pages through it, nothing else", async () => {
  const calls: Call[] = [];
  await loadMemberTrace(onePage([start(0, 2), assistant(1, 2, "thought"), end(2, 2)], calls), ref);
  assert.deepEqual(calls.map((c) => c.endpoint), ["session/projections", "session/page"],
    "never session/follow (it promotes a cold session), never a prompt");
  assert.deepEqual(calls[0]!.args, { request: { sessionId: "member-bear" } });
  assert.deepEqual(calls[1]!.args, {
    request: { address: { kind: "session", sessionId: "member-bear" }, throughSeq: 2, maxMessages: 100 },
  });
});

test("pages backwards past whole-message boundaries until turn/start, every page against the same cut, deduplicating overlaps", async () => {
  const records = [start(0, 1), assistant(1, 1, "old"), end(2, 1), start(3, 2), context(4, "context"),
    assistant(5, 2, "first step"), assistant(6, 2, "last step"), end(7, 2), start(8, 3), assistant(9, 3, "new"), end(10, 3)];
  const pages = [records.slice(8), records.slice(5, 9), records.slice(3, 6)];
  const requests: unknown[] = [];
  const rows = await loadMemberTrace(async (endpoint, args) => {
    if (endpoint === "session/projections") return { asOfSeq: 10, values: { agentPreset: "bear" } };
    assert.equal(endpoint, "session/page");
    requests.push(args);
    return { records: pages.shift(), hasMore: true };
  }, ref);
  const address = { kind: "session", sessionId: "member-bear" };
  assert.deepEqual(requests, [
    { request: { address, throughSeq: 10, maxMessages: 100 } },
    { request: { address, throughSeq: 10, maxMessages: 100, beforeSeq: 8 } },
    { request: { address, throughSeq: 10, maxMessages: 100, beforeSeq: 5 } },
  ]);
  assert.deepEqual(rows.map((row) => row.seq), [4, 5, 6]);
});

test("folds inclusive startSeq..endSeq replacements, including textless replacements and paired tool cards", async () => {
  // A reader of 0.1.1's `start`/`end` keys would fold nothing here and return
  // every shadowed row: the wire renamed them (types.ts:446-448).
  const replacement = context(9, "checkpoint", "compact-checkpoint");
  replacement.event.surfaceOp = { op: "replace", startSeq: 4, endSeq: 7 };
  const empty = context(11, "", "compact-checkpoint");
  empty.event.surfaceOp = { op: "replace", startSeq: 9, endSeq: 9 };
  const rows = await loadMemberTrace(onePage([
    start(2, 2), call(3, 2, "c1"), result(4, 2, "c1"), context(5, "old"), assistant(7, 2, "shadowed"),
    context(8, "retained"), replacement, assistant(10, 2, "final thinking"), empty, end(12, 2),
  ]), ref);
  assert.deepEqual(rows.map((row) => row.seq), [8, 10]);
  assert.ok(rows.every((row) => row.surfaceOp === "append"));
});

test("later replacements remove shadowed process without attributing later context to an old answer", async () => {
  const replacement = context(7, "new turn checkpoint", "compact-checkpoint");
  replacement.event.surfaceOp = { op: "replace", startSeq: 2, endSeq: 3 };
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

test("an unknown member session (projections null) is refused without paging", async () => {
  const calls: string[] = [];
  await assert.rejects(loadMemberTrace(async (endpoint) => { calls.push(endpoint); return null; }, ref), /不存在/);
  assert.deepEqual(calls, ["session/projections"]);
});

test("rejects absent turn references without calling the host and propagates read failures", async () => {
  let calls = 0;
  const failing = async () => { calls++; throw new Error("session/page: session/not-found - gone"); };
  await assert.rejects(loadMemberTrace(failing, { ...ref, turn: 0 }), /未记录/);
  await assert.rejects(loadMemberTrace(failing, { ...ref, sessionId: "" }), /未记录/);
  assert.equal(calls, 0);
  await assert.rejects(loadMemberTrace(failing, ref), /session\/not-found/);
  assert.equal(calls, 1);
});

test("malformed cuts, records and stalled pagination reject instead of silently returning partial data or looping", async () => {
  const cutThen = (page: () => unknown) => async (endpoint: string) => endpoint === "session/projections" ? { asOfSeq: 9, values: {} } : page();
  await assert.rejects(loadMemberTrace(async () => ({ values: {} }), ref), /格式无效/, "a cut without asOfSeq");
  await assert.rejects(loadMemberTrace(async () => ({ asOfSeq: -2, values: {} }), ref), /格式无效/, "throughSeq must be >= -1");
  await assert.rejects(loadMemberTrace(cutThen(() => ({})), ref), /格式无效/);
  await assert.rejects(loadMemberTrace(cutThen(() => ({ events: [], hasMore: false })), ref), /格式无效/, "0.1.1's page shape is not a 0.2 page");
  await assert.rejects(loadMemberTrace(cutThen(() => ({ records: [{ type: "event", event: { seq: "1" } }], hasMore: true })), ref), /格式无效/);
  await assert.rejects(loadMemberTrace(cutThen(() => ({ records: [{ event: { seq: 1, type: "turn/start", data: {} } }], hasMore: true })), ref), /格式无效/,
    "a record must say it is an event");
  await assert.rejects(loadMemberTrace(cutThen(() => ({ records: [], hasMore: true })), ref), /未能继续加载/);
  let pages = 0;
  await assert.rejects(loadMemberTrace(cutThen(() => {
    pages++;
    return { records: [assistant(5, 3, "unchanged page")], hasMore: true };
  }), ref), /未能继续加载/);
  assert.equal(pages, 2);
});
