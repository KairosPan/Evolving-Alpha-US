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
 * `kind: 'room'` is a native v4 message source (dsh 0.2 admits any non-empty
 * kind but `plugin`, NEW packages/session/session-format-v3-to-v4/src/message-sources.ts:7-11),
 * so logs this engine writes now reload. Logs written under dsh 0.1.1 do NOT:
 * the v2→v3 migration edge refuses every `user/message` whose kind it does not
 * know (NEW packages/session/session-format-v2-to-v3/src/payload.ts:10, 81, 110-114),
 * so a pre-0.2 room or member session fails to OPEN. The engine tolerates that
 * per member and per request, naming the legacy format, and never rewrites the
 * operator's logs (plan D11).
 *
 * HOW THE LOG IS READ: `session.snapshotEvents()` - dsh 0.2 removed the
 * `events` getter (commit 5660f44d29; NEW packages/core/session/src/index.ts:649-661,
 * deprecated for new callers but still upstream's own read, e.g.
 * NEW packages/api/session-controller/src/index.ts:229-241). Every read goes
 * through `eventsOf`/`unreadableLog`, so a later pin that drops it too fails
 * closed and says so instead of iterating `undefined`.
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
import { BRIEF_SCHEMA, formatDiscussionSummary, parseMemberView, type DiscussionSummary, type RoomBrief } from "./room-contract.ts";
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
  /** The whole log as one frozen snapshot, cached by dsh until the next append
   * (NEW packages/core/session/src/index.ts:649-661). Read it through `eventsOf`. */
  snapshotEvents(): readonly EventLike[];
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
/** The agent-scoped cordis `Context` that `setup` receives, held opaquely: the
 * engine only hands it back to dsh (`installModelSelection`, `agentPresets.mount`).
 * It no longer carries the agent - `Context.agent` was deleted (commit
 * ebce3a5f04) and the agent is `setup`'s SECOND argument now. */
export type AgentCtxLike = object;
/** dsh-agent's `AgentSetup` is `(agentCtx, agent)` (NEW packages/core/agent/src/index.ts:51-54);
 * the loop awaits it before inserting or announcing the session or the agent
 * (:100-112), which is what makes a pin inside it the member's first fact. */
export type MemberSetup = (agentCtx: AgentCtxLike, agent: AgentLike) => Promise<void>;
export interface CreateMemberOptions {
  sessionId: string;
  /** No `parentAgent`: omitting it makes the member a runtime ROOT (NEW packages/core/agent/src/index.ts:66-67). */
  meta: { cwd: string; parentSession: string; agentPreset: string };
  agentOptions: { provider: string; model: string };
  setup: MemberSetup;
}
export interface ResumeMemberOptions { resumeSessionId: string; agentOptions: { provider: string; model: string }; setup: MemberSetup }
/** dsh-session's `SessionHeader`, narrowed (NEW packages/core/session/src/types.ts:93-129). */
export interface PersistedHeaderLike { id: string; cwd?: string; parentSession?: string; agentPreset?: string; origin?: string; createdAt: number }
/** dsh-session-persistence's `SessionPersistenceSnapshot`: `list()` now returns
 * `{header, revision, …}` rows, not bare headers (NEW packages/session/session-persistence/src/index.ts:50-58, 201;
 * upstream maps `s.header`, NEW packages/workspace/workspace/src/index.ts:825-827). */
export interface PersistedSnapshotLike { readonly header: PersistedHeaderLike }
/** The session domain's resolve result (NEW packages/api/session-controller/src/agent.ts:61-66):
 * the live agent, or a `RemoteError` with a slash-namespaced `code`. */
export type ResolveAgentResultLike = { readonly agent: AgentLike } | { readonly error: { readonly code?: string; readonly message: string } };
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
  sessionPersistence?: { list(): Promise<readonly PersistedSnapshotLike[]> };
  tools: { register(definition: RoomToolDefinition): () => void };
  /** `stateOf(session, 'agentPreset')` is the preset a session RUNS - the header
   * is only the one it started with (NEW packages/preset/agent-preset-registry/src/session.ts:1-15;
   * NEW packages/session/session-projection/src/index.ts:319). */
  sessionProjections?: { register(definition: never): () => void; stateOf?(session: SessionLike, key: "agentPreset"): unknown };
  /** `current` folds the `permissions` projection of a SESSION now, not an event
   * list (NEW packages/interaction/permission-presets/src/index.ts:343-345; `set` :398-400). */
  permissionPresets: { set(session: SessionLike, name: string): void; current(session: SessionLike): string };
  agentPresets: { mount(agentCtx: AgentCtxLike, id: string): Promise<unknown> };
  agentDefaultModel: { currentSelection(): ModelSelectionLike };
  llm: { resolveCallConfig(config: { provider: string; model: string }): Promise<unknown> };
  workspaceRegistry: { resolveByPath(path: string): Promise<{ attachSession(id: string): Promise<void> } | undefined> };
  /** The session domain (service `sessionController`, NEW packages/api/session-controller/src/index.ts:71-76):
   * `resolveAgent` resumes a cold session through the host's OWN composition
   * (`composeAgent` = model selection + preset mount, agent.ts:381-397) - the
   * successor of 0.1.1's `apiProxy.sessions.models` path (see `ensureLive`). */
  sessionController?: { resolveAgent(sessionId: string): Promise<ResolveAgentResultLike> };
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
  /** Self-reported views, never an inferred consensus or organizer verdict. */
  discussion?: DiscussionSummary;
}
export interface Room {
  id: string;
  channel: RoomChannel;
  members: Map<string, Member>;
  ensuring: Map<string, Promise<Member>>;
  selections: Map<string, { selection: ModelSelectionLike; note?: string }>;
  /** Messages for the room log, waiting for a quiet log (deviation 2). */
  outbox: MessageLike[];
  /** Ids of the operator messages THIS engine posted (`say`), so the bus does
   * not read one back as a second, later operator send. */
  posted: Set<string>;
  roundsThisSend: number;
  turnsThisSend: number;
  active?: Round;
}

const errText = (err: unknown): string => (err instanceof Error ? err.message : String(err));
const defaultClock: RoomClock = { now: () => Date.now(), setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: (h) => clearTimeout(h as NodeJS.Timeout) };

/** Why this session's log cannot be read here, or `undefined` when it can.
 * The structural `SessionLike` cast hides a missing reader from `tsc`, so the
 * check is made at runtime, with the reason spelled out. */
export function unreadableLog(session: SessionLike): string | undefined {
  return typeof (session as Partial<SessionLike>).snapshotEvents === "function" ? undefined
    : `session ${session.id} exposes no snapshotEvents(): the dsh Session API moved under the face, so the room engine cannot read this log`;
}

/** The session's whole log, or a throw that names the drift (never `undefined`). */
export function eventsOf(session: SessionLike): readonly EventLike[] {
  const reason = unreadableLog(session);
  if (reason !== undefined) throw new Error(reason);
  return session.snapshotEvents();
}

/** No open turn on this log: the last `turn/start` has its `turn/end`.
 * FAILS CLOSED on an unreadable log: `false` keeps answers in the outbox rather
 * than dropping a user message between a tool call and its result. The callers
 * that can speak (`flush`, `whenQuiet`) report `unreadableLog`'s reason. */
export function isQuiet(session: SessionLike): boolean {
  if (unreadableLog(session) !== undefined) return false;
  const events = session.snapshotEvents();
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
      /* dsh 0.2's first-class tool-role message: `{role:'tool', toolCallId, isError?}`
       * on the MESSAGE (NEW packages/llm/llm/src/message.ts:173-180, built by
       * `createToolResultMessage` :299-306). The 0.1.1 wrapper put it in
       * `content[0]`; that shape is never read here - a live Session holds only
       * v4 events, because the v3→v4 edge lifts every stored wrapper on load
       * (NEW packages/session/session-format-v3-to-v4/src/tool-role.ts:27-60). */
      const callId = (data.message as { toolCallId?: unknown } | undefined)?.toolCallId;
      if (typeof callId === "string") openAsks.delete(callId);
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
  /** room session id → the rounds waiting for that log to go quiet. `retry`
   * re-reads the log after a `turn/end`; `fail` settles the round when the
   * engine is disposed rather than leaving it pending forever. */
  private readonly quietWaiters = new Map<string, Array<{ retry(): void; fail(err: Error): void }>>();
  /** Every armed deadline, so `dispose` disarms them: a timer that outlives the
   * engine can still cancel a member of a room nothing is driving any more. */
  private readonly timers = new Set<unknown>();
  private readonly disposers: Array<() => void> = [];
  readonly caps: RoomCaps;
  private readonly clock: RoomClock;
  private readonly installSelection: NonNullable<RoomDeps["installModelSelection"]>;
  private readonly log: (line: string) => void;

  constructor(private readonly deps: RoomDeps) {
    this.caps = { ...ROOM_CAPS, ...deps.caps };
    this.clock = deps.clock ?? defaultClock;
    /* dsh-agent-loop calls `setup(prepared.agent.ctx, prepared.agent)` (commit
     * ebce3a5f04), so `setup`'s first argument IS the agent-scoped cordis
     * `Context` this wants; `AgentCtxLike` holds it opaquely, hence the cast.
     * The ref is NOT cast — it is checked against dsh's own `ModelSelectionRef`
     * (NEW packages/core/agent/src/model-selection.ts:81). */
    this.installSelection = deps.installModelSelection ?? ((agentCtx, ref) => installDshModelSelection(agentCtx as unknown as Context, ref));
    this.log = deps.log ?? ((line) => console.log(`${BIN}: ${line}`));
    const off = deps.ctx.on("session/event", (session, event) => this.onEvent(session, event));
    this.disposers.push(() => { off(); });
  }

  dispose(): void {
    for (const handle of [...this.timers]) this.clock.clearTimeout(handle);
    this.timers.clear();
    this.turnWaiters.clear();
    for (const waiters of [...this.quietWaiters.values()]) for (const waiter of waiters) waiter.fail(new Error("the room engine was disposed"));
    this.quietWaiters.clear();
    for (const d of this.disposers.splice(0)) d();
  }

  /** Arm a deadline this engine can disarm on `dispose`. */
  private arm(fn: () => void, ms: number): unknown {
    let handle: unknown;
    handle = this.clock.setTimeout(() => { this.timers.delete(handle); fn(); }, ms);
    this.timers.add(handle);
    return handle;
  }

  private disarm(handle: unknown): void {
    if (handle === undefined) return;
    this.timers.delete(handle);
    this.clock.clearTimeout(handle);
  }

  /** Run `fn` when the engine is disposed (the tool and projection disposers). */
  onDispose(fn: () => void): void { this.disposers.push(fn); }

  /** The runtime for a room session; created on first sight. */
  roomOf(agentId: string, channel: RoomChannel): Room {
    let room = this.rooms.get(agentId);
    if (room === undefined) {
      room = { id: agentId, channel, members: new Map(), ensuring: new Map(), selections: new Map(), outbox: [], posted: new Set(), roundsThisSend: 0, turnsThisSend: 0 };
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
      /* A throw inside a microtask is an UNCAUGHT exception - main.ts answers
       * one by tearing the face down - so each reaction carries its own guard. */
      queueMicrotask(() => {
        this.guard(room, "flush the room log", () => this.flush(room));
        for (const waiter of waiters ?? []) this.guard(room, "wake a round waiting for a quiet log", () => waiter.retry());
      });
    } else if (event.type === "user/message") {
      const message = event.data as MessageLike | undefined;
      if (message?.source?.kind !== "user") return;
      /* `say` posts the operator's `@` and resets the caps in the same breath,
       * but when Kairos is mid-turn that message waits in the outbox and lands
       * on the log a turn LATER - after a round Kairos dispatched in between.
       * Log order is not wall order here, so an engine-posted message is never
       * read back as a fresh send: it would supersede a round that in fact came
       * after it and hand Kairos a second set of caps. */
      if (typeof message.id === "string" && room.posted.delete(message.id)) return;
      queueMicrotask(() => this.guard(room, "record the operator's send", () => this.onOperatorSend(room)));
    }
  }

  /** Run a bus reaction, logging rather than throwing into the microtask queue. */
  private guard(room: Room, what: string, fn: () => void): void {
    try {
      fn();
    } catch (err) {
      this.log(`could not ${what} in ${room.channel.name}: ${errText(err)}`);
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
    if (message.source.kind === "user" && typeof message.id === "string") room.posted.add(message.id);
    room.outbox.push(message);
    this.flush(room);
  }

  private flush(room: Room): void {
    if (room.outbox.length === 0) return;
    const session = this.deps.ctx.sessions.get(room.id);
    if (session === undefined) return;
    const unreadable = unreadableLog(session);
    if (unreadable !== undefined) {
      this.log(`${unreadable}; ${room.outbox.length} message(s) stay in the outbox of ${room.channel.name}`);
      return;
    }
    if (!isQuiet(session)) return;
    for (const message of room.outbox.splice(0)) session.append("user/message", message, { surfaceOp: "append" });
  }

  /**
   * Resolves once the room log has no open turn (immediately when it already
   * has none) and REJECTS when there is no such session any more: only a
   * `turn/end` on that very log can settle a waiter, so a room session that was
   * deleted or disposed mid-round would otherwise never wake its round.
   */
  whenQuiet(room: Room): Promise<void> {
    const session = this.deps.ctx.sessions.get(room.id);
    if (session === undefined) return Promise.reject(new Error(`room session ${room.id} is not live`));
    /* An unreadable log never reads quiet, so waiting would be forever: refuse with the reason. */
    const unreadable = unreadableLog(session);
    if (unreadable !== undefined) return Promise.reject(new Error(unreadable));
    if (isQuiet(session)) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const list = this.quietWaiters.get(room.id) ?? [];
      list.push({ retry: () => { this.whenQuiet(room).then(resolve, reject); }, fail: reject });
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

  /** The member's session on disk or in the room log, if it STILL exists. */
  private async findMemberSession(room: Room, bot: string): Promise<string | undefined> {
    const live = this.deps.ctx.sessions.get(room.id);
    let logged: string | undefined;
    for (const event of live === undefined ? [] : eventsOf(live)) {
      if (event.type !== "user/message") continue;
      const source = (event.data as MessageLike | undefined)?.source as { kind?: unknown; bot?: unknown; sessionId?: unknown } | undefined;
      if (source?.kind === "room" && source.bot === bot && typeof source.sessionId === "string" && source.sessionId !== "") { logged = source.sessionId; break; }
    }
    /* The log is a record of what WAS: the operator can delete a member session
     * from the sidebar afterwards. Resuming an id that is gone throws "not
     * found" on every round for as long as that answer stays in the log, so the
     * id is confirmed against the session store before it is trusted; when it
     * is gone the header scan and, failing that, creation take over. */
    if (logged !== undefined && this.deps.ctx.agents.get(logged) !== undefined) return logged;
    /* Snapshots, not headers, since dsh 0.2: reading `h.id` off a snapshot is
     * `undefined`, which never matched - every round after a restart created a
     * fresh member and orphaned the old one. A `list()` that throws is NOT
     * read as "no sessions" (that would fork the member silently): it fails
     * this member's turn, visibly, through `prepare`. */
    const headers = (await this.deps.ctx.sessionPersistence?.list() ?? []).map((s) => s.header);
    if (logged !== undefined) {
      if (headers.some((h) => h.id === logged)) return logged;
      this.log(`${bot}'s member session ${logged} in ${room.channel.name} is gone from the session store; looking for a newer one`);
    }
    const mine = headers
      .filter((h) => h.parentSession === room.id && h.agentPreset === bot && h.origin === undefined)
      .sort((a, b) => b.createdAt - a.createdAt);
    return mine[0]?.id;
  }

  private async materializeMember(room: Room, bot: RosterBot): Promise<Member> {
    const selection = await this.selectionFor(room, bot);
    const agentOptions = { provider: selection.provider, model: selection.model };
    const existing = await this.findMemberSession(room, bot.id);
    /* The host's own composeAgent, restated (NEW packages/api/session-controller/src/agent.ts:381-397):
     * the model selection ref, then the preset join. Plus, for a NEW member,
     * the read-only pin - INSIDE setup, on setup's own `agent` argument (the
     * upstream pattern, same lines), so it lands before the session is
     * announced: dsh-permission-presets pins the user default on
     * `session/created` only when no permission fact exists yet
     * (NEW packages/interaction/permission-presets/src/index.ts:245-247, 428-456),
     * and there is no create→set window a prompt could slip through. */
    const setup = async (agentCtx: AgentCtxLike, agent: AgentLike, pin: boolean): Promise<void> => {
      this.installSelection(agentCtx, { current: { ...selection }, assembled: undefined });
      await this.deps.ctx.agentPresets.mount(agentCtx, bot.id);
      if (pin) this.deps.ctx.permissionPresets.set(agent.session, "read-only");
    };
    let agent: AgentLike;
    if (existing !== undefined) {
      const live = this.deps.ctx.agents.get(existing);
      if (live !== undefined) agent = live;
      else {
        try {
          agent = (await this.deps.ctx.agents.resume({ resumeSessionId: existing, agentOptions, setup: (agentCtx, a) => setup(agentCtx, a, false) })).agent;
        } catch (err) {
          /* Never fall back to a fresh member here: that would fork the voice's
           * memory silently. The turn fails with the reason (the round-end text
           * carries it to Kairos) and the log line tells the operator what to do. */
          const reason = memberResumeFailure(bot.id, existing, err);
          this.log(`${reason} (channel ${room.channel.name})`);
          throw new Error(reason);
        }
      }
    } else {
      const sessionId = `session-${randomUUID()}`;
      agent = (await this.deps.ctx.agents.create({
        sessionId,
        meta: { cwd: room.channel.dir, parentSession: room.id, agentPreset: bot.id },
        agentOptions,
        setup: (agentCtx, a) => setup(agentCtx, a, true),
      })).agent;
      /* Re-read AFTER publication, from the session itself: whatever the
       * announcement listeners appended, the member is prompted only read-only. */
      const effective = this.deps.ctx.permissionPresets.current(agent.session);
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
    const lines = roomLinesOf(roomSession === undefined ? [] : eventsOf(roomSession), room.outbox, roster);
    const seen = seenIdsOf(eventsOf(member.agent.session));
    const fresh = lines.filter((line) => !seen.has(line.id));
    return { text: formatDelta(fresh, member.bot), messageIds: fresh.map((line) => line.id) };
  }

  async runMemberTurn(room: Room, member: Member, roster: readonly RosterBot[], trigger: TurnTrigger, brief?: RoomBrief): Promise<MemberTurnResult> {
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
      const answer = finalTextOf(eventsOf(member.agent.session), outcome.turn);
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
        this.disarm(timer);
        this.turnWaiters.delete(session.id);
        resolve(value);
      };
      const arm = (ms: number): void => {
        this.disarm(timer);
        timer = this.arm(check, ms);
      };
      const check = (): void => {
        const elapsed = this.clock.now() - startedAt;
        /* This runs in a TIMER: a throw here is an uncaught exception, which
         * tears the face down (main.ts). An unreadable log counts as no gate -
         * the hard cap still bounds the turn - and says so. */
        let gate = false;
        if (turn !== undefined) {
          const unreadable = unreadableLog(session);
          if (unreadable === undefined) gate = gatePending(session.snapshotEvents(), turn);
          else this.log(`${unreadable}; ${member.bot}'s deadline counts only its running status`);
        }
        const running = member.agent.status === "running" || gate;
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

  private answerMessage(record: RoomTurnRecord, text: string, round: number, parsed: ReturnType<typeof parseMemberView>): MessageLike {
    return createUserMessage({
      content: [{ type: "text", text }],
      source: { kind: "room", form: "answer", bot: record.bot, name: record.name, sessionId: record.sessionId, turn: record.turn ?? 0, round,
        ...(parsed.view ? { view: parsed.view, displayText: parsed.prose || parsed.view.position } : {}),
        ...(parsed.issue ? { viewIssue: parsed.issue } : {}) },
    }) as unknown as MessageLike;
  }

  private async runRound(room: Room, round: Round, to: readonly string[], roster: readonly RosterBot[], trigger: TurnTrigger, brief?: RoomBrief): Promise<void> {
    const discussion: DiscussionSummary = { ...(brief === undefined ? {} : { brief }), views: [], unstructuredBots: [] };
    round.discussion = discussion;
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
      /* A member turn that THROWS (an unreadable log, say) is that member's
       * failed turn with its reason - never a rejected round, which would skip
       * `finishRound` and leave Kairos asleep with no round-end at all. */
      const result = await this.enqueue(member, () => this.runMemberTurn(room, member, roster, trig, brief))
        .catch((err: unknown): MemberTurnResult => ({ record: { bot: member.bot, name: member.name, sessionId: member.agent.id, state: "failed", reason: errText(err) }, text: "" }));
      round.turns.push(result.record);
      if (result.record.state !== "answered") return;
      const parsed = parseMemberView(result.text, roster.map((bot) => bot.id), member.bot);
      if (parsed.view) discussion.views.push({ bot: result.record.bot, name: result.record.name,
        sessionId: result.record.sessionId, ...(result.record.turn === undefined ? {} : { turn: result.record.turn }), view: parsed.view });
      else discussion.unstructuredBots.push(result.record.bot);
      this.post(room, this.answerMessage(result.record, result.text, round.n, parsed));
      /* Spec §4.4 rule 2: a peer's `@` pulls in ONE continuation turn for a voice
       * that has not spoken this round - `called` is what makes "one continuation
       * for macro however many peers named it" true, and keeps two members that
       * name each other from trading turns inside one round. */
      for (const peer of resolveMentions(parsed.prose, roster.filter((b) => b.id !== member.bot))) {
        if (round.called.has(peer) || round.continuations.includes(peer)) continue;
        if (round.continuationsRun + round.continuations.length >= this.caps.maxContinuations) break;
        round.continuations.push(peer);
      }
    };
    const runOne = async (id: string, trig: TurnTrigger): Promise<void> => {
      const member = await prepare(id);
      if (member !== undefined) await drive(member, trig);
    };
    /* `finally`, not a trailing statement: a round left `active` by a throw
     * refuses every later dispatch with "round N is still running" until the
     * operator happens to speak, and its answers never leave the outbox. */
    try {
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
    } finally {
      if (room.active === round) room.active = undefined;
    }
  }

  /** Every buffered answer onto the log, then the ONE wake - one synchronous
   * block once the log is quiet. A room session that is gone takes its wake and
   * its buffered answers with it; that is a log line, never a hang. */
  private async finishRound(room: Room, round: Round, outcome: RoundOutcome): Promise<void> {
    try {
      await this.whenQuiet(room);
      this.flush(room);
      const text = [roundEndText(round.n, outcome, round.turns, Math.max(0, this.caps.maxRounds - room.roundsThisSend)),
        ...(round.discussion ? [formatDiscussionSummary(round.discussion)] : [])].join("\n\n");
      const end = createUserMessage({
        content: [{ type: "text", text }],
        source: { kind: "room", form: "round-end", round: round.n, outcome, turns: round.turns,
          ...(round.discussion ? { discussion: round.discussion } : {}) },
      });
      this.roomAgent(room).followup(end as unknown as MessageLike);
    } catch (err) {
      this.log(`round ${round.n} in ${room.channel.name} could not be delivered: ${errText(err)}; ${round.turns.length} turn(s) ran, ${room.outbox.length} message(s) stay in the outbox`);
    }
  }

  /* ---------- the operator's `@` (spec §4.4 rule 1) ---------- */

  /** The channel a session belongs to, live or cold; `null` when it is in none. */
  private async channelOf(sessionId: string): Promise<RoomChannel | null> {
    const live = this.deps.ctx.sessions.get(sessionId);
    let cwd = live?.header.cwd;
    /* `.header`: persistence lists snapshots since dsh 0.2 (see `findMemberSession`). */
    if (cwd === undefined) cwd = (await this.deps.ctx.sessionPersistence?.list() ?? []).find((s) => s.header.id === sessionId)?.header.cwd;
    return this.deps.channelFor(cwd);
  }

  /** A cold room session becomes live through the host's OWN composition path:
   * `sessionController.resolveAgent` resumes it with the model selection and
   * preset join the session domain gives every session and changes nothing
   * else (NEW packages/api/session-controller/src/index.ts:215-221; agent.ts:147-230),
   * so the face never composes Kairos's session itself. Its failures are
   * results, not throws; each becomes the route's status with dsh's reason. */
  private async ensureLive(sessionId: string): Promise<AgentLike> {
    const live = this.deps.ctx.agents.get(sessionId);
    if (live !== undefined) return live;
    const controller = this.deps.ctx.sessionController;
    if (controller === undefined) throw new HttpError(409, "the room session is not live and the session controller is not in the tree to resume it");
    const resolved = await controller.resolveAgent(sessionId);
    if ("error" in resolved) {
      const { code, message } = resolved.error;
      if (code === "session/not-found") throw new HttpError(404, "no such session");
      throw new HttpError(409, `the room session could not be resumed (${code ?? "error"}: ${message})${isLegacyFormatText(message) ? LEGACY_HINT : ""}`);
    }
    return resolved.agent;
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

/* ---------- legacy logs (plan D11) ---------- */

/** dsh-session-format's refusals are `SessionFormatError` and its subclasses
 * (NEW packages/session/session-format/src/error.ts:2-9); the persistence
 * layer's is `SessionFormatUnsupportedError` (NEW packages/session/session-persistence/src/errors.ts:111).
 * The session domain flattens them into a `gateway/internal` message via
 * `String(error)` (NEW packages/api/session-controller/src/agent.ts:217-226),
 * so the NAME is what survives - matched in text, the one form both paths share. */
export const isLegacyFormatText = (text: string): boolean => /SessionFormat[A-Za-z]*Error|unclassified message source/.test(text);

const LEGACY_HINT = "; it looks like a log written before dsh 0.2, whose `room` messages the 0.2 migration refuses - the file stays on disk untouched";

/** Walk the error and its `cause` chain for a session-format refusal. */
function isLegacyFormatError(err: unknown): boolean {
  for (let e: unknown = err, depth = 0; e !== undefined && e !== null && depth < 8; e = (e as { cause?: unknown }).cause, depth++) {
    const name = (e as { name?: unknown }).name;
    if (typeof name === "string" && name.startsWith("SessionFormat")) return true;
    if (isLegacyFormatText(errText(e))) return true;
  }
  return false;
}

/** The model- and log-visible reason a member session could not be resumed. */
export function memberResumeFailure(bot: string, sessionId: string, err: unknown): string {
  return isLegacyFormatError(err)
    ? `${bot}'s member session ${sessionId} is unreadable under dsh 0.2 (legacy format: ${errText(err)})${LEGACY_HINT}; deleting that member session gives ${bot} a fresh one in this room (archiving does not: an archived session is still found)`
    : `${bot}'s member session ${sessionId} could not be resumed: ${errText(err)}`;
}

/* ---------- the tool (spec §4.3) ---------- */

/** The caps sentence is model-facing TRUTH: the numbers come from the engine
 * that enforces them, never from prose, because a wrong one here is invisible
 * to the type checker and to every test. */
export const dispatchDescription = (caps: RoomCaps): string =>
  "Ask the bots on this channel's roster for their views, each in its own voice. You are the organizer: choose whom (bot ids " +
  "from the roster), the mode (parallel: everyone answers independently and sees no peer this round - use it first on a fresh " +
  "question; serial: each later bot sees the earlier answers). Prefer a structured brief with question, context, evidence requirements, " +
  "falsification and desired output. Also give a reason " +
  "(why these, why this mode - it lands in the transcript). The call returns at once; END YOUR TURN after it. You will be " +
  "woken once when the round ends, with who answered and who passed; every answer will be in this conversation, attributed. " +
  "Then name the disagreements before you conclude. A bot that is not on the roster cannot be called; the refusal names the " +
  `roster. Caps per operator message: ${caps.maxRounds} ${caps.maxRounds === 1 ? "round" : "rounds"}, ` +
  `${caps.maxBotMessages} bot ${caps.maxBotMessages === 1 ? "message" : "messages"}, ` +
  `${caps.maxContinuations} peer ${caps.maxContinuations === 1 ? "continuation" : "continuations"} per round. ` +
  "Dispatch grants a bot nothing.";

/** Every preset this session is on record as: the header's creation value and,
 * when the tree has the `agentPreset` projection, the one it RUNS now - a
 * blank session re-selected to a bot keeps `kairos` in its frozen header
 * (NEW packages/preset/agent-preset-registry/src/session.ts:1-15, 36-46). */
function presetsOf(session: SessionLike, projections: RoomContextLike["sessionProjections"]): string[] {
  const out: string[] = [];
  if (session.header.agentPreset !== undefined) out.push(session.header.agentPreset);
  const running = projections?.stateOf?.(session, "agentPreset");
  if (typeof running === "string") out.push(running);
  return out;
}

export function dispatchToolDefinition(engine: RoomEngine, deps: Pick<RoomDeps, "channelFor"> & { ctx?: Pick<RoomContextLike, "sessionProjections"> }): RoomToolDefinition {
  return {
    name: "dispatch",
    description: dispatchDescription(engine.caps),
    parameters: {
      type: "object",
      properties: {
        to: { type: "array", items: { type: "string" }, description: "bot ids from this channel's roster, in speaking order for serial" },
        mode: { type: "string", enum: ["parallel", "serial"] },
        brief: BRIEF_SCHEMA,
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
      /* The 0.1.1 check read the header only. Both records are checked now and
       * EITHER naming a bot refuses - strictly narrower, never wider. The mask
       * already keeps `dispatch` out of a voice's roster; this is the second lock. */
      if (presetsOf(agent.session, deps.ctx?.sessionProjections).some((preset) => preset !== DEFAULT_PRESET)) throw new Error("dispatch is Kairos's tool; a voice does not dispatch");
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
