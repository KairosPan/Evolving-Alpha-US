/** `/data/market.json` + `/data/account.json`: cached, single-flight spawns of
 * `scripts/face_data.py`.
 *
 * The face holds no market state of its own. Each route is a thin cache in
 * front of ONE producer process whose argv is FIXED — the script path and a
 * mode word, nothing else. No request data ever reaches the child (spec v2
 * section 3.1), so these routes cannot be turned into a command-injection
 * surface by a crafted URL; the one header the handlers read is `Host`, and
 * they read it to REFUSE, not to build anything with. The child's stderr goes
 * to the face's stderr and never into a response body — not even inside an
 * error message (see the catch path).
 *
 * These routes sit behind the same DNS-rebinding fence the harness's `/api`
 * routes get from dsh-client-connection, restated here because that fence
 * covers `/api` only and `/data/account.json` carries the operator's positions
 * and orders.
 *
 * The spawner is injected so tests can drive the whole cache/single-flight/
 * stale machine without a Python process; {@link defaultSpawner} is the real
 * one.
 * @module
 */
import { execFile } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { RouteRegistrar } from "./static.ts";

/** Run the producer and report what it wrote and how it exited.
 *
 * `timeoutMs` is per CALL rather than per spawner because the two modes have
 * budgets an order of magnitude apart (see {@link SPAWN_TIMEOUT_MS}). A
 * REJECTION means the process could not be trusted to have produced a payload
 * at all (spawn failure, timeout kill); a nonzero `code` with a body is the
 * producer's own honest failure report.
 */
export type Spawner = (argv: string[], timeoutMs: number) => Promise<{ stdout: string; code: number }>;

/** How long a good payload is served without re-spawning, per mode. Market
 * data is a daily bed walk — 15 minutes of staleness is invisible; an account
 * carries positions the operator may have just changed, so it re-reads within
 * the minute. */
export const TTL_MS = { market: 900_000, account: 60_000 } as const;

/** How long one spawn may run before it is killed, per mode.
 *
 * Market gets TEN MINUTES because a COLD assembly measured ~284s: the producer
 * keeps its own disk cache under `data/.face_cache`, so every later run is
 * under a second, but the first run ever — and the first after any change that
 * invalidates that cache — pays the full bed walk. A 30s budget there would
 * make that first request fail, and keep failing, since a killed run never
 * writes the cache that would have made the next one fast.
 *
 * Account gets 30s: it is a couple of REST calls, but it still pays the market
 * stack's import cost (~1-3s of Python imports) on every spawn.
 */
export const SPAWN_TIMEOUT_MS = { market: 600_000, account: 30_000 } as const;

/* Resolved from this module, never from the working directory: main.ts anchors
 * the process at the repo root, but a producer path that DEPENDS on that would
 * break silently the day something else calls `chdir`. */
const moduleDir = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(moduleDir, "..", "..");
const SCRIPT = join(REPO_ROOT, "scripts", "face_data.py");

/** Body of a refused (non-loopback) request. Fixed text: the Host that was
 * refused is attacker-controlled and is never echoed back. */
const FORBIDDEN = '{"ok":false,"error":"forbidden"}';

/** Body of a producer failure that wrote nothing usable. */
const PRODUCER_FAILED = '{"ok":false,"error":"producer failed"}';

/**
 * Whether a `Host` header names this loopback face.
 *
 * The DNS-rebinding fence: a rebound page reaches this socket while its Host
 * header still names the attacker's domain, and Host is the one header that
 * rebinding cannot forge. Deliberately the SAME predicate dsh-client-connection
 * applies to `/api` (`isLoopbackHostname`, 0.1.1-rc.2 lib/index.js:100-104) —
 * `localhost`, `[::1]`, any `127.x.x.x` — so the face has one trust boundary
 * rather than two that can drift apart. Parsing is WHATWG's, which strips the
 * port, lowercases, and brackets IPv6 for us; anything unparsable, and a
 * MISSING Host, is refused (fail closed).
 * @param host - the raw `Host` header, or `undefined` when absent.
 * @returns true when the request may be served.
 */
export function isLoopbackHost(host: string | undefined): boolean {
  if (host === undefined) return false;
  /* An unbracketed `::1` is not legal on the wire and does not survive URL
   * parsing; accepted anyway rather than left as a spelling that fails closed
   * for a genuinely local caller. */
  if (host.trim() === "::1") return true;
  let hostname: string;
  try {
    hostname = new URL(`http://${host}`).hostname;
  } catch {
    return false;
  }
  if (hostname === "localhost" || hostname === "[::1]") return true;
  const parts = hostname.split(".");
  return parts.length === 4 && parts[0] === "127"
    && parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255);
}

/**
 * The real spawner: `execFile` (no shell) of `python`, cwd at the repo root.
 * @param python - the interpreter to run; an absolute path or a `PATH` name.
 * @returns a {@link Spawner} over the fixed producer script.
 */
export function defaultSpawner(python: string): Spawner {
  return (argv, timeoutMs) => new Promise((resolve, reject) => {
    execFile(
      python,
      argv,
      { cwd: REPO_ROOT, timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (stderr) process.stderr.write(`face-data: ${stderr}`);
        /* Reject on the two failures whose stdout cannot be trusted as a
         * payload: a spawn failure (ENOENT) leaves stdout EMPTY, and a timeout
         * KILL sets `killed` and may leave a truncated one. Both then answer
         * with the caller's own JSON rather than half a payload.
         *
         * The third truncation, a maxBuffer overflow, does NOT set `killed`
         * (measured: `code` is the string ERR_CHILD_PROCESS_STDIO_MAXBUFFER,
         * `killed` undefined), so it resolves with code 1 and the truncated
         * stdout - a nonzero-exit 503 that is never cached, whose body the
         * client cannot parse. That is the honest outcome for a payload past
         * the 32 MB ceiling, which is ~400x the measured market payload. */
        const killed = err !== null && (err as { killed?: boolean }).killed === true;
        if (err && (killed || stdout === "")) return reject(err);
        const code = err && typeof (err as { code?: unknown }).code === "number"
          ? (err as { code: number }).code
          : err ? 1 : 0;
        resolve({ stdout: String(stdout), code });
      },
    );
  });
}

/** The producer's two modes; the same keys carry the TTL and the timeout. */
type Mode = keyof typeof TTL_MS;

/** One cached payload and the clock reading it was stored at. */
interface Entry { body: string; at: number }

/**
 * Mount the data routes: `exact /data/market.json` and
 * `exact /data/account.json`.
 *
 * Every request is fenced to a loopback `Host` FIRST (see
 * {@link isLoopbackHost}): a foreign or missing Host is a fixed-body 403 that
 * reaches neither the cache nor a producer process.
 *
 * Past the fence each route is cached for its mode's {@link TTL_MS},
 * single-flighted (concurrent misses share one child), and stale-on-error:
 * once a good payload exists, a later failure serves it again with
 * `stale: true` rather than blanking the instrument. A failure with NO cache is
 * a 503 carrying the producer's own `{ok:false,error}` JSON when it wrote one,
 * and a fixed message when it did not. Only a run that exited 0 WITH output is
 * cached — the next request after any failure retries immediately.
 *
 * @param webServer - the host webserver service (`ctx.webServer`), or a test
 * recorder; the same {@link RouteRegistrar} contract static.ts registers under,
 * so a route shape that drifts in an rc bump fails tsc in one place.
 * @param opts - injection seams: `spawn` (default {@link defaultSpawner} over
 * `$FACE_PYTHON`), `now` (default `Date.now`), `python` (default
 * `$FACE_PYTHON`, else `python3`).
 * @throws when either path is already registered — a duplicate route is a
 * composition error the webserver refuses on purpose.
 */
export function registerDataRoutes(
  webServer: RouteRegistrar,
  opts: { spawn?: Spawner; now?: () => number; python?: string } = {},
): void {
  /* `||` on the env var, not `??` — the face's convention throughout (main.ts,
   * setup.ts): `FACE_PYTHON=""` is a var the operator meant to leave at its
   * default, and `??` would take it literally and try to execFile "". */
  const spawn = opts.spawn ?? defaultSpawner(opts.python || process.env.FACE_PYTHON || "python3");
  const now = opts.now ?? Date.now;
  const cache = new Map<Mode, Entry>();
  const inflight = new Map<Mode, Promise<{ stdout: string; code: number }>>();

  const send = (res: ServerResponse, status: number, body: string): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(body);
  };

  const handler = (mode: Mode) => async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
    /* FIRST, before the cache and before any spawn: a refused request must not
     * be able to start a producer process either. */
    if (!isLoopbackHost(req.headers.host)) return send(res, 403, FORBIDDEN);

    const hit = cache.get(mode);
    if (hit && now() - hit.at < TTL_MS[mode]) return send(res, 200, hit.body);

    let flight = inflight.get(mode);
    if (!flight) {
      flight = spawn([SCRIPT, mode], SPAWN_TIMEOUT_MS[mode]);
      inflight.set(mode, flight);
      /* `then(clear, clear)`, NOT `finally(clear)`: a `finally` on a rejecting
       * promise DERIVES a second rejected promise that nobody awaits, and
       * main.ts turns any unhandled rejection into a process shutdown — the
       * face would die the first time python3 was missing. The two-handler
       * `then` consumes the rejection here; the awaiting handlers below still
       * see it on `flight` itself. */
      const clear = (): void => void inflight.delete(mode);
      void flight.then(clear, clear);
    }

    try {
      const { stdout, code } = await flight;
      /* `stdout !== ""` guards the cache write as tightly as the exit code
       * does: a producer that exits 0 having written NOTHING is broken, and
       * caching that would serve an empty 200 body for a whole TTL — a blank
       * instrument the client cannot tell from a parse failure. */
      if (code === 0 && stdout !== "") {
        cache.set(mode, { body: stdout, at: now() });
        return send(res, 200, stdout);
      }
      /* The producer's honest error payload: served, never cached. */
      if (hit) return send(res, 200, markStale(hit.body));
      return send(res, 503, stdout || PRODUCER_FAILED);
    } catch (err) {
      if (hit) return send(res, 200, markStale(hit.body));
      /* FIXED text plus the error's code — never `String(err)` or
       * `err.message`. Node's execFile error message is
       * `Command failed: <cmd>\n<the child's whole stderr>` (measured), so
       * stringifying it would echo a producer traceback — APCA_* values and
       * all — straight into the browser. The code (`ENOENT`, an exit number)
       * is the diagnostic part and carries nothing from the child. */
      const raw = (err as { code?: unknown } | null)?.code;
      const code = typeof raw === "string" || typeof raw === "number" ? raw : null;
      return send(res, 503, JSON.stringify({ ok: false, error: "producer spawn failed", code }));
    }
  };

  webServer.register({ kind: "exact", path: "/data/market.json", handler: handler("market") });
  webServer.register({ kind: "exact", path: "/data/account.json", handler: handler("account") });
}

/** Re-serve a cached body flagged `stale: true`, so the client can say so.
 * An unparseable body is passed through unchanged rather than replaced by an
 * error: it was served as a good payload once, and the flag is the only thing
 * being added. */
function markStale(body: string): string {
  try {
    const parsed = JSON.parse(body) as Record<string, unknown>;
    parsed.stale = true;
    return JSON.stringify(parsed);
  } catch {
    return body;
  }
}
