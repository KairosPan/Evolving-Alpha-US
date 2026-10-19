/** scripts/schema-sizes.ts's guard, offline: `refusal(home, live)` decides, before any dsh code
 * loads, whether the script may boot `home`. It must refuse the live harness home however it is
 * spelled - the same path, a trailing slash, a `..` back into it, a symlink to it or to a directory
 * inside it, a path inside it, a directory above it (also when the live home is itself a symlink) -
 * allow a separate copy, and refuse a home the face never set up. Every "live home" here is a temp
 * directory; nothing touches `~/.dsh`. */
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { refusal } from "../scripts/schema-sizes.ts";

/** A canonical temp directory (macOS puts tmpdir behind the /var -> /private/var link). */
function tempDir(prefix: string): string {
  return realpathSync.native(mkdtempSync(join(tmpdir(), prefix)));
}

/** A directory laid out like a home the face has booted: `profiles/face/package.json` exists. */
function faceHome(path: string): string {
  mkdirSync(path, { recursive: true });
  setupFaceProfile(path);
  return path;
}

const INSIDE = /is, or is inside, the live harness home/;
const CONTAINS = /contains the live harness home/;

test("schema-sizes refusal: the live home however it is spelled, inside it and above it; a copy allowed; an unset-up home refused", (t) => {
  const root = tempDir("face-sizes-");
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const live = faceHome(join(root, "live"));
  const refused = (home: string, pattern: RegExp, label: string, lives: readonly string[] = [live]) =>
    assert.match(refusal(home, lives) ?? "(allowed)", pattern, label);

  refused(live, INSIDE, "the same path");
  refused(`${live}/`, INSIDE, "a trailing slash");
  faceHome(join(root, "elsewhere"));
  refused(`${join(root, "elsewhere")}/../${basename(live)}`, INSIDE, "a `..` back into the live home");
  symlinkSync(live, join(root, "looks-like-a-copy"));
  refused(join(root, "looks-like-a-copy"), INSIDE, "a symlink to the live home");
  const inside = faceHome(join(live, "copy"));
  refused(inside, INSIDE, "a path inside the live home");
  symlinkSync(inside, join(root, "copy-link"));
  refused(join(root, "copy-link"), INSIDE, "a symlink to a directory inside the live home");
  refused(join(live, "not-made-yet"), INSIDE, "a path inside the live home that does not exist yet");
  refused(root, CONTAINS, "a parent of the live home");

  /* The live home itself reached through a symlink, as a `DSH_HOME` pointing at a link would make
   * it: the directory above its REAL location still contains it. */
  const realParent = join(root, "real");
  const realLive = faceHome(join(realParent, "home"));
  symlinkSync(realLive, join(root, "live-link"));
  refused(realParent, CONTAINS, "a parent of a symlinked live home's real directory", [join(root, "live-link")]);
  refused(realLive, INSIDE, "the real directory of a symlinked live home", [join(root, "live-link")]);

  const copy = faceHome(join(root, "copy-of-live"));
  assert.equal(refusal(copy, [live]), undefined, "a separate copy is allowed");
  assert.equal(refusal(copy, [live, realLive]), undefined, "against every live candidate");
  const bare = join(root, "bare");
  mkdirSync(bare);
  assert.match(refusal(bare, [live]) ?? "(allowed)", /has no profiles\/face/, "a home the face never set up is refused");
  assert.match(refusal(join(root, "absent"), [live]) ?? "(allowed)", /has no profiles\/face/, "and so is one that does not exist");
});

/* By device and inode, so a name spelled in another letter case on a case-insensitive volume (the macOS
 * default) is the same directory; skipped where the temp volume is case-sensitive. */
test("schema-sizes refusal: the live home spelled in another letter case", (t) => {
  const root = tempDir("face-sizes-case-");
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const live = faceHome(join(root, "LiveHome"));
  const other = join(dirname(live), "livehome");
  if (!existsSync(other)) {
    t.skip("the temp volume is case-sensitive");
    return;
  }
  assert.match(refusal(other, [live]) ?? "(allowed)", INSIDE);
});
