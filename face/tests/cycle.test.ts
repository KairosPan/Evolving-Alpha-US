import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
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
