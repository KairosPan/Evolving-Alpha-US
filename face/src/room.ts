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
  /** Every bot that has had a turn this round: one turn per member per round, so a
   * peer's `@` pulls in a voice that has not spoken rather than starting a duel. */
  called: Set<string>;
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

  /** Run `fn` when the engine is disposed (the tool and projection disposers). */
  onDispose(fn: () => void): void { this.disposers.push(fn); }

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

  /* ---------- rounds (spec §4.3, §4.4, §4.6) ---------- */

  /** The channel's bot roster, named: the file's ids with the display names dsh's roster reports. */
  async rosterFor(channel: RoomChannel): Promise<RosterBot[]> {
    const { rosters, corrupt } = await readRosters(this.deps.home);
    if (corrupt) throw new Error(`the channel roster is unreadable; repair ${this.deps.home}/face/channels.json`);
    if (!Object.hasOwn(rosters, channel.workspaceId)) throw new Error(`channel "${channel.name}" has no roster yet; it gets one the first time the channel list loads, and the operator checks bots in on the channel page`);
    const bots = await this.deps.listBots();
    return rosters[channel.workspaceId].bots.map((id) => {
      const row = bots.find((b) => b.id === id);
      return { id, name: row?.name ?? id, ...(row?.model === undefined ? {} : { model: row.model }), ...(row?.broken === undefined ? {} : { broken: row.broken }) };
    });
  }

  /**
   * Start a round for Kairos and return at once (the tool result tells the model
   * to end its turn). Refuses on the round cap and while a round is unsettled.
   */
  async dispatch(agentId: string, channel: RoomChannel, args: DispatchArgs, roster: readonly RosterBot[]): Promise<{ round: number; remainingRounds: number; notCalled: string[]; notes: string[] }> {
    const room = this.roomOf(agentId, channel);
    if (room.active !== undefined && !room.active.superseded) {
      throw new Error(`round ${room.active.n} is still running (${room.active.turns.length} of its turns have ended); end your turn and dispatch again when you are woken`);
    }
    if (room.roundsThisSend >= this.caps.maxRounds) {
      throw new Error(`the round cap (${this.caps.maxRounds} per operator message) is reached; reply to the operator now`);
    }
    room.roundsThisSend++;
    const round: Round = { n: room.roundsThisSend, mode: args.mode, superseded: false, capped: false, called: new Set(), continuations: [], continuationsRun: 0, turns: [] };
    room.active = round;
    const notes: string[] = [];
    for (const id of args.to) {
      const bot = roster.find((b) => b.id === id);
      if (bot === undefined) continue;
      await this.selectionFor(room, bot);
      const note = this.noteFor(room, id);
      if (note !== undefined) notes.push(note);
    }
    void this.runRound(room, round, args.to, roster, "dispatch", args.brief).catch((err: unknown) => this.log(`round ${round.n} in ${room.channel.name} failed: ${errText(err)}`));
    return {
      round: round.n,
      remainingRounds: this.caps.maxRounds - room.roundsThisSend,
      notCalled: roster.filter((b) => !args.to.includes(b.id)).map((b) => b.id),
      notes,
    };
  }

  private answerMessage(record: RoomTurnRecord, text: string, round: number): MessageLike {
    return createUserMessage({
      content: [{ type: "text", text }],
      source: { kind: "room", form: "answer", bot: record.bot, name: record.name, sessionId: record.sessionId, turn: record.turn ?? 0, round },
    }) as unknown as MessageLike;
  }

  private async runRound(room: Room, round: Round, to: readonly string[], roster: readonly RosterBot[], trigger: TurnTrigger, brief?: string): Promise<void> {
    /* Everything before the prompt: the roster row, the caps, the member session.
     * A parallel round overlaps the TURNS, not the member sessions coming up, so
     * this runs in `to` order there too and every voice is prompted in the order
     * it was named - however many awaits its model route happens to cost. */
    const prepare = async (id: string): Promise<Member | undefined> => {
      const bot = roster.find((b) => b.id === id);
      if (bot === undefined || round.superseded) return undefined;
      round.called.add(id);
      if (room.turnsThisSend >= this.caps.maxBotMessages) { round.capped = true; return undefined; }
      room.turnsThisSend++;
      try {
        return await this.ensureMember(room, bot);
      } catch (err) {
        round.turns.push({ bot: id, name: bot.name, sessionId: "", state: "failed", reason: errText(err) });
        return undefined;
      }
    };
    const drive = async (member: Member, trig: TurnTrigger): Promise<void> => {
      const result = await this.enqueue(member, () => this.runMemberTurn(room, member, roster, trig, brief));
      round.turns.push(result.record);
      if (result.record.state !== "answered") return;
      this.post(room, this.answerMessage(result.record, result.text, round.n));
      /* Spec §4.4 rule 2: a peer's `@` pulls in ONE continuation turn for a voice
       * that has not spoken this round - `called` is what makes "one continuation
       * for macro however many peers named it" true, and keeps two members that
       * name each other from trading turns inside one round. */
      for (const peer of resolveMentions(result.text, roster.filter((b) => b.id !== member.bot))) {
        if (round.called.has(peer) || round.continuations.includes(peer)) continue;
        if (round.continuationsRun + round.continuations.length >= this.caps.maxContinuations) break;
        round.continuations.push(peer);
      }
    };
    const runOne = async (id: string, trig: TurnTrigger): Promise<void> => {
      const member = await prepare(id);
      if (member !== undefined) await drive(member, trig);
    };
    if (round.mode === "serial") { for (const id of to) await runOne(id, trigger); }
    else {
      const members: (Member | undefined)[] = [];
      for (const id of to) members.push(await prepare(id));
      await Promise.all(members.map(async (member) => { if (member !== undefined) await drive(member, trigger); }));
    }
    while (!round.superseded && round.continuations.length > 0) {
      const id = round.continuations.shift() as string;
      /* A serial round queues a peer before that peer's OWN dispatched turn has
       * been prepared, so `called` is read here too, not only where continuations
       * are queued: one turn per member per round, whatever the mode. Its slot is
       * not spent - a voice that has not yet spoken can take it. */
      if (round.called.has(id)) continue;
      round.continuationsRun++;
      await runOne(id, "continuation");
    }
    const outcome: RoundOutcome = round.superseded ? "superseded" : round.capped ? "capped" : "settled";
    if (trigger === "dispatch") await this.finishRound(room, round, outcome);
    if (room.active === round) room.active = undefined;
  }

  /** Every buffered answer onto the log, then the ONE wake - one synchronous block once the log is quiet. */
  private async finishRound(room: Room, round: Round, outcome: RoundOutcome): Promise<void> {
    await this.whenQuiet(room);
    this.flush(room);
    const text = roundEndText(round.n, outcome, round.turns, Math.max(0, this.caps.maxRounds - room.roundsThisSend));
    const end = createUserMessage({
      content: [{ type: "text", text }],
      source: { kind: "room", form: "round-end", round: round.n, outcome, turns: round.turns },
    });
    this.roomAgent(room).followup(end as unknown as MessageLike);
  }

  /* ---------- the operator's `@` (spec §4.4 rule 1) ---------- */

  /** The channel a session belongs to, live or cold; `null` when it is in none. */
  private async channelOf(sessionId: string): Promise<RoomChannel | null> {
    const live = this.deps.ctx.sessions.get(sessionId);
    let cwd = live?.header.cwd;
    if (cwd === undefined) cwd = (await this.deps.ctx.sessionPersistence?.list() ?? []).find((h) => h.id === sessionId)?.cwd;
    return this.deps.channelFor(cwd);
  }

  /** A cold room session becomes live through the gateway's OWN composition path
   * (`session.models` resumes via its agent resolver and changes nothing else),
   * so the face never composes Kairos's session itself. */
  private async ensureLive(sessionId: string): Promise<AgentLike> {
    const live = this.deps.ctx.agents.get(sessionId);
    if (live !== undefined) return live;
    if (this.deps.ctx.apiProxy === undefined) throw new HttpError(409, "the room session is not live and the gateway is not available to resume it");
    await this.deps.ctx.apiProxy.sessions.models({ rpcId: `room-${randomUUID()}`, payload: { sessionId } });
    const resumed = this.deps.ctx.agents.get(sessionId);
    if (resumed === undefined) throw new HttpError(404, "no such session");
    return resumed;
  }

  /**
   * The operator's `@`: resolved against the roster deterministically, appended
   * to the room as the operator's own message (never a prompt - Kairos sees it
   * on its next wake), and each named member turns on the standard delta. A
   * member mid-turn takes it after that turn. Resets the caps like every send.
   */
  async say(sessionId: string, text: string): Promise<{ addressed: string[] }> {
    const channel = await this.channelOf(sessionId);
    if (channel === null) throw new HttpError(404, "this session is in no channel");
    const roster = await this.rosterFor(channel).catch((err: unknown) => { throw new HttpError(409, errText(err)); });
    const addressed = resolveMentions(text, roster);
    if (addressed.length === 0) return { addressed: [] };
    await this.ensureLive(sessionId);
    const room = this.roomOf(sessionId, channel);
    const message = createUserMessage({ content: [{ type: "text", text }], source: { kind: "user", mention: addressed } });
    this.post(room, message as unknown as MessageLike);
    this.onOperatorSend(room);
    const round: Round = { n: room.active?.n ?? 0, mode: "mention", superseded: false, capped: false, called: new Set(), continuations: [], continuationsRun: 0, turns: [] };
    void this.runRound(room, round, addressed, roster, "mention").catch((err: unknown) => this.log(`@ turn in ${room.channel.name} failed: ${errText(err)}`));
    return { addressed };
  }

  /** What the client asks about a room: the roster, the members this engine drove, the caps left. Never resumes anything. */
  async describe(sessionId: string): Promise<{ roster: RosterBot[]; members: Record<string, { sessionId: string; name: string }>; caps: { roundsLeft: number; messagesLeft: number; maxRounds: number; maxBotMessages: number }; round?: { n: number; mode: string; superseded: boolean } }> {
    const channel = await this.channelOf(sessionId);
    if (channel === null) throw new HttpError(404, "this session is in no channel");
    const roster = await this.rosterFor(channel).catch(() => [] as RosterBot[]);
    const room = this.rooms.get(sessionId);
    const members: Record<string, { sessionId: string; name: string }> = {};
    for (const [bot, member] of room?.members ?? []) members[bot] = { sessionId: member.agent.id, name: member.name };
    return {
      roster,
      members,
      caps: {
        roundsLeft: Math.max(0, this.caps.maxRounds - (room?.roundsThisSend ?? 0)),
        messagesLeft: Math.max(0, this.caps.maxBotMessages - (room?.turnsThisSend ?? 0)),
        maxRounds: this.caps.maxRounds,
        maxBotMessages: this.caps.maxBotMessages,
      },
      ...(room?.active === undefined ? {} : { round: { n: room.active.n, mode: room.active.mode, superseded: room.active.superseded } }),
    };
  }
}

const errorText = (error: unknown): string => {
  const e = error as { code?: unknown; message?: unknown } | undefined;
  const code = typeof e?.code === "string" ? e.code : undefined;
  const message = typeof e?.message === "string" ? e.message : "";
  return code === undefined ? (message || "error") : (message === "" ? code : `${code}: ${message}`);
};

/* ---------- the tool (spec §4.3) ---------- */

const DISPATCH_DESCRIPTION =
  "Ask the bots on this channel's roster for their views, each in its own voice. You are the organizer: choose whom (bot ids " +
  "from the roster), the mode (parallel: everyone answers independently and sees no peer this round - use it first on a fresh " +
  "question; serial: each later bot sees the earlier answers), a brief (the question or task for this batch) and a reason " +
  "(why these, why this mode - it lands in the transcript). The call returns at once; END YOUR TURN after it. You will be " +
  "woken once when the round ends, with who answered and who passed; every answer will be in this conversation, attributed. " +
  "Then name the disagreements before you conclude. A bot that is not on the roster cannot be called; the refusal names the " +
  "roster. Caps per operator message: 3 rounds, 10 bot messages, 2 peer continuations per round. Dispatch grants a bot nothing.";

export function dispatchToolDefinition(engine: RoomEngine, deps: Pick<RoomDeps, "channelFor">): RoomToolDefinition {
  return {
    name: "dispatch",
    description: DISPATCH_DESCRIPTION,
    parameters: {
      type: "object",
      properties: {
        to: { type: "array", items: { type: "string" }, description: "bot ids from this channel's roster, in speaking order for serial" },
        mode: { type: "string", enum: ["parallel", "serial"] },
        brief: { type: "string", description: "the question or task for this batch" },
        reason: { type: "string", description: "why these bots, why this mode" },
      },
      required: ["to", "mode", "brief", "reason"],
      additionalProperties: false,
    },
    output: {
      schema: {
        type: "object",
        properties: { text: { type: "string" }, round: { type: "number" }, called: { type: "array", items: { type: "string" } }, notCalled: { type: "array", items: { type: "string" } } },
        required: ["text", "round", "called", "notCalled"],
        additionalProperties: false,
      },
      render: (_args, value) => [{ type: "text", text: (value as { text: string }).text }],
    },
    timeoutMs: 30_000,
    async execute(args, exec) {
      const agent = exec.agent;
      if (agent === undefined) throw new Error("dispatch needs a session to run in");
      const preset = agent.session.header.agentPreset;
      if (preset !== undefined && preset !== DEFAULT_PRESET) throw new Error("dispatch is Kairos's tool; a voice does not dispatch");
      const channel = await deps.channelFor(agent.session.header.cwd);
      if (channel === null) throw new Error("dispatch works in a channel session; this session is in no channel");
      const roster = await engine.rosterFor(channel);
      const valid = validateDispatch(args, roster);
      if (!valid.ok) throw new Error(valid.message);
      const started = await engine.dispatch(agent.id, channel, valid.value, roster);
      return {
        text: dispatchResultText(valid.value, roster, started.round, started.remainingRounds, started.notes),
        round: started.round,
        called: valid.value.to,
        notCalled: started.notCalled,
      };
    },
    presentCall(args) {
      const a = (args !== null && typeof args === "object" ? args : {}) as { to?: unknown; mode?: unknown; reason?: unknown };
      const to = Array.isArray(a.to) ? a.to.filter((x): x is string => typeof x === "string").join(", ") : "?";
      return { card: "generic", title: `dispatch ${to} (${typeof a.mode === "string" ? a.mode : "?"})`, kind: "read", rawInput: typeof a.reason === "string" ? a.reason.slice(0, 200) : undefined };
    },
  };
}

/* ---------- install ---------- */

/** Register the tool, the projection unit and the bus on the ROOT context. Returns the engine; `dispose()` unwinds all three. */
export function installRoom(deps: RoomDeps): RoomEngine {
  const engine = new RoomEngine(deps);
  const unregister = deps.ctx.tools.register(dispatchToolDefinition(engine, deps));
  const registry = deps.ctx.sessionProjections;
  const unproject = registry === undefined ? undefined : registerRoomProjection(registry as unknown as Parameters<typeof registerRoomProjection>[0]);
  if (registry === undefined) deps.ctx.logger?.warn(`${BIN}: sessionProjections is not in the tree; the room strip will have no state`);
  engine.onDispose(() => { unregister(); unproject?.(); });
  return engine;
}

/* ---------- routes ---------- */

export function registerRoomRoutes(webServer: RouteRegistrar, engine: RoomEngine): void {
  const send = (res: ServerResponse, status: number, body: unknown): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(typeof body === "string" ? body : JSON.stringify(body));
  };
  const post = (act: (body: Record<string, unknown>) => Promise<object>) =>
    async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      if (req.method !== "POST") return send(res, 405, { ok: false, error: "POST only" });
      if (!isJsonBody(req)) return send(res, 415, { ok: false, error: "application/json only" });
      try {
        let body: Record<string, unknown>;
        try {
          const parsed: unknown = JSON.parse(await readBody(req, 16_384));
          if (parsed === null || typeof parsed !== "object") throw new Error("not an object");
          body = parsed as Record<string, unknown>;
        } catch (err) {
          if (err instanceof HttpError) throw err;
          throw new HttpError(400, "body must be a JSON object");
        }
        if (typeof body.sessionId !== "string" || !SESSION_ID_RE.test(body.sessionId)) throw new HttpError(400, "invalid session id");
        return send(res, 200, { ok: true, ...(await act(body)) });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        console.error(`${BIN}: room route failed:`, err);
        return send(res, 500, { ok: false, error: "request failed" });
      }
    };
  webServer.register({ kind: "exact", path: "/data/rooms/say", handler: post(async (body) => {
    if (typeof body.text !== "string" || body.text.trim() === "") throw new HttpError(400, "text required");
    return engine.say(body.sessionId as string, body.text);
  }) });
  webServer.register({ kind: "exact", path: "/data/rooms/state", handler: post(async (body) => engine.describe(body.sessionId as string)) });
}
