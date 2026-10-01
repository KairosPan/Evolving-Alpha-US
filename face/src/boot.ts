/** The face's dsh boot: a mirror of the dsh CLI's profile launcher.
 *
 * Source of the mirror, pinned: `@deepseek-ai/dsh` 0.2.0-rc.2, chunk
 * `lib/profile-boot-BZ2ZjNWi.js` — `prepareProfile`, `composeProfile` and
 * `runProfile` (NEW apps/cli/src/profile-boot.ts:167-173, 197-209, 244-326;
 * the chunk is byte-for-byte that logic). The CLI now also publishes them as
 * `@deepseek-ai/dsh/profile-boot`, a reading aid and NOT a dependency: taking
 * `runProfile` would bring `profileContext`, its own signal and fail-loud
 * handlers, an `appReady` committed before Gate 2 exists, and the whole CLI
 * dependency tree (MAP boot-mirror §8). On every DSH_PIN bump, re-diff this
 * file against the CLI's current `profile-boot-*.js` — a composition that
 * drifts boots a different tree while still typechecking.
 *
 * Module resolution is the new mandatory step. The 0.1.1 link farm
 * (`healProfilesModuleFallback` into `$DSH_HOME/profiles/node_modules`) is gone
 * upstream (commits 6aa2e4633c, 9fd0a5ad52); every bare row name now resolves
 * through an in-memory runtime resolution computed from {@link INSTALL_ANCHOR}
 * and installed by the `PluginPackages` service inside `prepare`
 * (NEW packages/boot/app-boot/src/profile.ts:416-464,
 * profile-resolution/service.ts:60-75). Without it a fresh home resolves no
 * dsh-base row at all.
 *
 * Deliberate divergences from `runProfile` (each one a decision, PLAN §6):
 * 1. No `--patch` overlay files: the face takes its host rows from
 *    {@link faceOverlay} and its operator rows from the profile's patch layer.
 * 2. No `profileContext` service (D1). With it, dsh-base's `settings` row
 *    would rename the operator's shared `$DSH_HOME/settings.yaml` on the first
 *    boot, and `config-editor`/`plugin-manager`/`dsh-hmr` would recompose the
 *    live tree from files that do not carry the face's programmatic layers —
 *    unmounting the webserver, the gateway rows and Gate 2's answerer
 *    (MAP boot-mirror §2.3). Consequences accepted: `settings/describe` has no
 *    service, and the operator's default model lives in the profile patch.
 * 3. No `installProxyFromEnvironment` (D10): 0.1.1 had no proxy policy, and it
 *    is not a no-op when `HTTP(S)_PROXY` is set — it would reroute the face's
 *    own quote and Alpaca fetches too (NEW packages/util/http-proxy/src/
 *    install.ts:62-68, 296-303).
 * 4. No `createProcessShutdown`, no SIGINT/SIGTERM and no `installFailLoud`
 *    here: `main.ts` owns process lifetime and installs `installFailLoud`
 *    itself; `ctx.appExit` stays a plain `process.exit`.
 * 5. `appReady` commits LAST, after the face's own audits — including the
 *    check that Gate 2 armed — not right after `boot()` as the CLI does. The
 *    gateway admits no `/api/remote.mux` stream until it fires (NEW
 *    packages/api/gateway/src/index.ts:265-276), so no browser can open an
 *    approval stream before the face is complete. The invariant that buys:
 *    every success path commits, or every stream stays dead with no error —
 *    the smoke's 101 upgrade is the proof. A tree that stopped during startup
 *    is refused, not returned uncommitted. `main.ts` moves the commit later
 *    still, after its own routes (`deferReady` + `BootedFace.commitReady`),
 *    so a reconnecting tab never finds `/data` half-mounted. This holds back
 *    the STREAMS only: unary `/api` is served from the moment the gateway row
 *    activates, mid-boot — which is why Gate 2 itself cannot wait for the
 *    commit (divergence 10).
 * 6. {@link INSTALL_ANCHOR} is the FACE's package.json, not the CLI's.
 * 7. A skipped bundle is a hard failure. `loadProfile` now SKIPS a bundle it
 *    cannot load instead of throwing (NEW packages/boot/app-boot/src/
 *    profile.ts:655-689; commit c8b10a16be); the CLI only reports it, but the
 *    face has one bundle and nothing works without it.
 * 8. A strict post-boot row audit ({@link assertEntriesActive}). NEW `boot()`
 *    fails only when one of seven required ids is inactive and merely WARNS on
 *    every other row (NEW packages/boot/app-boot/src/index.ts:746-754,
 *    925-939; commit bd4cfc7c46). 0.1.1 failed the boot on any inactive row;
 *    the face keeps that — a half-mounted trading workbench is worse than none.
 * 9. A face policy layer (src/policy.ts, PLAN S4) between the bundle layer and
 *    the operator's layers, restoring the 0.1.1 tool roster, egress and
 *    telemetry posture where dsh-base 0.2.0 changed them.
 * 10. Gate 2 for orders arms INSIDE `prepare` ({@link armOrderGate}), before
 *    the first config-tree row mounts — not after `boot()` resolves, where
 *    0.1.1 armed it. The gateway claims unary `/api` the moment its row
 *    activates and does not wait for readiness (NEW packages/api/gateway/src/
 *    index.ts:233-239; only the upgrade at :265-276 does), and an MCP row's
 *    tools are registered as that row activates. So for as long as ANY slow
 *    row held `boot()` open, a tab still holding its 30-day cookie could
 *    `session/create` and drive a turn into a live order tool while no ask
 *    listener and no guard existed: the order dispatched with no card
 *    (REVIEW-adversarial finding 1, proven by a probe;
 *    tests/order-gate-midboot-smoke.test.ts keeps it closed). Each half now
 *    waits, through `hostCtx.inject`, for exactly the service it reads — the
 *    guard for `tools`, the ask listener for `approval` — so the guard exists
 *    from the first moment the tool registry does, whatever order the rows
 *    activate in. Only the registrations moved: every audit still runs after
 *    `boot()`, plus {@link assertOrderGateArmed}.
 * The telemetry opt-out is honored exactly as the CLI honors it.
 *
 * LAYERING, and the one place the face inverts the CLI's: {@link faceOverlay}
 * composes LAST, after the profile's `cordis.patch.yml` and the home layer. In
 * the CLI the user's layers are the outermost word on every row. Here they are
 * not, for the rows the face owns — its host rows are its contract, not a
 * default, and loopback-only binding surviving an operator patch is the point
 * (spec section 3.2). The cost is real and was measured: an operator patch
 * aimed at `webserver` (or any other overlay-owned row) is silently overridden
 * — the face's `port` wins, and NOTHING is printed. The operator is warned
 * where they would actually look, in the patch file's own header
 * (`setup.ts` PATCH_HEADER). The policy layer is the opposite case: it sits
 * BELOW the operator's layers, so an operator row with the same id wins.
 * Note also that {@link composedRowIds} deliberately composes the layers BELOW
 * the overlay only: the row-presence switches ask "did the profile bring this
 * row?", which is a question about the tree the face is patching, not about
 * the face's own rows.
 * @module
 */
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Context, FiberState } from "@deepseek-ai/cordis";
import {
  boot,
  composeEntries,
  createRuntimeResolution,
  loadLayeredEnv,
  loadOptionalPatches,
  loadProfile,
  PluginPackages,
  PROFILE_PATCH_FILENAME,
  reportSkippedBundles,
  resolveTelemetryPatch,
  type Profile,
} from "@deepseek-ai/dsh-app-boot";
import { resolveDshHome } from "@deepseek-ai/dsh-home-paths";
import { DSH_LAUNCH_ENVIRONMENT_KEY } from "@deepseek-ai/dsh-launch-environment";
import { provideCmdline, type AppReady } from "@deepseek-ai/dsh-cmdline";
import type { Config as SystemPromptConfig } from "@deepseek-ai/dsh-system-prompt";
import { BOTS_ROOT, DEFAULT_PRESET, SYSTEM_PROMPT_ROW_ID, faceOverlay } from "./overlay.ts";
import { declareBots, definitionFor, type BotPresets } from "./bot-presets.ts";
import { PERSONA_PATH, readPersona } from "./persona.ts";
import { aksharePatches } from "./akshare.ts";
import { facePolicyPatches } from "./policy.ts";
import {
  auditOrderTools, effectiveApprovalPolicy, isOrderTool, orderApprovalDecision, orderGuardReasonForSession,
  type ApprovalPolicyLike, type PreToolDecision, type ToolSchemaLike,
} from "./orders.ts";

/** Diagnostic prefix dsh-app-boot puts on every error and warning raised from
 * here. Purely a label (nothing branches on it), so it names the face rather
 * than borrowing the CLI's `dsh` — an operator reading a stack must be able to
 * tell a face composition failure from a `dsh` one. */
const BIN = "kairos-face";

/** Absolute path of the face's OWN package.json — the anchor of the runtime
 * module resolution. `loadProfile` resolves each profile bundle from it first
 * (`resolveBundleDir`, installation before profile), and
 * `createRuntimeResolution({installAnchor})` walks its `dependencies` +
 * `peerDependencies` breadth-first to build the package table every bare row
 * name is answered from (NEW packages/boot/app-boot/src/profile.ts:363-414).
 * The CLI anchors on the dsh app's package.json for exactly this reason; here
 * the face IS the installed app, and `face/node_modules` is where dsh-base and
 * every host plugin actually live. It must be the package.json FILE and not its
 * directory: the resolution reads and parses it. (At 0.1.1 this was the heal
 * source of the `$DSH_HOME/profiles/node_modules` link farm; nothing writes
 * that farm now, and a stale one on a shared home is an operator concern —
 * PLAN D13.) */
const INSTALL_ANCHOR = fileURLToPath(new URL("../package.json", import.meta.url));

/** The session-telemetry row id `DSH_TELEMETRY_DISABLED` targets, verbatim from
 * the CLI. Not exported upstream (NEW packages/boot/app-boot/src/
 * profile-context.ts:39). dsh-base mounts this row, so the switch is live for
 * the face; a patch aimed at an absent row would apply to nothing and disable
 * nothing. */
const TELEMETRY_ROW_ID = "session-telemetry-otel";

/** dsh-base's live-reload row, now `@deepseek-ai/dsh-hmr` with
 * `disabled: !!js "!ctx.get('profileContext')"` (NEW packages/bundle/base/
 * cordis.patch.yml:27-32; commits fd814589fb, d06e6b5519). The face provides
 * no `profileContext` (divergence 2), so the row is already disabled by its
 * own expression; the face's `{ id: 'hmr', disabled: true }` stays as defence
 * in depth. Should anything ever provide `profileContext`, dsh-hmr would throw
 * without `--expose-internals` or `appReady` (NEW packages/boot/hmr/src/
 * index.ts:182, 208-209) — and, worse, reconcile the tree from files that do
 * not carry the face's layers. */
const HMR_ROW_ID = "hmr";

/** Root config filename inside a profile directory (the CLI's
 * `PROFILE_ROOT_FILENAME`; dsh-app-boot exports only the patch filename). */
const PROFILE_ROOT_FILENAME = "cordis.yml";

/** The empty root entry list the whole face tree patches over. */
const PROFILE_ROOT_CONFIG = `# kairos-face profile root - an empty entry list. The tree is composed as
# patches: bundles, the face's policy defaults, project market connections,
# profile/home user patches, then the face's own host rows. Edit
# cordis.patch.yml, not this file - kairos-face rewrites it on every boot.
[]
`;

/** `FiberState.ACTIVE`. The enum is a `declare const enum` with no runtime
 * object (installed `@deepseek-ai/cordis/lib/types/fiber.d.ts:67-74`): under
 * tsx a value import of it fails at link time. app-boot mirrors the value the
 * same way (NEW packages/boot/app-boot/src/index.ts:730-737). */
const FIBER_ACTIVE = 2 as FiberState.ACTIVE;
/** The remaining `FiberState` ordinals, for the row audit's diagnostic only. */
const FIBER_PENDING = 0 as FiberState.PENDING;
const FIBER_FAILED = 3 as FiberState.FAILED;
const FIBER_STATE_NAMES: Readonly<Record<number, string>> = {
  0: "pending", 1: "loading", 2: "active", 3: "failed", 4: "disposed", 5: "unloading",
};

/** The patch-list type {@link boot} accepts. Taken from the pinned signature
 * rather than by importing `@deepseek-ai/cordis-plugin-include`: the contract
 * is "whatever boot takes" (still `PatchOptions[]` at 0.2.0-rc.2). */
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
  /** The bots directory (`bots/`); tests point it at a fixture. Defaults to the repository's. */
  botsRoot?: string;
  /** Leave the gateway's readiness uncommitted: the caller commits it with
   * {@link BootedFace.commitReady} once its OWN routes are mounted. `main.ts`
   * sets it, because it registers `/`, the `/data` routes, the room engine and
   * the bot runtime AFTER `bootFace` returns, and a previously signed-in tab
   * (its cookie lives 30 days) reconnects its streams the moment the gateway
   * admits them - it must not find those routes missing (critique-boot-and-
   * composition observation 3, REMEDIATION B). Unset, `bootFace` commits as
   * its last step, which is what every smoke that boots without `main.ts`
   * needs. */
  deferReady?: boolean;
  /** An in-memory patch layer composed directly AFTER the operator's layers
   * (the profile's `cordis.patch.yml`, then the home's) and BEFORE the face's
   * own switches, persona and host rows - so it wins over every operator row
   * and loses to every face-owned one. It exists for tools that must change an
   * operator's composition without writing the operator's files:
   * `scripts/check-home.ts` disables the MCP rows of a harness-home COPY this
   * way instead of appending rows to the copy's patch file. `main.ts` never
   * sets it; unset, the stack is exactly what it was without the option. */
  extraPatches?: FacePatchList;
}

/** What {@link bootFace} hands back. */
export interface BootedFace {
  /** The settled root context. */
  ctx: Context;
  /** Idempotent: disposes the root fiber, and with it every declaration. */
  dispose(): Promise<void>;
  /** The face's bot preset declarations (src/bot-presets.ts): every
   * `bots/<id>/` but the default, declared after the tree settled.
   * `redeclare(id)` is what a bot save calls (main.ts `onBotChanged`), and
   * `errors` says why a bot is missing from the roster. */
  botPresets: BotPresets;
  /** Open the browser streams: commit the gateway's `appReady`, which admits
   * `/api/remote.mux` only once it fires (NEW packages/api/gateway/src/
   * index.ts:265-276). Idempotent. Already done by `bootFace` unless
   * {@link FaceBootOptions.deferReady} asked for it to be left to the caller.
   * @throws when the root stopped (disposed, or failed) since the boot - a
   * face that would never stream is refused, not committed. */
  commitReady(): void;
}

/** Top-level row ids of the tree these layers compose to, through the include's
 * own patch algorithm — the same single `applyEntryPatches` call boot makes, so
 * a switch that asks "is this row in the tree?" sees what will actually mount. */
function composedRowIds(layers: readonly FacePatchList[]): Set<string> {
  const ids = new Set<string>();
  for (const row of composeEntries(layers)) if (typeof row.id === "string") ids.add(row.id);
  return ids;
}

/**
 * Compose the face's full patch stack over its profile, in application order:
 * bundle layers in `dsh.profile.bundles` order, the face's policy defaults
 * (src/policy.ts), the project's AKShare connection, the profile's own user
 * layer, the machine-local home layer (`$DSH_HOME/cordis.patch.yml`, which
 * outranks the per-profile one), the caller's in-memory
 * {@link FaceBootOptions.extraPatches} (usually none), the telemetry switch,
 * the hmr switch, Kairos's persona, then the face's host rows last.
 *
 * Pure with respect to the environment — the home is threaded explicitly into
 * every dsh-app-boot call rather than materialized into `$DSH_HOME` — but NOT
 * pure with respect to the disk: it rewrites the profile root, which boot
 * requires. (It no longer writes the shared module fallback: resolution is
 * computed in memory by {@link bootFace}.)
 * @param opts - profile name, webserver port, optional harness home.
 * @returns the composed patch stack, the absolute root config path to boot,
 * and the loaded profile (the runtime resolution needs it).
 * @throws when the profile does not exist, a bundle was skipped, or a
 * patch file cannot load.
 */
export function composeFace(opts: FaceBootOptions): { patches: FacePatchList; rootConfig: string; profile: Profile } {
  const home = resolveDshHome(opts.dshHome);
  const profile = loadProfile(BIN, opts.profileName, INSTALL_ANCHOR, home, { userLayer: true });
  /* `loadProfile` never prints and no longer throws on a bundle it cannot load:
   * it lists it in `skippedBundles` and composes on without its layer (NEW
   * packages/boot/app-boot/src/profile.ts:655-689). Print them the way the
   * CLI does (NEW apps/cli/src/profile-boot.ts:170), then refuse: a face whose
   * dsh-base was skipped would compose with no approval, no tools and no
   * session store, and the first thing to notice would be a Gate-2 check
   * three screens later. */
  reportSkippedBundles(BIN, profile);
  if (profile.skippedBundles.length > 0) {
    throw new Error(
      `${BIN}: profile "${opts.profileName}" skipped bundle(s) ` +
        `${profile.skippedBundles.map((b) => `${b.packageName} (${b.reason})`).join(", ")}` +
        ` - the face needs @deepseek-ai/dsh-base`,
    );
  }
  const rootConfig = join(profile.dir, PROFILE_ROOT_FILENAME);
  /* Always rewritten, never merely created: the whole composition is patch
   * layers, and the vendored Loader's tree write-back (a plugin disposing
   * itself persists the settled tree) can bake composed rows into this file,
   * which would duplicate every bundle insert on the next boot. The file
   * exists on disk only because the Loader needs a real include root to anchor
   * `baseUrl` at the profile directory (NEW apps/cli/src/profile-boot.ts:
   * 152-173 keeps the same rule). */
  writeFileSync(rootConfig, PROFILE_ROOT_CONFIG);
  const bundlePatches = profile.layers.flatMap((layer) => layer.patches);
  /* The face's policy defaults (src/policy.ts, PLAN S4): directly above the
   * bundle layer and below everything the operator writes, so an operator row
   * with the same id wins. Guarded against the BUNDLE composition alone - the
   * rows those patches may target - and loud when a target is missing. */
  const policyPatches = facePolicyPatches(
    composedRowIds([bundlePatches]),
    (line) => { process.stderr.write(`${BIN}: warning: ${line}\n`); },
  );
  const marketPatches = aksharePatches();
  const homePatches = loadOptionalPatches(BIN, join(home, PROFILE_PATCH_FILENAME)) ?? [];
  /* Cloned: the include's patch algorithm pushes inserted rows by reference
   * and later patches assign into them, so composing the caller's own objects
   * could rewrite them under the caller. */
  const extraPatches: FacePatchList = structuredClone(opts.extraPatches ?? []);
  const patches: FacePatchList = [
    ...bundlePatches, ...policyPatches, ...marketPatches, ...profile.patches, ...homePatches, ...extraPatches,
  ];
  /* Both switches below are guarded on the row actually being in the composed
   * tree. A patch that matches nothing is inert and — measured, not assumed —
   * SILENT: the include plugin does call a warn sink for it, but nothing
   * reaches stdout or stderr in a booted face tree, so an unguarded switch
   * would look like it had taken effect while doing nothing at all. The guard
   * is what keeps "telemetry disabled" from being a lie on a profile that
   * never mounted the row. (With the policy layer disabling
   * `session-telemetry-otel` by default the env switch is redundant until an
   * operator re-enables the row - and then it still wins, composing after.) */
  const below = composeEntries([bundlePatches, policyPatches, marketPatches, profile.patches, homePatches, extraPatches]);
  const rows = new Set(below.flatMap((row) => (typeof row.id === "string" ? [row.id] : [])));
  /* app-boot exports the CLI's own resolver now (NEW packages/boot/app-boot/
   * src/profile-context.ts:52-55): ANY non-empty value disables, and a
   * composition without the row needs no patch. */
  const telemetry = resolveTelemetryPatch(process.env.DSH_TELEMETRY_DISABLED, rows.has(TELEMETRY_ROW_ID));
  if (telemetry !== undefined) patches.push(telemetry);
  if (rows.has(HMR_ROW_ID)) patches.push({ id: HMR_ROW_ID, disabled: true });
  /* Kairos's persona: the one config value dsh-base leaves empty on purpose
   * ("The deployment persona is a deployment choice", base :502-507, row
   * `config: { personaPrefix: '' }`). 0.2.0 renamed the key: `persona`
   * (section `deployment:persona`) became `personaPrefix`, rendered as section
   * `deployment:persona-prefix` at `DEPLOYMENT_PERSONA_PREFIX = 0` — the same
   * slot, the same order (NEW packages/core/system-prompt/src/index.ts:
   * 125-127, 179, 409-436; commit 40792330c0). `personaSuffix` is not set by
   * the face: it defaults to '' and 0.1.1 had no suffix.
   *
   * ONLY `personaPrefix` is the face's. A non-insert patch REPLACES the row's
   * whole config (NEW vendor/include/src/index.ts:116-123), and this one is
   * pushed AFTER the operator's profile and home layers - so writing
   * `{ personaPrefix }` alone would silently discard every other key an
   * operator set on this row: `includeRuntimeContext`, `includeHarnessIdentity`,
   * `personaSuffix`, `toolOrder` (system-prompt/src/index.ts:247-268). That was
   * the 0.1.1 behaviour too, and it bites harder now: `includeRuntimeContext:
   * false` is the operator's knob for 0.2.0's runtime-context prefix churn
   * (PLAN §7; critique-boot-and-composition W3). So the patch restates the row's
   * config exactly as the layers below the overlay left it and overrides the
   * persona alone. `!!js` values ride along unevaluated, as they would have in
   * the operator's own patch. Guarded like hmr: an unmatched patch is silent,
   * and a silently empty persona is D11 all over again. `readPersona` throws on
   * a malformed template, which refuses the boot with the file named - better
   * than a prompt that throws at every step. */
  if (rows.has(SYSTEM_PROMPT_ROW_ID)) {
    const inherited: unknown = below.find((row) => row.id === SYSTEM_PROMPT_ROW_ID)?.config;
    const persona: SystemPromptConfig = { personaPrefix: readPersona(PERSONA_PATH) };
    patches.push({
      id: SYSTEM_PROMPT_ROW_ID,
      name: "@deepseek-ai/dsh-system-prompt",
      config: {
        ...(inherited !== null && typeof inherited === "object" && !Array.isArray(inherited) ? inherited : {}),
        ...persona,
      },
    });
  }
  /* The static `preset-kairos` row IS `bots/kairos` (src/bot-presets.ts
   * `definitionFor`): its preset.yml name/description and its `[]`
   * composition - the host composition itself, no mask, no shadowed persona.
   * Static, not declared after boot like the other bots, because the default
   * must exist before the first `session/create` resolves it (NEW
   * packages/api/session-controller/src/agent.ts:380-397). `definitionFor`
   * throws with the file path when bots/kairos/agent.cordis.yml is missing or
   * not YAML, which refuses the compose as 0.1.1's roster check refused the
   * boot. `model` stays face-only - a definition carries no route (NEW
   * packages/preset/agent-preset-registry/src/definition.ts:5-11). */
  patches.push(...faceOverlay(opts.port, definitionFor(opts.botsRoot ?? BOTS_ROOT, DEFAULT_PRESET)));
  return { patches, rootConfig, profile };
}

/** The launcher-owned readiness signal the gateway waits on before it admits
 * any `/api/remote.mux` stream. A verbatim copy of the CLI-private helper (NEW
 * apps/cli/src/profile-boot.ts:44-65): it is not exported, and
 * `provideCmdline` takes any {@link AppReady}. `commit` is idempotent and runs
 * every listener registered before it; a listener added after it runs at once.
 */
function createAppReady(): { service: AppReady; commit(): void } {
  let ready = false;
  const listeners = new Set<() => void>();
  return {
    service: {
      onReady(listener) {
        if (ready) {
          listener();
          return () => {};
        }
        listeners.add(listener);
        return () => { listeners.delete(listener); };
      },
    },
    commit() {
      if (ready) return;
      ready = true;
      for (const listener of [...listeners]) listener();
      listeners.clear();
    },
  };
}

/** One Loader entry as the row audit reads it. Structural: the Loader's own
 * `Entry` type lives in `@deepseek-ai/cordis-plugin-loader`, which the face does
 * not declare (NEW vendor/loader/src/config/entry.ts:43-92). */
interface AuditEntryLike {
  options: { id: string; name: string };
  /** A getter: it walks the owning entries and evaluates `!!js` expressions, so it can THROW. */
  readonly disabled: boolean;
  fiber?: {
    state: number;
    inject: Record<string, unknown>;
    ctx: { get(name: string): unknown };
    await(): Promise<unknown>;
  };
}

/** A thrown value's message, for one-line diagnostics. */
function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Why one enabled entry is not ACTIVE, in the words app-boot's own startup
 * diagnostic uses (NEW packages/boot/app-boot/src/index.ts:824-883): a pending
 * fiber names the services it is still waiting for, and a failed fiber is
 * awaited to recover the error it failed with. */
async function whyInactive(fiber: NonNullable<AuditEntryLike["fiber"]>): Promise<string> {
  if (fiber.state === FIBER_PENDING) {
    const missing = Object.keys(fiber.inject).filter((service) => fiber.ctx.get(service) === undefined);
    return `pending (waiting for ${missing.length === 1 ? "service" : "services"}: ${missing.join(", ") || "unknown"})`;
  }
  if (fiber.state === FIBER_FAILED) {
    try {
      await fiber.await();
    } catch (err) {
      return `failed: ${messageOf(err)}`;
    }
    return "failed";
  }
  return `fiber state ${FIBER_STATE_NAMES[fiber.state] ?? String(fiber.state)}`;
}

/**
 * The strict row audit (divergence 8): every ENABLED Loader entry must be
 * ACTIVE once `boot()` resolves — the 0.1.1 contract (OLD packages/boot/
 * app-boot/src/index.ts:692-730). It walks `ctx.loader.entries()` exactly as
 * app-boot's own audit does (subtrees included): a disabled entry is skipped, a
 * throwing `disabled` expression is a failure, an entry with no fiber failed
 * to import. That covers every face overlay row, the operator's rows, and the
 * dsh-base rows Gate 2 and the room stand on (`approval`, `user-questions`,
 * `permission`, `tools`, `agent`, `session`, `typert-gateway`) — plus the
 * `api-remotes` answerer and the preset registry rows. Preset CHILD rows live
 * in the registry's private trees, not here (NEW packages/preset/
 * agent-preset-registry/src/mount.ts:9-24); a broken preset is the roster
 * check's to catch.
 *
 * `boot()` has already printed its own warning block for these same entries
 * (with stacks); this refusal lists them once more, one line each.
 * @param ctx - the settled root context.
 * @throws listing `id (package): state` for every enabled entry that is not ACTIVE.
 */
async function assertEntriesActive(ctx: Context): Promise<void> {
  /* `boot()` returns early — with the Loader gone — when a surface disposed the
   * tree while startup was in flight (NEW packages/boot/app-boot/src/
   * index.ts:1003-1011). The face has no one-shot runner that may do that, so
   * a vanished Loader is a failed startup, not an exit to honour. */
  const loader = ctx.get("loader") as { entries(): Iterable<AuditEntryLike> } | undefined;
  if (loader === undefined) {
    throw new Error(`${BIN}: the plugin tree disposed itself during startup - refusing to report a face that cannot serve`);
  }
  const problems: string[] = [];
  for (const entry of loader.entries()) {
    const label = `${entry.options.id} (${entry.options.name})`;
    try {
      if (entry.disabled) continue;
    } catch (err) {
      problems.push(`${label}: disabled expression threw: ${messageOf(err)}`);
      continue;
    }
    const fiber = entry.fiber;
    if (fiber === undefined) {
      problems.push(`${label}: failed to import`);
      continue;
    }
    if (fiber.state === FIBER_ACTIVE) continue;
    problems.push(`${label}: ${await whyInactive(fiber)}`);
  }
  if (problems.length > 0) {
    throw new Error(
      `${BIN}: ${problems.length} enabled ${problems.length === 1 ? "entry" : "entries"} did not activate - ` +
        `the face refuses a partial tree (dsh 0.2 boot fails only on its required ids and warns on the rest):\n  ` +
        problems.join("\n  "),
    );
  }
}

/** Services the face's gates and rooms route through, each with what its
 * absence would silently cost. The strict row audit already refuses an
 * enabled row that did not activate; these catch the case it cannot see — a
 * row an operator patch DISABLED, or a future bundle swap that stopped
 * providing the service under this key — where the tree would come up healthy
 * and the consequence would surface later with nothing on screen saying why.
 * - `approval`, `userQuestions`: Gate 2 (spec section 3.2); keys unchanged at
 *   0.2.0 (NEW packages/interaction/user-approval/src/index.ts:156,
 *   user-questions/src/index.ts:84).
 * - `typertGateway` (NEW packages/api/gateway/src/index.ts:228): the answerer.
 *   `api-remotes` registers the approval/question forwarder INTO it; without
 *   a gateway no card can reach a browser, and dsh-tools turns every ask into
 *   "no approval channel is available" (NEW packages/core/tools/src/
 *   index.ts:1762-1765).
 * - `permissionPresets` (NEW packages/interaction/permission-presets/src/
 *   index.ts:208): the room pins every member session `read-only` through it. */
const REQUIRED_SERVICES: ReadonlyArray<readonly [service: string, consequence: string]> = [
  ["approval", "every order card would fail closed invisibly"],
  ["userQuestions", "Kairos could not ask the operator anything"],
  ["typertGateway", "no approval answerer - every order would be denied 'no approval channel is available'"],
  ["permissionPresets", "room members could not be pinned read-only"],
];

/** The model-facing tool `@deepseek-ai/dsh-tool-ask-user` registers, checked by
 * name because its absence is the quietest failure this face has had. */
const ASK_USER_TOOL = "ask_user_question";

/** The package that answers Gate 2: api-remotes registers the gateway's only
 * `$events` source and forwards the `approval/request` and
 * `user-questions/request` waterfalls into it (NEW packages/api/remotes/src/
 * index.ts:37-75). */
const ANSWERER_PACKAGE = "@deepseek-ai/dsh-api-remotes";

/** Is some enabled Loader entry for `pkg` ACTIVE? The strict row audit proves
 * every ENABLED entry active; this proves one EXISTS - a row that was never
 * composed (or was disabled) passes that audit with nothing to audit. */
function hasActiveEntry(ctx: Context, pkg: string): boolean {
  const loader = ctx.get("loader") as { entries(): Iterable<AuditEntryLike> } | undefined;
  for (const entry of loader?.entries() ?? []) {
    if (entry.options.name !== pkg) continue;
    try {
      if (entry.disabled) continue;
    } catch {
      continue;
    }
    if (entry.fiber?.state === FIBER_ACTIVE) return true;
  }
  return false;
}

/** One Gate-2 fiber as {@link assertOrderGateArmed} reads it — the same four
 * members the row audit's {@link whyInactive} reads off a Loader entry's fiber.
 * Structural: what `ctx.inject` returns is a cordis `Fiber` and more. */
type GateFiberLike = NonNullable<AuditEntryLike["fiber"]>;

/** The two fibers that carry Gate 2, as {@link armOrderGate} returns them. */
export interface OrderGateFibers {
  /** Holds the `tools/pre-execute` ask listener; ACTIVE only while `approval` is. */
  listener: GateFiberLike;
  /** Holds the monotonic `tools.guard`; ACTIVE only while `tools` is. */
  guard: GateFiberLike;
}

/** The approval service as the ask listener reads it: the two public halves of
 * its private `effectivePolicy` (orders.ts {@link effectiveApprovalPolicy}). */
interface GateApprovalLike {
  overrideOf(session: unknown): ApprovalPolicyLike | undefined;
  config?: { policy?: ApprovalPolicyLike };
}

/** The tool registry as the guard reads it: the guard seam itself
 * (`ToolGuard`, NEW packages/core/tools/src/index.ts:731, 1136-1142) and the
 * live lookup of a call's description. */
interface GateToolsLike {
  get(name: string, scope?: unknown): { description?: string } | undefined;
  guard(check: (exec: { name: string; callId?: unknown; agent?: { session: unknown } }) => string | undefined): () => void;
}

/** `ctx.on`, narrowed to the one event the ask listener handles, in the face's
 * own structural terms. dsh-tools' declarations do augment cordis's event map
 * with this event, but they reach this compilation only transitively - the
 * face does not depend on `@deepseek-ai/dsh-tools` - so the listener states the
 * slice of `ToolExecution` it reads, as orders.ts states `PreToolDecision`. */
interface GateEventsLike {
  on(
    name: "tools/pre-execute",
    listener: (
      exec: { name: string; arguments?: unknown; agent?: { session: unknown } },
      next: () => Promise<PreToolDecision>,
    ) => Promise<PreToolDecision>,
    options?: { prepend?: boolean },
  ): () => boolean;
}

/**
 * Arm GATE 2 FOR ORDERS on the host context, from inside `prepare`
 * (divergence 10). Two registrations, because neither alone is enough: only a
 * `tools/pre-execute` listener can return `ask` (a guard is deny-only:
 * `ToolGuard = (exec) => string | undefined`, NEW packages/core/tools/src/
 * index.ts:731), and only a guard is monotonic - it is evaluated on EVERY
 * allow (`tools/src/index.ts:1519`), including the allow that `allowed-once`
 * becomes.
 *
 * WHEN. Each half is a `hostCtx.inject` fiber (NEW vendor/cordis/src/
 * registry.ts:300-302): it runs once the service it reads is ACTIVE, and
 * everything it registers is an effect of THAT fiber - `ctx.on` through the
 * events service (vendor/cordis/src/events.ts:254-260, 292-301), `tools.guard`
 * through the calling context, which owns the effect (tools/src/index.ts:
 * 1136-1142; packages/core/scope/src/store.ts:226-264). So a registration can
 * never outlive or double its service: when `approval` or `tools` is replaced,
 * cordis unloads the fiber - disposing the old registration - before it runs
 * the callback again for the new service (vendor/cordis/src/fiber.ts:625-696),
 * and disposing the host disposes both. Each half waits for exactly what it
 * reads, so neither is held back by the other: the guard arms with `tools`
 * alone, and while `approval` is absent an order is DENIED by the guard (no
 * logged grant can exist) rather than dispatched. And the guard arms before
 * any row can reach the new registry: `reflect.notify` wakes fibers in
 * registry order (vendor/cordis/src/reflect.ts:314-330) and these two were
 * registered before any config-tree row existed, so each one's single
 * microtask of `_reload` (fiber.ts:646-650) runs ahead of every row woken by
 * the same service.
 *
 * ORDER. `prepend` puts the listener in front of everything registered before
 * it - which, from `prepare`, is nothing. cordis runs a waterfall
 * outermost-first and `prepend` unshifts (NEW vendor/cordis/src/events.ts:
 * 226-243, 253-257), and each listener is free to ignore what `next()`
 * returned, so a row that registers with `prepend` LATER sits outside ours and
 * could take our `ask` and hand back `allow`. At 0.2.0-rc.2 the only one in
 * the composed tree is dsh-tool-jobs's, which records an output limit and
 * always returns `next()` (NEW packages/jobs/tool-jobs/src/index.ts:220-224).
 * Armed after `boot()` the listener was outermost over the boot-time rows too;
 * from `prepare` it is not, and that is exactly the case the guard exists for.
 * It asks the SESSION LOG rather than remembering what the listener saw:
 * `hasApprovalGrant` cannot be satisfied by any listener decision - only by a
 * logged `allowed-once` for this exact callId and tool - so an outer listener
 * that swallows our `ask` can at worst turn an order into a denial, never into
 * an unapproved dispatch. (A re-armed listener prepends again, so it returns
 * to the front.)
 * @param hostCtx - the root context `boot()` hands `prepare`.
 * @returns the two fibers, for {@link assertOrderGateArmed} once `boot()` settles.
 */
export function armOrderGate(hostCtx: Context): OrderGateFibers {
  const listener = hostCtx.inject(["approval"], function orderGateAskListener(gateCtx) {
    const approval = gateCtx.get("approval") as GateApprovalLike | undefined;
    /* The inject guarantees it (a fiber runs only for the epoch its services
     * were ACTIVE in, vendor/cordis/src/fiber.ts:648-656); a throw here would
     * FAIL this fiber, which assertOrderGateArmed refuses with the reason. */
    if (approval === undefined) throw new Error(`${BIN}: order gate: the approval service vanished before the listener armed`);
    (gateCtx as unknown as GateEventsLike).on("tools/pre-execute", async (exec, next) => {
      if (!isOrderTool(exec.name)) return next();
      /* Without a session there is nobody to ask, and `serviceAsk` would deny
       * anyway (NEW packages/core/tools/src/index.ts:1738-1743) - deny in our
       * own words rather than letting it report a refusal nobody made. */
      const session = exec.agent?.session;
      if (session === undefined) {
        return {
          kind: "deny",
          reason: `${exec.name} needs a per-order approval card and this call has no session to ask in`,
        };
      }
      const decision = orderApprovalDecision(
        exec.name,
        effectiveApprovalPolicy(approval, session),
        exec.arguments,
      );
      return decision ?? next();
    }, { prepend: true });
  });
  const guard = hostCtx.inject(["tools"], function orderGateGuard(gateCtx) {
    const tools = gateCtx.get("tools") as GateToolsLike | undefined;
    if (tools === undefined) throw new Error(`${BIN}: order gate: the tools service vanished before the guard armed`);
    /* The backstop, evaluated per call on every allow. It reads the LIVE
     * description rather than a boot snapshot because the registry fills in
     * asynchronously: `dsh-mcp-client` defaults `failOnStartupError` to false
     * (NEW packages/mcp/mcp-client/src/index.ts:128, 138), so a server whose
     * first connection failed still activates and can register its tools after
     * the boot audit has already run.
     *
     * It is handed the SESSION, not its events. 0.2.0 removed the
     * `Session.events` getter this guard used to read (commit 5660f44d29), and
     * the read went `undefined` without a word: every APPROVED order was then
     * denied as "without a logged allowed-once approval" (MAP gate2 §0.1).
     * `orderGuardReasonForSession` (orders.ts) reads `snapshotEvents()` (NEW
     * packages/core/session/src/index.ts:649-661) - and only for a gated tool,
     * since a full snapshot copies the log once per append and this runs on
     * every allow of every tool - and gives an UNREADABLE log its own denial,
     * distinct from a missing grant. */
    tools.guard((exec) =>
      orderGuardReasonForSession(
        exec.name,
        tools.get(exec.name, exec.agent)?.description,
        exec.agent?.session,
        exec.callId,
      )
    );
  });
  return { listener, guard };
}

/**
 * Refuse a boot on which Gate 2 did not arm. {@link armOrderGate}'s fibers
 * are not Loader entries, so the strict row audit cannot see them, and cordis
 * CONTAINS a throw from an inject callback (it logs it and marks the fiber
 * FAILED, NEW vendor/cordis/src/fiber.ts:659-664) - a half that failed to arm
 * would otherwise leave the face looking healthy with the gate quietly half
 * there. 0.1.1 registered both halves in `bootFace`'s own body, where any
 * failure refused the boot; this keeps that.
 * @param gate - the fibers {@link armOrderGate} returned inside `prepare`, or
 * `undefined` if `prepare` never reached it.
 * @throws naming each half that is not ACTIVE, with why (pending on which
 * service, or the error it failed with).
 */
async function assertOrderGateArmed(gate: OrderGateFibers | undefined): Promise<void> {
  if (gate === undefined) {
    throw new Error(`${BIN}: Gate 2 was never armed - prepare did not reach armOrderGate`);
  }
  const halves: ReadonlyArray<readonly [label: string, fiber: GateFiberLike]> = [
    ["ask listener (waits for approval)", gate.listener],
    ["guard (waits for tools)", gate.guard],
  ];
  const problems: string[] = [];
  for (const [label, fiber] of halves) {
    /* Let an in-flight (re)load settle first, so a transition is not
     * mistaken for a failure; a startup error is recovered by whyInactive. */
    try {
      await fiber.await();
    } catch {
      // reported below
    }
    if (fiber.state !== FIBER_ACTIVE) problems.push(`${label}: ${await whyInactive(fiber)}`);
  }
  if (problems.length > 0) {
    throw new Error(
      `${BIN}: Gate 2 did not arm - ${problems.join("; ")} - the face refuses to serve orders through a half-armed gate`,
    );
  }
}

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
 * @param opts - profile name, webserver port, optional harness home, bots
 * root, and whether the caller commits the gateway's readiness itself.
 * @returns the settled root context, an idempotent disposer, the bot preset
 * declarations, and the readiness commit (already done unless deferred).
 * @throws after disposing the tree when any enabled row did not activate, a
 * required service is missing, the `ask_user_question` tool did not register,
 * either half of Gate 2 did not arm, an operator-gated tool escapes the order
 * gate, the preset roster cannot supply its own default, or a declared bot is
 * not listed; `StartupError`
 * (from `boot`) when a required dsh entry is inactive; and whatever `boot`
 * throws when the plugin tree fails to load.
 */
export async function bootFace(opts: FaceBootOptions): Promise<BootedFace> {
  if (opts.dshHome !== undefined) process.env.DSH_HOME = resolveDshHome(opts.dshHome);
  const home = resolveDshHome();
  const environment = loadLayeredEnv(BIN);
  const { patches, rootConfig, profile } = composeFace(opts);
  /* The package table every bare row name resolves from, computed BEFORE any
   * plugin imports (NEW apps/cli/src/profile-boot.ts:205-206; usage model NEW
   * apps/cli/tests/web-agent-presets.e2e.ts:165-173). Pure: it writes nothing.
   * `home` is passed explicitly for the same reason composeFace threads it. */
  const resolution = await createRuntimeResolution({ installAnchor: INSTALL_ANCHOR, profile, home });
  const appReady = createAppReady();
  /* The CLI's own holder pattern: `prepare` runs before boot resolves, so a row
   * that requests exit while the tree is still mounting must still reach a real
   * context to dispose. */
  const app: { current?: Context } = {};
  /* Single-shot like the CLI's (NEW apps/cli/src/profile-boot.ts:254-263): a
   * second call awaits the first teardown instead of racing it. */
  let disposal: Promise<void> | undefined;
  const dispose = (): Promise<void> => disposal ??= (async () => {
    await app.current?.fiber.dispose();
  })();
  /* Gate 2's two fibers, set inside `prepare` and audited once boot() settles. */
  let gate: OrderGateFibers | undefined;
  try {
    const ctx = await boot(BIN, rootConfig, structuredClone(patches), async (hostCtx) => {
      app.current = hostCtx;
      /* Order mirrors NEW apps/cli/src/profile-boot.ts:296-312, minus
       * `profileContext` (divergence 2): every launch fact is provided before
       * the first config-tree entry mounts. */
      hostCtx.provide(DSH_LAUNCH_ENVIRONMENT_KEY, environment);
      /* Installs the runtime resolution into Node's ESM and CJS resolvers for
       * importers under `$DSH_HOME/profiles/**` (and Workers), disposed with the
       * fiber (NEW packages/boot/app-boot/src/profile-resolution/
       * service.ts:60-75, resolver.ts:185-209). MUST precede every row import.
       * Needs the native `node-addon-require-builtin`; if that cannot load,
       * this throws and boot reports "host preparation failed" (PLAN B4). */
      await hostCtx.plugin(PluginPackages, { resolution });
      /* No command line: the face is not a launcher, so the tree sees an empty
       * argument list, and `ctx.appExit` is a bare process exit. The CLI's
       * bounded, escalating shutdown controller is a scope cut (divergence 4) -
       * awaiting an unbounded dispose inside an exit request would trade a hard
       * exit for a hang, which is the worse failure for a request to stop.
       * `ready` is the gateway's WebSocket admission gate (divergence 5). */
      provideCmdline(hostCtx, { args: [], exit: (code) => process.exit(code), ready: appReady.service });
      /* Gate 2 arms HERE (divergence 10): still before the first config-tree
       * row mounts, because boot() mounts the root include only once `prepare`
       * resolves (NEW packages/boot/app-boot/src/index.ts:1001-1004). Neither
       * half can arm yet - no row has provided `tools` or `approval` - but
       * each will the moment its service does, instead of once boot() has
       * settled, by which time a slow row may have let unary `/api` drive a
       * turn into a live order tool with nothing listening. */
      gate = armOrderGate(hostCtx);
    });
    app.current = ctx;
    await assertEntriesActive(ctx);
    const missing = REQUIRED_SERVICES.filter(([name]) => ctx.get(name) === undefined);
    if (missing.length > 0) {
      throw new Error(
        `${BIN}: ${missing.map(([name, consequence]) => `${name} missing (${consequence})`).join("; ")}` +
          ` - profile ${JSON.stringify(opts.profileName)} must bundle @deepseek-ai/dsh-base with these rows enabled`,
      );
    }
    /* The answerer itself (PLAN S7 item 3). A gateway with no `$events` source
     * boots clean and passes every check above: measured by removing the
     * overlay's `api-remotes` row - the tree came up, and only the smoke's
     * `$events` open failed (`gateway/service-unavailable`). Every order would
     * then be denied the moment it asked, with no card anywhere: `decide()`
     * falls through to 'unavailable' (NEW packages/interaction/user-approval/
     * src/index.ts:280-284). */
    if (!hasActiveEntry(ctx, ANSWERER_PACKAGE)) {
      throw new Error(
        `${BIN}: no approval answerer - ${ANSWERER_PACKAGE} is not mounted, so every order would be denied` +
          ` 'no approval channel is available' and every question would reject NO_PROVIDER` +
          ` (the overlay's \`api-remotes\` row mounts it)`,
      );
    }
    /* The OTHER half of the question seam, and unlike the services above this
     * one has really shipped broken: `userQuestions` is the service,
     * `ask_user_question` is the only thing that can reach it from a model, and
     * they fail INDEPENDENTLY. dsh-base mounts the service and no tool row for
     * it, so from 2026-08-31 to 2026-09-02 the face came up healthy, passed the
     * check above, offered the model 35 tools, and could not ask the operator
     * anything - no error, no card, no pending question, just an agent that
     * guesses. Asserted against the live REGISTRY rather than the composed row
     * list because the two disagree exactly where it matters: a row can be
     * ACTIVE and still register nothing a model can call. */
    const tools = ctx.get("tools") as { schemas(): ToolSchemaLike[] } | undefined;
    if (tools?.schemas().some((schema) => schema.name === ASK_USER_TOOL) !== true) {
      throw new Error(
        `${BIN}: ${ASK_USER_TOOL} is not registered - Kairos would have no way to ask the operator` +
          ` anything, silently (the \`tool-ask-user\` overlay row mounts it)`,
      );
    }
    /* GATE 2 FOR ORDERS armed inside `prepare` (divergence 10, armOrderGate);
     * what remains here is proving it did, then cross-checking the live
     * registry against it. */
    await assertOrderGateArmed(gate);
    const audit = auditOrderTools(tools.schemas());
    if (audit.ungated.length > 0) {
      throw new Error(
        `${BIN}: ${audit.ungated.join(", ")} ${audit.ungated.length === 1 ? "is" : "are"} marked` +
          ` operator-gated but would not stop at the order gate - Gate 2 would cover nothing while` +
          ` looking healthy (a renamed tool or MCP server; see face/src/orders.ts)`,
      );
    }
    if (audit.gated.length > 0) {
      console.log(`${BIN}: order gate armed for ${audit.gated.join(", ")}`);
    }
    /* The preset roster: every `session/create` the controller serves resolves a
     * preset - the named one or `defaultId` - and fails at resolution if the
     * roster cannot supply it (NEW packages/api/session-controller/src/
     * agent.ts:380-397). Assert it here, against the LIVE service, so a broken
     * default refuses the boot instead of failing every session. */
    const presets = ctx.get("agentPresets") as
      | { defaultId: string; list(): Promise<{ id: string; broken?: string }[]> }
      | undefined;
    if (presets === undefined) {
      throw new Error(`${BIN}: agentPresets missing - the agent-preset-registry overlay row did not mount`);
    }
    /* `defaultId = selectedDefault ?? default` (NEW packages/preset/
     * agent-preset-registry/src/index.ts:74): a Settings-supplied default
     * could otherwise move every preset-less session off Kairos. Without
     * `profileContext` no settings service exists, so this holds today; the
     * check keeps it from drifting silently. */
    if (presets.defaultId !== DEFAULT_PRESET) {
      throw new Error(
        `${BIN}: the preset registry's default is "${presets.defaultId}", not "${DEFAULT_PRESET}" -` +
          ` every session that names no preset would leave the Kairos composition`,
      );
    }
    /* S6: every non-default bot, declared NOW - after Gate 2 is armed, before
     * the roster check below and before `appReady` commits - because the tree
     * has settled: the MCP rows awaited their initial discovery (NEW
     * packages/mcp/mcp-client/src/index.ts:194-199) and the strict audit proved
     * every host tool row ACTIVE. Activation is EAGER (NEW packages/preset/
     * agent-preset-registry/src/index.ts:80-118), so a declaration from an
     * overlay row would mount plugins/bot.js before the host's late tools
     * existed, and "a mount failure is final" (:120-131). A bot that cannot be
     * declared does not fail the boot - 0.1.1 listed a broken bot and started:
     * `declareBots` logs it and keeps the reason in `botPresets.errors`, which
     * /data/bots.json shows as broken. It throws only when the registry
     * service is absent (ruled out just above) or the bots root is unreadable;
     * either lands in this try's catch, which disposes and never commits. The
     * declarations are child fibers of the root, so `dispose` needs no extra
     * step to unwind them (tests/bot-presets.test.ts). */
    const botPresets = await declareBots(ctx, opts.botsRoot ?? BOTS_ROOT);
    let roster: { id: string; broken?: string }[];
    try {
      roster = await presets.list();
    } catch (err) {
      throw new Error(
        `${BIN}: agent presets: the roster could not be read - ${messageOf(err)}`,
        { cause: err },
      );
    }
    const fallback = roster.find((preset) => preset.id === presets.defaultId);
    if (fallback === undefined || fallback.broken !== undefined) {
      throw new Error(
        `${BIN}: default agent preset "${presets.defaultId}" is ` +
          (fallback === undefined
            ? `not in the roster (${roster.map((p) => p.id).join(", ") || "empty"})`
            : `broken: ${fallback.broken}`) +
          ` - every session/create would fail at resolution`,
      );
    }
    /* Every bot this boot declared must be LISTED - the registry is what
     * `session/create`, the rooms and the sidebar read, so a declaration it
     * does not list is a bot that silently vanished. Listed-but-`broken` is
     * fine: the roster shows it with its reason, as 0.1.1 did. */
    const listedIds = new Set(roster.map((preset) => preset.id));
    const unlisted = botPresets.ids().filter((id) => !listedIds.has(id));
    if (unlisted.length > 0) {
      throw new Error(
        `${BIN}: bot preset(s) ${unlisted.join(", ")} declared but not listed by the registry -` +
          ` the roster would hide them (src/bot-presets.ts)`,
      );
    }
    console.log(
      `${BIN}: agent presets: ${roster.map((p) => p.id + (p.broken === undefined ? "" : " (broken)")).join(", ")}` +
        ` (default ${presets.defaultId}; bots under ${opts.botsRoot ?? BOTS_ROOT})` +
        (botPresets.errors.size === 0 ? "" : `; ${botPresets.errors.size} bot(s) not declared, see above`),
    );
    /* LAST (divergence 5): only now may the gateway admit a browser stream.
     * The CLI's own condition (NEW apps/cli/src/profile-boot.ts:314-318), made
     * a refusal: a root that stopped would otherwise be committed anyway - a
     * face that boots "fine" and never streams. With `deferReady` the same
     * check runs when the caller commits, after its own routes. */
    const commitReady = (): void => {
      if (ctx.fiber.state !== FIBER_ACTIVE || ctx.get("loader") === undefined) {
        throw new Error(`${BIN}: the plugin tree stopped during startup - refusing to open the browser streams on it`);
      }
      appReady.commit();
    };
    if (opts.deferReady !== true) commitReady();
    return { ctx, dispose, botPresets, commitReady };
  } catch (error) {
    /* Every failure path lands here: the tree is disposed and appReady is never
     * committed. `boot()` disposes its own context before it throws; a repeat
     * dispose returns the settled single-shot result. A cleanup failure keeps
     * the original error (NEW apps/cli/src/profile-boot.ts:320-325). */
    try {
      await dispose();
    } catch (cleanup) {
      throw new AggregateError([error, cleanup], `${BIN}: startup and cleanup failed`);
    }
    throw error;
  }
}
