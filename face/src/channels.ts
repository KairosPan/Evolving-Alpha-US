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
import { readdir, readFile, stat } from "node:fs/promises";
import { join } from "node:path";
import { load } from "js-yaml";

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
    /* verbatim from strategies.ts:66 — the copy source is never a channel */
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
