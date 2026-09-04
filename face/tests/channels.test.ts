import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, realpath, stat, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import {
  createChannel, listChannelDirs, mergeSessionHeads, readChannelStatus, readChannelBody,
  reconcileChannels, registerChannelRoutes,
} from "../src/channels.ts";
import { rosterFor, setRoster } from "../src/roster.ts";
import { HttpError } from "../src/http.ts";

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

/** A registry standing in for ctx.workspaceRegistry: the same path
 * canonicalization (via `fs.realpath`) and the same rejection of a
 * nonexistent/non-directory path that the real `create` has, the same
 * create idempotence, the same membership early-out on `attachSession`, and
 * a `status()` that genuinely checks the directory rather than being told
 * what to answer. `attachSession` additionally rejects any session id named
 * in `rejectSessionIds`, standing in for the real header-cwd-mismatch
 * rejection. Exported because Task 7 reuses it. */
export function fakeRegistry(opts: { rejectSessionIds?: readonly string[] } = {}): { registry: any; attaches: string[] } {
  const rejectSessionIds = new Set(opts.rejectSessionIds ?? []);
  const byRealPath = new Map<string, any>();
  const attaches: string[] = [];
  let next = 0;
  const registry = {
    archivedSessionIds: [] as string[],
    list: () => [...byRealPath.values()],
    async create(path: string, title?: string) {
      // The real registry canonicalizes via fs.realpath and rejects a
      // nonexistent or non-directory path outright (it throws before ever
      // recording anything) - mirror both, so a reconcile racing a deleted
      // directory, or leaning on the raw `join()` spelling instead of the
      // canonical one, can't pass by accident here and only fail for real.
      const real = await realpath(path);
      if (!(await stat(real)).isDirectory()) throw new Error(`not a directory: ${path}`);
      const had = byRealPath.get(real);
      if (had !== undefined) return had; // idempotent; title unchanged
      const ws = {
        id: `ws-${++next}`,
        path: real,
        title: title ?? real.split("/").pop(),
        sessionIds: [] as string[],
        async attachSession(sessionId: string) {
          if (ws.sessionIds.includes(sessionId)) return; // membership early-out
          if (rejectSessionIds.has(sessionId)) {
            throw new Error(`cwd mismatch: ${sessionId} does not belong to ${ws.path}`);
          }
          attaches.push(`${ws.id}:${sessionId}`);
          ws.sessionIds.push(sessionId);
        },
        async status() {
          // A workspace's directory can vanish after it was created; report
          // that instead of throwing, same as the real registry.
          try {
            return (await stat(ws.path)).isDirectory() ? "ok" as const : "missing-dir" as const;
          } catch {
            return "missing-dir" as const;
          }
        },
      };
      byRealPath.set(real, ws);
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
  // A missing-dir workspace arises only by deleting a directory AFTER a
  // successful create - the real registry rejects `create` on a directory
  // that never existed, so that is the only honest way to set this up.
  const vanishedDir = join(root, "strategies", "vanished");
  await mkdir(vanishedDir, { recursive: true });
  await registry.create(vanishedDir);
  await rm(vanishedDir, { recursive: true, force: true });

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

test("reconcileChannels: a session the host refuses to attach falls into ungrouped, not vanishes", async () => {
  const root = await makeRoot();
  const home = await mkdtemp(join(tmpdir(), "face-home6-"));
  const { registry, attaches } = fakeRegistry({ rejectSessionIds: ["session-bad"] });
  const sessions = [{ sessionId: "session-bad", cwd: join(root, "strategies", "alpha") }];

  const out = await reconcileChannels({ registry, root, home, sessions, connectedBins: [] });
  assert.deepEqual(attaches, [], "the host's rejection is not forced through");
  assert.deepEqual(
    out.ungrouped.map((s) => s.sessionId),
    ["session-bad"],
    "a session the host refuses to attach is reported, never silently dropped (Rule 5)",
  );
});

test("reconcileChannels: a directory vanishing between readdir and create skips only that channel", async () => {
  const root = await makeRoot();
  const home = await mkdtemp(join(tmpdir(), "face-home7-"));
  const { registry: base } = fakeRegistry();
  const alphaDir = join(root, "strategies", "alpha");
  // Simulate the readdir→create race the defensive catch exists for: by the
  // time `create` runs for this one directory, it is already gone.
  const registry = {
    ...base,
    create: async (path: string, title?: string) => {
      if (path === alphaDir) await rm(alphaDir, { recursive: true, force: true });
      return base.create(path, title);
    },
  };

  const out = await reconcileChannels({ registry, root, home, sessions: [], connectedBins: [] });
  assert.deepEqual(
    out.channels.map((c) => c.name),
    ["workbench", "市场情绪"],
    "the vanished channel is skipped; the rest of the listing still renders",
  );
});

/* ---------- C1: the reconcile must see persisted history, not only live
 * sessions (main.ts's `listSessions` now feeds it `mergeSessionHeads`) ---------- */

test("mergeSessionHeads: a persisted-only session is kept, and a live entry wins over a stale persisted one", () => {
  const persisted = [
    { sessionId: "persisted-only", cwd: "/repo/strategies/alpha" },
    { sessionId: "both", cwd: "/stale/cwd" },
  ];
  const live = [{ sessionId: "both", cwd: "/fresh/cwd" }];
  assert.deepEqual(mergeSessionHeads(persisted, live), [
    { sessionId: "persisted-only", cwd: "/repo/strategies/alpha" },
    { sessionId: "both", cwd: "/fresh/cwd" },
  ], "the persisted-only session survives, and the live cwd wins for the shared id");
});

test("mergeSessionHeads: neither list is favoured for ORDER, only live wins on a shared id", () => {
  assert.deepEqual(mergeSessionHeads([], []), []);
  assert.deepEqual(
    mergeSessionHeads([{ sessionId: "a", cwd: "/x" }], []),
    [{ sessionId: "a", cwd: "/x" }],
    "persisted alone still surfaces",
  );
  assert.deepEqual(
    mergeSessionHeads([], [{ sessionId: "a", cwd: "/x" }]),
    [{ sessionId: "a", cwd: "/x" }],
    "live alone still surfaces",
  );
});

test("reconcileChannels attaches a session that ONLY the persisted listing reports - exactly what main.ts now feeds it", async () => {
  const root = await makeRoot();
  const home = await mkdtemp(join(tmpdir(), "face-home8-"));
  const { registry, attaches } = fakeRegistry();
  const alphaDir = join(root, "strategies", "alpha");
  // Mirrors main.ts's real wiring: sessionPersistence.list() (durable
  // history) merged with sessions.list() (live only) via mergeSessionHeads.
  // Nothing is live here - the session is on disk only, which is exactly
  // the C1 gap: feeding the reconcile from `sessions.list()` alone would
  // report zero sessions and never attach it.
  const persistedOnly = mergeSessionHeads(
    [{ sessionId: "session-from-disk", cwd: alphaDir }],
    [],
  );
  const out = await reconcileChannels({ registry, root, home, sessions: persistedOnly, connectedBins: [] });
  const alpha = out.channels.find((c) => c.name === "alpha")!;
  assert.deepEqual(attaches, [`${alpha.workspaceId}:session-from-disk`], "a persisted-only session is attached");
  assert.deepEqual(out.ungrouped, [], "it is not left ungrouped just because it was never live");
});

/* ---------- the routes (Task 7) ---------- */

function fakeRes(): { out: { status: number; body: string }; res: ServerResponse } {
  const out = { status: 0, body: "" };
  const res = {
    writeHead(status: number) { out.status = status; return res; },
    end(body?: string | Buffer) { out.body = String(body ?? ""); return res; },
  };
  return { out, res: res as unknown as ServerResponse };
}

function getReq(host?: string): IncomingMessage {
  return { headers: host === undefined ? {} : { host }, method: "GET" } as unknown as IncomingMessage;
}

function postReq(body: string, host = "127.0.0.1:3090"): IncomingMessage {
  const req = Readable.from([Buffer.from(body)]) as unknown as IncomingMessage;
  (req as { headers: unknown }).headers = { host, "content-type": "application/json" };
  (req as { method: string }).method = "POST";
  return req;
}

async function routesFor(root: string, home: string): Promise<Map<string, WebRoute>> {
  const { registry } = fakeRegistry();
  const routes: WebRoute[] = [];
  registerChannelRoutes({ register: (route) => routes.push(route) }, {
    registry, root, home,
    listSessions: async () => [],
    connectedBins: async () => ["codex"],
  });
  return new Map(routes.map((r) => [r.path, r]));
}

/** Read the listing and find one channel by name - several tests need an id. */
async function channelNamed(routes: Map<string, WebRoute>, name: string): Promise<{ workspaceId: string }> {
  const out = fakeRes();
  await routes.get("/data/channels.json")!.handler(getReq("127.0.0.1:3090"), out.res);
  const payload = JSON.parse(out.out.body) as { channels: { name: string; workspaceId: string }[] };
  return payload.channels.find((c) => c.name === name)!;
}

test("routes: exactly four paths, and every one refuses a forged Host FIRST", async () => {
  const routes = await routesFor(await makeRoot(), await mkdtemp(join(tmpdir(), "face-rt-")));
  assert.deepEqual([...routes.keys()].sort(), [
    "/data/channels", "/data/channels.json", "/data/channels/agents", "/data/channels/overview",
  ]);
  for (const [path, route] of routes) {
    const forged = fakeRes();
    await route.handler(postReq('{"name":"x"}', "evil.example.com"), forged.res);
    assert.equal(forged.out.status, 403, path);
    assert.equal(forged.out.body, '{"ok":false,"error":"forbidden"}', `${path} echoes nothing`);
  }
});

test("routes: the POSTs are POST-only and application/json-only", async () => {
  const routes = await routesFor(await makeRoot(), await mkdtemp(join(tmpdir(), "face-rt2-")));
  for (const path of ["/data/channels", "/data/channels/agents", "/data/channels/overview"]) {
    const wrongMethod = fakeRes();
    await routes.get(path)!.handler(getReq("127.0.0.1:3090"), wrongMethod.res);
    assert.equal(wrongMethod.out.status, 405, path);

    const req = postReq("{}");
    (req as unknown as { headers: Record<string, string> }).headers["content-type"] = "text/plain";
    const wrongType = fakeRes();
    await routes.get(path)!.handler(req, wrongType.res);
    assert.equal(wrongType.out.status, 415, path);
  }
});

test("routes: the listing carries channels, the ungrouped count, and the archive set", async () => {
  const routes = await routesFor(await makeRoot(), await mkdtemp(join(tmpdir(), "face-rt3-")));
  const ok = fakeRes();
  await routes.get("/data/channels.json")!.handler(getReq("127.0.0.1:3090"), ok.res);
  assert.equal(ok.out.status, 200);
  const payload = JSON.parse(ok.out.body) as { ok: boolean; channels: { name: string }[]; ungrouped: unknown[]; archived: unknown[] };
  assert.equal(payload.ok, true);
  assert.deepEqual(payload.channels.map((c) => c.name), ["workbench", "alpha", "市场情绪"]);
  assert.deepEqual(payload.ungrouped, []);
  assert.deepEqual(payload.archived, []);
});

test("routes: overview answers by workspace id, and a body value never becomes a path", async () => {
  const routes = await routesFor(await makeRoot(), await mkdtemp(join(tmpdir(), "face-rt4-")));
  const alpha = await channelNamed(routes, "alpha");

  const good = fakeRes();
  await routes.get("/data/channels/overview")!.handler(postReq(JSON.stringify({ workspaceId: alpha.workspaceId })), good.res);
  assert.equal(good.out.status, 200);
  assert.equal((JSON.parse(good.out.body) as { status: { status?: string } }).status.status, "researching");

  for (const bad of [{ workspaceId: "ws-nope" }, { workspaceId: "../../etc/passwd" }, { workspaceId: 7 }, {}]) {
    const out = fakeRes();
    await routes.get("/data/channels/overview")!.handler(postReq(JSON.stringify(bad)), out.res);
    assert.equal(out.out.status, 404, JSON.stringify(bad));
  }
});

test("routes: the roster write replaces the set and refuses an unknown channel", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-rt5-"));
  const routes = await routesFor(await makeRoot(), home);
  const alpha = await channelNamed(routes, "alpha");

  const set = fakeRes();
  await routes.get("/data/channels/agents")!.handler(
    postReq(JSON.stringify({ workspaceId: alpha.workspaceId, agents: ["codex", "codex"] })), set.res);
  assert.equal(set.out.status, 200);
  assert.deepEqual(await rosterFor(home, alpha.workspaceId), ["codex"]);

  const unknown = fakeRes();
  await routes.get("/data/channels/agents")!.handler(postReq(JSON.stringify({ workspaceId: "ws-nope", agents: [] })), unknown.res);
  assert.equal(unknown.out.status, 404);

  const junk = fakeRes();
  await routes.get("/data/channels/agents")!.handler(
    postReq(JSON.stringify({ workspaceId: alpha.workspaceId, agents: "codex" })), junk.res);
  assert.equal(junk.out.status, 400);
});

test("routes: POST /data/channels creates once, then conflicts; bad JSON is a 400", async () => {
  const root = await makeRoot();
  const routes = await routesFor(root, await mkdtemp(join(tmpdir(), "face-rt6-")));
  const create = routes.get("/data/channels")!;

  const first = fakeRes();
  await create.handler(postReq('{"name":"gamma"}'), first.res);
  assert.equal(first.out.status, 200);
  await stat(join(root, "strategies", "gamma"));

  const again = fakeRes();
  await create.handler(postReq('{"name":"gamma"}'), again.res);
  assert.equal(again.out.status, 409);

  const junkBody = fakeRes();
  await create.handler(postReq("not json"), junkBody.res);
  assert.equal(junkBody.out.status, 400);
});

test("routes: POST /data/channels stays 200 even when the reconcile AFTER creation fails (I3)", async () => {
  const root = await makeRoot();
  const { registry } = fakeRegistry();
  const routes: WebRoute[] = [];
  registerChannelRoutes({ register: (route) => routes.push(route) }, {
    registry, root, home: await mkdtemp(join(tmpdir(), "face-rt7-")),
    listSessions: async () => [],
    // Fails BEFORE reconcileChannels/registry.create ever runs (reconcile()
    // awaits this first) - simulates the EACCES/lock-timeout/EIO class I3
    // is about, entirely decoupled from directory creation itself.
    connectedBins: async () => { throw new Error("EACCES: permission denied"); },
  });
  const create = new Map(routes.map((r) => [r.path, r])).get("/data/channels")!;

  const out = fakeRes();
  await create.handler(postReq('{"name":"delta"}'), out.res);
  assert.equal(out.out.status, 200, "the directory is already on disk; a reconcile failure must not be reported as create failed");
  assert.equal((JSON.parse(out.out.body) as { ok: boolean }).ok, true);
  await stat(join(root, "strategies", "delta")); // the channel really was created, not just claimed to be
});

/* The name-validation cases carry over from strategies.test.ts:36-72. The NUL
 * case is built with String.fromCharCode and the two normalizations with
 * escapes, so this file has no literal control characters. */

test("createChannel copies the template, skips __pycache__, never overwrites", async () => {
  const root = await makeRoot();
  const template = join(root, "strategies", "_template");
  await writeFile(join(template, "THESIS.md"), "# <strategy name>\n");
  await mkdir(join(template, "__pycache__"), { recursive: true });
  await writeFile(join(template, "__pycache__", "x.pyc"), "junk");

  const made = await createChannel(root, "beta-1");
  assert.equal(made.dir, join(root, "strategies", "beta-1"));
  await stat(join(made.dir, "backtests"));
  await assert.rejects(stat(join(made.dir, "__pycache__")));
  await assert.rejects(createChannel(root, "beta-1"), (err: HttpError) => err.status === 409);
  await assert.rejects(createChannel(root, "alpha"), (err: HttpError) => err.status === 409);
});

test("createChannel refuses names outside the closed class", async () => {
  const root = await makeRoot();
  const NUL = String.fromCharCode(0);
  for (const bad of [
    "", "_template", "a b", "市场 情绪", "../evil", "a/../b", "市场/情绪",
    "a.b", ".hidden", "-lead", "_lead", `a${NUL}b`, "x".repeat(42), 42, null,
  ]) {
    await assert.rejects(createChannel(root, bad), (err: HttpError) => err.status === 400, JSON.stringify(bad));
  }
});

test("createChannel takes a name in any script and creates it in NFC", async () => {
  const root = await makeRoot();
  const NFD = `cafe${String.fromCharCode(0x301)}`; // e + combining acute
  const NFC = `caf${String.fromCharCode(0xe9)}`;   // precomposed e-acute
  assert.equal((await createChannel(root, NFD)).name, NFC, "created in NFC");
  await assert.rejects(createChannel(root, NFC), (err: HttpError) => err.status === 409, "one word, two normalizations, one directory");
  assert.equal((await createChannel(root, "Upper-Case_9")).name, "Upper-Case_9", "case is the operator's to choose");
  assert.equal((await createChannel(root, "存储超级周期")).name, "存储超级周期", "a Chinese name is a name");
});
