import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, stat, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import { promisify } from "node:util";
import { randomBytes } from "node:crypto";
import { zstdCompress, zstdCompressSync } from "node:zlib";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { deleteSession, pickGenerationLog, readMeta, registerSessionRoutes, setArchived } from "../src/sessions.ts";

const zstdCompressAsync = promisify(zstdCompress);

const SID = "session-0580173a-3484-4eff-a28a-280f82c9999e";
const OTHER = "session-100a30ce-5b8c-467e-a85a-afc7ff626c82";

/** Encode a session header the way dsh really stores it: the header JSON
 * line as one independently compressed Zstandard frame. Real artifacts are
 * `.jsonl.zstd` by default, and deleteSession now has to read a session's own
 * `cwd` back out of this file to decide whether it may touch it - a fixture
 * that wrote arbitrary placeholder bytes (this file's previous fixture, before
 * that guard existed) would make every delete look unreadable and get refused. */
function headerZstd(id: string, cwd: string): Buffer {
  const line = JSON.stringify({ type: "session", version: 0, id, createdAt: Date.now(), cwd, delegationDepth: 0 });
  return zstdCompressSync(`${line}\n`);
}

/** A throwaway harness home with one project slug holding one session whose
 * header claims `cwd` (default: a path no test's `root` ever equals — fine
 * for the tests below that never invoke deleteSession's repo check). */
async function makeHome(cwd = "/unused-in-this-test"): Promise<string> {
  const home = await mkdtemp(join(tmpdir(), "face-sessions-"));
  const dir = join(home, "sessions", "--proj--", SID);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, "session.jsonl.zstd"), headerZstd(SID, cwd));
  return home;
}

/** Encode a session log the way dsh 0.2.0-rc.2 writes a v4 generation: the
 * header line as its OWN Zstandard frame, then the events as a separate frame
 * (NEW `packages/session/session-persistence-jsonl/src/index.ts:1290-1297`,
 * `encodeMaterialization`; migrated logs do the same, `generation.ts:746-748`).
 * The v4 header carries the now-required `isSeeded` (`format.ts:83-98`). The
 * event frame is well over 64 KiB of incompressible text, so the face's
 * bounded prefix read truncates it mid-frame - the header must still decode. */
async function v4Log(id: string, cwd: string): Promise<Buffer> {
  const header = JSON.stringify({
    type: "session", version: 4, id, createdAt: 1756511990000, cwd, isSeeded: false, delegationDepth: 0,
  });
  const headerFrame = await zstdCompressAsync(Buffer.from(`${header}\n`));
  const events = Array.from({ length: 1500 }, (_, i) =>
    JSON.stringify({ seq: i, type: "user/message", data: { text: randomBytes(64).toString("hex") } })).join("\n");
  const eventFrame = await zstdCompressAsync(Buffer.from(`${events}\n`));
  assert.ok(eventFrame.length > 65536, "fixture must overflow the 64 KiB probe to exercise the bounded decode");
  return Buffer.concat([headerFrame, eventFrame]);
}

test("pickGenerationLog: highest canonical version wins; .zstd wins a tie; locks and temps never count", () => {
  assert.equal(pickGenerationLog([]), undefined);
  assert.equal(pickGenerationLog(["session.lock", "session.migration.0123456789abcdef.jsonl.zstd.tmp"]), undefined);
  assert.deepEqual(pickGenerationLog(["session.jsonl.zstd"]), { name: "session.jsonl.zstd", version: 0, zstd: true });
  assert.deepEqual(pickGenerationLog(["session.jsonl"]), { name: "session.jsonl", version: 0, zstd: false });
  /* a migrated 0.1.1 session: v0 byte-preserved, v4 published beside it */
  assert.equal(pickGenerationLog(["session.jsonl.zstd", "session.lock", "session.v4.jsonl.zstd"])?.name,
    "session.v4.jsonl.zstd");
  /* numeric, not lexicographic: v10 beats v4 and v9 */
  assert.equal(pickGenerationLog(["session.v4.jsonl.zstd", "session.v10.jsonl.zstd", "session.v9.jsonl.zstd"])?.version, 10);
  assert.equal(pickGenerationLog(["session.v4.jsonl", "session.v4.jsonl.zstd"])?.name, "session.v4.jsonl.zstd");
  assert.equal(pickGenerationLog(["session.v4.jsonl.zstd", "session.v4.jsonl"])?.name, "session.v4.jsonl.zstd");
  /* non-canonical names (NEW session-format/src/filename.ts:19-24): .v0, leading zero, uppercase, staging temps */
  for (const junk of [
    "session.v0.jsonl.zstd", "session.v04.jsonl.zstd", "SESSION.jsonl.zstd", "session.v4.jsonl.zstd.tmp",
    "session.v4.jsonl.zstd.0123456789ab.tmp", "session.v4.jsonl.gz", "session.v.jsonl",
  ]) {
    assert.equal(pickGenerationLog([junk]), undefined, junk);
  }
});

test("deleteSession reads a v4-only session (born under dsh 0.2.0) and deletes it", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-v4-"));
  const repo = await mkdtemp(join(tmpdir(), "face-repo-v4-"));
  const id = "session-44444444-4444-4444-4444-444444444444";
  const dir = join(home, "sessions", "--mine--", id);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, "session.v4.jsonl.zstd"), await v4Log(id, join(repo, "strategies", "alpha")));
  await writeFile(join(dir, "session.lock"), ""); // the flock lease file, never removed by the host (lease.ts:1-40)

  const meta = await deleteSession(home, repo, id);
  assert.deepEqual(meta.deleted, [id]);
  await assert.rejects(stat(dir)); // every generation, the lock and any temp go with the directory
});

test("deleteSession refuses a v4-only session whose header cwd is outside this repo", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-v4x-"));
  const repo = await mkdtemp(join(tmpdir(), "face-repo-v4x-"));
  const id = "session-45454545-4545-4545-4545-454545454545";
  const dir = join(home, "sessions", "--Users-pan-Desktop-trend-dragon--", id);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, "session.v4.jsonl.zstd"), await v4Log(id, "/Users/pan/Desktop/trend-dragon"));

  await assert.rejects(deleteSession(home, repo, id), (err: { status?: number }) => err.status === 404);
  await stat(dir); // untouched
});

test("a migrated session (v0 + v4 side by side): the v4 header decides, not the v0 one", async () => {
  const repo = await mkdtemp(join(tmpdir(), "face-repo-mig-"));
  const inside = join(repo, "strategies", "alpha");

  /* v0 says outside, v4 says inside: the delete is authorized by v4 */
  const home1 = await mkdtemp(join(tmpdir(), "face-mig1-"));
  const id1 = "session-46464646-4646-4646-4646-464646464646";
  const dir1 = join(home1, "sessions", "--mine--", id1);
  await mkdir(dir1, { recursive: true });
  await writeFile(join(dir1, "session.jsonl.zstd"), headerZstd(id1, "/somewhere/else"));
  await writeFile(join(dir1, "session.v4.jsonl.zstd"), await v4Log(id1, inside));
  await writeFile(join(dir1, "session.migration.0123456789abcdef.jsonl.zstd.tmp"), "not a log");
  await deleteSession(home1, repo, id1);
  await assert.rejects(stat(dir1));

  /* v0 says inside, v4 says outside: refused - an older generation never authorizes */
  const home2 = await mkdtemp(join(tmpdir(), "face-mig2-"));
  const id2 = "session-47474747-4747-4747-4747-474747474747";
  const dir2 = join(home2, "sessions", "--mine--", id2);
  await mkdir(dir2, { recursive: true });
  await writeFile(join(dir2, "session.jsonl.zstd"), headerZstd(id2, inside));
  await writeFile(join(dir2, "session.v4.jsonl.zstd"), await v4Log(id2, "/somewhere/else"));
  await assert.rejects(deleteSession(home2, repo, id2), (err: { status?: number }) => err.status === 404);
  await stat(dir2);
});

test("a session directory holding only a lock and temps is unknown, never deletable", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-lockonly-"));
  const repo = await mkdtemp(join(tmpdir(), "face-repo-lockonly-"));
  const id = "session-48484848-4848-4848-4848-484848484848";
  const dir = join(home, "sessions", "--mine--", id);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, "session.lock"), "");
  await writeFile(join(dir, "session.v4.jsonl.zstd.0123456789ab.tmp"), await v4Log(id, repo));
  await assert.rejects(deleteSession(home, repo, id), (err: { status?: number }) => err.status === 404);
  await stat(dir);
});

test("archive set: toggles, sorts, survives a re-read, drops junk", async () => {
  const home = await makeHome();
  assert.deepEqual(await readMeta(home), { archived: [], deleted: [] });
  await setArchived(home, SID, true);
  await setArchived(home, OTHER, true);
  assert.deepEqual((await readMeta(home)).archived, [SID, OTHER].sort());
  await setArchived(home, OTHER, false);
  assert.deepEqual((await readMeta(home)).archived, [SID]);
  /* hand-edited junk must not poison the set; a legacy bare array still reads */
  await writeFile(join(home, "face", "archived.json"), JSON.stringify([SID, "../evil", 42]));
  assert.deepEqual(await readMeta(home), { archived: [SID], deleted: [] });
});

test("un-archiving a host-archived session is refused, with the reason shown", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-unarch-"));
  const id = "session-d1a8a9ff-c0ad-432c-90a8-a81ba79352a9";
  await setArchived(home, id, true);
  await assert.rejects(
    setArchived(home, id, false, [id]), // the host's archive set
    /* PLAN D14: the face keeps refusing even though dsh 0.2.0's host CAN
     * un-archive; the reason names both halves - who archived it, and that a
     * host archive blocks model steps (ArchivedSessionGate). */
    (err: { status?: number; message?: string }) =>
      err.status === 409 && /archived by the host/i.test(err.message ?? "") && /no model step/i.test(err.message ?? ""),
  );
  assert.ok((await readMeta(home)).archived.includes(id), "it stays archived");
});

test("un-archiving an id the host never archived still works", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-unarch2-"));
  await setArchived(home, SID, true);
  const meta = await setArchived(home, SID, false, [OTHER]); // host archived a different session
  assert.deepEqual(meta.archived, []);
});

test("deleteSession removes the directory and its archive entry; absent is 404", async () => {
  const root = await mkdtemp(join(tmpdir(), "face-repo-"));
  const home = await makeHome(root); // header cwd === root: inside by the exact-match branch
  await setArchived(home, SID, true);
  const meta = await deleteSession(home, root, SID);
  await assert.rejects(stat(join(home, "sessions", "--proj--", SID)));
  assert.deepEqual(meta, { archived: [], deleted: [SID] }); // tombstoned, un-archived
  await assert.rejects(deleteSession(home, root, SID), (err: { status?: number }) => err.status === 404);
  await assert.rejects(deleteSession(home, root, "session-zzz"), (err: { status?: number }) => err.status === 400);
  await assert.rejects(deleteSession(home, root, "../../etc"), (err: { status?: number }) => err.status === 400);
});

test("deleteSession refuses a session whose cwd is outside this repo", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-del-"));
  const repo = await mkdtemp(join(tmpdir(), "face-repo-"));
  const id = "session-11111111-1111-1111-1111-111111111111";
  const foreign = join(home, "sessions", "--Users-pan-Desktop-trend-dragon--", id);
  await mkdir(foreign, { recursive: true });
  await writeFile(join(foreign, "session.jsonl.zstd"), headerZstd(id, "/Users/pan/Desktop/trend-dragon"));

  await assert.rejects(
    deleteSession(home, repo, id),
    (err: { status?: number }) => err.status === 404,
  );
  await stat(foreign); // still there - proves the guard refused, not that the id merely mismatched
});

test("deleteSession still deletes a session inside this repo", async () => {
  const home = await mkdtemp(join(tmpdir(), "face-del2-"));
  const repo = await mkdtemp(join(tmpdir(), "face-repo2-"));
  const id = "session-22222222-2222-2222-2222-222222222222";
  const mine = join(home, "sessions", "--mine--", id);
  await mkdir(mine, { recursive: true });
  await writeFile(join(mine, "session.jsonl.zstd"), headerZstd(id, join(repo, "strategies", "alpha")));

  await deleteSession(home, repo, id);
  await assert.rejects(stat(mine));
});

/* ---------- the routes ---------- */

function fakeRes(): { out: { status: number; body: string }; res: ServerResponse } {
  const out = { status: 0, body: "" };
  const res = {
    writeHead(status: number) { out.status = status; return res; },
    end(body?: string | Buffer) { out.body = String(body ?? ""); return res; },
  };
  return { out, res: res as unknown as ServerResponse };
}

function postReq(body: string, host = "127.0.0.1:3090"): IncomingMessage {
  const req = Readable.from([Buffer.from(body)]) as unknown as IncomingMessage;
  (req as { headers: unknown }).headers = { host, "content-type": "application/json" };
  (req as { method: string }).method = "POST";
  return req;
}

test("routes: meta lists, archive toggles, delete deletes, fence holds", async () => {
  const root = await mkdtemp(join(tmpdir(), "face-repo-"));
  const home = await makeHome(root);
  const routes: WebRoute[] = [];
  registerSessionRoutes({ register: (route) => routes.push(route) }, { root, home });
  const byPath = new Map(routes.map((r) => [r.path, r]));
  assert.deepEqual([...byPath.keys()].sort(),
    ["/data/sessions-meta.json", "/data/sessions/archive", "/data/sessions/delete"]);

  const archive = byPath.get("/data/sessions/archive")!;
  const on = fakeRes();
  await archive.handler(postReq(JSON.stringify({ sessionId: SID, archived: true })), on.res);
  assert.equal(on.out.status, 200);
  assert.deepEqual((JSON.parse(on.out.body) as { archived: string[] }).archived, [SID]);

  const meta = byPath.get("/data/sessions-meta.json")!;
  const read = fakeRes();
  await meta.handler({ headers: { host: "127.0.0.1:3090" }, method: "GET" } as unknown as IncomingMessage, read.res);
  assert.deepEqual((JSON.parse(read.out.body) as { archived: string[] }).archived, [SID]);

  const del = byPath.get("/data/sessions/delete")!;
  const forged = fakeRes();
  await del.handler(postReq(JSON.stringify({ sessionId: SID }), "evil.example.com"), forged.res);
  assert.equal(forged.out.status, 403);
  await stat(join(home, "sessions", "--proj--", SID)); // still there

  const gone = fakeRes();
  await del.handler(postReq(JSON.stringify({ sessionId: SID })), gone.res);
  assert.equal(gone.out.status, 200);
  await assert.rejects(stat(join(home, "sessions", "--proj--", SID)));

  const missing = fakeRes();
  await del.handler(postReq(JSON.stringify({ sessionId: SID })), missing.res);
  assert.equal(missing.out.status, 404);
});

test("routes: the archive route reads the host archive set live, off the deps object", async () => {
  const root = await mkdtemp(join(tmpdir(), "face-repo3-"));
  const home = await makeHome(root);
  const routes: WebRoute[] = [];
  /* A mutable stand-in for `ctx.workspaceRegistry`: the route must re-read
   * `archivedSessionIds` on every request, not snapshot it at registration -
   * the host set only grows while the face runs. */
  const hostArchive = { archivedSessionIds: [] as readonly string[] };
  registerSessionRoutes({ register: (route) => routes.push(route) }, { root, home, hostArchive });
  const archive = new Map(routes.map((r) => [r.path, r])).get("/data/sessions/archive")!;

  await archive.handler(postReq(JSON.stringify({ sessionId: SID, archived: true })), fakeRes().res);
  hostArchive.archivedSessionIds = [SID]; // the host archives it after registration, before this request

  const refused = fakeRes();
  await archive.handler(postReq(JSON.stringify({ sessionId: SID, archived: false })), refused.res);
  assert.equal(refused.out.status, 409);
  assert.match((JSON.parse(refused.out.body) as { error: string }).error, /host/i);
  assert.ok((await readMeta(home)).archived.includes(SID), "still archived - the refusal held");
});
