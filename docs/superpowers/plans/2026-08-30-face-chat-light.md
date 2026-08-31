# face/ chat-light Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single Node 22 process (`face/`) that boots the DeepSeek Harness in-process from a dedicated `face` profile and serves the operator's chat-light UI at `http://127.0.0.1:3090/`, with a live composer, live event stream, and the Gate-2 approval surface.

**Architecture:** TypeScript server re-implements the dsh CLI's private profile-composition (~60 lines, mirrored with citation) and boots via the public `@deepseek-ai/dsh-app-boot` seams; a programmatic overlay patch inserts the host rows (webserver on :3090, api-gateway, connection, directory-picker, cordis-host-runner); our static routes claim `/` (no bundled frontend). The client is the round-4 chat-light kit gone live: vanilla JS ESM, no bundler — a pure event→view mapper (unit-tested) plus a thin DOM renderer.

**Tech Stack:** Node 22, TypeScript (strict, ESM), `tsx` for run/test execution, `node:test` runner, `@deepseek-ai/dsh-*` family pinned exactly to `0.1.1-rc.2`. No frameworks, no bundler, no other deps.

**Spec:** `docs/superpowers/specs/2026-08-30-face-chat-light-design.md` (read it first; it carries the recon citations and the risk register)

## Global Constraints

- Every `@deepseek-ai/*` dependency pinned EXACTLY `0.1.1-rc.2` (lockstep peers; mixed versions break the wire contract). Commit `package-lock.json`.
- Node 22 target (`engines: {"node": ">=22"}`); ESM everywhere (`"type": "module"`).
- Loopback only: webserver host `127.0.0.1`, port `3090` (`FACE_PORT` overrides).
- `FACE_PROFILE` default `face`; the face NEVER edits profiles ($DSH_HOME is operator territory; setup refuses overwrite).
- Never touch `ALPACA_KIT_ENABLE_ORDERS`, order tools, or `dsh/` repo config.
- The Python suite must stay green and untouched: run `python -m pytest` before the final commit of any task that touched anything outside `face/` (Tasks 9–10).
- All shell commands below run from the repo root `/Users/pan/Desktop/self-evolve/evolving-alpha-us` unless the step says otherwise.
- The dsh packages' real behavior outranks this plan's code sketches: where a pinned `.d.ts` disagrees with a sketch (property name, config key), follow the `.d.ts` and say so in the commit message. The reference install to consult is `/Users/pan/.local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/<pkg>` (same version we pin).

---

### Task 1: Scaffold `face/` with pinned deps

**Files:**
- Create: `face/package.json`, `face/tsconfig.json`, `face/.gitignore`, `face/src/version.ts`, `face/tests/version.test.ts`

**Interfaces:**
- Produces: the compilable package every later task builds in; `DSH_PIN = "0.1.1-rc.2"` exported from `src/version.ts`.

- [ ] **Step 1: Write package.json**

```json
{
  "name": "kairos-face",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "engines": { "node": ">=22" },
  "scripts": {
    "typecheck": "tsc --noEmit",
    "test": "tsx --test tests/*.test.ts",
    "start": "tsx src/main.ts",
    "setup": "tsx src/setup.ts"
  },
  "dependencies": {
    "@deepseek-ai/cordis": "0.1.1-rc.2",
    "@deepseek-ai/dsh-app-boot": "0.1.1-rc.2",
    "@deepseek-ai/dsh-base": "0.1.1-rc.2",
    "@deepseek-ai/dsh-client-connection": "0.1.1-rc.2",
    "@deepseek-ai/dsh-cmdline": "0.1.1-rc.2",
    "@deepseek-ai/dsh-cordis-host-runner": "0.1.1-rc.2",
    "@deepseek-ai/dsh-home-paths": "0.1.1-rc.2",
    "@deepseek-ai/dsh-host-apiproxy": "0.1.1-rc.2",
    "@deepseek-ai/dsh-host-directory-picker-auto": "0.1.1-rc.2",
    "@deepseek-ai/dsh-host-webserver": "0.1.1-rc.2",
    "@deepseek-ai/dsh-launch-environment": "0.1.1-rc.2"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "tsx": "^4.19.0",
    "@types/node": "^22.0.0"
  }
}
```

- [ ] **Step 2: Write tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": false,
    "types": ["node"]
  },
  "include": ["src/**/*.ts", "tests/**/*.ts"]
}
```

`face/.gitignore`: `node_modules/`

- [ ] **Step 3: Install and check the pins resolve**

Run: `cd face && npm install`
Expected: installs; if any `@deepseek-ai` package does not exist on the npm registry at `0.1.1-rc.2`, STOP — fallback per spec risk (a): add `"overrides"`/file references to the local install at `/Users/pan/.local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/<pkg>` (use `file:` deps for the whole family), note it in the commit message, and continue. Peer-dependency warnings about sibling dsh packages are expected — npm ≥7 auto-installs them; a peer ERROR at a different version is a stop-and-look.

- [ ] **Step 4: Write the failing test**

`face/tests/version.test.ts`:
```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { DSH_PIN } from "../src/version.ts";
import { createRequire } from "node:module";

test("every installed @deepseek-ai package matches the pin", () => {
  assert.equal(DSH_PIN, "0.1.1-rc.2");
  const require = createRequire(import.meta.url);
  for (const pkg of [
    "@deepseek-ai/dsh-app-boot", "@deepseek-ai/dsh-base",
    "@deepseek-ai/dsh-host-apiproxy", "@deepseek-ai/dsh-host-webserver",
    "@deepseek-ai/dsh-client-connection",
  ]) {
    const version = require(`${pkg}/package.json`).version as string;
    assert.equal(version, DSH_PIN, pkg);
  }
});
```

Run: `cd face && npm test`
Expected: FAIL (cannot find `../src/version.ts`)

- [ ] **Step 5: Implement `src/version.ts`, verify pass + typecheck**

```typescript
/** The dsh family version this face is built against. Upgrade = bump here +
 * package.json together, then run the README upgrade drill (spec section 4). */
export const DSH_PIN = "0.1.1-rc.2";
```

Run: `cd face && npm test && npm run typecheck`
Expected: PASS, clean typecheck

- [ ] **Step 6: Commit**

```bash
git add face/package.json face/package-lock.json face/tsconfig.json face/.gitignore face/src/version.ts face/tests/version.test.ts
git commit -m "feat(face): scaffold kairos-face with the dsh family pinned to 0.1.1-rc.2"
```

---

### Task 2: The face overlay (host rows as a programmatic patch)

**Files:**
- Create: `face/src/overlay.ts`, `face/tests/overlay.test.ts`

**Interfaces:**
- Produces: `faceOverlay(port: number): PatchEntry[]` where `PatchEntry` is `{ insert?: RowEntry[] }` and `RowEntry` is `{ id: string; name: string; config?: Record<string, unknown> }` (exported types `FacePatchEntry`, `FaceRowEntry`). Task 3 passes the result into `boot()`'s patch stack.

- [ ] **Step 1: Write the failing test**

`face/tests/overlay.test.ts`:
```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { faceOverlay } from "../src/overlay.ts";

test("overlay inserts exactly the five host rows with loopback config", () => {
  const patches = faceOverlay(3090);
  assert.equal(patches.length, 1);
  const rows = patches[0].insert!;
  const byId = new Map(rows.map(r => [r.id, r]));
  assert.deepEqual(
    [...byId.keys()].sort(),
    ["api-gateway", "connection", "cordis-host-runner", "directory-picker", "webserver"],
  );
  assert.equal(byId.get("webserver")!.name, "@deepseek-ai/dsh-host-webserver");
  assert.deepEqual(byId.get("webserver")!.config, { host: "127.0.0.1", port: 3090 });
  assert.equal(byId.get("api-gateway")!.name, "@deepseek-ai/dsh-host-apiproxy");
  assert.equal(byId.get("connection")!.name, "@deepseek-ai/dsh-client-connection");
  assert.deepEqual(byId.get("connection")!.config, { trustedHosts: [] });
  assert.equal(byId.get("directory-picker")!.name, "@deepseek-ai/dsh-host-directory-picker-auto");
  assert.equal(byId.get("cordis-host-runner")!.name, "@deepseek-ai/dsh-cordis-host-runner");
});
```

Run: `cd face && npm test` — Expected: FAIL (module not found)

- [ ] **Step 2: Implement `src/overlay.ts`**

```typescript
/** The face's host rows, applied as the last patch layer over the `face`
 * profile (bundles: dsh-base only). Mirrors the row set dsh-web-app's bundle
 * patch mounts (its cordis.patch.yml at 0.1.1-rc.2, layer 1-2), minus every
 * frontend/client-ui row — the face serves its own UI (spec section 3.2).
 * Static config replaces the webStartup `!!js` expressions: no dsh-web-app. */
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
        config: { host: "127.0.0.1", port } },
      { id: "connection", name: "@deepseek-ai/dsh-client-connection",
        config: { trustedHosts: [] } },
    ],
  }];
}
```

Before finalizing, open the pinned `.d.ts` for `@deepseek-ai/dsh-client-connection` (reference install path in Global Constraints) and confirm its Config keys (`trustedHosts`) — adjust if the schema differs, and mirror any required key into both test and implementation.

- [ ] **Step 3: Verify pass + typecheck** — Run: `cd face && npm test && npm run typecheck` — Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add face/src/overlay.ts face/tests/overlay.test.ts
git commit -m "feat(face): host-row overlay patch - webserver 3090, api gateway, connection"
```

---

### Task 3: Profile setup script (creates `$DSH_HOME/profiles/face/`)

**Files:**
- Create: `face/src/setup.ts`, `face/tests/setup.test.ts`

**Interfaces:**
- Produces: `setupFaceProfile(dshHome: string, profileName = "face"): { created: boolean; dir: string }` — creates the profile directory, package.json (bundles `["@deepseek-ai/dsh-base"]`), and an empty commented `cordis.patch.yml`; REFUSES overwrite (`created: false`, touches nothing) when the directory exists. `src/setup.ts` run directly (npm run setup) calls it with the real `$DSH_HOME` (default `~/.dsh`, `DSH_HOME` env override).

- [ ] **Step 1: Write the failing test**

`face/tests/setup.test.ts`:
```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";

test("creates the face profile with dsh-base bundle and empty patch layer", () => {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  const res = setupFaceProfile(home);
  assert.equal(res.created, true);
  const pkg = JSON.parse(readFileSync(join(res.dir, "package.json"), "utf8"));
  assert.deepEqual(pkg.dsh.profile.bundles, ["@deepseek-ai/dsh-base"]);
  assert.equal(pkg.private, true);
  const patch = readFileSync(join(res.dir, "cordis.patch.yml"), "utf8");
  assert.match(patch, /^#/m);           // commented header
  assert.doesNotMatch(patch, /^- /m);   // no active entries
});

test("refuses to overwrite an existing profile", () => {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  const dir = join(home, "profiles", "face");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "cordis.patch.yml"), "# operator content\n");
  const res = setupFaceProfile(home);
  assert.equal(res.created, false);
  assert.equal(readFileSync(join(dir, "cordis.patch.yml"), "utf8"), "# operator content\n");
});
```

Run: `cd face && npm test` — Expected: FAIL

- [ ] **Step 2: Implement `src/setup.ts`**

```typescript
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
```

- [ ] **Step 3: Verify pass + typecheck** — `cd face && npm test && npm run typecheck` — PASS

- [ ] **Step 4: Commit**

```bash
git add face/src/setup.ts face/tests/setup.test.ts
git commit -m "feat(face): profile setup - dsh-base-only face profile, refuses overwrite"
```

---

### Task 4: Boot module (the mirrored composition + `bootFace`)

**Files:**
- Create: `face/src/boot.ts`, `face/tests/boot.test.ts`

**Interfaces:**
- Consumes: `faceOverlay` (Task 2), a profile laid out by `setupFaceProfile` (Task 3).
- Produces: `composeFace(opts: { profileName: string; port: number; dshHome?: string }): { patches: unknown[]; rootConfig: string }` (pure composition, testable offline) and `bootFace(opts): Promise<{ ctx: any; dispose(): Promise<void> }>` (live boot; `ctx` is the cordis Context — typed `any` at our boundary deliberately: the Context module augmentations across dsh packages are the moving part, and our compile-time contract is the package `.d.ts` imports themselves).

- [ ] **Step 1: Verify the app-boot exports this module needs**

Run:
```bash
grep -o "export [a-zA-Z ,{}]*" /Users/pan/.local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-app-boot/lib/types/index.d.ts | head -40
grep -rn "DSH_LAUNCH_ENVIRONMENT_KEY\|provideCmdline\|loadLayeredEnv" /Users/pan/.local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-launch-environment/lib/types/ /Users/pan/.local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-cmdline/lib/types/ /Users/pan/.local/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-app-boot/lib/types/ | head
```
Expected: confirm the import sources for `loadProfile`, `loadOptionalPatches`, `healProfilesModuleFallback`, `boot`, `loadLayeredEnv`, `DSH_LAUNCH_ENVIRONMENT_KEY`, `provideCmdline` and their signatures. If a name lives elsewhere, adjust the imports in Steps 2/4 — the shapes below are from the recon and the CLI chunk.

- [ ] **Step 2: Write the failing composition test**

`face/tests/boot.test.ts`:
```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setupFaceProfile } from "../src/setup.ts";
import { composeFace } from "../src/boot.ts";

test("composeFace: patch order ends with the face overlay; root is rewritten empty", () => {
  const home = mkdtempSync(join(tmpdir(), "face-home-"));
  setupFaceProfile(home);
  const { patches, rootConfig } = composeFace({ profileName: "face", port: 3090, dshHome: home });
  // the profile root file was rewritten to the empty include root (the
  // write-back guard - skipping this corrupts subsequent boots)
  assert.match(readFileSync(rootConfig, "utf8"), /\[\]/);
  // last layer is ours: find the webserver row in the final insert patch
  const last = patches.at(-1) as { insert?: Array<{ id: string; config?: { port?: number } }> };
  const ws = last.insert?.find(r => r.id === "webserver");
  assert.equal(ws?.config?.port, 3090);
  // base bundle layer present (dsh-base contributes patches before ours)
  assert.ok(patches.length > 1, "bundle patches precede the face overlay");
});
```

Run: `cd face && npm test` — Expected: FAIL (`composeFace` not found)

- [ ] **Step 3: Implement `composeFace` in `src/boot.ts`**

```typescript
/** Mirrors the dsh CLI's private profile composition (profile-boot chunk,
 * @deepseek-ai/dsh 0.1.1-rc.2, functions prepareProfile/composeProfile/
 * runProfile). The CLI does not export it; on every DSH_PIN bump, re-diff
 * this file against the CLI's current profile-boot-*.js (spec section 4).
 * Divergences from runProfile, all deliberate v1 scope cuts: no --patch
 * overlay files, no HMR/patch watchers, no installFailLoud, no shipped
 * agent-presets root graft (the face profile mounts none), telemetry
 * patch honored via DSH_TELEMETRY_DISABLED same as the CLI. */
import { writeFileSync } from "node:fs";
import { join } from "node:path";
import { createRequire } from "node:module";
import {
  boot, healProfilesModuleFallback, loadLayeredEnv, loadOptionalPatches, loadProfile,
} from "@deepseek-ai/dsh-app-boot";
import { DSH_LAUNCH_ENVIRONMENT_KEY } from "@deepseek-ai/dsh-launch-environment";
import { provideCmdline } from "@deepseek-ai/dsh-cmdline";
import { faceOverlay } from "./overlay.ts";

const BIN = "dsh";
const PROFILE_ROOT_FILENAME = "cordis.yml";
const PROFILE_ROOT_CONFIG = "# face root - composed entirely from patch layers; do not edit\n[]\n";
const require = createRequire(import.meta.url);
/** Anchor bundle resolution at OUR node_modules (we depend on dsh-base). */
const INSTALL_ANCHOR = join(require.resolve("@deepseek-ai/dsh-base/package.json"), "..", "..", "..", "..");

export interface FaceBootOptions { profileName: string; port: number; dshHome?: string }

export function composeFace(opts: FaceBootOptions): { patches: unknown[]; rootConfig: string } {
  if (opts.dshHome) process.env.DSH_HOME = opts.dshHome;
  healProfilesModuleFallback(INSTALL_ANCHOR);
  const profile = loadProfile(BIN, opts.profileName, INSTALL_ANCHOR, opts.dshHome, { userLayer: true });
  // the write-back guard: always rewrite the root to the empty include root
  writeFileSync(join(profile.dir, PROFILE_ROOT_FILENAME), PROFILE_ROOT_CONFIG);
  const bundlePatches = profile.layers.flatMap((layer: { patches: unknown[] }) => layer.patches);
  const homePatches = loadOptionalPatches(BIN, join(process.env.DSH_HOME!, "cordis.patch.yml")) ?? [];
  const telemetry = (process.env.DSH_TELEMETRY_DISABLED ?? "") !== ""
    ? [{ id: "telemetry", disabled: true }] : [];
  const patches = [
    ...bundlePatches,
    ...profile.patches,
    ...homePatches,
    ...telemetry,
    ...faceOverlay(opts.port),
  ];
  return { patches, rootConfig: join(profile.dir, PROFILE_ROOT_FILENAME) };
}
```

NOTE for the implementer: `loadProfile`'s exact return shape (`dir`, `patches`, `patchPath`, `layers[].patches`) and `homePatchPath` handling come from the pinned `.d.ts` (Step 1) — if `loadProfile` does not accept a home override argument, set `process.env.DSH_HOME` before the call (already done above) and drop the argument. The telemetry row id must match the base bundle's actual telemetry row id — grep `dsh-base/cordis.patch.yml` for `telemetry` and use its id; if the base has no such row, drop the telemetry block entirely (matching `resolveTelemetryPatch`'s `hasRow` guard).

- [ ] **Step 4: Run composition test — PASS; then add `bootFace`**

Run: `cd face && npm test` — composition test must PASS first.

Append to `src/boot.ts`:
```typescript
export async function bootFace(opts: FaceBootOptions): Promise<{ ctx: any; dispose(): Promise<void> }> {
  loadLayeredEnv();
  const { patches, rootConfig } = composeFace(opts);
  const ctx: any = await boot(BIN, rootConfig, structuredClone(patches), (hostCtx: any) => {
    hostCtx.provide(DSH_LAUNCH_ENVIRONMENT_KEY, {
      cwd: process.cwd(), env: process.env, argv: [],
    });
    provideCmdline(hostCtx, { args: [], exit: (code: number) => process.exit(code) });
  });
  // Gate 2 precondition (spec section 3.2): base must have mounted these.
  if (ctx.get("approval") === undefined || ctx.get("userQuestions") === undefined) {
    await ctx.fiber.dispose();
    throw new Error("face: approval/user-questions rows missing from the composed tree - Gate 2 would fail closed invisibly");
  }
  let disposed = false;
  return {
    ctx,
    dispose: async () => { if (!disposed) { disposed = true; await ctx.fiber.dispose(); } },
  };
}
```
The launch-environment payload shape and `loadLayeredEnv` invocation come from the pinned `.d.ts` (Step 1) — follow them where they differ. `ctx.get("userQuestions")` vs `"user-questions"`: check the service name in `dsh-user-questions`'s `.d.ts` and use that string.

- [ ] **Step 5: Typecheck + full test run** — `cd face && npm run typecheck && npm test` — PASS (bootFace has no unit test; the boot smoke in Task 8 covers it)

- [ ] **Step 6: Commit**

```bash
git add face/src/boot.ts face/tests/boot.test.ts
git commit -m "feat(face): mirrored profile composition and bootFace with Gate-2 precondition"
```

---

### Task 5: Static UI mount + main entry

**Files:**
- Create: `face/src/static.ts`, `face/src/main.ts`, `face/tests/static.test.ts`
- Create (placeholder page, replaced by Task 6): `face/client/index.html`

**Interfaces:**
- Consumes: `bootFace` (Task 4); `ctx.webServer.register(route: { kind: "exact" | "prefix"; path: string; handler(req, res): void })` (pinned `.d.ts`, `@deepseek-ai/dsh-host-webserver`).
- Produces: `contentTypeFor(path: string): string` and `registerStatic(webServer: { register(r: any): void }, clientDir: string): void` registering `exact /` → index.html and `prefix /client` → files under `clientDir` (path-traversal-safe).

- [ ] **Step 1: Write the failing tests**

`face/tests/static.test.ts`:
```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { contentTypeFor, resolveClientPath } from "../src/static.ts";

test("content types", () => {
  assert.equal(contentTypeFor("index.html"), "text/html; charset=utf-8");
  assert.equal(contentTypeFor("chat.css"), "text/css; charset=utf-8");
  assert.equal(contentTypeFor("api.js"), "text/javascript; charset=utf-8");
  assert.equal(contentTypeFor("x.unknown"), "application/octet-stream");
});

test("resolveClientPath refuses traversal out of the client dir", () => {
  assert.equal(resolveClientPath("/client/../../etc/passwd", "/srv/client"), null);
  assert.equal(resolveClientPath("/client/chat.css", "/srv/client"), "/srv/client/chat.css");
});
```

Run: `cd face && npm test` — Expected: FAIL

- [ ] **Step 2: Implement `src/static.ts`**

```typescript
import { readFile } from "node:fs/promises";
import { join, normalize, extname, resolve, sep } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";

const TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};
export function contentTypeFor(path: string): string {
  return TYPES[extname(path)] ?? "application/octet-stream";
}

/** /client/<file> -> absolute path inside clientDir, or null on traversal. */
export function resolveClientPath(urlPath: string, clientDir: string): string | null {
  const rel = normalize(urlPath.replace(/^\/client\/?/, "")).replace(/^([/\\])+/, "");
  const abs = resolve(clientDir, rel);
  return abs === clientDir || abs.startsWith(clientDir + sep) ? abs : null;
}

async function serveFile(res: ServerResponse, path: string): Promise<void> {
  try {
    const body = await readFile(path);
    res.writeHead(200, { "content-type": contentTypeFor(path) });
    res.end(body);
  } catch {
    res.writeHead(404, { "content-type": "text/plain" });
    res.end("not found");
  }
}

export function registerStatic(webServer: { register(r: unknown): void }, clientDir: string): void {
  webServer.register({
    kind: "exact", path: "/",
    handler: (_req: IncomingMessage, res: ServerResponse) => serveFile(res, join(clientDir, "index.html")),
  });
  webServer.register({
    kind: "prefix", path: "/client",
    handler: (req: IncomingMessage, res: ServerResponse) => {
      const target = resolveClientPath(req.url ?? "", clientDir);
      if (target === null) { res.writeHead(403); res.end(); return; }
      return serveFile(res, target);
    },
  });
}
```

- [ ] **Step 3: Verify pass** — `cd face && npm test && npm run typecheck` — PASS

- [ ] **Step 4: Write `src/main.ts` and the placeholder page**

```typescript
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { bootFace } from "./boot.ts";
import { registerStatic } from "./static.ts";

const port = Number(process.env.FACE_PORT ?? 3090);
const profileName = process.env.FACE_PROFILE ?? "face";
const clientDir = join(dirname(fileURLToPath(import.meta.url)), "..", "client");

const { ctx, dispose } = await bootFace({ profileName, port });
registerStatic(ctx.webServer, clientDir);
console.log(`kairos-face: http://127.0.0.1:${ctx.webServer.port}/ (profile: ${profileName})`);

for (const sig of ["SIGINT", "SIGTERM"] as const) {
  process.on(sig, () => { void dispose().then(() => process.exit(sig === "SIGINT" ? 130 : 0)); });
}
```

`face/client/index.html` (placeholder until Task 6):
```html
<!doctype html>
<meta charset="utf-8">
<title>KAIROS</title>
<p>kairos-face booted. Client lands in the next task.</p>
```

- [ ] **Step 5: Typecheck, then a manual boot probe (best-effort, not a gate)**

Run: `cd face && npm run typecheck` — PASS required.
Then (only if `~/.dsh` exists on this machine): `cd face && DSH_HOME=$HOME/.dsh npm run setup && timeout 60 npm start` in one terminal; in another: `curl -s http://127.0.0.1:3090/ | head -3` → expect the placeholder HTML. If boot fails on a missing service/config, capture the error into the task notes — Task 8's smoke is the real gate; do not thrash here.

- [ ] **Step 6: Commit**

```bash
git add face/src/static.ts face/src/main.ts face/tests/static.test.ts face/client/index.html
git commit -m "feat(face): static UI mount and main entry - face serves / on 3090"
```

---

### Task 6: Client — api envelope + pure event mapper (tested), ported r4 kit

**Files:**
- Create: `face/client/api.js`, `face/client/mapper.js`, `face/tests/mapper.test.ts`, `face/tests/fixtures/events.jsonl`
- Create: `face/client/chat.css` (copy `docs/design/prototypes/r4/chat.css`, then apply the two edits in Step 5)

**Interfaces:**
- Consumes: the dsh wire contract — `POST /api/<method>` envelope `{type:"client-request", rpcId, method, payload}` → `{type:"server-response", rpcId, result:{ok,...}}`; WS `GET /api/events.mux`.
- Produces: `client/api.js` exporting `rpc(method, payload)` and `openMux(onFrame)`; `client/mapper.js` exporting `mapFrame(frame)` → view-model objects `{ kind: "bubble"|"card"|"approval"|"question"|"ignore", role?, text?, card?, id? }` consumed by Task 7's renderer.

- [ ] **Step 1: Record fixtures**

`face/tests/fixtures/events.jsonl` — one JSON per line, the frame shapes the mapper must handle (taken from the pinned `@deepseek-ai/dsh-host-apiproxy/lib/types/api/events.d.ts` + `approvals.d.ts` + `questions.d.ts`; before writing, open those `.d.ts` files and adjust field names to the actual schema — the sketches here are the recon's read):
```json
{"sessionId":"s1","event":{"type":"user/message","seq":4,"data":{"text":"两个 pivot 今早都触发了"}}}
{"sessionId":"s1","event":{"type":"assistant/message","seq":7,"data":{"text":"Both pivots are technically valid."}}}
{"sessionId":"s1","event":{"type":"tool/result","seq":9,"data":{"callId":"c1","tool":"breadth","result":{"ok":true}}}}
{"sessionId":"s1","event":{"type":"assistant/chunk","seq":8,"data":{"delta":"…"}}}
{"type":"approval/requested","requestId":"a1","sessionId":"s1","callId":"c1"}
{"type":"question/asked","requestId":"q1","sessionId":"s1","question":{"text":"Proceed?","options":["yes","no"]}}
```

- [ ] **Step 2: Write the failing mapper test**

`face/tests/mapper.test.ts`:
```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
// mapper.js is plain ESM JS - importable from node directly
import { mapFrame } from "../client/mapper.js";

const lines = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "fixtures", "events.jsonl"), "utf8",
).trim().split("\n").map(l => JSON.parse(l));

test("surface events map to bubbles and cards; log-only types are ignored", () => {
  const views = lines.map(mapFrame);
  assert.equal(views[0].kind, "bubble"); assert.equal(views[0].role, "operator");
  assert.match(views[0].text, /pivot/);
  assert.equal(views[1].kind, "bubble"); assert.equal(views[1].role, "kairos");
  assert.equal(views[2].kind, "card");   assert.equal(views[2].card.tool, "breadth");
  assert.equal(views[2].card.callId, "c1");
  assert.equal(views[3].kind, "ignore"); // assistant/chunk is log-only for v1
  assert.equal(views[4].kind, "approval"); assert.equal(views[4].id, "a1");
  assert.equal(views[5].kind, "question"); assert.equal(views[5].id, "q1");
});

test("null-safe: unknown frames never throw, they ignore", () => {
  assert.equal(mapFrame({}).kind, "ignore");
  assert.equal(mapFrame({ event: { type: "weird/thing" } }).kind, "ignore");
});
```

Run: `cd face && npm test` — Expected: FAIL

- [ ] **Step 3: Implement `client/mapper.js`** (plain ESM JS, no TS — it ships to the browser)

```javascript
/** Pure frame -> view-model mapping. No DOM here: this is the tested half.
 * Frame shapes: @deepseek-ai/dsh-host-apiproxy lib/types/api/{events,approvals,questions}.d.ts
 * at the pinned version - adjust here AND in the fixtures on any pin bump. */
export function mapFrame(frame) {
  if (frame && typeof frame.type === "string") {
    if (frame.type === "approval/requested")
      return { kind: "approval", id: frame.requestId, sessionId: frame.sessionId, callId: frame.callId };
    if (frame.type === "question/asked")
      return { kind: "question", id: frame.requestId, sessionId: frame.sessionId, question: frame.question };
  }
  const ev = frame?.event;
  if (!ev || typeof ev.type !== "string") return { kind: "ignore" };
  switch (ev.type) {
    case "user/message":
      return { kind: "bubble", role: "operator", text: ev.data?.text ?? "—", seq: ev.seq };
    case "assistant/message":
      return { kind: "bubble", role: "kairos", text: ev.data?.text ?? "—", seq: ev.seq };
    case "tool/result":
      return { kind: "card", seq: ev.seq,
               card: { tool: ev.data?.tool ?? "tool", callId: ev.data?.callId ?? null, result: ev.data?.result ?? null } };
    default:
      return { kind: "ignore" };
  }
}
```

- [ ] **Step 4: Verify mapper tests pass** — `cd face && npm test` — PASS

- [ ] **Step 5: Write `client/api.js` and port the css**

`client/api.js`:
```javascript
let nextRpcId = 1;
export async function rpc(method, payload = {}) {
  const rpcId = String(nextRpcId++);
  const res = await fetch(`/api/${method}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ type: "client-request", rpcId, method, payload }),
  });
  const body = await res.json();
  if (body?.result?.ok === false) throw new Error(`${method}: ${body.result.error ?? "failed"}`);
  return body.result;
}

/** Mux stream with auto-reconnect; onFrame receives each parsed frame. */
export function openMux(onFrame) {
  let ws, closed = false;
  const connect = () => {
    ws = new WebSocket(`ws://${location.host}/api/events.mux`);
    ws.onmessage = (m) => { try { onFrame(JSON.parse(m.data)); } catch { /* skip bad frame */ } };
    ws.onclose = () => { if (!closed) setTimeout(connect, 1500); };
  };
  connect();
  return { close: () => { closed = true; ws?.close(); } };
}
```
`client/chat.css`: copy from `docs/design/prototypes/r4/chat.css`, then (1) delete any rule matching `.sample` / SAMPLE stamp styling (live data now), (2) change the composer's disabled styling into an enabled state (remove `opacity`/`cursor: not-allowed` on the composer input). Keep every other token verbatim — the light palette is the round-4 verdict.

- [ ] **Step 6: Typecheck + tests + commit**

```bash
cd face && npm run typecheck && npm test
git add face/client/api.js face/client/mapper.js face/client/chat.css face/tests/mapper.test.ts face/tests/fixtures/events.jsonl
git commit -m "feat(face): client api envelope, mux reconnect, tested event mapper, r4 css port"
```

---

### Task 7: Client — renderer, sessions sidebar, live composer, approval cards

**Files:**
- Create: `face/client/chat.js`, `face/client/index.html` (replace Task 5's placeholder)

**Interfaces:**
- Consumes: `rpc`/`openMux` (api.js), `mapFrame` (mapper.js), the chat.css classes ported from r4 (`.sidebar`, `.conv`, `.bubble`, `.card`, `.composer` — use the actual class names found in the ported chat.css).
- Produces: the working page. Wire contract used: `session.list` → `{ok, sessions:[{id,title,...}]}`; `session.create` → `{ok, sessionId}`; `session.prompt` `{sessionId, text}`; `session.history` `{sessionId}` → `{ok, events:[...]}`; `respond` `{requestId, response}` for approvals (`allowed-once` / `rejected`) and questions. BEFORE CODING: open the pinned `.d.ts` under `@deepseek-ai/dsh-host-apiproxy/lib/types/api/` (sessions.d.ts, approvals.d.ts, questions.d.ts) and correct every method name, payload key, and response key above to the actual schema — then keep chat.js consistent with what you found.

- [ ] **Step 1: Write `client/chat.js`**

```javascript
import { rpc, openMux } from "./api.js";
import { mapFrame } from "./mapper.js";

const $ = (sel) => document.querySelector(sel);
let activeSession = null;
const seen = new Set(); // "sessionId:seq" dedupe between history backfill and mux

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function renderView(view) {
  if (view.kind === "ignore") return null;
  if (view.kind === "bubble") {
    const wrap = el("div", `bubble bubble--${view.role === "operator" ? "op" : "kai"}`);
    if (view.role === "kairos") wrap.append(el("div", "bubble-label", "Kairos"));
    wrap.append(el("div", "bubble-text", view.text));
    return wrap;
  }
  if (view.kind === "card") {
    const card = el("div", "card");
    card.append(el("div", "card-kind", view.card.tool));
    card.append(el("pre", "card-body", JSON.stringify(view.card.result, null, 1) ?? "—"));
    const raw = el("div", "card-raw", `raw · ${view.card.tool}${view.card.callId ? " · " + view.card.callId : ""}`);
    card.append(raw);
    return card;
  }
  if (view.kind === "approval" || view.kind === "question") {
    const card = el("div", "card card--ask");
    card.append(el("div", "card-kind", view.kind === "approval" ? "approval requested" : "Kairos asks"));
    if (view.question?.text) card.append(el("div", "card-body", view.question.text));
    const row = el("div", "card-actions");
    const answers = view.kind === "approval"
      ? [["Approve", "allowed-once"], ["Deny", "rejected"]]
      : (view.question?.options ?? ["ok"]).map(o => [o, o]);
    for (const [label, response] of answers) {
      const btn = el("button", "card-btn", label);
      btn.onclick = async () => {
        await rpc("respond", { requestId: view.id, response });
        card.classList.add("card--answered");
        row.replaceChildren(el("span", "card-raw", `answered: ${label}`));
      };
      row.append(btn);
    }
    card.append(row);
    return card;
  }
  return null;
}

function appendView(view) {
  const node = renderView(view);
  if (!node) return;
  const flow = $("#flow");
  flow.append(node);
  flow.scrollTop = flow.scrollHeight;
}

function acceptFrame(frame) {
  const view = mapFrame(frame);
  if (view.kind === "ignore") return;
  const sid = frame.sessionId ?? frame.event?.sessionId ?? null;
  if (sid !== null && activeSession !== null && sid !== activeSession) return;
  if (view.seq !== undefined) {
    const key = `${sid}:${view.seq}`;
    if (seen.has(key)) return;
    seen.add(key);
  }
  appendView(view);
}

async function openSession(id) {
  activeSession = id;
  seen.clear();
  $("#flow").replaceChildren();
  const history = await rpc("session.history", { sessionId: id });
  for (const event of history.events ?? []) acceptFrame({ sessionId: id, event });
  document.querySelectorAll(".conv").forEach(n => n.classList.toggle("conv--active", n.dataset.id === id));
}

async function refreshSessions() {
  const res = await rpc("session.list", {});
  const list = $("#sessions");
  list.replaceChildren();
  for (const s of res.sessions ?? []) {
    const row = el("div", "conv", s.title ?? s.id);
    row.dataset.id = s.id;
    row.onclick = () => void openSession(s.id);
    list.append(row);
  }
}

async function send() {
  const input = $("#composer-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  if (activeSession === null) {
    const created = await rpc("session.create", {});
    activeSession = created.sessionId;
    await refreshSessions();
  }
  await rpc("session.prompt", { sessionId: activeSession, text });
}

$("#composer-form").onsubmit = (e) => { e.preventDefault(); void send(); };
$("#new-session").onclick = () => { activeSession = null; seen.clear(); $("#flow").replaceChildren(); };
openMux(acceptFrame);
void refreshSessions();
```

- [ ] **Step 2: Write `client/index.html`** (structure mirrors the r4 prototype's, minus SAMPLE tags, composer enabled)

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KAIROS</title>
<link rel="stylesheet" href="/client/chat.css">
</head>
<body>
<aside class="sidebar">
  <div class="sidebar-head">KAIROS <button id="new-session" class="conv-new" title="new session">+</button></div>
  <div id="sessions"></div>
  <div class="sidebar-foot">live · loopback only</div>
</aside>
<main class="main">
  <div id="flow" class="flow"></div>
  <form id="composer-form" class="composer">
    <input id="composer-input" type="text" placeholder="Message Kairos…" autocomplete="off">
  </form>
</main>
<script type="module" src="/client/chat.js"></script>
</body>
</html>
```
Adjust class names to the ported chat.css's actual vocabulary (the r4 kit's names win; this sketch's names are indicative). Add any missing structural CSS (sidebar/main two-pane grid) at the END of chat.css under a `/* live additions */` marker.

- [ ] **Step 3: Typecheck + tests still green** — `cd face && npm run typecheck && npm test` — PASS

- [ ] **Step 4: Manual probe (if a booted face is available)**: `npm start`, open http://127.0.0.1:3090/, expect sidebar + composer; a prompt requires `DEEPSEEK_API_KEY` in the env (`source .env.deepseek`) — without it, verify the UI renders and `session.list` answers; note results.

- [ ] **Step 5: Commit**

```bash
git add face/client/chat.js face/client/index.html face/client/chat.css
git commit -m "feat(face): live client - sessions sidebar, composer, stream render, approval cards"
```

---

### Task 8: Boot smoke test (gated, real harness, no LLM calls)

**Files:**
- Create: `face/tests/smoke.test.ts`

**Interfaces:**
- Consumes: `setupFaceProfile`, `bootFace`, `registerStatic` — the whole stack.

- [ ] **Step 1: Write the smoke test**

```typescript
import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { registerStatic } from "../src/static.ts";

const gated = process.env.FACE_SMOKE !== "1";

test("boot smoke: face serves /, /api answers, fence holds", { skip: gated && "set FACE_SMOKE=1" }, async () => {
  const home = mkdtempSync(join(tmpdir(), "face-smoke-"));
  setupFaceProfile(home);
  const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home });
  try {
    const clientDir = join(dirname(fileURLToPath(import.meta.url)), "..", "client");
    registerStatic(ctx.webServer, clientDir);
    const base = `http://127.0.0.1:${ctx.webServer.port}`;

    const index = await fetch(`${base}/`);
    assert.equal(index.status, 200);
    assert.match(await index.text(), /KAIROS/);

    const list = await fetch(`${base}/api/session.list`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ type: "client-request", rpcId: "1", method: "session.list", payload: {} }),
    });
    assert.equal(list.status, 200);
    const body = await list.json();
    assert.equal(body?.result?.ok, true);

    const mux = await fetch(`${base}/api/events.mux`);
    assert.equal(mux.status, 426); // WS upgrade required

    const forged = await fetch(`${base}/api/session.list`, {
      method: "POST", headers: { "content-type": "application/json", host: "evil.example.com" },
      body: JSON.stringify({ type: "client-request", rpcId: "2", method: "session.list", payload: {} }),
    });
    assert.equal(forged.status, 403); // the Host fence, drilled
  } finally {
    await dispose();
  }
});
```

- [ ] **Step 2: Run gated-off (must skip cleanly)** — `cd face && npm test` — smoke shows SKIP, everything else PASS

- [ ] **Step 3: Run for real** — `cd face && FACE_SMOKE=1 npm test`
Expected: PASS. This is the task's real gate. Failures here are information, not thrash: fix the boot/overlay code (config keys, service names) against the pinned `.d.ts` until green, keeping earlier unit tests green. If `fetch` refuses to override the `host` header, use `node:http.request` for the forged-Host probe instead.

- [ ] **Step 4: Commit**

```bash
git add face/tests/smoke.test.ts
git commit -m "test(face): gated boot smoke - static, api, 426 upgrade, host fence drill"
```

---

### Task 9: README with run + upgrade + Gate-2 drill instructions

**Files:**
- Create: `face/README.md`
- Modify: `dsh/README.md` (one pointer line, see Step 2)

- [ ] **Step 1: Write `face/README.md`**

```markdown
# kairos-face — the chat-light face as an in-process dsh host

One Node 22 process: boots the DeepSeek Harness from the `face` profile
(bundles: dsh-base only) and serves the operator's chat UI at
http://127.0.0.1:3090/. Spec: docs/superpowers/specs/2026-08-30-face-chat-light-design.md.

## Run

    cd face
    npm install
    npm run setup            # creates $DSH_HOME/profiles/face (never overwrites)
    source ../.env.deepseek  # LLM key - prompts fail without it; UI works read-only
    npm start                # http://127.0.0.1:3090/  (FACE_PORT/FACE_PROFILE override)

Mount the workbench toolset (alpaca_kit MCP + skills) into
$DSH_HOME/profiles/face/cordis.patch.yml per ../dsh/README.md steps 3-6 —
the face boots with or without it.

## Tests

    npm test                  # offline unit tests
    FACE_SMOKE=1 npm test     # + real boot smoke (temp DSH_HOME, no LLM calls)

## Upgrading the dsh family (pinned 0.1.1-rc.2)

Lockstep only - never mix versions. Bump every @deepseek-ai/* dep AND
src/version.ts together, then: (1) npm run typecheck - contract breaks
surface here; (2) re-diff src/boot.ts against the CLI's current
profile-boot-*.js chunk (the one private piece we mirror); (3) re-check the
frame shapes in client/mapper.js + tests/fixtures/events.jsonl against
lib/types/api/*.d.ts; (4) FACE_SMOKE=1 npm test; (5) run the Gate-2 drill
below. Only then trust it.

## The Gate-2 drill (run after any face or dsh change)

A guard never pulled is presumed broken. With the face live and a session
open, prompt Kairos to run a shell command that the profile's approval
policy marks `ask` (dsh-base ships shell under `approval: ask`). PASS =
the approval card renders in the face; Deny is honored (the tool does not
run); a second attempt with Approve is honored; the session log records
approval/asked + approval/decided for both. Never drill with order tools;
ALPACA_KIT_ENABLE_ORDERS stays unset.
```

Before committing, verify the claim "dsh-base ships shell under approval: ask" against `@deepseek-ai/dsh-base/cordis.patch.yml` (grep `approval:` — lines near 199-205 at the pin) and adjust the drill's tool wording to whatever the base actually marks `ask`.

- [ ] **Step 2: Add the pointer to `dsh/README.md`**

At the end of the Gate-2 paragraph in step 6 (the one ending "do not rely on Gate 2 to hold if the flag is ever mis-set."), append:
```
   The face's approval surface and its drill live in `face/README.md` — once
   that drill passes on a live face, Gate 2 has a validated home there.
```

- [ ] **Step 3: Commit**

```bash
git add face/README.md dsh/README.md
git commit -m "docs(face): README - run, upgrade drill, Gate-2 drill; dsh README pointer"
```

---

### Task 10: Wire into the repo's docs + suites stay green

**Files:**
- Modify: `CLAUDE.md` (Map table + Commands)
- Test: full Python suite + face suite

- [ ] **Step 1: Add the CLAUDE.md rows**

In the Map table, after the `dsh/` row, add:
```markdown
| `face/` | the operator's chat face: a Node 22 process hosting dsh in-process (profile `face`) and serving chat-light at 127.0.0.1:3090; the Gate-2 approval surface. `face/README.md` has run + drill instructions |
```
In the Commands block, append:
```bash
cd face && npm start        # the chat face, http://127.0.0.1:3090 (see face/README.md)
```

- [ ] **Step 2: Both suites green**

Run: `python -m pytest` → expect 324 passed (untouched).
Run: `cd face && npm run typecheck && npm test` → PASS (smoke skipped without FACE_SMOKE).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md map + commands rows for face/"
```
