// face/tests/bots-fixture.ts
import { mkdtemp, mkdir, writeFile, cp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
/** Absolute path of the real plugin file: a temp bots root cannot reach it by `../../face/…`. */
export const PLUGIN_ABS = join(REPO, "face", "plugins", "bot.js");

/** A throwaway `bots/` root: the repo's real `_template`, an inert `kairos`, and nothing else. */
export async function makeBotsRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "face-bots-"));
  await cp(join(REPO, "bots", "_template"), join(root, "_template"), { recursive: true });
  await mkdir(join(root, "kairos"));
  await writeFile(join(root, "kairos", "agent.cordis.yml"), "[]\n");
  await writeFile(join(root, "kairos", "preset.yml"), "name: Kairos\ndescription: the principal agent\n");
  return root;
}
