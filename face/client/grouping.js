/** Pure sidebar-bucket decision: the tested half of session grouping.
 *
 * No DOM, no network, no state — one session's channel/archived facts in, one
 * bucket key + display label out. Split out of chat.js for the same reason
 * mapper.js is: the exact bug class this exists to prevent (M2) is only
 * testable without a browser if the decision itself has no DOM in it.
 *
 * THE BUG THIS CLOSES. chat.js used to key sidebar buckets by the channel's
 * display TITLE. A channel's title is renameable and deliberately decoupled
 * from any stable identity (that is the whole point of the registry over the
 * old path-prefix grouping) — so two channels renamed to the same string
 * silently merged into one sidebar group, B's sessions rendering under A's
 * header, clicking it opening A. A channel titled exactly "archived" or
 * "ungrouped" collided with the two synthetic buckets the same way.
 *
 * The fix: bucket by `workspaceId` — durable, unique, never renamed — with
 * sentinel keys for the two synthetic buckets that can never collide with a
 * real one (workspace ids are UUIDs; `__archived`/`__ungrouped` are not).
 * @module
 */

/** Sentinel bucket key for archived sessions — never a real `workspaceId`. */
export const ARCHIVED_KEY = "__archived";
/** Sentinel bucket key for sessions no channel claims — never a real `workspaceId`. */
export const UNGROUPED_KEY = "__ungrouped";

/**
 * Which sidebar bucket one session belongs in, and what to show for it.
 * Archived takes priority over channel membership (an archived session's
 * channel, if any, is not what the sidebar groups it by).
 * @param {{workspaceId: string, title: string}|null} channel - the session's
 *   channel from the host's own membership index, or `null` when it belongs
 *   to none.
 * @param {boolean} archived - the session is archived (face-local ∪ host).
 * @returns {{key: string, label: string, channel: {workspaceId: string, title: string}|null}}
 *   `key` is the durable bucket identity to group and persist collapse state
 *   by; `label` is the display text; `channel` is `null` for both synthetic
 *   buckets (there is nothing to open by clicking their header).
 */
export function bucketFor(channel, archived) {
  if (archived) return { key: ARCHIVED_KEY, label: "archived", channel: null };
  if (channel !== null) return { key: channel.workspaceId, label: channel.title, channel };
  return { key: UNGROUPED_KEY, label: "ungrouped", channel: null };
}
