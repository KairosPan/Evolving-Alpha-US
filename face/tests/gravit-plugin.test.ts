import test from "node:test";
import assert from "node:assert/strict";
import SystemPrompt from "@deepseek-ai/dsh-system-prompt";
import { TODAY_SECTION, apply, inject, name, resolveZone, todayText, validateGravitConfig } from "../plugins/gravit.js";

const dshSectionOrder = (slot: "DEPLOYMENT_PERSONA_PREFIX"): number => SystemPrompt.prototype.getSectionOrder(slot);

function fakeScope() {
  const sections: Array<{ name: string; order: number; interpolate?: boolean; text: unknown }> = [];
  const disposers: Array<() => unknown> = [];
  const ctx = {
    effect(fn: () => unknown) { const d = fn(); assert.equal(typeof d, "function"); disposers.push(d as () => unknown); return d; },
    systemPrompt: {
      section(section: { name: string; order: number; interpolate?: boolean; text: unknown }) {
        sections.push(section);
        return () => { sections.splice(sections.indexOf(section), 1); };
      },
      getSectionOrder: (slot: "DEPLOYMENT_PERSONA_PREFIX") => dshSectionOrder(slot),
    },
  };
  return { ctx, sections, unload: () => { for (const d of disposers.splice(0).reverse()) d(); } };
}

test("gravit: name and inject are what the composition relies on", () => {
  assert.equal(name, "gravit");
  assert.deepEqual(inject, ["systemPrompt"]);
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
