/** The client's wire: one unary call and one reconnecting multiplexed socket,
 * the only two ways this page talks to the host.
 *
 * Pinned to dsh 0.2.0-rc.2, the Typert Remote wire. The 0.1.1 apiproxy wire
 * this file used to speak - `POST /api/<dotted.method>`, `POST /api/respond`,
 * the downlink-only `/api/events.mux` - was deleted upstream (commit
 * 4f00a8b82a); every byte of it now 404s.
 *
 *   `call`     POST `/api/<ns>/<method>`. The body is a client-request whose
 *              `method` repeats the path and whose payload is EXACTLY `{args}`
 *              (NEW packages/client/connection/src/rpc-schema.ts:35-40,
 *              rpc-host.ts:229-268; packages/api/gateway/src/index.ts:1127-1147).
 *              `args` names the method's wire parameters - `{_request:{}}`,
 *              `{request:{…}}`, `{agentId, …}` - and an unknown top-level key
 *              is `gateway/arguments-invalid` (gateway/src/index.ts:1478-1504).
 *              Back comes a server-response, `{ok:true, value?}` or
 *              `{ok:false, error:{code, message, details}}`.
 *   `openMux`  ONE WebSocket at `/api/remote.mux` carrying any number of
 *              logical streams, each keyed by a client-chosen `streamId`
 *              (gateway/src/stream-protocol.ts:7, 234-315; stream-server.ts:168-223).
 *              Client frames: `open`, `cancel`. Host frames: `item`, `end`, `error`.
 *              Three kinds of logical stream ride it:
 *                `$events`          internal to this module, one per socket
 *                                   generation: `ready` (the clientId every answer
 *                                   is bound to), `emit` (host facts such as
 *                                   api-session/*), `waterfall` (an approval or a
 *                                   question waiting on the operator), `cancel`
 *                                   (that wait is over) - stream-protocol.ts:33-71.
 *                `session/control`  host-wide projections: a baseline, then updates.
 *                `session/follow`   one session's transcript: a snapshot, then events.
 *              The caller opens the last two through `stream()`.
 *   `answer`   the operator's decision on a gate, POSTed to `$events/result`
 *              under the CURRENT generation's clientId (gateway/src/index.ts:430-442,
 *              stream-protocol.ts:87-138). The only way to answer an approval
 *              or a question.
 *   `randomUuid`  the client-minted `requestId` a prompt carries, minted in any
 *              context (`crypto.randomUUID` needs a secure one).
 *
 * Auth: every `/api` request and the mux upgrade must carry the HttpOnly
 * browser-session cookie that `GET /?token=…` minted
 * (connection/src/browser-auth.ts:238-280; rpc-host.ts:104-113;
 * gateway/src/index.ts:253-257). Same-origin fetch and WebSocket send it with
 * no code here; its absence is a 401, which `call` reports as "open the URL
 * kairos-face printed".
 * @module
 */

/** How long a lost socket waits before reconnecting. Loopback, one operator:
 * a fixed short delay beats a backoff nobody is there to be gentle to (the
 * upstream client backs off exponentially, NEW packages/client/connection/src/client/connection.ts:139-147). */
const RECONNECT_MS = 1500;

/** WebSocket `readyState` OPEN (WHATWG HTML, web sockets). A literal, so a test double needs no statics. */
const OPEN = 1;

/** How long after a generation's `ready` a gate the page still shows must have
 * been re-delivered before it is retired as settled-while-disconnected. The
 * host queues every pending replay BEFORE it yields `ready` and drains that
 * queue in order (gateway/src/index.ts:512-516), so on loopback the replays
 * trail `ready` by milliseconds; a gate missing after this long was settled
 * while this page held no delivery, and no `cancel` will ever say so
 * (:640-644, 657-668). A late replay simply re-delivers the gate: retirement
 * can close a card early, never grant anything. */
const REPLAY_SETTLE_MS = 1000;

/** How many of its own settled answers one generation remembers, to recognise a
 * LATE `cancel` for one of them. The host removes the answering client's
 * delivery before it settles, so the winner never gets a `cancel`
 * (gateway/src/index.ts:618-623, 646-668): a `cancel` for a gate this page
 * answered means its answer arrived after another tab's (or a Stop) and was a
 * silent no-op `ok`. The `cancel` frame (WebSocket) and the answer's response
 * (HTTP) travel on different connections, so the frame can land AFTER the
 * response resolved `answer`. It is pushed before the losing POST is even
 * processed, so it trails that response by milliseconds; a bound, not a
 * timer, keeps the memory small and the behaviour deterministic. */
const ANSWERED_MEMORY = 64;

/** The two waterfalls the operator answers - exactly the two api-remotes forwards
 * (NEW packages/api/remotes/src/remote-events.ts:22, 47). Any other waterfall is
 * handed straight back with `{kind:"next"}`: the host waits on EVERY delivered
 * client (gateway/src/index.ts:614-633), so one left unanswered would block it. */
const GATE_EVENTS = new Set(["approval/request", "user-questions/request"]);

/** The only approval outcomes the operator may send. The host now takes any
 * vocabulary value from a client (NEW packages/interaction/user-approval/src/index.ts:285-291),
 * so this set is the one place `cancelled`/`unavailable` stay host-side. */
const APPROVAL_ANSWERS = new Set(["allowed-once", "rejected"]);

/** One endpoint segment: the carrier's own charset (rpc-host.ts:36, 280-289). */
const SEGMENT = /^[A-Za-z0-9_$.-]+$/;

/** Monotonic per page load, shared by rpcIds and streamIds. An rpcId is only
 * echoed on its own HTTP response, and a streamId only has to be unique on its
 * own socket - a reload opens a new socket - so restarting at 1 collides with
 * nothing, and no id is ever reused on any socket (a duplicate `open` closes
 * the socket: stream-server.ts:201-204). */
let nextId = 1;

/**
 * A failed `call`. `code` and `details` are the host's own for a business
 * failure (`session/not-found`, `gateway/arguments-invalid`, …, rpc-schema.ts:10-14);
 * `status` is the HTTP status for a carrier failure (401, 404, 415, 500, …),
 * whose body is plain text (rpc-host.ts:229-266).
 * @typedef {Error & {code?: string, details?: unknown, status?: number}} CallError
 */

/**
 * Handlers for one logical stream. Each is optional; a throwing handler is
 * logged and never takes the socket down with it.
 * @typedef {object} StreamHandlers
 * @property {(value: any) => void} [onItem] - one host item, in order.
 * @property {() => void} [onEnd] - the host finished the stream; it is not re-opened.
 * @property {(error: {code: string, message: string, details: object}) => void} [onError] -
 *   the host failed the stream (`session/not-found`, `subagent/unauthorized`, …); it is not re-opened.
 */

/**
 * One pending gate, exactly as the `$events` stream delivers it
 * (stream-protocol.ts:52-58): `request` is the host waterfall's request minus
 * `agent` and `signal` (stream-protocol.ts:146-173) and `agentId` is the session id.
 * @typedef {object} GateFrame
 * @property {"waterfall"} type
 * @property {string} event - `approval/request` or `user-questions/request`.
 * @property {string} eventId - the id `answer` names; the same across reconnects (gateway/src/index.ts:512-516).
 * @property {string} agentId
 * @property {Record<string, unknown>} request
 */

/**
 * @typedef {object} MuxOptions
 * @property {(host: {home: string}) => void} [onReady] - after each generation's
 *   `ready`, the first connect included. Every registered stream has already
 *   been re-opened by then: the caller re-fetches what a socket drop lost (the
 *   session list), never the streams.
 * @property {(event: string, args: unknown[]) => void} [onEvent] - one host
 *   notification (`api-session/added|removed|status|activity|error`,
 *   `agent-preset/selected`, …: remotes/src/remote-events.ts:20-48).
 * @property {(frame: GateFrame) => void} [onGate] - an approval or a question the
 *   operator must answer through `answer`. Pending gates are re-delivered after
 *   every reconnect under their original `eventId`, so render idempotently by it.
 *   Without an `onGate`, every gate is handed back with `next` (the host then
 *   fails it closed: an approval resolves `unavailable`).
 * @property {(eventId: string) => void} [onGateGone] - a gate the page was given
 *   is over, and it carries NO outcome: the host withdrew it from this
 *   generation (another tab answered, the turn stopped, the session went away:
 *   gateway/src/index.ts:646-668), or a reconnect did not replay it, so it was
 *   settled while this page was disconnected (retired `replaySettleMs` after the
 *   new `ready`). The tab whose answer WON gets no such call (:622): its own
 *   `answer` settles its card. It IS called for a gate this page already
 *   answered when the host's `cancel` lands after that answer resolved: the
 *   host never cancels the winner, so the answer lost the race and was not
 *   applied - the caller must relabel a card it marked answered.
 * @property {(reason: string) => void} [onDown] - the socket was lost and a
 *   reconnect is scheduled; `reason` says why, for the status line.
 * @property {number} [reconnectMs] - the reconnect wait; tests shorten it.
 * @property {number} [replaySettleMs] - how long after `ready` an unreplayed gate
 *   is retired (REPLAY_SETTLE_MS); tests shorten it.
 */

/**
 * Why `answer` refused. The host cannot say it - an answer to a gate that is
 * settled, or that this connection was never delivered, is a silent `ok`
 * (gateway/src/index.ts:618-621) - so the refusal is decided here:
 *   `not-ready`    no `ready` has bound a clientId yet (disconnected): answer
 *                  again once it reconnects; pending gates are re-delivered.
 *   `not-pending`  this connection does not hold the gate (answered or withdrawn
 *                  already, or settled while disconnected): the card is dead.
 *   `gate-gone`    the host withdrew the gate while this answer was in flight
 *                  (another tab answered first, or the turn stopped): NOT applied.
 *   `bad-value`    the value is outside the gate's vocabulary: nothing was sent.
 * Any other failure is the `CallError` of the `$events/result` call itself, and
 * the gate stays answerable.
 * @typedef {Error & {code: "not-ready"|"not-pending"|"gate-gone"|"bad-value"}} AnswerError
 */

/**
 * @typedef {object} Mux
 * @property {(endpoint: string, args?: Record<string, unknown>, handlers?: StreamHandlers) => {cancel: () => void}} stream -
 *   open a logical stream now (or when the socket opens), and re-open it under a
 *   fresh id on every reconnect until `cancel()`, `end` or `error`.
 * @property {(eventId: string, value: unknown) => Promise<void>} answer - settle
 *   one gate this generation holds: an approval with `"allowed-once"` or
 *   `"rejected"`, a question with `{answers:[{id, selected, custom?}]}`
 *   (user-questions/src/types.ts:56-69). Rejects with an `AnswerError` (see its
 *   codes) or the call's `CallError`; resolves only when the host took THIS answer.
 * @property {() => void} close - stop for good: the socket closes and a pending
 *   reconnect is cancelled.
 */

/** @param {unknown} value @returns {value is Record<string, any>} a plain JSON object. */
function isRecord(value) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

/** Exact own keys, as the host's parsers demand (stream-protocol.ts:340-343).
 * @param {Record<string, unknown>} value @param {string[]} keys @returns {boolean} */
function hasKeys(value, keys) {
  const own = Reflect.ownKeys(value);
  return own.length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}

/** @param {unknown} value @returns {value is string} */
function nonEmpty(value) {
  return typeof value === "string" && value.length > 0;
}

/** `<namespace>/<method>`, each segment in the carrier's charset. The gateway
 * claims only two-segment endpoints (and `$events/result`), so a 0.1.1 dotted
 * name such as `session.list` is refused here with a message that says why,
 * instead of reaching the host as a bare 404 (gateway/src/index.ts:325-332).
 * @param {unknown} endpoint @returns {endpoint is string} */
function isEndpoint(endpoint) {
  if (typeof endpoint !== "string") return false;
  const segments = endpoint.split("/");
  return segments.length === 2 && segments.every((s) => s !== "." && s !== ".." && SEGMENT.test(s));
}

/**
 * A random v4 UUID for a client-minted wire id - `session/prompt`'s and
 * `subagents/prompt`'s `requestId`, which the host persists as the message's
 * `source.rpcId` and dedupes on, so a retry with the same id is idempotent
 * (NEW packages/api/session-controller/src/types.ts:332-340, 397-405).
 * `crypto.randomUUID` exists only in secure contexts, so a page reached by a
 * LAN name over plain HTTP has none; `crypto.getRandomValues` exists everywhere.
 * Mirrors upstream's own minting (NEW packages/util/crypto/src/index.ts `randomUUID`).
 * @returns {string}
 */
export function randomUuid() {
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  // RFC 9562 §5.4: version 4 in the high nibble of byte 6, variant 10 in byte 8.
  const hex = Array.from(bytes, (byte, index) => {
    const pinned = index === 6 ? (byte & 0x0f) | 0x40 : index === 8 ? (byte & 0x3f) | 0x80 : byte;
    return pinned.toString(16).padStart(2, "0");
  }).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

/** @param {string} message @param {{code?: string, details?: unknown, status?: number}} [fields] @returns {CallError} */
function callError(message, fields = {}) {
  return Object.assign(new Error(message), fields);
}

/** @param {AnswerError["code"]} code @param {string} message @returns {AnswerError} */
function answerError(code, message) {
  return Object.assign(new Error(`answer: ${message}`), { code });
}

/**
 * Rebuild a byte-bearing result: the host answers `multipart/form-data` when a
 * value holds a `Uint8Array`, with the envelope in part `metadata` and each
 * `null` placeholder at `attachments[i].path` filled from part `attachments[i].part`
 * (rpc-host.ts:295-312). Mirrors the upstream browser caller
 * (NEW packages/client/connection/src/client/rpc.ts:83-139). No face endpoint
 * returns bytes today; this keeps one that starts to from failing as "not JSON".
 * @param {Response} res @param {string} endpoint @returns {Promise<unknown>} the envelope.
 */
async function binaryEnvelope(res, endpoint) {
  const bad = (/** @type {string} */ why) => callError(`${endpoint}: bad-response - ${why}`, { code: "bad-response" });
  const form = await res.formData();
  const metadata = form.get("metadata");
  if (typeof metadata !== "string") throw bad("multipart result without a metadata part");
  const envelope = JSON.parse(metadata);
  if (!isRecord(envelope) || !isRecord(envelope.result) || envelope.result.ok !== true || !Array.isArray(envelope.attachments)) {
    throw bad("invalid multipart envelope");
  }
  const root = { value: envelope.result.value };
  for (const attachment of envelope.attachments) {
    if (!isRecord(attachment) || attachment.codec !== "bytes" || !nonEmpty(attachment.part) || !Array.isArray(attachment.path)) {
      throw bad("invalid multipart attachment");
    }
    const data = form.get(attachment.part);
    if (!(data instanceof Blob)) throw bad(`missing multipart part ${attachment.part}`);
    /** @type {any} */ let parent = root;
    /** @type {string|number} */ let key = "value";
    for (const segment of attachment.path) {
      const next = parent[key];
      if (typeof next !== "object" || next === null || !Object.hasOwn(next, segment)) throw bad("invalid attachment path");
      parent = next;
      key = segment;
    }
    if (parent[key] !== null) throw bad("attachment path names no null placeholder");
    parent[key] = new Uint8Array(await data.arrayBuffer());
  }
  return { ...envelope, result: { ok: true, value: root.value } };
}

/**
 * Call one unary host method.
 *
 * The `content-type` is load-bearing, not habit: the host answers 415 to any
 * other media type (rpc-host.ts:235-238), so a cross-site "simple" POST cannot
 * reach a side-effectful method without a preflight it never answers. A non-2xx
 * is a CARRIER failure whose body is plain text; a business failure arrives as
 * 200 with an error result.
 * @param {string} endpoint - `<namespace>/<method>`, e.g. `session/list` (Appendix A of the upgrade plan).
 * @param {Record<string, unknown>} [args] - the method's wire parameters, every one
 *   sent (`{_request:{}}` for `session/list`): a strict descriptor refuses a
 *   missing required one (gateway/src/index.ts:1494-1498).
 * @returns {Promise<any>} the business VALUE (`result.value`), unwrapped; a void
 *   method has no `value` key and resolves to undefined (gateway/src/index.ts:1004-1014).
 * @throws {CallError} on a business failure (host `code` + `message`), a carrier
 *   failure (`status`; 401 = not signed in), or a response that is not this call's.
 */
export async function call(endpoint, args = {}) {
  if (!isEndpoint(endpoint)) {
    throw callError(`call: ${JSON.stringify(endpoint)} is not a <namespace>/<method> endpoint (the 0.1.1 dotted names are gone)`);
  }
  if (!isRecord(args)) throw callError(`${endpoint}: args must be a plain object of wire parameters`);
  const rpcId = `c${nextId++}`;
  const res = await fetch(`/api/${endpoint}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ type: "client-request", rpcId, method: endpoint, payload: { args } }),
  });
  if (res.status === 401) {
    // Admission runs before any RPC handling (rpc-host.ts:104-113, 181-187): no
    // valid browser-session cookie. Only the tokenized URL can mint one.
    throw callError(
      `${endpoint}: not signed in - open the URL kairos-face printed when it started (…/?token=…); ` +
        "that visit sets a 30-day cookie for this host:port",
      { status: 401 },
    );
  }
  if (!res.ok) {
    const detail = (await res.text().catch(() => "")).slice(0, 200);
    const hint = res.status === 403 ? " (the host's Host/Origin fence refused this page: open it at the printed 127.0.0.1 URL)" : "";
    throw callError(`${endpoint}: HTTP ${res.status} ${detail}${hint}`.trim(), { status: res.status });
  }
  const mediaType = res.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase();
  /** @type {any} */ let body;
  if (mediaType === "multipart/form-data") body = await binaryEnvelope(res, endpoint);
  else {
    try {
      body = await res.json();
    } catch {
      throw callError(`${endpoint}: bad-response - the body is not JSON`, { code: "bad-response" });
    }
  }
  // Echoed rpcId (rpc-host.ts:295-301): anything else is not this call's answer.
  if (!isRecord(body) || body.type !== "server-response" || body.rpcId !== rpcId || !isRecord(body.result)) {
    throw callError(`${endpoint}: bad-response - not the server-response to ${rpcId}`, { code: "bad-response" });
  }
  const result = body.result;
  if (result.ok !== true) {
    // RpcError is an OBJECT (code + message + details), never a string (rpc-schema.ts:10-14).
    const code = typeof result.error?.code === "string" ? result.error.code : "bad-response";
    const message = typeof result.error?.message === "string" ? result.error.message : "host returned no result";
    throw callError(`${endpoint}: ${code} - ${message}`, { code, details: result.error?.details });
  }
  return result.value;
}

/**
 * Validate one host frame against the host's own grammar, exact keys included
 * (stream-protocol.ts:293-315; the upstream client fails its whole generation
 * on a frame that does not parse, client/stream-client.ts:306-322).
 * @param {unknown} data - one WebSocket message.
 * @returns {{type: "item", streamId: string, value?: unknown}
 *   | {type: "end", streamId: string}
 *   | {type: "error", streamId: string, error: {code: string, message: string, details: object}}
 *   | undefined} the frame, or undefined when it breaks the grammar.
 */
function hostFrame(data) {
  if (typeof data !== "string") return undefined; // text frames only (stream-server.ts:150-160)
  let frame;
  try {
    frame = JSON.parse(data);
  } catch {
    return undefined;
  }
  if (!isRecord(frame) || !nonEmpty(frame.streamId)) return undefined;
  if (frame.type === "item" && (hasKeys(frame, ["type", "streamId"]) || hasKeys(frame, ["type", "streamId", "value"]))) {
    return /** @type {any} */ (frame);
  }
  if (frame.type === "end" && hasKeys(frame, ["type", "streamId"])) return /** @type {any} */ (frame);
  if (frame.type === "error" && hasKeys(frame, ["type", "streamId", "error"]) && isRecord(frame.error)
    && hasKeys(frame.error, ["code", "message", "details"]) && typeof frame.error.code === "string"
    && typeof frame.error.message === "string" && isRecord(frame.error.details)) {
    return /** @type {any} */ (frame);
  }
  return undefined;
}

/**
 * Validate one `$events` item after `ready`, as the upstream client does
 * (NEW packages/api/gateway/src/client/remote-events.ts:282-314).
 * @param {unknown} value
 * @returns {{type: "emit", event: string, args: unknown[]} | {type: "cancel", eventId: string} | GateFrame | undefined}
 */
function eventItem(value) {
  if (!isRecord(value)) return undefined;
  if (value.type === "cancel" && hasKeys(value, ["type", "eventId"]) && nonEmpty(value.eventId)) {
    return /** @type {any} */ (value);
  }
  if (value.type === "emit" && hasKeys(value, ["type", "event", "args"]) && nonEmpty(value.event) && Array.isArray(value.args)) {
    return /** @type {any} */ (value);
  }
  if (value.type === "waterfall" && hasKeys(value, ["type", "event", "eventId", "agentId", "request"])
    && nonEmpty(value.event) && nonEmpty(value.eventId) && nonEmpty(value.agentId) && isRecord(value.request)
    && !Object.hasOwn(value.request, "agent") && !Object.hasOwn(value.request, "signal")) {
    return /** @type {any} */ (value);
  }
  return undefined;
}

/**
 * Run one caller handler so that its bug stays its own: logged, never thrown
 * into the socket's message loop where it would starve every other stream.
 * @param {string} label @param {() => void} run
 */
function safely(label, run) {
  try {
    run();
  } catch (err) {
    console.error(`face: mux ${label} handler threw`, err);
  }
}

/**
 * @typedef {object} Entry - one registered logical stream, alive across socket generations.
 * @property {string} endpoint
 * @property {Record<string, unknown>} args
 * @property {StreamHandlers} handlers
 * @property {boolean} internal - the module's own `$events`: never dropped, re-opened for good.
 * @property {Generation|null} gen - the generation it is open on.
 * @property {string|null} streamId - its id on that generation's socket.
 */

/**
 * @typedef {object} Generation - one physical socket and everything bound to it.
 * @property {WebSocket} ws
 * @property {boolean} opened - the socket reached `open`.
 * @property {boolean} dead - lost or closed; nothing on it counts any more.
 * @property {boolean} ready - its `$events` stream delivered `ready`.
 * @property {string|null} clientId - from that `ready`; answers name it.
 * @property {Map<string, Entry>} streams - by streamId, on this socket.
 * @property {Map<string, string>} gates - eventId → gate event, for the gates THIS
 *   generation was delivered and has not seen settle: the host's own
 *   `client.deliveries` for it (gateway/src/index.ts:608-612, 640-644).
 * @property {Set<string>} answered - eventIds this generation's `answer` resolved
 *   (the last ANSWERED_MEMORY), so a late `cancel` for one of them is reported
 *   as the lost race it is.
 * @property {ReturnType<typeof setTimeout>|null} retire - the pending retirement
 *   of gates this generation did not replay.
 */

/**
 * Open the multiplexed socket and keep it open for as long as the page lives.
 *
 * Reconnect contract. There is no resume cursor anywhere on this wire: each
 * socket is a new generation. On every connect, the first included, every
 * registered stream is opened again under a FRESH streamId - `$events` first -
 * and each delivers a fresh opening (a new `ready` and clientId, a new control
 * baseline, a new follow snapshot); the caller dedupes transcript events by
 * `seq`. Pending gates are replayed right after `ready` with their original
 * `eventId` (gateway/src/index.ts:512-516); a gate the page was given that the
 * new generation does NOT replay was settled while no delivery of this page
 * existed - no `cancel` can say so (:640-644) - and is reported gone
 * `replaySettleMs` after `ready`. A socket that closes, a frame that
 * breaks the grammar, and an `$events` stream that ends or fails all lose the
 * generation the same way: the socket is dropped and the next one opens after
 * `reconnectMs` - the upstream client treats every one of them as a lost
 * generation too (client/remote-events.ts:169-183).
 *
 * `close()` is honoured at every moment of the cycle, the reconnect WAIT
 * included: a pending timer is cleared and `connect` refuses to run once
 * closed, so a closed mux never resurrects itself into a second socket that
 * keeps calling handlers that stopped listening.
 * @param {MuxOptions} [options]
 * @returns {Mux}
 */
export function openMux(options = {}) {
  const {
    onReady, onEvent, onGate, onGateGone, onDown,
    reconnectMs = RECONNECT_MS, replaySettleMs = REPLAY_SETTLE_MS,
  } = options;
  /** @type {Generation|null} */
  let current = null;
  let closed = false;
  /** @type {ReturnType<typeof setTimeout>|null} */
  let retry = null;
  /** Every live stream in registration order; a Set iterates in insertion order, so `$events` re-opens first. @type {Set<Entry>} */
  const registry = new Set();
  /** Every gate handed to `onGate` and not yet reported over (withdrawn,
   * answered here, or retired): the cards the page may still be showing,
   * across generations. @type {Set<string>} */
  const held = new Set();

  /** Report one held gate over, once. @param {string} eventId */
  const gone = (eventId) => {
    if (held.delete(eventId)) safely("onGateGone", () => onGateGone?.(eventId));
  };

  /** Retire every held gate this generation was not re-delivered: settled while
   * no delivery of this page existed, so no `cancel` will come for it.
   * @param {Generation} gen */
  const retireUnreplayed = (gen) => {
    gen.retire = null;
    if (gen !== current || gen.dead) return;
    for (const eventId of [...held]) if (!gen.gates.has(eventId)) gone(eventId);
  };

  /** The module's own `$events` stream: exactly `{args:{}}`, or the gateway
   * refuses it (gateway/src/index.ts:477-494). @type {Entry} */
  const events = {
    endpoint: "$events",
    args: {},
    internal: true,
    gen: null,
    streamId: null,
    handlers: {
      onItem: (value) => { if (current !== null) acceptEvent(current, value); },
      // Without `$events` no gate can reach this page and no answer can be
      // bound, so its end is the generation's end (remote-events.ts:178-183).
      onEnd: () => lose(current, "the $events stream ended", 4000),
      onError: (error) => lose(current, `the $events stream failed: ${error.code} - ${error.message}`, 4000),
    },
  };
  registry.add(events);

  /**
   * Hand one waterfall back to the host: `{kind:"next"}` removes this client's
   * delivery, and the host moves on once every delivered client has
   * (gateway/src/index.ts:625-633; stream-protocol.ts:111-117).
   * @param {Generation} gen @param {string} eventId
   */
  const delegate = (gen, eventId) => {
    if (gen.clientId === null) return; // unreachable: `ready` is always the first item
    void call("$events/result", { clientId: gen.clientId, eventId, outcome: { kind: "next" } }).catch((err) => {
      console.warn(`face: could not hand host event ${eventId} back: ${err instanceof Error ? err.message : String(err)}`);
    });
  };

  /** @param {Generation} gen @param {unknown} value */
  const acceptEvent = (gen, value) => {
    if (gen.dead) return;
    if (!gen.ready) {
      // `ready` is always first on the wire, pending replays after it
      // (gateway/src/index.ts:512-516); anything else first is a broken stream
      // (upstream parseRemoteEventReady, client/remote-events.ts:265-279).
      if (!isRecord(value) || value.type !== "ready" || !hasKeys(value, ["type", "clientId", "host"])
        || !nonEmpty(value.clientId) || !isRecord(value.host) || !hasKeys(value.host, ["home"])
        || typeof value.host.home !== "string") {
        lose(gen, "the $events stream did not begin with ready", 4002);
        return;
      }
      gen.ready = true;
      gen.clientId = value.clientId;
      const host = { home: value.host.home };
      safely("onReady", () => onReady?.(host));
      if (held.size > 0) gen.retire = setTimeout(() => retireUnreplayed(gen), replaySettleMs);
      return;
    }
    const item = eventItem(value);
    if (item === undefined) {
      lose(gen, "the $events stream sent an invalid item", 4002);
      return;
    }
    if (item.type === "emit") {
      safely("onEvent", () => onEvent?.(item.event, item.args));
      return;
    }
    if (item.type === "cancel") {
      // Only a gate this generation holds can be withdrawn from it (:646-668).
      if (gen.gates.delete(item.eventId)) {
        gone(item.eventId);
      } else if (gen.answered.delete(item.eventId)) {
        // A gate this generation already ANSWERED: the host never cancels the
        // winner (:618-623), so this answer lost a race its HTTP response
        // outran. It is no longer `held`, so report it directly.
        const eventId = item.eventId;
        safely("onGateGone", () => onGateGone?.(eventId));
      }
      return;
    }
    if (!GATE_EVENTS.has(item.event) || typeof onGate !== "function") {
      delegate(gen, item.eventId);
      return;
    }
    gen.gates.set(item.eventId, item.event);
    held.add(item.eventId);
    // A throwing renderer leaves the gate pending, as 0.1.1 did: the host keeps
    // waiting (never granting), Stop still withdraws it, and a reload replays it.
    safely("onGate", () => onGate(/** @type {GateFrame} */ (item)));
  };

  /**
   * Lose a generation once: its streams, clientId and gates die with it, and
   * the next socket is scheduled.
   * @param {Generation|null} gen
   * @param {string} reason
   * @param {number} [code] - close the socket ourselves with this code (4000:
   *   reconnect requested, 4002: invalid frame - upstream's codes,
   *   client/stream-client.ts:82, 320). Omitted when the socket already closed.
   */
  const lose = (gen, reason, code) => {
    if (gen === null || gen !== current || gen.dead) return;
    gen.dead = true;
    // Its gates stay held: the next generation's replay decides which live on.
    if (gen.retire !== null) clearTimeout(gen.retire);
    gen.retire = null;
    if (code !== undefined) {
      try {
        gen.ws.close(code, reason.slice(0, 120));
      } catch {
        // already closing: nothing more to release
      }
    }
    if (closed) return;
    console.warn(`face: mux ${reason}; reconnecting in ${reconnectMs}ms`);
    safely("onDown", () => onDown?.(reason));
    retry = setTimeout(connect, reconnectMs);
  };

  /** @param {Generation} gen @param {Entry} entry */
  const openOn = (gen, entry) => {
    const streamId = `s${nextId++}`;
    entry.gen = gen;
    entry.streamId = streamId;
    gen.streams.set(streamId, entry);
    // Exactly these four keys: the host closes the socket on any other shape (stream-protocol.ts:277-283).
    gen.ws.send(JSON.stringify({ type: "open", streamId, endpoint: entry.endpoint, payload: { args: entry.args } }));
  };

  /** @param {Generation} gen @param {unknown} data */
  const receive = (gen, data) => {
    if (gen !== current || gen.dead) return;
    const frame = hostFrame(data);
    if (frame === undefined) {
      // A dropped frame would be a silent gap (a missing transcript event, a
      // lost gate); a fresh generation re-delivers everything instead.
      lose(gen, "received a frame outside the Remote stream grammar", 4002);
      return;
    }
    const entry = gen.streams.get(frame.streamId);
    // A stream already cancelled or finished: its in-flight frames are dropped,
    // exactly as the host drops ours (stream-server.ts:168-172).
    if (entry === undefined) return;
    if (frame.type === "item") {
      safely(`${entry.endpoint} item`, () => entry.handlers.onItem?.(frame.value));
      return;
    }
    gen.streams.delete(frame.streamId);
    entry.streamId = null;
    if (!entry.internal) registry.delete(entry);
    if (frame.type === "end") safely(`${entry.endpoint} end`, () => entry.handlers.onEnd?.());
    else safely(`${entry.endpoint} error`, () => entry.handlers.onError?.(frame.error));
  };

  const connect = () => {
    retry = null;
    if (closed) return;
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    /** @type {WebSocket} */ let ws;
    try {
      ws = new WebSocket(`${scheme}//${location.host}/api/remote.mux`);
    } catch (err) {
      console.error("face: mux could not create its WebSocket", err);
      retry = setTimeout(connect, reconnectMs);
      return;
    }
    /** @type {Generation} */
    const gen = {
      ws, opened: false, dead: false, ready: false, clientId: null,
      streams: new Map(), gates: new Map(), answered: new Set(), retire: null,
    };
    current = gen;
    ws.onopen = () => {
      if (gen !== current || gen.dead) return;
      gen.opened = true;
      for (const entry of registry) openOn(gen, entry);
    };
    ws.onmessage = (message) => receive(gen, message.data);
    ws.onclose = () => {
      // The browser hides an upgrade's HTTP status: a 401 (no cookie), a 403
      // (fence) and a host that is down all look like this (stream-server.ts:433-444).
      lose(gen, gen.opened ? "socket closed" : "socket closed before opening (host down, or the upgrade was refused: 401 not signed in / 403 fence)");
    };
  };

  connect();

  return {
    stream(endpoint, args = {}, handlers = {}) {
      if (closed) throw new Error("mux: stream() after close()");
      // `$events` is this module's own: a second one would be a second clientId
      // that no answer here is bound to.
      if (!isEndpoint(endpoint)) throw new Error(`mux: ${JSON.stringify(endpoint)} is not a <namespace>/<method> stream endpoint`);
      if (!isRecord(args)) throw new Error(`mux: ${endpoint} args must be a plain object of wire parameters`);
      JSON.stringify(args); // a non-JSON value throws HERE, not later inside a reconnect
      /** @type {Entry} */
      const entry = { endpoint, args, handlers, internal: false, gen: null, streamId: null };
      registry.add(entry);
      const gen = current;
      if (gen !== null && !gen.dead && gen.opened && gen.ws.readyState === OPEN) openOn(gen, entry);
      return {
        cancel() {
          if (!registry.delete(entry)) return; // idempotent; a no-op after end or error
          const on = entry.gen;
          const streamId = entry.streamId;
          entry.streamId = null;
          if (on === null || streamId === null || !on.streams.delete(streamId)) return;
          // Fire-and-forget: the host sends no terminal frame for a cancel (stream-server.ts:243-251).
          if (on === current && !on.dead && on.ws.readyState === OPEN) on.ws.send(JSON.stringify({ type: "cancel", streamId }));
        },
      };
    },

    async answer(eventId, value) {
      const gen = current;
      if (closed || gen === null || gen.dead || gen.clientId === null) {
        throw answerError("not-ready", "the event stream is not connected (no clientId yet) - answer again once it reconnects");
      }
      const event = gen.gates.get(eventId);
      if (event === undefined) {
        throw answerError("not-pending", `gate ${eventId} is not pending on this connection (answered, withdrawn, or settled while disconnected)`);
      }
      if (event === "approval/request" && (typeof value !== "string" || !APPROVAL_ANSWERS.has(value))) {
        throw answerError("bad-value", `an approval takes "allowed-once" or "rejected", not ${JSON.stringify(value)}`);
      }
      if (event === "user-questions/request" && !(isRecord(value) && Array.isArray(value.answers))) {
        throw answerError("bad-value", "a question takes {answers:[{id, selected, custom?}]}");
      }
      await call("$events/result", { clientId: gen.clientId, eventId, outcome: { kind: "result", value } });
      // The winner's own delivery is removed BEFORE the host settles, so the
      // winner never gets a `cancel` (gateway/src/index.ts:618-623, 646-668): a
      // `cancel` that landed while this answer was in flight means another
      // answer or a Stop settled the gate first, and this one was a no-op.
      if (!gen.gates.delete(eventId)) {
        throw answerError("gate-gone", `gate ${eventId} was settled elsewhere before this answer arrived; it was not applied`);
      }
      held.delete(eventId); // settled by this answer: its card is the caller's to settle, not a gone gate's
      // Remembered so a `cancel` that trails this response still reports the
      // lost race (ANSWERED_MEMORY); a Set iterates oldest-first.
      gen.answered.add(eventId);
      if (gen.answered.size > ANSWERED_MEMORY) gen.answered.delete(gen.answered.values().next().value);
    },

    close() {
      if (closed) return;
      closed = true;
      if (retry !== null) clearTimeout(retry);
      retry = null;
      const gen = current;
      current = null;
      registry.clear();
      held.clear();
      if (gen === null) return;
      gen.dead = true;
      if (gen.retire !== null) clearTimeout(gen.retire);
      gen.retire = null;
      try {
        gen.ws.close(1000, "closed by the page");
      } catch {
        // already closing
      }
    },
  };
}
