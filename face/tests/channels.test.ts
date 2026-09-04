import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { listChannelDirs } from "../src/channels.ts";

/** A throwaway workbench root: strategies/{_template, alpha, 市场情绪,
 * .hidden, __pycache__} plus a stray FILE that must never list. */
export async function makeRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "face-channels-"));
  for (const name of ["_template", "alpha", "市场情绪", ".hidden", "__pycache__"]) {
    await mkdir(join(root, "strategies", name, "backtests"), { recursive: true });
  }
  await writeFile(join(root, "strategies", "loose.txt"), "not a channel");
  await writeFile(join(root, "strategies", "alpha", "status.yaml"), "status: researching  # comment\n");
  return root;
}

test("listChannelDirs: repo root first, then strategies; template, dotted, __ and files excluded", async () => {
  const root = await makeRoot();
  const dirs = await listChannelDirs(root);
  assert.deepEqual(dirs.map((d) => d.name), ["workbench", "alpha", "市场情绪"]);
  assert.equal(dirs[0].isRoot, true);
  assert.equal(dirs[0].dir, root);
  assert.equal(dirs[1].isRoot, false);
  assert.equal(dirs[1].dir, join(root, "strategies", "alpha"));
});

test("listChannelDirs: a missing strategies/ still yields the workbench", async () => {
  const root = await mkdtemp(join(tmpdir(), "face-empty-"));
  assert.deepEqual((await listChannelDirs(root)).map((d) => d.name), ["workbench"]);
});
