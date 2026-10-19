// face/src/roles.ts
/** The role library: one directory per role under `roles/<id>/`.
 *
 * A role is a one-shot child Gravit hands a bounded piece of work. Its directory holds
 * `ROLE.md` (the child's persona, verbatim) and `role.yml` (`name`; `description`, the
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
 * @module
 */
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { load } from "js-yaml";
import { MODEL_ROUTE_RE } from "./bots.ts";

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
  if (description.length > SUMMARY_MAX) throw refusal(file, `description is ${description.length} characters; the limit is ${SUMMARY_MAX}`);

  const listed = fields.allow;
  if (!Array.isArray(listed) || listed.length === 0) throw refusal(file, "allow must be a non-empty list of exact tool names");
  /* Entries are kept exactly as written: no trimming, so a blank one fails the grammar. */
  const allow = listed.map((entry: unknown, index: number): string => {
    if (typeof entry !== "string") throw refusal(file, `allow entry ${index + 1} is not a string`);
    if (entry.includes("*")) throw refusal(file, `allow entry ${JSON.stringify(entry)}: wildcards are not accepted; name the exact tool, e.g. mcp__alpaca-kit__screen`);
    if (!TOOL_NAME_RE.test(entry)) throw refusal(file, `allow entry ${JSON.stringify(entry)} is not a tool name (letters, digits, _ and - only)`);
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
  /* ROLE.md first, so its refusals come before role.yml's. */
  return { id, tool: toolNameFor(id), persona: readPersona(join(dir, PERSONA_FILE)), ...readMeta(join(dir, META_FILE)) };
}

/** The role ids under `root`, sorted. A directory whose name is not a {@link ROLE_ID_RE} id,
 *  `_template`, and anything that is not a directory are skipped without a word. */
function listRoleIds(root: string): string[] {
  try {
    return readdirSync(root, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && entry.name !== ROLE_TEMPLATE && ROLE_ID_RE.test(entry.name))
      .map((entry) => entry.name)
      .sort();
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    throw refusal(root, code === "ENOENT" ? "the roles directory is missing" : code === "ENOTDIR" ? "is not a directory" : `cannot be listed: ${messageOf(error)}`, error);
  }
}

/** Read and validate every role under `root`, sorted by id. Synchronous. The first problem
 *  throws an `Error` whose message opens with the absolute path of the file it is about
 *  (the root itself when that is what is missing). */
export function readRoles(root: string): RoleFile[] {
  const base = resolve(root);
  return listRoleIds(base).map((id) => readRole(base, id));
}
