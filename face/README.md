# kairos-face — the chat-light face as an in-process dsh host

One Node 22 process. It boots the DeepSeek Harness from the `face` profile
(bundles: `@deepseek-ai/dsh-base` only), inserts its own host rows on top, and
serves the operator's chat UI at http://127.0.0.1:3090/. No build step — `tsx`
runs the TypeScript directly. Spec:
`../docs/superpowers/specs/2026-08-30-face-chat-light-design.md`.

## Run

```bash
cd face
npm install
npm run setup            # creates $DSH_HOME/profiles/face (never overwrites)
source ../.env.deepseek  # DEEPSEEK_API_KEY - see below
npm start                # http://127.0.0.1:3090/  (profile: face)
```

Without the key the face still boots and serves: sessions list, the UI works,
and the first prompt fails with a missing-credential error from the LLM route.
`../.env.deepseek` is gitignored and not loaded automatically. Equivalently, put
`DEEPSEEK_API_KEY` in `$DSH_HOME/.env` — `bootFace` runs dsh's layered env load
before composing, so the harness home's `.env` reaches the tree too.

| Env | Default | What |
|---|---|---|
| `FACE_PORT` | `3090` | webserver port. `0` asks the OS for a free one |
| `FACE_PROFILE` | `face` | profile directory name — honored by BOTH `npm run setup` and `npm start` |
| `DSH_HOME` | `~/.dsh` | the harness home: profiles, sessions, storages, credentials |
| `DEEPSEEK_API_KEY` | — | resolved per request through the credential seam, then the environment |
| `DSH_TELEMETRY_DISABLED` | unset | ANY non-empty value (`0` and `false` included) disables the telemetry row |
| `DSH_PERMISSION_MODE` | `workspace-write` | sandbox mode. `danger-full-access` also sets the approval policy to `never` — it DISARMS the Gate-2 surface below |

`FACE_PORT` and `FACE_PROFILE` read an empty value as unset, not as a literal:
`FACE_PROFILE=""` would otherwise resolve to `$DSH_HOME/profiles` itself, and
`FACE_PORT=""` is `Number("") === 0` — a face whose URL silently moves on every
restart. `"0"` is a non-empty string, so deliberately asking for an OS-assigned
port still works.

Ctrl-C (SIGINT) leaves 130, SIGTERM leaves 0; both dispose the tree first.

## The profile

`npm run setup` writes THREE files into `$DSH_HOME/profiles/<name>/`, and
refuses a directory that already exists — it prints `exists, untouched: <dir>`
and changes nothing. Profiles are operator territory.

| File | What |
|---|---|
| `package.json` | the profile manifest: `dsh.profile.bundles: ["@deepseek-ai/dsh-base"]` |
| `cordis.patch.yml` | the operator's patch layer — a header plus a load-bearing `[]` (an empty array, not an empty file: dsh-app-boot throws on anything that is not a top-level YAML array) |
| `pnpm-workspace.yaml` | pnpm settings, verbatim from dsh's own `initProfile`, so `dsh plugin add` can install into this profile later |

Mount the workbench toolset — the `alpaca_kit` MCP server and the two skill
roots — into `cordis.patch.yml` per `../dsh/README.md` steps 3-6. The face boots
with or without it.

Two things about that directory are NOT yours:

- **`<profile>/cordis.yml` is face-managed.** `composeFace` rewrites it on every
  boot. The whole tree is composed as patch layers, and the root exists only as
  an empty entry list anchoring the loader's `baseUrl`; anything you put there
  is gone at the next start. Edit `cordis.patch.yml`.
- **The face's own host rows compose LAST and win silently.** They are applied
  after your patch layer and after the machine-local `$DSH_HOME/cordis.patch.yml`
  — the inverse of the dsh CLI's layering, and deliberate: loopback-only binding
  surviving an operator patch is the point. A patch of yours aimed at
  `webserver`, `connection`, `api-gateway`, `directory-picker`,
  `cordis-host-runner`, the storage chain (`storage`, `storage-json`,
  `storage-domain`, `workspace`), or the `hmr` / `session-telemetry-otel`
  switches is accepted, overridden, and NEVER reported. Change those in
  `src/overlay.ts`. The same warning is in the patch file's own header, which is
  where an operator would actually look.

## Tests

```bash
npm test                  # offline unit tests - no keys, no network, no port
npm run typecheck         # strict tsc against the pinned .d.ts - the contract test
FACE_SMOKE=1 npm test     # + the one real boot (throwaway $DSH_HOME, no LLM call)
```

`npm test` works on seams: the composed patch stack, a recorder standing in for
the webserver, a recorded event stream, the version pins. The smoke test is the
only place a composition that typechecks but does not MOUNT gets caught — it
boots the real plugin tree into a `mkdtemp` home, then drills the surface: `/`
serves the client, `/client/chat.css` is served with the right content type,
`POST /api/session.list` returns a real `items` array (proof the api gateway
reached the session store behind it), a plain `GET /api/events.mux` answers 426
with an `upgrade: websocket` hint, and the same request with a forged
`Host: evil.example.com` answers 403 — the DNS-rebinding fence, drilled rather
than assumed.

## Upgrading dsh — TWO pins, not one

`src/version.ts` holds both, and they move independently:

- **`DSH_PIN` = `0.1.1-rc.2`** — the entire `@deepseek-ai/dsh-*` family, pinned
  EXACT. Lockstep only: these packages are tested only against each other at one
  version, and a mixed set breaks the rpc-map wire contract. `tests/version.test.ts`
  sweeps every `@deepseek-ai/dsh-*` entry across `dependencies` and
  `devDependencies` PROGRAMMATICALLY and asserts declared range == installed
  version == `DSH_PIN`, so a dependency added later is covered without anyone
  remembering to extend a list.
- **`CORDIS_PIN` = `4.0.2`** — `@deepseek-ai/cordis` rides its own 4.x track. The
  dsh packages peer-depend on it at `^4.0.1`, and the cordis-plugin family
  currently peers `^4.0.2`. It is bumped separately and deliberately.

Not pinned at all: the five `@deepseek-ai/cordis-plugin-*` packages (`group`,
`hmr`, `include`, `loader`, `timer`). They arrive transitively on caret ranges
declared by `dsh-app-boot` and `dsh-base`; only `package-lock.json` holds them
still. Keep the lockfile committed, and read a lockfile-only change to those
five as a real upgrade that deserves the drill below.

**The drill.** Bump `package.json` AND the matching constant in `src/version.ts`
together — both pins if both tracks moved — then:

1. `npm install` — first, and not optional: the pin sweep reads the INSTALLED
   tree as well as the manifest, so running it against a stale `node_modules`
   fails on the old versions rather than on anything about the upgrade.
2. `npm test` — the pin sweep fails first when the manifest, the installed tree,
   and either constant disagree. A green sweep is the precondition for the rest,
   not evidence the upgrade is good.
3. `npm run typecheck` — the contract test. A renamed config key, a narrowed
   value, a changed exported signature: they surface here, because the overlay's
   row configs are `satisfies`-checked against the plugins' OWN exported config
   types rather than against a local `Record<string, unknown>`.
4. **Re-diff `src/boot.ts` against the CLI's current `profile-boot-*.js` chunk.**
   At this pin that is `@deepseek-ai/dsh` 0.1.1-rc.2,
   `lib/profile-boot-DG5t9aNs.js` — functions `prepareProfile`, `composeProfile`,
   `resolveTelemetryPatch`, `runProfile`. The chunk name is content-hashed and
   changes on every release; the CLI is not a dependency of this package, so
   fetch it (`npm pack @deepseek-ai/dsh@<new>`) to read it. This is the one
   private piece the face mirrors: it is unexported, so nothing type-checks it,
   and a composition that has drifted boots a DIFFERENT tree while still
   compiling clean. `boot.ts`'s header lists the divergences that are deliberate
   (no `--patch` overlays, no HMR reload, no `installFailLoud`, no shipped
   agent-presets graft, the face's own install anchor) — anything else is drift.
5. **Re-check the frame shapes**: `client/mapper.js` and
   `tests/fixtures/events.jsonl` against the pinned
   `@deepseek-ai/dsh-host-apiproxy/lib/types/api/*.d.ts` — `events.d.ts`
   (`MuxFrame`), `rpc.d.ts` (`ServerRequest`), `rpc-map.d.ts` (the closed method
   list), `approvals.d.ts` and `questions.d.ts` (the two answerable frames).
   The client is untyped JavaScript talking to a typed wire, so `tsc`
   does not cover this hop — the fixture is the contract, and a fixture that no
   longer matches the wire makes the mapper tests green against a stream nobody
   sends.
6. `FACE_SMOKE=1 npm test` — the only step that proves the new tree MOUNTS.
7. Run the Gate-2 drill below.

Only then trust it.

## The Gate-2 drill (run after any face or dsh change)

A guard never pulled is presumed broken.

**What actually holds Gate 2 here.** dsh-base marks no tool `ask` per-tool.
It mounts `@deepseek-ai/dsh-user-approval` with a session-wide policy — `ask`
unless `DSH_PERMISSION_MODE=danger-full-access` — and
`@deepseek-ai/dsh-permission-presets`, whose `read-only` and `workspace-write`
presets both carry `approval: ask` while `danger-full-access` carries
`approval: never`. The default session is `workspace-write` + `ask`. What
actually RAISES a card is a **sandbox escalation**: under `workspace-write` the
sandboxed bash executor and the sandboxed fs write/edit tools are denied outside
the session workspace, and their one permitted retry carrying
`sandbox_permissions` + `justification` resolves `ctx.approval` before running.
An `ask` decision with no answerer degrades to DENY, and `bootFace` refuses to
start a tree missing the `approval` or `userQuestions` service for exactly that
reason — otherwise the tree would come up healthy and every approval would fail
closed with nothing on screen saying why.

**The drill**, with the face live and a session open:

1. Prompt Kairos to write a file OUTSIDE the session's workspace — the path
   shown on the session's sidebar row — and to escalate when the sandbox denies
   it. `touch ~/face-gate2-drill` from the bash tool does it, unless the session
   workspace IS your home directory, in which case pick any path outside it. Do
   NOT use `/tmp`: `workspace-write` already permits the platform temp areas, so
   a write there is allowed and asks nobody.
2. PASS, part one: the approval card renders in the face — headed `approval`,
   the tool's name beside it, the host's reason when it gave one, and exactly
   two buttons. Two outcomes and only two: `cancelled` and `unavailable` are
   host-side and no client may send them.
3. **Deny.** The card settles to `answered · deny` and the command does NOT run.
   The model sees a denial result, never the card.
4. Prompt again and **Approve**. The command runs. The grant is one-shot
   (`allowed-once`) and applies to that call alone — there is no `allow-always`,
   no remembered rule, no grant store.
5. Both decisions are in the session log under `$DSH_HOME/sessions` as paired
   `approval/asked` + `approval/decided` records. Those are log-only: the audit
   is for you, not for the model.
6. Clean up: `rm ~/face-gate2-drill` (or whatever path step 1 used).

The escalation retry is capped at ONE per turn: after a denial the model may
retry that same command once, in that same turn, with a wider mode and a
justification — and that retry is what raises the card. If it answers with prose
instead of retrying, that turn is spent; prompt again, more bluntly, rather than
concluding the seam is broken.

**Never drill with the order tools.** `ALPACA_KIT_ENABLE_ORDERS` stays unset.
Gate 1 — registration — is what keeps `place_order` / `cancel_order` out of the
toolset entirely, and a drill that arms the flag to exercise Gate 2 has disarmed
Gate 1 to do it. Any harmless denied-then-escalated file write proves the same
seam.

Until this drill passes on a live face, the face does not claim Gate 2.
