/** The tested half of sidebar grouping: the pure bucket-key decision (M2).
 *
 * Pins the exact bug class the finding named: two channels renamed to the
 * same display title, or a channel titled exactly "archived"/"ungrouped",
 * must never merge into one sidebar group. Bucketing must key on the
 * channel's durable `workspaceId`, never its renameable `title`.
 */
import test from "node:test";
import assert from "node:assert/strict";
// grouping.js is plain ESM JS (it ships to the browser); tsconfig `allowJs`
// lets this test import it and read its JSDoc-declared types.
import { ARCHIVED_KEY, BOT_KEY_PREFIX, bucketFor, isBotKey, UNGROUPED_KEY } from "../client/grouping.js";

test("two channels renamed to the SAME title still get DIFFERENT bucket keys", () => {
  const a = bucketFor({ workspaceId: "ws-a", title: "sentiment" }, false, null);
  const b = bucketFor({ workspaceId: "ws-b", title: "sentiment" }, false, null);
  assert.notEqual(a.key, b.key, "keyed by workspaceId, not by the collision-prone title");
  assert.equal(a.key, "ws-a");
  assert.equal(b.key, "ws-b");
  assert.equal(a.label, "sentiment");
  assert.equal(b.label, "sentiment", "the display label is still the title - only the KEY changed");
});

test("a channel titled exactly 'archived' or 'ungrouped' does not collide with the synthetic buckets", () => {
  const namedArchived = bucketFor({ workspaceId: "ws-1", title: "archived" }, false, null);
  const namedUngrouped = bucketFor({ workspaceId: "ws-2", title: "ungrouped" }, false, null);
  assert.equal(namedArchived.key, "ws-1", "a real channel's key is its workspaceId, whatever it is titled");
  assert.equal(namedUngrouped.key, "ws-2");
  assert.notEqual(namedArchived.key, ARCHIVED_KEY);
  assert.notEqual(namedUngrouped.key, UNGROUPED_KEY);
});

test("archived beats channel membership, and carries no channel to open", () => {
  const out = bucketFor({ workspaceId: "ws-1", title: "alpha" }, true, null);
  assert.deepEqual(out, { key: ARCHIVED_KEY, label: "archived", channel: null });
});

test("no channel is the ungrouped sentinel, and carries no channel to open", () => {
  assert.deepEqual(bucketFor(null, false, null), { key: UNGROUPED_KEY, label: "ungrouped", channel: null });
});

test("the sentinel keys are stable literals, never equal to a plausible workspaceId", () => {
  assert.equal(ARCHIVED_KEY, "__archived");
  assert.equal(UNGROUPED_KEY, "__ungrouped");
});

test("a bot session buckets under its bot, after archived and before channel membership", () => {
  const bot = { id: "buffett", label: "巴菲特型" };
  assert.deepEqual(bucketFor(null, false, bot), { key: "bot:buffett", label: "巴菲特型", channel: null });
  assert.deepEqual(bucketFor({ workspaceId: "ws-1", title: "alpha" }, false, bot), { key: "bot:buffett", label: "巴菲特型", channel: null });
  assert.deepEqual(bucketFor(null, true, bot), { key: ARCHIVED_KEY, label: "archived", channel: null });
  assert.equal(bucketFor(null, false, null).key, UNGROUPED_KEY);
  assert.equal(isBotKey(`${BOT_KEY_PREFIX}buffett`), true);
  assert.equal(isBotKey("bot:Bad Id"), false);
  assert.equal(isBotKey(UNGROUPED_KEY), false);
});
