// face/tests/bot-plugin.test.ts
import test from "node:test";
import assert from "node:assert/strict";
// Plain ESM JS (the dsh loader imports it by path); tsconfig `allowJs` lets tsx import it here.
import { apply, expandAllow, inject, name, validateBotConfig } from "../plugins/bot.js";

test("kairos-bot: name and inject are what the composition relies on", () => {
  assert.equal(name, "kairos-bot");
  assert.deepEqual(inject, ["systemPrompt", "tools"]);
});

test("validateBotConfig refuses what would fail at render or mount, and accepts the template shape", () => {
  assert.equal(validateBotConfig({ persona: "You are Probe.", allow: ["bash"] }), undefined);
  assert.match(validateBotConfig(null) ?? "", /object/);
  assert.match(validateBotConfig({ persona: "", allow: ["bash"] }) ?? "", /persona/);
  assert.match(validateBotConfig({ persona: "Hi {{model}}", allow: ["bash"] }) ?? "", /\{\{/);
  assert.match(validateBotConfig({ persona: "x", allow: [] }) ?? "", /allow/);
  assert.match(validateBotConfig({ persona: "x", allow: ["bash", 3] }) ?? "", /allow/);
});

test("expandAllow keeps exact names that exist, expands mcp__*__<raw> against the tree, and reports the rest", () => {
  const known = new Set(["bash", "read", "mcp__alpaca-kit__earnings", "mcp__alpaca-kit__place_order", "agent_claude"]);
  const out = expandAllow(["bash", "mcp__*__earnings", "web_search", "mcp__*__orders"], known);
  assert.deepEqual(out.allow, ["bash", "mcp__alpaca-kit__earnings"]);
  assert.deepEqual(out.missing, ["web_search", "mcp__*__orders"]);
});

test("apply registers the persona section at order 0 and one allow-list restriction, both through effects", () => {
  const sections: unknown[] = [];
  const restrictions: unknown[] = [];
  const warnings: string[] = [];
  const ctx = {
    effect(fn: () => unknown) { return fn(); },
    logger: { warn: (m: string) => { warnings.push(m); } },
    systemPrompt: { section(s: unknown) { sections.push(s); return () => {}; } },
    tools: {
      schemas: () => [{ name: "bash" }, { name: "read" }, { name: "subagent" }],
      restrict(r: unknown) { restrictions.push(r); return () => {}; },
    },
  };
  apply(ctx, { persona: "You are Probe, a test voice.", allow: ["bash", "read", "web_search"] });
  assert.deepEqual(sections, [{ name: "deployment:persona", order: 0, text: "You are Probe, a test voice." }]);
  assert.deepEqual(restrictions, [{ allow: ["bash", "read"] }]);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /web_search/);
});

test("apply throws before touching the tree when no allowed tool exists", () => {
  const ctx = {
    effect(fn: () => unknown) { return fn(); },
    systemPrompt: { section() { throw new Error("must not be reached"); } },
    tools: { schemas: () => [{ name: "bash" }], restrict() { throw new Error("must not be reached"); } },
  };
  assert.throws(() => apply(ctx, { persona: "x", allow: ["nothing_here"] }), /none of the allowed tools/);
});
