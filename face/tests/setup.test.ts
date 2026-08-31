import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";

test("creates the face profile with dsh-base bundle and empty patch layer", () => {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  const res = setupFaceProfile(home);
  assert.equal(res.created, true);
  const pkg = JSON.parse(readFileSync(join(res.dir, "package.json"), "utf8"));
  assert.deepEqual(pkg.dsh.profile.bundles, ["@deepseek-ai/dsh-base"]);
  assert.equal(pkg.private, true);
  const patch = readFileSync(join(res.dir, "cordis.patch.yml"), "utf8");
  assert.match(patch, /^#/m);           // commented header
  assert.doesNotMatch(patch, /^- /m);   // no active entries
});

test("refuses to overwrite an existing profile", () => {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  const dir = join(home, "profiles", "face");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "cordis.patch.yml"), "# operator content\n");
  const res = setupFaceProfile(home);
  assert.equal(res.created, false);
  assert.equal(readFileSync(join(dir, "cordis.patch.yml"), "utf8"), "# operator content\n");
  // "touches nothing" is the whole point: not even the file the operator lacks.
  assert.equal(existsSync(join(dir, "package.json")), false);
});
