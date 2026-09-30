/** The face's static UI mount: four routes on the host webserver, no framework.
 *
 * dsh-host-webserver "knows no harness concepts and serves no files" (its own
 * header) — the composing app owns dist serving. dsh-web-app does that through
 * the webserver's single `registerFallback` seat; the face deliberately does
 * NOT, and takes NAMED routes instead: `exact /` for the chat page, `exact
 * /market` and `exact /account` for the two instrument pages, and
 * `prefix /client` for their assets. The seat is left empty on purpose. It is a
 * one-owner seat that throws on a second claim, and everything it would catch
 * here is a 404 anyway; leaving it free keeps it available to a later row (a
 * frontend bundle, a dev proxy) without the face having to give it up first.
 *
 * `/` IS THE SIGN-IN, and it must stay behind {@link IndexAuth}. Since dsh
 * 0.2.0 every `/api` request and every `/api/remote.mux` upgrade passes
 * Connection's admission: the Host/Origin fence (403), then a signed,
 * authority-bound `dsh-auth-<hash>` browser cookie (401) (NEW
 * packages/client/connection/src/rpc-host.ts:104-123; packages/api/gateway/
 * src/index.ts:253-257; commits 3e24087bfa, 8ce7c27671). That cookie is minted
 * in exactly one place: `ctx.connection.authorizeIndex(req, res)` on
 * `GET /?token=<process launch token>`, which answers `303 ./` with
 * `Set-Cookie` (NEW packages/client/connection/src/browser-auth.ts:238-280).
 * A page served past it would load and then 401 on every call it makes.
 * `authorizeIndex` also OWNS the refusal: when it returns false it has already
 * written the 303 or the 401, so the handler must not touch the response.
 *
 * `/market`, `/account` and `/client/*` stay unauthenticated: the 0.1.1 posture
 * for everything that is not `/api` (PLAN D8 keeps `/data` fence-only too), and
 * upstream's own dist server keeps non-index assets public the same way (NEW
 * packages/host/frontend-static/src/index.ts:6-9, 88-90, 136). Their `/data`
 * reads do not need the cookie; their `/api` reads would, and the cookie is
 * `Path=/` for the whole authority once `/` minted it.
 * @module
 */
import { readFile } from "node:fs/promises";
import { join, normalize, extname, resolve, sep } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";

/** Extension → content-type, for the handful the face's own client ships.
 * Anything else is served as an opaque download rather than guessed at. */
const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

/** Content-type for a file path, by extension.
 * @param path - a file name or path; only its extension is read.
 * @returns the mapped type, or `application/octet-stream` when unmapped.
 */
export function contentTypeFor(path: string): string {
  return TYPES[extname(path)] ?? "application/octet-stream";
}

/**
 * Map a `/client/...` request target to an absolute path inside `clientDir`.
 *
 * The query and fragment are cut FIRST: `req.url` is a request-target, not a
 * path, so `/client/chat.css?v=2` would otherwise be resolved as a file whose
 * name ends in `?v=2` and 404 — a cache-busted asset silently failing to load.
 * The containment check is then made on the RESOLVED absolute path rather than
 * on the text of the request, so it holds for every spelling of a traversal
 * (`..`, doubled separators, an absolute-looking rest) instead of for the ones
 * a pattern happened to anticipate. Percent-encoding is deliberately NOT
 * decoded: `fs` does not decode either, so `%2e%2e` names a directory that does
 * not exist and 404s, and decoding would create the traversal it would then
 * have to re-check for.
 * @param urlPath - the raw request target, `req.url`.
 * @param clientDir - absolute, normalized, no trailing separator.
 * @returns the absolute file path, or `null` when it escapes `clientDir`.
 */
export function resolveClientPath(urlPath: string, clientDir: string): string | null {
  const path = urlPath.split(/[?#]/, 1)[0] ?? "";
  const rel = normalize(path.replace(/^\/client\/?/, "")).replace(/^([/\\])+/, "");
  const abs = resolve(clientDir, rel);
  return abs === clientDir || abs.startsWith(clientDir + sep) ? abs : null;
}

/** Send a file, or 404 when it cannot be read. Every read failure is one 404:
 * a missing file and an unreadable one are the same answer to the browser, and
 * the face has no client-visible error channel to distinguish them in. */
async function serveFile(res: ServerResponse, path: string): Promise<void> {
  try {
    const body = await readFile(path);
    res.writeHead(200, { "content-type": contentTypeFor(path) });
    res.end(body);
  } catch {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("not found");
  }
}

/** What {@link registerStatic} needs of a webserver. Structural so a test can
 * pass a recorder, but typed against the plugin's OWN exported {@link WebRoute}
 * — the same reason overlay.ts `satisfies`-checks its rows against the plugins'
 * config types: a route shape that drifted in an rc bump must fail tsc here
 * rather than register a silently dead handler. The disposer is returned as
 * `unknown` because the face never unregisters: these routes live as long as
 * the tree does. */
export interface RouteRegistrar {
  register(route: WebRoute): unknown;
}

/** The index gate: `ctx.connection` in the booted face, a fake in the tests.
 * The subset of Connection's `HostConnectionHandle.authorizeIndex` (installed
 * `@deepseek-ai/dsh-client-connection/lib/types/rpc.d.ts:176-182`) the `/`
 * route calls: `true` means "serve index.html"; `false` means it has already
 * answered — `303 ./` with `Set-Cookie` for a valid `?token=`, a bare `303` for
 * a signed-in token revisit, or `401` for everything else. */
export interface IndexAuth {
  authorizeIndex(req: IncomingMessage, res: ServerResponse): boolean;
}

/** The pages, as (route path → file name, behind the sign-in?). Each is an
 * EXACT route: a page is one address, not a subtree, and nothing under it is
 * served by accident. The instrument pages are plain documents against the
 * `/data/*.json` routes — no server-side rendering, so a page is a file like
 * the chat's. Only `/` is gated, because only `/` can mint the cookie. */
const PAGES: ReadonlyArray<readonly [path: string, file: string, gated: boolean]> = [
  ["/", "index.html", true],
  ["/market", "market.html", false],
  ["/account", "account.html", false],
];

/**
 * Mount the face's client: one `exact` route per page in {@link PAGES}, and
 * `prefix /client` → files under `clientDir`, traversal-refused.
 * @param webServer - the host webserver service (`ctx.webServer`).
 * @param clientDir - absolute path of the directory holding the page files.
 * @param auth - the index gate for `/` (`ctx.connection`). Required, not
 * optional: a `/` served without it hands the browser a page whose every
 * `/api` call 401s, and nothing on the server side would say so.
 * @throws when any (kind, path) is already registered — a duplicate route
 * is a composition error the webserver refuses on purpose.
 */
export function registerStatic(webServer: RouteRegistrar, clientDir: string, auth: IndexAuth): void {
  for (const [path, file, gated] of PAGES) {
    const page = join(clientDir, file);
    webServer.register({
      kind: "exact",
      path,
      handler: gated
        ? (req: IncomingMessage, res: ServerResponse) => (auth.authorizeIndex(req, res) ? serveFile(res, page) : undefined)
        : (_req: IncomingMessage, res: ServerResponse) => serveFile(res, page),
    });
  }
  webServer.register({
    kind: "prefix",
    path: "/client",
    handler: (req: IncomingMessage, res: ServerResponse) => {
      const target = resolveClientPath(req.url ?? "", clientDir);
      if (target === null) {
        res.writeHead(403);
        res.end();
        return;
      }
      return serveFile(res, target);
    },
  });
}
