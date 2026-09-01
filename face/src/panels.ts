/** The master-rail panel feeds the host RPC surface cannot serve: agent
 * roster, memory, and plugin.
 *
 * The sidebar's four sections split by data source. `strategy` runs on
 * `session.*`/`workspace.*` and the face's own session routes; the `agent`
 * panel's MAIN-agent cards run on RPC the client can already call
 * (`host.describe`, `settings.describe`, `credentials.describe`), while its
 * LOCAL-agent roster — the coding agents connected beside Kairos — lives
 * here, because only the face process can ask the machine what is on its
 * PATH. The roster is OPERATOR-CURATED, not fixed: it starts empty, a
 * connect route probes a binary and adds it (`$DSH_HOME/face/agents.json`,
 * the same face-metadata home archived.json uses), and a disconnect route
 * removes it. The remaining two need what only the booted tree holds
 * in-process:
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
 * The only writes are the agent roster's two (connect/disconnect), and they
 * touch nothing but the face's own metadata file. Loopback-fenced like every
 * `/data` route.
 * @module
 */
import { execFile } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Context } from "@deepseek-ai/cordis";
import { resolveDshHome } from "@deepseek-ai/dsh-home-paths";
import type { RouteRegistrar } from "./static.ts";
import { isLoopbackHost } from "./data.ts";
import { readBody, StrategyError } from "./strategies.ts";
import { DSH_PIN } from "./version.ts";

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

/** Candidate suggestions for the connect page: coding CLIs worth probing for
 * when the operator has not connected them yet, with their pretty labels.
 * Suggestions only — the connected roster is the operator's, in
 * `$DSH_HOME/face/agents.json`, and any valid bare name can be connected. */
const KNOWN_AGENTS: ReadonlyArray<{ bin: string; label: string }> = [
  { bin: "claude", label: "Claude Code" },
  { bin: "codex", label: "Codex" },
  { bin: "hermes", label: "Hermes" },
  { bin: "openclaw", label: "OpenClaw" },
];

/** Exactly a connectable binary name: ONE bare token for a PATH lookup. No
 * separators of any kind, so the probe (`execFile(bin, ["--version"])`, no
 * shell) can never be steered to a path — this regex is what makes the
 * connect route safe to feed from a request body at all. */
const AGENT_BIN_RE = /^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$/;

/** Per-agent AUTH probes — the Hermes-style second half of the handshake.
 * Hermes connects Claude Code and Codex at the ACCOUNT level (its own OAuth
 * session per provider, stored in its own auth store, never sharing the
 * other CLI's); the face doesn't run OAuth itself, but it adopts the shape:
 * a connect verifies the agent is INSTALLED (answers `--version`) and asks
 * its own status command whether it is SIGNED IN — argv fixed per known bin,
 * never from a request. A bin without an entry here just reads "unknown". */
const AUTH_PROBES: Readonly<Record<string, readonly string[]>> = {
  claude: ["auth", "status"],
  codex: ["login", "status"],
  hermes: ["status"],
};

/** One agent's auth reading: signed in, signed out, or not knowable. */
export interface AgentAuth {
  state: "ok" | "none" | "unknown";
  detail?: string;
  account?: string;
}

/**
 * Fold one auth-probe answer into an {@link AgentAuth} — pure, so the
 * per-CLI parsing is testable against real captured output.
 * @param bin - which agent answered.
 * @param result - exit code + stdout, or `null` when the probe could not run.
 */
export function authFromProbe(bin: string, result: { code: number; stdout: string } | null): AgentAuth {
  if (result === null) return { state: "unknown" };
  const out = result.stdout.trim();
  if (bin === "claude") {
    // `claude auth status` prints JSON: {loggedIn, authMethod, email, ...}.
    try {
      const parsed = JSON.parse(out) as { loggedIn?: unknown; authMethod?: unknown; email?: unknown };
      if (parsed.loggedIn === true) {
        return {
          state: "ok",
          detail: typeof parsed.authMethod === "string" ? parsed.authMethod : undefined,
          account: typeof parsed.email === "string" ? parsed.email : undefined,
        };
      }
      if (parsed.loggedIn === false) return { state: "none" };
    } catch { /* not JSON — fall through to unknown */ }
    return { state: "unknown" };
  }
  if (bin === "codex") {
    // `codex login status`: "Logged in using ChatGPT" / "Not logged in".
    if (/not logged in/i.test(out)) return { state: "none" };
    if (result.code === 0 && /logged in/i.test(out)) {
      return { state: "ok", detail: out.split("\n")[0]?.trim().slice(0, 120) };
    }
    return { state: "unknown" };
  }
  if (bin === "hermes") {
    // `hermes status` is a config report, not a login gate: a configured
    // provider line is the closest thing to "signed in" it has.
    const provider = /Provider:\s*(\S[^\n]*)/.exec(out)?.[1]?.trim();
    if (result.code === 0 && provider !== undefined && provider !== "") {
      return { state: "ok", detail: `provider ${provider.slice(0, 60)}` };
    }
    return { state: "unknown" };
  }
  return { state: "unknown" };
}

/** The face's agent-roster file under the harness home, beside archived.json. */
const AGENTS_META = ["face", "agents.json"] as const;

/** The operator's connected roster, in connect order. */
export interface AgentsMeta {
  connected: { bin: string; label: string }[];
}

/** One probed local agent: present-with-version, or connected-but-silent,
 * plus its auth reading when the agent has a status command. */
export interface LocalAgentRow {
  bin: string;
  label: string;
  found: boolean;
  version?: string;
  auth?: AgentAuth;
}

/** @returns the stored roster; an absent, unreadable, or hand-mangled file
 * reads as best it can — a convenience, never a gate. */
export async function readAgentsMeta(home: string): Promise<AgentsMeta> {
  try {
    const parsed: unknown = JSON.parse(await readFile(join(home, ...AGENTS_META), "utf8"));
    if (parsed !== null && typeof parsed === "object") {
      const rows = (parsed as { connected?: unknown }).connected;
      if (Array.isArray(rows)) {
        return {
          connected: rows
            .filter((row): row is { bin: string; label?: unknown } =>
              row !== null && typeof row === "object"
              && typeof (row as { bin?: unknown }).bin === "string"
              && AGENT_BIN_RE.test((row as { bin: string }).bin))
            .map((row) => ({ bin: row.bin, label: typeof row.label === "string" ? row.label : row.bin })),
        };
      }
    }
  } catch { /* fall through to empty */ }
  return { connected: [] };
}

async function writeAgentsMeta(home: string, meta: AgentsMeta): Promise<void> {
  await mkdir(join(home, AGENTS_META[0]), { recursive: true });
  await writeFile(join(home, ...AGENTS_META), JSON.stringify(meta), "utf8");
}

/** The pretty label for a bin: the known map's, else the bin itself. */
const labelFor = (bin: string): string => KNOWN_AGENTS.find((k) => k.bin === bin)?.label ?? bin;

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
  /** The harness home holding the face's agents.json roster file. */
  home: string;
  /** Run one local-agent probe: `<bin> --version`, first stdout line, `null`
   * when the binary is absent or refuses. Every `bin` that reaches this has
   * passed {@link AGENT_BIN_RE} — a bare PATH token, never a path. */
  probeAgent(bin: string): Promise<string | null>;
  /** Ask one agent's own status command whether it is signed in — the
   * {@link AUTH_PROBES} argv for that bin; "unknown" when it has none. */
  probeAuth(bin: string): Promise<AgentAuth>;
}

/** The real prober: `execFile` (no shell) of the bare bin name — resolved on
 * the face process's PATH, which is the operator's shell's — with a fixed
 * `--version` argv and a kill timeout. Every failure is the same `null`: a
 * missing binary, a hung one, and one that exits nonzero all read as "not
 * here", which is all the roster claims to know. */
export function defaultAgentProber(): PanelDeps["probeAgent"] {
  return (bin) => new Promise((resolve) => {
    execFile(bin, ["--version"], { timeout: 3_000 }, (err, stdout) => {
      if (err) return resolve(null);
      const line = String(stdout).split("\n")[0]?.trim() ?? "";
      resolve(line === "" ? null : line.slice(0, 120));
    });
  });
}

/** The real auth prober: the bin's own status command through the same
 * no-shell `execFile`, folded by {@link authFromProbe}. A status command
 * that exits nonzero still ANSWERED (signed-out CLIs often exit 1), so the
 * fold sees its output; only a spawn that produced nothing reads as null. */
export function defaultAuthProber(): PanelDeps["probeAuth"] {
  return (bin) => new Promise((resolve) => {
    const argv = AUTH_PROBES[bin];
    if (argv === undefined) return resolve({ state: "unknown" });
    execFile(bin, [...argv], { timeout: 10_000 }, (err, stdout) => {
      const out = String(stdout ?? "");
      if (err !== null && out.trim() === "") return resolve(authFromProbe(bin, null));
      const code = err === null ? 0 : 1;
      resolve(authFromProbe(bin, { code, stdout: out }));
    });
  });
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
export function panelDeps(ctx: Context, cwd: string, home = resolveDshHome(undefined)): PanelDeps {
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
    home,
    probeAgent: defaultAgentProber(),
    probeAuth: defaultAuthProber(),
  };
}

/** A probe that never throws: a prober crash reads as "not here". */
async function probeSoft(deps: PanelDeps, bin: string): Promise<string | null> {
  try {
    return await deps.probeAgent(bin);
  } catch {
    return null;
  }
}

/** The auth probe's never-throws twin: a crash reads as "unknown". */
async function authSoft(deps: PanelDeps, bin: string): Promise<AgentAuth> {
  try {
    return await deps.probeAuth(bin);
  } catch {
    return { state: "unknown" };
  }
}

/** The agent roster: the main agent (Kairos on this dsh runtime), the
 * operator's CONNECTED local agents (probed, in connect order — one that
 * stopped answering stays listed as found:false rather than vanishing), and
 * the connect page's candidates (known suggestions that answer on this
 * machine and are not yet connected). The A2A section is the client's — a
 * declared placeholder with no host data yet. */
export async function agentsListing(deps: PanelDeps): Promise<{
  main: object;
  local: LocalAgentRow[];
  candidates: { bin: string; label: string; version: string }[];
}> {
  const meta = await readAgentsMeta(deps.home);
  const local = await Promise.all(meta.connected.map(async ({ bin, label }): Promise<LocalAgentRow> => {
    const [version, auth] = await Promise.all([probeSoft(deps, bin), authSoft(deps, bin)]);
    return { bin, label, found: version !== null, ...(version === null ? {} : { version }), auth };
  }));
  const connected = new Set(meta.connected.map((row) => row.bin));
  const candidates = (await Promise.all(KNOWN_AGENTS
    .filter((known) => !connected.has(known.bin))
    .map(async ({ bin, label }) => {
      const version = await probeSoft(deps, bin);
      return version === null ? null : { bin, label, version };
    })))
    .filter((row): row is { bin: string; label: string; version: string } => row !== null);
  return { main: { name: "Kairos", runtime: `dsh ${DSH_PIN}` }, local, candidates };
}

/** The connect handshake, Hermes-shaped: validate the name, then verify the
 * agent is INSTALLED (answers `--version` — nothing silent joins; a connect
 * is a verification, not a bookmark) and ask whether it is SIGNED IN (its
 * own status command). A signed-out agent still connects — installing the
 * roster row is the face's business, signing in is the operator's, in the
 * agent's own terminal — but the row says so. Idempotent on an
 * already-connected bin. 400 on a malformed name, 404 when nothing answers. */
export async function connectLocalAgent(deps: PanelDeps, bin: unknown): Promise<LocalAgentRow> {
  if (typeof bin !== "string" || !AGENT_BIN_RE.test(bin)) throw new StrategyError(400, "invalid binary name");
  const [version, auth] = await Promise.all([probeSoft(deps, bin), authSoft(deps, bin)]);
  if (version === null) throw new StrategyError(404, "binary did not answer on this machine");
  const meta = await readAgentsMeta(deps.home);
  if (!meta.connected.some((row) => row.bin === bin)) {
    meta.connected.push({ bin, label: labelFor(bin) });
    await writeAgentsMeta(deps.home, meta);
  }
  return { bin, label: labelFor(bin), found: true, version, auth };
}

/** Remove one bin from the roster. 400 on a malformed name, 404 when it was
 * not connected. The binary itself is untouched — this is the face's list. */
export async function disconnectLocalAgent(deps: PanelDeps, bin: unknown): Promise<AgentsMeta> {
  if (typeof bin !== "string" || !AGENT_BIN_RE.test(bin)) throw new StrategyError(400, "invalid binary name");
  const meta = await readAgentsMeta(deps.home);
  if (!meta.connected.some((row) => row.bin === bin)) throw new StrategyError(404, "not connected");
  const next = { connected: meta.connected.filter((row) => row.bin !== bin) };
  await writeAgentsMeta(deps.home, next);
  return next;
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

  /** The shared POST shell: fence, method gate, JSON body, error mapping —
   * the same shape sessions.ts uses. */
  const post = (act: (body: Record<string, unknown>) => Promise<object>) =>
    async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isLoopbackHost(req.headers.host)) return send(res, 403, FORBIDDEN);
      if (req.method !== "POST") return send(res, 405, { ok: false, error: "POST only" });
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
        return send(res, 200, { ok: true, ...(await act(body)) });
      } catch (err) {
        if (err instanceof StrategyError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "request failed" });
      }
    };

  /* Probes are answered from a per-bin one-minute cache: flipping panels is
   * never a spawn storm, and a version bump shows on the next-but-soon open.
   * The CONNECT handshake deliberately probes FRESH (a binary installed ten
   * seconds ago must connect now, not after the cache turns) and then updates
   * the cache with what it learned. */
  const probeCache = new Map<string, { at: number; version: string | null }>();
  const authCache = new Map<string, { at: number; auth: AgentAuth }>();
  const cachedDeps: PanelDeps = {
    ...deps,
    probeAgent: async (bin) => {
      const hit = probeCache.get(bin);
      if (hit !== undefined && Date.now() - hit.at < 60_000) return hit.version;
      let version: string | null;
      try {
        version = await deps.probeAgent(bin);
      } catch {
        version = null;
      }
      probeCache.set(bin, { at: Date.now(), version });
      return version;
    },
    probeAuth: async (bin) => {
      const hit = authCache.get(bin);
      if (hit !== undefined && Date.now() - hit.at < 60_000) return hit.auth;
      let auth: AgentAuth;
      try {
        auth = await deps.probeAuth(bin);
      } catch {
        auth = { state: "unknown" };
      }
      authCache.set(bin, { at: Date.now(), auth });
      return auth;
    },
  };

  webServer.register({ kind: "exact", path: "/data/memory.json", handler: get(() => memoryListing(deps)) });
  webServer.register({ kind: "exact", path: "/data/plugins.json", handler: get(() => pluginListing(deps)) });
  webServer.register({ kind: "exact", path: "/data/agents.json", handler: get(() => agentsListing(cachedDeps)) });
  webServer.register({
    kind: "exact",
    path: "/data/memory/skill",
    handler: post(async (body) => await skillDetail(deps, body.name)),
  });
  webServer.register({
    kind: "exact",
    path: "/data/agents/connect",
    handler: post(async (body) => {
      const agent = await connectLocalAgent(deps, body.bin);
      probeCache.set(agent.bin, { at: Date.now(), version: agent.version ?? null });
      if (agent.auth !== undefined) authCache.set(agent.bin, { at: Date.now(), auth: agent.auth });
      return { agent };
    }),
  });
  webServer.register({
    kind: "exact",
    path: "/data/agents/disconnect",
    handler: post(async (body) => await disconnectLocalAgent(deps, body.bin)),
  });
}
