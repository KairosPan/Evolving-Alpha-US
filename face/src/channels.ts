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
import { readdir } from "node:fs/promises";
import { join } from "node:path";

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
 */
export async function listChannelDirs(root: string): Promise<ChannelDir[]> {
  const dirs: ChannelDir[] = [{ name: WORKBENCH, dir: root, isRoot: true }];
  let entries: import("node:fs").Dirent[] = [];
  try {
    entries = await readdir(join(root, "strategies"), { withFileTypes: true });
  } catch {
    /* no arena yet — the workbench is still a channel */
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
