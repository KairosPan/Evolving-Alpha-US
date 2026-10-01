/** The page's OWN transport against a real host: `client/api.js` and
 * `client/mapper.js`, unmodified, driving a booted face over its socket.
 *
 * Why this file exists (critique-wire-correctness G1; C1 handoff item 5). The
 * rest of the suite proves the two halves apart: `api.test.ts` and
 * `mapper.test.ts` run the client against a fake WebSocket and fixture frames,
 * and `smoke.test.ts` 7b / `order-gate-smoke.test.ts` step 7 prove the Gate-2
 * answer channel with hand-written frames. Neither would notice the browser
 * code and the host drifting apart - an `$events` answer the gateway refuses,
 * a follow record the mapper ignores, a reconnect that re-opens nothing - and
 * PLAN §7's "silent failure dominates" is exactly that shape. Here the only
 * stand-ins are the three browser globals the modules read (`location`,
 * `fetch` - relative URLs plus the cookie a browser would attach - and
 * `WebSocket`, which Node 22 provides and which takes a `headers` init), so
 * every frame the page would exchange is the real one.
 *
 * Drives, in order: the `$events` ready (`host.home` = the host's
 * `os.homedir()`, NEW packages/api/remotes/src/index.ts:42); the unary envelope
 * and business codes; the `api-session/added` emit; the `session/control`
 * baseline; a `session/follow` snapshot whose records the mapper renders
 * (raw and normalized alike); an approval raised by the real ApprovalService,
 * mapped and answered through `answer()`; the gap-free follow tail; a
 * rejection; a second tab that gets the same gate and then `cancel`, and whose
 * late answer is refused `not-pending`; a Stop that withdraws a gate; a
 * question answered with its batch; a gate replayed to a tab that connected
 * late; the non-activating `session/projections` + `session/page` reads the
 * member traces and cold sessions use; and a follow `cancel()` the host honours.
 *
 * ONE BOOT PER PROCESS (smoke.test.ts header): `bootFace` sets
 * `process.env.DSH_HOME`, so this is its own file. The scratch home is a
 * `mkdtemp` directory, never `~/.dsh`, and AKShare is disabled.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
// allowJs (tsconfig): the browser modules are imported as they ship, untranspiled.
import { call, openMux } from "../client/api.js";
import { mapFrame } from "../client/mapper.js";
import { makeBotsRoot } from "./bots-fixture.ts";
import { mountClient, signIn } from "./remote.ts";

const gated = process.env.FACE_SMOKE !== "1";

/** A mapped view, read loosely: the JSDoc `FrameView` names only the common fields. */
const viewOf = (frame: unknown): Record<string, unknown> => mapFrame(frame) as unknown as Record<string, unknown>;

/** Poll until `check` returns something truthy; fail naming `what` after `ms`. */
async function waitFor<T>(what: string, check: () => T | undefined | false, ms = 5_000): Promise<T> {
  const until = Date.now() + ms;
  for (;;) {
    const value = check();
    if (value) return value;
    if (Date.now() > until) throw new Error(`timed out waiting for ${what}`);
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

/** One browser tab's mux, with every callback recorded. */
interface Tab {
  mux: ReturnType<typeof openMux>;
  ready: { home: string }[];
  events: [string, unknown[]][];
  gates: { event: string; eventId: string; agentId: string; request: Record<string, unknown> }[];
  gone: string[];
  down: string[];
}

function openTab(): Tab {
  const tab: Omit<Tab, "mux"> = { ready: [], events: [], gates: [], gone: [], down: [] };
  const mux = openMux({
    onReady: (host) => { tab.ready.push(host); },
    onEvent: (event, args) => { tab.events.push([event, args]); },
    onGate: (frame) => { tab.gates.push(frame); },
    onGateGone: (eventId) => { tab.gone.push(eventId); },
    onDown: (reason) => { tab.down.push(reason); },
  });
  return { ...tab, mux };
}

test("client mux smoke: the page's own api.js + mapper.js against a real host - envelope, events, follow, Gate-2 answers, tabs, Stop, question, replay, non-activating reads", {
  skip: gated && "set FACE_SMOKE=1", timeout: 90_000,
}, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-client-mux-"));
  setupFaceProfile(home);
  const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
  const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
  // This smoke owns a scratch profile and must not start the operator's data server.
  writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: await makeBotsRoot() });

  const scope = globalThis as Record<string, unknown>;
  const realFetch = globalThis.fetch;
  const realSocket = globalThis.WebSocket;
  const realLocation = scope.location;
  const tabs: Tab[] = [];
  try {
    mountClient(ctx);
    const port = ctx.webServer.port;
    const base = `http://127.0.0.1:${port}`;
    const cookie = await signIn(ctx, base);

    /* The browser, as far as the two modules can tell: same-origin relative
     * `fetch` with the cookie attached, and a WebSocket that sends it too. */
    scope.location = { protocol: "http:", host: `127.0.0.1:${port}` };
    globalThis.fetch = ((input: string | URL | Request, init: RequestInit = {}) =>
      realFetch(new URL(String(input), base), {
        ...init,
        headers: { ...(init.headers as Record<string, string> | undefined), cookie },
      })) as typeof fetch;
    globalThis.WebSocket = class extends realSocket {
      constructor(url: string | URL) {
        // undici's non-standard WebSocketInit; the DOM typing knows only `protocols`.
        super(url, { headers: { cookie } } as unknown as string[]);
      }
    } as typeof WebSocket;

    const agents = ctx.get("agents") as { get(id: string): { session: { append(type: string, data: object): unknown } } | undefined };
    const approval = ctx.get("approval") as {
      request(req: { agent: object; toolName: string; callId: string; reason: string; signal?: AbortSignal }): Promise<string>;
    };
    const questions = ctx.get("userQuestions") as { ask(req: { agent: object; questions: object[] }): Promise<unknown> };

    const A = openTab();
    tabs.push(A);

    /* 1. `$events` opens with `ready` first, carrying the host's home. */
    await waitFor("tab A ready", () => A.ready.length > 0);
    assert.deepEqual(A.ready[0], { home: homedir() });

    /* 2. The unary envelope round-trips; business failures keep the host's
     * slash-namespaced code (`session/cancel` is live-only, commands.ts:511-524;
     * an unknown top-level key is `gateway/arguments-invalid`). */
    const list = await call("session/list", { _request: {} }) as { items: unknown[] };
    assert.ok(Array.isArray(list.items));
    await assert.rejects(() => call("session/cancel", { request: { sessionId: "no-such" } }), { code: "session/not-found" });
    await assert.rejects(() => call("session/list", { _request: {}, extra: 1 }), { code: "gateway/arguments-invalid" });

    /* 3. session/create, and the `api-session/added` emit that tells every tab. */
    const created = await call("session/create", { request: { cwd: home } }) as { sessionId: string };
    const sessionId = created.sessionId;
    assert.equal(typeof sessionId, "string");
    await waitFor("api-session/added", () =>
      A.events.find(([event, args]) => event === "api-session/added" && (args[0] as { sessionId?: unknown } | undefined)?.sessionId === sessionId));

    /* 4. session/control opens with its baseline. */
    const control: Record<string, unknown>[] = [];
    A.mux.stream("session/control", {}, { onItem: (value: unknown) => { control.push(value as Record<string, unknown>); } });
    const baseline = await waitFor("control baseline", () => control[0]);
    assert.equal(baseline.type, "baseline");
    assert.ok((baseline.value as { projections?: unknown }).projections !== undefined);

    /* 5. session/follow opens with a snapshot; every record maps the same raw
     * (`{type:'event'}`) as normalized (`session/event`) - the member-trace
     * mapping critique WC-F2 is about. */
    const follow: Record<string, any>[] = [];
    A.mux.stream("session/follow", { request: { address: { kind: "session", sessionId }, assistantStream: true } }, {
      onItem: (value: unknown) => { follow.push(value as Record<string, any>); },
      onError: (error: unknown) => { follow.push({ type: "ERROR", error }); },
    });
    const snapshot = await waitFor("follow snapshot", () => follow[0]);
    assert.equal(snapshot.type, "snapshot", JSON.stringify(snapshot).slice(0, 200));
    assert.equal(snapshot.header.id, sessionId);
    assert.ok(snapshot.assistantStream !== undefined, "the assistant-stream baseline rides a follow that opted in");
    for (const record of snapshot.records as { type: string; event: object }[]) {
      assert.equal(record.type, "event");
      assert.deepEqual(viewOf({ ...record, sessionId }), viewOf({ type: "session/event", sessionId, event: record.event }));
    }

    const agent = agents.get(sessionId);
    assert.ok(agent !== undefined, "session/create leaves a live root agent");
    // An approval needs an open turn (NEW packages/interaction/user-approval/src/index.ts:84-92).
    agent.session.append("turn/start", { turn: 1 });

    /* 6. An approval raised by the real ApprovalService reaches onGate as the
     * waterfall, maps to the card view, and `answer()` settles it. */
    const order = approval.request({ agent, toolName: "mcp__drill__place_order", callId: "c-mux-1", reason: "PAPER order - buy 1 AAPL" });
    const orderFrame = await waitFor("the order gate", () => A.gates.find((gate) => gate.request.callId === "c-mux-1"));
    const orderView = viewOf(orderFrame);
    assert.equal(orderView.kind, "approval");
    assert.equal(orderView.id, orderFrame.eventId, "a gate is keyed by its eventId");
    assert.equal(orderView.sessionId, sessionId, "a gate names its session through agentId");
    assert.equal(orderView.toolName, "mcp__drill__place_order");
    assert.equal(orderView.reason, "PAPER order - buy 1 AAPL");
    await A.mux.answer(orderFrame.eventId, "allowed-once");
    assert.equal(await order, "allowed-once");

    /* 7. The audit pair reaches the follow as a gap-free tail (history.ts:
     * 213-233); the mapper renders the turn and keeps the audit events out. */
    await waitFor("approval/decided on the follow", () => follow.find((item) => item.type === "event" && item.event.type === "approval/decided"));
    const live = follow.filter((item) => item.type === "event");
    for (const item of live) {
      const view = viewOf({ type: "session/event", sessionId, event: item.event });
      if (item.event.type === "turn/start") assert.equal(view.kind, "turn");
      if (String(item.event.type).startsWith("approval/")) assert.equal(view.kind, "ignore");
    }
    for (let i = 1; i < live.length; i++) assert.equal(live[i]!.event.seq, live[i - 1]!.event.seq + 1, "the follow tail is gap-free");

    /* 8. A rejection denies. */
    const denied = approval.request({ agent, toolName: "bash", callId: "c-mux-2", reason: "probe" });
    const deniedFrame = await waitFor("gate 2", () => A.gates.find((gate) => gate.request.callId === "c-mux-2"));
    await A.mux.answer(deniedFrame.eventId, "rejected");
    assert.equal(await denied, "rejected");

    /* 9. A second tab gets the same gate; once tab A answers, tab B gets the
     * `cancel` (gateway/src/index.ts:646-668) and its late answer is refused
     * `not-pending` instead of reading as applied. The winner gets no cancel. */
    const B = openTab();
    tabs.push(B);
    await waitFor("tab B ready", () => B.ready.length > 0);
    const shared = approval.request({ agent, toolName: "bash", callId: "c-mux-3", reason: "two tabs" });
    const inA = await waitFor("gate 3 in A", () => A.gates.find((gate) => gate.request.callId === "c-mux-3"));
    const inB = await waitFor("gate 3 in B", () => B.gates.find((gate) => gate.request.callId === "c-mux-3"));
    assert.equal(inA.eventId, inB.eventId, "one eventId for every holder");
    await A.mux.answer(inA.eventId, "allowed-once");
    assert.equal(await shared, "allowed-once");
    await waitFor("the cancel in tab B", () => B.gone.includes(inA.eventId));
    assert.equal(A.gone.includes(inA.eventId), false, "the answering tab gets no cancel for its own answer");
    await assert.rejects(() => B.mux.answer(inB.eventId, "rejected"), { code: "not-pending" });
    B.mux.close();

    /* 10. Stop withdraws a gate: the ask resolves `cancelled`, the tab gets `cancel`. */
    const stop = new AbortController();
    const stopped = approval.request({ agent, toolName: "bash", callId: "c-mux-4", reason: "stop me", signal: stop.signal });
    const stoppedFrame = await waitFor("gate 4", () => A.gates.find((gate) => gate.request.callId === "c-mux-4"));
    stop.abort();
    assert.equal(await stopped, "cancelled");
    await waitFor("the cancel for gate 4", () => A.gone.includes(stoppedFrame.eventId));

    /* 11. A question is answered with its whole batch (tool-ask-user/src/index.ts:98-117). */
    const asking = questions.ask({ agent, questions: [{ id: "q1", question: "Pin the paper account?", options: [{ label: "Yes" }, { label: "No" }] }] });
    const questionFrame = await waitFor("the question", () => A.gates.find((gate) => gate.event === "user-questions/request"));
    const questionView = viewOf(questionFrame);
    assert.equal(questionView.kind, "question");
    assert.equal((questionView.questions as unknown[]).length, 1);
    await A.mux.answer(questionFrame.eventId, { answers: [{ id: "q1", selected: ["Yes"] }] });
    assert.deepEqual(await asking, { answers: [{ id: "q1", selected: ["Yes"] }] });

    /* 12. A gate pending before a tab connects is replayed to it right after
     * `ready` (gateway/src/index.ts:512-516), and that tab can answer it. */
    const replayed = approval.request({ agent, toolName: "bash", callId: "c-mux-5", reason: "replay" });
    await waitFor("gate 5 in A", () => A.gates.find((gate) => gate.request.callId === "c-mux-5"));
    const C = openTab();
    tabs.push(C);
    const replay = await waitFor("the replay in tab C", () => C.gates.find((gate) => gate.request.callId === "c-mux-5"));
    assert.equal(C.ready.length, 1);
    await C.mux.answer(replay.eventId, "rejected");
    assert.equal(await replayed, "rejected");
    await waitFor("the cancel in tab A", () => A.gone.includes(replay.eventId));
    C.mux.close();

    /* 13. The non-activating reads a cold session and a member trace use:
     * the projections cut, then a page through it; an unknown session is `null`. */
    const projections = await call("session/projections", { request: { sessionId } }) as { asOfSeq: number };
    assert.equal(typeof projections.asOfSeq, "number");
    const page = await call("session/page", {
      request: { address: { kind: "session", sessionId }, throughSeq: projections.asOfSeq, maxMessages: 100 },
    }) as { records: { type: string }[] };
    assert.ok(Array.isArray(page.records));
    for (const record of page.records) assert.equal(record.type, "event");
    assert.equal(await call("session/projections", { request: { sessionId: "no-such" } }), null);

    /* 14. A follow `cancel()` is honoured: the host sends it nothing more, and
     * the socket never went down on the way. */
    const extra: unknown[] = [];
    const second = A.mux.stream("session/follow", { request: { address: { kind: "session", sessionId }, maxMessages: 1 } }, {
      onItem: (value: unknown) => { extra.push(value); },
    });
    await waitFor("the second follow's snapshot", () => extra[0]);
    second.cancel();
    const before = extra.length;
    agent.session.append("turn/end", { turn: 1, reason: { kind: "completed" } });
    await waitFor("turn/end on the main follow", () => follow.find((item) => item.type === "event" && item.event.type === "turn/end"));
    assert.equal(extra.length, before, "a cancelled follow delivers nothing more");
    assert.deepEqual(A.down, [], "tab A's socket never went down");
  } finally {
    for (const tab of tabs) tab.mux.close();
    globalThis.fetch = realFetch;
    globalThis.WebSocket = realSocket;
    scope.location = realLocation;
    await dispose();
  }
});
