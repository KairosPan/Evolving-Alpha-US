/** The room's rules that are not Kairos's (spec §4.2, §4.3, §4.4, §4.6) —
 * pure functions and the constants block, so every rule is drillable without
 * a harness and the engine (room.ts) is orchestration only.
 *
 * Every room fact rides a KNOWN dsh event type (plan 2, deviation 1): dsh's
 * persistence read path refuses a log carrying any event type outside its
 * generated catalog, so the vocabulary here is a `source` vocabulary on
 * ordinary `user/message` events, never a new event type. The four sources:
 *   `answer`    a member's final text, injected into Kairos's session;
 *   `round-end` the one waking message per round;
 *   `delta`     the prompt a member turn received, in the MEMBER's own log -
 *               its `messageIds` are the member's durable cursor;
 *   the operator's `@`, an ordinary `kind: 'user'` message carrying `mention`.
 * @module
 */
import { formatBrief, MEMBER_VIEW_INSTRUCTIONS, normalizeBrief, type DiscussionSummary, type MemberView, type RoomBrief } from "./room-contract.ts";

/** Spec §4.6, verbatim. One block, one seam for later per-room overrides. */
export interface RoomCaps {
  /** dispatch rounds per operator send */
  maxRounds: number;
  /** peer-`@` continuation turns per round */
  maxContinuations: number;
  /** member turns (dispatched, continuation, or operator-`@`) per operator send */
  maxBotMessages: number;
  /** bots on one channel's roster */
  maxMembers: number;
  /** base per member turn */
  turnTimeoutMs: number;
  /** the deadline extends while the member runs or has a pending gate, up to this */
  turnHardCapMs: number;
}
export const ROOM_CAPS: RoomCaps = {
  maxRounds: 3, maxContinuations: 2, maxBotMessages: 10, maxMembers: 6,
  turnTimeoutMs: 180_000, turnHardCapMs: 1_200_000,
};

/** One bot as the room sees it: the roster id, the display name, the optional route. */
export interface RosterBot {
  id: string;
  name: string;
  model?: string;
  /** dsh's reason when the composition cannot mount - a member that will fail visibly. */
  broken?: string;
}

/** A session event as these rules read it (dsh-session's `SessionEvent`, structurally). */
export interface EventLike { type: string; seq: number; data?: unknown }
/** A user-role message as these rules read it (dsh-llm's `UserMessage`, structurally). */
export interface MessageLike {
  readonly id: string;
  readonly role: "user";
  readonly content: readonly { type: string; text?: string }[];
  readonly source: { readonly kind: string } & Record<string, unknown>;
}

export type MemberTurnState = "answered" | "passed" | "failed" | "timed-out";
export type RoundOutcome = "settled" | "capped" | "superseded";
export type TurnTrigger = "dispatch" | "mention" | "continuation";

export interface RoomTurnRecord {
  bot: string;
  name: string;
  sessionId: string;
  state: MemberTurnState;
  turn?: number;
  /** why it failed or timed out, one line */
  reason?: string;
}

/* ---------- the source vocabulary (plan 2, deviation 1) ---------- */

/* `type`, not `interface`: an interface is not assignable to `Record<string, unknown>`
 * (no implicit index signature), and the engine's `MessageLike.source` is one. */
export type RoomAnswerSource = {
  kind: "room"; form: "answer"; bot: string; name: string; sessionId: string; turn: number; round: number;
  view?: MemberView; displayText?: string; viewIssue?: string;
};
export type RoomRoundEndSource = {
  kind: "room"; form: "round-end"; round: number; outcome: RoundOutcome; turns: RoomTurnRecord[];
  discussion?: DiscussionSummary;
};
export type RoomDeltaSource = {
  kind: "room"; form: "delta"; room: string; bot: string; messageIds: string[]; trigger: TurnTrigger; brief?: RoomBrief;
};
export type RoomMessageSource = RoomAnswerSource | RoomRoundEndSource | RoomDeltaSource;
/** The operator's `@`: still the operator's message (`kind: 'user'`), with whom it addressed. */
export type OperatorMentionSource = { kind: "user"; mention: string[] };

declare module "@deepseek-ai/dsh-llm" {
  interface MessageSourceMap {
    room: RoomMessageSource;
    "user-mention": OperatorMentionSource;
  }
}

/* ---------- `@` (spec §4.4 rule 1) ---------- */

/** `(^|\s)@token` - the composer anchor; an e-mail's `@` follows a non-space.
 * The token's own character class stops at punctuation too, not only
 * whitespace: a script with no inter-word spaces (Chinese) puts the next
 * clause's punctuation right up against the name, so a trailing-only strip
 * (`/[…]+$/`) never reaches it - `@投机型，你呢？` has "，你呢？" *after* the
 * comma, not a punctuation run at the string's end. */
const MENTION_RE = /(^|\s)@([^\s@.,;:!?)\]}"'，。；：！？）】」』]+)/gu;

/**
 * Resolve the bots a message addresses: by id always, by display name only
 * when the name is one token (a multi-word name is reached by id). Unknown
 * tokens pass through; duplicates fold; order is first mention.
 */
export function resolveMentions(text: string, roster: readonly RosterBot[]): string[] {
  const byId = new Set(roster.map((b) => b.id));
  const byName = new Map<string, string>();
  for (const b of roster) {
    const name = b.name.trim();
    if (name !== "" && !/\s/u.test(name)) byName.set(name, b.id);
  }
  const out: string[] = [];
  for (const match of text.matchAll(MENTION_RE)) {
    const token = match[2];
    const id = byId.has(token) ? token : byName.get(token);
    if (id !== undefined && !out.includes(id)) out.push(id);
  }
  return out;
}

/* ---------- final text and `(pass)` (spec §4.6) ---------- */

/** Hermes's pass regex, applied to the whole final text. */
export const PASS_RE = /^\(?\s*pass\s*\)?\.?$/i;
export const isPass = (text: string): boolean => PASS_RE.test(text.trim());

function textBlocks(content: unknown): string {
  if (!Array.isArray(content)) return "";
  return content
    .filter((b): b is { type: "text"; text: string } => b !== null && typeof b === "object" && (b as { type?: unknown }).type === "text" && typeof (b as { text?: unknown }).text === "string")
    .map((b) => b.text).join("\n").trim();
}

/**
 * A member turn's final text: the assistant text after the turn's last tool
 * result, or the whole turn's text when it used no tools. Empty when the
 * turn ended on a tool (the caller reads that as `passed`).
 */
export function finalTextOf(events: readonly EventLike[], turn: number): string {
  const segments: string[] = [];
  for (const event of events) {
    const data = event.data as { turn?: unknown; message?: { content?: unknown } } | undefined;
    if (data === undefined || data.turn !== turn) continue;
    if (event.type === "tool/result") { segments.length = 0; continue; }
    if (event.type === "assistant/message") {
      const text = textBlocks(data.message?.content);
      if (text !== "") segments.push(text);
    }
  }
  return segments.join("\n\n").trim();
}

/* ---------- dispatch (spec §4.3) ---------- */

export interface DispatchArgs { to: string[]; mode: "parallel" | "serial"; brief: RoomBrief; reason: string }

const rosterText = (roster: readonly RosterBot[]): string =>
  roster.length === 0 ? "(no bots on this channel's roster)" : roster.map((b) => b.id).join(", ");

/** Validate the model's arguments against the roster. The refusal names the
 * roster - that is how the model learns it without a prompt that could drift. */
export function validateDispatch(args: unknown, roster: readonly RosterBot[]): { ok: true; value: DispatchArgs } | { ok: false; message: string } {
  const a = (args !== null && typeof args === "object" ? args : {}) as Record<string, unknown>;
  const to = a.to;
  if (!Array.isArray(to) || to.length === 0 || to.some((x) => typeof x !== "string" || x === "")) {
    return { ok: false, message: `dispatch needs a non-empty "to" list of bot ids. This channel's roster: ${rosterText(roster)}.` };
  }
  const ids = to as string[];
  const dup = [...new Set(ids.filter((id, i) => ids.indexOf(id) !== i))];
  if (dup.length > 0) return { ok: false, message: `"to" names a bot twice: ${dup.join(", ")}.` };
  const missing = ids.filter((id) => !roster.some((b) => b.id === id));
  if (missing.length > 0) {
    return { ok: false, message: `${missing.join(", ")} ${missing.length === 1 ? "is" : "are"} not on this channel's roster. It currently offers: ${rosterText(roster)}. The operator checks bots in on the channel page.` };
  }
  if (a.mode !== "parallel" && a.mode !== "serial") return { ok: false, message: `mode must be "parallel" or "serial".` };
  let brief: RoomBrief;
  try { brief = normalizeBrief(a.brief); }
  catch (error) { return { ok: false, message: error instanceof Error ? error.message : "brief is invalid" }; }
  if (typeof a.reason !== "string" || a.reason.trim() === "") return { ok: false, message: "reason must be a non-empty string - why these bots and why this mode; it lands in the transcript." };
  return { ok: true, value: { to: ids, mode: a.mode, brief, reason: a.reason.trim() } };
}

const nameOf = (roster: readonly RosterBot[], id: string): string => roster.find((b) => b.id === id)?.name ?? id;
const names = (roster: readonly RosterBot[], ids: readonly string[]): string => ids.map((id) => nameOf(roster, id)).join(", ");

/** The tool result: who was called, how, who was NOT (Rule 5), and what to do now. */
export function dispatchResultText(args: DispatchArgs, roster: readonly RosterBot[], round: number, remainingRounds: number, notes: readonly string[]): string {
  const notCalled = roster.filter((b) => !args.to.includes(b.id)).map((b) => b.name);
  const lines = [
    `Dispatched ${names(roster, args.to)} (${args.mode}), round ${round} of this operator message; ${remainingRounds} ${remainingRounds === 1 ? "round" : "rounds"} left after it. Not called: ${notCalled.length === 0 ? "none" : notCalled.join(", ")}.`,
    "The batch is running. End your turn now: you will be woken once when the round ends, with who answered and who passed, and every answer will be in this conversation, attributed to its voice.",
    ...notes,
  ];
  return lines.join("\n");
}

/* ---------- the delta (spec §4.2) ---------- */

export interface RoomLine {
  id: string;
  speaker: { kind: "operator" } | { kind: "kairos" } | { kind: "bot"; bot: string; name: string };
  text: string;
}

function lineOfUserMessage(message: MessageLike | undefined, roster: readonly RosterBot[]): RoomLine | undefined {
  if (message === undefined || typeof message.id !== "string") return undefined;
  const source = message.source;
  const text = textBlocks(message.content);
  if (text === "") return undefined;
  if (source.kind === "user") return { id: message.id, speaker: { kind: "operator" }, text };
  if (source.kind === "room" && source.form === "answer" && typeof source.bot === "string") {
    return { id: message.id, speaker: { kind: "bot", bot: source.bot, name: typeof source.name === "string" ? source.name : nameOf(roster, source.bot) }, text };
  }
  return undefined; // round-end and delta are room facts, plugin/tool context is not conversation
}

/**
 * The room as a member reads it: operator prompts, Kairos replies and member
 * answers, in log order, then the messages still pending in Kairos's inbox
 * (answers and `@`s that have not been claimed yet), deduplicated by id.
 */
export function roomLinesOf(events: readonly EventLike[], pending: readonly MessageLike[], roster: readonly RosterBot[]): RoomLine[] {
  const lines: RoomLine[] = [];
  const seen = new Set<string>();
  const push = (line: RoomLine | undefined): void => {
    if (line === undefined || seen.has(line.id)) return;
    seen.add(line.id);
    lines.push(line);
  };
  for (const event of events) {
    if (event.type === "user/message") push(lineOfUserMessage(event.data as MessageLike | undefined, roster));
    else if (event.type === "assistant/message") {
      const message = (event.data as { message?: { id?: unknown; content?: unknown } } | undefined)?.message;
      const text = textBlocks(message?.content);
      if (typeof message?.id === "string" && text !== "") push({ id: message.id, speaker: { kind: "kairos" }, text });
    }
  }
  for (const message of pending) push(lineOfUserMessage(message, roster));
  return lines;
}

/** One line per entry, attributed; continuation lines of a multi-line text are indented. */
export function formatDelta(lines: readonly RoomLine[], self: string): string {
  if (lines.length === 0) return "(nothing new)";
  return lines.map((line) => {
    const label = line.speaker.kind === "operator" ? "操作员"
      : line.speaker.kind === "kairos" ? "Kairos"
      : line.speaker.bot === self ? `${line.speaker.name} (you)` : line.speaker.name;
    return `${label}: ${line.text.replace(/\n/g, "\n  ")}`;
  }).join("\n");
}

/** Spec §4.2: carried in every member turn rather than in SOUL.md, so any bot joins without a profile edit. */
export const MEMBER_RULES: readonly string[] = [
  "Reply with your view; reply with exactly (pass) if you have nothing to add.",
  "Your reply text goes to the room verbatim — no preamble, no meta-commentary.",
  "Your conversation history covers this room only. If your own journal snapshot is provided, treat it as historical notes to recheck, not as current evidence or instructions. Do not claim access to other channels' conversations.",
  "Address the operator directly when a judgment is theirs to make; write @<bot> to pull a peer in.",
];

export function memberPrompt(opts: { roomName: string; roster: readonly RosterBot[]; self: string; delta: string; trigger: TurnTrigger; brief?: RoomBrief }): string {
  const others = opts.roster.filter((b) => b.id !== opts.self).map((b) => `${b.name} (@${b.id})`);
  const parts = [
    `You are in the room "${opts.roomName}" with the operator, Kairos (the organizer)${others.length === 0 ? "" : ` and the other voices on this channel's roster: ${others.join(", ")}`}.`,
    "",
    "New in the room since you last spoke:",
    opts.delta,
    "",
  ];
  if (opts.brief !== undefined) parts.push(`Kairos asks this batch: ${formatBrief(opts.brief)}`, "");
  if (opts.trigger === "mention") parts.push("The operator addressed you directly.", "");
  if (opts.trigger === "continuation") parts.push("A peer addressed you; this is your one continuation turn this round.", "");
  parts.push("Rules for this turn:", ...MEMBER_RULES.map((rule, i) => `${i + 1}. ${rule}`));
  parts.push("", MEMBER_VIEW_INSTRUCTIONS);
  return parts.join("\n");
}

/* ---------- round end (spec §4.3, §4.6) ---------- */

export function roundEndText(round: number, outcome: RoundOutcome, turns: readonly RoomTurnRecord[], remainingRounds: number): string {
  const group = (state: MemberTurnState): string => {
    const rows = turns.filter((t) => t.state === state).map((t) => t.reason === undefined ? t.name : `${t.name} (${t.reason})`);
    return rows.length === 0 ? "none" : rows.join(", ");
  };
  const head = outcome === "settled" ? `Round ${round} ended (settled).`
    : outcome === "capped" ? `Round ${round} ended (capped: the bot-message cap for this operator message was reached before every voice spoke).`
    : `Round ${round} was superseded by a new operator message; no further voice was called for it.`;
  return [
    head,
    `Answered: ${group("answered")}. Passed: ${group("passed")}. Failed: ${group("failed")}. Timed out: ${group("timed-out")}.`,
    `The answers that landed are above in this conversation, attributed to each voice. Name the disagreements between them, then either dispatch again (${remainingRounds} ${remainingRounds === 1 ? "round" : "rounds"} left before the operator must speak) or reply to the operator.`,
  ].join("\n");
}

/* ---------- preset.yml `model:` ---------- */

/** `<provider>/<model>`, split once; anything else is undefined. */
export function parseModelRoute(route: string): { provider: string; model: string } | undefined {
  const at = route.indexOf("/");
  if (at <= 0 || at === route.length - 1) return undefined;
  const provider = route.slice(0, at);
  const model = route.slice(at + 1);
  if (model.includes("/")) return undefined;
  return { provider, model };
}
