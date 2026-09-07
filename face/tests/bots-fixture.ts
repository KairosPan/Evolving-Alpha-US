// face/tests/bots-fixture.ts
import { mkdtemp, mkdir, writeFile, cp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

/** The repository root — the anchor both roots below are measured from. */
export const REPO = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
/** Absolute path of the real plugin file: a temp bots root cannot reach it by `../../face/…`. */
export const PLUGIN_ABS = join(REPO, "face", "plugins", "bot.js");

/** The repo's real `_template`, an inert `kairos`, and nothing else. */
export async function populateBotsRoot(root: string): Promise<string> {
  await cp(join(REPO, "bots", "_template"), join(root, "_template"), { recursive: true });
  await mkdir(join(root, "kairos"));
  await writeFile(join(root, "kairos", "agent.cordis.yml"), "[]\n");
  await writeFile(join(root, "kairos", "preset.yml"), "name: Kairos\ndescription: the principal agent\n");
  return root;
}

/** A throwaway `bots/` root under the OS temp directory. Compositions made here
 *  must name the plugin by {@link PLUGIN_ABS}: `../../face/plugins/bot.js`
 *  resolves out of `$TMPDIR` and reaches nothing. */
export async function makeBotsRoot(): Promise<string> {
  return populateBotsRoot(await mkdtemp(join(tmpdir(), "face-bots-")));
}

/** A throwaway `bots/` root INSIDE the repository, two levels above
 *  `face/plugins/` exactly as the real `bots/` is — so a composition created
 *  here carries the SHIPPED relative plugin path (`BOT_PLUGIN_RELATIVE`) and
 *  mounting it executes the path the repository actually ships, not a fixture
 *  substitute. Gitignored as `.bots-smoke-*`; the caller must remove it. */
export async function makeRepoBotsRoot(): Promise<string> {
  return populateBotsRoot(await mkdtemp(join(REPO, ".bots-smoke-")));
}
