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
import { join } from "node:path";
import type { Config as WebServerConfig } from "@deepseek-ai/dsh-host-webserver";
import type { ConnectionConfig } from "@deepseek-ai/dsh-client-connection";
import type { Config as StorageJsonConfig } from "@deepseek-ai/dsh-storage-json";
import type { Config as StorageDomainConfig } from "@deepseek-ai/dsh-storage-domain";

export interface FaceRowEntry {
  id: string;
  name: string;
  config?: Record<string, unknown>;
}
export interface FacePatchEntry {
  insert?: FaceRowEntry[];
}

/**
 * The face's patch layer: the host rows dsh-base does not mount.
 * @param port - the webserver's TCP port; `0` asks the OS for a free one.
 * @param dshHome - the resolved harness home, for rows that must name a
 * directory under it. Passed rather than resolved from `$DSH_HOME` so a
 * composition for an explicit home cannot write into the ambient one — the
 * `!!js dshHomePath(...)` expressions dsh-web-app uses are evaluated by the
 * tree at mount time, and the face has no expression to evaluate.
 */
export function faceOverlay(port: number, dshHome: string): FacePatchEntry[] {
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
    ],
  }];
}
