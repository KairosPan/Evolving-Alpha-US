/** The native subagent lifecycle through the same host RPCs the face uses.
 * Local scripted models and disposable workspaces only; no provider calls.
 *
 * dsh 0.2.0 wire (PLAN Appendix A): every call is `remote(base, cookie,
 * "<ns>/<method>", args)` over the signed browser cookie (tests/remote.ts).
 * `subagent.list` and `subagent.history` have no Remote any more; they are
 * composed here the way the client composes them (PLAN S8): the catalog is the
 * parent's `subagentCatalog` projection (`session/projections`, non-activating,
 * NEW packages/api/session-controller/src/index.ts:490-512) plus the parent
 * row's `agentAvailable` from `session/list`; history is `session/page` with a
 * SUBAGENT address (types.ts:408-415) cut at the child's projection `asOfSeq`
 * (a page may not read past the source cursor, history.ts:89-94). The
 * `report` tool was deleted upstream (package tool-subagent-report,
 * b91e7ce366): a continuable child now reaches its parent with `send_message`,
 * delivered as an `agent-message` relay (NEW
 * packages/subagent/subagent/src/continuation-messages.ts:15-52).
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, realpath, rm, writeFile } from "node:fs/promises";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { GenerateOptions, StreamChunk } from "@deepseek-ai/dsh-llm";
import { SessionId } from "@deepseek-ai/dsh-session";
import type { PermissionPresetService } from "@deepseek-ai/dsh-permission-presets";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { makeBotsRoot } from "./bots-fixture.ts";
import { mountClient, remote, remoteResult, signIn } from "./remote.ts";
import { StubAdapter, type StubReply } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";

type Event = { type: string; data: unknown };
const sourceOf = (message: { source?: unknown }): Record<string, unknown> => (message.source ?? {}) as Record<string, unknown>;
const textOf = (message: GenerateOptions["messages"][number]): string =>
  message.content.map((block) => "text" in block ? block.text : "").join("\n");
function triggerOf(request: GenerateOptions) {
  /* `agent-message` is the 0.2.0 relay a child's `send_message` lands as; the
   * 0.1.1 `subagent-report` kind stays listed for migrated logs. Without it the
   * parent would route on its older START_* prompt and spawn again. */
  return [...request.messages].reverse().find((message) =>
    ["user", "tool", "coordinator", "agent-message", "subagent-report", "subagent-settled"].includes(String(sourceOf(message).kind)));
}
async function waitFor(label: string, check: () => boolean, ms = 20_000): Promise<void> {
  const until = Date.now() + ms;
  while (!check()) {
    if (Date.now() >= until) throw new Error(`timed out waiting for ${label}`);
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

/** One durable child address, as the Remote surface names it. */
type ChildAddress = { parentSessionId: SessionId; childSessionId: SessionId; mode: "continuable" | "one-shot" };
/** One catalog row (NEW packages/subagent/subagent/src/projection-types.ts:9-19). */
type CatalogEntry = { id: string; createdAt: number; mode: "one-shot" | "continuable" | "unknown"; label?: string };

test("native subagents: continuable and foreground calls, parent notices, read-only catalog, follow-up, interruption and cold recovery", {
  skip: gated && "set FACE_SMOKE=1", timeout: 120_000,
}, async () => {
  const bots = await makeBotsRoot();
  const root = await realpath(await mkdtemp(join(tmpdir(), "face-subagents-root-")));
  const home = await mkdtemp(join(tmpdir(), "face-subagents-home-"));
  let stop: (() => Promise<void>) | undefined;
  try {
    await mkdir(join(root, ".git"));
    await writeFile(join(root, "AGENTS.md"), "# Fixture\nComplete only the scripted subtask.\n");
    setupFaceProfile(home);
    const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
    const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
    // This smoke owns a scratch profile and must not start the operator's data server.
    /* The host default route is a PROFILE ROW at dsh 0.2.0: without
     * `profileContext` the face mounts no `configEditor`, and
     * `agentDefaultModel.saveSelection` then returns without writing anything
     * (NEW packages/core/agent-default-model/src/index.ts:74-91; PLAN D1/D2).
     * So the scratch profile names the stub route up front, the same way the
     * operator names theirs, and the boot below asserts it took. */
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n` +
      `- id: agent-default-model\n  config:\n    provider: stub\n    model: echo\n`);
    let booted = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    stop = booted.dispose;
    let ctx = booted.ctx;
    const blocked = new Set<string>();
    const requested = new Map<string, GenerateOptions[]>();
    const script = (request: GenerateOptions): StubReply => {
      if (request.purpose !== undefined) return { kind: "text", text: "Subagent fixture" };
      const id = String(request.sessionId);
      requested.set(id, [...requested.get(id) ?? [], request]);
      const trigger = triggerOf(request);
      const source = trigger ? sourceOf(trigger).kind : undefined;
      const text = trigger ? textOf(trigger) : "";
      const header = ctx.sessions.get(request.sessionId!)?.header;
      const child = header?.origin === "subagent";
      if (child) {
        if (text.includes("FOREGROUND_CHILD")) return { kind: "text", text: "FOREGROUND_RESULT" };
        if (text.includes("FOLLOWUP")) return { kind: "text", text: `FOLLOWUP_RESULT: ${text}` };
        if (source === "tool") return { kind: "text", text: "CHILD_CLOSING_RESULT" };
        /* The 0.1.1 `report` tool is gone; the explicit child-to-parent
         * message is `send_message` addressed to the direct parent. */
        return { kind: "tool", name: "send_message", args: { agent_id: String(header?.parentSession), message: "CHILD_REPORTED_EVIDENCE" } };
      }
      if (source === "user" && text === "START_BACKGROUND") return {
        kind: "tool", name: "subagent", args: { description: "Check fixture evidence", prompt: "CHILD_MAIN: inspect the fixture evidence and report." },
      };
      if (source === "user" && text === "START_FOREGROUND") return {
        kind: "tool", name: "subagent", args: { description: "Check foreground evidence", prompt: "FOREGROUND_CHILD", run_in_background: false },
      };
      return { kind: "text", text: "PARENT_ACKNOWLEDGED" };
    };
    class BlockingAdapter extends StubAdapter {
      override async *stream(request: GenerateOptions): AsyncIterable<StreamChunk> {
        const trigger = triggerOf(request);
        if (request.purpose === undefined && trigger && textOf(trigger) === "BLOCK_UNTIL_INTERRUPT"
            && ctx.sessions.get(request.sessionId!)?.header.origin === "subagent") {
          blocked.add(String(request.sessionId));
          const signal = request.signal;
          assert.ok(signal, "a child request receives a cancellation signal");
          await new Promise<void>((resolve) => {
            if (signal.aborted) resolve();
            else signal.addEventListener("abort", () => resolve(), { once: true });
          });
          throw signal.reason ?? new Error("fixture interrupted");
        }
        yield* super.stream(request);
      }
    }
    const installAdapter = () => ctx.llm.registerAdapter(["stub"], new BlockingAdapter(script));
    installAdapter();
    const defaultRoute = () => (ctx.get("agentDefaultModel") as { currentSelection(): { provider: string; model: string } })
      .currentSelection();
    assert.deepEqual({ ...defaultRoute() }, { provider: "stub", model: "echo" }, "the scratch profile's default route took");
    let base = `http://127.0.0.1:${ctx.webServer.port}`;
    mountClient(ctx);
    let cookie = await signIn(ctx, base);
    /** A business call that must succeed. */
    const rpc = <T = any>(endpoint: string, args: object): Promise<T> => remote<T>(base, cookie, endpoint, args);
    /** A business call whose failure is the assertion (HTTP 200, `ok:false`). */
    const rawRpc = (endpoint: string, args: object) => remoteResult(base, cookie, endpoint, args);
    const text = (value: string) => [{ type: "text", text: value }];
    /** The read-only catalog, composed as the client composes it (PLAN S8). */
    const catalogOf = async (parentSessionId: SessionId): Promise<{ parentAvailable: boolean; entries: CatalogEntry[] }> => {
      const projections = await rpc<{ asOfSeq: number; values: Record<string, unknown> } | null>(
        "session/projections", { request: { sessionId: parentSessionId } });
      const listed = await rpc<{ items: { sessionId: string; agentAvailable: boolean }[] }>("session/list", { _request: {} });
      return {
        parentAvailable: listed.items.find((item) => item.sessionId === parentSessionId)?.agentAvailable === true,
        entries: (projections?.values.subagentCatalog ?? []) as CatalogEntry[],
      };
    };
    /** A child's history without acquiring its Agent: one `session/page` over
     * the subagent address, cut at the child's current projection cursor. */
    const historyOf = async (address: ChildAddress) => {
      const cut = await rpc<{ asOfSeq: number } | null>("session/projections", { request: { sessionId: address.childSessionId } });
      assert.ok(cut, `child ${address.childSessionId} exists`);
      return rpc<{ records: { type: "event"; event: Event }[]; hasMore: boolean }>("session/page", {
        request: { address: { kind: "subagent", ...address }, throughSeq: cut.asOfSeq, maxMessages: 1000 },
      });
    };
    /** The child's durable header and log through a READ handle (NEW
     * packages/session/session-persistence/src/handle.ts:14-23, 59-83): read
     * never takes ownership; `close()` is the one teardown. Replaces 0.1.1's
     * `sessionPersistence.inspect`, removed with the handle-based seam. */
    const readStored = async (id: SessionId) => {
      const persistence = ctx.get("sessionPersistence") as {
        open(id: SessionId, access: "read"): Promise<{
          header: Record<string, unknown>; read(): Promise<{ events: readonly Event[] }>; close(): Promise<void>;
        }>;
      };
      const handle = await persistence.open(id, "read");
      try {
        return { meta: handle.header, events: (await handle.read()).events };
      } finally {
        await handle.close();
      }
    };

    const parentId = SessionId((await rpc<{ sessionId: string }>("session/create", { request: { cwd: root } })).sessionId);
    const parent = ctx.agents.get(parentId)!;
    const permission = ctx.get("permissionPresets") as PermissionPresetService;
    permission.set(parent.session, "read-only");
    const schemaNames = (ctx.get("tools") as { schemas(scope: object): { name: string }[] })
      .schemas(parent).map((tool) => tool.name);
    for (const name of ["subagent", "subagent_fork", "send_message", "interrupt_agent", "list_agents"]) assert.ok(schemaNames.includes(name), name);
    assert.equal(schemaNames.includes("report"), false, "the 0.1.1 report tool no longer exists");
    const promptParent = (value: string) => rpc("session/prompt", {
      request: { requestId: `subagents-${crypto.randomUUID()}`, sessionId: parentId, mode: "queue", content: text(value) },
    });
    const parentSources = () => parent.session.snapshotEvents().filter((event) => event.type === "user/message")
      .map((event) => sourceOf(event.data as { source?: unknown }));
    await promptParent("START_BACKGROUND");
    await waitFor("child settlement", () => parentSources().some((source) => source.kind === "subagent-settled"));
    await parent.whenIdle();
    const reported = parentSources().find((source) => source.kind === "agent-message" && source.form === "relay");
    const settled = parentSources().find((source) => source.kind === "subagent-settled");
    assert.ok(reported, "explicit child message is attributed independently (agent-message relay)");
    assert.ok(settled, "native completion wakes the parent with a separate notice");
    assert.equal(reported.senderSessionId, settled.senderSessionId);
    assert.ok(JSON.stringify(parent.session.snapshotEvents()).includes("CHILD_REPORTED_EVIDENCE"));
    assert.ok(JSON.stringify(parent.session.snapshotEvents()).includes("CHILD_CLOSING_RESULT"));
    const childId = SessionId(String(settled.senderSessionId));
    const address: ChildAddress = { parentSessionId: parentId, childSessionId: childId, mode: "continuable" };
    const countAgents = () => ctx.agents.list().length;
    const beforeRead = countAgents();
    const catalog = await catalogOf(parentId);
    assert.equal(catalog.parentAvailable, true);
    assert.ok(catalog.entries.some((entry) => entry.id === childId && entry.mode === "continuable" && entry.label === "Check fixture evidence"));
    const history = await historyOf(address);
    assert.equal(countAgents(), beforeRead, "catalog and history do not acquire a child Agent");
    assert.ok(JSON.stringify(history).includes("CHILD_CLOSING_RESULT"));
    const recorded = await readStored(childId);
    assert.equal(recorded.meta.origin, "subagent");
    assert.equal(recorded.meta.parentSession, parentId);
    assert.equal(recorded.meta.cwd, root);
    assert.equal(recorded.meta.agentPreset, "kairos");
    assert.equal(recorded.meta.delegationDepth, 1);
    assert.ok(recorded.events.some((event) => event.type === "sandbox/mode" && JSON.stringify(event.data).includes('"source":"delegation"') && JSON.stringify(event.data).includes('"mode":"read-only"')));
    assert.ok(recorded.events.some((event) => event.type === "approval/policy" && JSON.stringify(event.data).includes('"source":"delegation"') && JSON.stringify(event.data).includes('"policy":"never"')));
    const firstChildRequest = requested.get(childId)![0];
    assert.ok(firstChildRequest.tools?.some((tool) => tool.name === "send_message"), "a continuable child can message its parent");
    assert.ok(firstChildRequest.messages.some((message) => textOf(message).includes("permission scope was fixed")));
    assert.equal(firstChildRequest.messages.some((message) => textOf(message) === "START_BACKGROUND"), false, "spawn starts with a standalone prompt, without parent conversation history");

    /* `subagents/prompt` needs a client-minted `requestId` and a `delivery`
     * (NEW packages/subagent/subagent/src/control-types.ts:85-102). */
    const promptChild = (target: ChildAddress, value: string) => ({
      request: { requestId: `subagents-${crypto.randomUUID()}`, ...target, mode: "continuable", delivery: "queue", content: text(value) },
    });
    const followup = (value: string) => rpc("subagents/prompt", promptChild(address, value));
    await followup("FOLLOWUP_ONE");
    await waitFor("follow-up output", () => requested.get(childId)?.some((request) => request.messages.some((message) => textOf(message) === "FOLLOWUP_ONE")) ?? false);
    await waitFor("second child settlement", () => parentSources().filter((source) => source.kind === "subagent-settled").length === 2);
    await parent.whenIdle();
    assert.ok(JSON.stringify(await historyOf(address)).includes("FOLLOWUP_RESULT: FOLLOWUP_ONE"));
    const otherId = SessionId((await rpc<{ sessionId: string }>("session/create", { request: { cwd: root } })).sessionId);
    const foreignAddress: ChildAddress = { ...address, parentSessionId: otherId };
    assert.equal((await rawRpc("subagents/prompt", promptChild(foreignAddress, "unauthorized"))).ok, false);
    await followup("BLOCK_UNTIL_INTERRUPT");
    await waitFor("blocking child request", () => blocked.has(childId));
    assert.equal((await rawRpc("session/prompt", {
      request: { requestId: `subagents-${crypto.randomUUID()}`, sessionId: childId, mode: "queue", content: text("wrong route") },
    })).ok, false);
    assert.equal((await rawRpc("session/cancel", { request: { sessionId: childId } })).ok, false);
    /* `interruptByParent` takes three positional parameters, so three
     * top-level wire keys (index.ts:482-503). */
    const interrupt = (target: ChildAddress) => ({
      childSessionId: target.childSessionId, parentSessionId: target.parentSessionId, mode: "continuable",
    });
    const foreignStop = await rawRpc("subagents/interruptByParent", interrupt(foreignAddress));
    assert.equal(foreignStop.ok, false);
    assert.equal(foreignStop.ok ? undefined : foreignStop.error.code, "subagent/unauthorized");
    assert.equal((await rpc<{ accepted: boolean }>("subagents/interruptByParent", interrupt(address))).accepted, true);
    await waitFor("interrupted child settlement", () => parentSources().filter((source) => source.kind === "subagent-settled").length === 3);
    await parent.whenIdle();
    assert.ok(JSON.stringify(await historyOf(address)).includes("aborted"));
    await followup("FOLLOWUP_AFTER_INTERRUPT");
    await waitFor("post-interrupt settlement", () => parentSources().filter((source) => source.kind === "subagent-settled").length === 4);
    await parent.whenIdle();
    assert.ok(JSON.stringify(await historyOf(address)).includes("FOLLOWUP_RESULT: FOLLOWUP_AFTER_INTERRUPT"));

    await promptParent("START_FOREGROUND");
    await waitFor("foreground result in parent", () => parent.session.snapshotEvents().some((event) => event.type === "tool/result" && JSON.stringify(event.data).includes("FOREGROUND_RESULT")));
    await parent.whenIdle();
    const allChildren = (await catalogOf(parentId)).entries;
    const oneShot = allChildren.find((entry) => entry.mode === "one-shot");
    assert.ok(oneShot, "foreground subagent is cataloged as one-shot");
    assert.ok(requested.get(oneShot.id)?.length, "the one-shot child reached the adapter");
    assert.ok(JSON.stringify(await historyOf({ parentSessionId: parentId, childSessionId: SessionId(oneShot.id), mode: "one-shot" })).includes("FOREGROUND_RESULT"));
    assert.equal(parentSources().filter((source) => source.kind === "subagent-settled").length, 4, "foreground output returns through its tool, not a continuable notice");
    assert.equal((await rawRpc("subagents/prompt", promptChild({ parentSessionId: parentId, childSessionId: SessionId(oneShot.id), mode: "continuable" }, "invalid continuation"))).ok, false);

    await stop();
    stop = undefined;
    booted = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    stop = booted.dispose;
    ctx = booted.ctx;
    base = `http://127.0.0.1:${ctx.webServer.port}`;
    /* The browser-session secret persists in the credentials store, but the
     * cookie is per authority and the port changed - sign in again. */
    mountClient(ctx);
    cookie = await signIn(ctx, base);
    installAdapter();
    const coldCount = countAgents();
    const coldCatalog = await catalogOf(parentId);
    assert.equal(coldCatalog.parentAvailable, false);
    assert.ok(coldCatalog.entries.some((entry) => entry.id === childId && entry.mode === "continuable"));
    assert.ok(JSON.stringify(await historyOf(address)).includes("FOLLOWUP_AFTER_INTERRUPT"));
    assert.equal(countAgents(), coldCount, "cold catalog and history remain read-only");
    const coldSend = await rawRpc("subagents/prompt", promptChild(address, "FOLLOWUP_COLD"));
    assert.equal(coldSend.ok ? undefined : coldSend.error.code, "subagent/parent-unavailable");
    assert.equal((await rpc<{ sessionId: string }>("session/create", { request: { sessionId: parentId, cwd: root, agentPreset: "kairos" } })).sessionId, parentId);
    assert.equal((await catalogOf(parentId)).parentAvailable, true);
    await followup("FOLLOWUP_COLD_RESUMED");
    const restoredParent = ctx.agents.get(parentId)!;
    await waitFor("cold-resumed child settlement", () => restoredParent.session.snapshotEvents().some((event) => event.type === "user/message"
      && sourceOf(event.data as { source?: unknown }).kind === "subagent-settled" && JSON.stringify(event.data).includes("FOLLOWUP_COLD_RESUMED")));
    await restoredParent.whenIdle();
    assert.ok(JSON.stringify(await historyOf(address)).includes("FOLLOWUP_RESULT: FOLLOWUP_COLD_RESUMED"));
  } finally {
    await stop?.();
    await Promise.all([rm(bots, { recursive: true, force: true }), rm(root, { recursive: true, force: true }), rm(home, { recursive: true, force: true })]);
  }
});
