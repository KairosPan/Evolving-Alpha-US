import test from "node:test";
import assert from "node:assert/strict";
import { botModelChoices, botSettingsPayload, botToolLabel, draftBotSoul, normalizeBotModel } from "../client/botSettings.js";

test("empty model inherits the default; explicit routes follow the saved bot grammar", () => {
  assert.equal(normalizeBotModel("  "), null);
  assert.equal(normalizeBotModel(" local/model-v2:latest "), "local/model-v2:latest");
  assert.throws(() => normalizeBotModel("claude"), /provider\/model/);
  assert.throws(() => normalizeBotModel("router/vendor/model"), /one slash/);
  assert.throws(() => normalizeBotModel("provider/model with spaces"), /provider\/model/);
});

test("catalog suggestions contain only routes the bot settings endpoint accepts", () => {
  assert.deepEqual(botModelChoices({ groups: [
    { id: "local", name: "Local", models: [{ id: "small", name: "Small model" }] },
    { id: "router", models: [{ id: "vendor/large" }] },
    { id: "unavailable" },
  ], failures: [{ id: "offline" }] }), [
    { value: "local/small", label: "Local · Small model" },
  ]);
  assert.deepEqual(botModelChoices(null), []);
});

test("guided SOUL drafts include only operator-supplied perspectives and criteria", () => {
  const draft = draftBotSoul({ identity: "  A skeptical researcher. ", revise: "Change my mind after independent replication.", evidence: " " });
  assert.equal(draft, "## Identity and perspective\n\nA skeptical researcher.\n\n## What changes my mind\n\nChange my mind after independent replication.");
  assert.equal(draftBotSoul({}), "");
});

test("settings saves carry the viewed revision and explicitly clear model inheritance", () => {
  assert.deepEqual(botSettingsPayload({ id: "research", revision: "viewed-revision", allow: ["read"] }, {
    name: " Researcher ", description: " Evidence first ", model: "", soul: "Identity\n\nDetails.",
  }), { id: "research", revision: "viewed-revision", name: "Researcher", description: "Evidence first", model: null, soul: "Identity\n\nDetails." });
});

test("tool labels translate known patterns and preserve unfamiliar capabilities", () => {
  assert.equal(botToolLabel("mcp__*__daily_bars"), "Daily prices");
  assert.equal(botToolLabel("read"), "Read files");
  assert.equal(botToolLabel("mcp__private__unlisted"), "mcp__private__unlisted");
});
