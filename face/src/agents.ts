/** The agent tools: a connected local CLI becomes `agent_<bin>` in the dsh
 * tree, and Kairos calls it from a channel session.
 *
 * Split out of panels.ts because that module had grown to hold four unrelated
 * jobs; the per-channel roster check lives here, on `execute`.
 *
 * The GREEN rows of docs/research/2026-09-01-agent-connection-survey.md: the
 * face spawns the operator's own UNMODIFIED CLI as a child, lets it perform
 * its own sign-in, and handles no credential at any point. Hermes has NO
 * recipe on purpose - its default provider config reuses those very tokens.
 * @module
 */
import { spawn } from "node:child_process";
import { mkdtemp, readFile, realpath, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { HttpError } from "./http.ts";
import { isAgentBin, readAgentsMeta, type PanelDeps } from "./panels.ts";
import { readRosters } from "./roster.ts";

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
     * variadic, so it goes LAST). A call from Kairos is a READER: it answers
     * about the tree, it does not act on it. */
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
export const hasExec = (bin: string): boolean => Object.hasOwn(EXEC_SPECS, bin);

/** The dsh tool name a connected agent is reachable by. Tool names are
 * `[A-Za-z0-9_-]`; a bin may carry `.` or `+`, which fold to `_`. */
export const toolNameFor = (bin: string): string => `agent_${bin.replace(/[^A-Za-z0-9_-]/g, "_")}`;

/** Exactly a session/thread id both CLIs mint: a UUID. Anything else is
 * refused before it can reach an argv. */
const AGENT_SESSION_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const PROMPT_LIMIT = 32_000;
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
 * the cause must reach the caller. Anything else comes back as raw text so
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

/** What a runner is asked for: where, what to feed on stdin, which env, how
 * long, and the caller's cancellation (Kairos's tool call being aborted). */
export interface RunOptions {
  cwd: string;
  input: string;
  env: NodeJS.ProcessEnv;
  timeoutMs: number;
  signal?: AbortSignal;
}

/** How long a SIGTERMed child gets to leave before SIGKILL. */
const KILL_GRACE_MS = 5_000;

/** The real runner: `spawn` (no shell), prompt written to stdin then closed,
 * output collected up to {@link RUN_OUTPUT_LIMIT}, killed at `timeoutMs` or
 * when the caller's signal aborts. Three things a naive version gets wrong,
 * and this one does not: a child that traps SIGTERM is SIGKILLed after
 * {@link KILL_GRACE_MS}; a child that has EXITED while a grandchild still
 * holds its pipes settles a second later on `exit` rather than waiting on
 * `close` forever; and the streams are decoded through `setEncoding`, whose
 * decoder holds a multibyte sequence split across chunks (a CJK answer must
 * not arrive as U+FFFD). A spawn failure (the binary vanished) RESOLVES —
 * never rejects — as a null-code outcome with the reason on stderr, so the
 * caller sees it. The child dies with the face: a `process` 'exit' hook
 * SIGTERMs it. */
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
    const timers: ReturnType<typeof setTimeout>[] = [];
    const later = (fn: () => void, ms: number): void => {
      const t = setTimeout(fn, ms);
      t.unref();
      timers.push(t);
    };
    const onFaceExit = (): void => { child.kill("SIGTERM"); };
    process.once("exit", onFaceExit);
    const terminate = (): void => {
      child.kill("SIGTERM");
      later(() => { if (!settled) child.kill("SIGKILL"); }, KILL_GRACE_MS);
    };
    const onAbort = (): void => terminate();
    opts.signal?.addEventListener("abort", onAbort, { once: true });
    const finish = (code: number | null): void => {
      if (settled) return;
      settled = true;
      for (const t of timers) clearTimeout(t);
      process.off("exit", onFaceExit);
      opts.signal?.removeEventListener("abort", onAbort);
      resolve({ code, stdout, stderr, timedOut, truncated });
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
    if (opts.signal?.aborted) terminate();
    child.stdin.end(opts.input);
  });
}

/** The directory a run executes in: the calling session's cwd when it still
 * is a directory, else the workbench root. Not a fence — the cwd comes from
 * the SESSION (trusted, never a request), and dsh's own sandbox bounds what a
 * session may touch; this only keeps a vanished directory from failing the
 * spawn. */
async function resolveRunDir(root: string, requested: unknown): Promise<string> {
  if (typeof requested === "string" && requested !== "") {
    try {
      const real = await realpath(requested);
      if ((await stat(real)).isDirectory()) return real;
    } catch { /* fall through to the root */ }
  }
  return realpath(root);
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

/** One request to drive an agent through its recipe. */
export interface RunRequest {
  bin: unknown;
  prompt: unknown;
  cwd?: unknown;
  resume?: unknown;
  signal?: AbortSignal;
}

/** Runs in flight, keyed by bin — one run per agent at a time. Module-level so
 * the exported {@link runAgentRecipe} carries it in tests. */
const running = new Set<string>();

/**
 * Drive one agent through its exec recipe, one task.
 *
 * Gates, in order: a valid name with a recipe (400), a non-empty prompt under
 * {@link PROMPT_LIMIT} (400 / 413), a UUID session to resume if any (400), no
 * run already in flight for this agent (409). The prompt goes to the child on
 * stdin; the answer comes back parsed, with the exit code and the tail of
 * stderr when the run failed. Whether the agent is CONNECTED is not checked
 * here: the tool that calls this exists only while it is.
 */
export async function runAgentRecipe(deps: PanelDeps, req: RunRequest): Promise<RunResult> {
  const { bin, prompt, resume } = req;
  if (!isAgentBin(bin) || !hasExec(bin)) throw new HttpError(400, "no exec channel for this agent");
  const spec = EXEC_SPECS[bin];
  if (typeof prompt !== "string" || prompt.trim() === "") throw new HttpError(400, "prompt required");
  if (prompt.length > PROMPT_LIMIT) throw new HttpError(413, "prompt too long");
  if (resume !== undefined && (typeof resume !== "string" || !AGENT_SESSION_RE.test(resume))) {
    throw new HttpError(400, "invalid session id");
  }
  const workdir = await resolveRunDir(deps.cwd, req.cwd);
  if (running.has(bin)) throw new HttpError(409, "a run is already in progress for this agent");
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
      cwd: workdir, input: prompt, env: scrubbedEnv(), timeoutMs: RUN_TIMEOUT_MS, signal: req.signal,
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
     * own CLI, and its diagnostics are what the caller needs to see — so the
     * stderr TAIL is returned, error runs only. */
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

/** What the face reads off dsh's ToolRunContext (dsh-tools 0.1.1-rc.2
 * lib/types/index.d.ts:196-300): the calling session's directory and the
 * caller's cancellation. Stated structurally so the face neither declares
 * dsh-tools as a dependency nor drifts silently. */
export interface AgentToolExec {
  agent?: { session: { header: { cwd?: string } } };
  signal: AbortSignal;
}

/** The shape `ctx.tools.register` takes (dsh-tools ToolDefinition,
 * lib/types/index.d.ts:106-173), stated structurally for the same reason;
 * the registry validates the real contract at registration. */
export interface AgentToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  output: {
    schema: Record<string, unknown>;
    render(args: unknown, value: unknown): { type: "text"; text: string }[];
  };
  timeoutMs: number;
  execute(args: unknown, exec: AgentToolExec): Promise<unknown>;
  presentCall(args: unknown): { card: "generic"; title: string; kind: "read"; rawInput?: unknown };
}

/** The value one agent tool returns — exactly what `output.schema` declares. */
export interface AgentToolValue {
  text: string;
  session?: string;
  isError: boolean;
  cost?: number;
  turns?: number;
  durationMs: number;
}

/**
 * The tool Kairos gets for one connected agent. `execute` first checks the
 * calling session's channel roster (see the module docstring), then runs the
 * recipe in the CALLING SESSION's directory (a strategy's workspace),
 * forwards the call's cancellation to the child, and throws on a failed run
 * so the registry hands Kairos an error result with the cause. The rendered
 * text carries the CLI's session id so Kairos can continue the conversation.
 * @param deps - the process seams.
 * @param bin - a connected bin with a recipe.
 * @param label - its pretty label, for the description and the card title.
 */
export function agentToolDefinition(deps: PanelDeps, bin: string, label: string): AgentToolDefinition {
  const name = toolNameFor(bin);
  return {
    name,
    description:
      `Ask the operator's locally installed ${label} (${bin}) a question about the current working tree. ` +
      "It runs as itself, signed in with the operator's own account, in the session's working directory. " +
      "READ-ONLY: it can inspect files but cannot run commands or edit anything — use it for a second opinion, " +
      "a survey of the tree, or a review. Pass `resume` with the session id from a previous answer to continue " +
      "that same conversation.",
    parameters: {
      type: "object",
      properties: {
        prompt: { type: "string", description: `The task or question for ${label}.` },
        resume: { type: "string", description: "Session id from a previous answer, to continue that conversation." },
      },
      required: ["prompt"],
      additionalProperties: false,
    },
    output: {
      schema: {
        type: "object",
        properties: {
          text: { type: "string" },
          session: { type: "string" },
          isError: { type: "boolean" },
          cost: { type: "number" },
          turns: { type: "number" },
          durationMs: { type: "number" },
        },
        required: ["text", "isError", "durationMs"],
        additionalProperties: false,
      },
      render(_args, value) {
        const v = value as AgentToolValue;
        const tail = v.session === undefined ? "" : `\n\n[${label} session ${v.session} — pass resume="${v.session}" to continue this conversation]`;
        return [{ type: "text", text: `${v.text}${tail}` }];
      },
    },
    timeoutMs: RUN_TIMEOUT_MS,
    async execute(args, exec) {
      const cwd = exec.agent?.session.header.cwd;
      /* The channel's roster. NOT a fence: dsh registers tools tree-wide with
       * no per-session scope, and a shell turn can invoke the same CLI
       * directly. This refusal is a MENU - it states the operator's intent
       * and keeps an off-roster agent out of the way. The message IS the
       * roster contract, so it names the channel and the current set; that
       * is how the model learns the roster without a prompt that could
       * drift from the operator's file. A session in NO channel (`null`)
       * fails OPEN — there is no roster to consult, and tools are tree-wide
       * anyway, so refusing there would be a behaviour change with no
       * safety story. */
      const channel = await deps.channelFor(cwd);
      if (channel !== null) {
        /* `readRosters`, not `rosterFor`: the two ways this can come back
         * empty are different facts and need different messages. A file
         * that fails to PARSE is an operator-side break - repair it. A file
         * that parses fine but simply has no entry for this workspace yet
         * is the ORDINARY state of a channel the reconcile hasn't seeded
         * (created straight through the registry, before /data/channels.json
         * ever loaded) - nothing is broken, there is just nothing to read
         * yet, and it fills in on its own once the channel list loads. */
        const { rosters, corrupt } = await readRosters(deps.home);
        if (corrupt) {
          throw new Error(`the channel roster is unreadable, so ${label} is refused here; repair ${join(deps.home, "face", "channels.json")}`);
        }
        if (!Object.hasOwn(rosters, channel.workspaceId)) {
          throw new Error(`this channel has no roster yet, so ${label} is refused here; it gets one the first time the channel list loads, and the operator sets it on the channel page.`);
        }
        const roster = rosters[channel.workspaceId].agents;
        if (!roster.includes(bin)) {
          throw new Error(`${label} is not on this channel's roster. Channel "${channel.name}" currently offers: ${roster.length === 0 ? "(none)" : roster.join(", ")}. The operator adds agents on the channel page.`);
        }
      }
      const a = (args !== null && typeof args === "object" ? args : {}) as Record<string, unknown>;
      const run = await runAgentRecipe(deps, {
        bin, prompt: a.prompt, resume: a.resume,
        cwd, signal: exec.signal,
      });
      if (run.isError) {
        throw new Error(run.text !== "" ? run.text : run.stderr ?? (run.timedOut ? `${label} timed out` : `${label} reported an error`));
      }
      const value: AgentToolValue = { text: run.text, isError: false, durationMs: run.durationMs };
      if (run.session !== undefined) value.session = run.session;
      if (run.cost !== undefined) value.cost = run.cost;
      if (run.turns !== undefined) value.turns = run.turns;
      return value;
    },
    presentCall(args) {
      const prompt = (args as { prompt?: unknown } | null)?.prompt;
      return {
        card: "generic",
        title: `Ask ${label}`,
        kind: "read",
        rawInput: typeof prompt === "string" ? prompt.slice(0, 200) : undefined,
      };
    },
  };
}

/** Registered agent tools by bin, with their disposers — the live half of
 * "connected ⇒ callable". */
export type AgentToolRegistry = Map<string, () => void>;

/**
 * Make the registered tools match the roster: register every connected agent
 * with a recipe that is not registered yet, dispose every registered one no
 * longer connected. Idempotent; called at boot and after every roster write.
 * @returns which bins changed, for the caller's log line.
 */
export async function syncAgentTools(deps: PanelDeps, registry: AgentToolRegistry): Promise<{ added: string[]; removed: string[] }> {
  const meta = await readAgentsMeta(deps.home);
  const wanted = new Map(meta.connected.filter((row) => hasExec(row.bin)).map((row) => [row.bin, row.label]));
  const added: string[] = [];
  const removed: string[] = [];
  for (const [bin, dispose] of [...registry]) {
    if (wanted.has(bin)) continue;
    dispose();
    registry.delete(bin);
    removed.push(bin);
  }
  for (const [bin, label] of wanted) {
    if (registry.has(bin)) continue;
    registry.set(bin, deps.registerTool(agentToolDefinition(deps, bin, label)));
    added.push(bin);
  }
  return { added, removed };
}
