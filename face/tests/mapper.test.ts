/** The tested half of the client: the pure frame → view-model mapping.
 *
 * The fixtures are real wire frames, not sketches — each line is what the
 * dsh 0.2.0-rc.2 host delivers on `/api/remote.mux` (a `$events` gate or
 * withdrawal, a `session/control` projection, a `session/follow` snapshot or
 * assistant-stream frame, a mux error frame), or a follow event after the one
 * normalization chat.js performs, `{type:"session/event", sessionId, event}`.
 * Every session event in the file passes upstream's own client acceptance
 * (NEW packages/api/session-controller/src/client/session-wire-event.ts
 * `assertSessionWireEvent`), which rejects the 0.1.1 shapes this file used to hold.
 * Line numbers below are 1-based file lines; the array indexes are 0-based.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
// mapper.js is plain ESM JS (it ships to the browser); tsconfig `allowJs`
// lets this test import it and read its JSDoc-declared view-model type.
import { mapFrame } from "../client/mapper.js";

const frames: unknown[] = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "fixtures", "events.jsonl"),
  "utf8",
).trim().split("\n").map((line) => JSON.parse(line) as unknown);

const views = frames.map((frame) => mapFrame(frame));

test("fixture file and view list stay aligned", () => {
  assert.equal(frames.length, 26);
  assert.equal(views.length, 26);
});

test("every fixture line is a 0.2.0 frame: no 0.1.1 envelope or untyped history entry survives", () => {
  const known = new Set(["session/event", "assistant-stream", "waterfall", "cancel", "projection", "snapshot", "error"]);
  frames.forEach((frame, i) => {
    const type = (frame as { type?: unknown }).type;
    assert.ok(typeof type === "string" && known.has(type), `line ${i + 1} has frame type ${String(type)}`);
  });
});

test("message events become bubbles, attributed by role", () => {
  assert.equal(views[0].kind, "bubble");
  assert.equal(views[0].role, "operator");
  assert.match(views[0].text ?? "", /pivot/);
  assert.equal(views[0].seq, 4);
  assert.equal(views[0].sessionId, "s1");

  assert.equal(views[1].kind, "bubble");
  assert.equal(views[1].role, "kairos");
  assert.equal(views[1].text, "Both pivots are technically valid.");
  // Reasoning is not chat text: it rides the view on its own field, never the bubble.
  assert.doesNotMatch(views[1].text ?? "", /200DMA/);
  assert.equal(views[1].thinking, "weigh both against the 200DMA");
  assert.equal(views[0].thinking, undefined, "operator prompts carry no thinking");
});

test("a live block-start frame pulses; every other live frame stays silent", () => {
  // 0.2.0 logs no assistant/chunk: the pulse comes from a follow opened with
  // assistantStream:true (session-controller types.ts:513-543).
  assert.equal(views[17].kind, "pulse");
  assert.equal(views[17].mode, "reasoning");
  assert.equal(views[17].sessionId, "s1");
  assert.equal(views[17].seq, undefined, "a live frame is not a durable event: nothing to dedupe by");
  assert.equal(views[4].kind, "ignore", "a text-delta frame renders nothing");
  for (const frame of [
    { type: "start", attemptId: "a1", revision: 1, startedAfterSeq: 6, turn: 1, step: 1 },
    { type: "end", attemptId: "a1", revision: 1, index: 9, outcome: { kind: "committed", eventType: "assistant/message", seq: 7 } },
    { type: "chunk", attemptId: "a1", revision: 1, index: 0, time: 1, chunk: { type: "block-start", index: 0 } },
  ]) {
    assert.equal(mapFrame({ type: "assistant-stream", sessionId: "s1", frame }).kind, "ignore");
  }
});

test("tool call and tool result become cards keyed by callId; the title comes from the call itself", () => {
  assert.equal(views[2].kind, "card");
  assert.equal(views[2].card?.phase, "call");
  assert.equal(views[2].card?.name, "bash");
  assert.equal(views[2].card?.callId, "c1");
  // No host presenter reaches the client any more: a bash call is titled by its command.
  assert.equal(views[2].card?.title, "python -m alpaca_kit.breadth");

  assert.equal(views[3].kind, "card");
  assert.equal(views[3].card?.phase, "result");
  assert.equal(views[3].card?.callId, "c1");
  assert.equal(views[3].card?.title, undefined, "a result names no tool; the renderer titles it from its call");
  assert.equal(views[3].card?.text, "advancers 312 / decliners 188");
  assert.equal(views[3].card?.isError, false);
  assert.equal("view" in (views[3].card ?? {}), false, "no host render view exists at 0.2.0");
});

test("a call title falls back to the tool name whenever the call has no usable command", () => {
  const titleOf = (name: string, args: string) => mapFrame({ type: "session/event", sessionId: "s1", event: {
    type: "tool/call", seq: 1, time: 1, data: { turn: 1, step: 1, callId: "c9", name, arguments: args },
  } }).card?.title;
  assert.equal(titleOf("read", "{\"path\":\"AGENTS.md\"}"), "read");
  assert.equal(titleOf("bash", "{\"command\":"), "bash", "the model's malformed JSON is not guessed at");
  assert.equal(titleOf("bash", "{\"timeout\":5}"), "bash");
  assert.equal(titleOf("bash", "{\"command\":\"   \"}"), "bash");
});

test("a tool result is a tool-role message: its own toolCallId and flag, the source's callId only as fallback", () => {
  const resultOf = (message: Record<string, unknown>) => mapFrame({ type: "session/event", sessionId: "s1", event: {
    type: "tool/result", seq: 2, time: 1, surfaceOp: "append", data: { turn: 1, step: 1, message },
  } }).card;
  const card = resultOf({ id: "m", role: "tool", source: { kind: "tool", callId: "c-src" }, toolCallId: "c-own",
    content: [{ type: "text", text: "a" }, { type: "image", attachment: {} }, { type: "text", text: "b" }], isError: true });
  assert.equal(card?.callId, "c-own");
  assert.equal(card?.text, "a\nb", "every text block, in order; nothing else");
  assert.equal(card?.isError, true);
  assert.equal(resultOf({ id: "m", role: "tool", source: { kind: "tool", callId: "c-src" }, content: [] })?.callId, "c-src");
});

test("a failed tool result is flagged as an error card", () => {
  assert.equal(views[14].kind, "card");
  assert.equal(views[14].card?.phase, "result");
  assert.equal(views[14].card?.callId, "c3");
  assert.equal(views[14].card?.isError, true);
  assert.match(views[14].card?.text ?? "", /ENOENT/);
});

test("gate frames carry eventId as id and agentId as sessionId", () => {
  // stream-protocol.ts:52-58: the waterfall's eventId is the one id `$events/result`
  // names, and agentId IS the session id. There is no audit approvalId on the wire.
  assert.equal(views[6].kind, "approval");
  assert.equal(views[6].id, "ev-1");
  assert.equal(views[6].sessionId, "s1");
  assert.equal(views[6].toolName, "bash");
  assert.equal(views[6].callId, "c2");
  assert.equal(views[6].reason, "shell command outside the allowlist");
  assert.equal(views[6].displayReason, undefined);
  assert.equal("approvalId" in views[6], false);

  assert.equal(views[7].kind, "question");
  assert.equal(views[7].id, "ev-2");
  assert.equal(views[7].sessionId, "s1");
  assert.equal(views[7].questions?.length, 1);
});

test("an approval's English displayReason reaches the card; other locales and junk do not", () => {
  const approval = (request: Record<string, unknown>) => mapFrame({
    type: "waterfall", event: "approval/request", eventId: "ev-5", agentId: "s1", request,
  });
  // Sandbox escalations always send one (NEW packages/sandbox/sandbox/src/escalation.ts:188-199).
  const v = approval({ toolName: "bash", callId: "c5", reason: "escalate sandbox to workspace-write: fetch data",
    displayReason: { en: "Run with workspace write access", zh: "以工作区写权限运行" } });
  assert.equal(v.displayReason, "Run with workspace write access");
  assert.equal(v.reason, "escalate sandbox to workspace-write: fetch data");
  assert.equal(approval({ toolName: "bash", displayReason: { zh: "只有中文" } }).displayReason, undefined);
  assert.equal(approval({ toolName: "bash", displayReason: "not an object" }).displayReason, undefined);
});

test("a gate the host withdraws is reported by its eventId, with no outcome to guess from", () => {
  /* The withdrawal is a pure push, and it is the ONLY signal that a gate died
   * without this tab answering it — another tab answered, the turn stopped, the
   * session went away (gateway/src/index.ts:646-668). A `cancel` carries no
   * outcome and no session: the view says the gate is over, nothing more. */
  assert.deepEqual(views[19], { kind: "gate-resolved", id: "ev-2" });
  assert.deepEqual(views[20], { kind: "gate-resolved", id: "ev-1" });
});

test("waterfalls that are not operator gates, and malformed gates, render nothing", () => {
  for (const frame of [
    { type: "waterfall", event: "some-plugin/ask", eventId: "ev-7", agentId: "s1", request: {} },
    { type: "waterfall", event: "approval/request", agentId: "s1", request: { toolName: "bash" } },
    { type: "waterfall", event: "approval/request", eventId: "", agentId: "s1", request: { toolName: "bash" } },
    { type: "waterfall", event: "user-questions/request", eventId: "ev-8", agentId: "s1", request: "questions" },
    { type: "cancel" },
    { type: "cancel", eventId: "" },
  ]) {
    assert.equal(mapFrame(frame).kind, "ignore", JSON.stringify(frame));
  }
  const noQuestions = mapFrame({ type: "waterfall", event: "user-questions/request", eventId: "ev-9", agentId: "s1", request: {} });
  assert.equal(noQuestions.kind, "question");
  assert.deepEqual(noQuestions.questions, [], "an empty batch stays a card the operator can see, never a crash");
});

test("the 0.1.1 wire maps to ignore, so a stale host renders nothing rather than something half-right", () => {
  const event = { type: "user/message", seq: 4, time: 1, surfaceOp: "append",
    data: { id: "m", role: "user", content: [{ type: "text", text: "hi" }], source: { kind: "user" } } };
  const stale = [
    // The whole 0.1.1 mux envelope, around a frame that would otherwise be a bubble.
    { type: "server-request", rpcId: "r-01", method: "session/event", payload: { type: "session/event", sessionId: "s1", event } },
    { type: "server-request", rpcId: "r-07", method: "approval/requested",
      payload: { type: "approval/requested", sessionId: "s1", approvalId: "ap-1", toolName: "bash", callId: "c2" } },
    { type: "approval/requested", sessionId: "s1", approvalId: "ap-1", toolName: "bash" },
    { type: "question/requested", sessionId: "s1", questions: [{ id: "q1", question: "?" }] },
    { type: "question/resolved", sessionId: "s1", questionRpcId: "r-08", outcome: "cancelled" },
    { type: "approval/resolved", sessionId: "s1", approvalId: "ap-1", outcome: "rejected" },
    { type: "session/projection", sessionId: "s1", key: "tokenUsage", value: {}, seq: 1 },
    { type: "session/subscribed", sessionId: "s1", lastSeq: 9 },
    { type: "stream/error", error: { code: "internal", message: "boom", details: {} } },
    // The untyped session.history entry.
    { sessionId: "s1", event },
    // 0.1.1's logged chunk, the old pulse source.
    { type: "session/event", sessionId: "s1", event: { type: "assistant/chunk", seq: 5, time: 1,
      data: { turn: 1, step: 1, chunk: { type: "block-start", index: 0, blockType: "reasoning" } } } },
  ];
  for (const frame of stale) assert.equal(mapFrame(frame).kind, "ignore", JSON.stringify(frame).slice(0, 80));
});

test("log-only, control, and contentless frames are ignored", () => {
  assert.equal(views[4].kind, "ignore", "a live text delta");
  assert.equal(views[8].kind, "ignore", "the follow snapshot: chat.js seeds from it");
  assert.equal(views[9].kind, "ignore", "a mux error frame: api.js routes it to its stream");
  assert.equal(views[12].kind, "ignore", "assistant message with no text block");
  for (const frame of [
    { type: "baseline", value: { projections: {} } },
    { type: "ready", clientId: "k1", host: { home: "/Users/pan" } },
    { type: "emit", event: "api-session/status", args: ["s1", true] },
    { type: "item", streamId: "s2", value: {} },
    { type: "end", streamId: "s2" },
    { type: "session/event", sessionId: "s1", event: { type: "approval/decided", seq: 20, time: 1, data: { id: "a", outcome: "rejected" } } },
  ]) {
    assert.equal(mapFrame(frame).kind, "ignore", JSON.stringify(frame));
  }
});

test("a turn/start boundary surfaces too, with no reason (it hasn't ended yet)", () => {
  const v = views[5];
  assert.equal(v.kind, "turn");
  assert.equal(v.phase, "start");
  assert.equal(v.turn, 1);
  assert.equal(v.sessionId, "s1");
  assert.equal(v.reason, undefined);
});

test("normalized follow records map like live events", () => {
  // A follow snapshot's records and its live tail are both `{type:"event", event}`
  // naming no session (types.ts:425-429, 552-563); chat.js re-addresses them as
  // session/event frames, and the raw record maps identically.
  assert.equal(views[10].kind, "bubble");
  assert.equal(views[10].role, "operator");
  assert.equal(views[10].seq, 10);
  assert.equal(views[11].kind, "bubble");
  assert.equal(views[11].role, "kairos");
  assert.equal(views[11].seq, 11);
  assert.equal(views[11].text, "Breadth is still positive.");

  const live = (frames[11] as { event: unknown }).event;
  const snapshot = { type: "snapshot", cursor: 11, records: [{ type: "event", event: live }], hasMore: true };
  const normalized = snapshot.records.map((record) => ({ type: "session/event", sessionId: "s1", event: record.event }));
  assert.deepEqual(mapFrame(normalized[0]), views[11]);
  assert.deepEqual(mapFrame({ ...snapshot.records[0], sessionId: "s1" }), views[11], "the raw record, re-addressed");
  assert.equal(mapFrame(snapshot.records[0]).sessionId, undefined, "a raw record names no session of its own");
});

test("a bubble reports who produced the message, in v4's own source kinds", () => {
  // A user-ROLE message is not always the operator: producers inject context
  // through the same event. v4 names each producer directly - a migrated v3
  // `{kind:'plugin', plugin:X}` becomes `plugin:X` or a first-party kind
  // (session-format-v3-to-v4/src/sources.ts:38-65). The mapper only reports it.
  assert.equal(views[0].source, "user");
  assert.equal(views[13].kind, "bubble");
  assert.equal(views[13].role, "operator");
  assert.equal(views[13].source, "plugin:fs-observation");
  assert.equal(views[13].form, "notice");
  assert.equal(views[15].source, "compact-checkpoint");
});

test("a surface replacement carries its shadow instruction through", () => {
  // Compaction writes its checkpoint as a user/message whose surfaceOp replaces
  // the range it summarized, spelled startSeq/endSeq at 0.2.0 (session types.ts
  // SurfaceOp). The view keeps the renderer's {start, end}; a renderer that
  // never sees this shows the summary AND everything it summarized.
  assert.equal(views[15].kind, "bubble");
  assert.deepEqual(views[15].surfaceOp, { op: "replace", start: 4, end: 11 });
});

test("every other rendered event says plainly that it appends", () => {
  assert.equal(views[0].surfaceOp, "append", "explicit append survives");
  assert.equal(views[3].surfaceOp, "append", "tool/result");
  // Surface metadata is forbidden on log-only events, tool/call included, so an
  // absent op must read as append rather than as undefined.
  assert.equal(views[2].surfaceOp, "append", "tool/call carries no surfaceOp of its own");
  assert.equal(views[11].surfaceOp, "append", "a normalized follow record");

  const replace = (surfaceOp: unknown) => mapFrame({
    type: "session/event",
    sessionId: "s1",
    event: { type: "user/message", seq: 1, time: 1, surfaceOp, data: { content: [{ type: "text", text: "hi" }] } },
  }).surfaceOp;
  assert.equal(replace({ op: "replace", startSeq: 4 }), "append", "a replace missing its range is not obeyed");
  assert.equal(replace({ op: "replace", startSeq: "4", endSeq: 11 }), "append");
  // v4 rewrites stored references on read, so the 0.1.1 spelling is malformed, never a range.
  assert.equal(replace({ op: "replace", start: 4, end: 11 }), "append", "the 0.1.1 spelling is not obeyed");
});

test("an interrupted answer is never presented as a complete one", () => {
  assert.equal(views[16].kind, "bubble");
  assert.equal(views[16].role, "kairos");
  assert.equal(views[16].text, "The first pivot looks like");
  assert.equal(views[16].interrupted, true);
  // The flag is present-and-false on whole messages, so a renderer reads one field.
  assert.equal(views[1].interrupted, false);
  assert.equal(views[0].interrupted, false, "an operator prompt is never a prefix");
});

test("a projection frame carries its whole value through, keyed and sequenced", () => {
  // A session/control update is a STATE broadcast (control.ts:22-30): the store
  // keeps whole values per (session, key), higher seq winning — never a transcript node.
  assert.equal(views[18].kind, "projection");
  assert.equal(views[18].sessionId, "s1");
  assert.equal(views[18].key, "tokenUsage");
  assert.equal(views[18].seq, 16);
  assert.deepEqual(views[18].value, {
    uncachedInputTokens: 8123, outputTokens: 2411, cacheReadTokens: 51200, cacheWriteTokens: 900,
  });
  // A frame missing its address renders nothing rather than a nameless card.
  assert.equal(mapFrame({ type: "projection", key: "tokenUsage" }).kind, "ignore");
  assert.equal(mapFrame({ type: "projection", sessionId: "s1" }).kind, "ignore");
});

test("null-safe: unrecognized input never throws, it ignores", () => {
  for (const bad of [undefined, null, 0, "", "session/event", [], {}, { type: "server-request" },
    { type: "session/event" }, { type: "event" }, { event: {} }, { event: { type: "weird/thing" } },
    { type: "session/event", event: { type: "weird/thing" } }, { type: "assistant-stream" },
    { type: "assistant-stream", frame: { type: "chunk", chunk: null } }, { type: "waterfall" },
    { type: "waterfall", event: "approval/request", eventId: "e", request: null }, { type: "projection" },
    { type: "session/event", event: { type: "user/message" } }]) {
    assert.equal(mapFrame(bad).kind, "ignore", JSON.stringify(bad));
  }
});

test("a member's answer is a BOT bubble with its name and id, never an operator bubble or a context row", () => {
  const v = views[21];
  assert.equal(v.kind, "bubble");
  assert.equal(v.role, "bot");
  assert.equal(v.bot, "buffett");
  assert.equal(v.name, "巴菲特型");
  assert.equal(v.form, "answer");
  assert.equal(v.text, "买。理由：便宜。");
  assert.equal(v.seq, 30);
  assert.equal(v.sessionId, "s1", "the room retains its own identity");
  assert.equal(v.memberSessionId, "s-b");
  assert.equal(v.memberTurn, 1);
});

test("a legacy member answer without trace identity never guesses the room or another turn", () => {
  const v = mapFrame({ type: "session/event", sessionId: "room", event: {
    type: "user/message", seq: 1, data: {
      content: [{ type: "text", text: "回答" }],
      source: { kind: "room", form: "answer", bot: "member" },
    },
  } });
  assert.equal(v.sessionId, "room");
  assert.equal(v.memberSessionId, undefined);
  assert.equal(v.memberTurn, undefined);
});

test("the round-end message is a room line carrying the outcome and every turn's state", () => {
  const v = views[22];
  assert.equal(v.kind, "room-line");
  assert.equal(v.line, "round-end");
  assert.equal(v.round, 1);
  assert.equal(v.outcome, "settled");
  assert.deepEqual((v.turns as { bot: string; state: string }[]).map((t) => `${t.bot}:${t.state}`), ["buffett:answered", "speculator:passed"]);
  assert.match(v.text ?? "", /^Round 1 ended/);
});

test("structured member metadata is preserved identically for live events and follow records without replacing the original text", () => {
  const roomView = { position: "暂缓判断", evidence: ["待复核材料"], uncertainties: [], changeConditions: ["材料复核完成"], disagreements: [] };
  const event = { type: "user/message", seq: 32, time: 1, surfaceOp: "append", data: {
    id: "m-32", role: "user",
    content: [{ type: "text", text: "回答正文\n```room-view\n{...}\n```" }],
    source: { kind: "room", form: "answer", bot: "value", name: "Value", sessionId: "member-1", turn: 4, view: roomView, displayText: "回答正文" },
  } };
  const live = mapFrame({ type: "session/event", sessionId: "room", event });
  const record = mapFrame({ type: "event", sessionId: "room", event });
  assert.deepEqual(live, record);
  assert.deepEqual(live.roomView, roomView);
  assert.equal(live.displayText, "回答正文");
  assert.match(live.text ?? "", /room-view/);
  assert.equal(live.memberSessionId, "member-1");
  assert.equal(live.memberTurn, 4);
});

test("malformed structured metadata stays available for renderer validation and raw-answer fallback", () => {
  const event = { type: "user/message", seq: 1, data: {
    content: [{ type: "text", text: "原始回答" }],
    source: { kind: "room", form: "answer", bot: "member", view: ["malformed"], displayText: "不能替代原文", viewIssue: "Missing fields" },
  } };
  const view = mapFrame({ type: "session/event", sessionId: "room", event });
  assert.deepEqual(view.roomView, ["malformed"]);
  assert.equal(view.text, "原始回答");
  assert.equal(view.viewIssue, "Missing fields");
});

test("round comparison metadata survives live/record mapping and is never inferred from ordinary round prose", () => {
  const discussion = { brief: { question: "能否证伪？" }, views: [], unstructuredBots: ["value"] };
  const event = { type: "user/message", seq: 33, data: {
    content: [{ type: "text", text: "Round 1 ended" }],
    source: { kind: "room", form: "round-end", round: 1, outcome: "settled", turns: [], discussion },
  } };
  const live = mapFrame({ type: "session/event", sessionId: "room", event });
  assert.deepEqual(live, mapFrame({ type: "event", sessionId: "room", event }));
  assert.deepEqual(live.discussion, discussion);
  assert.equal(views[22].discussion, undefined, "the legacy round still renders only its state line");
});

test("the operator's @ stays an operator bubble and names whom it addressed", () => {
  const v = views[23];
  assert.equal(v.kind, "bubble");
  assert.equal(v.role, "operator");
  assert.equal(v.source, "user");
  assert.deepEqual(v.mention, ["buffett"]);
});

test("a member's delta prompt is an injected context row of source room, form delta", () => {
  const v = views[24];
  assert.equal(v.kind, "bubble");
  assert.equal(v.role, "operator");
  assert.equal(v.source, "room");
  assert.equal(v.form, "delta");
  assert.equal(v.sessionId, "s-b");
});

test("turn boundaries are surfaced for every session, so the strip can clear a member's fine state", () => {
  const v = views[25];
  assert.equal(v.kind, "turn");
  assert.equal(v.phase, "end");
  assert.equal(v.turn, 1);
  assert.equal(v.sessionId, "s-b");
  assert.equal(v.reason, "completed");
  // 0.2.0 adds closers the loop never emits live; they are read as strings (session types.ts TurnEndReasonMap).
  for (const kind of ["interrupted", "forked"]) {
    const closer = mapFrame({ type: "session/event", sessionId: "s1", event: { type: "turn/end", seq: 40, time: 1, data: { turn: 3, reason: { kind } } } });
    assert.equal(closer.reason, kind);
  }
});

test("a 0.2.0 child report is an agent-message relay: child attribution and the complete framed text, live and recorded alike", () => {
  // NEW packages/subagent/subagent/src/continuation-messages.ts:15-21, 46-72:
  // `send_message` from a continuable child prepends this header and records
  // only kind/form/senderSessionId.
  const event = { type: "user/message", seq: 44, time: 1, surfaceOp: "append", data: {
    id: "m-44", role: "user",
    content: [
      { type: "text", text: "Agent child-7 sent a message: " },
      { type: "text", text: "已核查样本；结论仍待复现。" },
    ],
    source: { kind: "agent-message", form: "relay", senderSessionId: "child-7" },
  } };
  const live = mapFrame({ type: "session/event", sessionId: "parent", event });
  assert.deepEqual(live, mapFrame({ type: "event", sessionId: "parent", event }));
  assert.deepEqual(live, {
    seq: 44, sessionId: "parent", surfaceOp: "append", kind: "subagent-message", line: "report",
    source: "agent-message", form: "relay", childSessionId: "child-7",
    // Blocks are joined verbatim: upstream's header ends in a space (continuation-messages.ts:68).
    text: "Agent child-7 sent a message: \n已核查样本；结论仍待复现。",
  });
  assert.equal(live.role, undefined, "a child report is neither an operator nor a room bot");
  assert.equal(live.summary, undefined);
  assert.equal(live.outcome, undefined, "reporting does not settle the child");
});

test("an agent-message outside the relay form is not a report: it stays a context row", () => {
  for (const form of [undefined, "notice", []]) {
    const view = mapFrame({ type: "session/event", sessionId: "parent", event: { type: "user/message", seq: 45, data: {
      content: [{ type: "text", text: "Agent child-7 sent a message: hi" }],
      source: { kind: "agent-message", senderSessionId: "child-7", ...(form === undefined ? {} : { form }) },
    } } });
    assert.equal(view.kind, "bubble");
    assert.equal(view.role, "operator");
    assert.equal(view.source, "agent-message");
    assert.equal(view.childSessionId, undefined, "attribution is metadata a report records, never read off another form");
  }
});

test("a report migrated from 0.1.1 keeps its subagent-report kind and still renders as the report line", () => {
  // The v3→v4 edge keeps `subagent-report` by name (session-format-v3-to-v4/src/sources.ts:48-56).
  const event = { type: "user/message", seq: 44, time: 1, surfaceOp: "append", data: {
    id: "m-44", role: "user",
    content: [
      { type: "text", text: "Background subagent child-7 reported:" },
      { type: "text", text: "已核查样本；结论仍待复现。" },
    ],
    source: { kind: "subagent-report", form: "relay", senderSessionId: "child-7" },
  } };
  const live = mapFrame({ type: "session/event", sessionId: "parent", event });
  assert.deepEqual(live, mapFrame({ type: "event", sessionId: "parent", event }));
  assert.deepEqual(live, {
    seq: 44, sessionId: "parent", surfaceOp: "append", kind: "subagent-message", line: "report",
    source: "subagent-report", form: "relay", childSessionId: "child-7",
    text: "Background subagent child-7 reported:\n已核查样本；结论仍待复现。",
  });
});

test("native subagent settlement remains a runtime notice, without turning prose into an outcome", () => {
  // createSettlementMessage() writes a bounded summary and the final output into
  // message content. Its source has no result/outcome/stopReason field
  // (continuation-messages.ts:131-170).
  const summary = "Background subagent child-7 was stopped before it finished.";
  const event = { type: "user/message", seq: 45, surfaceOp: { op: "replace", startSeq: 44, endSeq: 44 }, data: {
    content: [
      { type: "text", text: summary },
      { type: "text", text: "Its closing message:" },
      { type: "text", text: "这是停止前的部分记录。" },
    ],
    source: { kind: "subagent-settled", form: "notice", senderSessionId: "child-7", summary },
  } };
  const view = mapFrame({ type: "session/event", sessionId: "parent", event });
  assert.deepEqual(view, mapFrame({ type: "event", sessionId: "parent", event }));
  assert.equal(view.kind, "subagent-message");
  assert.equal(view.line, "settled");
  assert.equal(view.source, "subagent-settled");
  assert.equal(view.form, "notice");
  assert.equal(view.summary, summary);
  assert.equal(view.text, `${summary}\nIts closing message:\n这是停止前的部分记录。`);
  assert.equal(view.childSessionId, "child-7");
  assert.equal(view.sessionId, "parent");
  assert.deepEqual(view.surfaceOp, { op: "replace", start: 44, end: 44 });
  assert.equal(view.role, undefined, "the runtime is not speaking as the child");
  assert.equal(view.outcome, undefined, "settled is not synonymous with successful completion");
});

test("subagent messages with legacy or malformed source fields retain raw text without invented identity", () => {
  const malformed = (kind: string, form: unknown) => ({ kind, form, summary: { unsafe: true }, outcome: "completed",
    result: { output: "do not replace the log" }, name: "Operator", bot: "room-member" });
  const cases = [
    ...["subagent-report", "subagent-settled"].map((kind) => malformed(kind, [])),
    // A relay is recognized by its form; its other fields may still be junk.
    malformed("agent-message", "relay"),
  ];
  for (const source of cases) {
    for (const senderSessionId of [undefined, null, [], 2, "", "   "]) {
      const view = mapFrame({ type: "session/event", sessionId: "parent", event: { type: "user/message", seq: 46, data: {
        content: [{ type: "text", text: "旧日志原文 child-unknown completed" }],
        source: { ...source, senderSessionId },
      } } });
      assert.equal(view.kind, "subagent-message");
      assert.equal(view.text, "旧日志原文 child-unknown completed");
      assert.equal(view.childSessionId, undefined);
      assert.equal(view.summary, undefined);
      assert.equal(view.outcome, undefined);
      assert.equal(view.role, undefined);
      assert.equal(view.bot, undefined);
      assert.equal(view.name, undefined);
      assert.equal(view.form, source.kind === "agent-message" ? "relay" : undefined);
    }
  }
});

test("summary-only settlement is visible, while empty reports and unrelated prose keep the existing fallback", () => {
  const userMessage = (source: Record<string, unknown>, content: unknown[]) =>
    mapFrame({ type: "session/event", event: { type: "user/message", seq: 47, data: { content, source } } });
  const notice = userMessage({ kind: "subagent-settled", summary: "The child ended without a closing message." }, []);
  assert.equal(notice.kind, "subagent-message");
  assert.equal(notice.summary, "The child ended without a closing message.");
  assert.equal(notice.text, "");
  assert.equal(notice.childSessionId, undefined);

  assert.equal(userMessage({ kind: "subagent-report", summary: "This is not report metadata." }, []).kind, "ignore");
  assert.equal(userMessage({ kind: "agent-message", form: "relay", summary: "Nor is this." }, []).kind, "ignore");

  for (const kind of ["user", "plugin:fs-observation", "subagent-future-kind"]) {
    const view = userMessage({ kind, senderSessionId: "child-7" }, [{ type: "text", text: "Background subagent child-7 reported:" }]);
    assert.equal(view.kind, "bubble", "subagent attribution is metadata, never detected from text");
    assert.equal(view.childSessionId, undefined);
    assert.equal(view.text, "Background subagent child-7 reported:");
  }
});
