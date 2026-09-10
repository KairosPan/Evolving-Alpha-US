/** The tested half of the client: the pure frame → view-model mapping.
 *
 * The fixtures are real wire frames, not sketches — each line is what the
 * WebSocket at `/api/events.mux` actually delivers at the pinned host version:
 * a `ServerRequest` full form whose `payload` is a `MuxFrame`
 * (`@deepseek-ai/dsh-client-connection/lib/index.js` `serverRequest()`,
 * mirroring `dsh-host-apiproxy/lib/types/fetch/handler.js` `fullFrame()`).
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

test("a block-start chunk pulses; the stream itself stays log-only", () => {
  assert.equal(views[17].kind, "pulse");
  assert.equal(views[17].mode, "reasoning");
  assert.equal(views[17].sessionId, "s1");
  assert.equal(views[4].kind, "ignore", "a text-delta chunk renders nothing");
});

test("tool call and tool result become cards keyed by callId", () => {
  assert.equal(views[2].kind, "card");
  assert.equal(views[2].card?.phase, "call");
  assert.equal(views[2].card?.name, "bash");
  assert.equal(views[2].card?.callId, "c1");
  assert.equal(views[2].card?.title, "python -m alpaca_kit.breadth");

  assert.equal(views[3].kind, "card");
  assert.equal(views[3].card?.phase, "result");
  assert.equal(views[3].card?.callId, "c1");
  assert.equal(views[3].card?.title, "breadth · 312/188");
  assert.equal(views[3].card?.text, "advancers 312 / decliners 188");
  assert.equal(views[3].card?.isError, false);
});

test("a failed tool result is flagged as an error card", () => {
  assert.equal(views[14].kind, "card");
  assert.equal(views[14].card?.phase, "result");
  assert.equal(views[14].card?.callId, "c3");
  assert.equal(views[14].card?.isError, true);
  assert.match(views[14].card?.text ?? "", /ENOENT/);
});

test("answerable frames carry the envelope rpcId as their respond id", () => {
  // questions.d.ts:1-6 / approvals.d.ts:1-6 — the answer is a client-response
  // echoing the frame's rpcId; approvalId is audit correlation, not wire id.
  assert.equal(views[6].kind, "approval");
  assert.equal(views[6].id, "r-07");
  assert.equal(views[6].approvalId, "ap-1");
  assert.equal(views[6].toolName, "bash");
  assert.equal(views[6].callId, "c2");
  assert.equal(views[6].sessionId, "s1");

  assert.equal(views[7].kind, "question");
  assert.equal(views[7].id, "r-08");
  assert.equal(views[7].sessionId, "s1");
  assert.equal(views[7].questions?.length, 1);
});

test("a gate the host settles on its own is reported, never ignored", () => {
  /* Both resolutions are pure pushes, and they are the ONLY signal that a gate
   * died without this client answering it — a cancelled turn, a disposed
   * session, another answerer first. Ignoring them (as v1 did) leaves the card
   * answerable forever, re-drawn on every session switch and every reconnect.
   * The two name their gate differently on purpose: a question carries the wire
   * rpcId `/api/respond` echoes, an approval carries only its audit id. */
  assert.equal(views[19].kind, "gate-resolved");
  assert.equal(views[19].id, "r-08", "the question's own respond id, not the push's");
  assert.equal(views[19].approvalId, undefined);
  assert.equal(views[19].outcome, "cancelled");
  assert.equal(views[19].sessionId, "s1");

  assert.equal(views[20].kind, "gate-resolved");
  assert.equal(views[20].approvalId, "ap-1");
  assert.equal(views[20].id, undefined, "approval/resolved carries no wire id at all");
  assert.equal(views[20].outcome, "rejected");
  assert.equal(views[20].sessionId, "s1");
});

test("log-only, control, and contentless frames are ignored", () => {
  assert.equal(views[4].kind, "ignore", "assistant/chunk is log-only for v1");
  assert.equal(views[8].kind, "ignore", "session/subscribed is a control frame");
  assert.equal(views[9].kind, "ignore", "stream/error has no v1 surface");
  assert.equal(views[12].kind, "ignore", "assistant message with no text block");
});

test("a turn/start boundary surfaces too, with no reason (it hasn't ended yet)", () => {
  const v = views[5];
  assert.equal(v.kind, "turn");
  assert.equal(v.phase, "start");
  assert.equal(v.turn, 1);
  assert.equal(v.sessionId, "s1");
  assert.equal(v.reason, undefined);
});

test("bare mux frames and history entries map like enveloped ones", () => {
  // Task 7 backfills from session.history, whose entries are {event, view?}
  // with no envelope and no frame type (sessions.d.ts:65-68).
  assert.equal(views[10].kind, "bubble");
  assert.equal(views[10].role, "operator");
  assert.equal(views[10].seq, 10);

  assert.equal(views[11].kind, "bubble");
  assert.equal(views[11].role, "kairos");
  assert.equal(views[11].seq, 11);
  assert.equal(views[11].text, "Breadth is still positive.");
});

test("a bubble reports who produced the message", () => {
  // A user-ROLE message is not always the operator: plugins inject context
  // through the same event (message.d.ts:94-104). The renderer needs the
  // distinction; the mapper only reports it.
  assert.equal(views[0].source, "user");
  assert.equal(views[13].kind, "bubble");
  assert.equal(views[13].source, "plugin");
});

test("a surface replacement carries its shadow instruction through", () => {
  // Compaction writes its checkpoint as a user/message whose surfaceOp replaces
  // the range it summarized (dsh-compaction-basic/lib/index.js:604-616). A
  // renderer that never sees this shows the summary AND everything it summarized.
  assert.equal(views[15].kind, "bubble");
  assert.equal(views[15].source, "plugin");
  assert.deepEqual(views[15].surfaceOp, { op: "replace", start: 4, end: 11 });
});

test("every other rendered event says plainly that it appends", () => {
  assert.equal(views[0].surfaceOp, "append", "explicit append survives");
  assert.equal(views[3].surfaceOp, "append", "tool/result");
  // Surface metadata is forbidden on log-only events, tool/call included, so an
  // absent op must read as append rather than as undefined.
  assert.equal(views[2].surfaceOp, "append", "tool/call carries no surfaceOp of its own");
  assert.equal(views[11].surfaceOp, "append", "history entry");

  const malformed = mapFrame({
    type: "session/event",
    sessionId: "s1",
    event: {
      type: "user/message", seq: 1, surfaceOp: { op: "replace", start: "4" },
      data: { content: [{ type: "text", text: "hi" }] },
    },
  });
  assert.equal(malformed.surfaceOp, "append", "a replace missing its range is not obeyed");
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
  // session/projection is a STATE broadcast (events.d.ts): the store keeps
  // whole values per (session, key), higher seq winning — never a transcript node.
  assert.equal(views[18].kind, "projection");
  assert.equal(views[18].sessionId, "s1");
  assert.equal(views[18].key, "tokenUsage");
  assert.equal(views[18].seq, 16);
  assert.deepEqual(views[18].value, {
    uncachedInputTokens: 8123, outputTokens: 2411, cacheReadTokens: 51200, cacheWriteTokens: 900,
  });
  // A frame missing its address renders nothing rather than a nameless card.
  assert.equal(mapFrame({ type: "session/projection", key: "tokenUsage" }).kind, "ignore");
  assert.equal(mapFrame({ type: "session/projection", sessionId: "s1" }).kind, "ignore");
});

test("null-safe: unrecognized input never throws, it ignores", () => {
  for (const bad of [undefined, null, 0, "", "session/event", [], {}, { type: "server-request" },
    { type: "session/event" }, { event: {} }, { event: { type: "weird/thing" } },
    { type: "server-request", rpcId: "x", payload: { type: "nope/nope" } },
    { type: "session/event", event: { type: "user/message" } }]) {
    assert.equal(mapFrame(bad).kind, "ignore");
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

test("structured member metadata is preserved identically for live envelopes and history without replacing the original text", () => {
  const roomView = { position: "暂缓判断", evidence: ["待复核材料"], uncertainties: [], changeConditions: ["材料复核完成"], disagreements: [] };
  const event = { type: "user/message", seq: 32, data: {
    content: [{ type: "text", text: "回答正文\n```room-view\n{...}\n```" }],
    source: { kind: "room", form: "answer", bot: "value", name: "Value", sessionId: "member-1", turn: 4, view: roomView, displayText: "回答正文" },
  } };
  const live = mapFrame({ type: "server-request", method: "session/event", rpcId: "f32", payload: { type: "session/event", sessionId: "room", event } });
  const history = mapFrame({ sessionId: "room", event });
  assert.deepEqual(live, history);
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
  const view = mapFrame({ sessionId: "room", event });
  assert.deepEqual(view.roomView, ["malformed"]);
  assert.equal(view.text, "原始回答");
  assert.equal(view.viewIssue, "Missing fields");
});

test("round comparison metadata survives live/history mapping and is never inferred from ordinary round prose", () => {
  const discussion = { brief: { question: "能否证伪？" }, views: [], unstructuredBots: ["value"] };
  const event = { type: "user/message", seq: 33, data: {
    content: [{ type: "text", text: "Round 1 ended" }],
    source: { kind: "room", form: "round-end", round: 1, outcome: "settled", turns: [], discussion },
  } };
  const live = mapFrame({ type: "session/event", sessionId: "room", event });
  assert.deepEqual(live, mapFrame({ sessionId: "room", event }));
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
});

test("native subagent reports preserve child attribution and the complete framed text in live and history views", () => {
  // dsh-subagent continuation.js deliverReport() prepends this header to the
  // child's selected content and records only kind/form/senderSessionId.
  const event = { type: "user/message", seq: 44, data: {
    content: [
      { type: "text", text: "Background subagent child-7 reported:" },
      { type: "text", text: "已核查样本；结论仍待复现。" },
    ],
    source: { kind: "subagent-report", form: "relay", senderSessionId: "child-7" },
  } };
  const live = mapFrame({ type: "server-request", method: "session/event", rpcId: "f44", payload: { type: "session/event", sessionId: "parent", event } });
  const history = mapFrame({ sessionId: "parent", event });
  assert.deepEqual(live, history);
  assert.deepEqual(live, {
    seq: 44, sessionId: "parent", surfaceOp: "append", kind: "subagent-message", line: "report",
    source: "subagent-report", form: "relay", childSessionId: "child-7",
    text: "Background subagent child-7 reported:\n已核查样本；结论仍待复现。",
  });
  assert.equal(live.role, undefined, "a child report is neither an operator nor a room bot");
  assert.equal(live.bot, undefined);
  assert.equal(live.summary, undefined);
  assert.equal(live.outcome, undefined, "reporting does not settle the child");
});

test("native subagent settlement remains a runtime notice, without turning prose into an outcome", () => {
  // notifySettlement() writes a bounded summary and the final output into
  // message content. Its source has no result/outcome/stopReason field.
  const summary = "Background subagent child-7 was stopped before it finished.";
  const event = { type: "user/message", seq: 45, surfaceOp: { op: "replace", start: 44, end: 44 }, data: {
    content: [
      { type: "text", text: summary },
      { type: "text", text: "Its closing message:" },
      { type: "text", text: "这是停止前的部分记录。" },
    ],
    source: { kind: "subagent-settled", form: "notice", senderSessionId: "child-7", summary },
  } };
  const view = mapFrame({ type: "session/event", sessionId: "parent", event });
  assert.deepEqual(view, mapFrame({ sessionId: "parent", event }));
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
  for (const kind of ["subagent-report", "subagent-settled"]) {
    for (const senderSessionId of [undefined, null, [], 2, "", "   "]) {
      const view = mapFrame({ sessionId: "parent", event: { type: "user/message", seq: 46, data: {
        content: [{ type: "text", text: "旧日志原文 child-unknown completed" }],
        source: { kind, senderSessionId, summary: { unsafe: true }, form: [], outcome: "completed", result: { output: "do not replace the log" }, name: "Operator", bot: "room-member" },
      } } });
      assert.equal(view.kind, "subagent-message");
      assert.equal(view.text, "旧日志原文 child-unknown completed");
      assert.equal(view.childSessionId, undefined);
      assert.equal(view.summary, undefined);
      assert.equal(view.form, undefined);
      assert.equal(view.outcome, undefined);
      assert.equal(view.role, undefined);
      assert.equal(view.bot, undefined);
      assert.equal(view.name, undefined);
    }
  }
});

test("summary-only settlement is visible, while empty reports and unrelated prose keep the existing fallback", () => {
  const notice = mapFrame({ event: { type: "user/message", seq: 47, data: {
    content: [], source: { kind: "subagent-settled", summary: "The child ended without a closing message." },
  } } });
  assert.equal(notice.kind, "subagent-message");
  assert.equal(notice.summary, "The child ended without a closing message.");
  assert.equal(notice.text, "");
  assert.equal(notice.childSessionId, undefined);

  assert.equal(mapFrame({ event: { type: "user/message", data: {
    content: [], source: { kind: "subagent-report", summary: "This is not report metadata." },
  } } }).kind, "ignore");

  for (const kind of ["user", "plugin", "subagent-future-kind"]) {
    const view = mapFrame({ event: { type: "user/message", data: {
      content: [{ type: "text", text: "Background subagent child-7 reported:" }],
      source: { kind, senderSessionId: "child-7" },
    } } });
    assert.equal(view.kind, "bubble", "subagent attribution is metadata, never detected from text");
    assert.equal(view.childSessionId, undefined);
    assert.equal(view.text, "Background subagent child-7 reported:");
  }
});
