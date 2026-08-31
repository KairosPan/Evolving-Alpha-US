/** The client's wire envelope: the one place that speaks the harness's
 * four-quadrant RPC message model (rpc.d.ts:231-261).
 *
 * Three shapes, three functions — they are NOT interchangeable:
 *   `rpc`      a client-request POSTed to `/api/<method>`; the HTTP body back is a
 *              server-response whose `result` is `{ok:true,value}` or `{ok:false,error}`.
 *   `respond`  a client-RESPONSE POSTed to `/api/respond`, echoing the rpcId of an
 *              answerable server-request. It mints no id, names no method, and the
 *              HTTP body back is a carrier RECEIPT (`{accepted}`), not a response.
 *              This is the only way to answer an approval or a question.
 *   `openMux`  the downstream WebSocket at `/api/events.mux`. Downlink only —
 *              the host closes a socket that sends anything (1008 "downlink only").
 *
 * The face composes a reduced host: the client stays on `session.*`, `respond`,
 * and `events.mux`, because several stock rows are not mounted.
 * @module
 */

/** Monotonic client-request id. Per page load, and only ever echoed back on the
 * same HTTP response, so a reload restarting at 1 collides with nothing. */
let nextRpcId = 1;

/** How long a dropped mux socket waits before reconnecting. Loopback, one
 * client: a fixed short delay beats a backoff nobody is there to be gentle to. */
const RECONNECT_MS = 1500;

/**
 * POST one JSON envelope and read the JSON body back.
 *
 * The `content-type` is load-bearing, not habit: the host answers 415 to any
 * other media type on purpose, so that a cross-site "simple" POST cannot reach
 * a side-effectful method without a preflight it never answers
 * (fetch/handler.js `toFetchHandler`). A non-2xx here is a CARRIER failure
 * (404/415/400/500) whose body is plain text; business failures arrive as 200
 * with an error result and are read by the callers below.
 * @param {string} path - the absolute API path.
 * @param {unknown} body - the envelope to send.
 * @returns {Promise<any>} the parsed JSON body.
 * @throws {Error} when the carrier failed or the body is not JSON.
 */
async function postJson(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${path}: HTTP ${res.status} ${detail.slice(0, 200)}`.trim());
  }
  return res.json();
}

/**
 * Call one unary host method.
 * @param {string} method - an RpcMethodMap key, e.g. `session.list` (rpc-map.d.ts:23-76).
 *   The path segment and the envelope's `method` must agree; the host rejects a mismatch.
 * @param {unknown} [payload] - the method's business payload.
 * @returns {Promise<any>} the business VALUE (`result.value`), unwrapped — a
 *   method that returns nothing resolves to undefined.
 * @throws {Error} on a business error, carrying the host's own code and message.
 */
export async function rpc(method, payload = {}) {
  const rpcId = `c${nextRpcId++}`;
  const body = await postJson(`/api/${method}`, { type: "client-request", rpcId, method, payload });
  const result = body?.result;
  if (result?.ok !== true) {
    // RpcError is an OBJECT (code + message + details), never a string (rpc.d.ts:181-187).
    const code = result?.error?.code ?? "bad-response";
    const message = result?.error?.message ?? "host returned no result";
    throw new Error(`${method}: ${code} - ${message}`);
  }
  return result.value;
}

/**
 * Answer one answerable server-request: an approval or a question.
 * @param {string} rpcId - the id of the frame being answered, taken VERBATIM from
 *   the mux envelope (`view.id` from the mapper). Minting a new one answers nothing.
 * @param {unknown} value - the domain answer payload:
 *   approvals `{sessionId, approvalId, outcome:"allowed-once"|"rejected"}` (approvals.d.ts:15-19);
 *   questions `{sessionId, answer:{answers:[{id, selected:[label], custom?}]}}` (questions.d.ts:14-17)
 *   — one ask is answered as a whole batch, never split per question.
 * @returns {Promise<void>} resolves once the host accepts the answer.
 * @throws {Error} when the host refuses it: `not-pending` (already answered,
 *   cancelled, or too late) or `bad-response` (rpc.d.ts:256-261).
 */
export async function respond(rpcId, value) {
  const receipt = await postJson("/api/respond", {
    type: "client-response",
    rpcId,
    result: { ok: true, value },
  });
  if (receipt?.accepted !== true) throw new Error(`respond: ${receipt?.reason ?? "refused"}`);
}

/**
 * Open the all-session mux stream, reconnecting for as long as the page lives.
 *
 * On open the host emits a subscribed frame per attached session and REPLAYS
 * every still-pending approval/question with its original rpcId — that replay is
 * the refresh-recovery baseline, so a reconnect never strands a pending gate
 * (events.d.ts:44-61). What it does NOT replay is conversation: `since` is
 * unimplemented at this pin, and the documented recovery is "reopen the stream
 * and refetch history" — which is what `onOpen` is for.
 *
 * `close()` is honoured at every moment of the cycle, the reconnect WAIT
 * included: a pending timer is cleared and `connect` refuses to run once
 * closed, so a closed stream can never resurrect itself into a second socket
 * that keeps delivering frames to a listener that stopped listening.
 * @param {(frame: unknown) => void} onFrame - receives each parsed frame; pass it to `mapFrame`.
 * @param {{onOpen?: () => void, reconnectMs?: number}} [options] - `onOpen` fires on every
 *   successful connect, the first included. `reconnectMs` overrides the reconnect wait;
 *   it exists so tests can exercise the reconnect window without sleeping through it.
 * @returns {{close: () => void}} closes the stream and stops reconnecting, for good.
 */
export function openMux(onFrame, options = {}) {
  const { onOpen, reconnectMs = RECONNECT_MS } = options;
  let socket = null;
  let closed = false;
  let retry = null;
  const connect = () => {
    retry = null;
    if (closed) return;
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${scheme}//${location.host}/api/events.mux`);
    socket.onopen = () => onOpen?.();
    socket.onmessage = (message) => {
      let frame;
      try {
        frame = JSON.parse(message.data);
      } catch {
        // A frame the wire mangled: skip it, but say so. Swallowing the handler
        // call as well would hide renderer bugs behind "bad frame".
        console.warn("face: dropped an unparseable mux frame");
        return;
      }
      onFrame(frame);
    };
    socket.onclose = () => {
      if (closed) return;
      console.warn(`face: mux stream closed, reconnecting in ${reconnectMs}ms`);
      retry = setTimeout(connect, reconnectMs);
    };
  };
  connect();
  return {
    close: () => {
      closed = true;
      if (retry !== null) clearTimeout(retry);
      retry = null;
      socket?.close();
    },
  };
}
