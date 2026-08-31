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
  assert.equal(frames.length, 15);
  assert.equal(views.length, 15);
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
  // Reasoning is not chat text: the thinking block must not reach the bubble.
  assert.doesNotMatch(views[1].text ?? "", /200DMA/);
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

test("log-only, control, and contentless frames are ignored", () => {
  assert.equal(views[4].kind, "ignore", "assistant/chunk is log-only for v1");
  assert.equal(views[5].kind, "ignore", "turn/start is a boundary marker");
  assert.equal(views[8].kind, "ignore", "session/subscribed is a control frame");
  assert.equal(views[9].kind, "ignore", "stream/error has no v1 surface");
  assert.equal(views[12].kind, "ignore", "assistant message with no text block");
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

test("null-safe: unrecognized input never throws, it ignores", () => {
  for (const bad of [undefined, null, 0, "", "session/event", [], {}, { type: "server-request" },
    { type: "session/event" }, { event: {} }, { event: { type: "weird/thing" } },
    { type: "server-request", rpcId: "x", payload: { type: "nope/nope" } },
    { type: "session/event", event: { type: "user/message" } }]) {
    assert.equal(mapFrame(bad).kind, "ignore");
  }
});
