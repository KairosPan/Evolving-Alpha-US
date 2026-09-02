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
 * The roster's connect/disconnect are the only writes to face state (its own
 * metadata file); `run` spawns one connected agent's own CLI as a child inside
 * a fenced working directory (the exec-channel block above EXEC_SPECS) — its
 * only face-side write is a tmpdir scratch for codex's `-o`, removed after the
 * run. Same-origin-fenced like every `/data` route.
 * @module
 */
import { execFile, spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, realpath, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { isAbsolute, join, relative, resolve as resolvePath } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Context } from "@deepseek-ai/cordis";
import { resolveDshHome } from "@deepseek-ai/dsh-home-paths";
import type { RouteRegistrar } from "./static.ts";
import { isJsonBody, isTrustedDataRequest } from "./data.ts";
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

/** What the connect page's "detected on this machine" auto-discovery probes
 * for: the coding-agent CLIs in circulation, by the bare name each installs
 * on PATH, with pretty labels. Suggestions only — an absent one fails its
 * probe instantly (ENOENT) and never shows; the connected roster is the
 * operator's, in `$DSH_HOME/face/agents.json`, and any valid bare name can be
 * connected by hand. Extend by adding a row. */
const KNOWN_AGENTS: ReadonlyArray<{ bin: string; label: string }> = [
  { bin: "claude", label: "Claude Code" },
  { bin: "codex", label: "Codex" },
  { bin: "hermes", label: "Hermes" },
  { bin: "openclaw", label: "OpenClaw" },
  { bin: "gemini", label: "Gemini CLI" },
  { bin: "aider", label: "Aider" },
  { bin: "goose", label: "Goose" },
  { bin: "opencode", label: "OpenCode" },
  { bin: "amp", label: "Amp" },
  { bin: "cursor-agent", label: "Cursor Agent" },
  { bin: "copilot", label: "GitHub Copilot CLI" },
  { bin: "qwen", label: "Qwen Code" },
  { bin: "droid", label: "Factory Droid" },
  { bin: "crush", label: "Crush" },
  { bin: "auggie", label: "Auggie" },
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
 * plus its auth reading when the agent has a status command, and whether the
 * face can DRIVE it (has an exec recipe — see {@link EXEC_SPECS}). */
export interface LocalAgentRow {
  bin: string;
  label: string;
  found: boolean;
  version?: string;
  auth?: AgentAuth;
  exec?: boolean;
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

/* ---------- the exec channel: drive a connected agent, one run per agent ------
 * The GREEN rows of docs/research/2026-09-01-agent-connection-survey.md: the
 * face spawns the operator's own UNMODIFIED CLI as a child, lets it perform
 * its own sign-in, and reads what it prints — it handles no credential at any
 * point, which is what keeps it on the permitted side of Anthropic's terms
 * (the survey quotes the line). Hermes has NO recipe on purpose: its default
 * provider config reuses those very tokens (the survey's RED rows), so it
 * stays a directory entry until the operator pins its provider. */

/** What one run reads out of the child's output. */
export interface RunParse {
  text: string;
  session?: string;
  isError: boolean;
  cost?: number;
  turns?: number;
}

/** One agent's exec recipe. The prompt ALWAYS travels on stdin, never as an
 * argument: an argument beginning with "-" would parse as a flag, and stdin
 * is the documented prompt channel for both CLIs. */
interface ExecSpec {
  /** Whether the CLI wants a scratch file for its final message (codex -o). */
  lastMessageFile: boolean;
  argv(resume: string | undefined, lastMessageFile: string | undefined): string[];
  parse(stdout: string, lastMessage: string | undefined): RunParse;
}

const EXEC_SPECS: Readonly<Record<string, ExecSpec>> = {
  claude: {
    /* -p headless · json = one result object · --restricted = no Bash/code
     * tools, no WebFetch, user/project settings ignored, file tools confined
     * to the working directory, bypassPermissions refused · --strict-mcp-config
     * = no MCP servers from any config (a strategy dir's .mcp.json included) ·
     * --disallowedTools Read(./.env*) = the workbench's key files stay unread
     * even when the run's directory is the root that holds them (it is
     * variadic, so it goes LAST). A one-shot the face fires is a READER: it
     * answers about the tree, it does not act on it. */
    lastMessageFile: false,
    argv: (resume) => [
      "-p", "--output-format", "json", "--restricted", "--strict-mcp-config",
      ...(resume === undefined ? [] : ["--resume", resume]),
      "--disallowedTools", "Read(./.env)", "Read(./.env.*)",
    ],
    parse: parseClaudeRun,
  },
  codex: {
    /* exec headless · --sandbox read-only PINNED (the operator's
     * ~/.codex/config.toml says workspace-write, and a recipe must not inherit
     * its posture from a file the face does not own) · --json = JSONL events
     * (the thread id rides thread.started) · -o = the final message to a
     * scratch file, the documented robust channel for the answer · "-" =
     * prompt from stdin · --skip-git-repo-check: a strategy dir need not be a
     * repo. */
    lastMessageFile: true,
    argv: (resume, out) => [
      "exec", ...(resume === undefined ? [] : ["resume"]),
      "--sandbox", "read-only", "--json", "--skip-git-repo-check",
      ...(out === undefined ? [] : ["-o", out]),
      ...(resume === undefined ? [] : [resume]), "-",
    ],
    parse: parseCodexRun,
  },
};

/** Whether the face can drive this agent (has an exec recipe). `hasOwn`, not
 * a lookup: a bin named `constructor` must read as no recipe, not as
 * `Object.prototype.constructor`. */
const hasExec = (bin: string): boolean => Object.hasOwn(EXEC_SPECS, bin);

/** Exactly a session/thread id both CLIs mint: a UUID. Anything else is
 * refused before it can reach an argv. */
const AGENT_SESSION_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const PROMPT_LIMIT = 32_000;
/** A run's body carries a prompt (the shared 4 KB reader is sized for ids):
 * JSON of {bin, prompt, cwd, resume}, where a CJK prompt is 3 UTF-8 bytes per
 * UTF-16 unit — sized so the prompt cap, not the body cap, is what a long
 * prompt hits. */
const RUN_BODY_LIMIT = 4 * PROMPT_LIMIT;
/** How long one run may take before it is killed — a coding agent reading a
 * tree and answering is minutes, not seconds. */
const RUN_TIMEOUT_MS = 600_000;
/** Cap on collected child output; past it the child is killed. */
const RUN_OUTPUT_LIMIT = 16 * 1024 * 1024;

/** Variables scrubbed from a child's environment (probes and runs alike, so
 * what the auth card observes is what the run gets). Deliberately INHERITED:
 * CLAUDE_CODE_OAUTH_TOKEN (the operator's own headless sign-in, minted by
 * `claude setup-token`), CLAUDE_CONFIG_DIR and CODEX_HOME (pointers to the
 * operator's own stores) — scrubbing those would make a run fail while the
 * auth card says signed in. The face never reads any of them. */
const SCRUBBED_ENV = [
  // credential overrides that outrank the CLI's own sign-in — a set key
  // silently moves the CLI off its subscription onto per-token billing
  "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY",
  // endpoint redirects — would carry the sign-in to a foreign gateway
  "ANTHROPIC_BASE_URL", "ANTHROPIC_CUSTOM_HEADERS", "OPENAI_BASE_URL",
  // cloud-provider billing switches
  "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
  // the workbench's own secrets — no business in a coding agent's child
  "APCA_API_KEY_ID", "APCA_API_SECRET_KEY", "DEEPSEEK_API_KEY",
] as const;

/** `process.env` (or `base`) minus {@link SCRUBBED_ENV}. */
export function scrubbedEnv(base: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...base };
  for (const key of SCRUBBED_ENV) delete env[key];
  return env;
}

/** `claude -p --output-format json` prints one result object:
 * {result, session_id, is_error, total_cost_usd, num_turns, …}; an error
 * variant (`subtype: "error_*"`) carries `errors[]` instead of `result`, and
 * the cause must reach the operator. Anything else comes back as raw text so
 * they still see what happened. */
export function parseClaudeRun(stdout: string): RunParse {
  const start = stdout.indexOf("{");
  const end = stdout.lastIndexOf("}");
  if (start !== -1 && end > start) {
    try {
      const obj = JSON.parse(stdout.slice(start, end + 1)) as Record<string, unknown>;
      const errors = Array.isArray(obj.errors) ? obj.errors.filter((e): e is string => typeof e === "string") : [];
      const subtype = typeof obj.subtype === "string" ? obj.subtype : "";
      return {
        text: typeof obj.result === "string" ? obj.result : errors.length > 0 ? errors.join("\n") : subtype,
        session: typeof obj.session_id === "string" ? obj.session_id : undefined,
        isError: obj.is_error === true || subtype.startsWith("error"),
        cost: typeof obj.total_cost_usd === "number" ? obj.total_cost_usd : undefined,
        turns: typeof obj.num_turns === "number" ? obj.num_turns : undefined,
      };
    } catch { /* not the documented shape — fall through to raw */ }
  }
  return { text: stdout.trim(), isError: false };
}

/** `codex exec --json -o <file>`: the answer is the scratch file (else the
 * agent_message items joined), the thread id rides the thread.started event.
 * Non-JSON lines around the events are skipped, not fatal. */
export function parseCodexRun(stdout: string, lastMessage: string | undefined): RunParse {
  let session: string | undefined;
  const messages: string[] = [];
  for (const line of stdout.split("\n")) {
    if (line.trim() === "") continue;
    let event: Record<string, unknown>;
    try {
      event = JSON.parse(line) as Record<string, unknown>;
    } catch {
      continue;
    }
    if (event.type === "thread.started" && typeof event.thread_id === "string") session = event.thread_id;
    const item = event.item;
    if (event.type === "item.completed" && item !== null && typeof item === "object") {
      const it = item as Record<string, unknown>;
      if (it.type === "agent_message" && typeof it.text === "string") messages.push(it.text);
    }
  }
  const fileText = lastMessage?.trim() ?? "";
  return { text: fileText !== "" ? fileText : messages.join("\n\n"), session, isError: false };
}

/** What a runner returns: exit code (null when the process never ran or was
 * killed), both streams, whether the face's timeout fired, and whether the
 * output cap cut the child off. */
export interface RunOutcome {
  code: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  truncated: boolean;
}

/** How long a SIGTERMed child gets to leave before SIGKILL. */
const KILL_GRACE_MS = 5_000;

/** The real runner: `spawn` (no shell), prompt written to stdin then closed,
 * output collected up to {@link RUN_OUTPUT_LIMIT}, killed at `timeoutMs`.
 * Three things a naive version gets wrong, and this one does not: a child
 * that traps SIGTERM is SIGKILLed after {@link KILL_GRACE_MS}; a child that
 * has EXITED while a grandchild still holds its pipes settles a second
 * later on `exit` rather than waiting on `close` forever; and the streams
 * are decoded through `setEncoding`, whose decoder holds a multibyte
 * sequence split across chunks (a CJK answer must not arrive as U+FFFD).
 * A spawn failure (the binary vanished) RESOLVES — never rejects — as a
 * null-code outcome with the reason on stderr, so the operator sees it. The
 * child dies with the face: a `process` 'exit' hook SIGTERMs it. */
export function defaultAgentRunner(): PanelDeps["runAgent"] {
  return (bin, argv, opts) => new Promise((resolve) => {
    const child = spawn(bin, argv, { cwd: opts.cwd, env: opts.env, stdio: ["pipe", "pipe", "pipe"] });
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    let stdout = "";
    let stderr = "";
    let timedOut = false;
    let truncated = false;
    let settled = false;
    /** @type {ReturnType<typeof setTimeout>[]} every timer this run armed */
    const timers: ReturnType<typeof setTimeout>[] = [];
    const later = (fn: () => void, ms: number): void => {
      const t = setTimeout(fn, ms);
      t.unref();
      timers.push(t);
    };
    const onFaceExit = (): void => { child.kill("SIGTERM"); };
    process.once("exit", onFaceExit);
    const finish = (code: number | null): void => {
      if (settled) return;
      settled = true;
      for (const t of timers) clearTimeout(t);
      process.off("exit", onFaceExit);
      resolve({ code, stdout, stderr, timedOut, truncated });
    };
    const terminate = (): void => {
      child.kill("SIGTERM");
      later(() => { if (!settled) child.kill("SIGKILL"); }, KILL_GRACE_MS);
    };
    later(() => {
      timedOut = true;
      terminate();
    }, opts.timeoutMs);
    child.stdout.on("data", (chunk: string) => {
      if (truncated) return;
      stdout += chunk;
      if (stdout.length > RUN_OUTPUT_LIMIT) {
        truncated = true;
        stdout = stdout.slice(0, RUN_OUTPUT_LIMIT);
        terminate();
      }
    });
    child.stderr.on("data", (chunk: string) => { stderr += chunk; });
    child.on("error", (err) => {
      stderr += `spawn failed: ${(err as { code?: string }).code ?? err.message}`;
      finish(null);
    });
    child.on("exit", (code) => {
      /* The pipes may outlive the process (a grandchild inherited them):
       * give 'close' a second to deliver the tail, then settle regardless. */
      later(() => {
        child.stdout.destroy();
        child.stderr.destroy();
        finish(code);
      }, 1_000);
    });
    child.on("close", (code) => finish(code));
    child.stdin.on("error", () => { /* the child closed stdin early; its output still decides */ });
    child.stdin.end(opts.input);
  });
}

/** Resolve a requested working directory INSIDE the workbench root, or the
 * root itself when none is asked for. Symlinks are followed on both sides so
 * a link out of the tree cannot pass the prefix test. */
async function resolveWorkdir(root: string, requested: unknown): Promise<string> {
  const rootReal = await realpath(root);
  if (requested === undefined || requested === null || requested === "") return rootReal;
  if (typeof requested !== "string") throw new StrategyError(400, "invalid cwd");
  let real: string;
  try {
    real = await realpath(resolvePath(rootReal, requested));
    if (!(await stat(real)).isDirectory()) throw new Error("not a directory");
  } catch {
    throw new StrategyError(400, "cwd is not a directory");
  }
  const rel = relative(rootReal, real);
  if (rel.startsWith("..") || isAbsolute(rel)) throw new StrategyError(400, "cwd outside the workbench");
  return real;
}

/** The face's answer to one run. */
export interface RunResult extends RunParse {
  bin: string;
  cwd: string;
  durationMs: number;
  code: number | null;
  timedOut: boolean;
  truncated: boolean;
  stderr?: string;
}

/** Runs in flight, keyed by bin — the host-side half of "one run per agent".
 * Module-level so the exported {@link runLocalAgent} carries it in tests. */
const running = new Set<string>();

/**
 * Drive one connected agent through its exec recipe, one task.
 *
 * Gates, in order: a valid name with a recipe (400), connected (409), a
 * non-empty prompt under {@link PROMPT_LIMIT} (400 / 413), a UUID session to
 * resume if any (400), a working directory inside the workbench (400), no run
 * already in flight for this agent (409). The prompt goes to the child on
 * stdin; the answer comes back parsed, with the exit code and the tail of
 * stderr when the run failed.
 */
export async function runLocalAgent(deps: PanelDeps, body: Record<string, unknown>): Promise<RunResult> {
  const { bin, prompt, cwd, resume } = body;
  if (typeof bin !== "string" || !AGENT_BIN_RE.test(bin) || !hasExec(bin)) {
    throw new StrategyError(400, "no exec channel for this agent");
  }
  const spec = EXEC_SPECS[bin];
  const meta = await readAgentsMeta(deps.home);
  if (!meta.connected.some((row) => row.bin === bin)) throw new StrategyError(409, "not connected");
  if (typeof prompt !== "string" || prompt.trim() === "") throw new StrategyError(400, "prompt required");
  if (prompt.length > PROMPT_LIMIT) throw new StrategyError(413, "prompt too long");
  if (resume !== undefined && (typeof resume !== "string" || !AGENT_SESSION_RE.test(resume))) {
    throw new StrategyError(400, "invalid session id");
  }
  const workdir = await resolveWorkdir(deps.cwd, cwd);
  if (running.has(bin)) throw new StrategyError(409, "a run is already in progress for this agent");
  running.add(bin);

  let scratch: string | undefined;
  const t0 = Date.now();
  try {
    let lastMessageFile: string | undefined;
    if (spec.lastMessageFile) {
      scratch = await mkdtemp(join(tmpdir(), "face-run-"));
      lastMessageFile = join(scratch, "last-message.md");
    }
    const out = await deps.runAgent(bin, spec.argv(resume, lastMessageFile), {
      cwd: workdir, input: prompt, env: scrubbedEnv(), timeoutMs: RUN_TIMEOUT_MS,
    });
    let lastMessage: string | undefined;
    if (lastMessageFile !== undefined) {
      try {
        lastMessage = await readFile(lastMessageFile, "utf8");
      } catch { /* the CLI wrote none — the events carry the answer */ }
    }
    const parsed = spec.parse(out.stdout, lastMessage);
    const isError = parsed.isError || out.code !== 0 || out.timedOut || out.truncated;
    /* Unlike data.ts (whose producer runs WITH the APCA keys, so a traceback
     * could echo them), this child's env is scrubbed, it is the operator's
     * own CLI, and its diagnostics are what the operator needs to see — so
     * the stderr TAIL is returned, error runs only. */
    const stderr = out.stderr.trim();
    return {
      ...parsed, bin, cwd: workdir, isError,
      durationMs: Date.now() - t0, code: out.code, timedOut: out.timedOut, truncated: out.truncated,
      ...(isError && stderr !== "" ? { stderr: stderr.slice(-2000) } : {}),
    };
  } finally {
    running.delete(bin);
    if (scratch !== undefined) await rm(scratch, { recursive: true, force: true });
  }
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
  /** The workbench repo root: skill discovery resolves project roots against
   * it, and a run's working directory must resolve inside it. */
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
  /** Spawn one connected agent's CLI with a recipe's argv, the prompt on
   * stdin, inside `cwd` with a scrubbed env; see {@link defaultAgentRunner}. */
  runAgent(
    bin: string,
    argv: string[],
    opts: { cwd: string; input: string; env: NodeJS.ProcessEnv; timeoutMs: number },
  ): Promise<RunOutcome>;
}

/** The real prober: `execFile` (no shell) of the bare bin name — resolved on
 * the face process's PATH, which is the operator's shell's — with a fixed
 * `--version` argv and a kill timeout. Every failure is the same `null`: a
 * missing binary, a hung one, and one that exits nonzero all read as "not
 * here", which is all the roster claims to know. */
export function defaultAgentProber(): PanelDeps["probeAgent"] {
  return (bin) => new Promise((resolve) => {
    execFile(bin, ["--version"], { timeout: 3_000, env: scrubbedEnv() }, (err, stdout) => {
      if (err) return resolve(null);
      const line = String(stdout).split("\n")[0]?.trim() ?? "";
      resolve(line === "" ? null : line.slice(0, 120));
    });
  });
}

/** The real auth prober: the bin's own status command through the same
 * no-shell `execFile`, folded by {@link authFromProbe}. Both streams are
 * folded together — `codex login status` reports on STDERR (measured
 * 2026-09-01), `claude auth status` on stdout. A status command that exits
 * nonzero still ANSWERED (signed-out CLIs often exit 1), so the fold sees
 * its output; only a spawn that produced nothing reads as null. */
export function defaultAuthProber(): PanelDeps["probeAuth"] {
  return (bin) => new Promise((resolve) => {
    const argv = Object.hasOwn(AUTH_PROBES, bin) ? AUTH_PROBES[bin] : undefined;
    if (argv === undefined) return resolve({ state: "unknown" });
    execFile(bin, [...argv], { timeout: 10_000, env: scrubbedEnv() }, (err, stdout, stderr) => {
      const out = `${String(stdout ?? "")}\n${String(stderr ?? "")}`;
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
    runAgent: defaultAgentRunner(),
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
    return { bin, label, found: version !== null, ...(version === null ? {} : { version }), auth, exec: hasExec(bin) };
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
  return { bin, label: labelFor(bin), found: true, version, auth, exec: hasExec(bin) };
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
 * Mount the panel routes — reads `GET /data/memory.json`, `/data/plugins.json`,
 * `/data/agents.json`; lookups and actions `POST /data/memory/skill` ({name}),
 * `/data/agents/connect` and `/disconnect` ({bin}), `/data/agents/run`
 * ({bin, prompt, cwd?, resume?}, its own body limit).
 * @param webServer - the host webserver service, or a test recorder.
 * @param deps - the tree reads and process seams, from {@link panelDeps} or a
 *   test fake.
 */
export function registerPanelRoutes(webServer: RouteRegistrar, deps: PanelDeps): void {
  const send = (res: ServerResponse, status: number, body: unknown): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(typeof body === "string" ? body : JSON.stringify(body));
  };

  /** The shared GET shell: fence, then the read, errors mapped like /data's. */
  const get = (read: () => Promise<object> | object) =>
    async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      try {
        return send(res, 200, { ok: true, ...(await read()) });
      } catch (err) {
        if (err instanceof StrategyError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "request failed" });
      }
    };

  /** The shared POST shell: fence, method gate, JSON body, error mapping —
   * the same shape sessions.ts uses. */
  const post = (act: (body: Record<string, unknown>) => Promise<object>, bodyLimit?: number) =>
    async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      if (req.method !== "POST") return send(res, 405, { ok: false, error: "POST only" });
      if (!isJsonBody(req)) return send(res, 415, { ok: false, error: "application/json only" });
      try {
        let body: Record<string, unknown>;
        try {
          const parsed: unknown = JSON.parse(await readBody(req, bodyLimit));
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
  webServer.register({
    kind: "exact",
    path: "/data/agents/run",
    handler: post(async (body) => ({ run: await runLocalAgent(deps, body) }), RUN_BODY_LIMIT),
  });
  /* The connect page's refresh: forget every cached probe and look again —
   * the operator just installed something and should not wait out the
   * minute. Same shape as the listing, so the page re-renders from it. */
  webServer.register({
    kind: "exact",
    path: "/data/agents/rescan",
    handler: post(async () => {
      probeCache.clear();
      authCache.clear();
      return await agentsListing(cachedDeps);
    }),
  });
}
