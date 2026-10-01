/** Gate 2 is armed while `boot()` is still pending: the mid-boot window of
 * REVIEW-adversarial finding 1, closed and kept closed.
 *
 * THE FINDING. The gateway claims unary `/api` the moment its row activates,
 * mid-boot, and waits for `appReady` only on the `/api/remote.mux` upgrade
 * (NEW packages/api/gateway/src/index.ts:233-239 vs 265-276); an MCP row's
 * tools are registered as that row activates. Gate 2 used to be registered in
 * `bootFace`'s body AFTER `boot()` resolved - so while any slow row kept
 * `boot()` open, a tab still holding its cookie could `session/create` and run
 * a live order tool with no ask listener and no guard. The reviewer's probe
 * showed the stand-in order's body RUN at +152 ms with no `approval/asked`,
 * while `bootFace` returned at +3080 ms.
 *
 * THE FIX (src/boot.ts divergence 10, `armOrderGate`): both halves arm inside
 * `prepare`, each as a `hostCtx.inject` fiber waiting for exactly the service
 * it reads - the guard for `tools`, the ask listener for `approval`.
 *
 * TWO CASES.
 * 1. Offline: the arming MECHANICS on a bare cordis Context with two minimal
 *    services - real cordis, so real inject/effect semantics: nothing arms
 *    before its service exists; the guard arms on `tools` alone; each half
 *    re-arms exactly once when its service is replaced, reading the new one;
 *    each leaves with its service and with the host.
 * 2. FACE_SMOKE: the real tree, held mid-boot by a slow row
 *    (tests/fixtures/midboot-slow-row.js) with an operator-gated order
 *    stand-in registered as soon as the registry exists
 *    (tests/fixtures/midboot-order-standin.js). While `bootFace` is provably
 *    still pending - unary `/api` serving, a session created over it, the
 *    order tool live - the reviewer's exact call is HELD for a card (logged
 *    `approval/asked`, body not run), an agentless call is DENIED by the
 *    listener, and a marked tool the gate cannot name is DENIED by the guard
 *    alone. Then the boot is released, and the normal path runs on the same
 *    order: the held card reaches the first tab once the streams open, and
 *    `allowed-once` from it dispatches the order exactly once. Finally the
 *    real `approval` row is restarted - the listener re-arms exactly once -
 *    and disposal leaves no gate listener behind.
 *
 * Gated behind `FACE_SMOKE=1` and in its own FILE for the reason
 * `smoke.test.ts` states: `bootFace` sets `process.env.DSH_HOME` permanently,
 * so one boot per process, and `node --test` gives each file its own. The
 * offline case boots nothing.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { Context, Service } from "@deepseek-ai/cordis";
import { setupFaceProfile } from "../src/setup.ts";
import { armOrderGate, bootFace, type BootedFace } from "../src/boot.ts";
import { OPERATOR_GATED_MARKER, type PreToolDecision } from "../src/orders.ts";
import { makeBotsRoot } from "./bots-fixture.ts";
import { mountClient, remote, remoteResult, signIn } from "./remote.ts";

const gated = process.env.FACE_SMOKE !== "1";

/** `FiberState` ordinals. The enum is a `declare const enum` with no runtime
 * object, so it cannot be imported under tsx (src/boot.ts `FIBER_ACTIVE`). */
const FIBER = { pending: 0, active: 2, disposed: 4 } as const;

/** The stand-in's name: the raw-name suffix the gate anchors on
 * (src/orders.ts ORDER_RAW_NAMES), behind a server name nothing real uses. */
const NAME = "mcp__drill__place_order";

/** The order every call in the smoke carries. */
const ORDER = { symbol: "AAPL", qty: 1, side: "buy" } as const;

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

/** A registered guard check, as `tools.guard` receives one. */
type GuardCheck = (exec: { name: string; callId?: unknown; agent?: { session: unknown } }) => string | undefined;

/** A tool registry reduced to the guard seam, honouring upstream's ownership
 * contract: a guard registration is an effect of the CALLING context (NEW
 * packages/core/tools/src/index.ts:1136-1142 -> packages/core/scope/src/
 * store.ts:226-264), so it leaves with whoever registered it. `guards` is
 * what is registered right now. */
class FakeTools extends Service {
  readonly guards = new Set<GuardCheck>();

  constructor(ctx: Context) {
    super(ctx, "tools");
  }

  guard(check: GuardCheck): () => void {
    return this.ctx.effect(() => {
      this.guards.add(check);
      return () => { this.guards.delete(check); };
    }, "fake tools.guard()");
  }

  get(): undefined {
    return undefined;
  }
}

/** An approval service reduced to what the ask listener reads: the public
 * halves of its private `effectivePolicy` (src/orders.ts effectiveApprovalPolicy). */
class FakeApproval extends Service {
  constructor(ctx: Context, readonly config: { policy: "ask" | "never" }) {
    super(ctx, "approval");
  }

  overrideOf(): undefined {
    return undefined;
  }
}

/** Run the `tools/pre-execute` waterfall the way the registry does, ending in
 * its own terminal ALLOW (NEW packages/core/tools/src/index.ts:1505-1507): a
 * decision other than `allow` can only have come from a registered listener. */
function firePreExecute(ctx: Context, exec: object): Promise<PreToolDecision> {
  return (ctx as unknown as {
    waterfall(name: "tools/pre-execute", exec: object, next: () => Promise<PreToolDecision>): Promise<PreToolDecision>;
  }).waterfall("tools/pre-execute", exec, () => Promise.resolve({ kind: "allow" }));
}

/** The live `tools/pre-execute` listener records on a tree's event bus - one
 * per registration, prepended ones first (NEW vendor/cordis/src/events.ts:
 * 254-260). Introspection on purpose: a doubled gate listener decides exactly
 * like a single one, so counting is the only way to see it. */
function preExecuteHooks(ctx: Context): readonly object[] {
  return ctx.events._hooks["tools/pre-execute"] ?? [];
}

test("armOrderGate: the guard arms on tools alone, the listener on approval; each re-arms exactly once and leaves with its service", async () => {
  const root = new Context();
  const gate = armOrderGate(root);
  const order = (name: string) => ({ name, callId: `offline-${name}`, arguments: ORDER, agent: { session: {} } });
  let lastRegistry: FakeTools | undefined;
  try {
    /* 1. Nothing to arm against yet: both halves wait, nothing is registered. */
    assert.equal(gate.listener.state, FIBER.pending, "the listener waits for approval");
    assert.equal(gate.guard.state, FIBER.pending, "the guard waits for tools");
    assert.equal(preExecuteHooks(root).length, 0);

    /* 2. `tools` ALONE arms the guard: it must not wait for approval, or a
     * registry that activates first would run orders unguarded. */
    const toolsA = root.plugin(FakeTools);
    await toolsA;
    await gate.guard.await();
    /* Through `unknown`: the installed dsh types augment `Context` with the
     * real registry's `ToolRuntime`, which this minimal fake is not. */
    const registryA = root.get("tools") as unknown as FakeTools;
    assert.equal(gate.guard.state, FIBER.active);
    assert.equal(registryA.guards.size, 1, "exactly one guard");
    assert.equal(gate.listener.state, FIBER.pending, "no approval yet, so no listener");
    assert.equal(preExecuteHooks(root).length, 0);
    /* And it is the gate's guard: an order with no logged grant is refused,
     * anything else passes. */
    const [check] = registryA.guards;
    assert.ok(check);
    assert.match(check({ name: NAME, callId: "offline-guard" }) ?? "", /without a logged allowed-once approval/);
    assert.equal(check({ name: "bash", callId: "offline-bash" }), undefined);

    /* 3. `approval` arms the listener: one prepended record, orders ask. */
    const approvalAsk = root.plugin(FakeApproval, { policy: "ask" });
    await approvalAsk;
    await gate.listener.await();
    assert.equal(gate.listener.state, FIBER.active);
    assert.equal(preExecuteHooks(root).length, 1);
    assert.equal((await firePreExecute(root, order(NAME))).kind, "ask");
    assert.equal((await firePreExecute(root, order("bash"))).kind, "allow", "other tools fall through");

    /* 4. Losing `approval` takes the listener with it - and only the listener. */
    await approvalAsk.dispose();
    assert.equal(gate.listener.state, FIBER.pending);
    assert.equal(preExecuteHooks(root).length, 0, "the old listener was disposed");
    assert.equal(registryA.guards.size, 1, "the guard does not depend on approval");

    /* 5. A replacement re-arms it EXACTLY ONCE, and it reads the NEW service:
     * this one's policy is `never`, which the gate denies in its own words. */
    const approvalNever = root.plugin(FakeApproval, { policy: "never" });
    await approvalNever;
    await gate.listener.await();
    assert.equal(preExecuteHooks(root).length, 1, "re-armed once, not stacked on a stale registration");
    const refused = await firePreExecute(root, order(NAME));
    assert.equal(refused.kind, "deny");
    assert.match(refused.kind === "deny" ? refused.reason : "", /approval policy is "never"/);

    /* 6. Replacing `tools` moves the guard: out of the old registry, once into the new. */
    await toolsA.dispose();
    assert.equal(registryA.guards.size, 0, "the guard left with its registry");
    assert.equal(gate.guard.state, FIBER.pending);
    const toolsB = root.plugin(FakeTools);
    await toolsB;
    await gate.guard.await();
    lastRegistry = root.get("tools") as unknown as FakeTools;
    assert.notEqual(lastRegistry.guards, registryA.guards, "a new registry");
    assert.equal(lastRegistry.guards.size, 1);
  } finally {
    /* 7. Disposing the host disposes both halves (bootFace's `dispose` is this
     * same root-fiber disposal). */
    await root.fiber.dispose();
  }
  assert.equal(gate.listener.state, FIBER.disposed);
  assert.equal(gate.guard.state, FIBER.disposed);
  assert.equal(preExecuteHooks(root).length, 0);
  assert.equal(lastRegistry?.guards.size, 0);
});

/** What the two fixture rows and this test share, on `globalThis` under
 * {@link DRILL} (the rows are loaded by the Loader; nothing else reaches them). */
interface MidbootDrill {
  /** Resolves when the test lets the slow row finish. */
  released: Promise<void>;
  /** The slow row finishes on its own after this long, so a test that dies
   * without releasing cannot hang the process. */
  holdCapMs: number;
  /** Arguments of every stand-in call whose BODY ran. */
  ran: unknown[];
  /** The root context of the tree being booted, from the stand-in row. */
  root?: Context;
  slowStarted?: number;
  slowDone?: number;
  standinRegistered?: number;
}

/** The fixtures' key (tests/fixtures/midboot-*.js). */
const DRILL = Symbol.for("kairos-face.order-gate-midboot-drill");

/** The fixture directory, for the rows' `file:` URLs. */
const FIXTURES = fileURLToPath(new URL("./fixtures/", import.meta.url));

/** One session event, structurally - just what the assertions read. */
interface EventLike {
  type: string;
  data?: { id?: unknown; callId?: unknown; toolName?: unknown; outcome?: unknown };
}

/** The live registry, as the smoke drives it. */
interface ToolsLike {
  schemas(): { name: string }[];
  register(definition: unknown): () => void;
  execute(exec: {
    callId: string; name: string; arguments: unknown; agent?: object; signal: AbortSignal;
  }): Promise<{ isError: boolean; content?: { type?: string; text?: string }[] }>;
}

/** A live agent, as the smoke drives it. */
interface AgentLike {
  session: { append(type: string, data: object): unknown; snapshotEvents(): readonly EventLike[] };
}

/** A Loader entry, as the smoke reads it (structural, like src/boot.ts AuditEntryLike). */
interface LoaderEntryLike {
  options: { id: string; name: string };
  readonly disabled: boolean;
  fiber?: { state: number; restart(): Promise<void> };
}

/** One Host-to-browser mux frame (`RemoteStreamServerMessage`, NEW
 * packages/api/gateway/src/stream-protocol.ts:254-257). */
interface MuxFrame {
  type: "item" | "error" | "end";
  streamId: string;
  value?: { type?: string; clientId?: string; event?: string; eventId?: string; request?: Record<string, unknown> };
  error?: { code: string; message: string };
}

/**
 * The operator's tab, as small as it can be: one cookie-admitted
 * `/api/remote.mux` socket carrying one `$events` stream, the way
 * order-gate-smoke.test.ts opens it (Node 22's undici WebSocket takes a
 * `headers` init). Frames are kept, never consumed, so a waiter can find one
 * that already arrived. A new `$events` client is handed every event still
 * pending in the gateway (NEW packages/api/gateway/src/index.ts:512-513) -
 * which is how a card raised mid-boot reaches the first tab after the commit.
 * @throws when the socket does not open or `ready` does not arrive.
 */
async function openEventsTab(port: number, cookie: string) {
  const Socket = WebSocket as unknown as new (url: string, init: { headers: Record<string, string> }) => WebSocket;
  const ws = new Socket(`ws://127.0.0.1:${port}/api/remote.mux`, { headers: { cookie } });
  const frames: MuxFrame[] = [];
  ws.addEventListener("message", (event) => { frames.push(JSON.parse(String(event.data)) as MuxFrame); });
  await new Promise<void>((resolve, reject) => {
    ws.addEventListener("open", () => resolve(), { once: true });
    ws.addEventListener("error", () => reject(new Error("the mux socket did not open (cookie refused, or appReady never committed)")), { once: true });
  });
  const frame = async (what: string, match: (frame: MuxFrame) => boolean, ms = 10_000): Promise<MuxFrame> => {
    const deadline = Date.now() + ms;
    for (;;) {
      const hit = frames.find(match);
      if (hit !== undefined) return hit;
      const failed = frames.find((f) => f.type !== "item");
      if (failed !== undefined) throw new Error(`mux stream ${failed.streamId} ${failed.type}: ${JSON.stringify(failed.error ?? null)}`);
      if (Date.now() >= deadline) throw new Error(`timed out waiting for ${what}; frames so far: ${JSON.stringify(frames)}`);
      await sleep(20);
    }
  };
  /* `$events` wants exactly the empty args object, and `ready` comes first
   * (stream-protocol.ts:34-39; gateway index.ts:482-494). */
  ws.send(JSON.stringify({ type: "open", streamId: "events", endpoint: "$events", payload: { args: {} } }));
  const ready = await frame("$events ready", (f) => f.streamId === "events" && f.type === "item" && f.value?.type === "ready");
  const clientId = ready.value?.clientId;
  assert.ok(typeof clientId === "string" && clientId.length > 0, "ready carries a clientId");
  return { clientId, frame, close: () => ws.close() };
}

test("mid-boot: while a slow row holds boot() open, a live order tool is held for a card or denied - never dispatched", {
  skip: gated && "set FACE_SMOKE=1",
}, async () => {
  /* A scratch home: AKShare off (never the operator's data server), then the
   * two fixture rows. The stand-in's description carries the marker, so the
   * gate sees what the real alpaca-kit tool would show it. */
  const home = mkdtempSync(join(tmpdir(), "face-ordergate-midboot-"));
  setupFaceProfile(home);
  const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
  const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
  const description = `place a PAPER order - mid-boot drill stand-in, nothing behind it ${OPERATOR_GATED_MARKER}`;
  writeFileSync(patchPath, [
    patch,
    "- id: mcp-akshare",
    "  disabled: true",
    "- insert:",
    "    - id: midboot-order-standin",
    `      name: ${JSON.stringify(pathToFileURL(join(FIXTURES, "midboot-order-standin.js")).href)}`,
    "      config:",
    `        tool: ${NAME}`,
    `        description: ${JSON.stringify(description)}`,
    "    - id: midboot-slow-row",
    `      name: ${JSON.stringify(pathToFileURL(join(FIXTURES, "midboot-slow-row.js")).href)}`,
    "",
  ].join("\n"));

  let release: () => void = () => {};
  const drill: MidbootDrill = {
    released: new Promise<void>((resolve) => { release = resolve; }),
    holdCapMs: 30_000,
    ran: [],
  };
  (globalThis as Record<symbol, unknown>)[DRILL] = drill;

  const t0 = Date.now();
  const booting = bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: await makeBotsRoot() });
  let settled: { ok: boolean; error?: unknown } | undefined;
  booting.then(() => { settled = { ok: true }; }, (error: unknown) => { settled = { ok: false, error }; });

  /** Wait for a condition INSIDE the window: fail at once if the boot settled
   * first - then nothing below would be testing the window at all. */
  const midboot = async <T>(what: string, probe: () => T | undefined | Promise<T | undefined>, ms = 10_000): Promise<T> => {
    const deadline = Date.now() + ms;
    for (;;) {
      if (settled !== undefined) {
        throw new Error(`bootFace settled before ${what} - the slow row did not hold the boot open` +
          (settled.ok ? "" : `: ${String(settled.error)}`));
      }
      const value = await probe();
      if (value !== undefined) return value;
      if (Date.now() >= deadline) throw new Error(`timed out after ${ms} ms waiting for ${what}`);
      await sleep(20);
    }
  };
  const assertStillBooting = (when: string): void => {
    assert.equal(settled, undefined, `bootFace must still be pending ${when}`);
    assert.equal(drill.slowDone, undefined, `the slow row must still hold the boot open ${when}`);
  };

  const held = new AbortController();
  const cleanups: (() => void)[] = [() => held.abort()];
  let booted: BootedFace | undefined;
  try {
    /* M0. THE WINDOW, reproduced: the tree is serving, the order tool is live,
     * and `bootFace` has not returned. */
    const root = await midboot("the stand-in row's root context and a listening webserver", () =>
      drill.root !== undefined && drill.root.get("webServer") !== undefined && drill.root.get("connection") !== undefined
        ? drill.root
        : undefined);
    const port = root.webServer.port;
    const base = `http://127.0.0.1:${port}`;
    /* The tab's cookie. `/` is mounted by main.ts only after bootFace; the
     * smoke mounts it now, since the threat is a tab that already HOLDS a
     * cookie (it lives 30 days) - how it got one is not the point. */
    mountClient(root);
    const cookie = await signIn(root, base);
    const firstServed = await midboot("unary /api to serve session/list", async () => {
      try {
        return (await remoteResult(base, cookie, "session/list", { _request: {} })).ok ? Date.now() : undefined;
      } catch {
        return undefined; // the gateway has not claimed /api yet (404), or the socket is not up
      }
    });
    const created = await remote<{ sessionId: string }>(base, cookie, "session/create", { request: { cwd: home } });
    const tools = root.get("tools") as ToolsLike;
    const agent = (root.get("agents") as { get(id: string): AgentLike | undefined }).get(created.sessionId);
    assert.ok(agent !== undefined, `session/create must leave a live agent for ${created.sessionId}`);
    assert.ok(tools.schemas().some((schema) => schema.name === NAME), "the order stand-in is registered, live, mid-boot");
    /* The answer channel is up mid-boot as well, so a card raised now parks in
     * the gateway instead of failing 'unavailable' (NEW packages/api/remotes/
     * src/index.ts:57-75; gateway index.ts:549-606). */
    await midboot("the approval answerer row (dsh-api-remotes) to activate", () =>
      [...(root.get("loader") as { entries(): Iterable<LoaderEntryLike> }).entries()]
        .some((entry) => entry.options.name === "@deepseek-ai/dsh-api-remotes" && entry.fiber?.state === FIBER.active)
        ? true
        : undefined);
    assertStillBooting("once a session exists over unary /api");
    /* `approval.request` needs an open turn (NEW packages/interaction/
     * user-approval/src/index.ts:215-223); a created-but-undriven session has none. */
    agent.session.append("turn/start", { turn: 1 });

    /* M1. THE REVIEWER'S CALL: the stand-in, through the real registry, from a
     * live agent. Before the fix it dispatched here. Now the listener raises a
     * card, and the card PARKS - no tab can take it until the streams open. */
    const parked = tools.execute({ callId: "midboot-order", name: NAME, arguments: ORDER, agent, signal: held.signal });
    const asked = await midboot("the listener's approval/asked for the mid-boot order", () =>
      agent.session.snapshotEvents().find((event) => event.type === "approval/asked" && event.data?.callId === "midboot-order"));
    assert.equal(asked.data?.toolName, NAME, "the card is for this tool");
    assert.deepEqual(drill.ran, [], "the order body must not run mid-boot");
    assert.equal(await Promise.race([parked.then(() => "settled"), sleep(150).then(() => "held")]), "held",
      "the order must wait for a human, not settle on its own");

    /* M2. The same order with no agent: the LISTENER denies in its own words. */
    const agentless = await tools.execute({
      callId: "midboot-agentless", name: NAME, arguments: ORDER, signal: new AbortController().signal,
    });
    assert.equal(agentless.isError, true);
    assert.match(agentless.content?.[0]?.text ?? "", /needs a per-order approval card and this call has no session to ask in/);

    /* M3. THE GUARD, alone: a marked tool whose name the gate does not match.
     * The listener does not claim it, so the waterfall ends in ALLOW - the
     * denial can only be the guard's (it runs on every allow, NEW
     * packages/core/tools/src/index.ts:1519). Unregistered before the boot is
     * released: the post-boot audit would rightly refuse an ungated marked tool. */
    let renamedRan = false;
    const unregister = tools.register({
      name: "mcp__drill__submit_order",
      description: `submit a PAPER order - renamed drill stand-in ${OPERATOR_GATED_MARKER}`,
      parameters: {},
      output: { schema: { type: "object" }, render: () => [{ type: "text", text: "ok" }] },
      execute: async () => {
        renamedRan = true;
        return {};
      },
    });
    try {
      const renamed = await tools.execute({
        callId: "midboot-renamed", name: "mcp__drill__submit_order", arguments: {}, agent, signal: new AbortController().signal,
      });
      assert.equal(renamed.isError, true, "a marked tool the gate cannot name must not dispatch");
      assert.equal(renamedRan, false, "its body must never run");
      assert.match(renamed.content?.[0]?.text ?? "", /ORDER_RAW_NAMES/);
    } finally {
      unregister();
    }
    assert.deepEqual(drill.ran, [], "no order body ran mid-boot");
    assertStillBooting("after the three mid-boot calls");
    const rel = (at: number | undefined): string => (at === undefined ? "never" : `+${at - t0}ms`);
    console.log(
      `midboot observed: order stand-in registered ${rel(drill.standinRegistered)}, unary /api served ${rel(firstServed)},` +
        ` card raised and held, agentless and renamed calls denied - all before the slow row was released (+${Date.now() - t0}ms)`,
    );

    /* P1. Release the slow row; the boot completes on the SAME tree. */
    release();
    booted = await booting;
    assert.equal(booted.ctx, root, "the fixture saw the tree bootFace returned");

    /* P2. THE NORMAL PATH, on the order that arrived mid-boot: the held card
     * reaches the first tab once `appReady` committed, carries the order line,
     * and the operator's `allowed-once` dispatches it exactly once. */
    const tab = await openEventsTab(port, cookie);
    cleanups.push(() => tab.close());
    const card = await tab.frame("the held card on the first tab", (frame) => frame.streamId === "events"
      && frame.type === "item" && frame.value?.type === "waterfall" && frame.value.event === "approval/request"
      && frame.value.request?.callId === "midboot-order");
    assert.match(String(card.value?.request?.reason), /PAPER order - .*symbol=AAPL/, "the card names the order");
    assert.deepEqual(drill.ran, [], "nothing dispatched before the answer");
    const answered = await remoteResult(base, cookie, "$events/result", {
      clientId: tab.clientId, eventId: card.value?.eventId, outcome: { kind: "result", value: "allowed-once" },
    });
    assert.equal(answered.ok, true, `$events/result: ${JSON.stringify(answered)}`);
    const dispatched = await parked;
    assert.equal(dispatched.isError, false, `the approved order must dispatch; the tool said ${JSON.stringify(dispatched.content)}`);
    assert.deepEqual(drill.ran, [ORDER], "the body ran exactly once, with the approved arguments");
    const log = agent.session.snapshotEvents();
    assert.ok(log.some((event) => event.type === "approval/decided" && event.data?.id === asked.data?.id
      && event.data?.outcome === "allowed-once"), "the grant the guard read is logged against the mid-boot card");
    agent.session.append("turn/end", { turn: 1, reason: { kind: "completed" } });

    /* P3. THE RE-ARM, on the real tree: restart the `approval` row. Its
     * service leaves and comes back as a new instance, so the listener's
     * inject fiber unloads - disposing its record - and runs once more. Exactly
     * one record must be replaced (a stacked listener would add one), and the
     * fresh one is the outermost (it prepends again). */
    const before = [...preExecuteHooks(root)];
    const approvalEntry = [...(root.get("loader") as { entries(): Iterable<LoaderEntryLike> }).entries()]
      .find((entry) => entry.options.name === "@deepseek-ai/dsh-user-approval" && !entry.disabled);
    assert.ok(approvalEntry?.fiber !== undefined, "the approval row is mounted");
    await approvalEntry.fiber.restart();
    const replaced = (): object[] => preExecuteHooks(root).filter((hook) => !before.includes(hook));
    await (async () => {
      const deadline = Date.now() + 10_000;
      while (replaced().length === 0 || preExecuteHooks(root).length !== before.length) {
        if (Date.now() >= deadline) throw new Error(`the listener did not re-arm: ${preExecuteHooks(root).length} records, ${replaced().length} new`);
        await sleep(20);
      }
    })();
    await sleep(50); // a stacked second registration would land by now
    assert.equal(preExecuteHooks(root).length, before.length, "re-armed exactly once, not stacked");
    assert.equal(replaced().length, 1, "exactly one record was replaced: the gate's listener");
    assert.equal(preExecuteHooks(root)[0], replaced()[0], "the re-armed listener is outermost again");
    const again = await firePreExecute(root, {
      name: NAME, callId: "midboot-rearmed", arguments: ORDER, agent: { session: { seq: 0, eventAt: (): undefined => undefined } },
    });
    assert.equal(again.kind, "ask", "the re-armed listener still raises a card");

    /* P4. Disposal leaves no gate listener behind. */
    await booted.dispose();
    assert.equal(preExecuteHooks(root).length, 0, "nothing registered on tools/pre-execute outlives the tree");
  } finally {
    release();
    for (const cleanup of cleanups.reverse()) {
      try { cleanup(); } catch { /* the disposal below tears the tree down regardless */ }
    }
    try {
      booted ??= await booting;
    } catch {
      /* the boot's own failure is the test's failure, already thrown above */
    }
    await booted?.dispose();
    delete (globalThis as Record<symbol, unknown>)[DRILL];
  }
});
