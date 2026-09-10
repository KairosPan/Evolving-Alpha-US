/** Pure decisions for temporary subagent sessions. A catalog, not a running
 * flag or a room roster, determines the durable control address. */

/** @param {unknown} value */
const object = (value) => value !== null && typeof value === "object";
/** @param {unknown} value */
const word = (value) => typeof value === "string" && value.trim() !== "";

/** @param {any} summary */
export const isSubagentRow = (summary) => summary?.origin === "subagent";

/** Preserve diagnostic rows: corrupt children must remain visible.
 * @param {unknown} value
 * @returns {{entries: any[], parentAvailable: boolean}} */
export function normalizeSubagentCatalog(value) {
  if (!object(value)) throw new Error("子任务目录不可用：服务返回了无效记录。");
  const body = /** @type {any} */ (value);
  if (!Array.isArray(body.entries) || typeof body.parentAvailable !== "boolean") throw new Error("子任务目录不可用：服务返回了无效记录。");
  const seen = new Set();
  const entries = [];
  for (const row of Array.isArray(body.entries) ? body.entries : []) {
    if (!object(row) || !word(row.id) || seen.has(row.id)) continue;
    seen.add(row.id);
    if (row.kind === "diagnostic") {
      entries.push({ kind: "diagnostic", id: row.id, reason: ["corrupt", "unsupported", "unavailable"].includes(row.reason) ? row.reason : "unavailable" });
    } else if (row.kind === "child" && (row.mode === "one-shot" || (row.mode === "continuable" && word(row.label)))) {
      entries.push({ kind: "child", id: row.id, mode: row.mode, label: word(row.label) ? row.label : "临时子任务", activity: ["running", "inactive"].includes(row.activity) ? row.activity : "unknown", hasChildren: row.hasChildren === true });
    } else {
      entries.push({ kind: "diagnostic", id: row.id, reason: "unsupported" });
    }
  }
  return { entries, parentAvailable: body.parentAvailable === true };
}

/** The catalog is authoritative even when an old projection disagrees.
 * @param {string} parentSessionId @param {string} childSessionId @param {unknown} catalog
 * @returns {{parentSessionId: string, childSessionId: string, mode: string}|null} */
export function subagentAddress(parentSessionId, childSessionId, catalog) {
  if (!word(parentSessionId) || !word(childSessionId) || parentSessionId === childSessionId) return null;
  const row = normalizeSubagentCatalog(catalog).entries.find((entry) => entry.id === childSessionId);
  return row?.kind === "child" ? { parentSessionId, childSessionId, mode: row.mode } : null;
}

/** Inactive is deliberately not a success state. A cold parent prevents only
 * follow-up delivery; an admitted interrupt need not stop the child instantly.
 * @param {any} row @param {boolean} parentAvailable @param {boolean} [waiting]
 */
export function subagentControls(row, parentAvailable, waiting = false) {
  const healthy = row?.kind === "child";
  const continuable = healthy && row.mode === "continuable";
  return {
    canRead: healthy,
    canPrompt: continuable && parentAvailable,
    canInterrupt: continuable && row.activity === "running",
    state: !healthy ? `记录不可用 · ${row?.reason ?? "unavailable"}` : waiting ? "等待你的回应" : row.activity === "running" ? "运行中" : row.activity === "inactive" ? "未运行" : "运行状态未知",
    note: !healthy ? "保留记录，无法读取或续派。" : !continuable ? "一次性任务 · 对话只读" : !parentAvailable ? "父会话未加载；先在父会话发送消息，再续派此任务。查看记录不会加载父会话。" : "可续派任务",
  };
}

/** Last recorded assistant output, retaining interruption provenance.
 * @param {any[]} events */
export function subagentResult(events) {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const event = events[i]?.event;
    if (event?.type !== "assistant/message") continue;
    const text = (Array.isArray(event.data?.message?.content) ? event.data.message.content : [])
      .filter((part) => part?.type === "text" && typeof part.text === "string").map((part) => part.text).join("\n").trim();
    if (text !== "") return { text, interrupted: event.data?.interrupted === true };
  }
  return null;
}
