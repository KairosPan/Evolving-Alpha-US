/** The transcript names the voice: whose name goes over an assistant turn.
 *
 * THE BUG THIS CLOSES (R12). A bot's home session answers in the bot's
 * persona and the sidebar files it under the bot's name, but every surface
 * that NAMED the speaker was the literal `Kairos`: the `who` element over each
 * assistant bubble, the ask card's `kairos asks` head, and the composer
 * placeholder. The operator running two bots saw three panes all claiming to
 * be Kairos.
 *
 * WHAT IT IS NOT. It is not attribution. Nothing here decides which agent
 * actually produced a frame — it reads the SESSION's own `agentPreset` header,
 * the same field `botOf` (chat.js) buckets the sidebar by, so the label and
 * the bucket can never disagree. Per-MESSAGE attribution, several voices in
 * one room log, is plan 3 and does not exist yet.
 *
 * The one property worth pinning is the fallback direction: an unknown preset
 * must degrade to the ID, never to `Kairos`. Claiming the host said something
 * a bot said is the failure mode; an ugly `buffett-type` label is not.
 */
import test from "node:test";
import assert from "node:assert/strict";
// speaker.js is plain ESM JS (it ships to the browser); tsconfig `allowJs`
// lets this test import it, the same way botId.test.ts imports botId.js.
import { HOST_NAME, speakerFor } from "../client/speaker.js";

/** A roster in the shape `/data/bots.json` returns. */
const bots = [
  { id: "buffett-type", name: "Buffett Type" },
  { id: "nameless", name: "" },
  { id: "spaced", name: "  Macro Bear  " },
];

test("no preset - or the default one - is the host speaking", () => {
  assert.equal(speakerFor(null, bots), HOST_NAME);
  assert.equal(speakerFor(undefined, bots), HOST_NAME);
  assert.equal(speakerFor({}, bots), HOST_NAME);
  assert.equal(speakerFor({ agentPreset: "kairos" }, bots), HOST_NAME);
});

test("a non-string agentPreset is the host, not a crash and not a label", () => {
  assert.equal(speakerFor({ agentPreset: 42 }, bots), HOST_NAME);
  assert.equal(speakerFor({ agentPreset: null }, bots), HOST_NAME);
  assert.equal(speakerFor({ agentPreset: { id: "buffett-type" } }, bots), HOST_NAME);
});

test("a rostered bot speaks under its display name, trimmed", () => {
  assert.equal(speakerFor({ agentPreset: "buffett-type" }, bots), "Buffett Type");
  assert.equal(speakerFor({ agentPreset: "spaced" }, bots), "Macro Bear");
});

test("a bot with no usable name falls back to its id", () => {
  // name: "" is the roster answering "no name", not a nameless speaker.
  assert.equal(speakerFor({ agentPreset: "nameless" }, bots), "nameless");
  // a name that is only whitespace trims to nothing - same answer.
  assert.equal(speakerFor({ agentPreset: "b" }, [{ id: "b", name: "   " }]), "b");
  // and a roster row whose name is not a string at all.
  assert.equal(speakerFor({ agentPreset: "b" }, [{ id: "b", name: 7 }]), "b");
});

test("an unlisted preset is its own id - a deleted bot, or a roster that never loaded", () => {
  assert.equal(speakerFor({ agentPreset: "ghost" }, bots), "ghost");
  assert.equal(speakerFor({ agentPreset: "ghost" }, []), "ghost");
});

test("the fallback is never the host: no bot ever answers as Kairos", () => {
  // Every id here is dsh's preset grammar `[a-z0-9][a-z0-9-]*` minus `kairos`
  // — the closed domain `createBot` (src/bots.ts) admits. The id fallback is
  // safe precisely because a lowercase-only id can never BE the host's name.
  const presets = ["ghost", "buffett-type", "nameless", "spaced", "kairos-2", "kaiross", "x", "9lives"];
  for (const preset of presets) {
    const rosters = [bots, [], [{ id: preset, name: "" }], [{ id: preset, name: HOST_NAME + " Jr" }]];
    for (const roster of rosters) {
      assert.notEqual(speakerFor({ agentPreset: preset }, roster), HOST_NAME, `${preset} in ${roster.length}-row roster`);
    }
  }
});
