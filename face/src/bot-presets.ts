// face/src/bot-presets.ts
/** Bots as dsh agent presets the face DECLARES (PLAN S6).
 *
 * dsh 0.2.0 retired the directory-scanned roster (`dsh-agent-presets`, commit
 * d1e22a7e24): a preset is a `PresetDefinition` handed to
 * `agentPresets.register`, and nothing in dsh reads `agent.cordis.yml` or
 * `preset.yml` any more ("the registry neither scans directories nor accepts
 * preset paths", NEW packages/preset/agent-preset-registry/README.md:46). So the
 * face builds each definition from `bots/<id>/` itself, and every file there
 * stays byte-identical:
 * - `preset.yml` gives `name`, `description` and `order`, read exactly as
 *   0.1.1's dsh read them (OLD packages/preset/agent-presets/src/metadata.ts:
 *   41-85): trimmed, a blank value omitted (the registry publishes whatever it
 *   is given, NEW agent-preset-registry/src/index.ts:158-160), and an absent
 *   or malformed file is empty metadata - the composition still mounts
 *   (bots.ts `rowFor` reports the malformed file to the operator). `model`
 *   stays face-only: a preset carries no route (NEW
 *   agent-preset-registry/src/definition.ts:5-11).
 * - `agent.cordis.yml` is the `plugins` list, parsed in the Loader's own
 *   dialect (`entryListSchema`: `!!js` stays an expression node, NEW
 *   vendor/include/src/index.ts:9-23) and REBASED onto the bot directory. dsh
 *   resolves a preset's rows against the DECLARING context's base (NEW
 *   agent-preset-registry/src/index.ts:81, 108; src/mount.ts:258-264; NEW
 *   vendor/loader/src/config/tree.ts:112-127) - the profile directory for a
 *   face declaration (NEW packages/boot/app-boot/src/index.ts:994) - where
 *   0.1.1 resolved a relative row from the preset's own directory. A relative
 *   (`./`, `../`) or absolute path row becomes an absolute `file:` URL, and a
 *   relative `customSkillDirs` entry of a `@deepseek-ai/dsh-skill-filesystem`
 *   row becomes an absolute path: that plugin resolves roots against the
 *   PROCESS cwd (NEW packages/skill/skill-filesystem/src/index.ts:169), which
 *   made `./skills` mean `face/skills` in 0.1.1 too (a latent defect with no
 *   visible effect: no bot ships a SKILL.md). A composition that is not a list
 *   passes through untouched, so the registry marks the preset broken in its
 *   own words (definition.ts:18-23; index.ts:106-117).
 *
 * `definitionFor` is the pure half: boot's static `preset-kairos` overlay row
 * is `definitionFor(botsRoot, DEFAULT_PRESET)`, so `bots/kairos` stays
 * authoritative for the default. `declareBots` is the live half: every other
 * bot is declared from the booted root context once the tree has settled,
 * because activation is EAGER (NEW agent-preset-registry/src/index.ts:80-118)
 * and a row-time declaration would mount `plugins/bot.js` before the host's
 * late tools exist. It re-declares a bot when the face saves its files -
 * 0.1.1 re-read the directory on every mount; 0.2.0 never re-reads.
 * @module
 */
import { readFileSync } from "node:fs";
import { lstat, readdir } from "node:fs/promises";
import { isAbsolute, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import type { Context } from "@deepseek-ai/cordis";
import { entryListSchema } from "@deepseek-ai/cordis-plugin-include";
import type { PresetDefinition } from "@deepseek-ai/dsh-agent-preset-registry";
import { load } from "js-yaml";
import { isBotId } from "./bots.ts";
import { DEFAULT_PRESET } from "./overlay.ts";

const BIN = "kairos-face";
/** The composition file, as 0.1.1's dsh named it (OLD agent-presets/src/discovery.ts:26). */
export const COMPOSITION_FILE = "agent.cordis.yml";
/** The display-metadata file, as 0.1.1's dsh named it (OLD agent-presets/src/metadata.ts). */
export const METADATA_FILE = "preset.yml";
/** The one plugin whose config names directories rather than modules. */
const SKILL_FILESYSTEM = "@deepseek-ai/dsh-skill-filesystem";
/** `FiberState.ACTIVE`. A const enum with no runtime object under tsx, so the
 * literal, as app-boot itself does (NEW vendor/cordis/src/fiber.ts:147-154;
 * packages/boot/app-boot/src/index.ts:730-737). */
const FIBER_ACTIVE = 2;

type PresetRow = PresetDefinition["plugins"][number];

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
/** A `!!js` node (`{ __jsExpr }`, NEW vendor/include/src/index.ts:9-15): the
 * Loader evaluates it at activation, so the face never rewrites inside one. */
const isExpression = (value: unknown): boolean => isRecord(value) && "__jsExpr" in value;
const messageOf = (error: unknown): string => error instanceof Error ? error.message : String(error);

/** OLD metadata.ts:41-46, verbatim: a non-empty trimmed string, or nothing. */
function text(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed === "" ? undefined : trimmed;
}

/** `preset.yml` as 0.1.1's `readPresetMetadata` read it (OLD metadata.ts:56-85):
 * absent, unreadable, unparsable or not a mapping is empty metadata, never a
 * reason to leave the bot undeclared. */
function readMetadata(path: string): Pick<PresetDefinition, "name" | "description" | "order"> {
  let parsed: unknown;
  try {
    parsed = load(readFileSync(path, "utf8"));
  } catch {
    return {};
  }
  if (!isRecord(parsed)) return {};
  const name = text(parsed.name);
  const description = text(parsed.description);
  const order = typeof parsed.order === "number" && Number.isFinite(parsed.order) ? parsed.order : undefined;
  return {
    ...(name === undefined ? {} : { name }),
    ...(description === undefined ? {} : { description }),
    ...(order === undefined ? {} : { order }),
  };
}

/** A row's module name as the Loader must receive it from a face declaration.
 * Relative and absolute PATHS become `file:` URLs through `pathToFileURL`,
 * which also escapes `#`, `%` and `?` in directory names - a raw path would
 * be parsed as a URL there. The absolute case mirrors app-boot's own root
 * include (NEW packages/boot/app-boot/src/index.ts:549). Bare package names,
 * `file:` URLs and `cordis:` builtins resolve the same from any base and pass
 * through. */
function rebaseName(name: string, dir: string): string {
  if (name.startsWith("./") || name.startsWith("../")) return pathToFileURL(resolve(dir, name)).href;
  if (isAbsolute(name)) return pathToFileURL(name).href;
  return name;
}

/** One composition row, rebased onto the bot directory. Anything that is not
 * a plain row passes through: the registry names the bad row itself
 * (definition.ts:24-32). A `group: true` row's config is a nested entry list
 * the Loader resolves from the same base, so its rows are rebased too (the
 * registry validates nested groups the same way, definition.ts:33-36). */
function rebaseRow(row: unknown, dir: string): PresetRow {
  if (!isRecord(row)) return row as PresetRow;
  let next: Record<string, unknown> = row;
  if (typeof row.name === "string") {
    const name = rebaseName(row.name, dir);
    if (name !== row.name) next = { ...next, name };
  }
  const config = row.config;
  if (row.name === SKILL_FILESYSTEM && isRecord(config) && !isExpression(config) && Array.isArray(config.customSkillDirs)) {
    next = {
      ...next,
      config: {
        ...config,
        customSkillDirs: config.customSkillDirs.map((entry: unknown) =>
          typeof entry === "string" && !isAbsolute(entry) ? resolve(dir, entry) : entry),
      },
    };
  }
  if (row.group === true && Array.isArray(config)) {
    next = { ...next, config: config.map((child: unknown) => rebaseRow(child, dir)) };
  }
  return next as PresetRow;
}

/**
 * Build the dsh preset definition for `bots/<id>/`.
 * @param botsRoot - the `bots/` directory holding `<id>/`.
 * @param id - the preset id, which is the directory name.
 * @returns the definition to declare: rebased rows, published display metadata.
 * @throws with the composition file's absolute path when it is missing,
 * unreadable or not valid YAML - the caller records the reason and leaves the
 * bot undeclared (0.1.1 listed such a bot as broken, OLD discovery.ts:86-105,
 * 150-156). A readable composition that is not a list does NOT throw.
 */
export function definitionFor(botsRoot: string, id: string): PresetDefinition {
  const dir = join(botsRoot, id);
  const compositionPath = join(dir, COMPOSITION_FILE);
  let source: string;
  try {
    source = readFileSync(compositionPath, "utf8");
  } catch (error) {
    const missing = (error as NodeJS.ErrnoException).code === "ENOENT";
    throw new Error(
      missing
        ? `${compositionPath} is missing - the directory still occupies the id; restore the file or delete the directory`
        : `${compositionPath} cannot be read: ${messageOf(error)}`,
      { cause: error },
    );
  }
  let rows: unknown;
  try {
    rows = load(source, { schema: entryListSchema });
  } catch (error) {
    /* First line only: js-yaml appends a multi-line code frame, and this reason
     * is shown on a roster card (OLD discovery.ts:96-104 trimmed it the same way). */
    throw new Error(`${compositionPath} is not valid YAML: ${messageOf(error).replace(/\n[\s\S]*$/, "")}`, { cause: error });
  }
  return {
    id,
    ...readMetadata(join(dir, METADATA_FILE)),
    /* A non-list is handed over as it parsed: the registry refuses it with
     * "the composition must be a top-level list of plugin rows" and lists the
     * preset broken, which is the reason the operator should read. */
    plugins: Array.isArray(rows) ? rows.map((row) => rebaseRow(row, dir)) : (rows as PresetDefinition["plugins"]),
  };
}

/** What {@link declareBots} hands back to boot and to the bot routes. */
export interface BotPresets {
  /**
   * Re-read `bots/<id>/` and replace its declaration: dispose the current
   * one, then declare anew - the registry refuses a duplicate id (NEW
   * agent-preset-registry/src/index.ts:83), so never the other way round.
   * Live agents keep the revision they joined (index.ts:86-98; tests/
   * registry.spec.ts:39-60): old conversations keep the old soul, new ones
   * get the saved files. A directory that no longer exists stays undeclared.
   * Serialized per id with the initial declaration. A bot-level failure never
   * rejects: its reason lands in {@link errors}.
   * @throws for an id that is not a bot, or after {@link dispose}.
   */
  redeclare(id: string): Promise<void>;
  /** Dispose every declaration this handle holds; idempotent. Disposing the
   * root context disposes them too - they are its child fibers. */
  dispose(): Promise<void>;
  /** Why a bot is NOT declared, by id - a composition the face could not read,
   * or a declaration the registry refused. A LIVE map (mutated in place), so
   * a reader holding it follows every re-declaration. A declared bot whose
   * rows fail to mount is not here: the registry lists it `broken` instead. */
  readonly errors: ReadonlyMap<string, string>;
  /** The ids this handle has declared right now, sorted. */
  ids(): string[];
}

/** Options for {@link declareBots}. */
export interface DeclareBotsOptions {
  /** Where a declaration failure is reported (default `console.error`): a bot
   * that silently failed to declare would just be missing from every room. */
  log?: (line: string) => void;
}

/**
 * Declare every bot under `botsRoot` into the booted tree's preset registry.
 *
 * Every directory whose name passes {@link isBotId} - so never `_template`,
 * never the reserved default `kairos`, which the overlay's static row declares
 * - is declared through its own child plugin of `ctx`, exactly the registry's
 * own declaration model (NEW agent-preset-registry/tests/harness.ts:35-40):
 * `ctx.plugin({ inject: ["agentPresets"], async *apply(c) { yield await
 * c.agentPresets.register(definition) } })`. Disposing that fiber unregisters
 * the definition; if the registry itself restarts, cordis unloads and reloads
 * the fiber, which re-registers it on the new instance.
 *
 * Call it after `boot()` resolved - the MCP rows have awaited their initial
 * discovery (NEW packages/mcp/mcp-client/src/index.ts:194-199) and every host
 * tool row is active - and not from inside a host row's activation: the
 * registry's diagnostics wait for the host tree to settle (index.ts:120-131).
 * @param ctx - the booted ROOT context (its `baseUrl` is the profile directory).
 * @param botsRoot - the `bots/` directory.
 * @param options - where declaration failures are reported.
 * @returns the live handle; see {@link BotPresets}.
 * @throws when the preset registry service is absent (a fiber injecting a
 * missing service stays pending and would declare nothing, silently), or
 * when `botsRoot` exists but cannot be read.
 */
export async function declareBots(ctx: Context, botsRoot: string, options: DeclareBotsOptions = {}): Promise<BotPresets> {
  const log = options.log ?? ((line: string) => console.error(line));
  if (ctx.get("agentPresets") === undefined) {
    throw new Error(`${BIN}: agentPresets is missing - no bot under ${botsRoot} can be declared (the agent-preset-registry overlay row did not mount)`);
  }
  let entries: import("node:fs").Dirent[] = [];
  try {
    entries = await readdir(botsRoot, { withFileTypes: true });
  } catch (error) {
    /* An absent root holds no bots, as 0.1.1's scan held (OLD discovery.ts:139-146). */
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      throw new Error(`${BIN}: cannot read the bots root ${botsRoot}: ${messageOf(error)}`, { cause: error });
    }
  }
  const isBot = (id: string): boolean => isBotId(id) && id !== DEFAULT_PRESET;
  const ids = entries.filter((entry) => entry.isDirectory() && isBot(entry.name)).map((entry) => entry.name).sort();

  /* Declaration handles, NOT the fibers themselves: `ctx.plugin` returns a
   * thenable (NEW vendor/cordis/src/registry.ts:330-335), and a thenable that
   * reaches a `return` or `await` again is silently adopted. */
  const declared = new Map<string, { dispose(): Promise<void> }>();
  const errors = new Map<string, string>();
  const queue = new Map<string, Promise<void>>();
  let disposed = false;

  const fail = (id: string, reason: string): void => {
    errors.set(id, reason);
    log(`${BIN}: bot "${id}" is not declared - ${reason}`);
  };
  /** One id's tasks run one after another; different ids do not wait. */
  const serialize = (id: string, task: () => Promise<void>): Promise<void> => {
    const next = (queue.get(id) ?? Promise.resolve()).catch(() => undefined).then(task);
    queue.set(id, next);
    return next.finally(() => { if (queue.get(id) === next) queue.delete(id); });
  };
  const declareOne = async (id: string): Promise<void> => {
    let definition: PresetDefinition;
    try {
      definition = definitionFor(botsRoot, id);
    } catch (error) {
      return fail(id, messageOf(error));
    }
    const fiber = ctx.plugin({
      inject: ["agentPresets"],
      async *apply(declaring: Context) { yield await declaring.agentPresets.register(definition); },
    });
    try {
      await fiber;
    } catch (error) {
      /* A refused `register` (a duplicate or blank id) leaves the fiber FAILED
       * but attached (NEW vendor/cordis/src/fiber.ts:659-664); detach it. */
      await fiber.dispose();
      return fail(id, `the preset registry refused it: ${messageOf(error)}`);
    }
    /* Awaiting a fiber whose injected service is absent RESOLVES at once, with
     * the fiber still PENDING and nothing registered (measured on cordis 4.0.4). */
    if ((fiber.state as number) !== FIBER_ACTIVE) {
      await fiber.dispose();
      return fail(id, `its declaration never activated (fiber state ${String(fiber.state)}) - is the agentPresets service mounted?`);
    }
    declared.set(id, { dispose: () => fiber.dispose() });
    errors.delete(id);
  };

  for (const id of ids) await serialize(id, () => declareOne(id));

  return {
    redeclare(id: string): Promise<void> {
      if (!isBot(id)) return Promise.reject(new Error(`${BIN}: ${JSON.stringify(id)} is not a bot id - only bots/<id> directories are re-declared`));
      if (disposed) return Promise.reject(new Error(`${BIN}: the bot declarations are disposed - "${id}" was not re-declared`));
      return serialize(id, async () => {
        if (disposed) return;
        const current = declared.get(id);
        declared.delete(id);
        if (current !== undefined) await current.dispose();
        let isDirectory = false;
        try {
          isDirectory = (await lstat(join(botsRoot, id))).isDirectory();
        } catch (error) {
          if ((error as NodeJS.ErrnoException).code !== "ENOENT") return fail(id, `bots/${id} cannot be read: ${messageOf(error)}`);
        }
        if (!isDirectory) {
          errors.delete(id);
          return;
        }
        await declareOne(id);
      });
    },
    async dispose(): Promise<void> {
      if (disposed) return;
      disposed = true;
      await Promise.allSettled([...queue.values()]);
      const handles = [...declared.values()];
      declared.clear();
      await Promise.all(handles.map((handle) => handle.dispose()));
    },
    errors,
    ids: () => [...declared.keys()].sort(),
  };
}
