/** Channels: the arena as the sidebar and the landing page see it.
 *
 * A channel is one directory given an identity by the host. The directory is
 * the truth of EXISTENCE — `readdir` decides what a channel is, so a channel
 * Kairos makes with a plain `mkdir` is a channel on the next listing and git
 * stays the ledger. The dsh workspace registry adds IDENTITY on top: a stable
 * UUID, a display title decoupled from the folder name, durable session
 * membership, and order. See docs/superpowers/specs/2026-09-03-channels-design.md.
 * @module
 */
import { cp, readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { load } from "js-yaml";
import type { RouteRegistrar } from "./static.ts";
import { isJsonBody, isTrustedDataRequest } from "./data.ts";
import { FORBIDDEN, HttpError, readBody } from "./http.ts";
import { logRosterWrite, rosterFor, seedRoster, setRoster } from "./roster.ts";

/** The copy source every new channel starts from, and never a channel. */
const TEMPLATE = "_template";

/** The repo root's channel name — it is not under `strategies/`, so every
 * listing adds it by hand. */
export const WORKBENCH = "workbench";

/** One channel's directory, before the registry has said anything about it. */
export interface ChannelDir {
  /** Directory basename, or {@link WORKBENCH} for the repo root. */
  name: string;
  /** Absolute directory. */
  dir: string;
  /** True for the repo root, which has no `strategies/` parent. */
  isRoot: boolean;
}

/**
 * The channel directories: the repo root first, then every directory under
 * `<root>/strategies` except the template and hidden names.
 * @param root - absolute workbench repo root.
 * @throws Error if `strategies` exists but is not a directory, or if access is denied.
 */
export async function listChannelDirs(root: string): Promise<ChannelDir[]> {
  const dirs: ChannelDir[] = [{ name: WORKBENCH, dir: root, isRoot: true }];
  let entries: import("node:fs").Dirent[] = [];
  try {
    entries = await readdir(join(root, "strategies"), { withFileTypes: true });
  } catch (err) {
    /* No arena yet is a real state: the workbench is still a channel. Any
     * OTHER readdir failure - EACCES, ENOTDIR - is NOT "no channels", and
     * reporting it as an empty list would make every channel vanish from
     * the sidebar with nothing saying why (charter Rule 5). Let it throw:
     * the route turns it into a failed listing, which the client degrades
     * on rather than rendering as zero channels. */
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
    return dirs;
  }
  const found: ChannelDir[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    /* the copy source is never a channel (same exclusion createChannel's
     * NAME_RE enforces on the write side, below) */
    if (entry.name === TEMPLATE || entry.name.startsWith(".") || entry.name.startsWith("__")) continue;
    found.push({ name: entry.name, dir: join(root, "strategies", entry.name), isRoot: false });
  }
  found.sort((a, b) => a.name.localeCompare(b.name));
  return [...dirs, ...found];
}

/** The one thing the old regex could read, kept as the floor a broken file
 * degrades to: first line-anchored `status:`, first non-space run. */
const STATUS_RE = /(?:^|\n)status:\s*(\S+)/;

/** The channel card's header, every key optional. A channel that fills none
 * of them behaves exactly as it did before this existed. */
export interface ChannelStatus {
  /** Lifecycle: idea | researching | validated | paper | retired. */
  status?: string;
  /** The current conclusion, one sentence. */
  one_line?: string;
  /** The next step. */
  next?: string;
  /** Free key-value figures, stringified for display. */
  numbers?: Record<string, string>;
}

const str = (v: unknown): string | undefined =>
  typeof v === "string" && v.trim() !== "" ? v.trim() : undefined;

/**
 * Read `<dir>/status.yaml`. Absent or unreadable is `{}`; malformed YAML
 * falls back to the `status:` regex, because a hand-mangled file must never
 * remove a channel from the index — status is a badge, not a gate.
 */
export async function readChannelStatus(dir: string): Promise<ChannelStatus> {
  let text: string;
  try {
    text = await readFile(join(dir, "status.yaml"), "utf8");
  } catch {
    return {};
  }
  const floor: ChannelStatus = {};
  const word = STATUS_RE.exec(text)?.[1];
  if (word !== undefined) floor.status = word;

  let doc: unknown;
  try {
    doc = load(text);
  } catch {
    return floor; // malformed: the regex reading is all we honestly have
  }
  if (doc === null || typeof doc !== "object") return floor;

  const raw = doc as Record<string, unknown>;
  const out: ChannelStatus = {};
  const status = str(raw.status) ?? floor.status;
  if (status !== undefined) out.status = status;
  const one = str(raw.one_line);
  if (one !== undefined) out.one_line = one;
  const next = str(raw.next);
  if (next !== undefined) out.next = next;
  if (raw.numbers !== null && typeof raw.numbers === "object" && !Array.isArray(raw.numbers)) {
    const numbers: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw.numbers as Record<string, unknown>)) {
      if (v === null || typeof v === "object") continue;
      numbers[k] = String(v);
    }
    if (Object.keys(numbers).length > 0) out.numbers = numbers;
  }
  return out;
}

/** The template's H1 and its placeholder question, byte-exact. A channel
 * born from `_template` and never written is detected here so its page says
 * "no thesis yet" instead of presenting the placeholder as a thesis. */
const TEMPLATE_H1 = "# <strategy name>";
const TEMPLATE_BODY = "What market behavior does this capture, and why does it exist?";

/** A journal line: `- YYYY-MM-DD: text`. */
const JOURNAL_RE = /^-\s*(\d{4}-\d{2}-\d{2})\s*:\s*(.*)$/;

/** A dated backtest filename: `YYYY-MM-DD-<label>.json`. */
const BACKTEST_RE = /^(\d{4}-\d{2}-\d{2})-.*\.json$/;

/** Everything the landing page derives from a channel's own files. */
export interface ChannelBody {
  thesis: { markdown: string; isTemplate: boolean } | null;
  journal: { date: string; text: string }[];
  backtests: { file: string; bytes: number }[];
  latest: { file: string; json: unknown } | null;
  files: { name: string; bytes: number; mtime: string }[];
}

/**
 * Read one channel directory into the landing page's payload. Every block is
 * independent: a missing or broken file yields that block's empty value and
 * never fails the others, so one bad artifact cannot blank a channel's page.
 */
export async function readChannelBody(dir: string): Promise<ChannelBody> {
  const body: ChannelBody = { thesis: null, journal: [], backtests: [], latest: null, files: [] };

  try {
    const markdown = await readFile(join(dir, "THESIS.md"), "utf8");
    const isTemplate = markdown.includes(TEMPLATE_H1) && markdown.includes(TEMPLATE_BODY);
    body.thesis = { markdown, isTemplate };
  } catch { /* no thesis yet */ }

  try {
    const text = await readFile(join(dir, "journal.md"), "utf8");
    for (const line of text.split("\n")) {
      const m = JOURNAL_RE.exec(line.trim());
      if (m !== null) body.journal.push({ date: m[1], text: m[2].trim() });
    }
    /* newest first; a stable sort keeps same-day entries in file order */
    body.journal.sort((a, b) => b.date.localeCompare(a.date));
  } catch { /* no journal yet */ }

  try {
    const entries = await readdir(join(dir, "backtests"), { withFileTypes: true });
    const rows: { file: string; bytes: number; dated: string | null }[] = [];
    for (const entry of entries) {
      if (!entry.isFile() || entry.name.startsWith(".")) continue;
      const info = await stat(join(dir, "backtests", entry.name));
      rows.push({ file: entry.name, bytes: info.size, dated: BACKTEST_RE.exec(entry.name)?.[1] ?? null });
    }
    /* dated JSONs newest-first, then everything else by name */
    rows.sort((a, b) => {
      if (a.dated !== null && b.dated !== null) return b.dated.localeCompare(a.dated) || a.file.localeCompare(b.file);
      if (a.dated !== null) return -1;
      if (b.dated !== null) return 1;
      return a.file.localeCompare(b.file);
    });
    body.backtests = rows.map((r) => ({ file: r.file, bytes: r.bytes }));
    const newest = rows.find((r) => r.dated !== null);
    if (newest !== undefined) {
      try {
        body.latest = { file: newest.file, json: JSON.parse(await readFile(join(dir, "backtests", newest.file), "utf8")) };
      } catch { /* the file still lists; only the rendered summary is lost */ }
    }
  } catch { /* no backtests/ yet */ }

  try {
    const entries = await readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isFile() || entry.name === "__pycache__") continue;
      const info = await stat(join(dir, entry.name));
      body.files.push({ name: entry.name, bytes: info.size, mtime: info.mtime.toISOString() });
    }
    body.files.sort((a, b) => a.name.localeCompare(b.name));
  } catch { /* unreadable directory — the page still renders its header */ }

  return body;
}

/** One workspace as this module uses it - structural, matching
 * `@deepseek-ai/dsh-workspace`'s `Workspace` (lib/types/types.d.ts:20-90),
 * so the tests drive the reconcile without booting a harness. */
export interface WorkspaceLike {
  readonly id: string;
  readonly path: string;
  readonly title: string;
  readonly sessionIds: readonly string[];
  attachSession(sessionId: string): Promise<void>;
  status(): Promise<"ok" | "missing-dir">;
}

/** `ctx.workspaceRegistry`, narrowed to what the reconcile needs. NOTE:
 * `attachSession` and the `title` argument of `create` are service-only -
 * neither is on the RPC surface, which is why this runs in the face host and
 * not in the browser. */
export interface RegistryLike {
  create(path: string, title?: string): Promise<WorkspaceLike>;
  list(): readonly WorkspaceLike[];
  readonly archivedSessionIds: readonly string[];
  /** Look up by canonical directory path without creating or mutating
   * anything — the same `fs.realpath` canonicalization `create` applies, but
   * a missing path rejects instead of being adopted as a new channel. This is
   * the lookup a session's cwd needs (panels.ts's `channelFor`): asking which
   * channel a directory belongs to must never conjure one into existence. */
  resolveByPath(path: string): Promise<WorkspaceLike | undefined>;
}

/** The two header fields the reconcile reads off a session summary. */
export interface SessionHeadLike {
  sessionId: string;
  cwd?: string;
}

/**
 * Union a persisted session listing with a live one, live winning on a
 * shared id. `sessions.list()` (dsh-session) answers only "All live
 * sessions, in creation order" (`dsh-session/lib/types/index.d.ts:395`) —
 * sessions loaded into THIS process — never the durable history; feeding the
 * reconcile from that alone means a session attaches only if it happens to be
 * live at the moment the sidebar polls, which strands most of the operator's
 * past sessions in `ungrouped` (C1). `sessionPersistence.list()`
 * (`dsh-session-persistence/lib/types/index.d.ts:176`) is the seam that
 * answers the durable listing instead; `dsh-workspace`'s own registry
 * bootstrap reads both this way, live indexed after persisted so a live
 * header overrides a possibly-stale persisted one for the same id
 * (`dsh-workspace/lib/index.js:320-325`).
 *
 * Order is `[...persisted, ...live]` folded through a `Map`, so live entries
 * — later in the array — overwrite a same-id persisted entry rather than the
 * reverse: a just-created session may not be flushed to persistence yet, and
 * a live header is never staler than a persisted one.
 * @param persisted - every materialized session (`sessionPersistence.list()`, mapped).
 * @param live - every session held live by this process (`sessions.list()`, mapped).
 */
export function mergeSessionHeads(
  persisted: readonly SessionHeadLike[],
  live: readonly SessionHeadLike[],
): SessionHeadLike[] {
  return [...new Map([...persisted, ...live].map((s) => [s.sessionId, s] as const)).values()];
}

/** One channel as the sidebar and the picker see it. */
export interface ChannelRow {
  workspaceId: string;
  /** Directory basename (or "workbench") - the git-visible identity. */
  name: string;
  /** The registry's display title; defaults to the basename at create. */
  title: string;
  dir: string;
  isRoot: boolean;
  status?: string;
  /** The directory is gone but the record remains - greyed, never deleted. */
  missingDir: boolean;
  sessionIds: string[];
}

/**
 * Make the registry match the directories, then answer with the channel list.
 *
 * Idempotent by construction: `create` returns an existing record for a
 * canonical path without changing its title, `attachSession` early-outs on
 * membership before any validation, and `seedRoster` is a no-op once an entry
 * exists. Safe on every listing; in the steady state it performs no writes.
 *
 * A workspace whose directory has vanished is REPORTED, never deleted -
 * deleting it would silently drop the operator's history.
 */
export async function reconcileChannels(deps: {
  registry: RegistryLike;
  root: string;
  home: string;
  sessions: readonly SessionHeadLike[];
  connectedBins: readonly string[];
}): Promise<{ channels: ChannelRow[]; ungrouped: SessionHeadLike[] }> {
  const { registry, root, home, sessions, connectedBins } = deps;

  const dirs = await listChannelDirs(root);
  /* The real registry canonicalizes `path` (e.g. via fs.realpath) on create,
   * so the record it hands back can spell a directory differently than the
   * string we walked (a symlinked tmp dir or mount point, `..` segments,
   * ...) - macOS alone does this for every `os.tmpdir()` path. Track BOTH
   * spellings for every adopted channel: neither the attach match nor the
   * orphan scan below may assume the two are the same string. */
  const knownPaths = new Set<string>();
  const rows: ChannelRow[] = [];
  const claimed = new Set<string>();

  for (const d of dirs) {
    let ws: WorkspaceLike;
    try {
      ws = await registry.create(d.dir, d.name);
    } catch {
      /* the directory vanished between readdir and create - the next listing
       * sees it as gone, which is already a defined state */
      continue;
    }
    const paths = new Set([d.dir, ws.path]);
    for (const p of paths) knownPaths.add(p);

    for (const session of sessions) {
      if (session.cwd === undefined || !paths.has(session.cwd)) continue; // the channel dir itself, never a subdirectory
      try {
        await ws.attachSession(session.sessionId);
        /* Claimed only once the attach actually lands. The real host
         * validates the session header's cwd against the workspace path and
         * REJECTS a mismatch without writing (caught below) - marking the
         * session claimed before that call, as an earlier version of this
         * function did, would silently drop a refused session from every
         * surface: not in `sessionIds`, not in `ungrouped` either. Falling
         * through to `ungrouped` on rejection is the correct report
         * (charter Rule 5: what is never surfaced is never governed). */
        claimed.add(session.sessionId);
      } catch { /* the host validates the header cwd and refuses; not ours to force */ }
    }
    await seedRoster(home, ws.id, connectedBins);
    const status = await readChannelStatus(d.dir);
    const row: ChannelRow = {
      workspaceId: ws.id, name: d.name, title: ws.title, dir: d.dir, isRoot: d.isRoot,
      missingDir: (await ws.status()) === "missing-dir",
      sessionIds: [...ws.sessionIds],
    };
    if (status.status !== undefined) row.status = status.status;
    rows.push(row);
  }

  /* Registered workspaces whose directory is no longer a channel: keep them
   * visible so nothing the operator made disappears silently. */
  for (const ws of registry.list()) {
    if (knownPaths.has(ws.path)) continue;
    for (const id of ws.sessionIds) claimed.add(id);
    rows.push({
      workspaceId: ws.id,
      name: ws.path.split("/").filter((p) => p !== "").pop() ?? ws.title,
      title: ws.title, dir: ws.path, isRoot: false,
      missingDir: (await ws.status()) === "missing-dir",
      sessionIds: [...ws.sessionIds],
    });
  }

  /* Rule 5: what is never surfaced is never governed. Sessions belonging to
   * no channel are RETURNED and counted, not filtered away. */
  const ungrouped = sessions.filter((s) => !claimed.has(s.sessionId));
  return { channels: rows, ungrouped };
}

/* ---------- creating a channel, and the four routes over all of the above
 * (Task 7) ---------- */

/** Exactly a channel directory name: one path segment of letters and digits
 * in ANY script (a Chinese name is a name) plus `-` and `_`, 1-41 code
 * points, opening with a letter or digit - so `.`/`..`, dotfiles, separators,
 * spaces and control characters never reach a path. Compared and created in
 * NFC, so one word typed in two normalizations is one directory. */
const NAME_RE = /^[\p{L}\p{N}][\p{L}\p{N}\p{M}_-]{0,40}$/u;

/** Birth `strategies/<name>` from the template. Refuses a malformed name, a
 * taken name, and a missing template - never overwrites anything. */
export async function createChannel(root: string, rawName: unknown): Promise<ChannelDir> {
  const name = typeof rawName === "string" ? rawName.normalize("NFC") : rawName;
  if (typeof name !== "string" || !NAME_RE.test(name) || name === TEMPLATE) {
    throw new HttpError(400, "invalid channel name (letters or digits in any script, plus - and _; no spaces, dots or slashes; up to 41 characters)");
  }
  const template = join(root, "strategies", TEMPLATE);
  try {
    await stat(template);
  } catch {
    throw new HttpError(500, "strategies/_template missing");
  }
  const target = join(root, "strategies", name);
  let exists = true;
  try {
    await stat(target);
  } catch {
    exists = false;
  }
  if (exists) throw new HttpError(409, "channel already exists");
  await cp(template, target, { recursive: true, filter: (src) => !src.includes("__pycache__") });
  return { name, dir: target, isRoot: false };
}

/** What the routes need of the booted tree. Injected so the tests drive them
 * without a harness. */
export interface ChannelRouteDeps {
  registry: RegistryLike;
  /** Absolute workbench repo root. */
  root: string;
  /** The harness home holding `face/channels.json`. */
  home: string;
  /** Every visible session's id and cwd - `session.list`, host-side. */
  listSessions(): Promise<SessionHeadLike[]>;
  /** The bins a newly adopted channel's roster is seeded from. */
  connectedBins(): Promise<string[]>;
}

/** Mount the four channel routes. Same trust posture as data.ts: the fence
 * runs FIRST on every route, the refusal body is fixed text, and nothing
 * attacker-controlled is ever echoed. A workspace id from a body is only ever
 * COMPARED against the reconciled list - it never becomes a path. */
export function registerChannelRoutes(webServer: RouteRegistrar, deps: ChannelRouteDeps): void {
  const send = (res: ServerResponse, status: number, body: unknown): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(typeof body === "string" ? body : JSON.stringify(body));
  };

  const reconcile = async (): Promise<{ channels: ChannelRow[]; ungrouped: SessionHeadLike[] }> =>
    reconcileChannels({
      registry: deps.registry, root: deps.root, home: deps.home,
      sessions: await deps.listSessions(), connectedBins: await deps.connectedBins(),
    });

  /** The guard the three writing routes share. */
  const guardPost = (req: IncomingMessage, res: ServerResponse): boolean => {
    if (!isTrustedDataRequest(req)) { send(res, 403, FORBIDDEN); return false; }
    if (req.method !== "POST") { send(res, 405, { ok: false, error: "POST only" }); return false; }
    if (!isJsonBody(req)) { send(res, 415, { ok: false, error: "application/json only" }); return false; }
    return true;
  };

  const bodyOf = async (req: IncomingMessage): Promise<Record<string, unknown>> => {
    try {
      const parsed: unknown = JSON.parse(await readBody(req));
      return parsed !== null && typeof parsed === "object" ? parsed as Record<string, unknown> : {};
    } catch (err) {
      if (err instanceof HttpError) throw err;
      throw new HttpError(400, "body must be JSON");
    }
  };

  webServer.register({
    kind: "exact",
    path: "/data/channels.json",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      try {
        const { channels, ungrouped } = await reconcile();
        return send(res, 200, {
          ok: true, root: deps.root, channels, ungrouped,
          archived: [...deps.registry.archivedSessionIds],
        });
      } catch {
        /* nothing from the filesystem error reaches the body */
        return send(res, 500, { ok: false, error: "listing failed" });
      }
    },
  });

  webServer.register({
    kind: "exact",
    path: "/data/channels/overview",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!guardPost(req, res)) return;
      try {
        const { workspaceId } = await bodyOf(req);
        const { channels } = await reconcile();
        const channel = channels.find((c) => c.workspaceId === workspaceId);
        if (channel === undefined) return send(res, 404, { ok: false, error: "no such channel" });
        return send(res, 200, {
          ok: true, channel,
          status: await readChannelStatus(channel.dir),
          body: await readChannelBody(channel.dir),
          agents: await rosterFor(deps.home, channel.workspaceId) ?? [],
        });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "overview failed" });
      }
    },
  });

  webServer.register({
    kind: "exact",
    path: "/data/channels/agents",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!guardPost(req, res)) return;
      try {
        const { workspaceId, agents } = await bodyOf(req);
        const { channels } = await reconcile();
        if (!channels.some((c) => c.workspaceId === workspaceId)) return send(res, 404, { ok: false, error: "no such channel" });
        if (!Array.isArray(agents) || agents.some((a) => typeof a !== "string")) {
          return send(res, 400, { ok: false, error: "agents must be an array of bin names" });
        }
        const id = workspaceId as string;
        await setRoster(deps.home, id, agents as string[]);
        /* The roster is operator-owned, but the surface that writes it is an
         * unauthenticated loopback route (spec section 5, limit 3). What
         * cannot be prevented is at least made VISIBLE - Rule 5 - via a
         * dated line in a durable face log (I2; see roster.ts's
         * `logRosterWrite`), not just a bare, undated stdout line. */
        await logRosterWrite(deps.home, id, agents as string[]);
        return send(res, 200, { ok: true, agents: await rosterFor(deps.home, id) ?? [] });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "roster write failed" });
      }
    },
  });

  webServer.register({
    kind: "exact",
    path: "/data/channels",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!guardPost(req, res)) return;
      let made: ChannelDir;
      try {
        made = await createChannel(deps.root, (await bodyOf(req)).name);
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "create failed" });
      }
      /* I3: the directory is ON DISK once createChannel above returns - the
       * channel exists whether or not this reconcile succeeds. A throw here
       * (EACCES out of listChannelDirs, a withFileLock timeout in
       * seedRoster, an EIO in ws.status()) must NOT be reported as "create
       * failed": that would be a successful creation answered as a 500, the
       * client showing no row, and a retry hitting 409 "channel already
       * exists" - the face contradicting its own filesystem. Adoption and
       * roster-seeding are a convenience that also runs on every ordinary
       * listing, so a failure here just means the NEXT listing does the
       * adopting instead - never fatal to this response. */
      try {
        await reconcile(); // adopt it and seed its roster before the client asks
      } catch { /* surfaced on the next listing, same as any other reconcile failure */ }
      return send(res, 200, { ok: true, ...made });
    },
  });
}
