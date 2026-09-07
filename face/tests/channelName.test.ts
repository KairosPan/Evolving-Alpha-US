/** The tested half of the create box: the pure whitespace fold.
 *
 * THE BUG THIS CLOSES. `NAME_RE` (src/channels.ts) refuses a space, so an
 * operator typing "Bloom Energy营收预期分析" — or anything with a space in it —
 * got a 400 and no way forward but retyping by hand. It had already happened
 * once: the channel on disk is `市场情绪`, its space collapsed by hand.
 *
 * WHY FOLD RATHER THAN ADMIT THE SPACE. The closed class guarantees a channel
 * path is exactly ONE shell word opening on an alphanumeric. Nothing in the
 * face builds a shell string — `spawn` takes argv arrays and a `cwd` option
 * (src/agents.ts) — but Kairos does, and `cd` is the command it has to write: a
 * channel session's cwd is `strategies/<name>` while AGENTS.md tells it to work
 * from the repo root. Two words after `cd` are zsh's two-argument form, word 1
 * replaced by word 2 in $PWD — usually an error, but exit 0 in the WRONG
 * directory whenever the substituted path exists. That is the failure worth
 * spending a dash on: `python` and `git add` at least refuse a spaced path out
 * loud. AGENTS.md carries the same rule for Kairos, worked example included.
 *
 * The fold is NOT a fence. `createChannel` stays the only gate on a path, and
 * this file pins that folding a hostile name never widens what reaches disk.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
// channelName.js is plain ESM JS (it ships to the browser); tsconfig `allowJs`
// lets this test import it, the same way grouping.test.ts imports grouping.js.
import { foldChannelName } from "../client/channelName.js";
import { createChannel } from "../src/channels.ts";
import { HttpError } from "../src/http.ts";

/** A throwaway root with just the template `createChannel` copies from. Local
 * rather than imported from channels.test.ts, which would run that file's
 * tests a second time. */
async function makeRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "face-foldname-"));
  await mkdir(join(root, "strategies", "_template", "backtests"), { recursive: true });
  return root;
}

test("the name that started this: a space becomes a dash, the rest survives", () => {
  assert.equal(foldChannelName("Bloom Energy营收预期分析"), "Bloom-Energy营收预期分析");
});

test("a full-width space folds too - a Chinese IME emits U+3000, not U+0020", () => {
  const IDEOGRAPHIC = String.fromCharCode(0x3000);
  const NBSP = String.fromCharCode(0xa0);
  assert.equal(foldChannelName(`市场${IDEOGRAPHIC}情绪`), "市场-情绪");
  assert.equal(foldChannelName(`a${NBSP}b`), "a-b");
  assert.equal(foldChannelName("a\nb"), "a-b", "a paste can carry a newline");
  assert.equal(foldChannelName("a\tb"), "a-b", "and a tab");
});

test("spaces around a dash the operator typed collapse to that one dash", () => {
  assert.equal(foldChannelName("Ideas - part 2"), "Ideas-part-2");
  assert.equal(foldChannelName("NVDA -- Q3"), "NVDA-Q3");
});

test("edge whitespace is stripped, never turned into a leading or trailing dash", () => {
  assert.equal(foldChannelName("  Bloom Energy  "), "Bloom-Energy", "a leading dash would be refused");
  assert.equal(foldChannelName(" 存储超级周期\n"), "存储超级周期");
});

test("a dash run the operator typed on purpose is left alone", () => {
  assert.equal(foldChannelName("a--b"), "a--b", "only runs containing whitespace fold");
});

test("a name that is already valid passes through unchanged", () => {
  for (const name of ["storage-chain", "Upper-Case_9", "存储超级周期", "beta-1"]) {
    assert.equal(foldChannelName(name), name);
  }
});

test("the fold normalizes to NFC, so it agrees with createChannel's own fold", () => {
  const NFD = `cafe${String.fromCharCode(0x301)}`;
  assert.equal(foldChannelName(NFD), `caf${String.fromCharCode(0xe9)}`);
});

test("folding a hostile name never produces one createChannel accepts", async () => {
  const root = await makeRoot();
  const NUL = String.fromCharCode(0);
  for (const bad of [
    "", "   ", "_template", " _template ", "../evil", "a/../b", "市场/情绪",
    "a.b", ".hidden", "-lead", "_lead", " . ", " .. ", `a${NUL}b`, "x".repeat(42),
  ]) {
    await assert.rejects(
      createChannel(root, foldChannelName(bad)),
      (err: HttpError) => err.status === 400,
      JSON.stringify(bad),
    );
  }
});

test("the name that started this is ACCEPTED once folded, and lands on disk", async () => {
  const root = await makeRoot();
  const folded = foldChannelName("Bloom Energy营收预期分析");
  assert.equal(folded, "Bloom-Energy营收预期分析");
  // The other createChannel test here only proves refusals. This one proves the
  // fold is worth having: the name the operator typed now reaches disk.
  const created = await createChannel(root, folded);
  assert.equal(created.name, folded);
  assert.ok((await stat(created.dir)).isDirectory());
  assert.ok((await stat(join(root, "strategies", folded))).isDirectory());
});
