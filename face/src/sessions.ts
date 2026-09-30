/** Session housekeeping the host does not fully provide at this pin: delete,
 * and a reversible archive.
 *
 * dsh 0.2.0-rc.2 exposes rename and fork over RPC but still no session DELETE
 * (no delete/remove `@Remote` in `packages/api/session-controller/src` or
 * `packages/session/session-persistence/src`), so that lands here. The host
 * DOES own an archive — `workspaceRegistry.archiveSession` and, since 0.2.0,
 * `unarchiveSession` (NEW `packages/workspace/workspace/src/index.ts:363-411`)
 * — but a host archive is not presentation: an archived session "runs no model
 * step until it is restored" (`ArchivedSessionGate`, NEW
 * `packages/api/session-controller/src/index.ts:162-165`). The face's fold is
 * pure presentation and reversible, which is why `archived.json` stays and the
 * face never writes the host set (PLAN D14).
 *
 * - DELETE removes the session's persistence directory
 *   (`$DSH_HOME/sessions/<project-slug>/<session-id>/`) permanently — there
 *   is no trash. The id is validated against the exact session-uuid shape
 *   before it touches a path, and — because ids are unique across EVERY
 *   project under `$DSH_HOME/sessions/`, not just this repo's — the
 *   directory's own header `cwd` must resolve inside the workbench repo
 *   before it is touched, or the delete button could reach another
 *   project's session (this operator's home really does hold slugs for
 *   `trend-dragon` and `dsh-playground` alongside this repo's). The face
 *   cannot see whether an agent is attached, so the CLIENT refuses to offer
 *   delete on a running session; this route is the operator's own hand
 *   either way (loopback-fenced, like everything under /data).
 * - ARCHIVE is presentation metadata, not host state: a JSON set of session
 *   ids under `$DSH_HOME/face/archived.json`. Archived sessions still exist,
 *   still list, still open — the sidebar just folds them away. Reversible by
 *   the same route — UNLESS the host archived the same id itself: that
 *   un-archive is refused (409, with the reason in the response), never
 *   silently dropped (charter Rule 5).
 * @module
 */
import { mkdir, open, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { promisify } from "node:util";
import { zstdDecompress } from "node:zlib";
import { resolveDshHome } from "@deepseek-ai/dsh-home-paths";
import type { RouteRegistrar } from "./static.ts";
import { isJsonBody, isTrustedDataRequest } from "./data.ts";
import { FORBIDDEN, HttpError, readBody } from "./http.ts";

const zstdDecompressAsync = promisify(zstdDecompress);

/** Exactly a dsh session id: the literal prefix and a uuid, nothing else —
 * what makes it safe to use as one path segment. */
export const SESSION_ID_RE = /^session-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

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
    throw new HttpError(400, "invalid session id");
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

/** Add or remove one id from the archive set; returns the metadata after.
 * @param hostArchived - the host's own archive set
 * (`ctx.workspaceRegistry.archivedSessionIds`), if known. The face does not
 * un-archive host archives (PLAN D14): the host can
 * (`workspaceRegistry.unarchiveSession`, NEW
 * `packages/workspace/workspace/src/index.ts:397-411`), but that is a change
 * to what the session may RUN — a host-archived session runs no model step
 * (`ArchivedSessionGate`, NEW `packages/api/session-controller/src/index.ts:162-165`)
 * — not to what the sidebar shows. So an id already in the host set must
 * refuse un-archiving here: silently accepting the click would show a session
 * that every other surface still folds away and that still cannot run, and
 * the face's set has no way to represent "the host still considers this
 * archived" other than refusing to diverge from it. */
export async function setArchived(
  home: string,
  sessionId: unknown,
  archived: boolean,
  hostArchived: readonly string[] = [],
): Promise<SessionsMeta> {
  assertSessionId(sessionId);
  if (!archived && hostArchived.includes(sessionId)) {
    throw new HttpError(
      409,
      "this session was archived by the host: the face does not un-archive host archives, and a host-archived session runs no model step until the host restores it",
    );
  }
  const meta = await readMeta(home);
  const set = new Set(meta.archived);
  if (archived) set.add(sessionId);
  else set.delete(sessionId);
  const next = { archived: [...set].sort(), deleted: meta.deleted };
  await writeMeta(home, next);
  return next;
}

/** Bytes read from a session log's start when hunting for its header record.
 * A header carries a handful of short fields (id, cwd, optionally a parent
 * session id and an agent-preset name) — this is generous headroom for all of
 * them while staying far below the size of any real conversation, so probing
 * a multi-megabyte log costs the same one bounded read as a brand-new one. */
const HEADER_PROBE_BYTES = 65536;

/** Read up to `HEADER_PROBE_BYTES` from the start of `path`, or undefined if
 * it cannot be opened (most commonly: this candidate filename doesn't exist). */
async function readPrefix(path: string): Promise<Buffer | undefined> {
  let handle;
  try {
    handle = await open(path, "r");
  } catch {
    return undefined;
  }
  try {
    const buf = Buffer.alloc(HEADER_PROBE_BYTES);
    const { bytesRead } = await handle.read(buf, 0, HEADER_PROBE_BYTES, 0);
    return buf.subarray(0, bytesRead);
  } finally {
    await handle.close();
  }
}

/** The canonical generation-log basename, with or without the Zstandard
 * suffix: `session.jsonl[.zstd]` is format v0, `session.v<N>.jsonl[.zstd]`
 * (N >= 1, no leading zero) is format vN. Mirrors NEW
 * `packages/session/session-format/src/filename.ts:5` plus the compression
 * suffix of `packages/session/session-persistence-jsonl/src/format.ts:58-77`.
 * Everything else in a session directory — `session.lock` (the flock lease,
 * `session-persistence-jsonl/src/lease.ts:1-40`), `session.migration.*.tmp`
 * and `<final>.<hex>.tmp` staging files — fails this pattern by construction,
 * so it is never mistaken for a log. */
const GENERATION_LOG_RE = /^session(?:\.v([1-9]\d*))?\.jsonl(\.zstd)?$/;

/** One committed generation log found in a session directory. */
export interface GenerationLog {
  /** Basename inside the session directory. */
  name: string;
  /** Session format version the filename claims (0 when there is no `.vN`). */
  version: number;
  /** True for the `.zstd` encoding (one independent Zstandard frame per record batch). */
  zstd: boolean;
}

/** Pick the authoritative generation among a session directory's entries: the
 * numerically highest canonical version, as the host's own resolver does
 * (NEW `packages/session/session-persistence-jsonl/src/index.ts:1446-1483`,
 * "Select the numerically highest canonical generation"). A migrated 0.1.1
 * session holds BOTH `session.jsonl.zstd` (v0, byte-preserved) and
 * `session.v4.jsonl.zstd` (published beside it on the first 0.2.0 write
 * open); a session born under 0.2.0 holds only the v4 file. At an equal
 * version the `.zstd` file wins — the host itself refuses a directory mixing
 * both encodings (`index.ts:1462-1472`, `encodingMismatch`), so this tie-break
 * only decides which of two unreadable-to-the-host candidates we read, and the
 * compressed one is what dsh writes by default.
 * @param names - basenames in one session directory.
 * @returns the chosen log, or undefined when no canonical log is present. */
export function pickGenerationLog(names: readonly string[]): GenerationLog | undefined {
  let best: GenerationLog | undefined;
  for (const name of names) {
    const match = GENERATION_LOG_RE.exec(name);
    if (match === null) continue;
    const version = match[1] === undefined ? 0 : Number(match[1]);
    if (!Number.isSafeInteger(version)) continue; // absurd digit run: not canonical (filename.ts:30-31)
    const candidate = { name, version, zstd: match[2] !== undefined };
    if (
      best === undefined ||
      candidate.version > best.version ||
      (candidate.version === best.version && candidate.zstd && !best.zstd)
    ) {
      best = candidate;
    }
  }
  return best;
}

/** Read the `cwd` a session directory's own persisted header claims — the
 * only place `deleteSession` can learn it, since the id alone does not carry
 * it and the on-disk log is authoritative regardless of whether the session
 * is currently live in host memory (see the module docstring's tombstone
 * note). The log read is the highest canonical generation
 * ({@link pickGenerationLog}); without that, every session created under dsh
 * 0.2.0 (only `session.v4.jsonl.zstd` on disk) would read as "no header" and
 * be refused with a 404. Every generation "starts with a physical header whose
 * version equals its filename" (NEW `session-persistence-jsonl/README.md:56`),
 * and the header keeps `cwd` in v4 (`format.ts:83-98`). dsh writes that header
 * as its own independently compressed Zstandard frame when compression is on
 * — native v4 (`session-persistence-jsonl/src/index.ts:1290-1297`) and
 * migrated v4 (`generation.ts:746-748`) alike, as v0 did — and as a plain first
 * line when it is off, so a single-shot zstd decode of a bounded prefix is
 * enough: it consumes exactly the first complete frame and ignores whatever
 * event data follows it in the buffer.
 * @returns the header's cwd, or undefined when the header is missing,
 * unreadable, or carries no cwd. Callers MUST treat that as UNKNOWN, never as
 * "safe" — the whole point of this read is to tell "inside the repo" apart
 * from "can't tell", and only the former may authorize a delete.
 */
async function readSessionCwd(dir: string): Promise<string | undefined> {
  let names: string[];
  try {
    names = await readdir(dir);
  } catch {
    return undefined; // unlistable directory - unknown, not safe
  }
  const log = pickGenerationLog(names);
  if (log === undefined) return undefined;
  const prefix = await readPrefix(join(dir, log.name));
  if (prefix === undefined || prefix.length === 0) return undefined;
  try {
    const text = log.zstd ? (await zstdDecompressAsync(prefix)).toString("utf8") : prefix.toString("utf8");
    const parsed: unknown = JSON.parse(text.split("\n", 1)[0]);
    const cwd = parsed !== null && typeof parsed === "object" ? (parsed as { cwd?: unknown }).cwd : undefined;
    return typeof cwd === "string" ? cwd : undefined;
  } catch {
    return undefined; // present but undecodable - unknown, not safe
  }
}

/** Permanently remove one session's persistence directory, drop its archive
 * entry, and tombstone the id so a host-memory ghost never lists.
 * @param home - the harness home whose `sessions/` tree is searched.
 * @param root - the workbench repo root. Session ids are unique across every
 * project under `home`, so the id-only scan below would otherwise let this
 * reach another project's session directory; a session this face may delete
 * is one whose header `cwd` resolves inside `root` (an unreadable or missing
 * header — see {@link readSessionCwd} — refuses the same as "outside").
 * @param sessionId - the session id to remove.
 */
export async function deleteSession(home: string, root: string, sessionId: unknown): Promise<SessionsMeta> {
  assertSessionId(sessionId);
  const sessionsRoot = join(home, "sessions");
  let slugs: string[];
  try {
    slugs = (await readdir(sessionsRoot, { withFileTypes: true }))
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
  } catch {
    throw new HttpError(404, "session not found");
  }
  for (const slug of slugs) {
    const dir = join(sessionsRoot, slug, sessionId);
    try {
      await stat(dir);
    } catch {
      continue;
    }
    const cwd = await readSessionCwd(dir);
    if (cwd === undefined || (cwd !== root && !cwd.startsWith(`${root}/`))) {
      throw new HttpError(404, "session not found");
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
  throw new HttpError(404, "session not found");
}

/** What `registerSessionRoutes` needs from the booted tree. */
export interface SessionRouteDeps {
  /** The workbench repo root — {@link deleteSession}'s constraint (see its
   * docstring). Not defaulted: unlike `home`, there is no harness-wide
   * resolution for "this repo", so the caller must say what it is (main.ts
   * passes `process.cwd()`, the same value {@link registerChannelRoutes}
   * gets, right after the entry point commits to it). */
  root: string;
  /** Harness home override; defaults to the resolved `$DSH_HOME`. */
  home?: string;
  /** The host's own session-archive set, narrowed from `ctx.workspaceRegistry`
   * the same way channels.ts's `RegistryLike` is. Read live on every
   * un-archive attempt (never snapshotted at registration) because it changes
   * while the face runs — a session the host archives after this call still
   * must be refused, and one the host restores (`unarchiveSession`, from the
   * CLI or another client) must stop being refused. Omitted (e.g. no host
   * registry available) behaves as "the host has archived nothing". */
  hostArchive?: { readonly archivedSessionIds: readonly string[] };
}

/**
 * Mount the session-housekeeping routes.
 * @param webServer - the host webserver service, or a test recorder.
 * @param deps - the repo root, harness-home override, and host archive set.
 */
export function registerSessionRoutes(webServer: RouteRegistrar, deps: SessionRouteDeps): void {
  const { root } = deps;
  const dshHome = deps.home ?? resolveDshHome(undefined);
  const hostArchived = (): readonly string[] => deps.hostArchive?.archivedSessionIds ?? [];

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
          if (err instanceof HttpError) throw err;
          throw new HttpError(400, "body must be a JSON object");
        }
        return send(res, 200, { ok: true, ...(await act(body)) as object });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
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
    handler: post(async (body) =>
      await setArchived(dshHome, body.sessionId, body.archived === true, hostArchived())),
  });

  webServer.register({
    kind: "exact",
    path: "/data/sessions/delete",
    handler: post(async (body) => await deleteSession(dshHome, root, body.sessionId)),
  });
}
