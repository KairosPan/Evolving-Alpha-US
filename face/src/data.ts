/** `/data/market.json` + `/data/account.json`: cached, single-flight spawns of
 * `scripts/face_data.py`.
 *
 * The face holds no market state of its own. Each route is a thin cache in
 * front of ONE producer process whose argv is FIXED — the script path and a
 * mode word, nothing else. No request data ever reaches the child (spec v2
 * section 3.1), so these routes cannot be turned into a command-injection
 * surface by a crafted URL, and the handlers never read `req` at all. The
 * child's stderr goes to the face's stderr and never into a response body.
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
        /* Reject rather than report a code when there is no payload to report:
         * a spawn failure (ENOENT) has no stdout, and a timeout KILL may have
         * left a truncated one. Either way the caller must answer with its own
         * JSON, not with half a payload. */
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
 * Each is cached for its mode's {@link TTL_MS}, single-flighted (concurrent
 * misses share one child), and stale-on-error: once a good payload exists, a
 * later failure serves it again with `stale: true` rather than blanking the
 * instrument. A failure with NO cache is a 503 carrying the producer's own
 * `{ok:false,error}` JSON, and a failed run is never cached — the next request
 * retries immediately.
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
  const spawn = opts.spawn ?? defaultSpawner(opts.python ?? process.env.FACE_PYTHON ?? "python3");
  const now = opts.now ?? Date.now;
  const cache = new Map<Mode, Entry>();
  const inflight = new Map<Mode, Promise<{ stdout: string; code: number }>>();

  const send = (res: ServerResponse, status: number, body: string): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(body);
  };

  const handler = (mode: Mode) => async (_req: IncomingMessage, res: ServerResponse): Promise<void> => {
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
      if (code === 0) {
        cache.set(mode, { body: stdout, at: now() });
        return send(res, 200, stdout);
      }
      /* The producer's honest error payload: served, never cached. */
      if (hit) return send(res, 200, markStale(hit.body));
      return send(res, 503, stdout || '{"ok":false,"error":"producer failed"}');
    } catch (err) {
      if (hit) return send(res, 200, markStale(hit.body));
      return send(res, 503, JSON.stringify({ ok: false, error: String(err) }));
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
