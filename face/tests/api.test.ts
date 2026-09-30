/** The client's wire, tested against a stubbed `fetch` and a fake WebSocket —
 * no server, no browser. What is pinned here is the SHAPE the 0.2.0-rc.2 host
 * parses and the LIFECYCLE the page depends on:
 *   - a unary call is a client-request whose method repeats the path and whose
 *     payload is exactly `{args}` (rpc-host.ts:229-268; gateway/src/index.ts:1127-1147);
 *   - the mux opens `$events` first, binds answers to the clientId its `ready`
 *     carried, and hands every non-gate waterfall straight back with `next`;
 *   - every (re)connect re-opens every registered stream under a FRESH id
 *     (a duplicate `open` closes the host's socket: stream-server.ts:201-204);
 *   - a closed mux never opens a second socket.
 * Getting any of these subtly wrong fails at runtime as a 4xx, a socket the host
 * closes, or an approval that silently never lands — exactly the class of bug a
 * browser-only file would hide until the live drill.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { call, openMux, randomUuid } from "../client/api.js";

interface Sent {
  url: string;
  method: string | undefined;
  contentType: string | undefined;
  body: any;
}

const ok = (sent: Sent, value?: unknown) => Response.json({
  type: "server-response", rpcId: sent.body.rpcId, result: value === undefined ? { ok: true } : { ok: true, value },
});

/** Run `fn` with `fetch` replaced by `reply`, recording what was sent. */
async function withStubbedFetch(
  reply: (sent: Sent) => Response | Promise<Response>,
  fn: (sent: Sent[]) => Promise<void>,
): Promise<void> {
  const real = globalThis.fetch;
  const seen: Sent[] = [];
  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    const headers = (init?.headers ?? {}) as Record<string, string>;
    const sent: Sent = {
      url: String(input),
      method: init?.method,
      contentType: headers["content-type"],
      body: JSON.parse(String(init?.body)),
    };
    seen.push(sent);
    return reply(sent);
  }) as typeof fetch;
  try {
    await fn(seen);
  } finally {
    globalThis.fetch = real;
  }
}

/* ---------- call ---------- */

test("call posts a client-request to the endpoint's own path and unwraps result.value", async () => {
  await withStubbedFetch(
    (sent) => ok(sent, { items: [] }),
    async (seen) => {
      const value = await call("session/list", { _request: {} });
      assert.deepEqual(value, { items: [] });
      assert.equal(seen.length, 1);
      assert.equal(seen[0]?.url, "/api/session/list");
      assert.equal(seen[0]?.method, "POST");
      // Not habit: any other media type is refused with 415 to force a preflight.
      assert.equal(seen[0]?.contentType, "application/json");
      assert.deepEqual(Object.keys(seen[0]?.body).sort(), ["method", "payload", "rpcId", "type"]);
      assert.equal(seen[0]?.body.type, "client-request");
      // The envelope's method must equal the path endpoint or the host answers gateway/bad-request.
      assert.equal(seen[0]?.body.method, "session/list");
      // Exactly one own key, `args`, holding the wire parameters by name.
      assert.deepEqual(seen[0]?.body.payload, { args: { _request: {} } });
      assert.equal(typeof seen[0]?.body.rpcId, "string");
    },
  );
});

test("call with no args still sends the args object, and a void method resolves to undefined", async () => {
  await withStubbedFetch(
    // A void method's success result has no `value` key at all (gateway/src/index.ts:1004-1014).
    (sent) => ok(sent),
    async (seen) => {
      assert.equal(await call("session/modelCatalog"), undefined);
      assert.deepEqual(seen[0]?.body.payload, { args: {} });
    },
  );
});

test("call mints a fresh rpcId per call", async () => {
  await withStubbedFetch(
    (sent) => ok(sent),
    async (seen) => {
      await call("session/list", { _request: {} });
      await call("session/list", { _request: {} });
      assert.notEqual(seen[0]?.body.rpcId, seen[1]?.body.rpcId);
    },
  );
});

test("call surfaces a business failure with the host's own code, message and details", async () => {
  await withStubbedFetch(
    (sent) => Response.json({
      type: "server-response",
      rpcId: sent.body.rpcId,
      // RpcError is an object, not a string (rpc-schema.ts:10-14), and codes are namespaced.
      result: { ok: false, error: { code: "session/not-found", message: "session \"s9\" not found", details: { sessionId: "s9" } } },
    }),
    async () => {
      await assert.rejects(
        () => call("session/cancel", { request: { sessionId: "s9" } }),
        (err: Error & { code?: string; details?: unknown }) => {
          assert.match(err.message, /^session\/cancel: session\/not-found - session "s9" not found$/);
          assert.equal(err.code, "session/not-found");
          assert.deepEqual(err.details, { sessionId: "s9" });
          return true;
        },
      );
    },
  );
});

test("a 401 says to open the printed URL: the cookie is minted only by the tokenized visit", async () => {
  await withStubbedFetch(
    () => new Response("unauthorized", { status: 401 }),
    async () => {
      await assert.rejects(
        () => call("session/list", { _request: {} }),
        (err: Error & { status?: number }) => {
          assert.match(err.message, /not signed in - open the URL kairos-face printed/);
          assert.match(err.message, /\?token=/);
          assert.equal(err.status, 401);
          return true;
        },
      );
    },
  );
});

test("call surfaces any other carrier failure with its status, and explains a fence refusal", async () => {
  for (const [status, body] of [[404, "not found"], [415, "content type must be application/json"], [500, "handler failure: boom"]] as const) {
    await withStubbedFetch(
      () => new Response(body, { status }),
      async () => {
        await assert.rejects(() => call("session/nope", {}), (err: Error & { status?: number }) => {
          assert.match(err.message, new RegExp(`HTTP ${status} ${body}`));
          assert.equal(err.status, status);
          return true;
        });
      },
    );
  }
  await withStubbedFetch(
    () => new Response("forbidden", { status: 403 }),
    async () => {
      await assert.rejects(() => call("session/list", { _request: {} }), /HTTP 403 forbidden \(the host's Host\/Origin fence refused this page/);
    },
  );
});

test("a 0.1.1 dotted method, or any non-endpoint, never leaves the page", async () => {
  await withStubbedFetch(
    (sent) => ok(sent),
    async (seen) => {
      for (const endpoint of ["session.list", "host.describe", "session", "a/b/c", "session/../list", "./list", ""]) {
        await assert.rejects(() => call(endpoint), /is not a <namespace>\/<method> endpoint/, endpoint);
      }
      await assert.rejects(() => call("session/list", [] as unknown as Record<string, unknown>), /args must be a plain object/);
      assert.equal(seen.length, 0, "nothing reached the host");
    },
  );
});

test("call refuses a response that is not the server-response to its own rpcId", async () => {
  for (const reply of [
    (sent: Sent) => Response.json({ type: "server-response", rpcId: `${sent.body.rpcId}-other`, result: { ok: true, value: 1 } }),
    () => Response.json({ type: "client-request", rpcId: "x", result: { ok: true } }),
    () => new Response("<html>proxy</html>", { status: 200, headers: { "content-type": "text/html" } }),
  ]) {
    await withStubbedFetch(reply, async () => {
      await assert.rejects(() => call("session/list", { _request: {} }), /bad-response/);
    });
  }
});

test("a byte-bearing multipart result is rebuilt, each null placeholder filled from its part", async () => {
  await withStubbedFetch(
    (sent) => {
      // The host's own encoding (rpc-host.ts:302-311).
      const form = new FormData();
      form.set("bytes-0", new Blob([new Uint8Array([7, 8, 9])]));
      form.set("metadata", JSON.stringify({
        type: "server-response", rpcId: sent.body.rpcId,
        result: { ok: true, value: { name: "a.bin", data: null } },
        attachments: [{ path: ["data"], codec: "bytes", part: "bytes-0" }],
      }));
      return new Response(form);
    },
    async () => {
      const value = await call("files/read", { path: "a.bin" });
      assert.equal(value.name, "a.bin");
      assert.ok(value.data instanceof Uint8Array);
      assert.deepEqual([...value.data], [7, 8, 9]);
    },
  );
});

test("randomUuid mints v4 UUIDs without crypto.randomUUID, which insecure contexts lack", () => {
  const v4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
  const webCrypto = globalThis.crypto;
  // Shadow the secure-context method with an own property: a page on a LAN name over plain HTTP has none.
  Object.defineProperty(webCrypto, "randomUUID", { value: undefined, configurable: true, writable: true });
  try {
    const ids = Array.from({ length: 64 }, () => randomUuid());
    for (const id of ids) assert.match(id, v4);
    assert.equal(new Set(ids).size, ids.length, "a requestId is deduped by the host: never repeat one");
  } finally {
    Reflect.deleteProperty(webCrypto, "randomUUID"); // the prototype's method shows through again
  }
  assert.equal(typeof globalThis.crypto.randomUUID, "function", "the shadow is gone again");
});

/* ---------- the mux ---------- */

/** A WebSocket that connects to nothing: it records every construction and every frame sent. */
class FakeSocket {
  static built: FakeSocket[] = [];
  readyState = 0;
  sent: Record<string, any>[] = [];
  closedWith: { code?: number; reason?: string } | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.built.push(this);
  }
  send(text: string): void {
    if (this.readyState !== 1) throw new Error("InvalidStateError: the socket is not open");
    this.sent.push(JSON.parse(text));
  }
  close(code?: number, reason?: string): void {
    if (this.readyState === 3) return;
    this.closedWith = { code, reason };
    this.readyState = 3;
    // A browser fires `close` later, on its own task.
    setTimeout(() => this.onclose?.(), 0);
  }
  /** The host accepted the upgrade. */
  open(): void {
    this.readyState = 1;
    this.onopen?.();
  }
  /** One host frame, JSON-encoded unless it is already a string. */
  deliver(frame: unknown): void {
    this.onmessage?.({ data: typeof frame === "string" ? frame : JSON.stringify(frame) });
  }
  /** The connection died under us. */
  drop(): void {
    this.readyState = 3;
    this.onclose?.();
  }
  /** The `open` frames this socket carried, in order. */
  opens(): Record<string, any>[] {
    return this.sent.filter((frame) => frame.type === "open");
  }
  /** The streamId this socket opened `endpoint` under. */
  idOf(endpoint: string): string {
    const open = this.opens().find((frame) => frame.endpoint === endpoint);
    assert.ok(open, `${endpoint} was not opened on this socket`);
    return open.streamId as string;
  }
  /** Deliver one `$events` item. */
  event(value: unknown): void {
    this.deliver({ type: "item", streamId: this.idOf("$events"), value });
  }
  /** Open, then send the `ready` that binds `clientId`. */
  ready(clientId: string): void {
    this.open();
    this.event({ type: "ready", clientId, host: { home: "/Users/pan" } });
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

type MuxOptions = NonNullable<Parameters<typeof openMux>[0]>;
type Mux = ReturnType<typeof openMux>;

/**
 * Run `fn` against a mux over FakeSocket, with `location`, `fetch` and the
 * console faked (the mux is loud on every lost generation; tests read what it
 * said instead of printing it). Everything is restored afterwards.
 */
async function withMux(
  options: MuxOptions,
  fn: (h: { mux: Mux; socket: (i?: number) => FakeSocket; posts: Sent[]; logs: string[] }) => Promise<void>,
  reply: (sent: Sent) => Response | Promise<Response> = (sent) => ok(sent),
): Promise<void> {
  const scope = globalThis as Record<string, unknown>;
  const realSocket = scope.WebSocket;
  const realLocation = scope.location;
  const realWarn = console.warn;
  const realError = console.error;
  const logs: string[] = [];
  FakeSocket.built = [];
  scope.WebSocket = FakeSocket;
  scope.location = { protocol: "http:", host: "127.0.0.1:3090" };
  console.warn = (...args: unknown[]) => { logs.push(args.map(String).join(" ")); };
  console.error = (...args: unknown[]) => { logs.push(args.map(String).join(" ")); };
  let mux: Mux | undefined;
  try {
    await withStubbedFetch(reply, async (posts) => {
      mux = openMux(options);
      const socket = (i = FakeSocket.built.length - 1) => {
        const built = FakeSocket.built[i];
        assert.ok(built, `no socket #${i}`);
        return built;
      };
      await fn({ mux, socket, posts, logs });
    });
  } finally {
    mux?.close();
    scope.WebSocket = realSocket;
    scope.location = realLocation;
    console.warn = realWarn;
    console.error = realError;
  }
}

test("openMux dials the remote mux with the page's own scheme and host", async () => {
  await withMux({}, async ({ socket }) => {
    assert.equal(FakeSocket.built.length, 1);
    assert.equal(socket().url, "ws://127.0.0.1:3090/api/remote.mux");
  });
  const scope = globalThis as Record<string, unknown>;
  const realSocket = scope.WebSocket;
  const realLocation = scope.location;
  FakeSocket.built = [];
  scope.WebSocket = FakeSocket;
  scope.location = { protocol: "https:", host: "face.example:443" };
  try {
    openMux({}).close();
    assert.equal(FakeSocket.built[0]?.url, "wss://face.example:443/api/remote.mux");
  } finally {
    scope.WebSocket = realSocket;
    scope.location = realLocation;
  }
});

test("on open the first frame opens $events with exactly {args:{}}, in exactly the host's four keys", async () => {
  await withMux({}, async ({ socket }) => {
    assert.equal(socket().sent.length, 0, "nothing is sent before the socket opens");
    socket().open();
    const first = socket().sent[0];
    assert.deepEqual(Object.keys(first ?? {}).sort(), ["endpoint", "payload", "streamId", "type"]);
    assert.equal(first?.type, "open");
    assert.equal(first?.endpoint, "$events");
    // Anything but an empty args object is gateway/arguments-invalid (gateway/src/index.ts:477-494).
    assert.deepEqual(first?.payload, { args: {} });
    assert.equal(typeof first?.streamId, "string");
  });
});

test("ready binds the clientId: onReady gets the host facts and answer posts $events/result under it", async () => {
  const hosts: unknown[] = [];
  const gates: unknown[] = [];
  await withMux({ onReady: (host) => hosts.push(host), onGate: (frame) => gates.push(frame) }, async ({ mux, socket, posts }) => {
    socket().ready("client-1");
    assert.deepEqual(hosts, [{ home: "/Users/pan" }]);
    const gate = { type: "waterfall", event: "approval/request", eventId: "ev-1", agentId: "s1",
      request: { toolName: "mcp__alpaca-kit__place_order", callId: "c2", reason: "PAPER order - buy 1 AAPL" } };
    socket().event(gate);
    assert.deepEqual(gates, [gate], "the gate reaches the page exactly as the host sent it");
    assert.equal(posts.length, 0, "a gate the page handles is never answered for it");

    await mux.answer("ev-1", "allowed-once");
    assert.equal(posts.length, 1);
    assert.equal(posts[0]?.url, "/api/$events/result");
    assert.equal(posts[0]?.body.method, "$events/result");
    // Exactly clientId, eventId, outcome (stream-protocol.ts:102-138); the value is the bare outcome.
    assert.deepEqual(posts[0]?.body.payload, {
      args: { clientId: "client-1", eventId: "ev-1", outcome: { kind: "result", value: "allowed-once" } },
    });
    await assert.rejects(() => mux.answer("ev-1", "allowed-once"), { code: "not-pending" }, "answered once, never twice");
  });
});

test("a question is answered with the answers batch itself, no session or wrapper around it", async () => {
  await withMux({ onGate: () => {} }, async ({ mux, socket, posts }) => {
    socket().ready("client-q");
    socket().event({ type: "waterfall", event: "user-questions/request", eventId: "ev-2", agentId: "s1",
      request: { questions: [{ id: "q1", question: "Pin the paper account?" }] } });
    const answers = { answers: [{ id: "q1", selected: ["Yes, pin it"] }] };
    await mux.answer("ev-2", answers);
    assert.deepEqual(posts[0]?.body.payload.args.outcome, { kind: "result", value: answers });
  });
});

test("answer refuses before sending anything: not ready, not held, or outside the gate's vocabulary", async () => {
  await withMux({ onGate: () => {} }, async ({ mux, socket, posts }) => {
    await assert.rejects(() => mux.answer("ev-1", "allowed-once"), { code: "not-ready" });
    socket().open();
    await assert.rejects(() => mux.answer("ev-1", "allowed-once"), { code: "not-ready" }, "open is not ready: no clientId yet");
    socket().event({ type: "ready", clientId: "client-2", host: { home: "/Users/pan" } });
    // The host would take an answer to a gate it never delivered here as a silent `ok` (gateway/src/index.ts:618-621).
    await assert.rejects(() => mux.answer("ev-unknown", "rejected"), { code: "not-pending" });
    socket().event({ type: "waterfall", event: "approval/request", eventId: "ev-3", agentId: "s1", request: { toolName: "bash" } });
    socket().event({ type: "waterfall", event: "user-questions/request", eventId: "ev-4", agentId: "s1", request: { questions: [] } });
    // `cancelled` and `unavailable` are host-side outcomes; the host itself would now honour them.
    for (const value of ["cancelled", "unavailable", "allowed", undefined, { outcome: "allowed-once" }]) {
      await assert.rejects(() => mux.answer("ev-3", value), { code: "bad-value" }, JSON.stringify(value));
    }
    for (const value of ["yes", { answer: { answers: [] } }, undefined]) {
      await assert.rejects(() => mux.answer("ev-4", value), { code: "bad-value" }, JSON.stringify(value));
    }
    assert.equal(posts.length, 0, "no refused answer reached the host");
    await mux.answer("ev-3", "rejected");
    assert.equal(posts.length, 1, "the gate stayed answerable through every refusal");
  });
});

test("a waterfall that is not an operator gate is handed straight back with next, never shown", async () => {
  const gates: unknown[] = [];
  await withMux({ onGate: (frame) => gates.push(frame) }, async ({ socket, posts }) => {
    socket().ready("client-3");
    socket().event({ type: "waterfall", event: "some-plugin/ask", eventId: "ev-9", agentId: "s1", request: {} });
    await sleep(0);
    assert.deepEqual(gates, []);
    assert.equal(posts.length, 1, "the host waits on every delivered client: this one must reply");
    assert.deepEqual(posts[0]?.body.payload, { args: { clientId: "client-3", eventId: "ev-9", outcome: { kind: "next" } } });
  });
});

test("a mux without an onGate hands every gate back, so the host fails it closed instead of hanging", async () => {
  await withMux({}, async ({ socket, posts }) => {
    socket().ready("client-4");
    socket().event({ type: "waterfall", event: "approval/request", eventId: "ev-5", agentId: "s1", request: { toolName: "bash" } });
    await sleep(0);
    assert.deepEqual(posts[0]?.body.payload.args.outcome, { kind: "next" });
  });
});

test("a withdrawn gate is reported once by eventId, and cannot be answered afterwards", async () => {
  const gone: string[] = [];
  await withMux({ onGate: () => {}, onGateGone: (eventId) => gone.push(eventId) }, async ({ mux, socket, posts }) => {
    socket().ready("client-5");
    socket().event({ type: "waterfall", event: "approval/request", eventId: "ev-6", agentId: "s1", request: { toolName: "bash" } });
    socket().event({ type: "cancel", eventId: "ev-6" });
    socket().event({ type: "cancel", eventId: "ev-never-delivered" });
    assert.deepEqual(gone, ["ev-6"], "only a gate this generation held can be withdrawn from it");
    await assert.rejects(() => mux.answer("ev-6", "allowed-once"), { code: "not-pending" });
    assert.equal(posts.length, 0);
  });
});

test("a cancel that lands while the answer is in flight means the answer lost: it rejects gate-gone", async () => {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  let harness: FakeSocket | undefined;
  await withMux({ onGate: () => {}, onGateGone: () => {} }, async ({ mux, socket }) => {
    harness = socket();
    socket().ready("client-6");
    socket().event({ type: "waterfall", event: "approval/request", eventId: "ev-7", agentId: "s1", request: { toolName: "bash" } });
    const answering = mux.answer("ev-7", "allowed-once");
    // Another tab answered first: the host settles, then withdraws the gate from
    // this tab - and takes this tab's late answer as a silent `ok`.
    socket().event({ type: "cancel", eventId: "ev-7" });
    release();
    await assert.rejects(answering, { code: "gate-gone" });
  }, async (sent) => {
    await held;
    assert.ok(harness);
    return ok(sent);
  });
});

test("a cancel that lands AFTER the answer resolved still means the answer lost: onGateGone reports it, once", async () => {
  const gone: string[] = [];
  await withMux({ onGate: () => {}, onGateGone: (eventId) => gone.push(eventId) }, async ({ mux, socket }) => {
    socket().ready("client-7");
    socket().event({ type: "waterfall", event: "approval/request", eventId: "ev-8", agentId: "s1", request: { toolName: "bash" } });
    // The HTTP response outran the WebSocket frame: the answer resolves first...
    await mux.answer("ev-8", "allowed-once");
    assert.deepEqual(gone, [], "an answer that resolved reports nothing by itself");
    // ...then the host's cancel for that gate arrives. The host removes the
    // answering client's delivery before it settles and never cancels the
    // winner (gateway/src/index.ts:618-623, 646-668), so this tab LOST and its
    // `ok` was a no-op: the page must hear it to relabel the card.
    socket().event({ type: "cancel", eventId: "ev-8" });
    assert.deepEqual(gone, ["ev-8"], "the lost race is reported by eventId");
    socket().event({ type: "cancel", eventId: "ev-8" });
    assert.deepEqual(gone, ["ev-8"], "and only once");
  });
});

test("the late-cancel memory is bounded: the oldest answered gate is forgotten first", async () => {
  const gone: string[] = [];
  await withMux({ onGate: () => {}, onGateGone: (eventId) => gone.push(eventId) }, async ({ mux, socket }) => {
    socket().ready("client-8");
    const ids = Array.from({ length: 65 }, (_, i) => `ev-bound-${i}`);
    for (const eventId of ids) {
      socket().event({ type: "waterfall", event: "approval/request", eventId, agentId: "s1", request: { toolName: "bash" } });
      await mux.answer(eventId, "rejected");
    }
    socket().event({ type: "cancel", eventId: ids[0] });
    assert.deepEqual(gone, [], "the 65th answer pushed the first out of a 64-entry memory");
    socket().event({ type: "cancel", eventId: ids[64] });
    assert.deepEqual(gone, [ids[64]], "a recent answer is still recognised");
  });
});

test("host notifications reach onEvent with their event name and argument list", async () => {
  const seen: unknown[] = [];
  await withMux({ onEvent: (event, args) => seen.push([event, args]) }, async ({ socket }) => {
    socket().ready("client-7");
    socket().event({ type: "emit", event: "api-session/status", args: ["s1", true] });
    socket().event({ type: "emit", event: "agent-preset/selected", args: ["s2", "trader"] });
    assert.deepEqual(seen, [["api-session/status", ["s1", true]], ["agent-preset/selected", ["s2", "trader"]]]);
  });
});

test("stream opens under a fresh id with the endpoint's args, delivers items in order, and ends for good", async () => {
  const items: unknown[] = [];
  let ended = 0;
  await withMux({ reconnectMs: 5 }, async ({ mux, socket }) => {
    socket().ready("client-8");
    mux.stream("session/control", {}, { onItem: (value) => items.push(value), onEnd: () => { ended++; } });
    const open = socket().opens().find((frame) => frame.endpoint === "session/control");
    assert.deepEqual(open?.payload, { args: {} });
    assert.notEqual(open?.streamId, socket().idOf("$events"));
    const id = socket().idOf("session/control");
    socket().deliver({ type: "item", streamId: id, value: { type: "baseline", value: { projections: {} } } });
    socket().deliver({ type: "item", streamId: id, value: { type: "projection", sessionId: "s1", key: "title", value: "t", seq: 3 } });
    socket().deliver({ type: "end", streamId: id });
    socket().deliver({ type: "item", streamId: id, value: "after the end" });
    assert.deepEqual(items, [
      { type: "baseline", value: { projections: {} } },
      { type: "projection", sessionId: "s1", key: "title", value: "t", seq: 3 },
    ]);
    assert.equal(ended, 1);
    socket().drop();
    await sleep(40);
    socket().open();
    assert.deepEqual(socket().opens().map((frame) => frame.endpoint), ["$events"], "an ended stream is not re-opened");
  });
});

test("a stream the host fails reports its error and is not re-opened", async () => {
  const errors: unknown[] = [];
  await withMux({ reconnectMs: 5 }, async ({ mux, socket }) => {
    socket().ready("client-9");
    mux.stream("session/follow", { request: { address: { kind: "session", sessionId: "gone" }, assistantStream: true } }, {
      onError: (error) => errors.push(error),
    });
    const error = { code: "session/not-found", message: "session \"gone\" not found", details: { sessionId: "gone" } };
    socket().deliver({ type: "error", streamId: socket().idOf("session/follow"), error });
    assert.deepEqual(errors, [error]);
    socket().drop();
    await sleep(40);
    socket().open();
    assert.deepEqual(socket().opens().map((frame) => frame.endpoint), ["$events"]);
  });
});

test("cancel sends the host a cancel, drops the stream's in-flight frames, and is idempotent", async () => {
  const items: unknown[] = [];
  await withMux({ reconnectMs: 5 }, async ({ mux, socket }) => {
    socket().ready("client-10");
    const follow = mux.stream("session/follow", { request: { address: { kind: "session", sessionId: "s1" } } }, {
      onItem: (value) => items.push(value),
    });
    const id = socket().idOf("session/follow");
    follow.cancel();
    follow.cancel();
    assert.deepEqual(socket().sent.filter((frame) => frame.type === "cancel"), [{ type: "cancel", streamId: id }]);
    socket().deliver({ type: "item", streamId: id, value: "in flight" });
    assert.deepEqual(items, []);
    socket().drop();
    await sleep(40);
    socket().open();
    assert.deepEqual(socket().opens().map((frame) => frame.endpoint), ["$events"], "a cancelled stream is not re-opened");
  });
});

test("a stream registered before the socket opens is opened on open, after $events", async () => {
  await withMux({}, async ({ mux, socket }) => {
    mux.stream("session/control", {}, {});
    assert.equal(socket().sent.length, 0);
    socket().open();
    assert.deepEqual(socket().opens().map((frame) => frame.endpoint), ["$events", "session/control"]);
  });
});

test("every reconnect re-opens every registered stream under NEW ids, re-binds the clientId, and replays gates", async () => {
  const down: string[] = [];
  const gates: string[] = [];
  const ready: number[] = [];
  await withMux({
    reconnectMs: 5,
    onDown: (reason) => down.push(reason),
    onGate: (frame) => gates.push(frame.eventId),
    onReady: () => ready.push(1),
  }, async ({ mux, socket, posts, logs }) => {
    socket(0).ready("client-A");
    mux.stream("session/control", {}, {});
    mux.stream("session/follow", { request: { address: { kind: "session", sessionId: "s1" }, assistantStream: true } }, {});
    const gate = { type: "waterfall", event: "approval/request", eventId: "ev-8", agentId: "s1", request: { toolName: "bash" } };
    socket(0).event(gate);
    const firstIds = socket(0).opens().map((frame) => frame.streamId);

    socket(0).drop();
    assert.deepEqual(down.length, 1, "the page hears the socket went down");
    assert.match(logs.join("\n"), /reconnecting in 5ms/);
    await assert.rejects(() => mux.answer("ev-8", "rejected"), { code: "not-ready" }, "the old clientId died with its socket");
    await sleep(40);
    assert.equal(FakeSocket.built.length, 2, "the mux came back on a new socket");

    socket(1).ready("client-B");
    const reopened = socket(1).opens();
    assert.deepEqual(reopened.map((frame) => frame.endpoint), ["$events", "session/control", "session/follow"]);
    assert.deepEqual(reopened[2]?.payload, { args: { request: { address: { kind: "session", sessionId: "s1" }, assistantStream: true } } });
    const secondIds = reopened.map((frame) => frame.streamId);
    for (const id of secondIds) assert.ok(!firstIds.includes(id), `stream id ${id} was reused across sockets`);
    assert.equal(new Set(secondIds).size, secondIds.length, "ids are unique on the socket too");
    assert.equal(ready.length, 2, "onReady fires once per generation");

    // The host replays the still-pending gate after `ready` with its original eventId (gateway/src/index.ts:512-516).
    socket(1).event(gate);
    assert.deepEqual(gates, ["ev-8", "ev-8"]);
    await mux.answer("ev-8", "rejected");
    assert.equal(posts.at(-1)?.body.payload.args.clientId, "client-B", "answers bind the CURRENT generation's clientId");
  });
});

test("onDown runs before the next socket exists: a stream cancelled inside it is never re-opened", async () => {
  // Load-bearing for chat.js (C2 handoff): its onDown (suspendFollows) cancels
  // every follow whose blind re-open could promote a COLD session - a follow of
  // one activates it, an irreversible write-open that publishes session.v4 +
  // session.lock (NEW packages/api/session-controller/src/history.ts:204-212) -
  // and onReady re-decides them from the fresh list. That holds only while
  // onDown fires when the generation is lost and BEFORE any stream re-opens.
  let follow: { cancel(): void } | undefined;
  let socketsAtDown = -1;
  await withMux({
    reconnectMs: 5,
    onDown: () => { socketsAtDown = FakeSocket.built.length; follow?.cancel(); },
  }, async ({ mux, socket }) => {
    socket(0).ready("client-D1");
    follow = mux.stream("session/follow", { request: { address: { kind: "session", sessionId: "cold" } } }, {});
    mux.stream("session/control", {}, {});
    socket(0).drop();
    assert.equal(socketsAtDown, 1, "onDown ran while only the lost socket existed");
    await sleep(40);
    socket(1).ready("client-D2");
    assert.deepEqual(socket(1).opens().map((frame) => frame.endpoint), ["$events", "session/control"],
      "the follow cancelled in onDown stayed closed; everything else re-opened");
  });
});

test("cancel after a reconnect names the stream's CURRENT id, and the stream stays closed through the next reconnect", async () => {
  // A handle bound to its first id would cancel an id the host no longer owns
  // (dropped: stream-server.ts:189-191) and re-open the stream forever after.
  const items: unknown[] = [];
  await withMux({ reconnectMs: 5 }, async ({ mux, socket }) => {
    socket(0).ready("client-W2a");
    const follow = mux.stream("session/follow", { request: { address: { kind: "session", sessionId: "s1" } } }, {
      onItem: (value) => items.push(value),
    });
    const firstId = socket(0).idOf("session/follow");
    socket(0).drop();
    await sleep(40);
    socket(1).ready("client-W2b");
    const secondId = socket(1).idOf("session/follow");
    assert.notEqual(secondId, firstId);

    follow.cancel();
    assert.deepEqual(socket(1).sent.filter((frame) => frame.type === "cancel"), [{ type: "cancel", streamId: secondId }]);
    socket(1).deliver({ type: "item", streamId: secondId, value: "in flight" });
    assert.deepEqual(items, []);

    socket(1).drop();
    await sleep(40);
    socket(2).open();
    assert.deepEqual(socket(2).opens().map((frame) => frame.endpoint), ["$events"], "a cancelled stream never comes back");
  });
});

test("a held gate the reconnect does not replay was settled while disconnected: it is retired, once", async () => {
  // No `cancel` reaches a page that held no delivery when the gate settled
  // (gateway/src/index.ts:640-644, 657-668); the replay after `ready` is the
  // only proof a gate is still pending (:512-516).
  const gone: string[] = [];
  await withMux({ reconnectMs: 5, replaySettleMs: 10, onGate: () => {}, onGateGone: (eventId) => gone.push(eventId) },
    async ({ mux, socket, posts }) => {
      socket(0).ready("client-R1");
      for (const eventId of ["ev-1", "ev-2"]) {
        socket(0).event({ type: "waterfall", event: "approval/request", eventId, agentId: "s1", request: { toolName: "bash" } });
      }
      socket(0).drop();
      await sleep(40);
      socket(1).ready("client-R2");
      socket(1).event({ type: "waterfall", event: "approval/request", eventId: "ev-2", agentId: "s1", request: { toolName: "bash" } });
      assert.deepEqual(gone, [], "nothing is retired before the replay has had its time");
      await sleep(40);
      assert.deepEqual(gone, ["ev-1"]);
      await assert.rejects(() => mux.answer("ev-1", "rejected"), { code: "not-pending" });
      await mux.answer("ev-2", "rejected");
      assert.equal(posts.length, 1, "the replayed gate stays answerable");
      await sleep(30);
      assert.deepEqual(gone, ["ev-1"], "retired once, never again");
    });
});

test("retirement survives a chain of reconnects, and never reports a gate this page answered", async () => {
  const gone: string[] = [];
  await withMux({ reconnectMs: 5, replaySettleMs: 30, onGate: () => {}, onGateGone: (eventId) => gone.push(eventId) },
    async ({ mux, socket }) => {
      socket(0).ready("client-C1");
      socket(0).event({ type: "waterfall", event: "approval/request", eventId: "ev-held", agentId: "s1", request: { toolName: "bash" } });
      socket(0).event({ type: "waterfall", event: "approval/request", eventId: "ev-answered", agentId: "s1", request: { toolName: "bash" } });
      await mux.answer("ev-answered", "allowed-once");
      socket(0).drop();
      await sleep(20);
      // Generation 2 dies before its retirement is due (before any replay could
      // land): its retirement must never fire, even long after it would have.
      socket(1).ready("client-C2");
      socket(1).drop();
      await sleep(60);
      assert.deepEqual(gone, [], "a dead generation retires nothing");
      socket(2).ready("client-C3");
      await sleep(60);
      assert.deepEqual(gone, ["ev-held"], "the gate generation 1 held and nobody replayed is retired by generation 3");
    });
});

test("close() inside the reconnect window is honoured: no second socket, ever", async () => {
  const events: unknown[] = [];
  await withMux({ reconnectMs: 20, onEvent: (...args) => events.push(args) }, async ({ mux, socket }) => {
    socket().drop();
    // Closing now lands between the drop and the scheduled reconnect. Two guards
    // hold it (close() clears the timer, and connect() refuses to run once
    // closed); this pins the behaviour they share, not which one fired.
    mux.close();
    await sleep(60);
    assert.equal(FakeSocket.built.length, 1, "a closed mux must not resurrect itself");
    assert.equal(events.length, 0);
  });
});

test("close() on a live socket closes it, silences it, and refuses new streams", async () => {
  const events: unknown[] = [];
  await withMux({ reconnectMs: 5, onEvent: (...args) => events.push(args) }, async ({ mux, socket }) => {
    socket().ready("client-11");
    const eventsId = socket().idOf("$events");
    mux.close();
    assert.equal(socket().closedWith?.code, 1000);
    socket().deliver({ type: "item", streamId: eventsId, value: { type: "emit", event: "api-session/status", args: ["s1", true] } });
    await sleep(30);
    assert.deepEqual(events, []);
    assert.equal(FakeSocket.built.length, 1, "no reconnect after close");
    assert.throws(() => mux.stream("session/control", {}, {}), /after close/);
    await assert.rejects(() => mux.answer("ev-1", "rejected"), { code: "not-ready" });
  });
});

test("a frame outside the Remote stream grammar loses the generation loudly instead of leaving a silent gap", async () => {
  for (const bad of ["not json", JSON.stringify({ type: "item", streamId: "x", value: 1, extra: true }),
    JSON.stringify({ type: "error", streamId: "x", error: { code: "c", message: "m" } }), JSON.stringify({ type: "item" })]) {
    const down: string[] = [];
    await withMux({ reconnectMs: 5, onDown: (reason) => down.push(reason) }, async ({ socket }) => {
      socket().open();
      socket().deliver(bad);
      assert.equal(socket(0).closedWith?.code, 4002, bad);
      assert.match(down[0] ?? "", /outside the Remote stream grammar/);
      await sleep(40);
      assert.equal(FakeSocket.built.length, 2, "a fresh generation re-delivers everything");
    });
  }
});

test("an $events stream that fails, ends, or does not begin with ready loses the generation", async () => {
  const cases: [string, (s: FakeSocket) => void, RegExp, number][] = [
    ["error", (s) => s.deliver({ type: "error", streamId: s.idOf("$events"),
      error: { code: "gateway/service-unavailable", message: "forwarded Remote event source is unavailable", details: {} } }),
    /the \$events stream failed: gateway\/service-unavailable/, 4000],
    ["end", (s) => s.deliver({ type: "end", streamId: s.idOf("$events") }), /the \$events stream ended/, 4000],
    ["no ready", (s) => s.event({ type: "emit", event: "api-session/status", args: ["s1", true] }), /did not begin with ready/, 4002],
    ["bad item", (s) => { s.event({ type: "ready", clientId: "c", host: { home: "/" } }); s.event({ type: "waterfall", event: "approval/request" }); },
      /sent an invalid item/, 4002],
  ];
  for (const [name, act, reason, code] of cases) {
    const down: string[] = [];
    await withMux({ reconnectMs: 5, onDown: (why) => down.push(why) }, async ({ socket }) => {
      socket().open();
      act(socket());
      assert.equal(socket(0).closedWith?.code, code, name);
      assert.match(down[0] ?? "", reason, name);
      await sleep(40);
      assert.equal(FakeSocket.built.length, 2, `${name}: the mux reconnects`);
    });
  }
});

test("a throwing handler stays its own bug: logged, and every other stream keeps flowing", async () => {
  const items: unknown[] = [];
  await withMux({ onReady: () => { throw new Error("renderer bug"); } }, async ({ mux, socket, logs }) => {
    socket().ready("client-12");
    mux.stream("session/control", {}, { onItem: () => { throw new Error("control handler bug"); } });
    mux.stream("session/follow", { request: { address: { kind: "session", sessionId: "s1" } } }, { onItem: (value) => items.push(value) });
    socket().deliver({ type: "item", streamId: socket().idOf("session/control"), value: 1 });
    socket().deliver({ type: "item", streamId: socket().idOf("session/follow"), value: 2 });
    assert.deepEqual(items, [2]);
    assert.equal(socket().closedWith, null, "the socket survived both throws");
    assert.match(logs.join("\n"), /onReady handler threw/);
    assert.match(logs.join("\n"), /session\/control item handler threw/);
  });
});

test("stream refuses $events, dotted names, and args that are not plain JSON objects", async () => {
  await withMux({}, async ({ mux }) => {
    assert.throws(() => mux.stream("$events", {}, {}), /not a <namespace>\/<method> stream endpoint/, "$events is the module's own");
    assert.throws(() => mux.stream("session.follow", {}, {}), /not a <namespace>\/<method> stream endpoint/);
    assert.throws(() => mux.stream("session/follow", [] as unknown as Record<string, unknown>, {}), /plain object/);
    assert.throws(() => mux.stream("session/follow", { request: { big: 1n } }, {}), TypeError);
  });
});

test("the fixture's gate lines are exactly what the mux accepts and hands the page", async () => {
  // Cross-check with tests/fixtures/events.jsonl: the frames mapper.test.ts
  // decodes must also pass api.js's own validation of the $events stream.
  const lines = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "fixtures", "events.jsonl"), "utf8")
    .trim().split("\n").map((line) => JSON.parse(line) as { type: string; eventId?: string });
  const gateLines = lines.filter((frame) => frame.type === "waterfall");
  const cancelLines = lines.filter((frame) => frame.type === "cancel");
  assert.equal(gateLines.length, 2);
  assert.equal(cancelLines.length, 2);
  const gates: unknown[] = [];
  const gone: string[] = [];
  await withMux({ onGate: (frame) => gates.push(frame), onGateGone: (eventId) => gone.push(eventId) }, async ({ socket, posts }) => {
    socket().ready("client-13");
    for (const frame of [...gateLines, ...cancelLines]) socket().event(frame);
    assert.deepEqual(gates, gateLines);
    assert.deepEqual(gone, cancelLines.map((frame) => frame.eventId));
    assert.equal(socket().closedWith, null, "no fixture frame broke the grammar");
    assert.equal(posts.length, 0);
  });
});
