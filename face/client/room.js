/** Pure room decisions: the tested half of the room view.
 *
 * No DOM, no network, no state - session rows, a projection value and the
 * live maps in, chips / labels / folds out. Split out of chat.js for the
 * reason grouping.js and speaker.js are: the rules must be drillable
 * without a browser.
 *
 * WHAT THE WIRE CARRIES (plan 2 of the bots-and-rooms spec): no `room/*`
 * events. A member is known from its HEADER (`parentSessionId` + a bot
 * `agentPreset`, no `origin`); a room's coarse states come from the `room`
 * projection value; fine states (thinking / writing / tool) are the member
 * sessions' own pulses, which the mux forwards for every live session.
 * @module
 */

/** A dozen distinguishable shapes; a bot keeps its glyph for life (a hash of its id). */
export const GLYPHS = ["◆", "●", "▲", "■", "◇", "○", "△", "□", "⬟", "⬢", "✦", "✧"];

/** @param {string} id @returns {string} */
export function avatarGlyph(id) {
  let h = 0;
  for (const ch of String(id)) h = (h * 31 + (ch.codePointAt(0) ?? 0)) >>> 0;
  return GLYPHS[h % GLYPHS.length];
}

/** The composer anchor: start of text or whitespace, then `@` and a token. An e-mail's `@` follows a non-space. */
export const MENTION_RE = /(^|\s)@[^\s@]/u;
/** @param {string} text @returns {boolean} */
export const isMentionText = (text) => MENTION_RE.test(text);

/** Whether a row runs the host: no preset, or the inert default. @param {{agentPreset?: unknown}} row */
const isHost = (row) => typeof row.agentPreset !== "string" || row.agentPreset === "" || row.agentPreset === "kairos";

/**
 * The fold rule (spec §2.4 as plan 2 rebuilt it): a session is a member of
 * `P` when its header names `P` as parent, it has no `origin`, its preset is
 * a bot, and `P` itself is in the list running the host. Forks carry the
 * source's preset (`kairos` for a room) and subagent children carry
 * `origin`, so both stay out; a member of a member is not a member.
 * @param {ReadonlyArray<{sessionId: unknown, parentSessionId?: unknown, agentPreset?: unknown, origin?: unknown}>} items
 * @returns {{rooms: Map<string, any[]>, members: Set<string>}} rooms → their member rows, in list order; every member id.
 */
export function foldMembers(items) {
  const byId = new Map(items.map((s) => [String(s.sessionId), s]));
  /** @type {Map<string, any[]>} */
  const rooms = new Map();
  const members = new Set();
  for (const s of items) {
    if (typeof s.parentSessionId !== "string" || s.origin !== undefined || isHost(s)) continue;
    const room = byId.get(s.parentSessionId);
    if (room === undefined || !isHost(room)) continue;
    const list = rooms.get(s.parentSessionId) ?? [];
    if (list.length === 0) rooms.set(s.parentSessionId, list);
    list.push(s);
    members.add(String(s.sessionId));
  }
  return { rooms, members };
}

/**
 * Whether the session on screen is a MEMBER's own transcript rather than a
 * room's. Two witnesses, either one enough: its `room` projection reads
 * `kind: "member"` (the delta it was dispatched with wrote that), or the
 * header fold already files it under a room - which is true before any
 * projection lands.
 *
 * The strip describes THE ROOM ON SCREEN, and a member's transcript is not a
 * room. Nothing else stops it being drawn there: `engine.describe` answers for
 * a member too (a member's cwd IS the channel's, so it resolves to the same
 * channel and returns the same roster), while the member's own projection
 * carries no members - so the strip would read the whole roster `idle` and
 * Kairos `organizing` whenever the member itself is mid-turn.
 * @param {unknown} projection - the session's own `room` projection value.
 * @param {ReadonlySet<string>} memberIds - every id the header fold made a member.
 * @param {string|null|undefined} sessionId - the session on screen.
 * @returns {boolean}
 */
export function isMemberSession(projection, memberIds, sessionId) {
  if (projection !== null && typeof projection === "object" && /** @type {any} */ (projection).kind === "member") return true;
  return typeof sessionId === "string" && memberIds.has(sessionId);
}

/** @typedef {{id: string, name: string, state: string, kairos?: boolean, broken?: string, sessionId?: string}} Chip */

/**
 * The participants strip (spec §6): Kairos first, then every rostered bot,
 * then any member the roster no longer carries (`left`). States, in
 * precedence: a pending gate on the member's session → `waiting for you`;
 * while `called`, the live fine state if any; else the projection's coarse
 * state; else `idle`. Kairos is `organizing` while the projection says so,
 * or - before the session is a room - while the list says it is running.
 * @param {{roster: ReadonlyArray<{id: string, name: string, broken?: string}>, projection: any, members: Record<string, {sessionId?: string, name?: string}>, gates: Set<string>, fine: Map<string, string>, running: boolean, kairosName?: string}} input
 * @returns {Chip[]}
 */
export function stripChips(input) {
  const room = input.projection !== null && typeof input.projection === "object" && input.projection.kind === "room" ? input.projection : null;
  const projMembers = room !== null && room.members !== null && typeof room.members === "object" ? room.members : {};
  const organizing = room !== null ? room.organizing === true : input.running === true;
  /** @type {Chip[]} */
  const chips = [{ id: "kairos", name: input.kairosName ?? "Kairos", state: organizing ? "organizing" : "idle", kairos: true }];
  const stateOf = (bot) => {
    const sessionId = input.members[bot]?.sessionId ?? projMembers[bot]?.sessionId;
    if (sessionId !== undefined && input.gates.has(sessionId)) return { state: "waiting for you", sessionId };
    const coarse = projMembers[bot]?.state;
    if (coarse === "called") return { state: (sessionId !== undefined && input.fine.get(sessionId)) || "called", sessionId };
    return { state: typeof coarse === "string" ? coarse : "idle", sessionId };
  };
  const seen = new Set();
  for (const bot of input.roster) {
    seen.add(bot.id);
    const { state, sessionId } = stateOf(bot.id);
    chips.push({ id: bot.id, name: bot.name, state, ...(bot.broken === undefined ? {} : { broken: bot.broken }), ...(sessionId === undefined ? {} : { sessionId }) });
  }
  for (const bot of new Set([...Object.keys(input.members), ...Object.keys(projMembers)])) {
    if (seen.has(bot)) continue;
    const sessionId = input.members[bot]?.sessionId ?? projMembers[bot]?.sessionId;
    chips.push({ id: bot, name: input.members[bot]?.name ?? projMembers[bot]?.name ?? bot, state: "left", ...(sessionId === undefined ? {} : { sessionId }) });
  }
  return chips;
}

/** The round-end line: `round 1 · settled · answered: A · passed: B`; empty groups are omitted. @param {{round?: unknown, outcome?: unknown, turns?: unknown}} view */
export function roundEndLine(view) {
  const turns = Array.isArray(view.turns) ? view.turns : [];
  const group = (state, label) => {
    const names = turns.filter((t) => t && t.state === state).map((t) => (typeof t.name === "string" && t.name !== "" ? t.name : String(t.bot)));
    return names.length === 0 ? null : `${label}: ${names.join(", ")}`;
  };
  const head = view.outcome === "capped" ? "capped - the bot-message cap was reached"
    : view.outcome === "superseded" ? "superseded by a new operator message"
    : String(view.outcome ?? "ended");
  return [`round ${String(view.round ?? "?")}`, head, group("answered", "answered"), group("passed", "passed"), group("failed", "failed"), group("timed-out", "timed out")]
    .filter((part) => part !== null).join(" · ");
}

/** Whose gate this is: the member's bot name when the session is a member of the room on screen, else the fallback (the session's own voice).
 * @param {string|undefined} sessionId @param {ReadonlyArray<{sessionId: unknown, agentPreset?: unknown}>} memberRows @param {ReadonlyArray<{id: string, name?: unknown}>} bots @param {string} fallback */
export function gateSpeaker(sessionId, memberRows, bots, fallback) {
  const row = memberRows.find((r) => String(r.sessionId) === sessionId);
  if (row === undefined || typeof row.agentPreset !== "string") return fallback;
  const bot = bots.find((b) => b.id === row.agentPreset);
  const name = typeof bot?.name === "string" ? bot.name.trim() : "";
  return name === "" ? row.agentPreset : name;
}
