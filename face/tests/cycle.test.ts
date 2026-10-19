import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, relative } from "node:path";
import { CYCLE_MAX_BYTES, CYCLE_PATH, readCycle } from "../src/cycle.ts";
import { ROLES_ROOT, readRoles } from "../src/roles.ts";

test("the shipped cycle.md reads, fits its budget, and carries the six steps and the caps", () => {
  const text = readCycle(CYCLE_PATH);
  assert.ok(Buffer.byteLength(text, "utf8") <= CYCLE_MAX_BYTES);
  for (const step of ["Step 0", "Step 1", "Steps 2 to 5", "Step 6"]) assert.ok(text.includes(step), step);
  assert.ok(text.includes("max_goal_rounds 24") && text.includes("12 role calls"));
  assert.ok(text.includes("update_goal with action resume"), "the restart path is stated");
  assert.ok(text.includes("child-limit, bed-window, data-missing or needs-operator"), "the blocked vocabulary is stated");
});

/* cycle.md names the roles it delegates to by tool name, and nothing else ties the two: a role
 * renamed or removed under roles/ would leave Gravit told to call a tool that does not exist. */
test("every role_* tool cycle.md names is a role the shipped library has", () => {
  const named = [...new Set(readCycle(CYCLE_PATH).match(/\brole_[a-z0-9_]+/g) ?? [])].sort();
  assert.ok(named.length > 0, "cycle.md delegates to at least one role");
  const shipped = new Set(readRoles(ROLES_ROOT).map((role) => role.tool));
  assert.deepEqual(named.filter((tool) => !shipped.has(tool)), [], `cycle.md names ${named.join(", ")}; the library has ${[...shipped].sort().join(", ")}`);
});

test("readCycle: trimmed; empty and oversized refused with the path; braces allowed", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-cycle-"));
  try {
    const good = join(dir, "cycle.md");
    await writeFile(good, "\n# Cycle\n\nOpen {{nothing}}.\n\n");
    assert.equal(readCycle(good), "# Cycle\n\nOpen {{nothing}}.");
    const empty = join(dir, "empty.md");
    await writeFile(empty, "  \n");
    assert.throws(() => readCycle(empty), (e: Error) => e.message.includes(empty) && /empty/.test(e.message));
    const big = join(dir, "big.md");
    await writeFile(big, "x".repeat(CYCLE_MAX_BYTES + 1));
    assert.throws(() => readCycle(big), /bytes/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

/* The read fails path-first, as src/roles.ts's does: the message opens with the absolute path of the
 * file, then why - not Node's `ENOENT: no such file or directory, open '...'` (path last), and not,
 * for a directory in the file's place, an `EISDIR` that names no path at all. */
test("readCycle: a missing file and an unreadable one are refused path-first, with the absolute path", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-cycle-"));
  try {
    const missing = join(dir, "no-such-cycle.md");
    assert.throws(() => readCycle(missing), (e: Error) => e.message === `${missing}: the cycle file is missing`);
    /* A relative spelling is reported absolute. */
    assert.throws(() => readCycle(relative(process.cwd(), missing)), (e: Error) => e.message === `${missing}: the cycle file is missing`);
    /* Present but not readable as a file (a directory: EISDIR, the same on every platform and for root). */
    const notAFile = join(dir, "a-directory.md");
    await mkdir(notAFile);
    assert.throws(() => readCycle(notAFile), (e: Error) => e.message.startsWith(`${notAFile}: cannot be read: `) && e.message.includes("EISDIR"));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

/* The cap counts the file's RAW bytes, like ROLE_MD_MAX_BYTES, and is inclusive. Exactly the limit is
 * accepted - here ending in the newline a real file ends with, so the trimmed text is a byte shorter -
 * and one byte more is refused although its trimmed text is exactly the limit, which a cap on the trimmed
 * text would let through. The contract has em dashes in it: "—" (U+2014) is three bytes and one UTF-16
 * unit, so 1,000 of them are exactly the limit, accepted, and 1,001 are refused at 3,003 bytes - a cap
 * on the string's length (1,001) would let them through. */
test("readCycle: the limit is inclusive and counts raw bytes - CYCLE_MAX_BYTES accepted, one more refused, multibyte too", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-cycle-"));
  try {
    const atLimit = join(dir, "at-limit.md");
    await writeFile(atLimit, "x".repeat(CYCLE_MAX_BYTES - 1) + "\n");
    assert.equal(readCycle(atLimit), "x".repeat(CYCLE_MAX_BYTES - 1));
    const over = join(dir, "over.md");
    await writeFile(over, "x".repeat(CYCLE_MAX_BYTES) + "\n");
    assert.throws(() => readCycle(over), (e: Error) => e.message === `${over}: is ${CYCLE_MAX_BYTES + 1} bytes; the limit is ${CYCLE_MAX_BYTES}`);
    assert.equal(CYCLE_MAX_BYTES % 3, 0, "the multibyte cases below assume the limit is a whole number of em dashes");
    const dashes = CYCLE_MAX_BYTES / 3;
    const dashAtLimit = join(dir, "dash-at-limit.md");
    await writeFile(dashAtLimit, "—".repeat(dashes));
    assert.equal(Buffer.byteLength("—".repeat(dashes)), CYCLE_MAX_BYTES);
    assert.equal(readCycle(dashAtLimit), "—".repeat(dashes));
    const dashOver = join(dir, "dash-over.md");
    await writeFile(dashOver, "—".repeat(dashes + 1));
    assert.throws(() => readCycle(dashOver), (e: Error) => e.message === `${dashOver}: is ${CYCLE_MAX_BYTES + 3} bytes; the limit is ${CYCLE_MAX_BYTES}`);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
