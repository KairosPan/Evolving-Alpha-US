// face/tests/remote.ts
/** The smokes' client for dsh 0.2's HTTP Remote wire — shared by every
 * `*-smoke.test.ts` that talks to a booted face over its socket. Not a test
 * file itself (no `.test.ts`), so `npm test` never runs it.
 *
 * Two facts every caller relies on:
 * - `/api` needs a browser session now. Connection admits a request only past
 *   the Host/Origin fence (403) AND a signed, authority-bound `dsh-auth-*`
 *   cookie (401) (NEW packages/client/connection/src/rpc-host.ts:104-123), and
 *   the cookie is minted only by `GET /?token=<launch token>` through
 *   `authorizeIndex` → `303 ./` + `Set-Cookie` (browser-auth.ts:238-280). So
 *   {@link signIn} needs the face's `/` route mounted ({@link mountClient}, or
 *   `registerStatic` directly) — a tree without it answers the token URL with
 *   the webserver's bare 404.
 * - One unary call is `POST /api/<ns>/<method>` with the envelope
 *   `{type:'client-request', rpcId, method, payload:{args}}`, where `method`
 *   must equal the path endpoint and `payload` must be exactly `{args}` (NEW
 *   packages/client/connection/src/rpc-schema.ts:35-40, rpc-host.ts:229-268;
 *   packages/api/gateway/src/index.ts:1127-1147). The answer is
 *   `{type:'server-response', rpcId, result:{ok:true, value?}|{ok:false,
 *   error:{code, message, details}}}`; `value` is absent for a `void` method.
 *   Send every parameter (`_request:{}`, `request:{…}`): an unknown top-level
 *   key fails `gateway/arguments-invalid`, a missing strict one too (PLAN
 *   Appendix A).
 *
 * The usage model is upstream's own bare-fetch e2e client (NEW
 * apps/cli/tests/github-webhook-real.e2e.ts:30-43, 131-153).
 * @module
 */
import { randomUUID } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { registerStatic, type IndexAuth, type RouteRegistrar } from "../src/static.ts";

/** The face's real client directory, resolved from this module (face/tests → face/client). */
const CLIENT_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "client");

/**
 * Mount the face's pages on a booted tree, as `main.ts` does — `/` behind
 * `ctx.connection.authorizeIndex`. `bootFace` mounts no page itself, and
 * {@link signIn} needs `/`: without it the token URL gets the webserver's bare
 * 404. Call it once per tree (the webserver refuses a duplicate route); a smoke
 * that calls `registerStatic` itself must not call this too.
 * @param ctx - the booted root context.
 */
export function mountClient(ctx: { get(name: string): unknown; webServer: RouteRegistrar }): void {
  registerStatic(ctx.webServer, CLIENT_DIR, ctx.get("connection") as IndexAuth);
}

/** One Remote call's `result`: the business outcome, as the gateway answered it. */
export type RemoteResult =
  | { ok: true; value?: unknown }
  | { ok: false; error: { code: string; message: string; details?: unknown } };

/**
 * Exchange this process's launch token for the browser-session cookie, the way
 * the operator's browser does on the printed URL.
 * @param ctx - the booted root context (its `connection` service mints the URL).
 * @param base - the face's origin, e.g. `http://127.0.0.1:3090` (no trailing slash).
 * @returns the `name=value` pair to send as a `cookie` header on every later request.
 * @throws unless the exchange answered `303` with a `Set-Cookie`.
 */
export async function signIn(ctx: { get(name: string): unknown }, base: string): Promise<string> {
  const url = (ctx.get("connection") as { authenticatedUrl(b: string): string }).authenticatedUrl(`${base}/`);
  /* `manual`: the 303 IS the answer; following it would trade the Set-Cookie
   * for the page. */
  const res = await fetch(url, { redirect: "manual" });
  const setCookie = res.headers.get("set-cookie");
  if (res.status !== 303 || setCookie === null) throw new Error(`sign-in returned HTTP ${res.status}`);
  return setCookie.split(";", 1)[0]!;
}

/**
 * Call one Remote method and hand back its business `result` unopened — for a
 * test that asserts a refusal (`ok:false`, its `code`).
 * @param base - the face's origin.
 * @param cookie - from {@link signIn}.
 * @param endpoint - `<namespace>/<method>`, e.g. `session/list`.
 * @param args - the method's named wire arguments.
 * @returns the envelope's `result`.
 * @throws on a carrier failure (401/403/404/415/…): those are not business outcomes.
 */
export async function remoteResult(base: string, cookie: string, endpoint: string, args: object): Promise<RemoteResult> {
  const res = await fetch(`${base}/api/${endpoint}`, {
    method: "POST",
    headers: { "content-type": "application/json", cookie },
    body: JSON.stringify({ type: "client-request", rpcId: `t-${randomUUID()}`, method: endpoint, payload: { args } }),
  });
  if (!res.ok) throw new Error(`${endpoint}: HTTP ${res.status} ${await res.text()}`);
  const envelope = (await res.json()) as { result?: RemoteResult };
  /* A 200 without a `result` is not a gateway answer at all: say what came back
   * instead of failing later on `undefined.ok`. */
  if (envelope.result === undefined) throw new Error(`${endpoint}: no result in ${JSON.stringify(envelope)}`);
  return envelope.result;
}

/**
 * Call one Remote method and return its value, throwing on a business failure.
 * @returns `result.value` (absent → `undefined`, for a `void` method).
 * @throws `"<endpoint>: <code>: <message>"` when the method refused.
 */
export async function remote<T>(base: string, cookie: string, endpoint: string, args: object): Promise<T> {
  const r = await remoteResult(base, cookie, endpoint, args);
  if (!r.ok) throw new Error(`${endpoint}: ${r.error.code}: ${r.error.message}`);
  return r.value as T;
}
