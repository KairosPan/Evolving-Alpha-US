/** The face's host rows, applied as the last patch layer over the `face`
 * profile (bundles: dsh-base only). Mirrors the HOST rows dsh-web-app's bundle
 * patch mounts at 0.2.0-rc.2 (NEW packages/bundle/web-app/cordis.patch.yml:
 * 91-148 workspace + controllers, 169-231 transport, 559-565 the preset
 * registry), minus every frontend/client-ui row — the face serves its own UI
 * (spec section 3.2) — and MINUS web-app's agent-plane disable set (:447-556).
 * That set exists because every web-app session mounts a full preset that
 * re-declares the tools; Kairos's `kairos` preset is empty, so the face keeps
 * dsh-base's flat host roster and Kairos keeps its tools (MAP overlay-rows §5).
 * Static config replaces the webStartup/webRuntime `!!js` expressions: no
 * dsh-web-app row is mounted, so neither service exists here.
 *
 * What this layer no longer carries, and why (each was a 0.1.1-rc.2 row):
 * - `storage`, `storage-json`, `storage-domain`, `session-projection-cache`:
 *   dsh-base mounts all four itself now (NEW packages/bundle/base/
 *   cordis.patch.yml:165-186; commit 3a4232a8fa). A same-id insert is not an
 *   error — it silently REPLACES base's row (the Loader keys rows by id, last
 *   wins: NEW vendor/loader/src/config/group.ts:48-65) and swallows every
 *   operator patch aimed at it (NEW vendor/include/src/index.ts:93-100), so
 *   they are gone rather than restated. boot.test.ts proves each composes
 *   exactly once, from dsh-base.
 * - `api-gateway` (dsh-host-apiproxy): the package was deleted upstream
 *   (commit 4f00a8b82a). dsh-base's `typert-gateway` row serves `/api` now
 *   (base :52-53), and a second gateway would throw on the second `/api`
 *   interceptor (NEW packages/client/connection/src/rpc-host.ts:210-212). Its
 *   business methods moved to the controller rows below.
 * - `cordis-host-runner`: its only consumers are `tool-cordis` and the
 *   Creator UI, neither of which the face mounts (MAP overlay-rows §2); kept,
 *   it would publish Remote methods on `/api` for nobody.
 * - `agent-presets` (dsh-agent-presets): deleted upstream (commit
 *   d1e22a7e24). Presets are declarations now — one registry row plus one
 *   `@deepseek-ai/dsh-agent-preset` row per preset; see the last two rows.
 * @module
 */

/* The configured rows are `satisfies`-checked against the plugins' OWN
 * exported config types, not against FaceRowEntry.config — the loader types
 * every row's config as `any`, so without this an rc that renames a key or
 * narrows a value would load a silently dead config instead of failing tsc. */
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { Config as WebServerConfig } from "@deepseek-ai/dsh-host-webserver";
import type { ConnectionConfig } from "@deepseek-ai/dsh-client-connection";
import type { Config as AgentPresetRegistryConfig } from "@deepseek-ai/dsh-agent-preset-registry";
import type { Config as AgentPresetConfig } from "@deepseek-ai/dsh-agent-preset";

export interface FaceRowEntry {
  id: string;
  name: string;
  config?: Record<string, unknown>;
}
export interface FacePatchEntry {
  insert?: FaceRowEntry[];
}

/** The repository's bot directory — where the face reads its preset
 * declarations from (the registry itself scans nothing any more: NEW
 * packages/preset/agent-preset-registry/README.md "Minimal configuration").
 * Module-relative. */
export const BOTS_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "bots");
/** The inert preset every session that names none joins (spec S3). */
export const DEFAULT_PRESET = "kairos";
/** The preset registry's row id. Load-bearing beyond addressing: the row id is
 * also the registry's settings namespace (NEW apps/cli/tests/
 * web-agent-presets.e2e.ts:25-26), so it must match web-app's own row
 * (NEW packages/bundle/web-app/cordis.patch.yml:562). */
export const AGENT_PRESET_REGISTRY_ROW_ID = "agent-preset-registry";
/** The Loader row id of one preset declaration. The row id addresses Loader
 * edits; the definition's own `config.id` is the identity sessions persist
 * (NEW packages/preset/agent-preset/README.md:48). The `preset-` prefix is
 * web-app's own convention (presets/*.patch.yml) and collides with no
 * dsh-base row id. */
export const presetRowId = (id: string): string => `preset-${id}`;
/** dsh-base's system-prompt row, whose `personaPrefix` composeFace sets (boot.ts). */
export const SYSTEM_PROMPT_ROW_ID = "system-prompt";

/**
 * The face's patch layer: the host rows dsh-base does not mount.
 * @param port - the webserver's TCP port; `0` asks the OS for a free one.
 * @param defaultPreset - the `kairos` preset definition, declared statically
 * so the default exists AT BOOT: `session/create` without a preset resolves
 * `defaultId` and fails `agent-preset/not-found` when it is absent (NEW
 * packages/api/session-controller/src/agent.ts:380-397). Passed in rather
 * than read here so the composition stays pure and a test can hand it a
 * fixture. Every OTHER bot is declared programmatically after boot (PLAN S6):
 * declaration activates eagerly (NEW packages/preset/agent-preset-registry/
 * src/index.ts:80-118) and a static bot row could snapshot `tools.schemas()`
 * before the MCP tools exist.
 * @returns one insert patch, in the order the rows are listed below.
 */
export function faceOverlay(port: number, defaultPreset: AgentPresetConfig): FacePatchEntry[] {
  return [{
    insert: [
      /* --- host transport. Static: no inject, no webStartup/webRuntime
       * expressions (those services are provided only by dsh-web-app rows the
       * face does not mount, NEW web-app cordis.patch.yml:161-196). */

      /* `compression` is optional and defaults to 'none' (NEW
       * packages/host/webserver/src/index.ts:59-70, 126-132). Written anyway so
       * the choice is visible and type-checked: web-app runs gzip (web-app
       * :169-177), and gzip here would also wrap the face's own `/data` JSON
       * routes. */
      { id: "webserver", name: "@deepseek-ai/dsh-host-webserver",
        config: { host: "127.0.0.1", port, compression: "none" } satisfies WebServerConfig },
      /* No new required key at 0.2.0. The row's inject changed from
       * `webServer` to `credentials` (NEW packages/client/connection/src/
       * index.ts:89, 92-115), which dsh-base's `credentials` row provides
       * (base :117-118). Activation now creates or loads the browser-session
       * signing secret in the credentials store (NEW
       * packages/client/connection/src/browser-auth.ts:161-178): the first boot
       * on a home writes a `client-connection/browser-session` grant into
       * `$DSH_HOME/.credentials.yaml`. `/api` and the mux now need the cookie
       * that secret signs — see static.ts. */
      { id: "connection", name: "@deepseek-ai/dsh-client-connection",
        config: { trustedHosts: [] } satisfies ConnectionConfig },
      /* The gateway's SOLE `$events` source. It forwards the `approval/request`
       * and `user-questions/request` waterfalls to connected browsers (NEW
       * packages/api/remotes/src/index.ts:37-45, remote-events.ts:20-48). Not
       * in dsh-base. Without it every approval resolves 'unavailable' (NEW
       * packages/interaction/user-approval/src/index.ts:280-284) — every
       * paper order and sandbox escalation denied at once, with no card — and
       * every agent question rejects NO_PROVIDER. Configless. */
      { id: "api-remotes", name: "@deepseek-ai/dsh-api-remotes" },
      /* Provides `fileUploads`, which session-controller hard-injects (NEW
       * packages/client/file-upload/src/index.ts:58-65; session-controller
       * src/index.ts:100-112). Configless. */
      { id: "file-upload", name: "@deepseek-ai/dsh-client-file-upload" },

      /* --- workspace + the Remote controllers that replaced dsh-host-apiproxy. */

      /* Still a web-app-only row (web-app :91-92; dsh-base mounts the storage
       * stack it needs, but not this). Hard-injected by both controllers below
       * and read in-process by the face's own route modules. */
      { id: "workspace", name: "@deepseek-ai/dsh-workspace" },
      /* The `session`, `skills` and `fileReferences` Remote namespaces plus the
       * in-process `sessionController` service the room engine resumes cold
       * sessions through (NEW packages/api/session-controller/src/index.ts:136,
       * 219-243). Configless: `nativeOpen` keeps its platform detection. */
      { id: "session-controller", name: "@deepseek-ai/dsh-api-session-controller" },
      /* The `workspace` and `directoryPicker` namespaces (NEW
       * packages/api/workspace-controller/src/index.ts:52, 77;
       * directory-picker.ts:42-65). Configless: its two keys only feed
       * `initializeDefault`. */
      { id: "workspace-controller", name: "@deepseek-ai/dsh-api-workspace-controller" },
      /* `credentials/describe` lives here (NEW packages/api/settings-controller/
       * src/credentials.ts:45-51, 82-97). `settings/describe` on the same row
       * throws "settings service is absent" (index.ts:216-222) because the
       * face provides no `profileContext` (boot.ts, divergence D1) and so
       * dsh-base's `settings` row stays disabled; the client does not call it. */
      { id: "settings-controller", name: "@deepseek-ai/dsh-api-settings-controller" },
      /* Unchanged id and package, CHANGED failure mode: it now awaits both
       * Loader entries it mounts (the backend and its client surface) and
       * fails the row when either cannot load (NEW packages/host/
       * directory-picker-auto/src/index.ts:87-99). At 0.1.1 a missing one was
       * ignored. Hence the four picker packages in package.json. */
      { id: "directory-picker", name: "@deepseek-ai/dsh-host-directory-picker-auto" },

      /* --- the agent-plane seam the face owns. */

      /* The model-facing half of the question seam, and the one row here that
       * the "mirror dsh-web-app's host rows" rule does not reach: upstream puts
       * `ask_user_question` in no bundle at all — web-app carries it inside
       * each shipped preset's composition (NEW packages/bundle/web-app/
       * presets/standard.patch.yml:131-132) and dsh-base mounts only the
       * `user-questions` SERVICE. The face keeps dsh-base's flat tool roster
       * and so inherits that one hole. The two halves fail INDEPENDENTLY, and
       * that is what made the hole invisible at 0.1.1: the tree came up
       * healthy, `bootFace`'s Gate-2 service check passed, the model was
       * offered its full toolset, and Kairos simply never asked anything.
       * Measured 2026-09-02 on a real session: 35 tools offered, none of them
       * this one. Face-owned rather than left to the operator's patch layer for
       * the same reason `webserver` is: this overlay composes LAST, so a patch
       * aimed at a row it owns is silently overridden - and losing the agent's
       * voice to a silent override is the exact failure the row exists to
       * prevent. The package DOES export a Config at 0.2.0 (`mode:
       * 'legacy'|'timed'`, `timeout`; NEW packages/interaction/tool-ask-user/
       * src/index.ts:15-26). Left configless on purpose: the schema default is
       * `legacy`, the blocking `ask_user_question` 0.1.1 shipped and bootFace
       * asserts by name. */
      { id: "tool-ask-user", name: "@deepseek-ai/dsh-tool-ask-user" },

      /* --- presets (replace dsh-agent-presets). */

      /* The registry. dsh-base does not mount it (only web-app does, :559-565).
       * `default` is the only required key; `selectedDefault` is a Volatile the
       * Settings page would feed, typed as a REQUIRED property of `Config`
       * (NEW packages/preset/agent-preset-registry/src/preset.ts:13-18), so a
       * `{default}` literal is checked against `Pick<…, "default">` — against
       * the whole type it fails tsc. Schemastery wraps the absent volatile
       * itself, and without a `settings` service (no profileContext) nothing
       * can select another default: bootFace asserts `defaultId === kairos`.
       * `roots`, `trust` and `includeUserRoot` no longer exist anywhere — the
       * registry scans no directory, and the `trust`-gated copy/remove/
       * openDocument Remotes the 0.1.1 row defended against are gone; the
       * Remote surface is `list`, `read`, `select` (NEW
       * packages/preset/agent-preset-registry/src/index.ts:170, 193, 318). */
      { id: AGENT_PRESET_REGISTRY_ROW_ID, name: "@deepseek-ai/dsh-agent-preset-registry",
        config: { default: DEFAULT_PRESET } satisfies Pick<AgentPresetRegistryConfig, "default"> },
      /* The default preset, declared STATICALLY so it exists before the first
       * `session/create`. Its plugins are `[]` — the host composition itself —
       * which the registry accepts (NEW packages/preset/agent-preset-registry/
       * src/definition.ts:18-39; agent-preset README's own minimal example).
       * Row id = `presetRowId(config.id)`; the spread keeps the caller's
       * definition object out of the composed tree. */
      { id: presetRowId(defaultPreset.id), name: "@deepseek-ai/dsh-agent-preset",
        config: { ...defaultPreset } satisfies AgentPresetConfig },
    ],
  }];
}
