/** The face's dsh boot: a mirror of the dsh CLI's PRIVATE profile composition.
 *
 * Source of the mirror, pinned: `@deepseek-ai/dsh` 0.1.1-rc.2, chunk
 * `lib/profile-boot-DG5t9aNs.js` — functions `prepareProfile`,
 * `composeProfile`, `resolveTelemetryPatch` and `runProfile`. The CLI exports
 * none of them (they leave that chunk as single letters), so the face restates
 * them against the package `.d.ts` surface it does export. On every DSH_PIN
 * bump, re-diff this file against the CLI's current `profile-boot-*.js`
 * (spec section 4) — a composition that drifts boots a different tree while
 * still typechecking.
 *
 * Deliberate divergences from `runProfile`, all v1 scope cuts:
 * - no `--patch` overlay files: the face takes its host rows from
 *   {@link faceOverlay} and its operator rows from the profile's patch layer;
 * - no HMR / `watchUserPatches` reload of the patch layers — a face restart is
 *   the reload. dsh-base's `hmr` row is disabled here for the same reason the
 *   shipped mode bundles disable it: see {@link HMR_ROW_ID};
 * - no `installFailLoud` and no bounded process-shutdown controller: the face
 *   is a library booted by `main.ts`, which owns signals and exit codes;
 * - no shipped agent-presets root graft: that root ships beside the CLI's own
 *   app package, which is not in the face's dependency tree at all;
 * - {@link INSTALL_ANCHOR} is the FACE's package.json, not the CLI's — see there.
 * The telemetry opt-out is honored exactly as the CLI honors it.
 * @module
 */
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Context } from "@deepseek-ai/cordis";
import {
  boot,
  composeEntries,
  healProfilesModuleFallback,
  loadLayeredEnv,
  loadOptionalPatches,
  loadProfile,
  PROFILE_PATCH_FILENAME,
} from "@deepseek-ai/dsh-app-boot";
import { resolveDshHome } from "@deepseek-ai/dsh-home-paths";
import { DSH_LAUNCH_ENVIRONMENT_KEY } from "@deepseek-ai/dsh-launch-environment";
import { provideCmdline } from "@deepseek-ai/dsh-cmdline";
import { faceOverlay } from "./overlay.ts";

/** Diagnostic prefix dsh-app-boot puts on every error and warning raised from
 * here. Purely a label (nothing branches on it), so it names the face rather
 * than borrowing the CLI's `dsh` — an operator reading a stack must be able to
 * tell a face composition failure from a `dsh` one. */
const BIN = "kairos-face";

/** Absolute path of the face's OWN package.json — the first module-resolution
 * anchor for profile bundles, and the manifest whose dependency closure
 * {@link healProfilesModuleFallback} links into `$DSH_HOME/profiles/node_modules`
 * so a bare plugin name in a patch row resolves from the profile directory.
 * The CLI anchors on the dsh app's package.json for exactly this reason; here
 * the face IS the installed app, and `face/node_modules` is where dsh-base and
 * every host plugin actually live. It must be the package.json FILE and not its
 * directory: `healProfilesModuleFallback` reads and parses it. */
const INSTALL_ANCHOR = fileURLToPath(new URL("../package.json", import.meta.url));

/** The session-telemetry row id `DSH_TELEMETRY_DISABLED` targets, verbatim from
 * the CLI. dsh-base mounts this row, so the switch is live for the face; a
 * patch aimed at an absent row would apply to nothing and disable nothing. */
const TELEMETRY_ROW_ID = "session-telemetry-otel";

/** dsh-base's Cordis hot-reload row. It is a DEV-mode row: the plugin throws
 * `--expose-internals is required for HMR service` under any ordinary `node`,
 * so a tree carrying it enabled cannot boot from a plain bin — which is why
 * both shipped mode bundles (`dsh-web-app`, `dsh-headless`) open their patch
 * layer by disabling it. The face is its own mode bundle and does the same. */
const HMR_ROW_ID = "hmr";

/** Root config filename inside a profile directory (the CLI's private
 * `PROFILE_ROOT_FILENAME`; dsh-app-boot exports only the patch filename). */
const PROFILE_ROOT_FILENAME = "cordis.yml";

/** The empty root entry list the whole face tree patches over. */
const PROFILE_ROOT_CONFIG = `# kairos-face profile root - an empty entry list. The tree is composed as
# patches: each bundle in package.json's dsh.profile.bundles, then
# cordis.patch.yml, then the face's own host rows. Edit cordis.patch.yml,
# not this file - kairos-face rewrites it on every boot.
[]
`;

/** The patch-list type {@link boot} accepts. Taken from the pinned signature
 * rather than by importing `@deepseek-ai/cordis-plugin-include`, which the face
 * does not declare as a dependency: the contract is "whatever boot takes". */
export type FacePatchList = NonNullable<Parameters<typeof boot>[2]>;

/** What a face boot needs to know. `dshHome` overrides `$DSH_HOME` for this
 * composition; {@link bootFace} additionally materializes it (see there). */
export interface FaceBootOptions {
  /** Profile directory name under `$DSH_HOME/profiles`. */
  profileName: string;
  /** TCP port for the webserver row; `0` asks the OS for a free one. */
  port: number;
  /** Harness home override, highest precedence (see `resolveDshHome`). */
  dshHome?: string;
}

/** Top-level row ids of the tree these layers compose to, through the include's
 * own patch algorithm — the same single `applyEntryPatches` call boot makes, so
 * a switch that asks "is this row in the tree?" sees what will actually mount. */
function composedRowIds(layers: readonly FacePatchList[]): Set<string> {
  const ids = new Set<string>();
  for (const row of composeEntries(layers)) if (typeof row.id === "string") ids.add(row.id);
  return ids;
}

/** Resolve the telemetry opt-out switch into its boot patch, mirroring the
 * CLI's `resolveTelemetryPatch`. ANY non-empty value (including `'0'` and
 * `'false'`) disables: a privacy switch prefers off-by-mistake over
 * on-by-mistake. A composition without the row needs no patch, so a profile
 * that never mounts telemetry satisfies the switch trivially. */
function resolveTelemetryPatch(disabledEnv: string | undefined, hasRow: boolean): FacePatchList[number] | undefined {
  if ((disabledEnv ?? "") === "" || !hasRow) return undefined;
  return { id: TELEMETRY_ROW_ID, disabled: true };
}

/**
 * Compose the face's full patch stack over its profile, in application order:
 * bundle layers in `dsh.profile.bundles` order, the profile's own user layer,
 * the machine-local home layer (`$DSH_HOME/cordis.patch.yml`, which outranks
 * the per-profile one), the telemetry switch, then the face's host rows last.
 *
 * Pure with respect to the environment — the home is threaded explicitly into
 * every dsh-app-boot call rather than materialized into `$DSH_HOME` — but NOT
 * pure with respect to the disk: it heals the shared module fallback and
 * rewrites the profile root, both of which boot requires.
 * @param opts - profile name, webserver port, optional harness home.
 * @returns the composed patch stack and the absolute root config path to boot.
 * @throws when the profile does not exist or a bundle/patch file cannot load.
 */
export function composeFace(opts: FaceBootOptions): { patches: FacePatchList; rootConfig: string } {
  const home = resolveDshHome(opts.dshHome);
  healProfilesModuleFallback(INSTALL_ANCHOR, home);
  const profile = loadProfile(BIN, opts.profileName, INSTALL_ANCHOR, home, { userLayer: true });
  const rootConfig = join(profile.dir, PROFILE_ROOT_FILENAME);
  /* Always rewritten, never merely created: the whole composition is patch
   * layers, and the vendored Loader's tree write-back (a plugin disposing
   * itself persists the settled tree) can bake composed rows into this file,
   * which would duplicate every bundle insert on the next boot. The file
   * exists on disk only because the Loader needs a real include root to anchor
   * `baseUrl` at the profile directory. */
  writeFileSync(rootConfig, PROFILE_ROOT_CONFIG);
  const bundlePatches = profile.layers.flatMap((layer) => layer.patches);
  const homePatches = loadOptionalPatches(BIN, join(home, PROFILE_PATCH_FILENAME)) ?? [];
  const patches: FacePatchList = [...bundlePatches, ...profile.patches, ...homePatches];
  /* Both switches below are guarded on the row actually being in the composed
   * tree: a patch that matches nothing is inert AND warns at boot, so a profile
   * that never mounts the row must not be told to patch it. */
  const rows = composedRowIds([bundlePatches, profile.patches, homePatches]);
  const telemetry = resolveTelemetryPatch(process.env.DSH_TELEMETRY_DISABLED, rows.has(TELEMETRY_ROW_ID));
  if (telemetry !== undefined) patches.push(telemetry);
  if (rows.has(HMR_ROW_ID)) patches.push({ id: HMR_ROW_ID, disabled: true });
  patches.push(...faceOverlay(opts.port));
  return { patches, rootConfig };
}

/** Services the face's Gate 2 (spec section 3.2) routes every tool decision
 * through. dsh-base mounts both; a profile that dropped them would still boot,
 * and every approval would then fail closed with nothing on screen saying why. */
const GATE_2_SERVICES = ["approval", "userQuestions"] as const;

/**
 * Boot the face's dsh tree in-process and return it with its disposer.
 *
 * Unlike {@link composeFace} this materializes `$DSH_HOME` when `dshHome` is
 * given: the booted tree resolves its own harness home from the environment
 * (`boot` hands `dshHomePath` to config expressions, `loadLayeredEnv` reads
 * `$DSH_HOME/.env`, and mounted plugins call `resolveDshHome()` themselves), so
 * without this the composition would read one home and the running tree
 * another — sessions and credentials landing in `~/.dsh` while the profile came
 * from the override.
 * @param opts - profile name, webserver port, optional harness home.
 * @returns the settled root context and an idempotent disposer.
 * @throws after disposing the tree when a Gate 2 service is missing, and
 * whatever `boot` throws when the plugin tree fails to load.
 */
export async function bootFace(opts: FaceBootOptions): Promise<{ ctx: Context; dispose(): Promise<void> }> {
  if (opts.dshHome !== undefined) process.env.DSH_HOME = resolveDshHome(opts.dshHome);
  const environment = loadLayeredEnv(BIN);
  const { patches, rootConfig } = composeFace(opts);
  /* The CLI's own holder pattern: `prepare` runs before boot resolves, so a row
   * that requests exit while the tree is still mounting must still reach a real
   * context to dispose. */
  const app: { current?: Context } = {};
  let disposed = false;
  const dispose = async (): Promise<void> => {
    if (disposed) return;
    disposed = true;
    await app.current?.fiber.dispose();
  };
  const ctx = await boot(BIN, rootConfig, structuredClone(patches), (hostCtx) => {
    app.current = hostCtx;
    hostCtx.provide(DSH_LAUNCH_ENVIRONMENT_KEY, environment);
    /* No command line: the face is not a launcher, so the tree sees an empty
     * argument list, and `ctx.appExit` is a bare process exit. The CLI's
     * bounded, escalating shutdown controller is a v1 scope cut - awaiting an
     * unbounded dispose inside an exit request would trade a hard exit for a
     * hang, which is the worse failure for a request to stop. */
    provideCmdline(hostCtx, { args: [], exit: (code) => process.exit(code) });
  });
  app.current = ctx;
  const missing = GATE_2_SERVICES.filter((name) => ctx.get(name) === undefined);
  if (missing.length > 0) {
    await dispose();
    throw new Error(
      `${BIN}: ${missing.join(" and ")} missing from the composed tree - Gate 2 would fail closed invisibly` +
        ` (profile ${JSON.stringify(opts.profileName)} must bundle @deepseek-ai/dsh-base)`,
    );
  }
  return { ctx, dispose };
}
