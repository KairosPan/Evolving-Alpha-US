import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { CORDIS_PIN, DSH_PIN } from "../src/version.ts";

/** The face's own manifest, read rather than imported so the assertions below
 * see the declared RANGE strings and not just what npm happened to install. */
function manifest(): { dependencies?: Record<string, string>; devDependencies?: Record<string, string> } {
  return JSON.parse(readFileSync(fileURLToPath(new URL("../package.json", import.meta.url)), "utf8"));
}

/** Every `@deepseek-ai/dsh-*` requirement the face declares, from both blocks.
 * Deliberately NOT a hand-written list: a sample can only pin the packages
 * someone remembered to add to it, and the four rows the storage chain needed
 * were added months after this test was written. */
function dshRequirements(): Array<[string, string]> {
  const { dependencies = {}, devDependencies = {} } = manifest();
  return Object.entries({ ...dependencies, ...devDependencies })
    .filter(([name]) => name.startsWith("@deepseek-ai/dsh-"));
}

test("every declared @deepseek-ai/dsh-* requirement is the exact pin", () => {
  assert.equal(DSH_PIN, "0.1.1-rc.2");
  const requirements = dshRequirements();
  // Guard against a filter that silently matches nothing (or stops matching the
  // family prefix): a vacuous pass here is indistinguishable from a green suite.
  // Anchors rather than a count, so adding a dependency never trips this.
  const names = requirements.map(([name]) => name);
  for (const anchor of ["@deepseek-ai/dsh-app-boot", "@deepseek-ai/dsh-base"]) {
    assert.ok(names.includes(anchor), `${anchor} missing - the filter matched nothing useful`);
  }
  for (const [name, range] of requirements) {
    // Exact, not a range: spec section 4 mandates lockstep. A caret would let
    // `npm install` drift one package of the family onto a newer rc, and the
    // dsh packages are only ever tested against each other at one version.
    assert.equal(range, DSH_PIN, `${name} must be pinned exactly, got ${JSON.stringify(range)}`);
  }
});

test("every installed @deepseek-ai/dsh-* package matches the pin", () => {
  const require = createRequire(import.meta.url);
  for (const [name] of dshRequirements()) {
    const version = require(`${name}/package.json`).version as string;
    assert.equal(version, DSH_PIN, name);
  }
});

// cordis rides its own version track (4.x), not the dsh 0.1.1-rc.2 family — the
// dsh packages peer-depend on it at ^4.0.1. Pin it separately so an upgrade of
// either track is a deliberate edit here.
test("cordis matches its own pin", () => {
  assert.equal(CORDIS_PIN, "4.0.2");
  const require = createRequire(import.meta.url);
  const version = require("@deepseek-ai/cordis/package.json").version as string;
  assert.equal(version, CORDIS_PIN, "@deepseek-ai/cordis");
});
