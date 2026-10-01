import test from "node:test";
import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { contentTypeFor, registerStatic, resolveClientPath, type IndexAuth } from "../src/static.ts";

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

/** The index gate every fixture mounts unless a test hands it another: it
 * lets the page through, like `ctx.connection.authorizeIndex` on a request
 * that carries a valid cookie. */
const ALWAYS_SIGNED_IN: IndexAuth = { authorizeIndex: () => true };

/** A client dir with the three pages and one asset, plus a secret OUTSIDE it. */
function fixture(auth: IndexAuth = ALWAYS_SIGNED_IN): { clientDir: string; routes: WebRoute[] } {
  const root = mkdtempSync(join(tmpdir(), "face-client-"));
  const clientDir = join(root, "client");
  writeFileSync(join(root, "secret.txt"), "do not serve me");
  mkdirSync(clientDir);
  writeFileSync(join(clientDir, "index.html"), "<p>page</p>");
  writeFileSync(join(clientDir, "market.html"), "<p>market</p>");
  writeFileSync(join(clientDir, "account.html"), "<p>account</p>");
  writeFileSync(join(clientDir, "chat.css"), "body{}");
  const routes: WebRoute[] = [];
  registerStatic({ register: (route) => routes.push(route) }, clientDir, auth);
  return { clientDir, routes };
}

/** Call the route registered for (kind, path) with a bare request target. */
async function call(routes: WebRoute[], kind: WebRoute["kind"], path: string, url: string): Promise<Recorded> {
  const route = routes.find((r) => r.kind === kind && r.path === path);
  assert.ok(route !== undefined, `no ${kind} route at ${path}`);
  const { rec, res } = recorder();
  await route.handler({ url, method: "GET", headers: {} } as IncomingMessage, res);
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

/* `/` is the sign-in (dsh 0.2 browser-session auth): the cookie every `/api`
 * call and the `/api/remote.mux` upgrade now demand is minted ONLY by
 * `ctx.connection.authorizeIndex` on `GET /?token=…` (NEW
 * packages/client/connection/src/browser-auth.ts:238-280). A `/` that served
 * the page without asking would load a chat whose every call 401s - with the
 * whole offline suite green, which is why the gate is drilled here too. The
 * gate OWNS its refusal: it has already written the 303 or 401, so the route
 * must write nothing after it. */
test("/ asks the index gate first and serves index.html only when it says yes", async () => {
  const seen: { url?: string; res?: unknown }[] = [];
  const refusing: IndexAuth = {
    authorizeIndex(req, res) {
      seen.push({ url: req.url, res });
      res.writeHead(401, { "content-type": "text/plain; charset=utf-8" });
      res.end("dsh web authentication required");
      return false;
    },
  };
  const { routes } = fixture(refusing);
  const refused = await call(routes, "exact", "/", "/");
  assert.equal(refused.status, 401, "the gate's own answer must reach the browser untouched");
  assert.equal(refused.body, "dsh web authentication required", "index.html must not be written after a refusal");
  assert.equal(seen.length, 1, "the gate runs once per request");
  assert.equal(seen[0]!.url, "/", "the gate sees the raw request target (it reads ?token= off it)");

  const admitted = await call(fixture({ authorizeIndex: () => true }).routes, "exact", "/", "/");
  assert.equal(admitted.status, 200);
  assert.equal(String(admitted.body), "<p>page</p>");
});

/* The token exchange answers `303 ./` + Set-Cookie and returns false; the page
 * itself is served on the browser's follow-up request, not on this one. */
test("/ writes nothing of its own when the gate answers the token exchange", async () => {
  const minting: IndexAuth = {
    authorizeIndex(_req, res) {
      res.writeHead(303, { location: "./", "set-cookie": "dsh-auth-x=v1.a.b; Path=/; HttpOnly; SameSite=Strict" });
      res.end();
      return false;
    },
  };
  const rec = await call(fixture(minting).routes, "exact", "/", "/?token=abc");
  assert.equal(rec.status, 303);
  assert.equal(rec.headers.location, "./");
  assert.equal(rec.body, undefined);
});

/* D8: only `/` is gated, because only `/` can mint the cookie. The instrument
 * pages and the assets stay open, as every non-`/api` route was at 0.1.1 and
 * as upstream's own dist server keeps non-index assets. A gate that throws
 * proves none of them even asks. */
test("the instrument pages and /client assets never consult the index gate", async () => {
  const tripwire: IndexAuth = {
    authorizeIndex() { throw new Error("only / may consult the index gate"); },
  };
  const { routes } = fixture(tripwire);
  for (const path of ["/market", "/account"]) {
    assert.equal((await call(routes, "exact", path, path)).status, 200, path);
  }
  assert.equal((await call(routes, "prefix", "/client", "/client/chat.css")).status, 200);
});
