import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { listChannelDirs, readChannelStatus } from "../src/channels.ts";

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

test("listChannelDirs: strategies as a file (not directory) throws ENOTDIR", async () => {
  const root = await mkdtemp(join(tmpdir(), "face-enotdir-"));
  await writeFile(join(root, "strategies"), "not a directory");
  await assert.rejects(
    () => listChannelDirs(root),
    (err: NodeJS.ErrnoException) => err.code === "ENOTDIR",
  );
});

async function statusDir(text: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), "face-status-"));
  await writeFile(join(dir, "status.yaml"), text);
  return dir;
}

test("readChannelStatus reads the optional headline keys", async () => {
  const dir = await statusDir([
    "status: researching   # idea | researching | validated",
    "one_line: 存储涨价周期仍在早期",
    "next: 等 11 月合约价",
    "numbers:",
    "  样本天数: 526",
    "  最大回撤: -18.98%",
    "",
  ].join("\n"));
  const s = await readChannelStatus(dir);
  assert.equal(s.status, "researching");
  assert.equal(s.one_line, "存储涨价周期仍在早期");
  assert.equal(s.next, "等 11 月合约价");
  assert.deepEqual(s.numbers, { 样本天数: "526", 最大回撤: "-18.98%" });
});

test("readChannelStatus: today's one-line file still works, and unknown keys are ignored", async () => {
  const s = await readChannelStatus(await statusDir("status: idea   # idea | researching\nmystery: 7\n"));
  assert.deepEqual(s, { status: "idea" });
});

test("readChannelStatus: malformed YAML degrades to the regex — a badge, not a gate", async () => {
  const s = await readChannelStatus(await statusDir("status: paper\n  bad: [unclosed\n"));
  assert.equal(s.status, "paper", "the status word still comes through");
  assert.equal(s.one_line, undefined);
});

test("readChannelStatus: no file at all is an empty reading, never a throw", async () => {
  assert.deepEqual(await readChannelStatus(await mkdtemp(join(tmpdir(), "face-nostatus-"))), {});
});

test("readChannelStatus: numbers is stringified, and a non-object numbers is dropped", async () => {
  assert.deepEqual((await readChannelStatus(await statusDir("numbers:\n  n: 526\n"))).numbers, { n: "526" });
  assert.equal((await readChannelStatus(await statusDir("numbers: 7\n"))).numbers, undefined);
});
