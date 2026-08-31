/** The face's host rows, applied as the last patch layer over the `face`
 * profile (bundles: dsh-base only). Mirrors the row set dsh-web-app's bundle
 * patch mounts (its cordis.patch.yml at 0.1.1-rc.2, layer 1-2), minus every
 * frontend/client-ui row — the face serves its own UI (spec section 3.2).
 * Static config replaces the webStartup `!!js` expressions: no dsh-web-app.
 * @module
 */

/* The two configured rows are `satisfies`-checked against the plugins' OWN
 * exported config types, not against FaceRowEntry.config — the loader types
 * every row's config as `any`, so without this an rc that renames a key or
 * narrows a value would load a silently dead config instead of failing tsc. */
import type { Config as WebServerConfig } from "@deepseek-ai/dsh-host-webserver";
import type { ConnectionConfig } from "@deepseek-ai/dsh-client-connection";

export interface FaceRowEntry {
  id: string;
  name: string;
  config?: Record<string, unknown>;
}
export interface FacePatchEntry {
  insert?: FaceRowEntry[];
}

export function faceOverlay(port: number): FacePatchEntry[] {
  return [{
    insert: [
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
