import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { CORDIS_INCLUDE_PIN, CORDIS_PIN, DSH_PIN } from "../src/version.ts";

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
  assert.equal(DSH_PIN, "0.2.0-rc.2");
  const requirements = dshRequirements();
  // Guard against a filter that silently matches nothing (or stops matching the
  // family prefix): a vacuous pass here is indistinguishable from a green suite.
  // Anchors rather than a count, so adding a dependency never trips this.
  const names = requirements.map(([name]) => name);
  for (const anchor of ["@deepseek-ai/dsh-app-boot", "@deepseek-ai/dsh-base"]) {
    assert.ok(names.includes(anchor), `${anchor} missing - the filter matched nothing useful`);
  }
  for (const [name, range] of requirements) {
    // Exact, not a range: the README mandates lockstep. A caret would let
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

// cordis rides its own version track (4.x), not the dsh family — the dsh
// packages peer-depend on it at ~4.0.4. Pin it separately so an upgrade of
// either track is a deliberate edit here.
test("cordis matches its own pin", () => {
  assert.equal(CORDIS_PIN, "4.0.4");
  const { dependencies = {} } = manifest();
  assert.equal(dependencies["@deepseek-ai/cordis"], CORDIS_PIN, "declared range must be the exact pin");
  const require = createRequire(import.meta.url);
  const version = require("@deepseek-ai/cordis/package.json").version as string;
  assert.equal(version, CORDIS_PIN, "@deepseek-ai/cordis");
});

// The include plugin is the one cordis-plugin-* the face imports itself
// (entryListSchema); the rest are transitive and lockfile-held.
test("cordis-plugin-include matches its own pin", () => {
  assert.equal(CORDIS_INCLUDE_PIN, "1.0.9");
  const { dependencies = {} } = manifest();
  assert.equal(dependencies["@deepseek-ai/cordis-plugin-include"], CORDIS_INCLUDE_PIN, "declared range must be the exact pin");
  const require = createRequire(import.meta.url);
  const version = require("@deepseek-ai/cordis-plugin-include/package.json").version as string;
  assert.equal(version, CORDIS_INCLUDE_PIN, "@deepseek-ai/cordis-plugin-include");
});

// Packages dsh 0.2.0-rc.2 deleted or that the face stopped mounting. A partial
// revert of the upgrade would bring one of these back as a resolvable name
// pointing at a 0.1.1-rc.2 tarball, and the pin sweep above would then pass
// against a mixed-version tree.
test("retired packages are not declared", () => {
  const { dependencies = {}, devDependencies = {} } = manifest();
  const declared = { ...dependencies, ...devDependencies };
  for (const retired of [
    "@deepseek-ai/dsh-agent-presets",
    "@deepseek-ai/dsh-host-apiproxy",
    "@deepseek-ai/dsh-cordis-host-runner",
  ]) {
    assert.equal(declared[retired], undefined, `${retired} was retired at 0.2.0-rc.2 and must not be declared`);
  }
});
