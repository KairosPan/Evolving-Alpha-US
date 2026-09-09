/** The `room` projection unit: the coarse state of a room, folded from the
 * KNOWN events that carry room facts (plan 2, deviation 1), served to clients
 * as one whole value per session through dsh's own carriers - the
 * `session/projection` push frame, the history tail page and, for a cold
 * session, the persisted cache row the face now mounts.
 *
 * Registered process-wide (dsh-session-projection: the unit table is not
 * per-session), so the key is in EVERY session's snapshot; its `none` value
 * means "not a room" and a client reads the VALUE, never the key's presence.
 *
 * Coarse only: `called`, `answered`, `passed`, `failed`, `timed-out` are log
 * facts. "Thinking / writing / calling a tool" are live pulses on the member
 * sessions' own feeds and the client's to read - the registry has no
 * out-of-fold write (plan 2, deviation 3).
 * @module
 */
import { z } from "zod";
import type { EventLike, MemberTurnState, RoundOutcome } from "./room-rules.ts";

export const ROOM_PROJECTION_KEY = "room";
/** Bump when the state fields or the fold change: the persisted cache
 * discards rows of another version instead of forward-applying garbage. */
export const ROOM_STATE_VERSION = 1;

export type MemberCoarseState = "called" | MemberTurnState;

export interface RoomMemberState {
  sessionId?: string;
  name?: string;
  state: MemberCoarseState;
  turn?: number;
}

export interface RoomState {
  kind: "none" | "room" | "member";
  /** room: the current or last round */
  round?: { n: number; mode: "parallel" | "serial" | "mention"; open: boolean; outcome?: RoundOutcome };
  /** room: the members of the current round, by bot id */
  members?: Record<string, RoomMemberState>;
  /** room: Kairos's turn is open */
  organizing?: boolean;
  /** member: the room session this member belongs to */
  room?: string;
  /** member: the bot */
  bot?: string;
}

const memberSchema = z.object({
  sessionId: z.string().optional(),
  name: z.string().optional(),
  state: z.enum(["called", "answered", "passed", "failed", "timed-out"]),
  turn: z.number().optional(),
});
export const roomStateSchema: z.ZodType<RoomState> = z.object({
  kind: z.enum(["none", "room", "member"]),
  round: z.object({
    n: z.number(),
    mode: z.enum(["parallel", "serial", "mention"]),
    open: z.boolean(),
    outcome: z.enum(["settled", "capped", "superseded"]).optional(),
  }).optional(),
  members: z.record(z.string(), memberSchema).optional(),
  organizing: z.boolean().optional(),
  room: z.string().optional(),
  bot: z.string().optional(),
});

export const initRoomState = (): RoomState => ({ kind: "none" });

type Source = { kind?: unknown; form?: unknown } & Record<string, unknown>;
const sourceOf = (message: unknown): Source | undefined => {
  const source = (message as { source?: unknown } | undefined)?.source;
  return source !== null && typeof source === "object" ? source as Source : undefined;
};

/** `none` becomes `room`; `room` stays; `member` is never promoted (a masked voice cannot dispatch). */
const asRoom = (state: RoomState): RoomState | undefined =>
  state.kind === "room" ? state : state.kind === "none" ? { kind: "room", members: {}, organizing: false } : undefined;

function withMember(state: RoomState, bot: string, patch: Partial<RoomMemberState> & { state: MemberCoarseState }): RoomState {
  const current = state.members?.[bot] ?? { state: "called" as const };
  return { ...state, members: { ...state.members, [bot]: { ...current, ...patch } } };
}

function applyAnswer(state: RoomState, message: unknown): RoomState {
  const source = sourceOf(message);
  if (source?.kind !== "room" || source.form !== "answer" || typeof source.bot !== "string") return state;
  const room = asRoom(state);
  if (room === undefined) return state;
  return withMember(room, source.bot, {
    state: "answered",
    ...(typeof source.sessionId === "string" ? { sessionId: source.sessionId } : {}),
    ...(typeof source.name === "string" ? { name: source.name } : {}),
    ...(typeof source.turn === "number" ? { turn: source.turn } : {}),
  });
}

function applyOperator(state: RoomState, source: Source): RoomState {
  const mention = Array.isArray(source.mention) ? source.mention.filter((m): m is string => typeof m === "string") : [];
  if (state.kind === "member") return state;
  if (state.kind === "none" && mention.length === 0) return state;
  const room = asRoom(state) as RoomState;
  const reset: RoomState = { ...room, members: {}, ...(room.round === undefined ? {} : { round: { ...room.round, open: false } }) };
  if (mention.length === 0) return reset;
  let next = reset;
  for (const bot of mention) next = withMember(next, bot, { state: "called" });
  return { ...next, round: { n: room.round?.n ?? 1, mode: "mention", open: true } };
}

/**
 * The pure transition. Returns the SAME reference for every event that is not
 * the unit's (the registry gates its change feed on `Object.is`).
 */
export function applyRoomEvent(state: RoomState, event: EventLike): RoomState {
  const data = event.data as Record<string, unknown> | undefined;
  switch (event.type) {
    case "user/message": {
      const source = sourceOf(data);
      if (source?.kind === "room") {
        if (source.form === "delta") {
          if (state.kind === "member") return state;
          return { kind: "member", ...(typeof source.room === "string" ? { room: source.room } : {}), ...(typeof source.bot === "string" ? { bot: source.bot } : {}) };
        }
        if (source.form === "answer") return applyAnswer(state, data);
        if (source.form === "round-end") {
          const room = asRoom(state);
          if (room === undefined) return state;
          let next = room;
          const turns = Array.isArray(source.turns) ? source.turns : [];
          for (const t of turns as Array<Record<string, unknown>>) {
            if (typeof t.bot !== "string" || typeof t.state !== "string") continue;
            next = withMember(next, t.bot, {
              state: t.state as MemberCoarseState,
              ...(typeof t.sessionId === "string" ? { sessionId: t.sessionId } : {}),
              ...(typeof t.name === "string" ? { name: t.name } : {}),
              ...(typeof t.turn === "number" ? { turn: t.turn } : {}),
            });
          }
          const n = typeof source.round === "number" ? source.round : next.round?.n ?? 1;
          const outcome = source.outcome === "settled" || source.outcome === "capped" || source.outcome === "superseded" ? source.outcome : undefined;
          return { ...next, round: { n, mode: next.round?.mode ?? "parallel", open: false, ...(outcome === undefined ? {} : { outcome }) } };
        }
        return state;
      }
      if (source?.kind === "user") return applyOperator(state, source);
      return state;
    }
    case "agent/inbox/spliced": {
      const inserted = Array.isArray(data?.inserted) ? data.inserted : [];
      let next = state;
      for (const message of inserted) {
        const source = sourceOf(message);
        if (source?.kind === "room") next = applyAnswer(next, message);
        else if (source?.kind === "user" && Array.isArray(source.mention) && source.mention.length > 0) next = applyOperator(next, source);
      }
      return next;
    }
    case "tool/call": {
      if (data?.name !== "dispatch" || typeof data.arguments !== "string") return state;
      let args: { to?: unknown; mode?: unknown };
      try { args = JSON.parse(data.arguments) as { to?: unknown; mode?: unknown }; } catch { return state; }
      const room = asRoom(state);
      if (room === undefined) return state;
      const to = Array.isArray(args.to) ? args.to.filter((x): x is string => typeof x === "string") : [];
      const members: Record<string, RoomMemberState> = {};
      for (const bot of to) members[bot] = { state: "called" };
      const mode = args.mode === "serial" ? "serial" : "parallel";
      return { ...room, members, round: { n: (room.round?.n ?? 0) + 1, mode, open: true } };
    }
    case "turn/start":
      return state.kind === "room" && state.organizing !== true ? { ...state, organizing: true } : state;
    case "turn/end":
      return state.kind === "room" && state.organizing !== false ? { ...state, organizing: false } : state;
    default:
      return state;
  }
}

/** What `ctx.sessionProjections.register` takes, stated structurally (dsh-session-projection `ProjectionDefinition`). */
export interface ProjectionDefinitionLike {
  key: string;
  stateSchema: z.ZodType<RoomState>;
  init(): RoomState;
  apply(state: RoomState, event: EventLike): RoomState;
  wire: { viewSchema: z.ZodType<RoomState>; view(state: RoomState): RoomState };
  stateVersion: number;
}

/** Register the unit; returns the registry's own disposer. */
export function registerRoomProjection(registry: { register(definition: ProjectionDefinitionLike): () => void }): () => void {
  return registry.register({
    key: ROOM_PROJECTION_KEY,
    stateSchema: roomStateSchema,
    init: initRoomState,
    apply: applyRoomEvent,
    wire: { viewSchema: roomStateSchema, view: (state) => state },
    stateVersion: ROOM_STATE_VERSION,
  });
}
