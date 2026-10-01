// face/tests/bot-plugin.test.ts
import test from "node:test";
import assert from "node:assert/strict";
import SystemPrompt, { PERSONA_PREFIX_SECTION as DSH_PERSONA_PREFIX_SECTION } from "@deepseek-ai/dsh-system-prompt";
// Plain ESM JS (the dsh loader imports it by URL); tsconfig `allowJs` lets tsx import it here.
import { PERSONA_PREFIX_SECTION, apply, expandAllow, inject, name, validateBotConfig } from "../plugins/bot.js";

/** The installed allocator itself, not a copy of its table: `getSectionOrder`
 *  reads a module constant and no instance state (NEW
 *  packages/core/system-prompt/src/index.ts:470-472). */
const dshSectionOrder = (slot: "DEPLOYMENT_PERSONA_PREFIX"): number => SystemPrompt.prototype.getSectionOrder(slot);

/** Past the coalesced re-expansion bot.js queues behind a burst of `tools/change`. */
const settle = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 10));

/**
 * The slice of a preset scope `apply` touches, with dsh's semantics where they
 * matter: `restrict` refuses a name the tree does not have (NEW
 * packages/core/tools/src/index.ts:1114-1118), announces `tools/change`
 * synchronously AFTER the mutation and again when lifted (NEW
 * packages/core/scope/src/store.ts:233-262), and `emit` runs listeners
 * synchronously with no error containment (NEW vendor/cordis/src/events.ts:
 * 194-196) - so a listener that throws would surface in `register` below.
 * `on` is an effect of the fiber, as cordis registers it (events.ts:246-252),
 * so `unload` removes the listener with the rest.
 */
function fakeTree(initial: readonly string[]) {
  const names = new Set(initial);
  const listeners = new Set<() => void>();
  const live = new Set<{ allow: string[] }>();
  const disposers: (() => unknown)[] = [];
  const sections: unknown[] = [];
  const slots: string[] = [];
  const warnings: string[] = [];
  let restricts = 0;
  let failNextRestrict = false;
  const emit = (): void => { for (const listener of [...listeners]) listener(); };
  const ctx = {
    effect(fn: () => unknown) {
      const disposer = fn();
      assert.equal(typeof disposer, "function", "every effect hands back its disposer");
      disposers.push(disposer as () => unknown);
      return disposer;
    },
    on(event: string, listener: () => void) {
      assert.equal(event, "tools/change");
      listeners.add(listener);
      const off = (): boolean => listeners.delete(listener);
      disposers.push(off);
      return off;
    },
    logger: { warn: (message: string) => { warnings.push(message); } },
    systemPrompt: {
      section(section: unknown) {
        sections.push(section);
        return () => { sections.splice(sections.indexOf(section), 1); };
      },
      getSectionOrder(slot: "DEPLOYMENT_PERSONA_PREFIX") { slots.push(slot); return dshSectionOrder(slot); },
    },
    tools: {
      schemas: () => [...names].map((tool) => ({ name: tool })),
      restrict(filter: { allow: string[] }) {
        restricts++;
        if (failNextRestrict) { failNextRestrict = false; throw new Error("restrict refused (test)"); }
        const unknown = filter.allow.filter((tool) => !names.has(tool));
        if (unknown.length > 0) throw new Error(`tools.restrict() names unknown global tools ${unknown.join(", ")}`);
        const entry = { allow: [...filter.allow] };
        live.add(entry);
        emit();
        let lifted = false;
        return () => { if (lifted) return; lifted = true; live.delete(entry); emit(); };
      },
    },
  };
  return {
    ctx, sections, slots, warnings,
    /** The allow lists in force right now, oldest first. */
    masks: () => [...live].map((entry) => entry.allow),
    restricts: () => restricts,
    failNextRestrict: () => { failNextRestrict = true; },
    listeners: () => listeners.size,
    register(...added: string[]) { for (const tool of added) { names.add(tool); emit(); } },
    unregister(...removed: string[]) { for (const tool of removed) { names.delete(tool); emit(); } },
    /** What a fiber unload does: run every effect's disposer. */
    unload() { for (const disposer of disposers.splice(0).reverse()) disposer(); },
  };
}

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

/* The star is dsh's minting, not a suffix: `mcp__<server>__<raw>` is three
 * segments. A four-segment name ends in `__earnings` too, and admitting it
 * would hand the bot a tool the operator's list never named. */
test("expandAllow's star matches mcp__<server>__<raw> exactly, never a longer name ending in __<raw>", () => {
  const out = expandAllow(["mcp__*__earnings"], new Set(["mcp__a__b__earnings"]));
  assert.deepEqual(out.allow, []);
  assert.deepEqual(out.missing, ["mcp__*__earnings"]);
  const server = expandAllow(["mcp__*__earnings"], new Set(["mcp____earnings", "mcp__alpaca_kit__earnings"]));
  assert.deepEqual(server.allow, ["mcp__alpaca_kit__earnings"], "an empty server segment is not a server");
});

/* dsh 0.2.0 renamed the slot: 0.1.1's `deployment:persona` names NO section
 * now, so a bot registering it would carry Kairos's persona AND its own. Only
 * the prefix slot's name shadows the deployment prefix (NEW
 * packages/core/system-prompt/src/index.ts:179, 251-253). */
test("the persona is dsh's persona-PREFIX slot at the central prefix order - the one name that shadows Kairos's", () => {
  assert.equal(PERSONA_PREFIX_SECTION, DSH_PERSONA_PREFIX_SECTION, "bot.js restates the installed constant exactly");
  const tree = fakeTree(["bash", "read"]);
  apply(tree.ctx, { persona: "You are Probe, a test voice.", allow: ["bash"] });
  assert.deepEqual(tree.sections, [{ name: "deployment:persona-prefix", order: dshSectionOrder("DEPLOYMENT_PERSONA_PREFIX"), text: "You are Probe, a test voice." }]);
  assert.equal(dshSectionOrder("DEPLOYMENT_PERSONA_PREFIX"), 0, "the prefix opens the deployment's part of the prompt");
  assert.deepEqual(tree.slots, ["DEPLOYMENT_PERSONA_PREFIX"], "the order comes from dsh's allocator, not a literal");
});

test("apply masks to allow ∩ tree through one restriction, and warns once about the names the tree lacks", () => {
  const tree = fakeTree(["bash", "read", "subagent"]);
  apply(tree.ctx, { persona: "You are Probe, a test voice.", allow: ["bash", "read", "web_search"] });
  assert.deepEqual(tree.masks(), [["bash", "read"]]);
  assert.equal(tree.restricts(), 1);
  assert.equal(tree.warnings.length, 1);
  assert.match(tree.warnings[0], /web_search/);
});

/* The regression this guards: dsh 0.2.0 mounts a preset when it is DECLARED
 * (NEW packages/preset/agent-preset-registry/src/index.ts:80-118), so a mask
 * computed once at `apply` would shut every bot out of every tool that
 * registers later - an MCP server's market reads, first of all. */
test("a tool registered after the mount is admitted once its tools/change burst settles - but only when the allow list names it", async () => {
  const tree = fakeTree(["bash", "read"]);
  apply(tree.ctx, { persona: "You are Trader.", allow: ["bash", "read", "mcp__*__earnings", "mcp__*__daily_bars"] });
  assert.deepEqual(tree.masks(), [["bash", "read"]]);
  tree.register("mcp__alpaca-kit__earnings", "mcp__alpaca-kit__place_order", "agent_claude", "dispatch", "mcp__alpaca-kit__daily_bars");
  assert.deepEqual(tree.masks(), [["bash", "read"]], "coalesced: nothing moves inside the burst");
  await settle();
  assert.deepEqual(tree.masks(), [["bash", "read", "mcp__alpaca-kit__earnings", "mcp__alpaca-kit__daily_bars"]],
    "one mask in force - the old one lifted - admitting exactly the named late tools, never an order tool, agent_<bin> or dispatch");
  assert.equal(tree.restricts(), 2, "one re-expansion for the whole burst, and none for restrict's own tools/change");
  assert.equal(tree.warnings.length, 1, "the mount's warning only");
  tree.register("mcp__alpaca-kit__place_order_v2");
  await settle();
  assert.equal(tree.restricts(), 2, "a change that alters nothing the list names restricts nothing");
});

test("a tool that goes away leaves the mask; returning, it is admitted again; with every allowed tool gone the mask stays", async () => {
  const tree = fakeTree(["bash", "read", "mcp__alpaca-kit__earnings"]);
  apply(tree.ctx, { persona: "You are Probe.", allow: ["bash", "read", "mcp__*__earnings"] });
  tree.unregister("mcp__alpaca-kit__earnings");
  await settle();
  assert.deepEqual(tree.masks(), [["bash", "read"]]);
  tree.register("mcp__alpaca-kit__earnings");
  await settle();
  assert.deepEqual(tree.masks(), [["bash", "read", "mcp__alpaca-kit__earnings"]], "a reconnect under the same name is admitted again");
  tree.unregister("bash", "read", "mcp__alpaca-kit__earnings");
  await settle();
  assert.deepEqual(tree.masks(), [["bash", "read", "mcp__alpaca-kit__earnings"]],
    "never lifted to no mask: the stale mask admits nothing a later global could slip through");
  assert.equal(tree.warnings.length, 0, "tools going away is not a configuration error");
});

test("a re-expansion that fails is contained and logged, the mask in force stays, and the next change retries", async () => {
  const tree = fakeTree(["bash"]);
  apply(tree.ctx, { persona: "You are Probe.", allow: ["bash", "read"] });
  tree.failNextRestrict();
  assert.doesNotThrow(() => tree.register("read"), "the registration that triggered it never sees the failure");
  await settle();
  assert.deepEqual(tree.masks(), [["bash"]], "the previous mask stays in force");
  assert.equal(tree.warnings.length, 2);
  assert.match(tree.warnings[1], /could not follow a tool change.*restrict refused/);
  tree.register("unrelated_tool");
  await settle();
  assert.deepEqual(tree.masks(), [["bash", "read"]], "the failed key was not recorded as applied, so the retry lands");
});

test("unloading the revision lifts the mask, cancels a queued re-expansion and stops listening", async () => {
  const tree = fakeTree(["bash"]);
  apply(tree.ctx, { persona: "You are Probe.", allow: ["bash", "read"] });
  assert.equal(tree.listeners(), 1);
  tree.register("read");                   // queues a re-expansion
  tree.unload();
  assert.deepEqual(tree.masks(), []);
  assert.deepEqual(tree.sections, []);
  assert.equal(tree.listeners(), 0);
  await settle();
  assert.equal(tree.restricts(), 1, "the queued re-expansion never ran on the unloaded revision");
  assert.deepEqual(tree.masks(), []);
});

test("apply throws before touching the tree when no allowed tool exists", () => {
  const ctx = {
    effect(fn: () => unknown) { return fn(); },
    on() { throw new Error("must not be reached"); },
    systemPrompt: { section() { throw new Error("must not be reached"); }, getSectionOrder() { throw new Error("must not be reached"); } },
    tools: { schemas: () => [{ name: "bash" }], restrict() { throw new Error("must not be reached"); } },
  };
  assert.throws(() => apply(ctx, { persona: "x", allow: ["nothing_here"] }), /none of the allowed tools/);
});
