/** The operator's read-only dry run of a COPY of their harness home against
 * the dsh this face pins (0.2.0-rc.2): what the first live boot will do to the
 * home, measured on a copy, before it is done to the home. Step 3 of the
 * go-live runbook, docs/superpowers/runbooks/2026-09-30-dsh-0.2.0-rc.2-go-live.md.
 *
 *     SCRATCH=$(mktemp -d)
 *     cp -a ~/.dsh "$SCRATCH/dsh-dryrun"
 *     touch "$SCRATCH/dsh-dryrun/DRY-RUN-COPY"
 *     cd face && npx tsx scripts/check-home.ts "$SCRATCH/dsh-dryrun"
 *
 * What it does, in order, and nothing else:
 * 1. REFUSES (exit 2) before it loads any dsh plugin code or writes anything,
 *    unless the one argument is an existing directory that is not the live
 *    harness home (`$DSH_HOME` as this environment resolves it, and
 *    `~/.dsh`), not inside it and not above it - compared by device and inode,
 *    because a path string is not an identity (`realpath` keeps the caller's
 *    case on a case-insensitive APFS volume, so `~/.DSH` would pass a string
 *    comparison) - and that carries the `DRY-RUN-COPY` marker file the runbook
 *    has the operator create IN THE COPY. The marker is the second key: an
 *    accidental live path never passes, because nobody creates the marker
 *    there.
 * 2. Reads what needs no boot: an inventory of every file in the copy (so the
 *    report can say exactly what the boot and the scan wrote), the raw session
 *    logs (physical generation, raw event count, message source kinds), the
 *    0.1.1 module link farm (`profiles/node_modules`, PLAN D13) and
 *    `settings.yaml`'s `agent-default-model` section (D1/D2).
 * 3. Boots the face's own composition on the copy with `bootFace`, as
 *    `main.ts` boots the live home except for three things: the copy is the
 *    home, `DSH_TELEMETRY_DISABLED=1`, and every MCP client row (the
 *    operator's `mcp-alpaca-kit`, the face's `mcp-akshare`, any other) is
 *    disabled through an IN-MEMORY patch layer
 *    ({@link FaceBootOptions.extraPatches}) - never by writing the copy's
 *    patch files - so no MCP server is spawned and no key leaves the machine.
 * 4. Lists `sessionPersistence.list()` and opens every session READ-ONLY -
 *    `open(id, "read")`, `read()`, `close()`: the in-memory V0..V4 migration
 *    the 0.2.0 host runs before it can page or follow a session, which
 *    publishes nothing - and records each refusal with its class
 *    ({@link classifyRefusal}), plus the sessions whose header preset is no
 *    longer in the roster.
 * 5. Disposes the tree, writes `<copy>.check-home.json` BESIDE the copy,
 *    prints a summary, and reminds the operator to delete the copy - it holds
 *    `.credentials.yaml` and every session log.
 *
 * Exit codes: 0 - the scan completed (a refused session is a FINDING, not a
 * failure); 1 - the boot or the scan could not complete (the report says why;
 * the live boot would fail the same way); 2 - refused to run.
 * @module
 */
import { createHash } from "node:crypto";
import {
  existsSync, lstatSync, readdirSync, readFileSync, readlinkSync, realpathSync, statSync, writeFileSync,
} from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { zstdDecompressSync } from "node:zlib";
import { load } from "js-yaml";
import { defaultDshHome, resolveDshHome } from "@deepseek-ai/dsh-home-paths";
import type { FaceBootOptions, FacePatchList } from "../src/boot.ts";
import { AKSHARE_MCP_ROW_ID } from "../src/akshare.ts";
import { DSH_PIN } from "../src/version.ts";

/** The file the runbook has the operator create in the COPY, and only there. */
export const MARKER_FILE = "DRY-RUN-COPY";
/** Refused to run: nothing was loaded, nothing was written. */
export const EXIT_REFUSED = 2;
/** The boot or the scan did not complete; the report says why. */
export const EXIT_INCOMPLETE = 1;
/** The package every MCP server row mounts (dsh-base, the face's AKShare row
 * and the operator's alpaca-kit row alike). */
export const MCP_CLIENT_PACKAGE = "@deepseek-ai/dsh-mcp-client";
/** The operator's alpaca-kit row id (dsh/README.md steps 3-6), disabled by id
 * as well as by package, in case a future row spells its package differently. */
const ALPACA_KIT_ROW_ID = "mcp-alpaca-kit";
/** The D2 row the operator adds to the face profile patch. */
const DEFAULT_MODEL_ROW_ID = "agent-default-model";

/** A thrown value's message, for one-line diagnostics. */
function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/* ------------------------------------------------------------------ guard */

/** The harness homes this environment would boot, which the dry run must
 * never touch: `$DSH_HOME` as dsh resolves it (blank = unset, `~` expanded),
 * and the default `~/.dsh`.
 * @param env - the environment to read `DSH_HOME` from.
 */
export function liveHomeCandidates(env: NodeJS.ProcessEnv = process.env): string[] {
  return [...new Set([resolveDshHome(undefined, env), defaultDshHome()])];
}

/** Device and inode of an existing path, or `undefined`. */
function identity(path: string): { dev: number; ino: number } | undefined {
  try {
    const st = statSync(path);
    return { dev: st.dev, ino: st.ino };
  } catch {
    return undefined;
  }
}

/** Is `ancestor` the same directory as `path` or one of its parents? Walks
 * `path` upward comparing device+inode, so case, symlinks and `..` cannot
 * disguise the relation. */
function isSameOrAncestor(ancestor: { dev: number; ino: number }, path: string): boolean {
  let current = path;
  for (;;) {
    const id = identity(current);
    if (id !== undefined && id.dev === ancestor.dev && id.ino === ancestor.ino) return true;
    const parent = dirname(current);
    if (parent === current) return false;
    current = parent;
  }
}

/** The guard's verdict: the canonical copy path, or why it was refused. */
export type TargetCheck = { ok: true; copy: string } | { ok: false; reason: string };

/**
 * Decide whether `arg` may be dry-run. Reads the filesystem, writes nothing.
 * @param arg - the operator's argument, read the way `bootFace({dshHome})`
 * would read it (`~` expanded, relative to the working directory).
 * @param liveHomes - the homes that must never be the target (see
 * {@link liveHomeCandidates}); a home that does not exist yet still counts.
 * @param profileName - the face profile the copy must carry.
 */
export function checkTarget(arg: string | undefined, liveHomes: readonly string[], profileName = "face"): TargetCheck {
  const refuse = (reason: string): TargetCheck => ({ ok: false, reason });
  if (arg === undefined || arg.trim() === "") {
    return refuse("usage: npx tsx scripts/check-home.ts <path of a COPY of the harness home>");
  }
  const candidate = resolveDshHome(arg);
  const target = identity(candidate);
  if (target === undefined) return refuse(`${candidate} does not exist`);
  if (!statSync(candidate).isDirectory()) return refuse(`${candidate} is not a directory`);
  const copy = realpathSync.native(candidate);
  for (const home of liveHomes) {
    const live = identity(home);
    const homeReal = live === undefined ? resolve(home) : realpathSync.native(home);
    if (live === undefined ? resolve(copy) === homeReal : live.dev === target.dev && live.ino === target.ino) {
      return refuse(`${copy} IS the live harness home (${homeReal}). Dry-run a COPY: see the runbook, step 3`);
    }
    if (live !== undefined && isSameOrAncestor(live, dirname(copy))) {
      return refuse(`${copy} is inside the live harness home ${homeReal}; put the copy outside it (mktemp -d)`);
    }
    if (isSameOrAncestor(target, homeReal)) {
      return refuse(`${copy} contains the live harness home ${homeReal}; pass the COPY itself`);
    }
  }
  let marker: ReturnType<typeof lstatSync> | undefined;
  try {
    marker = lstatSync(join(copy, MARKER_FILE));
  } catch {
    marker = undefined;
  }
  if (marker === undefined || !marker.isFile()) {
    return refuse(
      `${copy} has no ${MARKER_FILE} marker file. Create it IN THE COPY, never in the live home: ` +
        `touch '${join(copy, MARKER_FILE)}'`,
    );
  }
  if (!existsSync(join(copy, "profiles", profileName, "package.json"))) {
    return refuse(`${copy} has no profiles/${profileName}/package.json - not a copy of a home the face has booted`);
  }
  return { ok: true, copy };
}

/* -------------------------------------------------------------- inventory */

/** What the inventory records per path; enough to tell a write from a read. */
export interface FileFact {
  kind: "file" | "dir" | "link" | "other";
  size?: number;
  mtimeMs?: number;
  ino?: number;
  sha256?: string;
  target?: string;
}

/**
 * Every path under `root` (symlinks recorded, never followed), with a content
 * hash per regular file. A path that vanishes mid-walk is skipped.
 * @param root - the directory to walk.
 * @returns relative POSIX path → fact.
 */
export function inventory(root: string): Map<string, FileFact> {
  const out = new Map<string, FileFact>();
  const walk = (rel: string): void => {
    let names: string[];
    try {
      names = readdirSync(rel === "" ? root : join(root, rel));
    } catch {
      return;
    }
    for (const name of names.sort()) {
      const path = rel === "" ? name : `${rel}/${name}`;
      const abs = join(root, path);
      try {
        const st = lstatSync(abs);
        if (st.isSymbolicLink()) out.set(path, { kind: "link", target: readlinkSync(abs) });
        else if (st.isDirectory()) {
          out.set(path, { kind: "dir" });
          walk(path);
        } else if (st.isFile()) {
          const sha256 = createHash("sha256").update(readFileSync(abs)).digest("hex");
          out.set(path, { kind: "file", size: st.size, mtimeMs: st.mtimeMs, ino: st.ino, sha256 });
        } else out.set(path, { kind: "other" });
      } catch {
        /* vanished between readdir and lstat: a temp file of a concurrent write */
      }
    }
  };
  walk("");
  return out;
}

/** One difference between two inventories. `rewritten` = same bytes, new
 * inode or mtime: the file was written even though its content is unchanged. */
export interface Change {
  path: string;
  change: "added" | "removed" | "modified" | "rewritten";
  kind: FileFact["kind"];
}

/** The writes between two inventories (directories: added/removed only). */
export function diffInventory(before: ReadonlyMap<string, FileFact>, after: ReadonlyMap<string, FileFact>): Change[] {
  const changes: Change[] = [];
  for (const [path, now] of after) {
    const was = before.get(path);
    if (was === undefined) changes.push({ path, change: "added", kind: now.kind });
    else if (was.kind !== now.kind) changes.push({ path, change: "modified", kind: now.kind });
    else if (now.kind === "file") {
      if (was.sha256 !== now.sha256) changes.push({ path, change: "modified", kind: now.kind });
      else if (was.ino !== now.ino || was.mtimeMs !== now.mtimeMs) changes.push({ path, change: "rewritten", kind: now.kind });
    } else if (now.kind === "link" && was.target !== now.target) {
      changes.push({ path, change: "modified", kind: now.kind });
    }
  }
  for (const [path, was] of before) {
    if (!after.has(path)) changes.push({ path, change: "removed", kind: was.kind });
  }
  return changes.sort((a, b) => a.path.localeCompare(b.path));
}

/* ------------------------------------------------------- raw session logs */

const ZSTD_MAGIC = 0xfd2fb528;

/**
 * Byte ranges of the complete Zstandard frames in a concatenated stream, and
 * whether it ends inside a frame. Needed because `node:zlib` decodes only the
 * FIRST frame of a multi-frame buffer, and dsh writes a session log as one
 * frame per append batch. The structural walk is the one upstream's own
 * reader uses (`scanZstdFrames`, NEW packages/session/session-persistence-jsonl/
 * src/zstd.ts): frame header, then block headers up to the last block, then
 * the optional checksum; nothing is decompressed to find a boundary.
 * @param buffer - the file's bytes.
 * @throws on a non-Zstandard frame or a reserved bit or block type.
 */
export function zstdFrames(buffer: Buffer): { frames: Array<[start: number, end: number]>; torn: boolean } {
  const frames: Array<[number, number]> = [];
  let offset = 0;
  while (offset < buffer.length) {
    const start = offset;
    if (buffer.length - offset < 5) return { frames, torn: true };
    if (buffer.readUInt32LE(offset) !== ZSTD_MAGIC) throw new Error(`not a Zstandard frame at byte ${offset}`);
    const descriptor = buffer.readUInt8(offset + 4);
    offset += 5;
    if ((descriptor & 0x18) !== 0) throw new Error(`reserved frame-header bit at byte ${offset - 1}`);
    const contentSizeFlag = descriptor >>> 6;
    const singleSegment = (descriptor & 0x20) !== 0;
    const dictionaryFlag = descriptor & 0x03;
    offset += (singleSegment ? 0 : 1) + (dictionaryFlag === 3 ? 4 : dictionaryFlag) +
      (contentSizeFlag === 0 ? (singleSegment ? 1 : 0) : 1 << contentSizeFlag);
    for (;;) {
      if (buffer.length - offset < 3) return { frames, torn: true };
      const block = buffer.readUIntLE(offset, 3);
      offset += 3;
      const type = (block >>> 1) & 0x03;
      if (type === 0x03) throw new Error(`reserved block type at byte ${offset - 3}`);
      offset += type === 0x01 ? 1 : block >>> 3;
      if (offset > buffer.length) return { frames, torn: true };
      if ((block & 1) !== 0) break;
    }
    if ((descriptor & 0x04) !== 0) offset += 4;
    if (offset > buffer.length) return { frames, torn: true };
    frames.push([start, offset]);
  }
  return { frames, torn: false };
}

/** The text of a stored session log, every complete frame decoded. */
export function readLogText(file: string): { text: string; torn: boolean } {
  const bytes = readFileSync(file);
  if (!file.endsWith(".zstd")) return { text: bytes.toString("utf8"), torn: false };
  const { frames, torn } = zstdFrames(bytes);
  const text = frames.map(([start, end]) => zstdDecompressSync(bytes.subarray(start, end)).toString("utf8")).join("");
  return { text, torn };
}

/** One session directory as it sits on disk, read without dsh. */
export interface RawSession {
  /** Session directory, relative to the home. */
  dir: string;
  /** Every file in it: generations, `session.lock`, temps. */
  files: string[];
  /** The log dsh reads: the highest canonical generation. */
  log?: string;
  /** Its physical format generation (0 = `session.jsonl[.zstd]`). */
  generation?: number;
  bytes?: number;
  /** Rows after the header: the raw logged events. */
  rawEvents?: number;
  /** Message source kinds found in the log (`data.source.kind`, `data.message.source.kind`). */
  sourceKinds?: string[];
  torn?: boolean;
  error?: string;
}

/** `session.jsonl`, `session.v4.jsonl.zstd`, ... - never `session.lock` or a temp. */
const GENERATION_RE = /^session(?:\.v(\d+))?\.jsonl(\.zstd)?$/;

/**
 * Read every session directory under `<home>/sessions` the way dsh picks its
 * log (the highest canonical generation, `.zstd` winning a tie), keyed by the
 * id in the log's own header. Read-only; a log that cannot be read is
 * recorded with its error, never fatal.
 */
export function scanRawSessions(home: string): Map<string, RawSession> {
  const root = join(home, "sessions");
  const out = new Map<string, RawSession>();
  let projects: string[];
  try {
    projects = readdirSync(root);
  } catch {
    return out;
  }
  for (const project of projects.sort()) {
    let dirs: string[];
    try {
      if (!statSync(join(root, project)).isDirectory()) continue;
      dirs = readdirSync(join(root, project));
    } catch {
      continue;
    }
    for (const name of dirs.sort()) {
      const abs = join(root, project, name);
      let files: string[];
      try {
        if (!statSync(abs).isDirectory()) continue;
        files = readdirSync(abs).sort();
      } catch {
        continue;
      }
      const raw: RawSession = { dir: `sessions/${project}/${name}`, files };
      let best: { file: string; generation: number; zstd: boolean } | undefined;
      for (const file of files) {
        const m = GENERATION_RE.exec(file);
        if (m === null) continue;
        const generation = m[1] === undefined ? 0 : Number(m[1]);
        const zstd = m[2] !== undefined;
        if (best === undefined || generation > best.generation || (generation === best.generation && zstd && !best.zstd)) {
          best = { file, generation, zstd };
        }
      }
      if (best === undefined) {
        out.set(`(no log) ${raw.dir}`, { ...raw, error: "no session log in this directory" });
        continue;
      }
      raw.log = best.file;
      raw.generation = best.generation;
      let id = `(unreadable) ${raw.dir}`;
      try {
        const path = join(abs, best.file);
        raw.bytes = statSync(path).size;
        const { text, torn } = readLogText(path);
        if (torn) raw.torn = true;
        const lines = text.split("\n").filter((line) => line.length > 0);
        const header = JSON.parse(lines[0] ?? "null") as { id?: unknown } | null;
        if (typeof header?.id === "string") id = header.id;
        raw.rawEvents = Math.max(0, lines.length - 1);
        const kinds = new Set<string>();
        for (const line of lines.slice(1)) {
          let event: { data?: { source?: { kind?: unknown }; message?: { source?: { kind?: unknown } } } };
          try {
            event = JSON.parse(line) as typeof event;
          } catch {
            continue;
          }
          for (const kind of [event.data?.source?.kind, event.data?.message?.source?.kind]) {
            if (typeof kind === "string") kinds.add(kind);
          }
        }
        raw.sourceKinds = [...kinds].sort();
      } catch (err) {
        raw.error = messageOf(err);
      }
      if (!out.has(id)) out.set(id, raw);
    }
  }
  return out;
}

/* --------------------------------------------------------- classification */

/** Why 0.2.0 refused to read a session, by the upstream edge that refused it. */
export type RefusalClass = "room-source" | "subagent-descriptor" | "seq-gap" | "other";

/**
 * Classify a read-open refusal. Keyed on upstream's own refusal text; the room
 * class additionally requires the raw log to carry a `room` source kind, since
 * the v2->v3 edge refuses ANY kind outside its whitelist with the same words
 * (NEW packages/session/session-format-v2-to-v3/src/payload.ts, `assertSource`)
 * and only the room kind is covered by a decision (D11). Anything unmatched is
 * `other` - the runbook's stop condition.
 * @param error - the refusal's name and message.
 * @param sourceKinds - the raw log's message source kinds, when it was readable.
 */
export function classifyRefusal(error: { name: string; message: string }, sourceKinds: readonly string[] | undefined): RefusalClass {
  if (/cannot safely transform unclassified message source/.test(error.message)) {
    return sourceKinds?.includes("room") === true ? "room-source" : "other";
  }
  /* NEW packages/session/session-format-v0-to-v1/src/validation.ts,
   * `assertReleasedEventPayload`: a V0 descriptor must be version 3. */
  if (/subagent\/descriptor \d+ uses unsupported descriptor version/.test(error.message)) return "subagent-descriptor";
  /* NEW packages/session/session-format-v0-to-v1/src/codec.ts: a released row
   * whose seq is not the next one. */
  if (/has seq gap/.test(error.message)) return "seq-gap";
  return "other";
}

/** How the summary names each class, and the decision that covers it. */
const CLASS_LABEL: Record<RefusalClass, string> = {
  "room-source": "kind:'room' message source, refused by the v2->v3 edge (decision D11)",
  "subagent-descriptor": "subagent descriptor version 2, refused by the v0->v1 edge (decision D17)",
  "seq-gap": "corrupt log, seq gap (decision D17)",
  other: "OTHER - covered by no decision: STOP before go-live (runbook step 3)",
};

/* ---------------------------------------------------- composition helpers */

/** A composed Loader entry, as far as this tool reads one. */
interface EntryLike {
  id?: unknown;
  name?: unknown;
  group?: unknown;
  config?: unknown;
}

/** Every MCP client row in a composed entry list, group subtrees included
 * (an id patch reaches rows inside groups too: NEW vendor/include/src/
 * index.ts, `applyEntryPatches`). */
export function mcpRowsIn(entries: readonly EntryLike[]): Array<{ id?: string; serverName?: string }> {
  const out: Array<{ id?: string; serverName?: string }> = [];
  const walk = (list: readonly EntryLike[]): void => {
    for (const entry of list) {
      if (entry.name === MCP_CLIENT_PACKAGE) {
        const config = entry.config as { serverName?: unknown } | undefined;
        out.push({
          ...(typeof entry.id === "string" ? { id: entry.id } : {}),
          ...(typeof config?.serverName === "string" ? { serverName: config.serverName } : {}),
        });
      }
      if (entry.group === true && Array.isArray(entry.config)) walk(entry.config as EntryLike[]);
    }
  };
  walk(entries);
  return out;
}

/** The last row a patch list writes for `id` (an id patch, or an inserted
 * row), or `undefined` when the list never names it. */
export function findPatchRow(
  patches: readonly Record<string, unknown>[],
  id: string,
): { source: "patch" | "insert"; config?: unknown; disabled?: unknown } | undefined {
  let found: { source: "patch" | "insert"; config?: unknown; disabled?: unknown } | undefined;
  for (const patch of patches) {
    if (Array.isArray(patch.insert)) {
      for (const row of patch.insert as Record<string, unknown>[]) {
        if (row?.id === id) found = { source: "insert", config: row.config, disabled: row.disabled };
      }
    } else if (patch.id === id) {
      found = { source: "patch", config: patch.config, disabled: patch.disabled };
    }
  }
  return found;
}

/* --------------------------------------------------------- home-level facts */

/** The 0.1.1 module link farm, `profiles/node_modules` (PLAN D13). */
export interface LinkFarm {
  present: boolean;
  symlinks?: number;
  /** Link count per target root (the path up to its last `/node_modules`). */
  targets?: Record<string, number>;
}

/** Count the link farm's symlinks by where they point. Reads links, never
 * follows them. */
export function inspectLinkFarm(home: string): LinkFarm {
  const root = join(home, "profiles", "node_modules");
  try {
    if (!lstatSync(root).isDirectory()) return { present: true, symlinks: 0, targets: {} };
  } catch {
    return { present: false };
  }
  const targets: Record<string, number> = {};
  let symlinks = 0;
  const visit = (dir: string, depth: number): void => {
    for (const name of readdirSync(dir)) {
      const abs = join(dir, name);
      const st = lstatSync(abs);
      if (st.isSymbolicLink()) {
        symlinks += 1;
        const target = resolve(dir, readlinkSync(abs));
        const cut = target.lastIndexOf("/node_modules");
        const key = cut === -1 ? dirname(target) : target.slice(0, cut + "/node_modules".length);
        targets[key] = (targets[key] ?? 0) + 1;
      } else if (st.isDirectory() && depth === 0 && name.startsWith("@")) visit(abs, 1);
    }
  };
  visit(root, 0);
  return { present: true, symlinks, targets };
}

/** `settings.yaml`, which the 0.2.0 face does not read (D1), and whether a
 * 0.2.0 CLI has already imported and renamed it (D12). */
export interface SettingsFacts {
  present: boolean;
  importedCopyPresent: boolean;
  sections?: string[];
  agentDefaultModel?: unknown;
  error?: string;
}

/** Read `settings.yaml`'s section names and its `agent-default-model` section. */
export function inspectSettings(home: string): SettingsFacts {
  const file = join(home, "settings.yaml");
  const importedCopyPresent = existsSync(join(home, "settings.yaml.imported"));
  if (!existsSync(file)) return { present: false, importedCopyPresent };
  try {
    const doc = load(readFileSync(file, "utf8")) as Record<string, unknown> | null;
    const sections = doc !== null && typeof doc === "object" ? Object.keys(doc) : [];
    return { present: true, importedCopyPresent, sections, agentDefaultModel: doc?.[DEFAULT_MODEL_ROW_ID] ?? null };
  } catch (err) {
    return { present: true, importedCopyPresent, error: messageOf(err) };
  }
}

/* ----------------------------------------------------------------- report */

/** One session as the dry run found it. */
export interface SessionFinding {
  id: string;
  cwd?: string;
  agentPreset?: string;
  parentSession?: string;
  /** `readable` sessions carry `eventCount`; refused ones `error` + `refusal`. */
  readable: boolean;
  /** Events the read returned, after the in-memory migration to V4. */
  eventCount?: number;
  error?: { name: string; message: string };
  refusal?: RefusalClass;
  /** `default` = no preset in the header; `orphaned` = named, not in the roster. */
  preset: "default" | "listed" | "broken" | "orphaned";
  raw?: RawSession;
}

/** The JSON report written beside the copy. */
export interface CheckHomeReport {
  tool: "face/scripts/check-home.ts";
  dshPin: string;
  generatedAt: string;
  copy: string;
  liveHomes: string[];
  profile: string;
  boot: { ok: boolean; error?: string; mcpRowsDisabled: Array<{ id: string; serverName?: string; present: boolean }> };
  scan?: { ok: boolean; error?: string };
  defaultModel: {
    effective?: unknown;
    profilePatchRow?: { source: "patch" | "insert"; config?: unknown; disabled?: unknown } | null;
  };
  settingsYaml: SettingsFacts;
  linkFarm: LinkFarm;
  roster: Array<{ id: string; broken?: string }>;
  sessions: {
    listed: number;
    readable: number;
    refused: number;
    byClass: Record<RefusalClass, string[]>;
    orphanedPresets: Array<{ id: string; agentPreset: string }>;
    rawEvents: { total: number; refused: number };
    bytes: { total: number; refused: number };
    notListed: string[];
    items: SessionFinding[];
  };
  writes: { boot: Change[]; scanWindow: Change[]; dispose: Change[]; sessionsTouchedByScan: Change[] };
  warnings: string[];
}

/** Where the report goes: beside the copy, so deleting the copy keeps it. */
export function reportPathFor(copy: string): string {
  return `${copy}.check-home.json`;
}

/** One line per changed file, a directory with more than three same-kind
 * changes folded into one line, at most `limit` lines. */
export function describeChanges(changes: readonly Change[], limit = 14): string[] {
  const groups = new Map<string, Change[]>();
  for (const change of changes) {
    if (change.kind === "dir") continue;
    const key = `${dirname(change.path)}\u0000${change.change}`;
    groups.set(key, [...(groups.get(key) ?? []), change]);
  }
  const sign = { added: "+", removed: "-", modified: "~", rewritten: "=" } as const;
  const lines: string[] = [];
  for (const [key, group] of groups) {
    const [dir, change] = key.split("\u0000") as [string, Change["change"]];
    if (group.length > 3) lines.push(`${sign[change]} ${dir}/ (${group.length} files ${change})`);
    else for (const c of group) lines.push(`${sign[c.change]} ${c.path} (${c.change})`);
  }
  return lines.length > limit ? [...lines.slice(0, limit), `... ${lines.length - limit} more in the report`] : lines;
}

const home = homedir();
const tilde = (path: string | undefined): string => (path ?? "?").startsWith(home) ? `~${(path ?? "").slice(home.length)}` : path ?? "?";
const num = (n: number): string => n.toLocaleString("en-US");
const size = (bytes: number): string =>
  bytes >= 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${(bytes / 1024).toFixed(1)} KB`;

/** The human summary of a report. */
export function summarize(report: CheckHomeReport, reportPath: string): string {
  const out: string[] = [];
  out.push(`check-home: dry run of a COPY of a harness home against dsh ${report.dshPin} (profile "${report.profile}")`);
  out.push(`  copy:       ${report.copy}`);
  out.push(`  live homes: ${report.liveHomes.join(", ")} (compared by inode, never read)`);
  const disabled = report.boot.mcpRowsDisabled.filter((row) => row.present)
    .map((row) => row.serverName === undefined ? row.id : `${row.id} (${row.serverName})`);
  out.push(report.boot.ok
    ? `  boot:       ok - MCP rows disabled in memory for the dry run: ${disabled.join(", ") || "none composed"}`
    : `  boot:       FAILED - ${report.boot.error}\n              the live boot on the home would fail the same way; fix this first`);
  if (report.scan !== undefined && !report.scan.ok) out.push(`  scan:       FAILED - ${report.scan.error}`);
  const s = report.sessions;
  if (report.boot.ok) {
    out.push("");
    out.push(`Sessions: ${s.listed} listed, ${s.readable} readable, ${s.refused} refused by the 0.2.0 read`);
    for (const cls of ["room-source", "subagent-descriptor", "seq-gap", "other"] as const) {
      const ids = s.byClass[cls];
      if (ids.length === 0 && cls !== "other") continue;
      out.push(`  refused - ${CLASS_LABEL[cls]}: ${ids.length}`);
      for (const id of ids) {
        const item = s.items.find((i) => i.id === id);
        const raw = item?.raw?.rawEvents === undefined ? "" : `  ${num(item.raw.rawEvents)} raw events`;
        out.push(`    ${id}  ${tilde(item?.cwd)}${raw}`);
        if (cls === "other") out.push(`      ${item?.error?.name}: ${item?.error?.message}`);
      }
    }
    if (s.refused > 0) {
      const pct = s.rawEvents.total === 0 ? 0 : (100 * s.rawEvents.refused) / s.rawEvents.total;
      out.push(`  refused sessions hold ${num(s.rawEvents.refused)} of ${num(s.rawEvents.total)} raw logged events ` +
        `(${pct.toFixed(1)}%), ${size(s.bytes.refused)} of ${size(s.bytes.total)} of logs; their files stay on disk unchanged`);
    }
    if (s.notListed.length > 0) {
      out.push(`  on disk but not listed by 0.2.0 (${s.notListed.length}): ${s.notListed.join(", ")}`);
    }
    if (s.orphanedPresets.length > 0) {
      out.push(`  header preset not in the roster (${s.orphanedPresets.length}; readable, but a resume refuses agent-preset/not-found):`);
      for (const o of s.orphanedPresets) out.push(`    ${o.id}  ${o.agentPreset}`);
    }
  }
  out.push("");
  const eff = report.defaultModel.effective as { provider?: string; model?: string; reasoningEffort?: string } | undefined;
  const row = report.defaultModel.profilePatchRow;
  out.push(`Default model (D2): ${eff === undefined ? "(not read: no boot)" :
    `the face would run ${eff.provider}/${eff.model}${eff.reasoningEffort === undefined ? "" : `, effort ${eff.reasoningEffort}`}`}`);
  out.push(row === undefined
    ? `  profiles/${report.profile}/cordis.patch.yml: not read (the composition failed before it)`
    : row === null
      ? `  profiles/${report.profile}/cordis.patch.yml has NO ${DEFAULT_MODEL_ROW_ID} row - add the D2 row (runbook step 4)`
      : `  profiles/${report.profile}/cordis.patch.yml sets it (${row.source}): ${JSON.stringify(row.config)}`);
  const st = report.settingsYaml;
  out.push(!st.present
    ? `  settings.yaml: absent${st.importedCopyPresent ? " (settings.yaml.imported present: a 0.2.0 CLI already imported it - D12)" : ""}`
    : `  settings.yaml: ${st.error === undefined ? `agent-default-model ${JSON.stringify(st.agentDefaultModel)}` : `unreadable: ${st.error}`}` +
      " - the 0.2.0 face does not read it (D1)");
  const farm = report.linkFarm;
  out.push(farm.present
    ? `Link farm (D13): profiles/node_modules holds ${farm.symlinks} symlinks: ` +
      Object.entries(farm.targets ?? {}).map(([target, n]) => `${n} -> ${tilde(target)}`).join(", ")
    : "Link farm (D13): profiles/node_modules absent");
  out.push("");
  out.push(report.writes.boot.length === 0 ? "What the boot wrote in the copy: nothing" : "What the boot wrote in the copy:");
  for (const line of describeChanges(report.writes.boot)) out.push(`    ${line}`);
  if (report.boot.ok) {
    out.push(report.writes.sessionsTouchedByScan.length === 0
      ? "Scan window: nothing under sessions/ changed - the read-opens wrote nothing"
      : `Scan window: ${report.writes.sessionsTouchedByScan.length} change(s) under sessions/ - UNEXPECTED, see the report`);
    const other = report.writes.scanWindow.filter((c) => !c.path.startsWith("sessions/"));
    if (other.length > 0) out.push(`  (host background writes in the same window: ${describeChanges(other, 4).join("; ")})`);
    if (report.writes.dispose.length > 0) out.push(`At shutdown: ${describeChanges(report.writes.dispose, 4).join("; ")}`);
  }
  if (report.warnings.length > 0) {
    out.push("");
    out.push(`Warnings (${report.warnings.length}):`);
    for (const w of report.warnings) out.push(`  ${w}`);
  }
  out.push("");
  out.push(`Report: ${reportPath}`);
  out.push("");
  const grant = report.writes.boot.some((c) => c.path === ".credentials.yaml");
  out.push("DELETE THE COPY NOW. It holds .credentials.yaml (your API key" +
    (grant ? ", and the browser-session signing secret this dry run wrote into it" : "") + ")");
  out.push("and every session log. The report beside it holds no credential values.");
  out.push(`    rm -rf '${report.copy}'`);
  return out.join("\n");
}

/* ------------------------------------------------------------------- main */

/** A structural view of the services the scan reads from the booted tree. */
interface ScanServices {
  sessionPersistence: {
    list(): Promise<ReadonlyArray<{ header: { id: unknown; cwd?: string; agentPreset?: string; parentSession?: unknown } }>>;
    open(id: string, access: "read"): Promise<{ read(): Promise<{ events: readonly unknown[] }>; close(): Promise<void> }>;
  };
  agentPresets: { list(): Promise<Array<{ id: string; broken?: string }>> };
  agentDefaultModel?: { currentSelection(): unknown };
  loader?: { entries(): Iterable<{ options: { id: string; name: string }; readonly disabled: boolean }> };
}

/**
 * The dry run. Returns the exit code; never exits the process itself.
 * @param args - the command-line arguments after the script path.
 * @param env - where `DSH_HOME` and `FACE_PROFILE` are read from.
 */
export async function runCheckHome(args: readonly string[], env: NodeJS.ProcessEnv = process.env): Promise<number> {
  const profileName = env.FACE_PROFILE || "face";
  const liveHomes = liveHomeCandidates(env);
  const target = args.length > 1
    ? { ok: false as const, reason: `one argument only (got ${args.length}): the path of the COPY` }
    : checkTarget(args[0], liveHomes, profileName);
  if (!target.ok) {
    process.stderr.write(`check-home: REFUSED - ${target.reason}\n`);
    return EXIT_REFUSED;
  }
  const copy = target.copy;
  const reportPath = reportPathFor(copy);
  const report: CheckHomeReport = {
    tool: "face/scripts/check-home.ts",
    dshPin: DSH_PIN,
    generatedAt: new Date().toISOString(),
    copy,
    liveHomes,
    profile: profileName,
    boot: { ok: false, mcpRowsDisabled: [] },
    defaultModel: {},
    settingsYaml: inspectSettings(copy),
    linkFarm: inspectLinkFarm(copy),
    roster: [],
    sessions: {
      listed: 0, readable: 0, refused: 0,
      byClass: { "room-source": [], "subagent-descriptor": [], "seq-gap": [], other: [] },
      orphanedPresets: [], rawEvents: { total: 0, refused: 0 }, bytes: { total: 0, refused: 0 }, notListed: [], items: [],
    },
    writes: { boot: [], scanWindow: [], dispose: [], sessionsTouchedByScan: [] },
    warnings: [],
  };
  const finish = (code: number): number => {
    writeFileSync(reportPath, JSON.stringify(report, null, 2) + "\n", { mode: 0o600 });
    process.stdout.write(summarize(report, reportPath) + "\n");
    return code;
  };

  const before = inventory(copy);
  const raw = scanRawSessions(copy);
  /* As main.ts: the telemetry opt-out, and the repository root as the working
   * directory (it decides which project `.env` loadLayeredEnv reads). */
  process.env.DSH_TELEMETRY_DISABLED = "1";
  process.chdir(fileURLToPath(new URL("../../", import.meta.url)));
  /* A plugin failing in the background must not kill the run before the report
   * exists; it is recorded and printed instead. Removed before returning. */
  const onRejection = (reason: unknown): void => { report.warnings.push(`unhandled rejection: ${messageOf(reason)}`); };
  const onException = (err: unknown): void => { report.warnings.push(`uncaught exception: ${messageOf(err)}`); };
  process.on("unhandledRejection", onRejection);
  process.on("uncaughtException", onException);
  try {
    /* Loaded only now: a refused run never imports a dsh plugin. */
    const { bootFace, composeFace } = await import("../src/boot.ts");
    const { composeEntries } = await import("@deepseek-ai/dsh-app-boot");
    let booted: Awaited<ReturnType<typeof bootFace>>;
    try {
      /* A dry composition first (no boot): it names every MCP row the tree
       * would mount, and the operator's own D2 row. */
      const dry = composeFace({ profileName, port: 0, dshHome: copy });
      report.defaultModel.profilePatchRow =
        findPatchRow(dry.profile.patches as unknown as Record<string, unknown>[], DEFAULT_MODEL_ROW_ID) ?? null;
      const mcp = mcpRowsIn(composeEntries([dry.patches]) as EntryLike[]);
      const unaddressable = mcp.filter((row) => row.id === undefined);
      if (unaddressable.length > 0) {
        throw new Error(`${unaddressable.length} MCP row(s) have no id, so no patch can disable them - ` +
          "refusing to boot a dry run that would spawn them");
      }
      const ids = [...new Set([...mcp.map((row) => row.id as string), ALPACA_KIT_ROW_ID, AKSHARE_MCP_ROW_ID])];
      report.boot.mcpRowsDisabled = ids.map((id) => ({
        id,
        ...((({ serverName }) => serverName === undefined ? {} : { serverName })(mcp.find((row) => row.id === id) ?? {})),
        present: mcp.some((row) => row.id === id),
      }));
      const extraPatches: FacePatchList = ids.map((id) => ({ id, disabled: true }));
      const options: FaceBootOptions = { profileName, port: 0, dshHome: copy, extraPatches };
      booted = await bootFace(options);
      report.boot.ok = true;
    } catch (err) {
      report.boot.error = messageOf(err);
      report.writes.boot = diffInventory(before, inventory(copy));
      return finish(EXIT_INCOMPLETE);
    }
    const afterBoot = inventory(copy);
    report.writes.boot = diffInventory(before, afterBoot);
    let afterScan = afterBoot;
    try {
      const services = booted.ctx as unknown as { get<K extends keyof ScanServices>(name: K): ScanServices[K] | undefined };
      /* The dry run's own promise: nothing it disabled came up anyway. */
      for (const entry of services.get("loader")?.entries() ?? []) {
        let enabled: boolean;
        try {
          enabled = !entry.disabled;
        } catch {
          enabled = true;
        }
        if (entry.options.name === MCP_CLIENT_PACKAGE && enabled) {
          report.warnings.push(`MCP row ${entry.options.id} is ENABLED in the dry-run tree`);
        }
      }
      const presets = services.get("agentPresets");
      const persistence = services.get("sessionPersistence");
      if (presets === undefined || persistence === undefined) {
        throw new Error("the booted tree has no agentPresets or sessionPersistence service");
      }
      report.roster = (await presets.list()).map((p) => (p.broken === undefined ? { id: p.id } : { id: p.id, broken: p.broken }));
      report.defaultModel.effective = services.get("agentDefaultModel")?.currentSelection();
      const roster = new Map(report.roster.map((p) => [p.id, p]));
      const snapshots = await persistence.list();
      report.sessions.listed = snapshots.length;
      for (const snapshot of snapshots) {
        const id = String(snapshot.header.id);
        const { cwd, agentPreset } = snapshot.header;
        const parentSession = snapshot.header.parentSession === undefined ? undefined : String(snapshot.header.parentSession);
        const listed = agentPreset === undefined ? undefined : roster.get(agentPreset);
        const finding: SessionFinding = {
          id,
          ...(cwd === undefined ? {} : { cwd }),
          ...(agentPreset === undefined ? {} : { agentPreset }),
          ...(parentSession === undefined ? {} : { parentSession }),
          readable: false,
          preset: agentPreset === undefined ? "default" : listed === undefined ? "orphaned" : listed.broken === undefined ? "listed" : "broken",
          ...(raw.has(id) ? { raw: raw.get(id) } : {}),
        };
        try {
          const handle = await persistence.open(id, "read");
          try {
            finding.eventCount = (await handle.read()).events.length;
            finding.readable = true;
          } finally {
            await handle.close();
          }
        } catch (err) {
          const name = err instanceof Error ? err.name : "Error";
          finding.error = { name, message: messageOf(err) };
          finding.refusal = classifyRefusal(finding.error, finding.raw?.sourceKinds);
        }
        report.sessions.items.push(finding);
      }
      const items = report.sessions.items;
      report.sessions.readable = items.filter((i) => i.readable).length;
      report.sessions.refused = items.length - report.sessions.readable;
      for (const item of items) if (item.refusal !== undefined) report.sessions.byClass[item.refusal].push(item.id);
      report.sessions.orphanedPresets = items.flatMap((i) => i.preset === "orphaned" && i.agentPreset !== undefined
        ? [{ id: i.id, agentPreset: i.agentPreset }] : []);
      for (const item of items) {
        report.sessions.rawEvents.total += item.raw?.rawEvents ?? 0;
        report.sessions.bytes.total += item.raw?.bytes ?? 0;
        if (!item.readable) {
          report.sessions.rawEvents.refused += item.raw?.rawEvents ?? 0;
          report.sessions.bytes.refused += item.raw?.bytes ?? 0;
        }
      }
      const listedIds = new Set(items.map((i) => i.id));
      report.sessions.notListed = [...raw.keys()].filter((id) => !listedIds.has(id));
      report.scan = { ok: true };
    } catch (err) {
      report.scan = { ok: false, error: messageOf(err) };
    } finally {
      afterScan = inventory(copy);
      report.writes.scanWindow = diffInventory(afterBoot, afterScan);
      report.writes.sessionsTouchedByScan = report.writes.scanWindow.filter((c) => c.path.startsWith("sessions/"));
      try {
        await booted.dispose();
      } catch (err) {
        report.warnings.push(`dispose failed: ${messageOf(err)}`);
      }
    }
    report.writes.dispose = diffInventory(afterScan, inventory(copy));
    return finish(report.scan?.ok === true ? 0 : EXIT_INCOMPLETE);
  } finally {
    process.off("unhandledRejection", onRejection);
    process.off("uncaughtException", onException);
  }
}

/* Run only as a script (the tests import the functions above). Compared as
 * real paths: tsx and a symlinked checkout may spell the same file two ways. */
const invokedAs = process.argv[1];
if (invokedAs !== undefined && existsSync(invokedAs) &&
  realpathSync(invokedAs) === realpathSync(fileURLToPath(import.meta.url))) {
  const code = await runCheckHome(process.argv.slice(2));
  process.exitCode = code;
  /* Everything was disposed; this only guards against a handle some plugin
   * leaked, which would otherwise hold the process open. Unref'd: it never
   * keeps a finished process alive. */
  setTimeout(() => process.exit(code), 10_000).unref();
}
