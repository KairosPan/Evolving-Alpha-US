/** Pure frame → view-model mapping: the tested half of the client.
 *
 * No DOM, no network, no state — one frame in, one view-model out, so the
 * decoding of the harness wire format is testable without a browser and the
 * renderer stays a dumb consumer of `kind`.
 *
 * WHAT ARRIVES. The mux WebSocket delivers a `ServerRequest` full form whose
 * `payload` is one `MuxFrame` and whose `method` repeats that frame's own type
 * (`dsh-client-connection/lib/index.js` `serverRequest()`, the WebSocket twin of
 * `dsh-host-apiproxy/lib/types/fetch/handler.js` `fullFrame()`). The envelope is
 * not decoration: for the two ANSWERABLE frames (approval/question requested)
 * its `rpcId` IS the id `/api/respond` must echo — the payload carries no wire
 * id of its own (approvals.d.ts:1-6, questions.d.ts:1-6). `mapFrame` therefore
 * lifts `rpcId` into `view.id`.
 *
 * A bare `MuxFrame` (no envelope) is accepted too, and so is a `session.history`
 * entry `{ event, view? }` with a `sessionId` added — history has no envelope and
 * no frame type (sessions.d.ts:61-68), and one mapping for both paths is what
 * keeps a backfilled transcript identical to a streamed one.
 *
 * Shapes are pinned to `@deepseek-ai/dsh-host-apiproxy@0.1.1-rc.2`:
 *   frame union      lib/types/api/events.d.ts:66-145 (MuxFrame)
 *   envelope         lib/types/api/rpc.d.ts:236-242 (ServerRequest)
 *   session event    @deepseek-ai/dsh-session/lib/types/types.d.ts:223-457
 *   message/content  @deepseek-ai/dsh-llm/lib/types/{message,types}.d.ts
 *   tool render view @deepseek-ai/dsh-tools/lib/types/presentation.d.ts
 * On a pin bump, re-read those and correct this file AND tests/fixtures/events.jsonl.
 * @module
 */

/**
 * How a surface event entered the transcript: appended to the tail, or
 * replacing an inclusive seq range that must stop being shown.
 * @typedef {"append"|{op: "replace", start: number, end: number}} SurfaceOpView
 */

/**
 * A completed or pending tool call, as one card.
 * @typedef {object} ToolCardView
 * @property {"call"|"result"} phase - `call` announces the invocation, `result` completes it.
 * @property {string} [callId] - pairs the two phases; absent only on a malformed event.
 * @property {string} [name] - the tool's name. Present on `call` ONLY: `tool/result`
 *   carries the message, not the name, so a renderer titles a result from the call it remembers.
 * @property {string} [title] - the host's render intent for this phase, when a presenter produced one.
 * @property {string} [text] - result text, model-facing blocks joined (`result` phase).
 * @property {boolean} [isError] - whether the tool reported failure.
 * @property {unknown} [view] - the raw ToolCallView/ToolResultView, for a renderer that grows card kinds.
 */

/**
 * One frame's whole meaning to the UI. A closed `kind` vocabulary with optional
 * payload fields: a renderer switches on `kind` and reads only its own fields.
 * @typedef {object} FrameView
 * @property {"bubble"|"card"|"approval"|"question"|"pulse"|"ignore"} kind
 * @property {number} [seq] - the session event's seq; the renderer's dedupe key across backfill and stream.
 * @property {string} [sessionId] - which session this belongs to (absent on a history entry that carries none).
 * @property {SurfaceOpView} [surfaceOp] - on every rendered session event: `append`, or a
 *   replace instruction the renderer MUST honour by dropping the shadowed range.
 * @property {"operator"|"kairos"} [role] - bubble side.
 * @property {string} [text] - bubble text.
 * @property {boolean} [interrupted] - bubbles: the turn was cancelled mid-stream and this is
 *   only the prefix that had arrived. Never render a partial answer as a complete one.
 * @property {string} [source] - who produced a bubble's message: `user`, `plugin`, `model`, `tool`.
 * @property {string} [thinking] - kairos bubbles: the message's reasoning blocks, joined.
 *   Thinking is never chat text; a renderer shows it apart from the bubble or not at all.
 * @property {string} [mode] - pulses: which block kind just opened live — `reasoning`, `text`, `tool-call`.
 * @property {ToolCardView} [card] - the card body.
 * @property {string} [id] - answerable frames: the rpcId `/api/respond` echoes.
 * @property {string} [approvalId] - approvals: the host's audit id (NOT the wire id).
 * @property {string} [toolName] - approvals: the tool awaiting permission.
 * @property {string} [callId] - approvals: the call awaiting permission.
 * @property {string} [reason] - approvals: why permission is being asked, when the host said.
 * @property {unknown[]} [questions] - questions: the AskUserQuestionItem batch (one ask, many questions, ONE answer).
 */

/** @param {unknown} value @returns {boolean} true for a non-null, non-array object. */
function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A view that renders nothing. Built fresh each call so no caller can alias it. @returns {FrameView} */
function ignore() {
  return { kind: "ignore" };
}

/**
 * Join the visible text of a content-block list. `reasoning` blocks are
 * deliberately excluded — thinking is not chat — and so is everything with no
 * text of its own (images, tool calls).
 * @param {unknown} blocks - a ContentBlock[], or anything else.
 * @returns {string} the joined text, possibly empty.
 */
function blocksText(blocks) {
  if (!Array.isArray(blocks)) return "";
  return blocks
    .filter((block) => isObject(block) && block.type === "text" && typeof block.text === "string")
    .map((block) => block.text)
    .join("\n")
    .trim();
}

/** The message's reasoning blocks, joined — the model's thinking, never chat
 * text (message.d.ts reasoning block: same `text` field, its own type).
 * @param {unknown} blocks @returns {string} */
function blocksReasoning(blocks) {
  if (!Array.isArray(blocks)) return "";
  return blocks
    .filter((block) => isObject(block) && block.type === "reasoning" && typeof block.text === "string")
    .map((block) => block.text)
    .join("\n")
    .trim();
}

/**
 * Where a surface event sits in the transcript.
 *
 * `surfaceOp` lives on the session EVENT, not on the mux frame, and only on the
 * three surface types (`SessionEvent`'s conditional member,
 * dsh-session types.d.ts:425-457; the op union at :393-397). Absent means
 * `append` — which is also what every log-only event and every `tool/call` is,
 * since surface metadata is forbidden on them (types.d.ts:398-411).
 *
 * A `replace` is not cosmetic: compaction (mounted in this tree) writes its
 * checkpoint as a `user/message` carrying `{op:'replace', start, end}`
 * (dsh-compaction-basic/lib/index.js:604-616), and a renderer that ignores it
 * shows the summary AND everything it summarized.
 * @param {Record<string, unknown>} event - the session event.
 * @returns {SurfaceOpView} the normalized op; malformed input reads as `append`.
 */
function surfaceOpOf(event) {
  const op = event.surfaceOp;
  if (isObject(op) && op.op === "replace" && typeof op.start === "number" && typeof op.end === "number") {
    return { op: "replace", start: op.start, end: op.end };
  }
  return "append";
}

/**
 * One message as a bubble, or nothing when it has no text. A textless message
 * is real and normal — an assistant message that exists only to host usage or
 * tool calls (session types.d.ts:269-285) — and an empty bubble would be a lie
 * about what was said. v1 limitations that share this drop: an image-only
 * message (the face has no attachment path yet), and — only in theory, since
 * every producer of one frames a summary — a textless REPLACE node, whose
 * shadow instruction would be dropped with it.
 * @param {"operator"|"kairos"} role - which side of the flow.
 * @param {unknown} message - the LLM Message wrapper.
 * @param {FrameView} base - seq/sessionId/surfaceOp already read off the event.
 * @param {boolean} interrupted - whether this is a cancelled turn's prefix.
 * @returns {FrameView}
 */
function bubble(role, message, base, interrupted) {
  const text = isObject(message) ? blocksText(message.content) : "";
  const thinking = role === "kairos" && isObject(message) ? blocksReasoning(message.content) : "";
  if (text === "" && thinking === "") return ignore();
  const source = isObject(message) && isObject(message.source) ? message.source.kind : undefined;
  return {
    ...base,
    kind: "bubble",
    role,
    text,
    interrupted,
    source: typeof source === "string" ? source : undefined,
    thinking: thinking === "" ? undefined : thinking,
  };
}

/**
 * The host's render intent for one phase of a tool call, when the frame carries
 * one for THAT phase (`for` names the vocabulary — events.d.ts:19-33).
 * @param {unknown} toolEventView - the frame's `view` slot.
 * @param {"call"|"result"} phase - the phase being rendered.
 * @returns {Record<string, unknown>|undefined} the phase's view, or undefined.
 */
function renderIntent(toolEventView, phase) {
  if (!isObject(toolEventView) || toolEventView.for !== phase) return undefined;
  return isObject(toolEventView.view) ? toolEventView.view : undefined;
}

/**
 * Map one `session/event` frame (streamed or backfilled) to its view.
 * @param {Record<string, unknown>} frame - a session/event MuxFrame or a history entry.
 * @returns {FrameView}
 */
function mapSessionEvent(frame) {
  const event = frame.event;
  if (!isObject(event) || typeof event.type !== "string") return ignore();
  const data = isObject(event.data) ? event.data : {};
  /** @type {FrameView} */
  const base = {
    kind: "ignore",
    seq: typeof event.seq === "number" ? event.seq : undefined,
    sessionId: typeof frame.sessionId === "string" ? frame.sessionId : undefined,
    surfaceOp: surfaceOpOf(event),
  };

  switch (event.type) {
    case "user/message":
      // The event data IS the message here (SessionEventMap['user/message'] = UserMessage).
      // An operator prompt is committed the moment it is logged: never interrupted.
      return bubble("operator", data, base, false);
    case "assistant/message":
      // interrupted marks a turn cancelled mid-stream: what follows is the
      // delivered PREFIX, not the answer (session types.d.ts:269-285).
      return bubble("kairos", data.message, base, data.interrupted === true);
    case "tool/call": {
      const view = renderIntent(frame.view, "call");
      return { ...base, kind: "card", card: {
        phase: "call",
        callId: typeof data.callId === "string" ? data.callId : undefined,
        name: typeof data.name === "string" ? data.name : undefined,
        title: typeof view?.title === "string" ? view.title : undefined,
        view,
      } };
    }
    case "tool/result": {
      const view = renderIntent(frame.view, "result");
      const message = isObject(data.message) ? data.message : {};
      // ToolResultMessage.content is exactly one ToolResultBlock (message.d.ts:140-144);
      // the source's callId is the same id by construction, kept as the fallback.
      const block = Array.isArray(message.content) && isObject(message.content[0]) ? message.content[0] : {};
      const sourceCallId = isObject(message.source) ? message.source.callId : undefined;
      const callId = typeof block.toolCallId === "string" ? block.toolCallId
        : typeof sourceCallId === "string" ? sourceCallId : undefined;
      return { ...base, kind: "card", card: {
        phase: "result",
        callId,
        title: typeof view?.title === "string" ? view.title : undefined,
        text: blocksText(block.content),
        // Either channel means failure: the block's own flag, or an internal
        // failure identity on the event (session types.d.ts:309-318).
        isError: block.isError === true || isObject(data.error),
        view,
      } };
    }
    case "assistant/chunk": {
      // The stream itself stays log-only, but a block OPENING is the one live
      // signal worth surfacing: it says what Kairos is doing right now
      // (reasoning / text / tool-call) while nothing settled has landed yet.
      const chunk = isObject(data.chunk) ? data.chunk : {};
      if (chunk.type !== "block-start" || typeof chunk.blockType !== "string") return ignore();
      return { ...base, kind: "pulse", mode: chunk.blockType };
    }
    default:
      // Every other session event type is log-only for v1: boundaries
      // (turn/step), raw chunks, todo/write, request headers, compaction.
      return ignore();
  }
}

/**
 * Map one wire frame to its view model.
 * @param {unknown} frame - a mux ServerRequest envelope, a bare MuxFrame, or a
 *   `session.history` entry carrying `{ sessionId, event, view? }`.
 * @returns {FrameView} always a view; unrecognized input maps to `ignore`.
 */
export function mapFrame(frame) {
  if (!isObject(frame)) return ignore();
  const enveloped = frame.type === "server-request";
  const rpcId = enveloped && typeof frame.rpcId === "string" ? frame.rpcId : undefined;
  const mux = enveloped ? frame.payload : frame;
  if (!isObject(mux)) return ignore();

  switch (mux.type) {
    case "approval/requested":
      return {
        kind: "approval",
        id: rpcId,
        sessionId: typeof mux.sessionId === "string" ? mux.sessionId : undefined,
        approvalId: typeof mux.approvalId === "string" ? mux.approvalId : undefined,
        toolName: typeof mux.toolName === "string" ? mux.toolName : undefined,
        callId: typeof mux.callId === "string" ? mux.callId : undefined,
        reason: typeof mux.reason === "string" ? mux.reason : undefined,
      };
    case "question/requested":
      return {
        kind: "question",
        id: rpcId,
        sessionId: typeof mux.sessionId === "string" ? mux.sessionId : undefined,
        questions: Array.isArray(mux.questions) ? mux.questions : [],
      };
    case "session/event":
      return mapSessionEvent(mux);
    case undefined:
      // No frame type: a session.history entry, which carries only { event, view? }.
      return isObject(mux.event) ? mapSessionEvent(mux) : ignore();
    default:
      // session/subscribed · approval/resolved · question/resolved · session/queue ·
      // session/jobs · session/projection · stream/error. All carried, none rendered
      // in v1: the face is a single loopback client with no queue dock, no job list,
      // and no second answerer to be told about. stream/error is the one with a real
      // cost — an internal stream failure stays silent — and is the first candidate
      // when this vocabulary next grows.
      return ignore();
  }
}
