/** Session housekeeping the host does not provide at this pin: delete and
 * archive.
 *
 * dsh 0.1.1-rc.2 exposes rename and fork over RPC but no delete and no
 * archive. Both land here, host-side in the face:
 *
 * - DELETE removes the session's persistence directory
 *   (`$DSH_HOME/sessions/<project-slug>/<session-id>/`) permanently — there
 *   is no trash. The id is validated against the exact session-uuid shape
 *   before it touches a path. The face cannot see whether an agent is
 *   attached, so the CLIENT refuses to offer delete on a running session;
 *   this route is the operator's own hand either way (loopback-fenced, like
 *   everything under /data).
 * - ARCHIVE is presentation metadata, not host state: a JSON set of session
 *   ids under `$DSH_HOME/face/archived.json`. Archived sessions still exist,
 *   still list, still open — the sidebar just folds them away. Reversible by
 *   the same route.
 * @module
 */
import { mkdir, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { resolveDshHome } from "@deepseek-ai/dsh-home-paths";
import type { RouteRegistrar } from "./static.ts";
import { isJsonBody, isTrustedDataRequest } from "./data.ts";
import { readBody, StrategyError } from "./strategies.ts";

const FORBIDDEN = '{"ok":false,"error":"forbidden"}';

/** Exactly a dsh session id: the literal prefix and a uuid, nothing else —
 * what makes it safe to use as one path segment. */
const SESSION_ID_RE = /^session-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** The face's session-metadata file under the harness home. */
const META_FILE = ["face", "archived.json"] as const;

/** What the face remembers about sessions the host does not: the archive fold,
 * and tombstones for deletions — a session deleted while its agent was still
 * attached keeps LISTING from host memory until a restart (and write-behind
 * may even re-persist its directory); the tombstone keeps the ghost out of
 * the sidebar either way. */
export interface SessionsMeta {
  archived: string[];
  deleted: string[];
}

function assertSessionId(sessionId: unknown): asserts sessionId is string {
  if (typeof sessionId !== "string" || !SESSION_ID_RE.test(sessionId)) {
    throw new StrategyError(400, "invalid session id");
  }
}

const cleanIds = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((id) => typeof id === "string" && SESSION_ID_RE.test(id)) : [];

/** @returns the stored metadata; an absent, unreadable, or legacy (bare
 * archive array) file reads as best it can — this is a convenience, never a gate. */
export async function readMeta(home: string): Promise<SessionsMeta> {
  try {
    const parsed: unknown = JSON.parse(await readFile(join(home, ...META_FILE), "utf8"));
    if (Array.isArray(parsed)) return { archived: cleanIds(parsed), deleted: [] };
    if (parsed !== null && typeof parsed === "object") {
      const record = parsed as Record<string, unknown>;
      return { archived: cleanIds(record.archived), deleted: cleanIds(record.deleted) };
    }
  } catch { /* fall through to empty */ }
  return { archived: [], deleted: [] };
}

async function writeMeta(home: string, meta: SessionsMeta): Promise<void> {
  await mkdir(join(home, META_FILE[0]), { recursive: true });
  await writeFile(join(home, ...META_FILE), JSON.stringify(meta), "utf8");
}

/** Add or remove one id from the archive set; returns the metadata after. */
export async function setArchived(home: string, sessionId: unknown, archived: boolean): Promise<SessionsMeta> {
  assertSessionId(sessionId);
  const meta = await readMeta(home);
  const set = new Set(meta.archived);
  if (archived) set.add(sessionId);
  else set.delete(sessionId);
  const next = { archived: [...set].sort(), deleted: meta.deleted };
  await writeMeta(home, next);
  return next;
}

/** Permanently remove one session's persistence directory, drop its archive
 * entry, and tombstone the id so a host-memory ghost never lists. */
export async function deleteSession(home: string, sessionId: unknown): Promise<SessionsMeta> {
  assertSessionId(sessionId);
  const sessionsRoot = join(home, "sessions");
  let slugs: string[];
  try {
    slugs = (await readdir(sessionsRoot, { withFileTypes: true }))
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
  } catch {
    throw new StrategyError(404, "session not found");
  }
  for (const slug of slugs) {
    const dir = join(sessionsRoot, slug, sessionId);
    try {
      await stat(dir);
    } catch {
      continue;
    }
    await rm(dir, { recursive: true, force: true });
    const meta = await readMeta(home);
    const next = {
      archived: meta.archived.filter((id) => id !== sessionId),
      deleted: [...new Set([...meta.deleted, sessionId])].sort(),
    };
    await writeMeta(home, next);
    return next;
  }
  throw new StrategyError(404, "session not found");
}

/**
 * Mount the session-housekeeping routes.
 * @param webServer - the host webserver service, or a test recorder.
 * @param home - harness home override; defaults to the resolved `$DSH_HOME`.
 */
export function registerSessionRoutes(webServer: RouteRegistrar, home?: string): void {
  const dshHome = home ?? resolveDshHome(undefined);

  const send = (res: ServerResponse, status: number, body: unknown): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(typeof body === "string" ? body : JSON.stringify(body));
  };

  /** The shared shell: fence, method gate, JSON body, error mapping. */
  const post = (act: (body: Record<string, unknown>) => Promise<unknown>) =>
    async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      if (req.method !== "POST") return send(res, 405, { ok: false, error: "POST only" });
      if (!isJsonBody(req)) return send(res, 415, { ok: false, error: "application/json only" });
      try {
        let body: Record<string, unknown>;
        try {
          const parsed: unknown = JSON.parse(await readBody(req));
          if (parsed === null || typeof parsed !== "object") throw new Error("not an object");
          body = parsed as Record<string, unknown>;
        } catch (err) {
          if (err instanceof StrategyError) throw err;
          throw new StrategyError(400, "body must be a JSON object");
        }
        return send(res, 200, { ok: true, ...(await act(body)) as object });
      } catch (err) {
        if (err instanceof StrategyError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "request failed" });
      }
    };

  webServer.register({
    kind: "exact",
    path: "/data/sessions-meta.json",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      return send(res, 200, { ok: true, ...(await readMeta(dshHome)) });
    },
  });

  webServer.register({
    kind: "exact",
    path: "/data/sessions/archive",
    handler: post(async (body) => await setArchived(dshHome, body.sessionId, body.archived === true)),
  });

  webServer.register({
    kind: "exact",
    path: "/data/sessions/delete",
    handler: post(async (body) => await deleteSession(dshHome, body.sessionId)),
  });
}
