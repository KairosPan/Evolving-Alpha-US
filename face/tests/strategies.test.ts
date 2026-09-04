import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable } from "node:stream";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { createStrategy, listStrategies, registerStrategyRoutes } from "../src/strategies.ts";
import { HttpError } from "../src/http.ts";

/** A throwaway workbench root: strategies/{_template,alpha}, alpha with a
 * status.yaml, the template carrying a nested dir and a __pycache__ that must
 * never be copied. */
async function makeRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "face-strategies-"));
  const template = join(root, "strategies", "_template");
  await mkdir(join(template, "backtests"), { recursive: true });
  await mkdir(join(template, "__pycache__"), { recursive: true });
  await writeFile(join(template, "THESIS.md"), "# <strategy name>\n");
  await writeFile(join(template, "status.yaml"), "status: idea\n");
  await writeFile(join(template, "__pycache__", "x.pyc"), "junk");
  const alpha = join(root, "strategies", "alpha");
  await mkdir(alpha, { recursive: true });
  await writeFile(join(alpha, "status.yaml"), "status: researching  # comment\n");
  return root;
}

test("listStrategies lists real strategies with status, template excluded", async () => {
  const root = await makeRoot();
  const { strategies } = await listStrategies(root);
  assert.deepEqual(strategies.map((s) => s.name), ["alpha"]);
  assert.equal(strategies[0].status, "researching");
  assert.equal(strategies[0].cwd, join(root, "strategies", "alpha"));
});

test("createStrategy copies the template, skips __pycache__, never overwrites", async () => {
  const root = await makeRoot();
  const entry = await createStrategy(root, "beta-1");
  assert.equal(entry.cwd, join(root, "strategies", "beta-1"));
  assert.match(await readFile(join(entry.cwd, "THESIS.md"), "utf8"), /strategy name/);
  await stat(join(entry.cwd, "backtests"));
  await assert.rejects(stat(join(entry.cwd, "__pycache__")));
  await assert.rejects(createStrategy(root, "beta-1"), (err: HttpError) => err.status === 409);
  await assert.rejects(createStrategy(root, "alpha"), (err: HttpError) => err.status === 409);
});

test("createStrategy refuses names outside the closed class", async () => {
  const root = await makeRoot();
  // the class is letters/digits in any script plus - and _: one path segment, nothing else
  for (const bad of [
    "", "_template", "a b", "市场 情绪", "../evil", "a/../b", "市场/情绪", "a.b",
    ".hidden", "-lead", "_lead", "a\u0000b", "x".repeat(42), 42, null,
  ]) {
    await assert.rejects(createStrategy(root, bad), (err: HttpError) => err.status === 400, JSON.stringify(bad));
  }
});

test("createStrategy takes a name in any script, and creates it in NFC", async () => {
  const root = await makeRoot();
  const zh = "市场情绪";
  const made = await createStrategy(root, zh);
  assert.equal(made.name, zh);
  assert.ok((await stat(join(root, "strategies", zh))).isDirectory());
  /* one word, two normalizations -> one directory: NFD in, NFC on disk */
  const NFD = "cafe\u0301"; // e + combining acute
  const NFC = "caf\u00e9";
  const decomposed = await createStrategy(root, NFD);
  assert.equal(decomposed.name, NFC, "created in NFC");
  assert.ok((await stat(join(root, "strategies", NFC))).isDirectory());
  await assert.rejects(createStrategy(root, NFC), (err: HttpError) => err.status === 409, "the NFC spelling is the same strategy");
  assert.equal((await createStrategy(root, "Upper-Case_9")).name, "Upper-Case_9", "case is the operator's to choose");
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

function getReq(host?: string): IncomingMessage {
  return { headers: host === undefined ? {} : { host }, method: "GET" } as unknown as IncomingMessage;
}

/** A POST whose body streams like a real request's. */
function postReq(body: string, host = "127.0.0.1:3090"): IncomingMessage {
  const req = Readable.from([Buffer.from(body)]) as unknown as IncomingMessage;
  (req as { headers: unknown }).headers = { host, "content-type": "application/json" };
  (req as { method: string }).method = "POST";
  return req;
}

async function routesFor(root: string): Promise<Map<string, WebRoute>> {
  const routes: WebRoute[] = [];
  registerStrategyRoutes({ register: (route) => routes.push(route) }, root);
  return new Map(routes.map((r) => [r.path, r]));
}

test("routes: shapes, loopback fence, method gate", async () => {
  const root = await makeRoot();
  const routes = await routesFor(root);
  assert.deepEqual([...routes.keys()].sort(), ["/data/strategies", "/data/strategies.json"]);

  const list = routes.get("/data/strategies.json")!;
  const forged = fakeRes();
  await list.handler(getReq("evil.example.com"), forged.res);
  assert.equal(forged.out.status, 403);

  const ok = fakeRes();
  await list.handler(getReq("127.0.0.1:3090"), ok.res);
  assert.equal(ok.out.status, 200);
  const payload = JSON.parse(ok.out.body) as { ok: boolean; strategies: { name: string }[] };
  assert.equal(payload.ok, true);
  assert.deepEqual(payload.strategies.map((s) => s.name), ["alpha"]);

  const create = routes.get("/data/strategies")!;
  const wrongMethod = fakeRes();
  await create.handler(getReq("127.0.0.1:3090"), wrongMethod.res);
  assert.equal(wrongMethod.out.status, 405);
});

test("routes: POST creates once, then conflicts; bad JSON is a 400", async () => {
  const root = await makeRoot();
  const routes = await routesFor(root);
  const create = routes.get("/data/strategies")!;

  const first = fakeRes();
  await create.handler(postReq('{"name":"gamma"}'), first.res);
  assert.equal(first.out.status, 200);
  await stat(join(root, "strategies", "gamma", "THESIS.md"));

  const again = fakeRes();
  await create.handler(postReq('{"name":"gamma"}'), again.res);
  assert.equal(again.out.status, 409);

  const junk = fakeRes();
  await create.handler(postReq("not json"), junk.res);
  assert.equal(junk.out.status, 400);

  const forged = fakeRes();
  await create.handler(postReq('{"name":"delta"}', "evil.example.com"), forged.res);
  assert.equal(forged.out.status, 403);
  await assert.rejects(stat(join(root, "strategies", "delta")));
});
