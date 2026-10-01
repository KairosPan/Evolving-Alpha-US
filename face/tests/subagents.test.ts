import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { composeSubagentCatalog, isSubagentRow, normalizeSubagentCatalog, subagentAddress, subagentControls, subagentResult } from "../client/subagents.js";

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
  // 0.2 page records are `{type:'event', event}` (session-controller src/types.ts:425-429).
  const entry = (text: string, interrupted = false) => ({ type: "event", event: { type: "assistant/message", data: { message: { content: [{ type: "text", text }] }, interrupted } } });
  assert.deepEqual(subagentResult([entry("first"), entry("partial", true), { type: "event", event: { type: "turn/end" } }]), { text: "partial", interrupted: true });
  assert.equal(subagentResult([]), null);
});

/* ---------- composing 0.1.1's `subagent.list` from what 0.2 serves ---------- */

/** The parent's `subagentCatalog` projection value (NEW subagent src/projection-types.ts:9-19). */
const projected = [
  { id: "live", createdAt: 1, mode: "continuable", label: "核查" },
  { id: "once", createdAt: 2, mode: "one-shot" },
  { id: "legacy", createdAt: 3, mode: "unknown" },
  { id: "cold", createdAt: 4, mode: "continuable", label: "冷任务" },
];
/** `session/list` rows (0.2 SessionSummary). */
const rows = [
  { sessionId: "parent", agentAvailable: true, running: false },
  { sessionId: "live", origin: "subagent", parentSessionId: "parent", agentAvailable: true, running: true },
  { sessionId: "once", origin: "subagent", parentSessionId: "parent", agentAvailable: false, running: false },
  { sessionId: "grandchild", origin: "subagent", parentSessionId: "live", agentAvailable: false, running: false },
  { sessionId: "fork", parentSessionId: "once", agentPreset: "kairos" }, // a fork, not a subagent: not a child of `once`
];

test("compose: catalog order, modes and labels; activity from the child's running row; hasChildren from subagent rows", () => {
  const composed = composeSubagentCatalog({ catalog: projected, parentSummary: rows[0], rows });
  assert.equal(composed.parentAvailable, true);
  assert.deepEqual(composed.entries, [
    { kind: "child", id: "live", mode: "continuable", label: "核查", activity: "running", hasChildren: true },
    { kind: "child", id: "once", mode: "one-shot", activity: "inactive", hasChildren: false },
    { kind: "diagnostic", id: "legacy", reason: "unsupported" },
    { kind: "child", id: "cold", mode: "continuable", label: "冷任务", hasChildren: false },
  ]);
});

test("compose → normalize keeps every 0.1.1 decision: unknown mode is a diagnostic, an unlisted child's activity is unknown", () => {
  const normalized = normalizeSubagentCatalog(composeSubagentCatalog({ catalog: projected, parentSummary: rows[0], rows }));
  assert.deepEqual(normalized.entries.map((e) => `${e.id}:${e.kind}:${e.activity ?? e.reason}`), [
    "live:child:running", "once:child:inactive", "legacy:diagnostic:unsupported", "cold:child:unknown",
  ]);
  assert.deepEqual(subagentAddress("parent", "live", normalized), { parentSessionId: "parent", childSessionId: "live", mode: "continuable" });
  assert.equal(subagentAddress("parent", "legacy", normalized), null, "an unknown-mode child is never controllable");
  assert.equal(subagentControls(normalized.entries[3], true).state, "运行状态未知");
});

test("compose: parent availability is the parent row's agentAvailable, and an unlisted parent is not available", () => {
  assert.equal(composeSubagentCatalog({ catalog: [], parentSummary: { sessionId: "p", agentAvailable: false }, rows }).parentAvailable, false);
  assert.equal(composeSubagentCatalog({ catalog: [], parentSummary: undefined, rows }).parentAvailable, false);
});

test("compose: an absent projection is no children; a present non-list is unavailable, never an empty listing", () => {
  assert.deepEqual(composeSubagentCatalog({ catalog: undefined, parentSummary: rows[0], rows }), { entries: [], parentAvailable: true });
  for (const bad of [null, {}, "live", 3]) {
    assert.throws(() => composeSubagentCatalog({ catalog: bad, parentSummary: rows[0], rows }), /目录不可用/);
  }
  const skipped = composeSubagentCatalog({ catalog: [null, { mode: "one-shot" }, { id: "", mode: "one-shot" }, projected[1]], parentSummary: rows[0], rows });
  assert.deepEqual(skipped.entries.map((e) => e.id), ["once"], "malformed rows are skipped as normalize skips them");
});

// Execute the production async controller functions with a real deferred call
// boundary. Parsing only removes unrelated DOM startup; none of the routing,
// catalog recovery or draft ownership logic is recreated by the harness.
const chatSource = ts.createSourceFile("chat.js", readFileSync(new URL("../client/chat.js", import.meta.url), "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
type Call = (endpoint: string, args: any) => Promise<any>;
const DEFAULT_ROWS = [
  { sessionId: "child", origin: "subagent", parentSessionId: "parent", agentAvailable: false, running: false },
  { sessionId: "parent", agentAvailable: true, running: false },
];
function subagentClient(call: Call, lastSessions: unknown[] = DEFAULT_ROWS) {
  const input = { value: "请继续核查这个结论" };
  const errors: unknown[] = [];
  const notices: string[] = [];
  const context = vm.createContext({
    activeSession: "child", openSeq: 1, subagentRefreshSeq: 0, subagentInfoError: "",
    lastSessions,
    subagentCatalogs: new Map(), subagentAddresses: new Map(), subagentParents: new Map(), subagentCatalogReads: new Map(),
    isSubagentRow, normalizeSubagentCatalog, composeSubagentCatalog, subagentAddress, subagentControls,
    call, $: () => input, timeZone: () => "UTC", newRequestId: () => "req-1", renderSubagents: () => {},
    syncSubagentComposer: () => {}, SUBAGENT_OUTPUT_MESSAGES: 12,
    status: (text: string) => notices.push(text), failed: (error: unknown) => errors.push(error),
  });
  const names = new Set(["activeSubagent", "isSubagentSession", "childRow", "readSubagentCatalog", "resolveSubagentAddress", "loadSubagentInfo", "send", "interruptSubagent", "readChildTail"]);
  const declarations = chatSource.statements.filter((node): node is ts.FunctionDeclaration => ts.isFunctionDeclaration(node) && names.has(node.name?.text ?? ""));
  assert.equal(declarations.length, names.size, "the test loads every production controller function");
  vm.runInContext(declarations.map((node) => node.getText(chatSource)).join("\n"), context);
  return { context, input, errors, notices };
}
/** The JSON the call would carry: objects built inside the vm realm have that realm's
 * prototypes, and what matters about an argument is exactly its wire form anyway. */
const wire = (value: unknown): unknown => JSON.parse(JSON.stringify(value));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
/** A host whose parent catalog lists `child` continuable, and whose child has no children. */
const catalogHost = (calls: string[] = []): Call => async (endpoint, args) => {
  calls.push(`${endpoint}:${args?.request?.sessionId ?? args?.childSessionId ?? ""}`);
  if (endpoint === "session/projections" && args.request.sessionId === "parent") {
    return { asOfSeq: 9, values: { subagentCatalog: [{ id: "child", createdAt: 1, mode: "continuable", label: "恢复任务" }] } };
  }
  if (endpoint === "session/projections") return { asOfSeq: 3, values: { subagentCatalog: [] } };
  if (endpoint === "session/page") return { records: [], hasMore: false };
  return { accepted: true };
};

test("a deferred child lookup failure never restores its instruction into another conversation", async () => {
  for (const destination of ["other", null, "child"]) {
    const pending = deferred<unknown>();
    const calls: string[] = [];
    const ui = subagentClient(async (endpoint) => { calls.push(endpoint); return pending.promise; });
    const sending = ui.context.send();
    assert.equal(ui.input.value, "");
    assert.deepEqual(calls, ["session/projections"]);
    // The last case navigates away and back to the same child: its new view
    // still must not inherit the abandoned view's in-flight draft recovery.
    ui.context.activeSession = destination;
    ui.context.openSeq += 1;
    pending.reject(new Error("parent catalog unavailable"));
    await sending;
    assert.equal(ui.input.value, "");
    assert.equal(ui.errors.length, 0, "the abandoned view cannot replace the new view's status either");
    assert.deepEqual(calls, ["session/projections"], "no session or room write fallback");
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
  const ui = subagentClient(async (endpoint, args) => {
    const sessionId = args.request.sessionId;
    calls.push(`${endpoint}:${sessionId}`);
    // A projections read never activates the session it reads (NEW session-controller src/index.ts:490-512).
    assert.equal(endpoint, "session/projections", "refresh must remain read-only");
    if (sessionId === "parent" && ++parentReads === 1) return firstRead.promise;
    if (sessionId === "child") return { asOfSeq: 3, values: { subagentCatalog: [] } };
    return { asOfSeq: 9, values: { subagentCatalog: [{ id: "child", createdAt: 1, mode: "continuable", label: "恢复任务" }] } };
  });
  const opening = ui.context.resolveSubagentAddress("child");
  firstRead.reject(new Error("temporary catalog failure"));
  await assert.rejects(opening, /temporary catalog failure/);
  assert.equal(ui.context.subagentParents.size, 0);
  assert.equal(ui.context.subagentAddresses.size, 0);
  ui.context.subagentInfoError = "temporary catalog failure";
  await ui.context.loadSubagentInfo();
  assert.deepEqual(calls, ["session/projections:parent", "session/projections:child", "session/projections:parent"]);
  assert.equal(ui.context.subagentInfoError, "");
  assert.equal(ui.context.activeSubagent().parentSessionId, "parent");
  assert.equal(ui.context.activeSubagent().mode, "continuable");
  assert.equal(ui.context.subagentCatalogs.get("parent").parentAvailable, true, "from the parent's list row");
});

test("a parent the host does not know (projections null) is an unavailable catalog, never an empty one", async () => {
  const ui = subagentClient(async () => null);
  await assert.rejects(ui.context.readSubagentCatalog("parent"), /父会话不存在/);
  const bad = subagentClient(async () => ({ asOfSeq: 1 }));
  await assert.rejects(bad.context.readSubagentCatalog("parent"), /无效记录/);
});

test("a continued instruction to a child is one subagents/prompt with a minted requestId and queue delivery", async () => {
  const sent: { endpoint: string; args: any }[] = [];
  const host = catalogHost();
  const ui = subagentClient(async (endpoint, args) => { sent.push({ endpoint, args }); return host(endpoint, args); });
  await ui.context.send();
  const prompt = sent.find((c) => c.endpoint === "subagents/prompt");
  assert.ok(prompt, `sent: ${sent.map((c) => c.endpoint).join(", ")}`);
  // NEW packages/subagent/subagent/src/control-types.ts:85-102: requestId and delivery are required.
  assert.deepEqual(wire(prompt.args), { request: {
    requestId: "req-1", parentSessionId: "parent", childSessionId: "child", mode: "continuable",
    delivery: "queue", content: [{ type: "text", text: "请继续核查这个结论" }], clientTimeZone: "UTC",
  } });
  assert.equal(ui.errors.length, 0);
});

test("an interrupt is three positional wire keys with the literal continuable mode; a one-shot address is refused unsent", async () => {
  const sent: { endpoint: string; args: any }[] = [];
  const host = catalogHost();
  const ui = subagentClient(async (endpoint, args) => { sent.push({ endpoint, args }); return host(endpoint, args); });
  const button = { disabled: false, id: "", isConnected: true };
  await ui.context.interruptSubagent({ parentSessionId: "parent", childSessionId: "child", mode: "continuable" }, button);
  const interrupt = sent.find((c) => c.endpoint === "subagents/interruptByParent");
  assert.deepEqual(wire(interrupt?.args), { childSessionId: "child", parentSessionId: "parent", mode: "continuable" });
  assert.equal(button.disabled, false, "the button comes back");
  const before = sent.length;
  await ui.context.interruptSubagent({ parentSessionId: "parent", childSessionId: "child", mode: "one-shot" }, button);
  assert.equal(sent.length, before, "nothing was sent for a read-only child");
  assert.equal(ui.errors.length, 1);
});

test("a child's latest output is read without activating it: its projections cut, then one page on its subagent address", async () => {
  const sent: { endpoint: string; args: any }[] = [];
  const host = catalogHost();
  const ui = subagentClient(async (endpoint, args) => { sent.push({ endpoint, args }); return host(endpoint, args); });
  const records = await ui.context.readChildTail({ parentSessionId: "parent", childSessionId: "child", mode: "one-shot" });
  assert.deepEqual(wire(records), []);
  assert.deepEqual(sent.map((c) => c.endpoint), ["session/projections", "session/page"], "never session/follow, never a prompt");
  assert.deepEqual(wire(sent[1]!.args), { request: {
    address: { kind: "subagent", parentSessionId: "parent", childSessionId: "child", mode: "one-shot" },
    throughSeq: 3, maxMessages: 12,
  } });
  const gone = subagentClient(async () => null);
  await assert.rejects(gone.context.readChildTail({ parentSessionId: "parent", childSessionId: "x", mode: "one-shot" }), /不存在/);
});

/* ---------- chat.js: how the session on screen is READ (follow vs page) ----------
 *
 * The same production-function harness, over the view controller. What it pins:
 *  - a session born from the composer is followed BEFORE it is prompted, or its
 *    reply never renders (0.2 has no all-session feed: critique WC-F1);
 *  - a COLD ordinary session is only paged - `session/projections` +
 *    `session/page`, never `session/follow`, whose snapshot promotes a cold
 *    session into an irreversible write-open (remediation SC-F2; NEW
 *    session-controller src/history.ts:204-212);
 *  - it is followed as soon as it is live, a follow is stopped when the host says
 *    the session left the registry, and a socket drop suspends it for re-decision. */

type Wire = { log: string[]; opens: { endpoint: string; args: any; handlers: any; cancelled: boolean }[] };
/** A mux whose streams only record: `open:<endpoint>:<address id>` and `cancel:…`. */
function fakeMux(wireLog: Wire) {
  return {
    stream(endpoint: string, args: any, handlers: any) {
      const id = args?.request?.address?.sessionId ?? args?.request?.address?.childSessionId ?? "";
      const entry = { endpoint, args, handlers, cancelled: false };
      wireLog.opens.push(entry);
      wireLog.log.push(`open:${endpoint}:${id}`);
      return { cancel() { entry.cancelled = true; wireLog.log.push(`cancel:${endpoint}:${id}`); } };
    },
    answer: async () => {},
  };
}
function viewClient(rows: Record<string, unknown>[], extra: Record<string, unknown> = {}) {
  const wireLog: Wire = { log: [], opens: [] };
  const snapshots: { id: string; snapshot: any }[] = [];
  const failures: unknown[] = [];
  const call: Call = async (endpoint, args) => {
    wireLog.log.push(`call:${endpoint}`);
    if (endpoint === "session/create") return { sessionId: "fresh", agentPreset: "kairos" };
    if (endpoint === "session/projections") return { asOfSeq: 7, values: { title: "t" } };
    if (endpoint === "session/page") return { records: [{ type: "event", event: { seq: 7, type: "turn/end", data: { turn: 1 } } }], hasMore: false };
    if (endpoint === "commands/execute") return undefined;
    return { accepted: true };
  };
  const input = { value: "hello" };
  const context = vm.createContext({
    activeSession: null, activeView: null, openSeq: 1, loadingSession: null,
    lastSessions: rows, pendingWorkspaceId: undefined, pendingCwd: undefined, pendingAgentPreset: undefined,
    FOLLOW_RETRY_MS: 5, mux: fakeMux(wireLog), call, $: () => input, timeZone: () => "UTC", newRequestId: () => "req-1",
    // Collaborators outside the controller: recorded or inert.
    applySnapshot: async (id: string, _token: number, snapshot: unknown) => { snapshots.push({ id, snapshot }); },
    openFailed: (_id: string, err: unknown) => failures.push(err), acceptFrame: () => {},
    setSpeaker: () => {}, refreshSessions: async () => {}, markActive: () => {}, loadRoomInfo: async () => {},
    flow: () => ({ querySelector: () => null }), isMentionText: () => false, channelOf: () => null,
    panelData: async () => ({}), isSubagentSession: () => false, status: () => {}, failed: (err: unknown) => failures.push(err),
    closeDetail: () => {}, resetFlow: () => {}, resolveSubagentAddress: async () => { throw new Error("not a child"); },
    setSubagentSpeaker: () => {},
    ...extra,
  });
  const names = new Set(["send", "openSession", "viewSession", "isLiveSession", "followPromotes", "followActive", "pageActive",
    "closeActiveView", "reconcileActiveView", "stopFollowing", "suspendFollows", "revived", "patchSession", "liveMux"]);
  const declarations = chatSource.statements.filter((node): node is ts.FunctionDeclaration => ts.isFunctionDeclaration(node) && names.has(node.name?.text ?? ""));
  assert.equal(declarations.length, names.size, "the test loads every production view function");
  vm.runInContext(declarations.map((node) => node.getText(chatSource)).join("\n"), context);
  // suspendFollows also stops member follows; none are open in these cases.
  context.memberFollows = new Map();
  return { context, wireLog, snapshots, failures, input };
}

test("a new conversation is followed before its first prompt, or its reply would never render", async () => {
  const ui = viewClient([]);
  await ui.context.send();
  assert.deepEqual(ui.wireLog.log, ["call:session/create", "open:session/follow:fresh", "call:session/prompt"]);
  assert.deepEqual(wire(ui.wireLog.opens[0]!.args), { request: { address: { kind: "session", sessionId: "fresh" }, assistantStream: true } });
  assert.equal(ui.context.loadingSession, "fresh", "other streams' frames hold until the snapshot is drawn");
  assert.equal(ui.context.activeView.mode, "follow");
  assert.equal(ui.failures.length, 0);
});

test("opening a COLD session pages it without activating it: projections + page, never a follow", async () => {
  const ui = viewClient([{ sessionId: "cold", agentAvailable: false, running: false }]);
  await ui.context.openSession("cold");
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(ui.wireLog.log, ["call:session/projections", "call:session/page"], "nothing that could promote it");
  assert.equal(ui.wireLog.opens.length, 0);
  assert.equal(ui.context.activeView.mode, "page");
  assert.equal(ui.snapshots.length, 1, "the paged window is drawn like a snapshot");
  assert.deepEqual(wire(ui.snapshots[0]!.snapshot), {
    projections: { asOfSeq: 7, values: { title: "t" } },
    records: [{ type: "event", event: { seq: 7, type: "turn/end", data: { turn: 1 } } }],
  });
  // An unlisted session is not known to be live either: paged, not followed.
  const unknown = viewClient([]);
  await unknown.context.openSession("ghost");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(unknown.wireLog.opens.length, 0);
});

test("opening a LIVE session follows it, with the assistant stream for its pulses", async () => {
  const ui = viewClient([{ sessionId: "live", agentAvailable: true, running: true }]);
  await ui.context.openSession("live");
  assert.deepEqual(ui.wireLog.log, ["open:session/follow:live"]);
  assert.deepEqual(wire(ui.wireLog.opens[0]!.args), { request: { address: { kind: "session", sessionId: "live" }, assistantStream: true } });
  assert.equal(ui.context.activeView.mode, "follow");
});

test("a paged session is followed once this tab prompts it, and the follow's snapshot replaces the window", async () => {
  const rows = [{ sessionId: "cold", agentAvailable: false, running: false }];
  const ui = viewClient(rows);
  await ui.context.openSession("cold");
  await new Promise((resolve) => setImmediate(resolve));
  ui.context.loadingSession = null; // the paged window was drawn (applySnapshot is recorded, not run)
  ui.input.value = "continue";
  await ui.context.send();
  assert.deepEqual(ui.wireLog.log, ["call:session/projections", "call:session/page", "call:session/prompt", "open:session/follow:cold"],
    "the prompt resumed it (session-controller commands.ts:311-330), so following now activates nothing");
  assert.equal(ui.context.activeView.mode, "follow");
});

test("a paged session the host reports alive is followed; one it reports gone stops being followed", async () => {
  const ui = viewClient([{ sessionId: "s", agentAvailable: false, running: false }]);
  await ui.context.openSession("s");
  await new Promise((resolve) => setImmediate(resolve));
  ui.context.lastSessions = [{ sessionId: "s", agentAvailable: true, running: true }];
  ui.context.reconcileActiveView();
  assert.equal(ui.context.activeView.mode, "follow");
  assert.equal(ui.wireLog.log.at(-1), "open:session/follow:s");
  // `api-session/removed`: a later re-open would promote it, so the follow stops; the window stays.
  ui.context.stopFollowing("s");
  assert.equal(ui.context.activeView.mode, "page");
  assert.equal(ui.wireLog.log.at(-1), "cancel:session/follow:s");
  // A stale list answer never downgrades a live follow by itself.
  ui.context.lastSessions = [{ sessionId: "s", agentAvailable: true }];
  ui.context.reconcileActiveView();
  ui.context.lastSessions = [{ sessionId: "s", agentAvailable: false }];
  const opens = ui.wireLog.opens.length;
  ui.context.reconcileActiveView();
  assert.equal(ui.context.activeView.mode, "follow");
  assert.equal(ui.wireLog.opens.length, opens);
});

test("a socket drop suspends a session follow; the fresh list decides follow (live) or re-page (went cold)", async () => {
  for (const [liveAfter, expected] of [[true, "open:session/follow:s"], [false, "call:session/page"]] as const) {
    const ui = viewClient([{ sessionId: "s", agentAvailable: true, running: false }]);
    await ui.context.openSession("s");
    ui.context.suspendFollows();
    assert.equal(ui.wireLog.log.at(-1), "cancel:session/follow:s", "nothing left for the mux to re-open blindly");
    assert.equal(ui.context.activeView.stale, true);
    ui.context.lastSessions = [{ sessionId: "s", agentAvailable: liveAfter }];
    ui.context.reconcileActiveView();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(ui.wireLog.log.at(-1), expected);
  }
});

test("a follow the host refuses is reported once and never retried behind the operator's back", async () => {
  const ui = viewClient([{ sessionId: "s", agentAvailable: true }]);
  await ui.context.openSession("s");
  ui.wireLog.opens[0]!.handlers.onError({ code: "session/not-found", message: "gone", details: {} });
  assert.equal(ui.failures.length, 1);
  const opens = ui.wireLog.opens.length;
  ui.context.reconcileActiveView();
  assert.equal(ui.wireLog.opens.length, opens);
  assert.equal(ui.context.activeView.failed, true);
});

/* ---------- chat.js: gates across reconnects (the reload/replay path) ----------
 *
 * The host replays every still-pending gate to a new `$events` generation,
 * after its `ready`, under the SAME eventId (NEW gateway src/index.ts:512-516);
 * a gate settled while this page was away gets no `cancel` here
 * (index.ts:640-644, 657-668), and an answer to it would be a silent no-op `ok`
 * (:618-621). So: replays dedupe by eventId, a gate the new generation did not
 * re-deliver is retired as closed, and a `cancel` that reaches the ANSWERING
 * tab means its answer lost the race (the winner gets no cancel, :622). */

/** A card as the gate logic touches it: settle() is recorded, not drawn. */
function fakeCard() {
  const classes = new Set<string>();
  return { isConnected: true, classes, classList: { contains: (c: string) => classes.has(c) }, querySelectorAll: () => [] };
}
function gateClient() {
  const settled: { node: unknown; outcome: string; verb: string }[] = [];
  const rendered: string[] = [];
  const context = vm.createContext({
    gates: new Map(), gateNodes: new Map(), gateDelivery: new Map(), answering: new Set(), lostRaces: new Set(),
    eventsGeneration: 1, activeSession: "s", convRows: new Map(),
    renderGate: (view: { id: string }) => rendered.push(view.id), renderStrip: () => {}, scheduleListRefresh: () => {},
    memberSessionIds: () => new Set(), waitingChip: () => ({}), status: () => {},
    settle: (node: { classes: Set<string> }, outcome: string, verb = "answered") => { node.classes.add("answered"); settled.push({ node, outcome, verb }); },
  });
  const names = new Set(["acceptGate", "acceptGateResolved", "purgeUndeliveredGates", "gateIsLive", "closeStaleGate"]);
  const declarations = chatSource.statements.filter((node): node is ts.FunctionDeclaration => ts.isFunctionDeclaration(node) && names.has(node.name?.text ?? ""));
  assert.equal(declarations.length, names.size, "the test loads every production gate function");
  vm.runInContext(declarations.map((node) => node.getText(chatSource)).join("\n"), context);
  /** What the mux wiring does on delivery: record the generation, then accept. */
  const deliver = (id: string) => {
    context.gateDelivery.set(id, context.eventsGeneration);
    context.acceptGate({ kind: "approval", id, sessionId: "s", toolName: "mcp__alpaca-kit__place_order" });
  };
  return { context, settled, rendered, deliver };
}

test("gates: a replay after a reconnect is the same gate (keyed by eventId), and it stays answerable", () => {
  const ui = gateClient();
  ui.deliver("ev-1");
  ui.context.eventsGeneration = 2; // the socket dropped; a new `ready`
  ui.deliver("ev-1");
  assert.equal(ui.context.gates.size, 1, "one pending gate, not two");
  assert.equal(ui.context.gateIsLive({ id: "ev-1" }), true, "re-delivered to this generation: an answer can land");
  ui.context.purgeUndeliveredGates(2);
  assert.equal(ui.context.gates.has("ev-1"), true);
});

test("gates: one the new generation did not re-deliver was settled while away - retired closed, never answerable", () => {
  const ui = gateClient();
  ui.deliver("ev-live");
  ui.deliver("ev-gone");
  const card = fakeCard();
  ui.context.gateNodes.set("ev-gone", card);
  ui.context.eventsGeneration = 2;
  ui.deliver("ev-live");
  assert.equal(ui.context.gateIsLive({ id: "ev-gone" }), false, "an answer to it would be a silent no-op ok");
  ui.context.purgeUndeliveredGates(2);
  assert.deepEqual([...ui.context.gates.keys()], ["ev-live"]);
  assert.deepEqual(ui.settled.map((s) => `${s.verb} · ${s.outcome}`), ["closed · closed"]);
  assert.equal(ui.context.gateNodes.has("ev-gone"), false, "a later re-delivery would draw a fresh card");
  // A check scheduled by an older generation never retires anything.
  ui.deliver("ev-late");
  ui.context.eventsGeneration = 3;
  ui.context.purgeUndeliveredGates(2);
  assert.equal(ui.context.gates.has("ev-late"), true);
});

test("gates: a cancel reaching the tab that is answering means another answer won - never labelled answered", () => {
  const ui = gateClient();
  ui.deliver("ev-1");
  ui.context.answering.add("ev-1");
  // The call is still out: the handler is told, and will settle `closed`.
  ui.context.acceptGateResolved({ kind: "gate-resolved", id: "ev-1" });
  assert.equal(ui.context.lostRaces.has("ev-1"), true);
  assert.equal(ui.context.gates.has("ev-1"), false);
  // The handler already said "answered": the card is corrected in place.
  ui.deliver("ev-2");
  const card = fakeCard();
  card.classes.add("answered");
  ui.context.gateNodes.set("ev-2", card);
  ui.context.answering.add("ev-2");
  ui.context.acceptGateResolved({ kind: "gate-resolved", id: "ev-2" });
  assert.deepEqual(ui.settled.map((s) => `${s.verb} · ${s.outcome}`), ["closed · settled elsewhere"]);
});

test("gates: a failed open never strands a pending approval - frames are released and the session's gates are drawn", () => {
  const drawn: string[] = [];
  const reported: unknown[] = [];
  let flushed = 0;
  const context = vm.createContext({
    loadingSession: "s", activeSession: "s",
    gates: new Map([["ev-own", { id: "ev-own", sessionId: "s" }], ["ev-other", { id: "ev-other", sessionId: "elsewhere" }]]),
    memberSessionIds: () => new Set(), renderGate: (gate: { id: string }) => drawn.push(gate.id),
    renderSubagents: () => {}, flushQueued: () => { flushed++; }, failed: (err: unknown) => reported.push(err),
  });
  const openFailed = chatSource.statements.find((node): node is ts.FunctionDeclaration => ts.isFunctionDeclaration(node) && node.name?.text === "openFailed");
  assert.ok(openFailed);
  vm.runInContext(openFailed.getText(chatSource), context);
  context.openFailed("s", new Error("session/follow: session/not-found - gone"), "session/follow");
  assert.equal(context.loadingSession, null, "frames stop queueing (critique WC-F3)");
  assert.equal(flushed, 1);
  assert.deepEqual(drawn, ["ev-own"], "the Gate-2 card of the session on screen is visible even without its transcript");
  assert.equal(reported.length, 1);
});

test("gates: a withdrawal nobody here answered closes the card with no invented outcome; an id-less one matches nothing", () => {
  const ui = gateClient();
  ui.deliver("ev-1");
  const card = fakeCard();
  ui.context.gateNodes.set("ev-1", card);
  ui.context.acceptGateResolved({ kind: "gate-resolved" });
  assert.equal(ui.context.gates.size, 1);
  ui.context.acceptGateResolved({ kind: "gate-resolved", id: "ev-1" });
  assert.equal(ui.context.gates.size, 0);
  assert.deepEqual(ui.settled.map((s) => `${s.verb} · ${s.outcome}`), ["closed · closed"]);
});
