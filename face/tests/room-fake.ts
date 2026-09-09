// face/tests/room-fake.ts
/** A fake dsh tree for the room engine's offline tests: scriptable agents, a
 * manual clock, and a root `session/event` bus. Structural twins of exactly
 * the members `RoomContextLike` (src/room.ts) reads - nothing more. */
import type { EventLike, MessageLike } from "../src/room-rules.ts";

export type Script =
  | { kind: "answer"; text: string; afterMs?: number; toolFirst?: boolean }
  | { kind: "error"; message: string }
  | { kind: "hang" }
  | { kind: "gate" }
  | { kind: "throw" };

type Listener = (session: FakeSession, event: EventLike) => void;

export class FakeSession {
  readonly events: EventLike[] = [];
  tree?: FakeTree;
  constructor(readonly id: string, readonly header: { cwd?: string; parentSession?: string; agentPreset?: string; origin?: string; createdAt: number }) {}
  get seq(): number { return this.events.length; }
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
        this.emit("tool/result", { turn, step: 1, message: { id: `${this.id}-t${this.session.seq}`, role: "user", content: [{ type: "tool-result", toolCallId: `${this.id}-c1`, content: [] }], source: { kind: "tool", callId: `${this.id}-c1` } } });
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
  readonly persisted: { id: string; cwd?: string; parentSession?: string; agentPreset?: string; origin?: string; createdAt: number }[] = [];
  routes = new Set<string>(["stub/echo", "deepseek-official/deepseek-v4-flash"]);
  brokenPresets = new Set<string>();
  modelsCalls: string[] = [];
  private createdAt = 1;

  emit(session: FakeSession, event: EventLike): void {
    session.events.push(event);
    for (const l of [...this.listeners]) l(session, event);
  }
  script(bot: string, fn: (message: MessageLike, turn: number) => Script): void { this.scripts.set(bot, fn); }
  /** A room: Kairos's live session in a channel. */
  newRoom(id: string, cwd: string): FakeAgent {
    const session = new FakeSession(id, { cwd, agentPreset: "kairos", createdAt: this.createdAt++ });
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

  readonly ctx = {
    agents: {
      get: (id: string) => this.agents.get(id),
      create: async (opts: { sessionId: string; meta: { cwd: string; parentSession?: string; agentPreset?: string }; agentOptions?: unknown; setup?: (agentCtx: unknown) => Promise<unknown> | unknown }) => {
        if (this.agents.has(opts.sessionId)) throw new Error(`session "${opts.sessionId}" already exists`);
        this.agentsCreated.push(opts);
        const session = new FakeSession(opts.sessionId, { ...opts.meta, createdAt: this.createdAt++ });
        session.tree = this;
        const bot = opts.meta.agentPreset ?? "";
        const agent = new FakeAgent(this, session, this.scripts.get(bot) ?? (() => ({ kind: "answer", text: "(pass)" })));
        await opts.setup?.({ agent });
        this.sessions.set(session.id, session);
        this.agents.set(session.id, agent);
        this.persisted.push({ id: session.id, ...opts.meta, createdAt: session.header.createdAt });
        return { agent, dispose: async () => {} };
      },
      resume: async (opts: { resumeSessionId: string; agentOptions?: unknown; setup?: (agentCtx: unknown) => Promise<unknown> | unknown }) => {
        const header = this.persisted.find((h) => h.id === opts.resumeSessionId);
        if (header === undefined) throw new Error(`session "${opts.resumeSessionId}" not found`);
        if (this.agents.has(opts.resumeSessionId)) throw new Error(`agent "${opts.resumeSessionId}" is already registered`);
        this.resumed.push(opts);
        const session = new FakeSession(header.id, header);
        session.tree = this;
        const agent = new FakeAgent(this, session, this.scripts.get(header.agentPreset ?? "") ?? (() => ({ kind: "answer", text: "(pass)" })));
        await opts.setup?.({ agent });
        this.sessions.set(session.id, session);
        this.agents.set(session.id, agent);
        return { agent, dispose: async () => {} };
      },
    },
    sessions: { get: (id: string) => this.sessions.get(id) },
    sessionPersistence: { list: async () => [...this.persisted] },
    tools: { register: (definition: { name: string }) => { this.registeredTools.push(definition); return () => { this.registeredTools.splice(this.registeredTools.indexOf(definition), 1); }; } },
    sessionProjections: { register: () => () => {} },
    permissionPresets: {
      set: (session: FakeSession, name: string) => { this.emit(session, { type: "permission/preset", seq: session.seq, data: { preset: name } }); },
      current: (events: readonly EventLike[]) => {
        const last = [...events].reverse().find((e) => e.type === "permission/preset");
        return last === undefined ? "workspace-write" : String((last.data as { preset: string }).preset);
      },
    },
    agentPresets: {
      mount: async (agentCtx: { agent: FakeAgent }, id: string) => {
        if (this.brokenPresets.has(id)) throw new Error(`agent preset "${id}" is broken: not a list`);
        this.mounts.push({ agent: agentCtx.agent.id, preset: id });
        return { id };
      },
    },
    agentDefaultModel: { currentSelection: () => ({ provider: "deepseek-official", model: "deepseek-v4-flash" }) },
    llm: { resolveCallConfig: async (config: { provider: string; model: string }) => { if (!this.routes.has(`${config.provider}/${config.model}`)) throw new Error(`no adapter serves ${config.provider}`); return config; } },
    workspaceRegistry: { resolveByPath: async (_path: string) => ({ attachSession: async (id: string) => { this.attached.push(id); } }) },
    apiProxy: { sessions: { models: async (request: { payload: { sessionId: string } }) => { this.modelsCalls.push(request.payload.sessionId); return { ok: true }; } } },
    on: (_name: "session/event", listener: Listener) => { this.listeners.push(listener); return () => { const i = this.listeners.indexOf(listener); if (i >= 0) this.listeners.splice(i, 1); return i >= 0; }; },
    logger: { warn: (_m: string) => {} },
  };
}

export const makeFakeTree = (): FakeTree => new FakeTree();
