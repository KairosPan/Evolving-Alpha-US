/** Pure session-summary normalization: the one place a `session/list` row gets
 * back the `agentPreset` field the rest of the client reads.
 *
 * No DOM, no network, no state - one list row plus the face's own preset
 * hints in, one row out. Split out of chat.js for the same reason speaker.js
 * and grouping.js are: the decision has to be drillable without a browser.
 *
 * WHY IT EXISTS. dsh 0.1.1-rc.2's apiproxy summary carried `agentPreset`
 * directly. dsh 0.2.0-rc.2's `SessionSummary` does not (NEW
 * packages/api/session-controller/src/types.ts:177-188; list.ts:105-117,
 * 146-158): the preset now rides the row's projection block as
 * `projections.values.agentPreset` (the registry's `agentPreset` projection,
 * NEW packages/preset/agent-preset-registry/src/session.ts:35-43; the
 * upstream client reads it the same way). Without this fold every bot row,
 * every room member and every bot home session would silently read as the
 * host - the sidebar buckets, the member fold (room.js), the speaker label
 * (speaker.js) and the gate attribution all key on `summary.agentPreset`.
 *
 * PRECEDENCE. The projection value wins: it is the preset the session RUNS,
 * advanced by `agentPresets/select` (session.ts:38-41, and its module doc: the
 * header "names the preset a session STARTED with"), where the persisted header
 * only records the creation-time choice. The hint - `/data/channels.json`'s
 * `presets`, built by the face server from persisted and live session HEADERS
 * (src/channels.ts) - fills in when the block is absent or omits the key:
 * listing hints "remain partial: missing cells and cache rows are never
 * materialized" (list.ts:304-305), and a pre-upgrade v3 projection cache
 * record yields only the predecessor title (list.ts:283), so a cold
 * session opened before its first 0.2 resume has no projected preset at all.
 * An absent value stays absent: the row is never labelled with a guess.
 * @module
 */

/** @param {unknown} value @returns {value is Record<string, any>} a non-null, non-array object. */
const record = (value) => typeof value === "object" && value !== null && !Array.isArray(value);

/**
 * One list row with `agentPreset` restored when the host or the face knows it.
 * Idempotent: a row that already carries `agentPreset` (a second pass, or a
 * `session/create` answer, which still names it - NEW session-controller
 * src/types.ts:292-296) keeps it unless its projection names another.
 * @template {Record<string, any>} T
 * @param {T} row - a `SessionSummary` from `session/list` or an
 *   `api-session/added` notification.
 * @param {Record<string, unknown>|null|undefined} [presetHints] - sessionId → preset
 *   from the persisted/live headers (`/data/channels.json`'s `presets`).
 * @returns {T & {agentPreset?: string}} a shallow copy; the input row is never mutated.
 */
export function summaryOf(row, presetHints) {
  if (!record(row)) return row;
  const projections = record(row.projections) ? row.projections : undefined;
  const values = record(projections?.values) ? projections.values : undefined;
  // `null` is the registry's "this deployment composes none" (agent-preset-registry
  // src/types.ts:55; session.ts:38 folds a header without one to null),
  // not a preset name: it defers to the hint like an absent key does.
  const projected = values?.agentPreset;
  const id = typeof row.sessionId === "string" ? row.sessionId : undefined;
  // Own keys only: a hint map is plain JSON, and a session id must never reach
  // an inherited Object.prototype member.
  const hinted = id !== undefined && record(presetHints) && Object.hasOwn(presetHints, id) ? presetHints[id] : undefined;
  const agentPreset = typeof projected === "string" && projected !== "" ? projected
    : typeof hinted === "string" && hinted !== "" ? hinted
      : undefined;
  return agentPreset === undefined ? { ...row } : { ...row, agentPreset };
}
