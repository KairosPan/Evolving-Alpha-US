import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
// The REAL consumer: loadProfile() reads $DSH_HOME/profiles/<name>/cordis.patch.yml
// through loadOverlayPatches (dsh-app-boot lib/index.js, loadProfile), and
// PROFILE_PATCH_FILENAME is the name it looks for. Asserting against the
// package's own loader — instead of regexing the text — is what catches a file
// that reads fine but cannot load.
import { loadOverlayPatches, PROFILE_PATCH_FILENAME } from "@deepseek-ai/dsh-app-boot";
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

// A comment-only YAML document parses to `undefined`, and dsh's parsePatchList
// throws "must be a top-level YAML array" on it — a failure no amount of
// regexing the file's text can see. This test loads what we wrote with the
// function dsh itself calls, so the patch file is verified to BOOT, not to
// merely look right.
test("the written patch layer loads through dsh's own overlay loader", () => {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  const { dir } = setupFaceProfile(home);
  // Also pins the filename: loadOverlayPatches throws if the file is absent,
  // so writing it under any other name fails here.
  const patches = loadOverlayPatches("kairos-face", join(dir, PROFILE_PATCH_FILENAME));
  assert.ok(Array.isArray(patches), "patch layer must parse to a top-level array");
  assert.equal(patches.length, 0, "the operator's layer ships empty");
});

// dsh's own initProfile writes this third file; a profile without it works
// until the operator runs `dsh plugin add` into it.
test("writes the pnpm settings an out-of-tree plugin install needs", () => {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  const { dir } = setupFaceProfile(home);
  assert.equal(
    readFileSync(join(dir, "pnpm-workspace.yaml"), "utf8"),
    "packages:\n  - .\n\nnodeLinker: hoisted\nautoInstallPeers: false\n",
  );
});

test("honors a non-default profile name", () => {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  const res = setupFaceProfile(home, "face-dev");
  assert.equal(res.created, true);
  assert.equal(res.dir, join(home, "profiles", "face-dev"));
  assert.ok(existsSync(join(res.dir, "package.json")));
});

test("refuses to overwrite an existing profile", () => {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  const dir = join(home, "profiles", "face");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "cordis.patch.yml"), "# operator content\n");
  const res = setupFaceProfile(home);
  assert.equal(res.created, false);
  assert.equal(readFileSync(join(dir, "cordis.patch.yml"), "utf8"), "# operator content\n");
  // "touches nothing" is the whole point: not even the files the operator lacks.
  assert.equal(existsSync(join(dir, "package.json")), false);
  assert.equal(existsSync(join(dir, "pnpm-workspace.yaml")), false);
});
