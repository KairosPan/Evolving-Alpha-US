/** The client's wire envelope, tested against a stubbed `fetch` — no server,
 * no browser. What is pinned here is the SHAPE the host parses: a client-request
 * for a method call, a client-response for an answer, and the two different
 * bodies that come back (a server-response vs a carrier receipt). Getting
 * either envelope subtly wrong fails at runtime as a 400 or a silently
 * unanswered approval, which is exactly the class of bug a browser-only file
 * would hide until the live drill.
 *
 * `openMux` is deliberately absent: it needs a real WebSocket server, and the
 * live drill is its test.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { rpc, respond } from "../client/api.js";

interface Sent {
  url: string;
  method: string | undefined;
  contentType: string | undefined;
  body: any;
}

/** Run `fn` with `fetch` replaced by `reply`, recording what was sent. */
async function withStubbedFetch(
  reply: (sent: Sent) => Response,
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

test("rpc posts a client-request to the method's own path and unwraps result.value", async () => {
  await withStubbedFetch(
    (sent) => Response.json({ type: "server-response", rpcId: sent.body.rpcId, result: { ok: true, value: { sessions: [] } } }),
    async (seen) => {
      const value = await rpc("session.list", { workspaceId: "w1" });
      assert.deepEqual(value, { sessions: [] });
      assert.equal(seen.length, 1);
      assert.equal(seen[0]?.url, "/api/session.list");
      assert.equal(seen[0]?.method, "POST");
      // Not habit: any other media type is refused with 415 to force a preflight.
      assert.equal(seen[0]?.contentType, "application/json");
      assert.equal(seen[0]?.body.type, "client-request");
      // The envelope's method must equal the path segment or the host rejects it.
      assert.equal(seen[0]?.body.method, "session.list");
      assert.deepEqual(seen[0]?.body.payload, { workspaceId: "w1" });
      assert.equal(typeof seen[0]?.body.rpcId, "string");
    },
  );
});

test("rpc mints a fresh id per call", async () => {
  await withStubbedFetch(
    (sent) => Response.json({ type: "server-response", rpcId: sent.body.rpcId, result: { ok: true } }),
    async (seen) => {
      await rpc("session.list");
      await rpc("session.list");
      assert.notEqual(seen[0]?.body.rpcId, seen[1]?.body.rpcId);
    },
  );
});

test("rpc surfaces a business error with the host's own code and message", async () => {
  await withStubbedFetch(
    (sent) => Response.json({
      type: "server-response",
      rpcId: sent.body.rpcId,
      // RpcError is an object, not a string.
      result: { ok: false, error: { code: "session-not-found", message: "no session s9", details: { sessionId: "s9" } } },
    }),
    async () => {
      await assert.rejects(
        () => rpc("session.history", { sessionId: "s9" }),
        /session-not-found - no session s9/,
      );
    },
  );
});

test("rpc surfaces a carrier failure with its status", async () => {
  await withStubbedFetch(
    () => new Response("not found", { status: 404 }),
    async () => {
      await assert.rejects(() => rpc("session.nope"), /HTTP 404/);
    },
  );
});

test("respond echoes the frame's rpcId as a client-response and never mints one", async () => {
  await withStubbedFetch(
    () => Response.json({ accepted: true }),
    async (seen) => {
      await respond("host-minted-77", { sessionId: "s1", approvalId: "ap-1", outcome: "allowed-once" });
      assert.equal(seen[0]?.url, "/api/respond");
      assert.equal(seen[0]?.body.type, "client-response");
      assert.equal(seen[0]?.body.rpcId, "host-minted-77");
      assert.equal(seen[0]?.body.result.ok, true);
      assert.deepEqual(seen[0]?.body.result.value, { sessionId: "s1", approvalId: "ap-1", outcome: "allowed-once" });
      // A client-response carries no method: the frame it answers named it.
      assert.equal(seen[0]?.body.method, undefined);
    },
  );
});

test("respond refuses to pass off a rejected receipt as success", async () => {
  await withStubbedFetch(
    () => Response.json({ accepted: false, reason: "not-pending" }),
    async () => {
      await assert.rejects(() => respond("stale-1", {}), /not-pending/);
    },
  );
});
