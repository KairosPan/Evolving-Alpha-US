import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { isSubagentRow, normalizeSubagentCatalog, subagentAddress, subagentControls, subagentResult } from "../client/subagents.js";

const catalog = { parentAvailable: true, entries: [
  { kind: "child", id: "live", label: "核查", mode: "continuable", activity: "running", hasChildren: true },
  { kind: "child", id: "once", mode: "one-shot", activity: "inactive" },
  { kind: "diagnostic", id: "broken", reason: "corrupt" },
] };

test("subagents remain separate from room members and ordinary forks", () => {
  assert.equal(isSubagentRow({ parentSessionId: "p", agentPreset: "bot" }), false);
  assert.equal(isSubagentRow({ parentSessionId: "p", agentPreset: "kairos" }), false);
  assert.equal(isSubagentRow({ origin: "subagent", parentSessionId: "p" }), true);
});
test("catalog keeps diagnostics and makes unknown schemas visible but uncontrollable", () => {
  const normalized = normalizeSubagentCatalog({ parentAvailable: false, entries: [...catalog.entries,
    { kind: "child", id: "bad", mode: "continuable" }, { kind: "child", id: "live", mode: "one-shot" }, null] });
  assert.equal(normalized.parentAvailable, false);
  assert.equal(normalized.entries.length, 4);
  assert.deepEqual(normalized.entries[3], { kind: "diagnostic", id: "bad", reason: "unsupported" });
});
test("malformed catalog is unavailable, never an empty successful listing", () => {
  for (const value of [null, {}, { entries: [], parentAvailable: 1 }, { parentAvailable: false }]) assert.throws(() => normalizeSubagentCatalog(value), /目录不可用/);
});
test("unknown activity stays unknown, not inactive", () => {
  const row = normalizeSubagentCatalog({ parentAvailable: true, entries: [{ kind: "child", id: "unknown", mode: "one-shot" }] }).entries[0];
  assert.equal(subagentControls(row, true).state, "运行状态未知");
});
test("only a healthy catalog child yields a durable direct-parent address", () => {
  assert.deepEqual(subagentAddress("p", "live", catalog), { parentSessionId: "p", childSessionId: "live", mode: "continuable" });
  assert.equal(subagentAddress("p", "broken", catalog), null);
  assert.equal(subagentAddress("p", "missing", catalog), null);
  assert.equal(subagentAddress("live", "live", catalog), null);
});
test("inactive never means completed; one-shot remains read-only", () => {
  const state = subagentControls(catalog.entries[1], true);
  assert.equal(state.state, "未运行");
  assert.equal(state.canRead, true);
  assert.equal(state.canPrompt, false);
  assert.equal(state.canInterrupt, false);
});
test("cold parent disables continuation while allowing reads and live interrupt", () => {
  const state = subagentControls(catalog.entries[0], false);
  assert.equal(state.canRead, true);
  assert.equal(state.canPrompt, false);
  assert.equal(state.canInterrupt, true);
  assert.match(state.note, /父会话未加载/);
  assert.equal(subagentControls(catalog.entries[0], true, true).state, "等待你的回应");
});
test("diagnostics never enable controls", () => {
  assert.deepEqual(subagentControls(catalog.entries[2], true), { canRead: false, canPrompt: false, canInterrupt: false, state: "记录不可用 · corrupt", note: "保留记录，无法读取或续派。" });
});
test("last recorded output skips tool-only messages and marks interrupted prefixes", () => {
  const entry = (text: string, interrupted = false) => ({ event: { type: "assistant/message", data: { message: { content: [{ type: "text", text }] }, interrupted } } });
  assert.deepEqual(subagentResult([entry("first"), entry("partial", true), { event: { type: "turn/end" } }]), { text: "partial", interrupted: true });
  assert.equal(subagentResult([]), null);
});

// Execute the production async controller functions with a real deferred RPC
// boundary. Parsing only removes unrelated DOM startup; none of the routing,
// catalog recovery or draft ownership logic is recreated by the harness.
const chatSource = ts.createSourceFile("chat.js", readFileSync(new URL("../client/chat.js", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
function subagentClient(rpc: (method: string, payload: any) => Promise<any>) {
  const input = { value: "请继续核查这个结论" };
  const errors: unknown[] = [];
  const notices: string[] = [];
  const context = vm.createContext({
    activeSession: "child", openSeq: 1, subagentRefreshSeq: 0, subagentInfoError: "",
    lastSessions: [{ sessionId: "child", origin: "subagent", parentSessionId: "parent" }],
    subagentCatalogs: new Map(), subagentAddresses: new Map(), subagentParents: new Map(), subagentCatalogReads: new Map(),
    isSubagentRow, normalizeSubagentCatalog, subagentAddress, subagentControls,
    rpc, $: () => input, timeZone: () => "UTC", renderSubagents: () => {},
    status: (text: string) => notices.push(text), failed: (error: unknown) => errors.push(error),
  });
  const names = new Set(["activeSubagent", "isSubagentSession", "childRow", "readSubagentCatalog", "resolveSubagentAddress", "loadSubagentInfo", "send"]);
  const declarations = chatSource.statements.filter((node): node is ts.FunctionDeclaration => ts.isFunctionDeclaration(node) && names.has(node.name?.text ?? ""));
  assert.equal(declarations.length, names.size, "the test loads every production controller function");
  vm.runInContext(declarations.map((node) => node.getText(chatSource)).join("\n"), context);
  return { context, input, errors, notices };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("a deferred child lookup failure never restores its instruction into another conversation", async () => {
  for (const destination of ["other", null, "child"]) {
    const pending = deferred<unknown>();
    const calls: string[] = [];
    const ui = subagentClient(async (method) => { calls.push(method); return pending.promise; });
    const sending = ui.context.send();
    assert.equal(ui.input.value, "");
    assert.deepEqual(calls, ["subagent.list"]);
    // The last case navigates away and back to the same child: its new view
    // still must not inherit the abandoned view's in-flight draft recovery.
    ui.context.activeSession = destination;
    ui.context.openSeq += 1;
    pending.reject(new Error("parent catalog unavailable"));
    await sending;
    assert.equal(ui.input.value, "");
    assert.equal(ui.errors.length, 0, "the abandoned view cannot replace the new view's status either");
    assert.deepEqual(calls, ["subagent.list"], "no session or room write fallback");
  }
});

test("the submitting child view still recovers a failed draft without replacing newly typed text", async () => {
  for (const nextDraft of ["", "新的指令"]) {
    const pending = deferred<unknown>();
    const ui = subagentClient(async () => pending.promise);
    const sending = ui.context.send();
    ui.input.value = nextDraft;
    pending.reject(new Error("temporary lookup failure"));
    await sending;
    assert.equal(ui.input.value, nextDraft || "请继续核查这个结论");
    assert.equal(ui.errors.length, 1);
  }
});

test("refresh recovers a first sidebar child open whose parent catalog failed before identity was cached", async () => {
  const firstRead = deferred<unknown>();
  const calls: string[] = [];
  let parentReads = 0;
  const ui = subagentClient(async (method, payload) => {
    calls.push(`${method}:${payload.parentSessionId}`);
    assert.equal(method, "subagent.list", "refresh must remain read-only");
    if (payload.parentSessionId === "parent" && ++parentReads === 1) return firstRead.promise;
    if (payload.parentSessionId === "child") return { entries: [], parentAvailable: false };
    return { parentAvailable: true, entries: [{ kind: "child", id: "child", label: "恢复任务", mode: "continuable", activity: "inactive" }] };
  });
  const opening = ui.context.resolveSubagentAddress("child");
  firstRead.reject(new Error("temporary catalog failure"));
  await assert.rejects(opening, /temporary catalog failure/);
  assert.equal(ui.context.subagentParents.size, 0);
  assert.equal(ui.context.subagentAddresses.size, 0);
  ui.context.subagentInfoError = "temporary catalog failure";
  await ui.context.loadSubagentInfo();
  assert.deepEqual(calls, ["subagent.list:parent", "subagent.list:child", "subagent.list:parent"]);
  assert.equal(ui.context.subagentInfoError, "");
  assert.equal(ui.context.activeSubagent().parentSessionId, "parent");
  assert.equal(ui.context.activeSubagent().mode, "continuable");
  assert.equal(ui.context.subagentCatalogs.get("parent").parentAvailable, true);
});
