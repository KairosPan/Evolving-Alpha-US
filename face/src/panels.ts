/** The master-rail panel feeds the host RPC surface cannot serve: memory and
 * plugin.
 *
 * The sidebar's four sections split by data source. `strategy` runs on
 * `session.*`/`workspace.*` and the face's own session routes; `agent` runs
 * entirely on RPC the client can already call (`host.describe`,
 * `settings.describe`, `credentials.describe`). The remaining two need what
 * only the booted tree holds in-process:
 *
 * - MEMORY is the skill catalog — Kairos's standing knowledge (the mechanics
 *   and style-kairos packs). `skill.list` over RPC needs an attached session
 *   and drops source/path/body; `ctx.skills` has the full record and the
 *   markdown body, so the routes here read it directly.
 * - PLUGIN is the composed row tree and the MCP tool roster. Neither has any
 *   RPC at this pin (`dsh-host-plugin-inventory` is not mounted, and its
 *   record is a 12-line projection of `ctx.loader.entries()` anyway — restated
 *   here rather than mounted, so no new row and no second gateway).
 *
 * Read-only by construction: three GET-shaped reads and one body-addressed
 * lookup, no writes anywhere. Loopback-fenced like every `/data` route.
 * @module
 */
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Context } from "@deepseek-ai/cordis";
import type { RouteRegistrar } from "./static.ts";
import { isLoopbackHost } from "./data.ts";
import { readBody, StrategyError } from "./strategies.ts";

const FORBIDDEN = '{"ok":false,"error":"forbidden"}';

/** Exactly a dsh skill name (`isSkillName`, dsh-tool-skill 0.1.1-rc.2):
 * kebab-case, which is what makes it safe to hand to a registry lookup. */
const SKILL_NAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/** Fiber state → phase word, the mirror of dsh-host-plugin-inventory's
 * FIBER_PHASE (lib/index.js:47-63): PENDING/LOADING/ACTIVE/FAILED/DISPOSED/
 * UNLOADING by ordinal, DISPOSED reading as null like an absent fiber. */
const FIBER_PHASE: ReadonlyArray<string | null> = [
  "pending", "loading", "active", "failed", null, "unloading",
];

/** What a skill summary looks like to these routes (dsh-skill's SkillSummary,
 * structurally): enough to list and to group by pack directory. */
export interface SkillRow {
  name: string;
  description: string;
  whenToUse?: string;
  source?: string;
  invocation?: { modelInvocable?: boolean; userInvocable?: boolean };
  resourceBase?: { kind?: string; path?: string };
}

/** A full skill definition: the summary plus the markdown body. */
export interface SkillBody extends SkillRow {
  content?: string;
  path?: string;
}

/** One composed Loader row, as the plugin panel shows it — the same projection
 * `dsh-host-plugin-inventory` makes, plus `serverName` for MCP rows so the
 * panel can pair a server with its registered tools. */
export interface PluginRow {
  id: string;
  module: string;
  enabled: boolean;
  phase: string | null;
  serverName?: string;
}

/** What {@link registerPanelRoutes} needs of the booted tree. Structural and
 * injected so the tests drive the routes without a harness; {@link panelDeps}
 * builds the real one from `ctx`. */
export interface PanelDeps {
  skills: {
    list(options: { cwd: string }): Promise<SkillRow[]>;
    get(name: string, options: { cwd: string }): Promise<SkillBody | undefined>;
  };
  /** `ctx.tools.schemas()` — the global tool view, MCP registrations included. */
  toolSchemas(): { name: string; description: string }[];
  /** `ctx.loader.entries()` — the LIVE composed row tree. */
  loaderEntries(): Iterable<{
    id: string;
    options: { name?: string; group?: unknown; config?: unknown };
    disabled?: boolean;
    fiber?: { state: number };
  }>;
  /** The cwd skill discovery resolves project roots against. */
  cwd: string;
}

/**
 * Build the real {@link PanelDeps} from the booted root context.
 *
 * Fails loud at boot rather than 500 at first click: a tree missing any of
 * these services is a composition error (`dsh-base` mounts all three), and a
 * panel that comes up dead with nothing on stderr saying why is the failure
 * mode this check exists to prevent.
 * @param ctx - the settled root context `bootFace` returned.
 * @param cwd - the workbench repo root (main.ts anchored the process there).
 */
export function panelDeps(ctx: Context, cwd: string): PanelDeps {
  const skills = ctx.get("skills") as PanelDeps["skills"] | undefined;
  const tools = ctx.get("tools") as { schemas(): { name: string; description: string }[] } | undefined;
  const loader = ctx.get("loader") as { entries(): ReturnType<PanelDeps["loaderEntries"]> } | undefined;
  const missing = [
    ...(skills === undefined ? ["skills"] : []),
    ...(tools === undefined ? ["tools"] : []),
    ...(loader === undefined ? ["loader"] : []),
  ];
  if (skills === undefined || tools === undefined || loader === undefined) {
    throw new Error(`kairos-face: panel services missing from the composed tree: ${missing.join(", ")}`);
  }
  return {
    skills,
    toolSchemas: () => tools.schemas(),
    loaderEntries: () => loader.entries(),
    cwd,
  };
}

/** Which pack a skill belongs to: the directory under `dsh/skills/` when it
 * came from one of the repo's skill roots, else its discovery source. The
 * summary carries no group field — `resourceBase.path` is the skill's own
 * directory (`.../dsh/skills/<pack>/<name>`), so the pack is its parent. */
export function skillGroup(row: SkillRow): string {
  const path = row.resourceBase?.kind === "directory" ? row.resourceBase.path : undefined;
  const match = typeof path === "string" ? /\/dsh\/skills\/([^/]+)\//.exec(`${path}/`) : null;
  return match?.[1] ?? row.source ?? "other";
}

/** The memory listing: skills grouped by pack, mechanics first — the neutral
 * pack outranks style in the sidebar for the same reason it does in the
 * doctrine: findings never overrule mechanics. */
export async function memoryListing(deps: PanelDeps): Promise<{ groups: { name: string; skills: object[] }[] }> {
  const rows = await deps.skills.list({ cwd: deps.cwd });
  const buckets = new Map<string, object[]>();
  for (const row of rows) {
    const group = skillGroup(row);
    const bucket = buckets.get(group) ?? [];
    if (bucket.length === 0) buckets.set(group, bucket);
    bucket.push({
      name: row.name,
      description: row.description,
      whenToUse: row.whenToUse,
      modelInvocable: row.invocation?.modelInvocable === true,
      userInvocable: row.invocation?.userInvocable === true,
    });
  }
  const order = [...buckets.keys()].sort((a, b) => {
    const rank = (name: string): number => (name === "mechanics" ? 0 : name === "style-kairos" ? 1 : 2);
    return rank(a) - rank(b) || a.localeCompare(b);
  });
  return { groups: order.map((name) => ({ name, skills: buckets.get(name) ?? [] })) };
}

/** One skill's full record, body included. 400 on a malformed name, 404 when
 * the registry has no such skill. */
export async function skillDetail(deps: PanelDeps, name: unknown): Promise<object> {
  if (typeof name !== "string" || !SKILL_NAME_RE.test(name)) throw new StrategyError(400, "invalid skill name");
  const skill = await deps.skills.get(name, { cwd: deps.cwd });
  if (skill === undefined) throw new StrategyError(404, "skill not found");
  return {
    name: skill.name,
    description: skill.description,
    group: skillGroup(skill),
    path: skill.path,
    content: skill.content ?? "",
  };
}

/**
 * The plugin listing: the live composed rows and the MCP servers with their
 * registered tools.
 *
 * SECURITY: a row's `options.config` is NEVER serialized — the MCP row's env
 * block carries the operator's APCA keys. The one field read out of any
 * config is the MCP row's `serverName`, a validated `[A-Za-z0-9_-]` token.
 */
export function pluginListing(deps: PanelDeps): {
  mcp: { server: string; phase: string | null; tools: { name: string; description: string }[] }[];
  rows: PluginRow[];
} {
  const rows: PluginRow[] = [];
  for (const entry of deps.loaderEntries()) {
    if (entry.options.group) continue; // group rows are containers, not plugins
    const module = entry.options.name ?? "";
    if (module === "" || module === "cordis:include") continue; // the tree's own root
    const config = entry.options.config;
    const serverName = module === "@deepseek-ai/dsh-mcp-client"
      && config !== null && typeof config === "object"
      && typeof (config as { serverName?: unknown }).serverName === "string"
      ? (config as { serverName: string }).serverName
      : undefined;
    rows.push({
      id: entry.id,
      module,
      enabled: entry.disabled !== true,
      phase: entry.fiber === undefined ? null : FIBER_PHASE[entry.fiber.state] ?? null,
      ...(serverName === undefined ? {} : { serverName }),
    });
  }
  const schemas = deps.toolSchemas();
  const mcp = rows
    .filter((row) => row.serverName !== undefined)
    .map((row) => {
      const server = row.serverName as string;
      const prefix = `mcp__${server}__`;
      return {
        server,
        phase: row.phase,
        tools: schemas
          .filter((tool) => tool.name.startsWith(prefix))
          .map((tool) => ({ name: tool.name, description: tool.description })),
      };
    });
  return { mcp, rows };
}

/**
 * Mount the panel routes: `exact GET /data/memory.json`,
 * `exact POST /data/memory/skill` (body `{name}`), and
 * `exact GET /data/plugins.json`.
 * @param webServer - the host webserver service, or a test recorder.
 * @param deps - the tree reads, from {@link panelDeps} or a test fake.
 */
export function registerPanelRoutes(webServer: RouteRegistrar, deps: PanelDeps): void {
  const send = (res: ServerResponse, status: number, body: unknown): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(typeof body === "string" ? body : JSON.stringify(body));
  };

  /** The shared GET shell: fence, then the read, errors mapped like /data's. */
  const get = (read: () => Promise<object> | object) =>
    async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isLoopbackHost(req.headers.host)) return send(res, 403, FORBIDDEN);
      try {
        return send(res, 200, { ok: true, ...(await read()) });
      } catch (err) {
        if (err instanceof StrategyError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "request failed" });
      }
    };

  webServer.register({ kind: "exact", path: "/data/memory.json", handler: get(() => memoryListing(deps)) });
  webServer.register({ kind: "exact", path: "/data/plugins.json", handler: get(() => pluginListing(deps)) });
  webServer.register({
    kind: "exact",
    path: "/data/memory/skill",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isLoopbackHost(req.headers.host)) return send(res, 403, FORBIDDEN);
      if (req.method !== "POST") return send(res, 405, { ok: false, error: "POST only" });
      try {
        let name: unknown;
        try {
          name = (JSON.parse(await readBody(req)) as Record<string, unknown>).name;
        } catch (err) {
          if (err instanceof StrategyError) throw err;
          throw new StrategyError(400, "body must be a JSON object");
        }
        return send(res, 200, { ok: true, ...(await skillDetail(deps, name)) });
      } catch (err) {
        if (err instanceof StrategyError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "request failed" });
      }
    },
  });
}
