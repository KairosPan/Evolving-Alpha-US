import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, stat, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { deleteSession, readMeta, registerSessionRoutes, setArchived } from "../src/sessions.ts";

const SID = "session-0580173a-3484-4eff-a28a-280f82c9999e";
const OTHER = "session-100a30ce-5b8c-467e-a85a-afc7ff626c82";

/** A throwaway harness home with one project slug holding one session. */
async function makeHome(): Promise<string> {
  const home = await mkdtemp(join(tmpdir(), "face-sessions-"));
  const dir = join(home, "sessions", "--proj--", SID);
  await mkdir(dir, { recursive: true });
  await writeFile(join(dir, "session.jsonl.zstd"), "log");
  return home;
}

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

test("deleteSession removes the directory and its archive entry; absent is 404", async () => {
  const home = await makeHome();
  await setArchived(home, SID, true);
  const meta = await deleteSession(home, SID);
  await assert.rejects(stat(join(home, "sessions", "--proj--", SID)));
  assert.deepEqual(meta, { archived: [], deleted: [SID] }); // tombstoned, un-archived
  await assert.rejects(deleteSession(home, SID), (err: { status?: number }) => err.status === 404);
  await assert.rejects(deleteSession(home, "session-zzz"), (err: { status?: number }) => err.status === 400);
  await assert.rejects(deleteSession(home, "../../etc"), (err: { status?: number }) => err.status === 400);
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
  const home = await makeHome();
  const routes: WebRoute[] = [];
  registerSessionRoutes({ register: (route) => routes.push(route) }, home);
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
