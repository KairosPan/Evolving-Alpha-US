/** The room engine: `dispatch`, member sessions, deltas, rounds, continuations,
 * caps, deadlines, the `room` projection and the operator's `@` — spec §4, §5.
 *
 * Installed on the booted ROOT context by main.ts (`installRoom`), the way Gate
 * 2 and the `agent_<bin>` tools are: a root-level `session/event` listener sees
 * every session, a root-created member is a runtime root (so it can ask the
 * operator a question - a runtime-owned child is refused `DELEGATED_CALLER`),
 * and the disposers ride the face's lifetime.
 *
 * HOW A ROOM FACT IS RECORDED (plan 2, deviation 1): only through KNOWN dsh
 * event types. dsh's persistence refuses to reload a log carrying a type
 * outside its generated catalog, so there are no `room/*` events. Membership
 * is the member's own header (`parentSession` + `agentPreset`); the dispatch is
 * the tool's own `tool/call`/`tool/result`; an answer is a `user/message` in
 * Kairos's session with `source.kind === 'room'`; the member's cursor is the
 * delta message in ITS log.
 *
 * HOW AN ANSWER REACHES KAIROS (deviation 2): appended straight onto the room
 * session's log with `surfaceOp: 'append'` - visible at once, seq now, in the
 * next request's history - but ONLY while the room log is quiet (no open turn),
 * because a user message dropped between an assistant tool-call message and
 * its tool result breaks the running request. Otherwise it waits in the room's
 * outbox for the next `turn/end`. Kairos is woken only by the round-end
 * `followup`, issued in the same synchronous block as the last flush.
 *
 * WHAT THIS IS NOT. Dispatch grants nothing: a member's tools are its mask,
 * its writes are its `read-only` sandbox mode (pinned inside creation setup),
 * its orders are Gate 2. The roster it checks is a menu (channels spec §5).
 * @module
 */
import { randomUUID } from "node:crypto";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Context } from "@deepseek-ai/cordis";
import { installModelSelection as installDshModelSelection } from "@deepseek-ai/dsh-agent";
import { createUserMessage, type ReasoningEffortId } from "@deepseek-ai/dsh-llm";
import type { BotRow } from "./bots.ts";
import { isJsonBody, isTrustedDataRequest } from "./data.ts";
import { FORBIDDEN, HttpError, readBody } from "./http.ts";
import { DEFAULT_PRESET } from "./overlay.ts";
import { readRosters } from "./roster.ts";
import { registerRoomProjection } from "./room-projection.ts";
import {
  ROOM_CAPS, dispatchResultText, finalTextOf, formatDelta, isPass, memberPrompt, parseModelRoute,
  resolveMentions, roomLinesOf, roundEndText, validateDispatch,
  type DispatchArgs, type EventLike, type MessageLike, type RoomCaps, type RoomTurnRecord, type RosterBot,
  type RoundOutcome, type TurnTrigger,
} from "./room-rules.ts";
import { SESSION_ID_RE } from "./sessions.ts";
import type { RouteRegistrar } from "./static.ts";

const BIN = "kairos-face";

/* ---------- what the engine reads of the tree, stated structurally ---------- */

/** dsh-session's `Session`, narrowed. `append` is used on the ROOM session only (deviation 2). */
export interface SessionLike {
  readonly id: string;
  readonly header: { readonly cwd?: string; readonly parentSession?: string; readonly agentPreset?: string; readonly origin?: string };
  readonly events: readonly EventLike[];
  readonly seq: number;
  append(type: "user/message", data: MessageLike, opts: { surfaceOp: "append" }): unknown;
}
/** dsh-agent's `Agent`, narrowed. */
export interface AgentLike {
  readonly id: string;
  readonly status: "idle" | "running";
  readonly session: SessionLike;
  followup(message: MessageLike): void;
  cancel(cause: { kind: "hook"; reason: string }, options?: { keepInbox?: boolean }): void;
}
export interface ModelSelectionLike { provider: string; model: string; reasoningEffort?: ReasoningEffortId }
/** dsh-agent's `ModelSelectionRef`; assignable to it, so the real call below is type-checked. */
export interface ModelSelectionRefLike { current: ModelSelectionLike | undefined; assembled: ModelSelectionLike | undefined }
/** The scoped `Context` `setup` receives (dsh-agent-loop calls `setup(prepared.agent.ctx)`): `agentCtx.agent` is the agent being composed. */
export interface AgentCtxLike { agent?: AgentLike }
export interface CreateMemberOptions {
  sessionId: string;
  meta: { cwd: string; parentSession: string; agentPreset: string };
  agentOptions: { provider: string; model: string };
  setup(agentCtx: AgentCtxLike): Promise<void>;
}
export interface ResumeMemberOptions { resumeSessionId: string; agentOptions: { provider: string; model: string }; setup(agentCtx: AgentCtxLike): Promise<void> }
export interface PersistedHeaderLike { id: string; cwd?: string; parentSession?: string; agentPreset?: string; origin?: string; createdAt: number }
/** dsh-tools' `ToolRunContext`, narrowed: the calling agent and Kairos's TURN signal (which the round must not run on). */
export interface RoomToolExec { agent?: AgentLike; signal: AbortSignal }
/** dsh-tools' `ToolDefinition`, stated the way agents.ts states it. */
export interface RoomToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  output: { schema: Record<string, unknown>; render(args: unknown, value: unknown): { type: "text"; text: string }[] };
  timeoutMs: number;
  execute(args: unknown, exec: RoomToolExec): Promise<unknown>;
  presentCall(args: unknown): { card: "generic"; title: string; kind: "read"; rawInput?: unknown };
}
export interface RoomContextLike {
  agents: {
    get(id: string): AgentLike | undefined;
    create(options: CreateMemberOptions): Promise<{ agent: AgentLike }>;
    resume(options: ResumeMemberOptions): Promise<{ agent: AgentLike }>;
  };
  sessions: { get(id: string): SessionLike | undefined };
  sessionPersistence?: { list(): Promise<PersistedHeaderLike[]> };
  tools: { register(definition: RoomToolDefinition): () => void };
  sessionProjections?: { register(definition: never): () => void };
  permissionPresets: { set(session: SessionLike, name: string): void; current(events: readonly EventLike[]): string };
  agentPresets: { mount(agentCtx: AgentCtxLike, id: string): Promise<unknown> };
  agentDefaultModel: { currentSelection(): ModelSelectionLike };
  llm: { resolveCallConfig(config: { provider: string; model: string }): Promise<unknown> };
  workspaceRegistry: { resolveByPath(path: string): Promise<{ attachSession(id: string): Promise<void> } | undefined> };
  /** The gateway; `sessions.models` resumes a cold session through the gateway's OWN composition (see `ensureLive`). */
  apiProxy?: { sessions: { models(request: { rpcId: string; payload: { sessionId: string } }): Promise<unknown> } };
  on(name: "session/event", listener: (session: SessionLike, event: EventLike) => void): () => boolean;
  logger?: { warn(message: string): void };
}

/* ---------- the engine's own seams ---------- */

export interface RoomChannel { workspaceId: string; name: string; dir: string }
export interface RoomClock { now(): number; setTimeout(fn: () => void, ms: number): unknown; clearTimeout(handle: unknown): void }
export interface RoomDeps {
  ctx: RoomContextLike;
  /** The harness home holding `face/channels.json`. */
  home: string;
  /** Which channel a session's directory belongs to (panels.ts `channelFor`, with `dir`). */
  channelFor(cwd: string | undefined): Promise<RoomChannel | null>;
  /** `listBots(botsRoot, presets.list)` from bots.ts, narrowed. */
  listBots(): Promise<Pick<BotRow, "id" | "name" | "model" | "broken">[]>;
  caps?: Partial<RoomCaps>;
  clock?: RoomClock;
  /** dsh-agent's `installModelSelection`; injected so the fake tree can record it. */
  installModelSelection?: (agentCtx: AgentCtxLike, ref: ModelSelectionRefLike) => () => void;
  log?: (line: string) => void;
}

export interface Member { bot: string; name: string; agent: AgentLike; queue: Promise<unknown> }
export interface MemberTurnResult { record: RoomTurnRecord; text: string }
export interface Round {
  n: number;
  mode: "parallel" | "serial" | "mention";
  superseded: boolean;
  capped: boolean;
  continuations: string[];
  continuationsRun: number;
  turns: RoomTurnRecord[];
}
export interface Room {
  id: string;
  channel: RoomChannel;
  members: Map<string, Member>;
  ensuring: Map<string, Promise<Member>>;
  selections: Map<string, { selection: ModelSelectionLike; note?: string }>;
  /** Messages for the room log, waiting for a quiet log (deviation 2). */
  outbox: MessageLike[];
  roundsThisSend: number;
  turnsThisSend: number;
  active?: Round;
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err));
const defaultClock: RoomClock = { now: () => Date.now(), setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: (h) => clearTimeout(h as NodeJS.Timeout) };

/** No open turn on this log: the last `turn/start` has its `turn/end`. */
export function isQuiet(session: SessionLike): boolean {
  const events = session.events;
  for (let i = events.length - 1; i >= 0; i--) {
    const type = events[i].type;
    if (type === "turn/end") return true;
    if (type === "turn/start") return false;
  }
  return true;
}

/** The turn's open gate, read from ITS log (deviation 8): an `ask_user_question` call with no result yet, or an approval asked and not decided. */
export function gatePending(events: readonly EventLike[], turn: number): boolean {
  const openAsks = new Set<string>();
  const openApprovals = new Set<string>();
  for (const event of events) {
    const data = event.data as Record<string, unknown> | undefined;
    if (data === undefined) continue;
    if (event.type === "tool/call" && data.turn === turn && data.name === "ask_user_question" && typeof data.callId === "string") openAsks.add(data.callId);
    else if (event.type === "tool/result" && data.turn === turn) {
      const block = (data.message as { content?: { toolCallId?: unknown }[] } | undefined)?.content?.[0];
      if (typeof block?.toolCallId === "string") openAsks.delete(block.toolCallId);
    } else if (event.type === "approval/asked" && typeof data.id === "string") openApprovals.add(data.id);
    else if (event.type === "approval/decided" && typeof data.id === "string") openApprovals.delete(data.id);
  }
  return openAsks.size > 0 || openApprovals.size > 0;
}

/** Message ids a member has already been shown, from the delta prompts in its own log (its durable cursor). */
export function seenIdsOf(events: readonly EventLike[]): Set<string> {
  const seen = new Set<string>();
  for (const event of events) {
    if (event.type !== "user/message") continue;
    const source = (event.data as MessageLike | undefined)?.source as { kind?: unknown; form?: unknown; messageIds?: unknown } | undefined;
    if (source?.kind === "room" && source.form === "delta" && Array.isArray(source.messageIds)) {
      for (const id of source.messageIds) if (typeof id === "string") seen.add(id);
    }
  }
  return seen;
}

export class RoomEngine {
  private readonly rooms = new Map<string, Room>();
  /** member session id → the listener of the turn being driven on it (one at a time per member). */
  private readonly turnWaiters = new Map<string, (event: EventLike) => void>();
  private readonly quietWaiters = new Map<string, Array<() => void>>();
  private readonly disposers: Array<() => void> = [];
  readonly caps: RoomCaps;
  private readonly clock: RoomClock;
  private readonly installSelection: NonNullable<RoomDeps["installModelSelection"]>;
  private readonly log: (line: string) => void;

  constructor(private readonly deps: RoomDeps) {
    this.caps = { ...ROOM_CAPS, ...deps.caps };
    this.clock = deps.clock ?? defaultClock;
    /* dsh-agent-loop's `setupAndPublish` calls `setup(prepared.agent.ctx)`, so
     * what `setup` holds IS the agent-scoped cordis `Context` this wants; the
     * cast erases only dsh's branded ids (`MessageId` on `Session.append`),
     * which this module states as plain strings. The ref is NOT cast — it is
     * checked against dsh's own `ModelSelectionRef`. */
    this.installSelection = deps.installModelSelection ?? ((agentCtx, ref) => installDshModelSelection(agentCtx as unknown as Context, ref));
    this.log = deps.log ?? ((line) => console.log(`${BIN}: ${line}`));
    const off = deps.ctx.on("session/event", (session, event) => this.onEvent(session, event));
    this.disposers.push(() => { off(); });
  }

  dispose(): void {
    for (const d of this.disposers.splice(0)) d();
  }

  /** The runtime for a room session; created on first sight. */
  roomOf(agentId: string, channel: RoomChannel): Room {
    let room = this.rooms.get(agentId);
    if (room === undefined) {
      room = { id: agentId, channel, members: new Map(), ensuring: new Map(), selections: new Map(), outbox: [], roundsThisSend: 0, turnsThisSend: 0 };
      this.rooms.set(agentId, room);
    }
    return room;
  }

  /** The model-fallback note for a bot in this room, if its route was not served. */
  noteFor(room: Room, bot: string): string | undefined { return room.selections.get(bot)?.note; }

  /* ---------- the event bus ---------- */

  private onEvent(session: SessionLike, event: EventLike): void {
    this.turnWaiters.get(session.id)?.(event);
    const room = this.rooms.get(session.id);
    if (room === undefined) return;
    /* Everything below runs in a later tick: `Session.append` rejects reentrancy,
     * and these reactions append to the very session that just emitted. */
    if (event.type === "turn/end") {
      const waiters = this.quietWaiters.get(room.id);
      this.quietWaiters.delete(room.id);
      queueMicrotask(() => {
        this.flush(room);
        for (const w of waiters ?? []) w();
      });
    } else if (event.type === "user/message") {
      const source = (event.data as MessageLike | undefined)?.source;
      if (source?.kind === "user") queueMicrotask(() => this.onOperatorSend(room));
    }
  }

  /** Spec §4.4: every operator send resets the caps; a running round is superseded (its running turns finish). */
  private onOperatorSend(room: Room): void {
    room.roundsThisSend = 0;
    room.turnsThisSend = 0;
    if (room.active !== undefined) room.active.superseded = true;
  }

  /* ---------- the room log (deviation 2) ---------- */

  /** Queue a message for the room log and append it now if the log is quiet. */
  post(room: Room, message: MessageLike): void {
    room.outbox.push(message);
    this.flush(room);
  }

  private flush(room: Room): void {
    if (room.outbox.length === 0) return;
    const session = this.deps.ctx.sessions.get(room.id);
    if (session === undefined || !isQuiet(session)) return;
    for (const message of room.outbox.splice(0)) session.append("user/message", message, { surfaceOp: "append" });
  }

  /** Resolves once the room log has no open turn (immediately when it already has none). */
  whenQuiet(room: Room): Promise<void> {
    const session = this.deps.ctx.sessions.get(room.id);
    if (session !== undefined && isQuiet(session)) return Promise.resolve();
    return new Promise((resolve) => {
      const list = this.quietWaiters.get(room.id) ?? [];
      list.push(() => { void this.whenQuiet(room).then(resolve); });
      this.quietWaiters.set(room.id, list);
    });
  }

  private roomAgent(room: Room): AgentLike {
    const agent = this.deps.ctx.agents.get(room.id);
    if (agent === undefined) throw new Error(`room session ${room.id} is not live`);
    return agent;
  }

  /* ---------- members (spec §2.4, §4.1, §4.7) ---------- */

  async ensureMember(room: Room, bot: RosterBot): Promise<Member> {
    const have = room.members.get(bot.id);
    if (have !== undefined) return have;
    let pending = room.ensuring.get(bot.id);
    if (pending === undefined) {
      pending = this.materializeMember(room, bot).finally(() => room.ensuring.delete(bot.id));
      room.ensuring.set(bot.id, pending);
    }
    return pending;
  }

  /** preset.yml's route when the tree serves it, else the default with a visible note. Cached per room. */
  private async selectionFor(room: Room, bot: RosterBot): Promise<ModelSelectionLike> {
    const cached = room.selections.get(bot.id);
    if (cached !== undefined) return cached.selection;
    const fallback = this.deps.ctx.agentDefaultModel.currentSelection();
    let entry: { selection: ModelSelectionLike; note?: string } = { selection: { provider: fallback.provider, model: fallback.model } };
    if (bot.model !== undefined) {
      const route = parseModelRoute(bot.model);
      if (route === undefined) entry = { ...entry, note: `${bot.name}: preset.yml model "${bot.model}" is not one provider/model route; using the default route.` };
      else {
        try {
          await this.deps.ctx.llm.resolveCallConfig(route);
          entry = { selection: route };
        } catch {
          entry = { ...entry, note: `${bot.name}: model ${bot.model} is not served by this tree; using the default route.` };
        }
      }
    }
    room.selections.set(bot.id, entry);
    if (entry.note !== undefined) this.log(entry.note);
    return entry.selection;
  }

  /** The member's session on disk or in the room log, if it exists. */
  private async findMemberSession(room: Room, bot: string): Promise<string | undefined> {
    const live = this.deps.ctx.sessions.get(room.id);
    for (const event of live?.events ?? []) {
      if (event.type !== "user/message") continue;
      const source = (event.data as MessageLike | undefined)?.source as { kind?: unknown; bot?: unknown; sessionId?: unknown } | undefined;
      if (source?.kind === "room" && source.bot === bot && typeof source.sessionId === "string" && source.sessionId !== "") return source.sessionId;
    }
    const headers = await this.deps.ctx.sessionPersistence?.list() ?? [];
    const mine = headers
      .filter((h) => h.parentSession === room.id && h.agentPreset === bot && h.origin === undefined)
      .sort((a, b) => b.createdAt - a.createdAt);
    return mine[0]?.id;
  }

  private async materializeMember(room: Room, bot: RosterBot): Promise<Member> {
    const selection = await this.selectionFor(room, bot);
    const agentOptions = { provider: selection.provider, model: selection.model };
    const existing = await this.findMemberSession(room, bot.id);
    /* The gateway's own composeAgent, restated: the model selection ref, then the
     * preset join. Plus, for a NEW member, the read-only pin — INSIDE setup so it
     * is the session's first permission fact and no create→set window exists. */
    const setup = async (agentCtx: AgentCtxLike, pin: boolean): Promise<void> => {
      this.installSelection(agentCtx, { current: { ...selection }, assembled: undefined });
      await this.deps.ctx.agentPresets.mount(agentCtx, bot.id);
      if (pin) {
        const session = agentCtx.agent?.session;
        if (session === undefined) throw new Error("member setup has no scoped agent");
        this.deps.ctx.permissionPresets.set(session, "read-only");
      }
    };
    let agent: AgentLike;
    if (existing !== undefined) {
      agent = this.deps.ctx.agents.get(existing)
        ?? (await this.deps.ctx.agents.resume({ resumeSessionId: existing, agentOptions, setup: (agentCtx) => setup(agentCtx, false) })).agent;
    } else {
      const sessionId = `session-${randomUUID()}`;
      agent = (await this.deps.ctx.agents.create({
        sessionId,
        meta: { cwd: room.channel.dir, parentSession: room.id, agentPreset: bot.id },
        agentOptions,
        setup: (agentCtx) => setup(agentCtx, true),
      })).agent;
      const effective = this.deps.ctx.permissionPresets.current(agent.session.events);
      if (effective !== "read-only") throw new Error(`member session ${sessionId} for ${bot.id} is "${effective}", not read-only; refusing to prompt it`);
      const ws = await this.deps.ctx.workspaceRegistry.resolveByPath(room.channel.dir).catch(() => undefined);
      await ws?.attachSession(sessionId).catch((err: unknown) => this.log(`could not attach ${sessionId} to channel ${room.channel.name}: ${errText(err)}`));
    }
    const member: Member = { bot: bot.id, name: bot.name, agent, queue: Promise.resolve() };
    room.members.set(bot.id, member);
    return member;
  }

  /* ---------- one member turn (spec §4.2, §4.6) ---------- */

  /** Run `fn` after whatever this member is already doing (an `@` to a running member is queued, never refused). */
  enqueue<T>(member: Member, fn: () => Promise<T>): Promise<T> {
    const next = member.queue.then(fn, fn);
    member.queue = next.then(() => undefined, () => undefined);
    return next;
  }

  /** The delta this member has not seen: room lines (log + outbox) minus its cursor. */
  private deltaFor(room: Room, roster: readonly RosterBot[], member: Member): { text: string; messageIds: string[] } {
    const roomSession = this.deps.ctx.sessions.get(room.id);
    const lines = roomLinesOf(roomSession?.events ?? [], room.outbox, roster);
    const seen = seenIdsOf(member.agent.session.events);
    const fresh = lines.filter((line) => !seen.has(line.id));
    return { text: formatDelta(fresh, member.bot), messageIds: fresh.map((line) => line.id) };
  }

  async runMemberTurn(room: Room, member: Member, roster: readonly RosterBot[], trigger: TurnTrigger, brief?: string): Promise<MemberTurnResult> {
    const delta = this.deltaFor(room, roster, member);
    const text = memberPrompt({ roomName: room.channel.name, roster, self: member.bot, delta: delta.text, trigger, ...(brief === undefined ? {} : { brief }) });
    const message = createUserMessage({
      content: [{ type: "text", text }],
      source: { kind: "room", form: "delta", room: room.id, bot: member.bot, messageIds: delta.messageIds, trigger, ...(brief === undefined ? {} : { brief }) },
    });
    const outcome = await this.driveTurn(member, () => member.agent.followup(message as unknown as MessageLike));
    const base = { bot: member.bot, name: member.name, sessionId: member.agent.id };
    if (outcome.kind === "ended") {
      const reason = outcome.reason;
      if (reason.kind === "error") return { record: { ...base, turn: outcome.turn, state: "failed", reason: errorText(reason.error) }, text: "" };
      if (reason.kind === "aborted") return { record: { ...base, turn: outcome.turn, state: outcome.cancelledByUs ? "timed-out" : "failed", reason: outcome.cancelledByUs ? "turn hard cap" : "cancelled" }, text: "" };
      if (reason.kind === "interrupted") return { record: { ...base, turn: outcome.turn, state: "failed", reason: "interrupted" }, text: "" };
      const answer = finalTextOf(member.agent.session.events, outcome.turn);
      if (answer === "" || isPass(answer)) return { record: { ...base, turn: outcome.turn, state: "passed" }, text: "" };
      return { record: { ...base, turn: outcome.turn, state: "answered" }, text: answer };
    }
    return { record: { ...base, state: "failed", reason: outcome.reason }, text: "" };
  }

  /**
   * Start a turn on a member and wait for ITS `turn/end`. The turn is the first
   * `turn/start` after the send (members are single-driven through `enqueue`).
   * Deadline: the base timeout, extended while the member runs or has a gate
   * pending, up to the hard cap, which cancels (keeping the inbox).
   */
  private driveTurn(member: Member, start: () => void): Promise<
    { kind: "ended"; turn: number; reason: { kind: string; error?: unknown }; cancelledByUs: boolean } | { kind: "never-started"; reason: string }
  > {
    const session = member.agent.session;
    const sinceSeq = session.seq;
    const startedAt = this.clock.now();
    return new Promise((resolve) => {
      let turn: number | undefined;
      let timer: unknown;
      let cancelledByUs = false;
      let settled = false;
      const finish = (value: Parameters<typeof resolve>[0]): void => {
        if (settled) return;
        settled = true;
        this.clock.clearTimeout(timer);
        this.turnWaiters.delete(session.id);
        resolve(value);
      };
      const arm = (ms: number): void => {
        this.clock.clearTimeout(timer);
        timer = this.clock.setTimeout(check, ms);
      };
      const check = (): void => {
        const elapsed = this.clock.now() - startedAt;
        const running = member.agent.status === "running" || (turn !== undefined && gatePending(session.events, turn));
        if (elapsed < this.caps.turnHardCapMs && running) {
          arm(Math.min(this.caps.turnTimeoutMs, this.caps.turnHardCapMs - elapsed));
          return;
        }
        cancelledByUs = true;
        member.agent.cancel({ kind: "hook", reason: "room: turn hard cap reached" }, { keepInbox: true });
        /* The loop answers a cancel with `turn/end aborted`; if it does not, do not wait forever. */
        arm(5_000);
        if (turn === undefined) finish({ kind: "never-started", reason: "no turn opened before the deadline" });
        else if (elapsed >= this.caps.turnHardCapMs + 5_000) finish({ kind: "ended", turn, reason: { kind: "aborted" }, cancelledByUs: true });
      };
      this.turnWaiters.set(session.id, (event) => {
        if (event.seq < sinceSeq) return;
        const data = event.data as { turn?: number; reason?: { kind: string; error?: unknown } } | undefined;
        if (turn === undefined && event.type === "turn/start" && typeof data?.turn === "number") turn = data.turn;
        else if (event.type === "turn/end" && turn !== undefined && data?.turn === turn) {
          finish({ kind: "ended", turn, reason: data.reason ?? { kind: "completed" }, cancelledByUs });
        }
      });
      arm(this.caps.turnTimeoutMs);
      try {
        start();
      } catch (err) {
        finish({ kind: "never-started", reason: errText(err) });
      }
    });
  }
}

const errorText = (error: unknown): string => {
  const e = error as { code?: unknown; message?: unknown } | undefined;
  const code = typeof e?.code === "string" ? e.code : undefined;
  const message = typeof e?.message === "string" ? e.message : "";
  return code === undefined ? (message || "error") : (message === "" ? code : `${code}: ${message}`);
};
