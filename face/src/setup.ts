/** One-shot setup of the face's dsh profile at `$DSH_HOME/profiles/face`.
 *
 * The profile bundles ONLY `@deepseek-ai/dsh-base` — the face's own host rows
 * (webserver, api gateway, connection, ...) are inserted programmatically at
 * boot by `faceOverlay()`, never written to disk. The written patch layer is
 * therefore empty: it belongs to the operator.
 * @module
 */
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";

const PROFILE_PKG = {
  name: "dsh-profile-face",
  private: true,
  dependencies: {},
  dsh: { profile: { bundles: ["@deepseek-ai/dsh-base"] } },
};

const PATCH_HEADER = `# face profile patch layer. The face's own host rows (webserver :3090,
# api gateway, connection) are inserted programmatically by kairos-face at
# boot - do NOT add them here. This file is the operator's: mount the
# alpaca_kit MCP server and skill roots here per dsh/README.md steps 3-6.
`;

/** Create $DSH_HOME/profiles/<name>. Profiles are operator territory: an
 * existing directory is NEVER touched (created: false). */
export function setupFaceProfile(dshHome: string, profileName = "face"): { created: boolean; dir: string } {
  const dir = join(dshHome, "profiles", profileName);
  if (existsSync(dir)) return { created: false, dir };
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "package.json"), JSON.stringify(PROFILE_PKG, null, 2) + "\n");
  writeFileSync(join(dir, "cordis.patch.yml"), PATCH_HEADER);
  return { created: true, dir };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const home = process.env.DSH_HOME ?? join(homedir(), ".dsh");
  const res = setupFaceProfile(home);
  console.log(res.created ? `created ${res.dir}` : `exists, untouched: ${res.dir}`);
}
