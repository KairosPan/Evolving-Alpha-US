/** Gate 2's POSITIVE path, on a real booted face: an order that a human
 * approves actually dispatches, and one a human rejects does not.
 *
 * WHY THIS EXISTS. At dsh 0.2.0 the `Session.events` getter disappeared
 * (commit 5660f44d29). The guard read it, saw `undefined`, and denied EVERY
 * order - including ones the operator had just approved. It failed closed, so
 * nothing looked wrong: `order-gate.test.ts` only drills the ask and the
 * denials, and the README's "What is NOT drilled" admitted the approved path
 * was never automated (MAP gate2 §0.1). This file is the test that would have
 * caught it. Run it after every future dsh pin bump (PLAN §7).
 *
 * HOW. The model is upstream's own approval routing test, NEW
 * `packages/core/tools/tests/tools.spec.ts:799-842`: an `approval/request`
 * answerer returns a fixed outcome, `ctx.tools.execute` runs the call, and the
 * body's side effect is the evidence. Six steps (PLAN S7):
 * 1. a scratch home with AKShare disabled, then `bootFace`;
 * 2. a stand-in `mcp__drill__place_order` whose description carries
 *    `OPERATOR_GATED_MARKER` - the raw-name suffix exercises the identical gate
 *    code path with nothing behind it (no keys, no broker; README forbids
 *    drilling with the real order tools, since arming Gate 1 to test Gate 2
 *    disarms Gate 1);
 * 3. a root `approval/request` listener registered with `prepend`, so it is
 *    the OUTERMOST listener and claims before the `api-remotes` forwarder
 *    (cordis waterfall runs outermost-first and a listener that does not call
 *    `next()` ends it, NEW `vendor/cordis/src/events.ts:226-243`; `prepend`
 *    unshifts, `:255`; an untagged root listener is admitted for every scoped
 *    dispatch, `packages/core/scope/src/index.ts:170-183`);
 * 4. a real session created over the gateway (`session/create`), its live
 *    agent, and an open turn - `ApprovalService.request` throws outside one
 *    (NEW `packages/interaction/user-approval/src/index.ts:84-92, 215-223`);
 * 5. `ctx.tools.execute` with `allowed-once`: the body RAN;
 * 6. the same with `rejected`: the body did not run, and the model reads the
 *    upstream sentence `the user rejected tool "<name>"`
 *    (NEW `packages/core/tools/src/index.ts:1754-1757`).
 *
 * This proves the host half end to end: gate listener -> `ask` -> the real
 * ApprovalService -> the answerer -> the logged `approval/asked` +
 * `approval/decided` pair -> the guard reading it through `snapshotEvents()`
 * -> dispatch.
 *
 * Step 7 then removes the stand-in answerer and drives the REAL channel the
 * browser uses, so the in-process shortcut cannot hide a broken forwarder
 * (critique-wire-correctness G1): two `$events` streams on one cookie-admitted
 * `/api/remote.mux` socket, the `approval/request` waterfall item reaching
 * both, `POST /api/$events/result` with `allowed-once` from one, the body
 * running, and the other receiving `cancel` (NEW
 * `packages/api/gateway/src/index.ts:505-516, 583-602, 615-668`;
 * `stream-protocol.ts:7-71, 235-258`; forwarder
 * `packages/api/remotes/src/index.ts:57-75`). It does NOT prove the browser
 * card renders; that stays the operator drill in `face/README.md`.
 *
 * Gated behind `FACE_SMOKE=1` and in its own FILE for the reason
 * `smoke.test.ts` states: `bootFace` sets `process.env.DSH_HOME` permanently,
 * so one boot per process, and `node --test` gives each file its own.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { OPERATOR_GATED_MARKER } from "../src/orders.ts";
import { makeBotsRoot } from "./bots-fixture.ts";
import { mountClient, remote, remoteResult, signIn } from "./remote.ts";

const gated = process.env.FACE_SMOKE !== "1";


/** The outcomes the face client may send (PLAN §1.1(a)); the host would
 * accept any vocabulary value, so the smoke only ever uses these two. */
type Answer = "allowed-once" | "rejected";

/** What the answerer saw - the projected request a client card is drawn from. */
interface SeenRequest {
  toolName?: unknown;
  callId?: unknown;
  reason?: unknown;
  displayReason?: { en?: unknown };
}

/** One session event, structurally - just what the audit assertions read. */
interface EventLike {
  type: string;
  data?: { id?: unknown; callId?: unknown; toolName?: unknown; outcome?: unknown };
}

/** One Host-to-browser mux frame (NEW packages/api/gateway/src/stream-protocol.ts:271-274). */
interface MuxFrame {
  type: "item" | "error" | "end";
  streamId: string;
  value?: { type?: string; clientId?: string; event?: string; eventId?: string; request?: Record<string, unknown> };
  error?: { code: string; message: string };
}

/** The smallest real `/api/remote.mux` client: the browser's own socket,
 * cookie-admitted (the upgrade passes the same `admit()` as `/api`, NEW
 * packages/api/gateway/src/index.ts:251-260). Node 22's built-in WebSocket
 * (undici) accepts a `headers` init, which is how the cookie rides the
 * upgrade; no new dependency. Frames are kept, never consumed, so a waiter can
 * look for one that already arrived. */
async function openMux(base: string, cookie: string) {
  const Socket = WebSocket as unknown as new (url: string, init: { headers: Record<string, string> }) => WebSocket;
  const ws = new Socket(`${base.replace(/^http/, "ws")}/api/remote.mux`, { headers: { cookie } });
  const frames: MuxFrame[] = [];
  ws.addEventListener("message", (event) => { frames.push(JSON.parse(String(event.data)) as MuxFrame); });
  await new Promise<void>((resolve, reject) => {
    ws.addEventListener("open", () => resolve(), { once: true });
    ws.addEventListener("error", () => reject(new Error("the mux socket did not open (cookie refused, or appReady not committed)")), { once: true });
  });
  const waitFor = async (what: string, match: (frame: MuxFrame) => boolean, ms = 10_000): Promise<MuxFrame> => {
    const until = Date.now() + ms;
    for (;;) {
      const hit = frames.find(match);
      if (hit !== undefined) return hit;
      const failed = frames.find((frame) => frame.type === "error");
      if (failed !== undefined) throw new Error(`mux stream ${failed.streamId} failed: ${failed.error?.code}: ${failed.error?.message}`);
      if (Date.now() >= until) throw new Error(`timed out waiting for ${what}; frames so far: ${JSON.stringify(frames)}`);
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
  };
  /** Open one `$events` generation and return its `clientId` from the
   * mandatory first `ready` item (stream-protocol.ts:34-39; the gateway
   * requires exactly the empty args object, `REMOTE_EVENT_STREAM_PAYLOAD`). */
  const openEvents = async (streamId: string): Promise<string> => {
    ws.send(JSON.stringify({ type: "open", streamId, endpoint: "$events", payload: { args: {} } }));
    const ready = await waitFor(`${streamId} ready`, (f) => f.streamId === streamId && f.type === "item" && f.value?.type === "ready");
    assert.ok(typeof ready.value?.clientId === "string" && ready.value.clientId.length > 0, "ready carries a clientId");
    return ready.value.clientId;
  };
  return { ws, frames, waitFor, openEvents };
}

test("Gate 2 positive path: an approved PAPER order dispatches; a rejected one does not", {
  skip: gated && "set FACE_SMOKE=1",
}, async () => {
  /* 1. Scratch home. This smoke owns a scratch profile and must not start the
   * operator's data server, so the AKShare row is disabled in the patch. */
  const home = mkdtempSync(join(tmpdir(), "face-ordergate-positive-"));
  setupFaceProfile(home);
  const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
  const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
  writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: await makeBotsRoot() });
  const cleanups: (() => void)[] = [];
  try {
    const tools = ctx.get("tools") as {
      register(definition: unknown): () => void;
      execute(exec: {
        callId: string; name: string; arguments: unknown; agent: object; signal: AbortSignal;
      }): Promise<{ isError: boolean; content?: { type?: string; text?: string }[] }>;
    };

    /* 2. The stand-in order tool. Its body is the evidence: it only records. */
    const NAME = "mcp__drill__place_order";
    const ran: unknown[] = [];
    cleanups.push(tools.register({
      name: NAME,
      description: `place a PAPER order - drill stand-in, nothing behind it ${OPERATOR_GATED_MARKER}`,
      parameters: {
        type: "object",
        properties: { symbol: { type: "string" }, qty: { type: "number" }, side: { type: "string" } },
      },
      output: { schema: { type: "object" }, render: () => [{ type: "text", text: "drill order recorded" }] },
      execute: async (args: unknown) => {
        ran.push(args);
        return { recorded: true };
      },
    }));

    /* 3. The outermost answerer. `answer` is read per request so one listener
     * serves both halves of the drill. */
    let answer: Answer = "allowed-once";
    const seen: SeenRequest[] = [];
    const on = ctx.on as unknown as (
      name: "approval/request",
      listener: (req: SeenRequest, next: () => Promise<string>) => Promise<string>,
      options: { prepend: boolean },
    ) => () => void;
    const offAnswerer = on.call(ctx, "approval/request", (req) => {
      seen.push({ toolName: req.toolName, callId: req.callId, reason: req.reason, displayReason: req.displayReason });
      return Promise.resolve(answer);
    }, { prepend: true });
    cleanups.push(offAnswerer);

    /* 4. A real session over the NEW wire (Appendix A: `session/create`
     * `{request:{cwd}}` -> `{sessionId}`), then its live agent. */
    const base = `http://127.0.0.1:${ctx.webServer.port}`;
    mountClient(ctx);
    const cookie = await signIn(ctx, base);
    const created = await remote<{ sessionId: string }>(base, cookie, "session/create", { request: { cwd: home } });
    const agents = ctx.get("agents") as {
      get(id: string): { session: { append(type: string, data: object): unknown; snapshotEvents(): readonly EventLike[] } } | undefined;
    };
    const agent = agents.get(created.sessionId);
    assert.ok(agent, `session/create must leave a live agent for ${created.sessionId}`);
    /* `request()` needs an open turn (user-approval/src/index.ts:84-92); a
     * created-but-undriven session has none. Upstream's model does the same
     * append on a detached Session (tools.spec.ts:800-803). */
    agent.session.append("turn/start", { turn: 1 });

    const order = { symbol: "AAPL", qty: 1, side: "buy" };

    /* 5. APPROVED: the body must run - the assertion 0.2.0 silently broke. */
    const approved = await tools.execute({
      callId: "drill-approved", name: NAME, arguments: order, agent, signal: new AbortController().signal,
    });
    assert.equal(approved.isError, false,
      `an allowed-once order must dispatch; the tool said ${JSON.stringify(approved.content)}`);
    assert.deepEqual(ran, [order], "the stand-in body ran exactly once, with the approved arguments");
    assert.equal(seen.length, 1, "exactly one card was raised");
    /* The card the human decided on named the order, in both fields a client
     * may draw (orders.ts orderApprovalDecision). */
    assert.equal(seen[0]?.toolName, NAME);
    assert.equal(seen[0]?.callId, "drill-approved");
    assert.match(String(seen[0]?.reason), /PAPER order - .*symbol=AAPL/);
    assert.equal(seen[0]?.displayReason?.en, seen[0]?.reason);
    /* And the grant the guard trusted is IN the log, paired by id. */
    const log = agent.session.snapshotEvents();
    const asked = log.find((e) => e.type === "approval/asked" && e.data?.callId === "drill-approved");
    assert.ok(asked, "approval/asked for this call is logged");
    assert.equal(asked.data?.toolName, NAME);
    assert.ok(log.some((e) => e.type === "approval/decided" && e.data?.id === asked.data?.id && e.data?.outcome === "allowed-once"),
      "approval/decided allowed-once is logged against the same id");

    /* 6. REJECTED: the body must not run, and the model hears the human's
     * refusal in upstream's own words. */
    answer = "rejected";
    const rejected = await tools.execute({
      callId: "drill-rejected", name: NAME, arguments: order, agent, signal: new AbortController().signal,
    });
    assert.equal(rejected.isError, true, "a rejected order must not dispatch");
    assert.deepEqual(ran, [order], "the body did not run a second time");
    assert.match(rejected.content?.[0]?.text ?? "", /the user rejected tool "mcp__drill__place_order"/);
    assert.equal(seen.length, 2);

    /* 7. THE REAL CHANNEL. Remove the stand-in so the only answerer left is
     * the `api-remotes` forwarder, then answer as the browser does. */
    offAnswerer();
    const mux = await openMux(base, cookie);
    cleanups.push(() => mux.ws.close());
    const answering = await mux.openEvents("events-a");
    const watching = await mux.openEvents("events-b");
    assert.notEqual(answering, watching, "each $events stream is its own client generation");
    const viaChannel = tools.execute({
      callId: "drill-channel", name: NAME, arguments: order, agent, signal: new AbortController().signal,
    });
    /* The waterfall item reaches EVERY connected client (gateway index.ts:599-602, 608-612). */
    const isCard = (streamId: string) => (frame: MuxFrame) => frame.streamId === streamId && frame.type === "item"
      && frame.value?.type === "waterfall" && frame.value.event === "approval/request"
      && frame.value.request?.callId === "drill-channel";
    const card = await mux.waitFor("the approval card on events-a", isCard("events-a"));
    await mux.waitFor("the same card on events-b", isCard("events-b"));
    const eventId = card.value?.eventId;
    assert.ok(typeof eventId === "string" && eventId.length > 0, "the card is keyed by eventId");
    const request = card.value?.request ?? {};
    assert.equal(request.toolName, NAME);
    assert.match(String(request.reason), /PAPER order - .*symbol=AAPL/, "the card a human sees names the order");
    assert.deepEqual(request.displayReason, { en: request.reason });
    /* The projection strips the Host-only fields (stream-protocol.ts:146-173). */
    assert.equal("agent" in request || "signal" in request, false);
    assert.equal(ran.length, 1, "nothing dispatches while the card is pending");
    const answered = await remoteResult(base, cookie, "$events/result", {
      clientId: answering, eventId, outcome: { kind: "result", value: "allowed-once" },
    });
    assert.equal(answered.ok, true, `$events/result: ${JSON.stringify(answered)}`);
    const channelResult = await viaChannel;
    assert.equal(channelResult.isError, false,
      `an order approved over the real channel must dispatch; the tool said ${JSON.stringify(channelResult.content)}`);
    assert.deepEqual(ran, [order, order], "the body ran for the channel-approved call");
    /* The other client's copy is withdrawn (gateway index.ts:646-668). */
    await mux.waitFor("cancel on events-b", (frame) => frame.streamId === "events-b" && frame.type === "item"
      && frame.value?.type === "cancel" && frame.value.eventId === eventId);
    assert.ok(agent.session.snapshotEvents().some((e) => e.type === "approval/decided" && e.data?.outcome === "allowed-once"
      && agent.session.snapshotEvents().some((a) => a.type === "approval/asked" && a.data?.id === e.data?.id && a.data?.callId === "drill-channel")),
      "the channel decision is logged against this call");

    /* Close the turn we opened, so disposal persists a well-formed log. */
    agent.session.append("turn/end", { turn: 1, reason: { kind: "completed" } });
  } finally {
    for (const off of cleanups.reverse()) {
      try { off(); } catch { /* disposal below tears the tree down regardless */ }
    }
    await dispose();
  }
});
