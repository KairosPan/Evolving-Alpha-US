// face/tests/bots-fixture.ts
import { mkdtemp, mkdir, writeFile, cp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { entryListSchema } from "@deepseek-ai/cordis-plugin-include";
import { dump } from "js-yaml";
import { GRAVIT_PLUGIN_RELATIVE } from "../src/overlay.ts";
import { ROLE_TEMPLATE } from "../src/roles.ts";

/** The repository root — the anchor both roots below are measured from. */
export const REPO = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
/** Absolute path of the real plugin file. The face rebases a relative plugin
 *  row against `bots/<id>/` (src/bot-presets.ts), so from a temp root the
 *  shipped `../../face/…` lands under `$TMPDIR` and reaches nothing; a
 *  composition made there names this path instead (rebased to a `file:` URL). */
export const PLUGIN_ABS = join(REPO, "face", "plugins", "bot.js");
/** {@link PLUGIN_ABS} for Gravit's own plugin (`plugins/gravit.js`): what a
 *  temp root's `gravit` composition names, for the same reason. */
export const GRAVIT_PLUGIN_ABS = join(REPO, "face", "plugins", "gravit.js");

/** The repo's real `_template`, and a `gravit` whose composition is the
 *  repository's own shape: one row, the gravit plugin with `config: {}`.
 *  `gravitPlugin` spells that row's name. The default is the SHIPPED relative
 *  path, which the face's rebase lands on the real file only from a root two
 *  levels above `face/` (see {@link makeRepoBotsRoot}); a temp root passes
 *  {@link GRAVIT_PLUGIN_ABS}. Written with `dump` as `renderComposition` does.
 *  That `gravit` composition is documentation: the booted default is rendered
 *  from a roles root at compose time and `composeFace` never reads the file. */
export async function populateBotsRoot(root: string, gravitPlugin: string = GRAVIT_PLUGIN_RELATIVE): Promise<string> {
  await cp(join(REPO, "bots", "_template"), join(root, "_template"), { recursive: true });
  await mkdir(join(root, "gravit"));
  const rows = [{ id: "gravit", name: gravitPlugin, config: {} }];
  await writeFile(join(root, "gravit", "agent.cordis.yml"), dump(rows, { schema: entryListSchema, lineWidth: -1, noRefs: true }));
  await writeFile(join(root, "gravit", "preset.yml"), "name: Gravit\ndescription: the principal agent\n");
  return root;
}

/** A throwaway `bots/` root under the OS temp directory. Compositions made here
 *  must name the plugin by {@link PLUGIN_ABS} (and Gravit's by
 *  {@link GRAVIT_PLUGIN_ABS}, which this root's `gravit` does): the shipped
 *  `../../face/plugins/…`, rebased against a bot directory under `$TMPDIR`,
 *  reaches nothing. */
export async function makeBotsRoot(): Promise<string> {
  return populateBotsRoot(await mkdtemp(join(tmpdir(), "face-bots-")), GRAVIT_PLUGIN_ABS);
}

/** A throwaway `bots/` root INSIDE the repository, two levels above
 *  `face/plugins/` exactly as the real `bots/` is — so a composition created
 *  here carries the SHIPPED relative plugin path (`BOT_PLUGIN_RELATIVE`, and
 *  `GRAVIT_PLUGIN_RELATIVE` for the root's own `gravit`), the face's rebasing
 *  (src/bot-presets.ts) lands it on the real `face/plugins/bot.js` (and
 *  `gravit.js`), and mounting it executes the path the repository actually
 *  ships, not a fixture substitute. Gitignored as `.bots-smoke-*`; the caller
 *  must remove it. */
export async function makeRepoBotsRoot(): Promise<string> {
  return populateBotsRoot(await mkdtemp(join(REPO, ".bots-smoke-")));
}

/** A throwaway roles root with one valid role (`probe`) beside `_template`; the
 *  caller breaks it, or hands it to `composeFace` as `rolesRoot`. The caller
 *  removes it. */
export async function makeRolesRoot(): Promise<string> {
  const root = await mkdtemp(join(tmpdir(), "face-roles-"));
  await mkdir(join(root, ROLE_TEMPLATE));
  await writeFile(join(root, ROLE_TEMPLATE, "ROLE.md"), "You are <role name>.\n");
  await mkdir(join(root, "probe"));
  await writeFile(join(root, "probe", "ROLE.md"), "You are the probe, a test role.\n");
  await writeFile(join(root, "probe", "role.yml"), "name: Probe\ndescription: a test role\nallow:\n  - read\n  - mcp__alpaca-kit__earnings\n");
  return root;
}
