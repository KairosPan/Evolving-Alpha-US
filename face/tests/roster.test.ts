import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { logRosterWrite, readRosters, rosterFor, seedRoster, setRoster } from "../src/roster.ts";

const home = (): Promise<string> => mkdtemp(join(tmpdir(), "face-roster-"));

async function corrupt(h: string): Promise<void> {
  await mkdir(join(h, "face"), { recursive: true });
  await writeFile(join(h, "face", "channels.json"), "{not json");
}

test("an absent file reads as no rosters and is not corrupt", async () => {
  assert.deepEqual(await readRosters(await home()), { rosters: {}, corrupt: false });
});

test("seedRoster writes once and never overwrites an existing entry", async () => {
  const h = await home();
  await seedRoster(h, "ws-1", ["claude", "codex"]);
  await seedRoster(h, "ws-1", ["claude"]);
  assert.deepEqual(await rosterFor(h, "ws-1"), ["claude", "codex"]);
});

test("setRoster is the operator's explicit write and replaces the set", async () => {
  const h = await home();
  await seedRoster(h, "ws-1", ["claude", "codex"]);
  await setRoster(h, "ws-1", ["codex"]);
  assert.deepEqual(await rosterFor(h, "ws-1"), ["codex"]);
  await setRoster(h, "ws-1", []);
  assert.deepEqual(await rosterFor(h, "ws-1"), [], "an empty roster is a real, definite set");
});

test("rosterFor: an unknown workspace is null, not an empty set", async () => {
  assert.equal(await rosterFor(await home(), "ws-nope"), null);
});

test("a corrupt file fails CLOSED: no rosters, and seeding never overwrites it", async () => {
  const h = await home();
  await corrupt(h);
  assert.deepEqual(await readRosters(h), { rosters: {}, corrupt: true });
  assert.equal(await rosterFor(h, "ws-1"), null);
  await seedRoster(h, "ws-1", ["claude"]);
  assert.equal(await readFile(join(h, "face", "channels.json"), "utf8"), "{not json", "the operator's file is never clobbered by a background seed");
});

test("setRoster REFUSES over a corrupt file - it must not replace every other channel's roster with just this one entry (I1)", async () => {
  const h = await home();
  await corrupt(h);
  const path = join(h, "face", "channels.json");
  const before = await readFile(path, "utf8");
  await assert.rejects(
    setRoster(h, "ws-1", ["claude"]),
    (err: Error) => err.message.includes(path) && /corrupt/i.test(err.message),
    "the refusal names the file's absolute path",
  );
  assert.equal(
    await readFile(path, "utf8"),
    before,
    "the operator's bytes on disk are unchanged - a click on one channel must not wipe the others",
  );
});

test("concurrent seed and toggle: the operator's write survives", async () => {
  const h = await home();
  await seedRoster(h, "ws-1", ["claude", "codex"]);
  /* a sidebar poll seeding a NEW channel races an operator toggle on an old one */
  await Promise.all([
    seedRoster(h, "ws-2", ["claude"]),
    setRoster(h, "ws-1", ["codex"]),
  ]);
  assert.deepEqual(await rosterFor(h, "ws-1"), ["codex"], "the toggle was not reverted");
  assert.deepEqual(await rosterFor(h, "ws-2"), ["claude"], "the seed still landed");
});

test("bins are stored as given but junk entries are dropped on read", async () => {
  const h = await home();
  await mkdir(join(h, "face"), { recursive: true });
  await writeFile(join(h, "face", "channels.json"), JSON.stringify({
    version: 1, channels: { "ws-1": { agents: ["codex", 7, null, "codex"] } },
  }));
  assert.deepEqual(await rosterFor(h, "ws-1"), ["codex"], "non-strings and duplicates drop");
});

test("logRosterWrite appends a dated, append-only line naming the workspace and the resulting roster (I2)", async () => {
  const h = await home();
  await logRosterWrite(h, "ws-1", ["claude", "codex"]);
  const first = (await readFile(join(h, "face", "roster.log"), "utf8")).trim().split("\n");
  assert.equal(first.length, 1);
  assert.match(first[0]!, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z roster ws-1 = \[claude, codex\]$/);

  await logRosterWrite(h, "ws-1", []);
  const second = (await readFile(join(h, "face", "roster.log"), "utf8")).trim().split("\n");
  assert.equal(second.length, 2, "append-only: a second write grows the log, never replaces it");
  assert.match(second[1]!, /roster ws-1 = \[\]$/);
});

test("logRosterWrite swallows a write failure - the log is a record, never a gate on the roster write it follows (I2)", async () => {
  const h = await home();
  // A FILE named "face" blocks `mkdir(home/face, {recursive:true})` with
  // ENOTDIR - the write failure the durable half of this log can hit for real.
  await writeFile(join(h, "face"), "not a directory");
  await assert.doesNotReject(logRosterWrite(h, "ws-1", ["claude"]));
});
