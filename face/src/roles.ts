// face/src/roles.ts
/** The role library: one directory per role under `roles/<id>/`.
 *
 * A role is a one-shot child Gravit hands a bounded piece of work. Its directory holds
 * `ROLE.md` (the child's persona, trimmed) and `role.yml` (`name`; `description`, the
 * one-line summary Gravit reads when it chooses a role; `allow`, the child's tools; an
 * optional `model` route). The operator owns both files and Gravit never writes here.
 * {@link readRoles} reads and validates the directory and returns plain data; `_template`
 * is the copy source and is never a role.
 *
 * `allow` names are EXACT, and a wildcard is refused where the file is read. The dsh spawn
 * backend applies a child's tool filter inside the child's creation window:
 * `applyChildComposition` (installed dsh-subagent `lib/index.js`) calls the child context's
 * `tools.restrict(filter)`, and `restrict()` (installed dsh-tools `lib/index.js`) checks
 * every name by set membership against `restrictableNames`, the tools the child inherits.
 * There is no glob and no prefix match; a name outside the set throws
 * `tools.restrict() names unknown global tool ...` (spec §11.1 (a)).
 *
 * Whether a named tool exists is therefore a fact about the tree at the moment the role is
 * CALLED - an MCP tool exists as `mcp__<server>__<raw>` under the server name the installed
 * profile mounts - not about this directory, so nothing here checks it. A missing tool fails
 * that delegation (no child is created and `restrict()`'s error names the tool), never the
 * face's boot.
 *
 * A role never carries what a delegated child cannot use or must not hold: a tool that needs
 * a human, the open web, delegation, the cycle's goal and todo bookkeeping, the reserved PTC
 * transport `run_code`, the account and order tools under any server name, the AKShare tools
 * (the `NEVER` table, with the reason for each). The job tools are a bash role's own: a
 * command that outruns the executor's default timeout moves to a background job the child
 * owns, which it reads with `job_output` and stops with `job_kill`, and which is cancelled
 * when the child is. The reader refuses a never-carried `allow` entry where it reads the
 * file, an entry listed twice, a role id whose tool name would pass {@link TOOL_NAME_MAX}
 * characters, and an entry under `roles/` it would otherwise drop without a word: a symbolic
 * link, or a directory whose name is not an id.
 *
 * {@link gravitRows} renders the roles as Gravit's composition: the `gravit` plugin row,
 * whose config carries each role's tool and summary for the `gravit:roles` section
 * (plugins/gravit.js), then one `@deepseek-ai/dsh-tool-subagent` row per role.
 * {@link renderGravitComposition} dumps those rows as `bots/gravit/agent.cordis.yml`, a
 * GENERATED mirror (`cd face && npm run render:roles`); tests/roles.test.ts fails while the
 * committed file differs from the render.
 * @module
 */
import { readdirSync, readFileSync, type Dirent } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { entryListSchema } from "@deepseek-ai/cordis-plugin-include";
import type { Config as ToolSubagentConfig } from "@deepseek-ai/dsh-tool-subagent";
import { dump, load } from "js-yaml";
import type { PresetRow } from "./bot-presets.ts";
import { MODEL_ROUTE_RE } from "./bots.ts";
import { GRAVIT_PLUGIN_RELATIVE } from "./overlay.ts";

/** The repository's role directory - where the face reads the role library from.
 *  Module-relative, as `BOTS_ROOT` is. */
export const ROLES_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "roles");
/** The copy source: never a role. */
export const ROLE_TEMPLATE = "_template";
/** A role id, which is its directory name: the grammar of a bot id (`BOT_ID_RE`). */
export const ROLE_ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
/** One `allow` entry: a host tool name or `mcp__<server>__<raw>`. Letters, digits, `_`, `-`;
 *  no `*`, since a name is matched exactly (module header). */
export const TOOL_NAME_RE = /^[A-Za-z0-9_-]+$/;
/** The longest `description`, in characters: the one-line summary Gravit reads. */
export const SUMMARY_MAX = 300;
/** The largest `ROLE.md`, in bytes as `wc -c` counts them: it becomes a section of the
 *  child's system prompt. */
export const ROLE_MD_MAX_BYTES = 2000;
/** The longest tool name Gravit may be handed, in characters: a model API caps a function
 *  name (64 is the common cap), and {@link ROLE_ID_RE} admits ids of 64 characters, so
 *  `role_` plus an id can pass it. */
export const TOOL_NAME_MAX = 64;

/** What a role never carries, and why: for each reason, the exact `names`, the name `prefixes`,
 *  and the `rawNames` it covers - a raw MCP name refused bare and under ANY server
 *  (`entry === raw` or `entry.endsWith("__" + raw)`), the match src/orders.ts `isOrderTool`
 *  applies to the order tools, so a server the operator mounts under another name than
 *  `alpaca-kit` cannot slip an account or order tool in. {@link readMeta} refuses an `allow`
 *  entry that matches, with the reason in the message. The shipped roles obey it, and
 *  tests/roles.test.ts holds an independent copy of the names. */
const NEVER: ReadonlyArray<{ what: string; because: string; names: readonly string[]; prefixes: readonly string[]; rawNames: readonly string[] }> = [
  { what: "a tool that needs a human",
    because: "a delegated child has no human to ask or to review a plan (dsh refuses ask_user_question to it with DELEGATED_CALLER); a role that needs the operator says so in its report",
    names: ["ask_user_question", "exit_plan_mode"], prefixes: [], rawNames: [] },
  { what: "a web tool",
    because: "the open web carries no as-of guard, and a role reads the market only through the PIT channels",
    names: ["web_search", "web_fetch"], prefixes: [], rawNames: [] },
  { what: "a delegation tool",
    because: "Gravit alone delegates; a role is one hand, not a team",
    names: ["subagent", "subagent_fork", "send_message", "interrupt_agent", "list_agents", "workflow", "ralph", "dispatch"],
    prefixes: ["role_", "agent_"], rawNames: [] },
  { what: "a goal or todo tool",
    because: "Gravit tracks the goal and the todos; a role is one bounded call",
    names: ["create_goal", "get_goal", "update_goal", "todo_write"], prefixes: [], rawNames: [] },
  { what: "the PTC transport",
    because: "run_code is the reserved PTC mode presentation transport, which tools.restrict() refuses to name, so every delegation would fail; name the end-capability tools instead",
    names: ["run_code"], prefixes: [], rawNames: [] },
  { what: "an account or order tool",
    because: "orders stay behind the two order gates, and a role has no reason to read the account",
    names: [], prefixes: [], rawNames: ["account", "positions", "orders", "place_order", "cancel_order"] },
  { what: "an AKShare tool",
    because: "the AKShare tools carry no point-in-time guard and are never backtest evidence",
    names: [], prefixes: ["mcp__akshare__"], rawNames: [] },
];

/** Why a role may not carry `entry`, as the end of a refusal; `undefined` when it may. */
function neverCarries(entry: string): string | undefined {
  const rule = NEVER.find((candidate) => candidate.names.includes(entry)
    || candidate.prefixes.some((prefix) => entry.startsWith(prefix))
    || candidate.rawNames.some((raw) => entry === raw || entry.endsWith(`__${raw}`)));
  return rule === undefined ? undefined : `a role never carries ${rule.what}: ${rule.because}`;
}

const PERSONA_FILE = "ROLE.md";
const META_FILE = "role.yml";

/** One role, as read from `roles/<id>/`. */
export interface RoleFile {
  /** The directory name; matches {@link ROLE_ID_RE}. */
  id: string;
  /** The tool Gravit calls: {@link toolNameFor}(id). */
  tool: string;
  name: string;
  /** The one-line summary Gravit reads, at most {@link SUMMARY_MAX} characters. */
  description: string;
  /** `ROLE.md`, trimmed: the child's persona. */
  persona: string;
  /** Exact tool names, as written in `role.yml`. */
  allow: string[];
  /** The `<provider>/<model>` route the role's children run on, when `role.yml` names one. */
  model?: string;
}

/** The tool Gravit sees for a role id: `role_` plus the id with `-` as `_`
 *  (`data-check` is `role_data_check`). */
export function toolNameFor(id: string): string {
  return "role_" + id.replace(/-/g, "_");
}

const messageOf = (error: unknown): string => error instanceof Error ? error.message : String(error);

/** Every refusal opens with the absolute path of the file (or directory) it is about. */
const refusal = (path: string, reason: string, cause?: unknown): Error =>
  new Error(`${path}: ${reason}`, cause === undefined ? undefined : { cause });

function readBytes(file: string): Buffer {
  try {
    return readFileSync(file);
  } catch (error) {
    const missing = (error as NodeJS.ErrnoException).code === "ENOENT";
    throw refusal(file, missing ? "missing" : `cannot be read: ${messageOf(error)}`, error);
  }
}

/** `ROLE.md`: refused when empty, over {@link ROLE_MD_MAX_BYTES}, or carrying `{{`. */
function readPersona(file: string): string {
  const bytes = readBytes(file);
  const persona = bytes.toString("utf8").trim();
  if (persona === "") throw refusal(file, "the persona is empty");
  if (bytes.length > ROLE_MD_MAX_BYTES) throw refusal(file, `is ${bytes.length} bytes; the limit is ${ROLE_MD_MAX_BYTES}`);
  if (persona.includes("{{")) throw refusal(file, "contains '{{' - the system prompt is a strict template with no escape");
  return persona;
}

/** A `name` or `description`: a string, trimmed. Anything else, or blank, is missing. */
const textOf = (value: unknown): string | undefined =>
  typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;

/** `role.yml`. Keys the face does not know are ignored. */
function readMeta(file: string): Pick<RoleFile, "name" | "description" | "allow" | "model"> {
  const source = readBytes(file).toString("utf8");
  let doc: unknown;
  try {
    doc = load(source);
  } catch (error) {
    /* First line only: js-yaml appends a multi-line code frame. */
    throw refusal(file, `is not valid YAML: ${messageOf(error).replace(/\n[\s\S]*$/, "")}`, error);
  }
  if (typeof doc !== "object" || doc === null || Array.isArray(doc)) throw refusal(file, "must be a mapping with name, description and allow");
  const fields = doc as Record<string, unknown>;

  const name = textOf(fields.name);
  if (name === undefined) throw refusal(file, "name is missing or blank");
  const description = textOf(fields.description);
  if (description === undefined) throw refusal(file, "description is missing or blank");
  /* The summary is one line: `rolesText` (plugins/gravit.js) emits one bullet per role. */
  if (/[\r\n]/.test(description)) throw refusal(file, "description must be one line");
  if (description.length > SUMMARY_MAX) throw refusal(file, `description is ${description.length} characters; the limit is ${SUMMARY_MAX}`);

  const listed = fields.allow;
  if (!Array.isArray(listed) || listed.length === 0) throw refusal(file, "allow must be a non-empty list of exact tool names");
  /* Entries are kept exactly as written: no trimming, so a blank one fails the grammar. A name
   * listed twice is refused: harmless to `restrict()`, which takes a set, but a typo'd list. */
  const seen = new Set<string>();
  const allow = listed.map((entry: unknown, index: number): string => {
    if (typeof entry !== "string") throw refusal(file, `allow entry ${index + 1} is not a string`);
    if (entry.includes("*")) throw refusal(file, `allow entry ${JSON.stringify(entry)}: wildcards are not accepted; name the exact tool, e.g. mcp__alpaca-kit__screen`);
    if (!TOOL_NAME_RE.test(entry)) throw refusal(file, `allow entry ${JSON.stringify(entry)} is not a tool name (letters, digits, _ and - only)`);
    const never = neverCarries(entry);
    if (never !== undefined) throw refusal(file, `allow entry ${JSON.stringify(entry)}: ${never}`);
    if (seen.has(entry)) throw refusal(file, `allow entry ${JSON.stringify(entry)} is listed twice`);
    seen.add(entry);
    return entry;
  });

  const route = fields.model;
  let model: string | undefined;
  if (route !== undefined) {
    if (typeof route !== "string" || !MODEL_ROUTE_RE.test(route)) {
      throw refusal(file, `model must be a <provider>/<model> route, e.g. deepseek-official/deepseek-v4-flash (got ${typeof route === "string" ? JSON.stringify(route) : "a non-string"})`);
    }
    model = route;
  }
  return { name, description, allow, ...(model === undefined ? {} : { model }) };
}

function readRole(root: string, id: string): RoleFile {
  const dir = join(root, id);
  const tool = toolNameFor(id);
  if (tool.length > TOOL_NAME_MAX) throw refusal(dir, `the tool name ${tool} is ${tool.length} characters; the limit is ${TOOL_NAME_MAX} - shorten the directory name`);
  /* ROLE.md first, so its refusals come before role.yml's. */
  return { id, tool, persona: readPersona(join(dir, PERSONA_FILE)), ...readMeta(join(dir, META_FILE)) };
}

/** The role ids under `root`, sorted. A symbolic link, whatever its name, and a directory
 *  whose name is not a {@link ROLE_ID_RE} id are refused with their path: the reader would
 *  otherwise drop a role the operator meant to ship without a word. Any other hidden entry
 *  (a leading `.`), `_template` and a plain file are skipped. Entries are walked in name
 *  order, so the first refusal is the same on every filesystem. */
function listRoleIds(root: string): string[] {
  let entries: Dirent[];
  try {
    entries = readdirSync(root, { withFileTypes: true });
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    throw refusal(root, code === "ENOENT" ? "the roles directory is missing" : code === "ENOTDIR" ? "is not a directory" : `cannot be listed: ${messageOf(error)}`, error);
  }
  const ids: string[] = [];
  for (const entry of [...entries].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0))) {
    const path = join(root, entry.name);
    if (entry.isSymbolicLink()) throw refusal(path, "is a symbolic link; a role is a directory of its own under roles/ - copy it in instead of linking it");
    if (entry.name.startsWith(".") || entry.name === ROLE_TEMPLATE || !entry.isDirectory()) continue;
    if (!ROLE_ID_RE.test(entry.name)) throw refusal(path, `is not a role id: a role directory is named [a-z0-9][a-z0-9-]*, at most 64 characters, and only ${ROLE_TEMPLATE} is exempt - rename it or move it out of roles/`);
    ids.push(entry.name);
  }
  return ids;
}

/** Read and validate every role under `root`, sorted by id. Synchronous. The first problem
 *  throws an `Error` whose message opens with the absolute path of the file it is about
 *  (the root itself when that is what is missing). */
export function readRoles(root: string): RoleFile[] {
  const base = resolve(root);
  return listRoleIds(base).map((id) => readRole(base, id));
}

/** The id of Gravit's own plugin row; `bots/gravit/agent.cordis.yml` leads with it. */
export const GRAVIT_ROW_ID = "gravit";
/** The id of a role's `dsh-tool-subagent` row. */
export const roleRowId = (id: string): string => "role-" + id;
/** `plugins/gravit.js` as the in-memory form of the row's `name`: an absolute `file:` URL,
 *  module-relative, which the face's rebase passes through untouched (`rebaseName` in
 *  src/bot-presets.ts). The committed mirror spells it {@link GRAVIT_PLUGIN_RELATIVE}. */
export const GRAVIT_PLUGIN_URL: string = pathToFileURL(join(dirname(fileURLToPath(import.meta.url)), "..", "plugins", "gravit.js")).href;
const TOOL_SUBAGENT_PLUGIN = "@deepseek-ai/dsh-tool-subagent";

/** What {@link gravitRows} takes besides the roles. */
export interface GravitRowsOptions {
  /** The first row's `name`: how this composition spells the plugin. */
  plugin: string;
  /** The text of the `gravit:cycle` section; absent when there is none. */
  cycle?: string;
}

/**
 * Gravit's composition rows for `roles`: the `gravit` plugin row first, its config the
 * summaries (and the cycle text, when given) the plugin turns into sections, then one
 * `@deepseek-ai/dsh-tool-subagent` row per role. The role row is a one-shot spawn child with
 * the role's persona, an exact tool allow-list, and its route when `role.yml` names one;
 * `dsh-tool-subagent` has no description key, which is why the summaries ride on the first
 * row. Pure: the same roles give the same rows.
 */
export function gravitRows(roles: readonly RoleFile[], options: GravitRowsOptions): PresetRow[] {
  return [
    {
      id: GRAVIT_ROW_ID,
      name: options.plugin,
      config: {
        roles: roles.map((role) => ({ tool: role.tool, summary: role.description })),
        ...(options.cycle === undefined ? {} : { cycle: options.cycle }),
      },
    },
    ...roles.map((role): PresetRow => ({
      id: roleRowId(role.id),
      name: TOOL_SUBAGENT_PLUGIN,
      config: {
        provider: "spawn",
        toolName: role.tool,
        backgroundMode: "one-shot",
        persona: role.persona,
        toolFilter: { allow: [...role.allow] },
        /* `model` is `<provider>/<model>` with exactly two segments (MODEL_ROUTE_RE). */
        ...(role.model === undefined ? {} : { agentOptions: { provider: role.model.split("/")[0], model: role.model.split("/")[1] } }),
      } satisfies ToolSubagentConfig,
    })),
  ];
}

const GENERATED_HEADER =
  "# GENERATED by face/src/roles.ts renderGravitComposition from roles/ and dsh/profile/cycle.md - do not hand-edit.\n" +
  "# A role's summary, persona and tools are edited in roles/<id>/ (the cycle in dsh/profile/cycle.md), then:\n" +
  "# cd face && npm run render:roles   (tests/roles.test.ts fails while this file differs from the render)\n";

/** The text of `bots/gravit/agent.cordis.yml`: the generated header, then {@link gravitRows}
 *  with the plugin spelled by its shipped relative path, dumped in the Loader's own dialect
 *  as `renderComposition` (src/bots.ts) dumps a bot's. `face/scripts/render-roles.ts` writes it. */
export function renderGravitComposition(roles: readonly RoleFile[], options: { cycle?: string }): string {
  const rows = gravitRows(roles, { plugin: GRAVIT_PLUGIN_RELATIVE, cycle: options.cycle });
  return GENERATED_HEADER + dump(rows, { schema: entryListSchema, lineWidth: -1, noRefs: true });
}
