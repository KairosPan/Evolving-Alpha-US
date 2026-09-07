/** The browser's id proposal must never propose an id the server refuses.
 *
 * `client/botId.js` is a convenience, not a fence: it runs in the form so the
 * operator SEES the id a display name becomes before the POST. The one thing
 * that would make it a liar is proposing something `createBot` then rejects —
 * so the second test walks the proposal back through the server's own
 * `isBotId`, the only gate.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { proposeBotId } from "../client/botId.js";
import { isBotId } from "../src/bots.ts";

test("proposeBotId folds a display name into dsh's grammar, or to nothing", () => {
  assert.equal(proposeBotId("Buffett Type"), "buffett-type");
  assert.equal(proposeBotId("  Speculator_2  "), "speculator-2");
  assert.equal(proposeBotId("Macro -- Bear!"), "macro-bear");
  assert.equal(proposeBotId("巴菲特型"), "");
  assert.equal(proposeBotId("Éric"), "eric");
  assert.equal(proposeBotId("x".repeat(80)).length, 64);
});

test("a non-empty proposal is always an id the server accepts", () => {
  for (const name of ["Buffett Type", "Speculator_2", "Macro -- Bear!", "Éric", "a", "9lives", "x".repeat(80)]) {
    const id = proposeBotId(name);
    assert.equal(isBotId(id), true, `${name} -> ${id}`);
  }
});
