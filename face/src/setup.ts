/** One-shot setup of the face's dsh profile at `$DSH_HOME/profiles/face`.
 *
 * The profile bundles ONLY `@deepseek-ai/dsh-base` — the face's own host rows
 * (webserver, api gateway, connection, ...) are inserted programmatically at
 * boot by `faceOverlay()`, never written to disk. The written patch layer is
 * therefore empty: it belongs to the operator.
 *
 * The three written files mirror dsh-app-boot's own `initProfile` (manifest,
 * patch layer, pnpm settings) so a face profile is indistinguishable from one
 * `dsh plugin` made — with one deliberate difference: dsh fills in per missing
 * file, the face refuses per directory. See {@link setupFaceProfile}.
 * @module
 */
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";

const PROFILE_PKG = {
  name: "dsh-profile-face",
  private: true,
  dependencies: {},
  dsh: { profile: { bundles: ["@deepseek-ai/dsh-base"] } },
};

/* The trailing `[]` is load-bearing, not decoration. dsh-app-boot parses this
 * file with `parsePatchList`, which throws "must be a top-level YAML array of
 * loader patch entries" on anything that is not an array — and a comment-ONLY
 * YAML document parses to `undefined`. A header with no `[]` would therefore
 * hard-fail boot the moment the profile loaded. dsh's own initProfile template
 * ends with the same `[]` for the same reason. Covered by the loader test. */
const PATCH_HEADER = `# face profile patch layer. The face's own host rows (webserver :3090,
# api gateway, connection) are inserted programmatically by kairos-face at
# boot - do NOT add them here. This file is the operator's: mount the
# alpaca_kit MCP server and skill roots here per dsh/README.md steps 3-6.
#
# Face-owned rows are applied AFTER this file and win over it, silently: a
# patch here targeting webserver, connection, api-gateway, directory-picker,
# cordis-host-runner, the storage chain (storage, storage-json,
# storage-domain, workspace), or the hmr / session-telemetry-otel switches is
# accepted, overridden, and never reported. Change those in kairos-face's
# overlay, not here.
[]
`;

/* Verbatim from dsh-app-boot's PROFILE_PNPM_WORKSPACE: the pnpm settings an
 * out-of-tree plugin needs to install into this profile. Omitting it leaves a
 * profile that works until the operator runs `dsh plugin add`. */
const PNPM_WORKSPACE = `packages:
  - .

nodeLinker: hoisted
autoInstallPeers: false
`;

/** Create $DSH_HOME/profiles/<name>. Profiles are operator territory: an
 * existing directory is NEVER touched (created: false). */
export function setupFaceProfile(dshHome: string, profileName = "face"): { created: boolean; dir: string } {
  const dir = join(dshHome, "profiles", profileName);
  if (existsSync(dir)) return { created: false, dir };
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "package.json"), JSON.stringify(PROFILE_PKG, null, 2) + "\n");
  writeFileSync(join(dir, "cordis.patch.yml"), PATCH_HEADER);
  writeFileSync(join(dir, "pnpm-workspace.yaml"), PNPM_WORKSPACE);
  return { created: true, dir };
}

/* `fileURLToPath`, not `file://` + argv[1]: the naive concatenation compares a
 * percent-ENCODED URL against a raw path, so it silently no-ops (exit 0, no
 * output, nothing created) for any checkout under a directory with a space or
 * a non-ASCII character in its name. `||` not `??` on FACE_PROFILE so an empty
 * value falls back to "face" instead of resolving to $DSH_HOME/profiles. */
if (fileURLToPath(import.meta.url) === process.argv[1]) {
  const home = process.env.DSH_HOME ?? join(homedir(), ".dsh");
  const res = setupFaceProfile(home, process.env.FACE_PROFILE || "face");
  console.log(res.created ? `created ${res.dir}` : `exists, untouched: ${res.dir}`);
}
