/** `$DSH_HOME/face/channels.json`: which agents a channel offers Kairos.
 *
 * Operator-owned and keyed by workspace id, so renaming a directory does not
 * lose it. Two properties this file needs that the face's other state files
 * do not: the RECONCILE writes it (seeding a newly adopted channel) and the
 * reconcile runs on a GET, so unlike agents.json/archived.json its writers
 * are not serialized by the operator's own clicking — hence the lock. And it
 * fails CLOSED: an unparseable file reads as "no rosters", which refuses
 * every agent call rather than silently offering everything.
 *
 * What this is NOT: containment. dsh registers agent tools tree-wide with no
 * per-session scope, and Kairos has an unrestricted shell and unrestricted
 * network. The roster is a menu that states intent; see spec §5.
 * @module
 */
import { mkdir, readFile } from "node:fs/promises";
import { join } from "node:path";
import { withFileLock, writeFileAtomic } from "@deepseek-ai/dsh-atomic-write";

const ROSTER_FILE = ["face", "channels.json"] as const;

/** The on-disk shape. `version` exists so a later change can migrate rather
 * than guess. */
export interface RosterFile {
  version: 1;
  channels: Record<string, { agents: string[] }>;
}

const pathOf = (home: string): string => join(home, ...ROSTER_FILE);

/** Parse defensively: unknown shapes read as empty, junk entries drop, and
 * an unparseable file is reported so callers can fail closed. */
export async function readRosters(home: string): Promise<{ rosters: RosterFile["channels"]; corrupt: boolean }> {
  let text: string;
  try {
    text = await readFile(pathOf(home), "utf8");
  } catch {
    return { rosters: {}, corrupt: false }; // absent is not corrupt
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { rosters: {}, corrupt: true };
  }
  if (parsed === null || typeof parsed !== "object") return { rosters: {}, corrupt: true };
  const { channels } = parsed as { channels?: unknown };
  if (channels === null || typeof channels !== "object") return { rosters: {}, corrupt: true };
  const rosters: RosterFile["channels"] = {};
  for (const [id, row] of Object.entries(channels as Record<string, unknown>)) {
    if (row === null || typeof row !== "object") continue;
    const { agents } = row as { agents?: unknown };
    if (!Array.isArray(agents)) continue;
    const bins: string[] = [];
    for (const bin of agents) {
      if (typeof bin !== "string" || bin === "" || bins.includes(bin)) continue;
      bins.push(bin);
    }
    rosters[id] = { agents: bins };
  }
  return { rosters, corrupt: false };
}

/** Read-modify-write inside one cross-process lock. `mutate` returns the new
 * channels map, or `null` to leave the file untouched.
 *
 * The read happens INSIDE `withFileLock`, not before it: this file is seeded
 * from the GET path, so a reconcile and an operator's toggle can start
 * within the same tick. If the read ran outside the lock, the second writer
 * would already hold a stale snapshot by the time it got the lock and would
 * commit right over the first writer's change — the exact silent-revert this
 * store exists to prevent. */
async function update(
  home: string,
  mutate: (current: { rosters: RosterFile["channels"]; corrupt: boolean }) => RosterFile["channels"] | null,
): Promise<void> {
  const file = pathOf(home);
  // withFileLock creates the lock beside `file`; the parent directory must
  // already exist for that `wx` create to succeed on a fresh $DSH_HOME.
  await mkdir(join(home, ROSTER_FILE[0]), { recursive: true });
  await withFileLock(file, async () => {
    const current = await readRosters(home);
    const next = mutate(current);
    if (next === null) return;
    const doc: RosterFile = { version: 1, channels: next };
    await writeFileAtomic(file, `${JSON.stringify(doc, null, 2)}\n`, { mode: 0o600 });
  });
}

/** Give a newly adopted channel its starting roster. A no-op when the channel
 * already has one, and a no-op when the file is corrupt — a background seed
 * must never clobber a file the operator can still repair by hand. */
export async function seedRoster(home: string, workspaceId: string, bins: readonly string[]): Promise<void> {
  await update(home, ({ rosters, corrupt }) => {
    if (corrupt || Object.hasOwn(rosters, workspaceId)) return null;
    return { ...rosters, [workspaceId]: { agents: [...bins] } };
  });
}

/** The operator's explicit write: this channel's roster is exactly `bins`.
 * Allowed over a corrupt file — an operator action is a repair. */
export async function setRoster(home: string, workspaceId: string, bins: readonly string[]): Promise<void> {
  await update(home, ({ rosters }) => ({ ...rosters, [workspaceId]: { agents: [...new Set(bins)] } }));
}

/** This channel's roster, or `null` when none is known — an unadopted
 * channel, or a corrupt file. `null` is the fail-closed reading. */
export async function rosterFor(home: string, workspaceId: string): Promise<string[] | null> {
  const { rosters } = await readRosters(home);
  return Object.hasOwn(rosters, workspaceId) ? [...rosters[workspaceId].agents] : null;
}
