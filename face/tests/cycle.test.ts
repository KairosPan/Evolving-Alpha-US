import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { CYCLE_MAX_BYTES, CYCLE_PATH, readCycle } from "../src/cycle.ts";

test("the shipped cycle.md reads, fits its budget, and carries the six steps and the caps", () => {
  const text = readCycle(CYCLE_PATH);
  assert.ok(Buffer.byteLength(text, "utf8") <= CYCLE_MAX_BYTES);
  for (const step of ["Step 0", "Step 1", "Steps 2 to 5", "Step 6"]) assert.ok(text.includes(step), step);
  assert.ok(text.includes("max_goal_rounds 24") && text.includes("12 role calls"));
  assert.ok(text.includes("update_goal with action resume"), "the restart path is stated");
  assert.ok(text.includes("child-limit, bed-window, data-missing or needs-operator"), "the blocked vocabulary is stated");
});

test("readCycle: trimmed; empty and oversized refused with the path; braces allowed", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-cycle-"));
  const good = join(dir, "cycle.md");
  await writeFile(good, "\n# Cycle\n\nOpen {{nothing}}.\n\n");
  assert.equal(readCycle(good), "# Cycle\n\nOpen {{nothing}}.");
  const empty = join(dir, "empty.md");
  await writeFile(empty, "  \n");
  assert.throws(() => readCycle(empty), (e: Error) => e.message.includes(empty) && /empty/.test(e.message));
  const big = join(dir, "big.md");
  await writeFile(big, "x".repeat(CYCLE_MAX_BYTES + 1));
  assert.throws(() => readCycle(big), /bytes/);
});

/* The read fails path-first, as src/roles.ts's does: the message opens with the absolute path of the
 * file, then why - not Node's `ENOENT: no such file or directory, open '...'` (path last), and not,
 * for a directory in the file's place, an `EISDIR` that names no path at all. */
test("readCycle: a missing file and an unreadable one are refused path-first, with the absolute path", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-cycle-"));
  const missing = join(dir, "no-such-cycle.md");
  assert.throws(() => readCycle(missing), (e: Error) => e.message === `${missing}: the cycle file is missing`);
  /* A relative spelling is reported absolute. */
  assert.throws(() => readCycle(relative(process.cwd(), missing)), (e: Error) => e.message === `${missing}: the cycle file is missing`);
  /* Present but not readable as a file (a directory: EISDIR, the same on every platform and for root). */
  const notAFile = join(dir, "a-directory.md");
  await mkdir(notAFile);
  assert.throws(() => readCycle(notAFile), (e: Error) => e.message.startsWith(`${notAFile}: cannot be read: `) && e.message.includes("EISDIR"));
});

/* The cap counts the file's RAW bytes, like ROLE_MD_MAX_BYTES, and is inclusive. Exactly the limit is
 * accepted - here ending in the newline a real file ends with, so the trimmed text is a byte shorter -
 * and one byte more is refused although its trimmed text is exactly the limit, which a cap on the trimmed
 * text would let through. */
test("readCycle: the limit is inclusive and counts raw bytes - CYCLE_MAX_BYTES accepted, one more refused", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-cycle-"));
  const atLimit = join(dir, "at-limit.md");
  await writeFile(atLimit, "x".repeat(CYCLE_MAX_BYTES - 1) + "\n");
  assert.equal(readCycle(atLimit), "x".repeat(CYCLE_MAX_BYTES - 1));
  const over = join(dir, "over.md");
  await writeFile(over, "x".repeat(CYCLE_MAX_BYTES) + "\n");
  assert.throws(() => readCycle(over), (e: Error) => e.message === `${over}: is ${CYCLE_MAX_BYTES + 1} bytes; the limit is ${CYCLE_MAX_BYTES}`);
});
