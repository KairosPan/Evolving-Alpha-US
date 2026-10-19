import test from "node:test";
import assert from "node:assert/strict";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import { CYCLE_SECTION, ROLES_SECTION, TODAY_SECTION, apply, canCall, inject, name, resolveZone, rolesText, todayText, validateGravitConfig } from "../plugins/gravit.js";

const dshSectionOrder = (slot: "DEPLOYMENT_PERSONA_PREFIX" | "DEPLOYMENT_PERSONA_SUFFIX" | "TOOL_SUBAGENT"): number => SystemPrompt.prototype.getSectionOrder(slot);

/** A stand-in scope for `apply`. `systemPrompt` records the sections; `tools.get(name, scope)`
 *  resolves a name when the scope it is handed lists it in `visible`, and records every lookup -
 *  the assembly context's `scope` is the agent, and the registry answers what that scope can call. */
type FakeToolScope = { visible?: readonly string[] };
function fakeScope() {
  const sections: Array<{ name: string; order: number; interpolate?: boolean; text: unknown }> = [];
  const disposers: Array<() => unknown> = [];
  const lookups: Array<{ name: string; scope: FakeToolScope | undefined }> = [];
  const ctx = {
    effect(fn: () => unknown) { const d = fn(); assert.equal(typeof d, "function"); disposers.push(d as () => unknown); return d; },
    systemPrompt: {
      section(section: { name: string; order: number; interpolate?: boolean; text: unknown }) {
        sections.push(section);
        return () => { sections.splice(sections.indexOf(section), 1); };
      },
      getSectionOrder: (slot: "DEPLOYMENT_PERSONA_PREFIX" | "DEPLOYMENT_PERSONA_SUFFIX" | "TOOL_SUBAGENT") => dshSectionOrder(slot),
    },
    tools: {
      get(name: string, scope?: FakeToolScope) {
        lookups.push({ name, scope });
        return scope?.visible?.includes(name) ? { name } : undefined;
      },
    },
  };
  return { ctx, sections, lookups, unload: () => { for (const d of disposers.splice(0).reverse()) d(); } };
}

test("gravit: name and inject are what the composition relies on", () => {
  assert.equal(name, "gravit");
  assert.deepEqual(inject, ["systemPrompt", "tools"]);
  assert.equal(TODAY_SECTION, "deployment:today");
});

test("validateGravitConfig: {} is valid; cycle and roles are checked when present", () => {
  assert.equal(validateGravitConfig({}), undefined);
  assert.match(validateGravitConfig(null) ?? "", /object/);
  assert.match(validateGravitConfig({ cycle: "" }) ?? "", /cycle/);
  assert.equal(validateGravitConfig({ cycle: "Open one goal per cycle." }), undefined);
  assert.match(validateGravitConfig({ roles: [{ tool: "screener", summary: "x" }] }) ?? "", /role_/);
  assert.match(validateGravitConfig({ roles: [{ tool: "role_screener", summary: "" }] }) ?? "", /summary/);
  assert.equal(validateGravitConfig({ roles: [{ tool: "role_screener", summary: "runs the screen" }] }), undefined);
});

test("todayText renders the LOCAL date of the zone, ISO date then weekday", () => {
  assert.equal(todayText(new Date("2026-10-18T12:00:00Z"), "America/New_York"), "Today is 2026-10-18, Sunday (America/New_York).");
  assert.equal(todayText(new Date("2026-10-18T03:00:00Z"), "America/New_York"), "Today is 2026-10-17, Saturday (America/New_York).");
  assert.equal(todayText(new Date("2026-10-18T03:00:00Z"), "Asia/Shanghai"), "Today is 2026-10-18, Sunday (Asia/Shanghai).");
});

test("apply registers exactly one scoped, uninterpolated section right after the persona slot, and unload removes it", () => {
  const tree = fakeScope();
  apply(tree.ctx, {});
  assert.equal(tree.sections.length, 1);
  const [section] = tree.sections;
  assert.equal(section.name, TODAY_SECTION);
  assert.ok(Number.isFinite(section.order), "the persona slot exists in the installed SECTION_ORDERS");
  assert.equal(section.order, dshSectionOrder("DEPLOYMENT_PERSONA_PREFIX") + 1);
  assert.equal(section.interpolate, false);
  assert.equal(typeof section.text, "function");
  assert.match((section.text as () => string)(), /^Today is \d{4}-\d{2}-\d{2}, [A-Z][a-z]+ \(.+\)\.$/);
  tree.unload();
  assert.equal(tree.sections.length, 0);
});

test("apply refuses a bad config with its reason", () => {
  assert.throws(() => apply(fakeScope().ctx, { cycle: 7 }), /gravit: .*cycle/);
});

/* The text function runs at every assembly and `apply` never calls it, so an
 * unusable TZ - "" resolves to "Etc/Unknown", which Intl refuses; "Foo/Bar"
 * resolves to undefined - would mount cleanly and then throw (or print
 * "(undefined)") in every Gravit prompt. Node re-reads TZ on assignment, so the
 * real resolution is exercised; the key is put back (or deleted) in `finally`. */
test("an unusable TZ is rendered in UTC and labelled, never thrown at assembly", () => {
  const saved = process.env.TZ;
  try {
    for (const unusable of ["", "Foo/Bar"]) {
      process.env.TZ = unusable;
      assert.equal(resolveZone(), "UTC", `TZ=${JSON.stringify(unusable)}`);
      const tree = fakeScope();
      apply(tree.ctx, {});
      const text = (tree.sections[0].text as () => string)();
      assert.match(text, /^Today is \d{4}-\d{2}-\d{2}, [A-Z][a-z]+ \(UTC\)\.$/, `TZ=${JSON.stringify(unusable)}`);
      tree.unload();
    }
    process.env.TZ = "America/New_York";
    assert.equal(resolveZone(), "America/New_York");
    const tree = fakeScope();
    apply(tree.ctx, {});
    assert.match((tree.sections[0].text as () => string)(), /\(America\/New_York\)\.$/);
    tree.unload();
  } finally {
    if (saved === undefined) delete process.env.TZ;
    else process.env.TZ = saved;
  }
});

/* The roles section lists what the ASSEMBLING scope can call, the gate dsh-tool-web and
 * dsh-tool-subagent put on their own sections: a role child, whose allow list restricts the
 * `role_<id>` tools away, is told of none; a `subagent_fork` child - seeded, unrestricted - sees
 * every role tool, so it gets Gravit's text unchanged and its inherited prefix stays byte-identical
 * (roles-smoke pins that on a real boot); a role whose tool never registered is not advertised. */
test("gravit: the roles section follows dsh's subagent section and lists exactly the roles the assembling scope can call", () => {
  const tree = fakeScope();
  const roles = [{ tool: "role_screener", summary: "runs the screen" }, { tool: "role_reviewer", summary: "audits" }];
  apply(tree.ctx, { roles });
  const section = tree.sections.find((s) => s.name === ROLES_SECTION)!;
  assert.ok(section, "registered");
  assert.equal(section.order, dshSectionOrder("TOOL_SUBAGENT") + 1);
  assert.equal(section.interpolate, false);
  assert.equal(tree.lookups.length, 0, "nothing is looked up at mount: the gate is read at every assembly");
  const textFor = (visible: string[]) => (section.text as (c: unknown) => string)({ scope: { visible } });
  const all = textFor(["read", "role_screener", "role_reviewer"]);
  assert.equal(all, rolesText(roles), "every role tool visible: the whole list, as Gravit and a fork child read it");
  assert.match(all, /^Roles\. /);
  assert.ok(all.includes("- role_screener — runs the screen") && all.includes("- role_reviewer — audits"));
  assert.equal(textFor(["read", "grep"]), "", "no role tool visible (a role child's allow list removed them): nothing");
  assert.equal(textFor(["role_reviewer"]), rolesText([roles[1]]), "one of two visible: that one only");
  assert.equal(textFor(["role_reviewer"]).includes("role_screener"), false);
});

test("canCall is the registry's view of the assembling scope: tools.get(name, context.scope)", () => {
  const tree = fakeScope();
  const scope = { visible: ["role_screener"] };
  assert.equal(canCall(tree.ctx, { scope }, "role_screener"), true);
  assert.equal(canCall(tree.ctx, { scope }, "role_reviewer"), false);
  assert.deepEqual(tree.lookups.map((l) => [l.name, l.scope === scope]), [["role_screener", true], ["role_reviewer", true]], "each lookup is handed the context's own scope");
  assert.equal(canCall(tree.ctx, {}, "role_screener"), false, "no scope is the global view, where no preset-scoped tool lives");
  assert.equal(canCall(tree.ctx, undefined, "role_screener"), false, "total on a missing context");
});

test("gravit: without a roles key there is no roles section; an empty list renders nothing", () => {
  const tree = fakeScope();
  apply(tree.ctx, {});
  assert.equal(tree.sections.some((s) => s.name === ROLES_SECTION), false);
  assert.equal(rolesText([]), "");
});

/* The cycle section is gated the way the roles section is: on what the ASSEMBLING scope can call.
 * `create_goal` is the probe because the contract is written for the session that opens a goal -
 * Gravit, and a `subagent_fork` child, which resolves every tool Gravit does and so reads the
 * identical text (its inherited prefix stays byte-identical; roles-smoke pins that on a real boot) -
 * while a role child, whose allow list removed the goal tools, is told nothing about a goal it cannot open. */
test("gravit: the cycle section sits just before the persona suffix, is literal, and is blank where create_goal is not visible", () => {
  const tree = fakeScope();
  const cycle = "# The research cycle\n\nStep 0 — ask once.";
  apply(tree.ctx, { cycle });
  const section = tree.sections.find((s) => s.name === CYCLE_SECTION)!;
  assert.ok(section);
  assert.equal(section.order, dshSectionOrder("DEPLOYMENT_PERSONA_SUFFIX") - 50);
  assert.equal(section.interpolate, false);
  assert.equal(tree.lookups.length, 0, "nothing is looked up at mount: the gate is read at every assembly");
  const textFor = (visible: string[]) => (section.text as (c: unknown) => string)({ scope: { visible } });
  assert.equal(textFor(["read", "create_goal", "update_goal"]), cycle, "create_goal visible (Gravit, or a fork child): the cycle, verbatim");
  assert.equal(textFor(["read", "grep"]), "", "create_goal not visible (a role child's allow list removed it): nothing");
  tree.unload();
  assert.equal(tree.sections.length, 0, "unloading the preset revision takes the cycle section out with the date's");
});
