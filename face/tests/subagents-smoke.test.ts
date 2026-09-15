/** The native subagent lifecycle through the same host RPCs the face uses.
 * Local scripted models and disposable workspaces only; no provider calls. */
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
import { StubAdapter, type StubReply } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";
type Event = { type: string; data: unknown };
const sourceOf = (message: { source?: unknown }): Record<string, unknown> => (message.source ?? {}) as Record<string, unknown>;
const textOf = (message: GenerateOptions["messages"][number]): string =>
  message.content.map((block) => "text" in block ? block.text : "").join("\n");
function triggerOf(request: GenerateOptions) {
  return [...request.messages].reverse().find((message) =>
    ["user", "tool", "coordinator", "subagent-report", "subagent-settled"].includes(String(sourceOf(message).kind)));
}
async function waitFor(label: string, check: () => boolean, ms = 20_000): Promise<void> {
  const until = Date.now() + ms;
  while (!check()) {
    if (Date.now() >= until) throw new Error(`timed out waiting for ${label}`);
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

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
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
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
      const child = ctx.sessions.get(request.sessionId!)?.header.origin === "subagent";
      if (child) {
        if (text.includes("FOREGROUND_CHILD")) return { kind: "text", text: "FOREGROUND_RESULT" };
        if (text.includes("FOLLOWUP")) return { kind: "text", text: `FOLLOWUP_RESULT: ${text}` };
        if (source === "tool") return { kind: "text", text: "CHILD_CLOSING_RESULT" };
        return { kind: "tool", name: "report", args: { output: "CHILD_REPORTED_EVIDENCE" } };
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
    await (ctx.get("agentDefaultModel") as { saveSelection(selection: object): Promise<void> })
      .saveSelection({ provider: "stub", model: "echo" });
    let base = `http://127.0.0.1:${ctx.webServer.port}`;
    let seq = 0;
    const rawRpc = async (method: string, payload: object) => {
      const response = await fetch(`${base}/api/${method}`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ type: "client-request", rpcId: `subagents-${++seq}`, method, payload }),
      });
      assert.equal(response.status, 200, method);
      return (await response.json() as { result: { ok: boolean; value?: any; error?: { code: string; message: string } } }).result;
    };
    const rpc = async (method: string, payload: object): Promise<any> => {
      const result = await rawRpc(method, payload);
      assert.equal(result.ok, true, `${method}: ${JSON.stringify(result.error)}`);
      return result.value;
    };
    const parentId = SessionId((await rpc("session.create", { cwd: root })).sessionId);
    const parent = ctx.agents.get(parentId)!;
    const permission = ctx.get("permissionPresets") as PermissionPresetService;
    permission.set(parent.session, "read-only");
    const schemaNames = (ctx.get("tools") as { schemas(scope: object): { name: string }[] })
      .schemas(parent).map((tool) => tool.name);
    for (const name of ["subagent", "subagent_fork", "send_message", "interrupt_agent", "list_agents"]) assert.ok(schemaNames.includes(name), name);
    assert.equal(schemaNames.includes("report"), false, "report belongs only to continuable children");
    const promptParent = (text: string) => rpc("session.prompt", { sessionId: parentId, mode: "queue", content: [{ type: "text", text }] });
    const parentSources = () => parent.session.events.filter((event) => event.type === "user/message")
      .map((event) => sourceOf(event.data as { source?: unknown }));
    await promptParent("START_BACKGROUND");
    await waitFor("child settlement", () => parentSources().some((source) => source.kind === "subagent-settled"));
    await parent.whenIdle();
    const reported = parentSources().find((source) => source.kind === "subagent-report");
    const settled = parentSources().find((source) => source.kind === "subagent-settled");
    assert.ok(reported, "explicit child report is attributed independently");
    assert.ok(settled, "native completion wakes the parent with a separate notice");
    assert.equal(reported.senderSessionId, settled.senderSessionId);
    assert.ok(JSON.stringify(parent.session.events).includes("CHILD_REPORTED_EVIDENCE"));
    assert.ok(JSON.stringify(parent.session.events).includes("CHILD_CLOSING_RESULT"));
    const childId = SessionId(String(settled.senderSessionId));
    const address = { parentSessionId: parentId, childSessionId: childId, mode: "continuable" };
    const countAgents = () => ctx.agents.list().length;
    const beforeRead = countAgents();
    const catalog = await rpc("subagent.list", { parentSessionId: parentId });
    assert.equal(catalog.parentAvailable, true);
    assert.ok(catalog.entries.some((entry: any) => entry.id === childId && entry.mode === "continuable" && entry.label === "Check fixture evidence"));
    const history = await rpc("subagent.history", address);
    assert.equal(countAgents(), beforeRead, "catalog and history do not acquire a child Agent");
    assert.ok(JSON.stringify(history).includes("CHILD_CLOSING_RESULT"));
    const persistence = ctx.get("sessionPersistence") as { inspect(id: SessionId): Promise<{ meta: Record<string, unknown>; events: Event[] }> };
    const recorded = await persistence.inspect(childId);
    assert.equal(recorded.meta.origin, "subagent");
    assert.equal(recorded.meta.parentSession, parentId);
    assert.equal(recorded.meta.cwd, root);
    assert.equal(recorded.meta.agentPreset, "kairos");
    assert.equal(recorded.meta.delegationDepth, 1);
    assert.ok(recorded.events.some((event) => event.type === "sandbox/mode" && JSON.stringify(event.data).includes('"source":"delegation"') && JSON.stringify(event.data).includes('"mode":"read-only"')));
    assert.ok(recorded.events.some((event) => event.type === "approval/policy" && JSON.stringify(event.data).includes('"source":"delegation"') && JSON.stringify(event.data).includes('"policy":"never"')));
    const firstChildRequest = requested.get(childId)![0];
    assert.ok(firstChildRequest.tools?.some((tool) => tool.name === "report"));
    assert.ok(firstChildRequest.messages.some((message) => textOf(message).includes("permission scope was fixed")));
    assert.equal(firstChildRequest.messages.some((message) => textOf(message) === "START_BACKGROUND"), false, "spawn starts with a standalone prompt, without parent conversation history");

    const followup = (text: string) => rpc("subagent.prompt", { ...address, content: [{ type: "text", text }] });
    await followup("FOLLOWUP_ONE");
    await waitFor("follow-up output", () => requested.get(childId)?.some((request) => request.messages.some((message) => textOf(message) === "FOLLOWUP_ONE")) ?? false);
    await waitFor("second child settlement", () => parentSources().filter((source) => source.kind === "subagent-settled").length === 2);
    await parent.whenIdle();
    assert.ok(JSON.stringify(await rpc("subagent.history", address)).includes("FOLLOWUP_RESULT: FOLLOWUP_ONE"));
    const otherId = (await rpc("session.create", { cwd: root })).sessionId;
    const foreignAddress = { ...address, parentSessionId: otherId };
    assert.equal((await rawRpc("subagent.prompt", { ...foreignAddress, content: [{ type: "text", text: "unauthorized" }] })).ok, false);
    await followup("BLOCK_UNTIL_INTERRUPT");
    await waitFor("blocking child request", () => blocked.has(childId));
    assert.equal((await rawRpc("session.prompt", { sessionId: childId, mode: "queue", content: [{ type: "text", text: "wrong route" }] })).ok, false);
    assert.equal((await rawRpc("session.cancel", { sessionId: childId })).ok, false);
    const foreignStop = await rawRpc("subagent.interrupt", foreignAddress);
    assert.equal(foreignStop.ok, false);
    assert.equal(foreignStop.error?.code, "subagent-unauthorized");
    assert.equal((await rpc("subagent.interrupt", address)).accepted, true);
    await waitFor("interrupted child settlement", () => parentSources().filter((source) => source.kind === "subagent-settled").length === 3);
    await parent.whenIdle();
    assert.ok(JSON.stringify(await rpc("subagent.history", address)).includes("aborted"));
    await followup("FOLLOWUP_AFTER_INTERRUPT");
    await waitFor("post-interrupt settlement", () => parentSources().filter((source) => source.kind === "subagent-settled").length === 4);
    await parent.whenIdle();
    assert.ok(JSON.stringify(await rpc("subagent.history", address)).includes("FOLLOWUP_RESULT: FOLLOWUP_AFTER_INTERRUPT"));

    await promptParent("START_FOREGROUND");
    await waitFor("foreground result in parent", () => parent.session.events.some((event) => event.type === "tool/result" && JSON.stringify(event.data).includes("FOREGROUND_RESULT")));
    await parent.whenIdle();
    const allChildren = (await rpc("subagent.list", { parentSessionId: parentId })).entries;
    const oneShot = allChildren.find((entry: any) => entry.mode === "one-shot");
    assert.ok(oneShot, "foreground subagent is cataloged as one-shot");
    assert.equal(requested.get(oneShot.id)![0].tools?.some((tool) => tool.name === "report"), false, "one-shot children return a result and carry no report capability");
    assert.ok(JSON.stringify(await rpc("subagent.history", { parentSessionId: parentId, childSessionId: oneShot.id, mode: "one-shot" })).includes("FOREGROUND_RESULT"));
    assert.equal(parentSources().filter((source) => source.kind === "subagent-settled").length, 4, "foreground output returns through its tool, not a continuable notice");
    assert.equal((await rawRpc("subagent.prompt", { parentSessionId: parentId, childSessionId: oneShot.id, mode: "continuable", content: [{ type: "text", text: "invalid continuation" }] })).ok, false);

    await stop();
    stop = undefined;
    booted = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    stop = booted.dispose;
    ctx = booted.ctx;
    base = `http://127.0.0.1:${ctx.webServer.port}`;
    installAdapter();
    const coldCount = countAgents();
    const coldCatalog = await rpc("subagent.list", { parentSessionId: parentId });
    assert.equal(coldCatalog.parentAvailable, false);
    assert.ok(coldCatalog.entries.some((entry: any) => entry.id === childId && entry.mode === "continuable"));
    assert.ok(JSON.stringify(await rpc("subagent.history", address)).includes("FOLLOWUP_AFTER_INTERRUPT"));
    assert.equal(countAgents(), coldCount, "cold catalog and history remain read-only");
    const coldSend = await rawRpc("subagent.prompt", { ...address, content: [{ type: "text", text: "FOLLOWUP_COLD" }] });
    assert.equal(coldSend.error?.code, "subagent-parent-unavailable");
    assert.equal((await rpc("session.create", { sessionId: parentId, cwd: root, agentPreset: "kairos" })).sessionId, parentId);
    assert.equal((await rpc("subagent.list", { parentSessionId: parentId })).parentAvailable, true);
    await followup("FOLLOWUP_COLD_RESUMED");
    const restoredParent = ctx.agents.get(parentId)!;
    await waitFor("cold-resumed child settlement", () => restoredParent.session.events.some((event) => event.type === "user/message"
      && sourceOf(event.data as { source?: unknown }).kind === "subagent-settled" && JSON.stringify(event.data).includes("FOLLOWUP_COLD_RESUMED")));
    await restoredParent.whenIdle();
    assert.ok(JSON.stringify(await rpc("subagent.history", address)).includes("FOLLOWUP_RESULT: FOLLOWUP_COLD_RESUMED"));
  } finally {
    await stop?.();
    await Promise.all([rm(bots, { recursive: true, force: true }), rm(root, { recursive: true, force: true }), rm(home, { recursive: true, force: true })]);
  }
});
