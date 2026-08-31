import test from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { contentTypeFor, registerStatic, resolveClientPath } from "../src/static.ts";

test("content types", () => {
  assert.equal(contentTypeFor("index.html"), "text/html; charset=utf-8");
  assert.equal(contentTypeFor("chat.css"), "text/css; charset=utf-8");
  assert.equal(contentTypeFor("api.js"), "text/javascript; charset=utf-8");
  assert.equal(contentTypeFor("x.unknown"), "application/octet-stream");
});

test("resolveClientPath refuses traversal out of the client dir", () => {
  assert.equal(resolveClientPath("/client/../../etc/passwd", "/srv/client"), null);
  assert.equal(resolveClientPath("/client/chat.css", "/srv/client"), "/srv/client/chat.css");
});

/* `req.url` is a request-target, not a path. Without the cut, a cache-busted
 * asset resolves to a file whose NAME ends in `?v=2` and 404s - a stylesheet
 * that silently never loads, with a green test suite above it. The sibling-
 * prefix case is the containment check earning its `+ sep`: `/srv/client-old`
 * starts with the string `/srv/client`, but is not inside it. */
test("resolveClientPath cuts the query/fragment and holds the directory boundary", () => {
  assert.equal(resolveClientPath("/client/chat.css?v=2", "/srv/client"), "/srv/client/chat.css");
  assert.equal(resolveClientPath("/client/chat.css#top", "/srv/client"), "/srv/client/chat.css");
  assert.equal(resolveClientPath("/client/../client-old/secret", "/srv/client"), null);
  // A nested path is fine; only escaping the root is not.
  assert.equal(resolveClientPath("/client/a/b.js", "/srv/client"), "/srv/client/a/b.js");
});

/** Captured status/headers/body from one handler call. */
interface Recorded {
  status: number;
  headers: Record<string, string>;
  body?: Buffer | string;
}

/** The two methods {@link serveFile} uses, cast to the response it is given.
 * A structural stand-in, not a mock framework: the handler owns the full
 * response lifecycle, so what it wrote IS its whole observable behaviour. */
function recorder(): { rec: Recorded; res: ServerResponse } {
  const rec: Recorded = { status: 0, headers: {} };
  const res = {
    writeHead(status: number, headers?: Record<string, string>) {
      rec.status = status;
      if (headers !== undefined) rec.headers = headers;
      return res;
    },
    end(body?: Buffer | string) {
      rec.body = body;
      return res;
    },
  };
  return { rec, res: res as unknown as ServerResponse };
}

/** A client dir with the three pages and one asset, plus a secret OUTSIDE it. */
function fixture(): { clientDir: string; routes: WebRoute[] } {
  const root = mkdtempSync(join(tmpdir(), "face-client-"));
  const clientDir = join(root, "client");
  writeFileSync(join(root, "secret.txt"), "do not serve me");
  mkdirSync(clientDir);
  writeFileSync(join(clientDir, "index.html"), "<p>page</p>");
  writeFileSync(join(clientDir, "market.html"), "<p>market</p>");
  writeFileSync(join(clientDir, "account.html"), "<p>account</p>");
  writeFileSync(join(clientDir, "chat.css"), "body{}");
  const routes: WebRoute[] = [];
  registerStatic({ register: (route) => routes.push(route) }, clientDir);
  return { clientDir, routes };
}

/** Call the route registered for (kind, path) with a bare request target. */
async function call(routes: WebRoute[], kind: WebRoute["kind"], path: string, url: string): Promise<Recorded> {
  const route = routes.find((r) => r.kind === kind && r.path === path);
  assert.ok(route !== undefined, `no ${kind} route at ${path}`);
  const { rec, res } = recorder();
  await route.handler({ url } as IncomingMessage, res);
  return rec;
}

/* The route SHAPE is the contract with the host webserver: three named pages
 * and `prefix /client` for everything else the face owns. Asserting it here is
 * what catches a mount that registered, say, `prefix /` - which would
 * typecheck, boot, serve index.html for every asset request, and look fine
 * until the browser tried to parse HTML as CSS. */
test("registerStatic mounts exactly the routes it claims", () => {
  const { routes } = fixture();
  assert.deepEqual(
    routes.map((r) => `${r.kind} ${r.path}`).sort(),
    ["exact /", "exact /account", "exact /market", "prefix /client"],
  );
});

test("the / route serves index.html as html", async () => {
  const { routes } = fixture();
  const rec = await call(routes, "exact", "/", "/");
  assert.equal(rec.status, 200);
  assert.equal(rec.headers["content-type"], "text/html; charset=utf-8");
  assert.equal(String(rec.body), "<p>page</p>");
});

/* Each instrument route must serve its OWN page. A copy-paste that pointed
 * both at one file would satisfy a route-shape assertion and still show the
 * operator the market when they asked for the account. */
test("the instrument routes serve their own page file", async () => {
  const { routes } = fixture();
  for (const [path, body] of [["/market", "<p>market</p>"], ["/account", "<p>account</p>"]] as const) {
    const rec = await call(routes, "exact", path, path);
    assert.equal(rec.status, 200);
    assert.equal(rec.headers["content-type"], "text/html; charset=utf-8");
    assert.equal(String(rec.body), body);
  }
});

test("the /client route serves assets, 404s misses, and 403s traversal", async () => {
  const { routes } = fixture();

  const css = await call(routes, "prefix", "/client", "/client/chat.css");
  assert.equal(css.status, 200);
  assert.equal(css.headers["content-type"], "text/css; charset=utf-8");
  assert.equal(String(css.body), "body{}");

  const missing = await call(routes, "prefix", "/client", "/client/nope.js");
  assert.equal(missing.status, 404);

  /* The one that matters: the file EXISTS and is readable, so a 403 here can
   * only come from the containment check - a 404 would prove nothing. */
  const escaped = await call(routes, "prefix", "/client", "/client/../secret.txt");
  assert.equal(escaped.status, 403);
  assert.equal(escaped.body, undefined);
});
