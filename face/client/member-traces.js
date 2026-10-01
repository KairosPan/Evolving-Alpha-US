import { mapFrame } from "./mapper.js";

/** Read one room answer's process from its member session, without opening,
 * prompting or ACTIVATING that session.
 *
 * The read is two dsh 0.2.0-rc.2 Remotes that never resume an Agent
 * (NEW packages/api/session-controller/src/history.ts:77-112 `page`;
 * index.ts:490-512 `projections`; both observe through `sessionQuery` and
 * neither promotes, unlike `session/follow`, which background-activates a
 * cold ordinary session after its snapshot, history.ts:204-212):
 *
 *   1. `session/projections` fixes the cut. Its `asOfSeq` is the observed log
 *      cursor (session-projection src/index.ts:338-351 `cursorBefore(seq)`),
 *      which is exactly the inclusive `throughSeq` a page request must carry
 *      (types.ts:471-484) - the member may keep running while we page, and
 *      every page is read against the same cut. `null` means no such session.
 *   2. `session/page` walks backwards from that cut. `beforeSeq` is exclusive
 *      and page boundaries are messages, not turns (history.ts:392-427), so we
 *      keep paging until the answer's own `turn/start` is present. A page is
 *      `{records:[{type:'event', event}], hasMore}` (types.ts:425-429, 546-549).
 *
 * Every event arrives in the 0.2 shape - persisted 0.1.1 logs are migrated on
 * read (session-format-v3-to-v4 README) - so a surface replacement names
 * `startSeq`/`endSeq` (types.ts:446-448) and a tool result is a `role:'tool'`
 * message; the mapper absorbs the latter.
 * @module
 */

/** @param {unknown} value @returns {boolean} */
function object(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** @param {Array<any>} entries - records sorted by seq. @param {string} sessionId @param {number} turn
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
    const event = entries[index].event;
    const op = event.surfaceOp;
    // Honor even a textless replacement, and later compaction of this turn.
    // Paired call/result events share one UI card: replacing either drops it.
    // The wire names the inclusive range startSeq..endSeq (types.ts:446-448);
    // 0.1.1's start/end is migrated away on read (v3-to-v4 "Sequence references").
    if (object(op) && op.op === "replace" && Number.isSafeInteger(op.startSeq) && Number.isSafeInteger(op.endSeq) && op.startSeq <= op.endSeq) {
      const shadowed = views.filter((view) => view.seq >= op.startSeq && view.seq <= op.endSeq);
      const calls = new Set(shadowed.map((view) => view.card?.callId).filter((id) => id !== undefined));
      views = views.filter((view) => !shadowed.includes(view) && !(view.card?.callId !== undefined && calls.has(view.card.callId)));
    }
    if (index >= end) continue;
    // User/context messages have no top-level turn; other process events do.
    if (typeof event.data?.turn === "number" && event.data.turn !== turn) continue;
    // The mapper's one transcript path: a record is normalized to the frame a
    // live follow event becomes, so a trace maps exactly like the transcript.
    const view = mapFrame({ type: "session/event", sessionId, event });
    if (view.kind === "card") views.push(view);
    else if (view.kind === "bubble" && view.role === "operator" && typeof view.source === "string" && view.source !== "user") views.push(view);
    else if (view.kind === "bubble" && view.role === "kairos" && view.thinking) views.push({ ...view, text: "" });
  }
  // The fold is already applied. Never pass member replacement instructions
  // to the room transcript, whose sequence numbers are a separate namespace.
  return views.map((view) => ({ ...view, surfaceOp: "append" }));
}

/**
 * @param {(endpoint: string, args: Record<string, unknown>) => Promise<any>} call -
 *   api.js's unary Remote call (injected, so the tests drive it without a host).
 * @param {{sessionId: string, turn: number}} reference
 * @returns {Promise<import("./mapper.js").FrameView[]>} Process rows only; no answer prose.
 * @throws {Error} when the exact turn is unavailable, incomplete, or unreadable.
 */
export async function loadMemberTrace(call, { sessionId, turn }) {
  if (typeof sessionId !== "string" || sessionId.trim() === "" || !Number.isSafeInteger(turn) || turn < 1) {
    throw new Error("该回答未记录成员回合，无法读取思考轨迹。");
  }
  const cut = await call("session/projections", { request: { sessionId } });
  if (cut === null) throw new Error("成员会话不存在，无法读取思考轨迹。");
  // throughSeq must be an integer >= -1 (history.ts:305-318); -1 is an empty log.
  if (!object(cut) || !Number.isSafeInteger(cut.asOfSeq) || cut.asOfSeq < -1) {
    throw new Error("思考轨迹的历史记录格式无效。");
  }
  const address = { kind: "session", sessionId };
  const entries = new Map();
  let beforeSeq;
  while (true) {
    const page = await call("session/page", {
      request: { address, throughSeq: cut.asOfSeq, maxMessages: 100, ...(beforeSeq === undefined ? {} : { beforeSeq }) },
    });
    if (!object(page) || !Array.isArray(page.records) || typeof page.hasMore !== "boolean") {
      throw new Error("思考轨迹的历史记录格式无效。");
    }
    let oldest = Infinity;
    for (const record of page.records) {
      if (!object(record) || record.type !== "event" || !object(record.event)
        || !Number.isSafeInteger(record.event.seq) || record.event.seq < 0) {
        throw new Error("思考轨迹的历史记录格式无效。");
      }
      oldest = Math.min(oldest, record.event.seq);
      if (!entries.has(record.event.seq)) entries.set(record.event.seq, record);
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
