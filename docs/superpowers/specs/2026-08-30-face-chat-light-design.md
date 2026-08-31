# face/ — the chat-light face as an in-process dsh host (v1)

**Date:** 2026-08-30 · **Status:** approved design, spec for implementation
**Authority:** mechanism authority for `face/`. On intent, `Kairos-Design.md` outranks this
spec; on mechanism, this spec and code win. The design lineage (rounds 1–4, the wiring
decision) is `docs/design/prototypes/` + `docs/research/2026-08-30-dsh-wiring-recon.md`.

## 1. What this is

A single Node process that **hosts the DeepSeek Harness in-process** (wiring option B′,
operator-chosen) and serves the operator's own chat face — the round-4 `chat-light`
messenger — instead of the bundled dsh web UI. The face's composer is live: the operator
talks to Kairos through our page; approval prompts (Gate 2) render on our page.

Evidence base: the installed `@deepseek-ai/dsh` 0.1.1-rc.2 — every `@deepseek-ai/dsh-*`
sibling is a real npm package with typed exports; `boot()`, `createApiProxy`,
`toFetchHandler`, and the approvals/questions mux contract are public seams. The one
app-private piece is the CLI's ~60-line profile-composition chunk, which we re-implement.

## 2. Goals / non-goals

**v1 goals**

1. `face/` boots the operator's installed cordis profile (alpaca_kit MCP + skill packs, per
   `dsh/README.md`) inside our process — one harness per process.
2. Serves the chat-light UI at `http://127.0.0.1:3090/`; `/api/*` is the dsh typed contract
   via `toFetchHandler`; `events.mux`/`events.host` WebSocket upgrades work.
3. The face renders: session list (plain `session.list` — no strategies mapping yet),
   composer (`session.create`/`session.prompt`), live message flow from `events.mux`
   (user/message, assistant/message, tool/result → bubbles / inline cards, r4 grammar).
4. **Gate 2 becomes ours and testable**: `user-approval` + `user-questions` rows mounted;
   `approval/requested` and question frames render as approve/deny cards → `/api/respond`.
   v1 acceptance includes a drill (§7).
5. Exact-version pinning of the dsh family + a documented upgrade policy.

**v1 non-goals** (deliberate): market/account instrument pages · the strategies-as-
conversations sidebar mapping · exposing order tools (`ALPACA_KIT_ENABLE_ORDERS` posture
unchanged — flag lives only in the harness home, default off) · remote access (loopback
only) · reusing the bundled web frontend · multi-harness or multi-user anything.

## 3. Architecture

```
face/
  package.json          exact-pinned @deepseek-ai/* 0.1.1-rc.2 family; committed lockfile
  tsconfig.json         Node 22, ESM, strict
  src/
    boot.ts             profile composition (re-implemented chunk) → boot() → Context
    server.ts           webserver/connection/apiproxy/approval/question rows + static mount
    main.ts             entry: env → boot → serve; SIGINT teardown
  client/               vanilla JS ESM + CSS, no build step — the r4 kit gone live
    index.html  chat.css  chat.js  api.js  stream.js
  README.md             run/upgrade/drill instructions
```

**Server = TypeScript** (the lockstep d.ts make rc breaks fail at compile time — the cheapest
hedge against the pre-1.0 contract). **Client = vanilla JS ESM, no bundler** (the r4 kit
evolves; stays hackable).

### 3.1 Boot (src/boot.ts)

Re-implements the CLI chunk's composition (mirror of `profile-boot-*.js` lines ~127–281 at
0.1.1-rc.2 — cite this in a comment):

1. `loadLayeredEnv` → `healProfilesModuleFallback(installAnchor)` →
   `loadProfile("dsh", <profileName>, installAnchor)`. Profile name from `FACE_PROFILE`,
   default `web`. Honest note: the stock `web` profile boots but carries none of the
   workbench toolset — the real face requires the operator to have installed the repo's
   cordis profile per `dsh/README.md` (steps 2–4, still a pending operator item) and to
   point `FACE_PROFILE` at it. The face must boot EITHER cleanly; it never edits profiles.
2. Patch stack in the CLI's order: bundle patches from `dsh.profile.bundles` → the profile's
   `cordis.patch.yml` → `$DSH_HOME/cordis.patch.yml` → our face overlay (§3.2).
3. The root-`cordis.yml` rewrite guard (empty `[]` root) — **must not be skipped**; skipping
   corrupts subsequent boots (loader write-back duplication).
4. Re-implement the two chunk-only patches we'd otherwise lose: the shipped agent-presets
   root patch (`config/agent-presets/`) and telemetry-disable.
5. `boot("dsh", <profileDir>/cordis.yml, patches, prepare)` where `prepare` provides
   `DSH_LAUNCH_ENVIRONMENT_KEY` and `provideCmdline(hostCtx, {args, exit})`.

### 3.2 The face overlay (server.ts rows, applied as our patch layer)

- `dsh-host-webserver` — host `127.0.0.1`, port `3090` (`FACE_PORT` overrides; 3080 stays
  free for the stock `dsh web` as fallback/reference).
- `dsh-host-apiproxy` (`ApiProxyService`) — needs the dsh-base spine (the profile brings it);
  defaults: `cwd` = the workbench repo root, `defaultModelSelection()` per profile.
- `dsh-client-connection` — mounts `/api` prefix (Host-header fence, loopback trust) and the
  two WebSocket upgrade paths. We restate `host/port`/`trustedHosts` config ourselves since
  we bypass `dsh-web-app/startup` (recon risk d). Privileged methods stay loopback-pinned.
- `dsh-user-approval` + `dsh-user-questions` — REQUIRED: the apiproxy gateway registers its
  pending-table listener only if `ctx.get("approval")` exists; without these rows, `ask`
  policies fail closed to deny and Gate 2 never reaches the face.
- **Not mounted**: `dsh-host-frontend-static`, `dsh-client-modules`, client-ui rows. Our
  static routes claim `/` (index.html, chat.css, client JS) on `ctx.webServer`.

### 3.3 The client (client/)

- `api.js` — thin typed-enough wrapper: `POST /api/<method>` envelope
  (`{type:"client-request", rpcId, method, payload}`), plus the mux WebSocket with
  reconnect. No framework.
- `stream.js` — event mapping: `session/event` surface types → DOM via the r4 renderer
  grammar (operator bubble right / Kairos bubble left / tool result as flat inline card one
  notch quieter); `approval/requested` + question frames → approve/deny · answer cards
  posting `/api/respond`; backfill on open via `session.history`, then live mux frames
  (dedupe by seq).
- `chat.js`/`chat.css` — evolved from `docs/design/prototypes/r4/` (same visual tokens;
  light palette per the round-4 verdict). Honesty furniture carries over where it applies
  live: raw pointers on tool cards (producing tool name + callId), null → em-dash. SAMPLE
  tags drop (this is live data now); the composer is enabled.
- Sidebar: `session.list` rows (title, updated). New-session button → `session.create`.

### 3.4 Teardown

SIGINT/SIGTERM → dispose the Context once (the harness installs fail-loud handlers; ours
must not double-dispose). One boot per process lifetime; no hot profile reload in v1.

## 4. Version pinning & upgrade policy

- `package.json` pins the entire `@deepseek-ai/*` family to `0.1.1-rc.2` exactly (lockstep
  peerDeps; mixed versions break the rpc-map wire contract). Lockfile committed.
- README states the upgrade drill: bump the family together → `tsc` (contract breaks
  surface here) → re-verify `boot.ts` against the CLI's new profile-boot chunk (the one
  vendored re-implementation) → run the Gate-2 drill → then trust it.

## 5. Risks (carried, from the recon — restated honestly)

(a) the profile-composition chunk is app-private; our ~60-line mirror can drift on upgrade
(mitigation: §4 drill + the citation comment). (b) `$DSH_HOME` anchors profiles/settings/
storages — the face requires a properly installed harness home (`dsh/README.md` steps 2–4).
(c) process-singleton posture: one harness, one face, per process. (d) bypassing
`dsh-web-app/startup` means we own webserver/connection config restatement. (e) lockstep rc
coupling — §4. (f) `DSH_TOOLS_MODE`/`DSH_TELEMETRY_DISABLED` read at compose time — set in
`main.ts` before boot.

## 6. Testing

- **Compile = contract test**: strict `tsc` against the pinned d.ts.
- **Unit (offline, no keys)**: boot-composition module — patch-stack order, root-rewrite
  guard invoked, overlay rows present in the composed tree (assert on composition output,
  not a live boot). Client: `stream.js` event→DOM mapping tested against recorded
  `session/event` fixtures (a small checked-in JSONL of the three surface types + one
  approval frame + one question frame).
- **Boot smoke (local, no LLM call)**: boots the real profile, asserts `/` serves our HTML,
  `POST /api/session.list` answers `ok`, GET on `events.mux` returns 426, foreign Host
  returns 403, then clean teardown. Marked/skipped when `$DSH_HOME` or the profile is absent
  (CI-safe); run locally by the operator.
- **The Python suite is untouched** (324 tests stay green; `face/` adds `npm test`).

## 7. The Gate-2 drill (charter: a guard never pulled is presumed broken)

v1 acceptance, run by the operator with the face live: trigger a tool call whose approval
policy is `ask` using a HARMLESS tool (never the order tools; ORDERS stays unarmed) — e.g. a
session whose prompt asks Kairos to run a shell command under an `ask` pre-execute rule in
the operator's installed profile. PASS = the approval card renders on the face, Deny is
honored (tool does not run), Approve is honored, and both decisions appear in the session
log as `approval/asked`/`approval/decided`. The README documents the exact drill steps.
Until this drill passes, the face must not claim Gate 2; `dsh/README.md`'s honest Gate-2
note stays as-is and gains a pointer here once the drill is green.

## 8. Charter check

`Kairos-Design.md` P1/P2/P5 unaffected (wide hands, operator-only teaching, human steady
state). dsh remains the STRATEGY runtime — now vendored into our process rather than beside
it; the write map gains one row: `face/` is normal workspace code. The face is no longer
"presentation only" (it hosts the loop) — recorded here as the successor posture, replacing
the v1-era faces principle for this surface. Revisit trigger: if dsh ships a stable (≥1.0)
contract or an official custom-frontend API, re-evaluate the vendored composition.
