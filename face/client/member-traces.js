import { mapFrame } from "./mapper.js";

/** Read one room answer's process from its member session, without opening or
 * prompting that session. At the pinned host version, history is a read-only
 * raw event window; beforeSeq is exclusive and page boundaries are messages,
 * not turns. Keep paging until the answer's own turn/start is present. */

/** @param {unknown} value @returns {boolean} */
function object(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** @param {Array<any>} entries @param {string} sessionId @param {number} turn
 * @returns {import("./mapper.js").FrameView[]} */
function traceOf(entries, sessionId, turn) {
  const start = entries.findIndex(({ event }) => event.type === "turn/start" && event.data?.turn === turn);
  const end = entries.findIndex(({ event }, index) => index > start && event.type === "turn/end" && event.data?.turn === turn);
  if (end < 0 || entries.slice(start + 1, end).some(({ event }) => event.type === "turn/start")) {
    throw new Error("该回答的回合记录不完整，暂时无法读取思考轨迹。");
  }

  /** @type {import("./mapper.js").FrameView[]} */
  let views = [];
  for (let index = start + 1; index < entries.length; index++) {
    const entry = entries[index];
    const event = entry.event;
    const op = event.surfaceOp;
    // Honor even a textless replacement, and later compaction of this turn.
    // Paired call/result events share one UI card: replacing either drops it.
    if (object(op) && op.op === "replace" && Number.isSafeInteger(op.start) && Number.isSafeInteger(op.end) && op.start <= op.end) {
      const shadowed = views.filter((view) => view.seq >= op.start && view.seq <= op.end);
      const calls = new Set(shadowed.map((view) => view.card?.callId).filter((id) => id !== undefined));
      views = views.filter((view) => !shadowed.includes(view) && !(view.card?.callId !== undefined && calls.has(view.card.callId)));
    }
    if (index >= end) continue;
    // User/context messages have no top-level turn; other process events do.
    if (typeof event.data?.turn === "number" && event.data.turn !== turn) continue;
    const view = mapFrame({ ...entry, sessionId });
    if (view.kind === "card") views.push(view);
    else if (view.kind === "bubble" && view.role === "operator" && typeof view.source === "string" && view.source !== "user") views.push(view);
    else if (view.kind === "bubble" && view.role === "kairos" && view.thinking) views.push({ ...view, text: "" });
  }
  // The fold is already applied. Never pass member replacement instructions
  // to the room transcript, whose sequence numbers are a separate namespace.
  return views.map((view) => ({ ...view, surfaceOp: "append" }));
}

/**
 * @param {(method: string, payload: Record<string, unknown>) => Promise<any>} rpc
 * @param {{sessionId: string, turn: number}} reference
 * @returns {Promise<import("./mapper.js").FrameView[]>} Process rows only; no answer prose.
 * @throws {Error} when the exact turn is unavailable, incomplete, or unreadable.
 */
export async function loadMemberTrace(rpc, { sessionId, turn }) {
  if (typeof sessionId !== "string" || sessionId.trim() === "" || !Number.isSafeInteger(turn) || turn < 1) {
    throw new Error("该回答未记录成员回合，无法读取思考轨迹。");
  }
  const entries = new Map();
  let beforeSeq;
  while (true) {
    const page = await rpc("session.history", { sessionId, maxMessages: 100, ...(beforeSeq === undefined ? {} : { beforeSeq }) });
    if (!object(page) || !Array.isArray(page.events) || typeof page.hasMore !== "boolean") {
      throw new Error("思考轨迹的历史记录格式无效。");
    }
    let oldest = Infinity;
    for (const entry of page.events) {
      if (!object(entry) || !object(entry.event) || !Number.isSafeInteger(entry.event.seq) || entry.event.seq < 0) {
        throw new Error("思考轨迹的历史记录格式无效。");
      }
      oldest = Math.min(oldest, entry.event.seq);
      if (!entries.has(entry.event.seq)) entries.set(entry.event.seq, entry);
    }
    const sorted = [...entries.values()].sort((a, b) => a.event.seq - b.event.seq);
    if (sorted.some(({ event }) => event.type === "turn/start" && event.data?.turn === turn)) {
      return traceOf(sorted, sessionId, turn);
    }
    if (!page.hasMore) throw new Error("未找到该回答对应回合的思考轨迹。");
    if (!Number.isFinite(oldest) || (beforeSeq !== undefined && oldest >= beforeSeq)) {
      throw new Error("思考轨迹的历史记录未能继续加载，请重试。");
    }
    beforeSeq = oldest;
  }
}
