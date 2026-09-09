/** The face's host rows, applied as the last patch layer over the `face`
 * profile (bundles: dsh-base only). Mirrors the row set dsh-web-app's bundle
 * patch mounts (its cordis.patch.yml at 0.1.1-rc.2, layer 1-2), minus every
 * frontend/client-ui row — the face serves its own UI (spec section 3.2).
 * Static config replaces the webStartup `!!js` expressions: no dsh-web-app.
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
import type { Config as StorageJsonConfig } from "@deepseek-ai/dsh-storage-json";
import type { Config as StorageDomainConfig } from "@deepseek-ai/dsh-storage-domain";
import type { Config as AgentPresetsConfig } from "@deepseek-ai/dsh-agent-presets";
import type { Config as ProjectionCacheConfig } from "@deepseek-ai/dsh-session-projection-cache";

export interface FaceRowEntry {
  id: string;
  name: string;
  config?: Record<string, unknown>;
}
export interface FacePatchEntry {
  insert?: FaceRowEntry[];
}

/** The repository's bot directory — the ONLY preset root the face scans. Module-relative. */
export const BOTS_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "bots");
/** The inert preset every session that names none joins (spec S3). */
export const DEFAULT_PRESET = "kairos";
export const AGENT_PRESETS_ROW_ID = "agent-presets";
export const PROJECTION_CACHE_ROW_ID = "session-projection-cache";
/** dsh-base's system-prompt row, whose `persona` composeFace sets (boot.ts). */
export const SYSTEM_PROMPT_ROW_ID = "system-prompt";

/**
 * The face's patch layer: the host rows dsh-base does not mount.
 * @param port - the webserver's TCP port; `0` asks the OS for a free one.
 * @param dshHome - the resolved harness home, for rows that must name a
 * directory under it. Passed rather than resolved from `$DSH_HOME` so a
 * composition for an explicit home cannot write into the ambient one — the
 * `!!js dshHomePath(...)` expressions dsh-web-app uses are evaluated by the
 * tree at mount time, and the face has no expression to evaluate.
 * @param botsRoot - the preset root the roster scans, normally {@link BOTS_ROOT};
 * passed for the same reason `dshHome` is, so a test can point it at a fixture.
 */
export function faceOverlay(port: number, dshHome: string, botsRoot: string): FacePatchEntry[] {
  return [{
    insert: [
      /* The storage → domain → workspace chain. NOT optional and NOT
       * frontend: the api-gateway row below injects `workspaceRegistry`, which
       * dsh-workspace provides, which needs `storageDomain`, which needs
       * `storage` plus a backend. dsh-base mounts none of the four (they are
       * mode-bundle rows in dsh-web-app), so without them the api-gateway row
       * never activates and boot fails the whole tree with "pending (waiting
       * for service: workspaceRegistry)". */
      { id: "storage", name: "@deepseek-ai/dsh-storage" },
      { id: "storage-json", name: "@deepseek-ai/dsh-storage-json",
        config: { root: join(dshHome, "storages") } satisfies StorageJsonConfig },
      { id: "storage-domain", name: "@deepseek-ai/dsh-storage-domain",
        config: { backend: "json" } satisfies StorageDomainConfig },
      { id: "workspace", name: "@deepseek-ai/dsh-workspace" },

      { id: "directory-picker", name: "@deepseek-ai/dsh-host-directory-picker-auto" },
      { id: "api-gateway", name: "@deepseek-ai/dsh-host-apiproxy" },
      { id: "cordis-host-runner", name: "@deepseek-ai/dsh-cordis-host-runner" },
      { id: "webserver", name: "@deepseek-ai/dsh-host-webserver",
        config: { host: "127.0.0.1", port } satisfies WebServerConfig },
      { id: "connection", name: "@deepseek-ai/dsh-client-connection",
        config: { trustedHosts: [] } satisfies ConnectionConfig },

      /* The model-facing half of the question seam, and the one row above that
       * the "mirror dsh-web-app's bundle patch" rule does not reach: upstream
       * puts `ask_user_question` in no bundle at all. dsh-web-app DISABLES
       * dsh-base's tool rows and lets each session mount an agent preset
       * instead; ask_user rides the shipped `standard` preset, whose root sits
       * beside the CLI app package that this face deliberately does not graft
       * (boot.ts, divergence 4). So the face keeps dsh-base's flat tool roster
       * and inherits its one hole: dsh-base mounts the `user-questions` SERVICE
       * and nothing that lets a model reach it. The two halves fail
       * INDEPENDENTLY, and that is what made the hole invisible - the tree came
       * up healthy, `bootFace`'s Gate-2 service check passed, the model was
       * offered its full toolset, and Kairos simply never asked anything. No
       * error, no card, no pending question; just an agent that guesses.
       * Measured 2026-09-02 on a real session: 35 tools offered, none of them
       * this one. Face-owned rather than left to the operator's patch layer for
       * the same reason `webserver` is: this overlay composes LAST, so a patch
       * aimed at a row it owns is silently overridden - and losing the agent's
       * voice to a silent override is the exact failure the row exists to
       * prevent. Configless by contract (`apply(ctx)`, no exported Config), so
       * it joins the unconfigured rows rather than the `satisfies` set. */
      { id: "tool-ask-user", name: "@deepseek-ai/dsh-tool-ask-user" },

      /* R13. `session.list` fills a session's `projections` column from
       * `sessionProjections.snapshot` when the session is attached in this
       * boot and from `sessionProjectionCache.cachedSnapshot` when it is cold
       * (dsh-host-apiproxy `listProjectionsFor`). dsh-base composes the
       * registry and NOT the cache, so every cold session listed with no
       * column at all and the sidebar read `untitled` after every restart
       * (measured 2026-09-08: 24 sessions, none with a block). The cache
       * writes a whole-record checkpoint at every `turn/end` and at session
       * disposal, throttled between by these two REQUIRED keys - the values
       * are dsh-web-app's own. It fills forward only: a session cold before
       * this row existed stays `untitled` until it is resumed and completes a
       * turn. The `room` projection unit (src/room-projection.ts) rides the
       * same cache, which is what lets a cold room keep its member states. */
      { id: PROJECTION_CACHE_ROW_ID, name: "@deepseek-ai/dsh-session-projection-cache",
        config: { writeEveryEvents: 200, writeIntervalMs: 5000 } satisfies ProjectionCacheConfig },

      /* A bot is a dsh agent preset: a directory under `bots/` holding one
       * `agent.cordis.yml` (spec §2). The roster's only root is the repository's
       * own `bots/` — `includeUserRoot: false` keeps `$DSH_HOME/.agent-presets`
       * out, so a bot the repository does not carry cannot exist. `default` is
       * REQUIRED by the plugin and is what the gateway mounts for a session that
       * names no preset: `kairos`, an empty composition, so Kairos's own sessions
       * keep the flat host roster unchanged (spec S3). The plugin warns on every
       * agent created outside a preset once a roster is mounted; the default
       * makes that warning unreachable.
       *
       * `trust: "system"`, not `"user"`: the face authors bots by its own
       * filesystem write, so it needs no writable root, and `user` trust arms
       * exactly the three RPCs the face does not want - `agentPreset.copy`,
       * `.remove` and `.openDocument`, which the gateway serves on `/api` for
       * any connected client (dsh-host-apiproxy). Under `system` each refuses
       * with "it ships with the deployment" (`deleteComposition`,
       * `writableRoot`), and `authorable` reads false. Trust gates nothing
       * else: `scanRoot` merely stamps it on the row, and MOUNTING never reads
       * it - so the roster, the broken reasons and every preset session are
       * unchanged. Deleting a bot stays `git rm`, as face/README.md says. */
      { id: AGENT_PRESETS_ROW_ID, name: "@deepseek-ai/dsh-agent-presets",
        config: {
          default: DEFAULT_PRESET,
          roots: [{ path: botsRoot, trust: "system" }],
          includeUserRoot: false,
        } satisfies AgentPresetsConfig },
    ],
  }];
}
