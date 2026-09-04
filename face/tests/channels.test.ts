import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { listChannelDirs, readChannelStatus, readChannelBody, reconcileChannels } from "../src/channels.ts";
import { rosterFor, setRoster } from "../src/roster.ts";

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

const TEMPLATE_THESIS = "# <strategy name>\n\n**Status:** idea\n\n## Thesis\n\nWhat market behavior does this capture, and why does it exist?\n";

test("readChannelBody: an untouched template thesis is flagged, not presented as content", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-body-"));
  await writeFile(join(dir, "THESIS.md"), TEMPLATE_THESIS);
  const body = await readChannelBody(dir);
  assert.equal(body.thesis?.isTemplate, true);
});

test("readChannelBody: a written thesis is not flagged", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-body2-"));
  await writeFile(join(dir, "THESIS.md"), "# 市场情绪\n\n## Thesis\n\nBreadth leads price.\n");
  const body = await readChannelBody(dir);
  assert.equal(body.thesis?.isTemplate, false);
  assert.match(body.thesis?.markdown ?? "", /Breadth leads price/);
});

test("readChannelBody: no THESIS.md is null, not an empty string", async () => {
  assert.equal((await readChannelBody(await mkdtemp(join(tmpdir(), "face-body3-")))).thesis, null);
});

test("readChannelBody: journal entries parse newest first, prose without a date is ignored", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-body4-"));
  await writeFile(join(dir, "journal.md"), [
    "# Journal",
    "",
    "- 2026-09-01: built the composite.",
    "- 2026-09-02: falsified; cold +0.82%.",
    "some loose prose",
    "",
  ].join("\n"));
  const body = await readChannelBody(dir);
  assert.deepEqual(body.journal.map((e) => e.date), ["2026-09-02", "2026-09-01"]);
  assert.equal(body.journal[0].text, "falsified; cold +0.82%.");
});

test("readChannelBody: the newest backtest by FILENAME date is picked and parsed", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-body5-"));
  await mkdir(join(dir, "backtests"), { recursive: true });
  await writeFile(join(dir, "backtests", "2026-09-02-sentiment.json"), JSON.stringify({ n_days: 526 }));
  await writeFile(join(dir, "backtests", "2026-08-11-run.json"), JSON.stringify({ n_days: 1 }));
  await writeFile(join(dir, "backtests", "sentiment_series.csv"), "day,score\n");
  await writeFile(join(dir, "backtests", ".gitkeep"), "");
  const body = await readChannelBody(dir);
  assert.deepEqual(body.backtests.map((b) => b.file), ["2026-09-02-sentiment.json", "2026-08-11-run.json", "sentiment_series.csv"]);
  assert.equal(body.latest?.file, "2026-09-02-sentiment.json");
  assert.deepEqual(body.latest?.json, { n_days: 526 });
});

test("readChannelBody: an unparseable backtest never throws — latest is null, the file still lists", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-body6-"));
  await mkdir(join(dir, "backtests"), { recursive: true });
  await writeFile(join(dir, "backtests", "2026-09-02-broken.json"), "{not json");
  const body = await readChannelBody(dir);
  assert.equal(body.latest, null);
  assert.deepEqual(body.backtests.map((b) => b.file), ["2026-09-02-broken.json"]);
});

test("readChannelBody: the file list skips __pycache__ and directories", async () => {
  const dir = await mkdtemp(join(tmpdir(), "face-body7-"));
  await mkdir(join(dir, "__pycache__"), { recursive: true });
  await mkdir(join(dir, "backtests"), { recursive: true });
  await writeFile(join(dir, "screen.py"), "print(1)\n");
  const body = await readChannelBody(dir);
  assert.deepEqual(body.files.map((f) => f.name), ["screen.py"]);
});

/** A registry standing in for ctx.workspaceRegistry: the same create
 * idempotence and the same membership early-out the real one has. Exported
 * because Task 7 reuses it. */
export function fakeRegistry(): { registry: any; attaches: string[] } {
  const byPath = new Map<string, any>();
  const attaches: string[] = [];
  let next = 0;
  const registry = {
    archivedSessionIds: [] as string[],
    list: () => [...byPath.values()],
    async create(path: string, title?: string) {
      const had = byPath.get(path);
      if (had !== undefined) return had; // idempotent; title unchanged
      const ws = {
        id: `ws-${++next}`,
        path,
        title: title ?? path.split("/").pop(),
        sessionIds: [] as string[],
        async attachSession(sessionId: string) {
          if (ws.sessionIds.includes(sessionId)) return; // membership early-out
          attaches.push(`${ws.id}:${sessionId}`);
          ws.sessionIds.push(sessionId);
        },
        async status() { return "ok" as const; },
      };
      byPath.set(path, ws);
      return ws;
    },
  };
  return { registry, attaches };
}

test("reconcileChannels adopts every channel dir plus the repo root, and is idempotent", async () => {
  const root = await makeRoot();
  const home = await mkdtemp(join(tmpdir(), "face-home-"));
  const { registry, attaches } = fakeRegistry();
  const sessions = [
    { sessionId: "session-a", cwd: root },
    { sessionId: "session-b", cwd: join(root, "strategies", "alpha") },
    { sessionId: "session-c", cwd: "/Users/pan/Desktop/trend-dragon" },
  ];
  const first = await reconcileChannels({ registry, root, home, sessions, connectedBins: ["claude", "codex"] });

  assert.deepEqual(first.channels.map((c) => c.name), ["workbench", "alpha", "市场情绪"]);
  assert.deepEqual(first.ungrouped.map((s) => s.sessionId), ["session-c"], "a foreign session is counted, never dropped");
  assert.equal(attaches.length, 2, "session-a to the workbench, session-b to alpha");

  const second = await reconcileChannels({ registry, root, home, sessions, connectedBins: ["claude", "codex"] });
  assert.equal(attaches.length, 2, "a repeat listing attaches nothing new");
  assert.deepEqual(second.channels.map((c) => c.workspaceId), first.channels.map((c) => c.workspaceId), "ids are stable");
});

test("reconcileChannels seeds each channel's roster once, from the connected bins", async () => {
  const root = await makeRoot();
  const home = await mkdtemp(join(tmpdir(), "face-home2-"));
  const { registry } = fakeRegistry();
  const run = () => reconcileChannels({ registry, root, home, sessions: [], connectedBins: ["codex"] });
  const first = await run();
  const alpha = first.channels.find((c) => c.name === "alpha")!;
  assert.deepEqual(await rosterFor(home, alpha.workspaceId), ["codex"]);

  await setRoster(home, alpha.workspaceId, []);
  await run();
  assert.deepEqual(await rosterFor(home, alpha.workspaceId), [], "a second listing never re-seeds over the operator");
});

test("reconcileChannels carries status and reports a missing directory instead of deleting it", async () => {
  const root = await makeRoot();
  const home = await mkdtemp(join(tmpdir(), "face-home3-"));
  const { registry } = fakeRegistry();
  const ghost = await registry.create(join(root, "strategies", "vanished"));
  ghost.status = async () => "missing-dir" as const;

  const out = await reconcileChannels({ registry, root, home, sessions: [], connectedBins: [] });
  assert.equal(out.channels.find((c) => c.name === "alpha")?.status, "researching");
  const gone = out.channels.find((c) => c.dir.endsWith("vanished"));
  assert.equal(gone?.missingDir, true, "a registered workspace whose directory is gone still lists, greyed");
});

test("reconcileChannels attaches only sessions whose cwd IS the channel directory", async () => {
  const root = await makeRoot();
  const home = await mkdtemp(join(tmpdir(), "face-home4-"));
  const { registry, attaches } = fakeRegistry();
  await reconcileChannels({
    registry, root, home, connectedBins: [],
    sessions: [{ sessionId: "session-deep", cwd: join(root, "strategies", "alpha", "backtests") }],
  });
  assert.deepEqual(attaches, [], "a subdirectory is not the channel; the host would reject the attach anyway");
});
