// face/tests/room-fake.ts
/** A fake dsh tree for the room engine's offline tests: scriptable agents, a
 * manual clock, and a root `session/event` bus. Structural twins of exactly
 * the members `RoomContextLike` (src/room.ts) reads - nothing more - in dsh
 * 0.2.0-rc.2's shapes, so an engine still reading a 0.1.1 shape FAILS here:
 *   - a session has no `events` getter, only `snapshotEvents()`
 *     (NEW packages/core/session/src/index.ts:649-661);
 *   - `setup` is `(agentCtx, agent)` and the ctx carries NO `agent`
 *     (NEW packages/core/agent/src/index.ts:51-54, commit ebce3a5f04);
 *   - `permissionPresets.current` takes the SESSION
 *     (NEW packages/interaction/permission-presets/src/index.ts:343-345), and
 *     the user default is pinned on announcement when setup pinned nothing
 *     (`pinInitialPermission`, :428-456);
 *   - `sessionPersistence.list()` returns `{header, revision}` snapshots
 *     (NEW packages/session/session-persistence/src/index.ts:50-58);
 *   - a cold session is resumed by `sessionController.resolveAgent`, which
 *     answers `{agent} | {error}` (NEW packages/api/session-controller/src/agent.ts:61-66);
 *   - a tool result is a `role:'tool'` message with `toolCallId`/`isError` on it
 *     (NEW packages/llm/llm/src/message.ts:173-180);
 *   - the default route is `deepseek-official/deepseek-flash`
 *     (NEW packages/bundle/base/cordis.patch.yml:82-86).
 * The type assertion at the bottom makes `tsc` hold the fake to the engine's
 * `RoomContextLike`, so the two cannot drift apart silently. */
import type { RoomContextLike } from "../src/room.ts";
import type { EventLike, MessageLike } from "../src/room-rules.ts";

export type Script =
  | { kind: "answer"; text: string; afterMs?: number; toolFirst?: boolean }
  | { kind: "error"; message: string }
  | { kind: "hang" }
  | { kind: "gate" }
  | { kind: "throw" };

type Listener = (session: FakeSession, event: EventLike) => void;
export interface FakeHeader { id: string; cwd?: string; parentSession?: string; agentPreset?: string; origin?: string; createdAt: number }
/** The agent-scoped context `setup` receives: an opaque token here, like dsh's
 * cordis `Context` to the engine - deliberately WITHOUT an `agent` member. */
export interface FakeAgentCtx { readonly fakeAgentId: string }
type FakeSetup = (agentCtx: FakeAgentCtx, agent: FakeAgent) => Promise<unknown> | unknown;
/** The preset dsh-permission-presets pins on `session/created` when setup pinned none (the fake's `defaultPreset`). */
export const DEFAULT_PERMISSION_PRESET = "workspace-write";

export class FakeSession {
  private readonly log: EventLike[] = [];
  tree?: FakeTree;
  constructor(readonly id: string, readonly header: FakeHeader) {}
  get seq(): number { return this.log.length; }
  /** dsh 0.2's reader: a frozen snapshot of the whole log. */
  snapshotEvents(): readonly EventLike[] { return Object.freeze([...this.log]); }
  /** The tree's append path (bus emits land here). */
  record(event: EventLike): void { this.log.push(event); }
  /** The engine's direct append (plan 2, deviation 2): a known event, published on the bus. */
  append(type: "user/message", data: MessageLike, _opts: { surfaceOp: "append" }): EventLike {
    const event = { type, seq: this.seq, data };
    this.tree!.emit(this, event);
    return event;
  }
}

export class FakeAgent {
  status: "idle" | "running" = "idle";
  readonly inbox = { nextStep: [] as MessageLike[], nextTurn: [] as MessageLike[] };
  turn = 0;
  cancelled: { cause: unknown; options: unknown }[] = [];
  private idleWaiters: (() => void)[] = [];
  private pendingFinish?: (reason: unknown) => void;
  constructor(readonly tree: FakeTree, readonly session: FakeSession, readonly script?: (message: MessageLike, turn: number) => Script) {}
  get id(): string { return this.session.id; }
  private emit(type: string, data: unknown): void { this.tree.emit(this.session, { type, seq: this.session.seq, data }); }
  private splice(target: "next-step" | "next-turn", message: MessageLike): void {
    const list = target === "next-step" ? this.inbox.nextStep : this.inbox.nextTurn;
    if ([...this.inbox.nextStep, ...this.inbox.nextTurn].some((m) => m.id === message.id)) throw new Error(`message "${message.id}" is already pending`);
    this.emit("agent/inbox/spliced", { target, start: list.length, inserted: [message] });
    list.push(message);
  }
  inject(message: MessageLike): void { this.splice("next-step", message); }
  followup(message: MessageLike): void {
    this.splice("next-turn", message);
    if (this.script !== undefined) this.drive();
  }
  /** A member: claim the queued prompt and play the script. */
  private drive(): void {
    const claimed = [...this.inbox.nextStep.splice(0), ...this.inbox.nextTurn.splice(0, 1)];
    const prompt = claimed[claimed.length - 1];
    const turn = ++this.turn;
    this.status = "running";
    this.emit("turn/start", { turn });
    for (const m of claimed) this.emit("user/message", m);
    let script: Script;
    try { script = this.script!(prompt, turn); } catch (err) { script = { kind: "error", message: String(err) }; }
    const finish = (reason: unknown): void => {
      this.emit("turn/end", { turn, reason });
      this.status = "idle";
      for (const w of this.idleWaiters.splice(0)) w();
    };
    const say = (text: string): void => this.emit("assistant/message", { turn, step: 1, message: { id: `${this.id}-m${this.session.seq}`, role: "assistant", content: [{ type: "text", text }], source: { kind: "model", provider: "fake", model: "fake" } } });
    if (script.kind === "throw") throw new Error("followup exploded");
    if (script.kind === "error") { this.tree.clock.setTimeout(() => finish({ kind: "error", error: { message: (script as { message: string }).message, code: "FAKE" } }), 1); return; }
    if (script.kind === "hang") { this.pendingFinish = finish; return; }
    if (script.kind === "gate") {
      this.emit("tool/call", { turn, step: 1, callId: `${this.id}-ask`, name: "ask_user_question", arguments: "{}" });
      this.pendingFinish = finish;
      return;
    }
    const answer = script;
    this.tree.clock.setTimeout(() => {
      if (answer.toolFirst) {
        say("let me check");
        this.emit("tool/call", { turn, step: 1, callId: `${this.id}-c1`, name: "bash", arguments: "{}" });
        this.emit("tool/result", { turn, step: 1, message: toolResultMessage(`${this.id}-t${this.session.seq}`, `${this.id}-c1`, false) });
      }
      if (answer.text !== "") say(answer.text);
      finish({ kind: "completed" });
    }, answer.afterMs ?? 10);
  }
  cancel(cause: unknown, options?: unknown): void {
    this.cancelled.push({ cause, options });
    const finish = this.pendingFinish;
    this.pendingFinish = undefined;
    if (finish !== undefined) this.tree.clock.setTimeout(() => finish({ kind: "aborted", reason: cause }), 1);
  }
  /** A Kairos fake: settle when the test says the driver went idle. */
  whenIdle(): Promise<void> {
    return this.status === "idle" ? Promise.resolve() : new Promise((resolve) => { this.idleWaiters.push(resolve); });
  }
  /** A Kairos fake: the driver wakes and claims every pending message into one turn. */
  wake(): MessageLike[] {
    const claimed = [...this.inbox.nextStep.splice(0), ...this.inbox.nextTurn.splice(0, 1)];
    const turn = ++this.turn;
    this.emit("turn/start", { turn });
    for (const m of claimed) this.emit("user/message", m);
    return claimed;
  }
  /** A Kairos fake: end the open turn. */
  sleep(): void {
    this.emit("turn/end", { turn: this.turn, reason: { kind: "completed" } });
    this.status = "idle";
    for (const w of this.idleWaiters.splice(0)) w();
  }
}

/** dsh 0.2's tool-role result message (`createToolResultMessage`, NEW packages/llm/llm/src/message.ts:299-306). */
export const toolResultMessage = (id: string, callId: string, isError: boolean) => ({
  id, role: "tool" as const, toolCallId: callId, isError, content: [] as unknown[], source: { kind: "tool" as const, callId },
});
/** dsh 0.1.1's wrapper shape (`role:'user'`, the result inside `content[0]`) - kept ONLY so tests can prove it is no longer read. */
export const legacyToolResultMessage = (id: string, callId: string, isError: boolean) => ({
  id, role: "user" as const, content: [{ type: "tool-result", toolCallId: callId, content: [], isError }], source: { kind: "tool" as const, callId },
});

export class FakeClock {
  private t = 1_000_000;
  private timers: { at: number; fn: () => void; id: number }[] = [];
  private nextId = 1;
  now(): number { return this.t; }
  setTimeout(fn: () => void, ms: number): number {
    const id = this.nextId++;
    this.timers.push({ at: this.t + ms, fn, id });
    return id;
  }
  clearTimeout(handle: unknown): void { this.timers = this.timers.filter((x) => x.id !== handle); }
  /** Let every pending promise continuation run. */
  async flush(): Promise<void> { for (let i = 0; i < 20; i++) await new Promise<void>((r) => setImmediate(r)); }
  /** Advance the clock, firing due timers in order and flushing between them. */
  async advance(ms: number): Promise<void> {
    const until = this.t + ms;
    await this.flush();
    for (;;) {
      const due = this.timers.filter((x) => x.at <= until).sort((a, b) => a.at - b.at)[0];
      if (due === undefined) break;
      this.timers = this.timers.filter((x) => x.id !== due.id);
      this.t = Math.max(this.t, due.at);
      due.fn();
      await this.flush();
    }
    this.t = until;
    await this.flush();
  }
}

type ResolveResult = { agent: FakeAgent } | { error: { code?: string; message: string } };

export class FakeTree {
  readonly clock = new FakeClock();
  readonly sessions = new Map<string, FakeSession>();
  readonly agents = new Map<string, FakeAgent>();
  readonly scripts = new Map<string, (message: MessageLike, turn: number) => Script>();
  readonly listeners: Listener[] = [];
  readonly agentsCreated: unknown[] = [];
  readonly resumed: unknown[] = [];
  readonly mounts: { agent: string; preset: string }[] = [];
  readonly selections: { agent: string; selection: unknown }[] = [];
  readonly registeredTools: { name: string }[] = [];
  readonly attached: string[] = [];
  readonly persisted: FakeHeader[] = [];
  /** The effective permission preset of each session at the moment it was PUBLISHED (after setup, after the announcement pin). */
  readonly publishedWith = new Map<string, string>();
  /** Session ids whose stored log the (fake) persistence refuses to open, with the error it throws. */
  readonly unopenable = new Map<string, Error>();
  routes = new Set<string>(["stub/echo", "deepseek-official/deepseek-flash"]);
  brokenPresets = new Set<string>();
  /** Every `sessionController.resolveAgent` call, by session id. */
  resolveCalls: string[] = [];
  /** What `resolveAgent` does for a session that is not live (the default: dsh's `session/not-found`). */
  resolveCold: (sessionId: string) => ResolveResult = (sessionId) => ({ error: { code: "session/not-found", message: `session "${sessionId}" not found` } });
  private createdAt = 1;

  emit(session: FakeSession, event: EventLike): void {
    session.record(event);
    for (const l of [...this.listeners]) l(session, event);
  }
  script(bot: string, fn: (message: MessageLike, turn: number) => Script): void { this.scripts.set(bot, fn); }
  /** A room: Kairos's live session in a channel. */
  newRoom(id: string, cwd: string): FakeAgent {
    const session = new FakeSession(id, { id, cwd, agentPreset: "kairos", createdAt: this.createdAt++ });
    session.tree = this;
    const agent = new FakeAgent(this, session);
    this.sessions.set(id, session);
    this.agents.set(id, agent);
    return agent;
  }
  /** A cold member on disk (a header only), for the resume path. */
  persistMember(id: string, room: string, bot: string, cwd: string): void {
    this.persisted.push({ id, cwd, parentSession: room, agentPreset: bot, createdAt: this.createdAt++ });
  }
  /** The last `permission/preset` on a session's log, else the default (dsh derives it from the knobs). */
  private permissionOf(session: FakeSession): string {
    const last = [...session.snapshotEvents()].reverse().find((e) => e.type === "permission/preset");
    return last === undefined ? DEFAULT_PERMISSION_PRESET : String((last.data as { preset: string }).preset);
  }
  /** Publication, as dsh-agent orders it: setup has settled, then `session/created`
   * (where dsh-permission-presets pins the default when nothing is pinned), then
   * the ids become visible. */
  private publish(session: FakeSession, agent: FakeAgent): void {
    if (!session.snapshotEvents().some((e) => e.type === "permission/preset")) this.emit(session, { type: "permission/preset", seq: session.seq, data: { preset: DEFAULT_PERMISSION_PRESET } });
    this.publishedWith.set(session.id, this.permissionOf(session));
    this.sessions.set(session.id, session);
    this.agents.set(session.id, agent);
  }

  readonly ctx = {
    agents: {
      get: (id: string) => this.agents.get(id),
      create: async (opts: { sessionId: string; meta: { cwd: string; parentSession?: string; agentPreset?: string }; agentOptions?: unknown; setup?: FakeSetup }) => {
        if (this.agents.has(opts.sessionId)) throw new Error(`session "${opts.sessionId}" already exists`);
        this.agentsCreated.push(opts);
        const session = new FakeSession(opts.sessionId, { id: opts.sessionId, ...opts.meta, createdAt: this.createdAt++ });
        session.tree = this;
        const bot = opts.meta.agentPreset ?? "";
        const agent = new FakeAgent(this, session, this.scripts.get(bot) ?? (() => ({ kind: "answer", text: "(pass)" })));
        await opts.setup?.({ fakeAgentId: agent.id }, agent);
        this.publish(session, agent);
        this.persisted.push({ id: session.id, ...opts.meta, createdAt: session.header.createdAt });
        return { agent, dispose: async () => {} };
      },
      resume: async (opts: { resumeSessionId: string; agentOptions?: unknown; setup?: FakeSetup }) => {
        const header = this.persisted.find((h) => h.id === opts.resumeSessionId);
        if (header === undefined) throw new Error(`session "${opts.resumeSessionId}" not found`);
        const refused = this.unopenable.get(opts.resumeSessionId);
        if (refused !== undefined) throw refused;
        if (this.agents.has(opts.resumeSessionId)) throw new Error(`agent "${opts.resumeSessionId}" is already registered`);
        this.resumed.push(opts);
        const session = new FakeSession(header.id, header);
        session.tree = this;
        const agent = new FakeAgent(this, session, this.scripts.get(header.agentPreset ?? "") ?? (() => ({ kind: "answer", text: "(pass)" })));
        await opts.setup?.({ fakeAgentId: agent.id }, agent);
        this.publish(session, agent);
        return { agent, dispose: async () => {} };
      },
    },
    sessions: { get: (id: string) => this.sessions.get(id) },
    sessionPersistence: { list: async () => this.persisted.map((header, i) => ({ header: { ...header }, revision: `r${i}` })) },
    tools: { register: (definition: { name: string }) => { this.registeredTools.push(definition); return () => { this.registeredTools.splice(this.registeredTools.indexOf(definition), 1); }; } },
    sessionProjections: {
      register: () => () => {},
      /** The `agentPreset` unit: the header's value, advanced by `agent-preset/selected` (NEW .../agent-preset-registry/src/session.ts:36-46). */
      stateOf: (session: FakeSession, _key: "agentPreset"): string | null => {
        let preset: string | null = session.header.agentPreset ?? null;
        for (const e of session.snapshotEvents()) if (e.type === "agent-preset/selected") preset = String((e.data as { agentPreset: string }).agentPreset);
        return preset;
      },
    },
    permissionPresets: {
      /** Appends only on a change, like dsh's `apply` (NEW .../permission-presets/src/index.ts:403-420). */
      set: (session: FakeSession, name: string) => { if (this.permissionOf(session) !== name) this.emit(session, { type: "permission/preset", seq: session.seq, data: { preset: name } }); },
      current: (session: FakeSession) => this.permissionOf(session),
    },
    agentPresets: {
      mount: async (agentCtx: FakeAgentCtx, id: string) => {
        if (this.brokenPresets.has(id)) throw new Error(`agent preset "${id}" is broken: not a list`);
        this.mounts.push({ agent: agentCtx.fakeAgentId, preset: id });
        return { id };
      },
    },
    agentDefaultModel: { currentSelection: () => ({ provider: "deepseek-official", model: "deepseek-flash" }) },
    llm: { resolveCallConfig: async (config: { provider: string; model: string }) => { if (!this.routes.has(`${config.provider}/${config.model}`)) throw new Error(`no adapter serves ${config.provider}`); return config; } },
    workspaceRegistry: { resolveByPath: async (_path: string) => ({ attachSession: async (id: string) => { this.attached.push(id); } }) },
    sessionController: {
      resolveAgent: async (sessionId: string): Promise<ResolveResult> => {
        this.resolveCalls.push(sessionId);
        const live = this.agents.get(sessionId);
        return live !== undefined ? { agent: live } : this.resolveCold(sessionId);
      },
    },
    on: (_name: "session/event", listener: Listener) => { this.listeners.push(listener); return () => { const i = this.listeners.indexOf(listener); if (i >= 0) this.listeners.splice(i, 1); return i >= 0; }; },
    logger: { warn: (_m: string) => {} },
  };
}

export const makeFakeTree = (): FakeTree => new FakeTree();

/* `tsc` holds the fake to the engine's contract: a `RoomContextLike` change
 * that the fake does not mirror is a type error here, not a green test over a
 * shape dsh no longer has. */
export const fakeRoomContext = (tree: FakeTree): RoomContextLike => tree.ctx;
