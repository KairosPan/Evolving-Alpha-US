/** Pure decisions for temporary subagent sessions. A catalog, not a running
 * flag or a room roster, determines the durable control address.
 *
 * dsh 0.2.0-rc.2 has no catalog Remote: 0.1.1's `subagent.list` is gone, and
 * the upstream client composes the same facts itself (NEW
 * packages/api/session-controller/src/client/sessions/manager.ts:130-172,
 * 378-388). {@link composeSubagentCatalog} does that composition in the 0.1.1
 * shape, so {@link normalizeSubagentCatalog} - and every decision below it -
 * stays exactly as it was. Diagnostics the old listing carried for unreadable
 * children now arrive as errors of the read that needs them (`session/follow`
 * or `session/page` on a subagent address: `subagent/catalog-diagnostic`,
 * `subagent/not-found`, `subagent/unauthorized`; NEW
 * packages/api/session-controller/src/history.ts:341-390). */

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

/**
 * Compose 0.1.1's `subagent.list` answer from what dsh 0.2.0-rc.2 still serves:
 * the parent's `subagentCatalog` projection and the session list.
 *
 * - entries: the parent's catalog rows `[{id, createdAt, mode, label?}]`, in
 *   catalog order (NEW packages/subagent/subagent/src/projection-types.ts:9-19,
 *   69-71). A row the catalog records in mode `unknown` - the 0.2 migration's
 *   unreadable-membership marker (NEW docs/persistence-changes/2026-09-20-unknown-child-catalog.md)
 *   - becomes the `unsupported` diagnostic 0.1.1 gave an unknown mode ("the
 *   parent catalog records an unknown child mode", control-types.ts:60-69):
 *   visible, never controllable.
 * - parentAvailable: the parent summary's `agentAvailable` (session-controller
 *   src/list.ts:113; the upstream manager reads the same field, manager.ts:378-381).
 *   An unlisted parent is not available.
 * - activity: the child's own list row, `running` → "running" else "inactive"
 *   (the upgrade plan's mapping); omitted when the list has no row for the child,
 *   which {@link normalizeSubagentCatalog} reads as "unknown" - never guessed idle.
 * - hasChildren: some listed row names this child as its subagent parent - the
 *   old field's own definition, "a direct descendant has durable
 *   `origin: 'subagent'`" (OLD packages/subagent/subagent/src/list-children.ts:56).
 * @param {{catalog: unknown, parentSummary: any, rows: ReadonlyArray<any>}} input -
 *   `catalog` is `values.subagentCatalog` from `session/projections` for the
 *   parent (undefined when the projection is absent: no children recorded).
 * @returns {{entries: any[], parentAvailable: boolean}} the 0.1.1 listing shape.
 * @throws {Error} when a catalog is present but is not a list: a malformed
 *   projection is "unavailable", never an empty successful listing.
 */
export function composeSubagentCatalog({ catalog, parentSummary, rows }) {
  if (catalog !== undefined && !Array.isArray(catalog)) throw new Error("子任务目录不可用：服务返回了无效记录。");
  const listed = (Array.isArray(rows) ? rows : []).filter(object);
  const byId = new Map(listed.map((row) => [String(row.sessionId), row]));
  const entries = [];
  for (const entry of catalog ?? []) {
    // Malformed rows are skipped exactly as normalizeSubagentCatalog skips them.
    if (!object(entry) || !word(entry.id)) continue;
    if (entry.mode === "unknown") {
      entries.push({ kind: "diagnostic", id: entry.id, reason: "unsupported" });
      continue;
    }
    const row = byId.get(entry.id);
    entries.push({
      kind: "child",
      id: entry.id,
      mode: entry.mode,
      ...(word(entry.label) ? { label: entry.label } : {}),
      ...(row === undefined ? {} : { activity: row.running === true ? "running" : "inactive" }),
      hasChildren: listed.some((other) => other.origin === "subagent" && other.parentSessionId === entry.id),
    });
  }
  return { entries, parentAvailable: parentSummary?.agentAvailable === true };
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
 * @param {any[]} events - history records, each `{event}`: 0.2's `session/page`
 *   records are `{type:'event', event}` (session-controller src/types.ts:425-429),
 *   which read the same way. */
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
