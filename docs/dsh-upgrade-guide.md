# dsh upgrade guide

**What this is.** The operator's entry point for the next DeepSeek Harness (dsh) upgrade, and
the record of every upgrade so far, so that a pin bump is a checklist and not a redesign.
Written 2026-10-15 at the 0.2.0-rc.2 pin · **Owner:** the operator · **Rule:** this file
restates no mechanism. Every row points at code and at the section of `DEVELOPMENT.md` or the
README that carries the depth; when this file and the code disagree, the code is the fact and
this file is corrected. The complete seam inventory with the verbatim upstream citations it was
compiled from is frozen at `docs/research/2026-10-15-dsh-seams-inventory.md` (159 rows); the
row ids below (`A1`, `E12`…) are its.

**How to use it.** Before an upgrade: §1 (where we stand), §2 (the procedure), §3 (what to
re-check by hand and what a test will tell you), §4 (decisions to re-take), §5 (drills). After
it: append a record to §6, retire the §7 watch items that landed, update §1's pins. Each change
that adds a dependency on dsh adds its row to §3 in the same commit.

---

## 1. Where we stand (2026-10-15)

| Component | Version | Pinned where | Checked by |
|---|---|---|---|
| the dsh family, 29 `@deepseek-ai/dsh-*` packages, every one exact | **0.2.0-rc.2** | `face/package.json`; `face/src/version.ts` `DSH_PIN` | `face/tests/version.test.ts` sweeps manifest, installed tree and constant |
| `@deepseek-ai/cordis` (every dsh package peers it `~4.0.4`) | 4.0.4 | `package.json`; `CORDIS_PIN` | `version.test.ts` |
| `@deepseek-ai/cordis-plugin-include` (imported directly for `entryListSchema`) | 1.0.9 | `package.json`; `CORDIS_INCLUDE_PIN` | `version.test.ts` |
| `cordis-plugin-loader` / `-group` / `-timer` | 1.0.5 / 1.0.4 / 1.1.6 | **lockfile only** | nothing: a lockfile-only move of these is an upgrade and gets the whole §2 |
| packages read by path but **not declared**: `dsh-api-gateway`, `dsh-user-approval`, `dsh-user-questions` | via dsh-base's exact deps | — | only `npm run check:fixture` fails loudly; the sweep is blind to them (A6; §7.4) |
| the CLI's boot chunk `boot.ts` mirrors | `lib/profile-boot-BZ2ZjNWi.js` (content-hashed, changes every release) | cited in `boot.ts` header, README "Upgrading dsh" step 4, `DEVELOPMENT.md` §4.1 and §6.7 | manual re-diff (A9) |
| the global CLI `~/.local/bin/dsh` | 0.2.0-rc.2, installed 2026-10-01, **never run** (its first run would import `~/.dsh/settings.yaml` into its own profile) | — | D12 |
| the operator's home `~/.dsh` | live on 0.2.0 since 2026-10-01; session format **v4**; profile `face`; the `agent-default-model` row present (D2); the link farm deleted (D13) | backup `~/.dsh.bak-pre-0.2.0-20261001`; exports `~/dsh-session-exports-2026-10-01/` | the runbook §7 C checks, run 2026-10-01 |
| upstream | repo `deepseek-ai/deepseek-harness`, tag `dsh-v0.2.0-rc.2`; npm dist-tags `latest` = `next` = 0.2.0-rc.2 (checked 2026-10-14); alpha line 0.2.1-alpha.1/.2/.3 (2026-10-03/09/14) | — | §7.1 |

Three homes on disk and what each is for: `DEVELOPMENT.md` §1. The profile's two operator rows
(the alpaca-kit MCP server, the skill roots) and the D2 model row: `dsh/README.md` "Installed
state".

## 2. The procedure

Merged from `face/README.md` "Upgrading dsh — three pins, not one", `DEVELOPMENT.md` §6.7 and
§10 items 13–14, `dsh/README.md` step 2, and the go-live runbook
(`docs/superpowers/runbooks/2026-09-30-dsh-0.2.0-rc.2-go-live.md`). The numbering is the
inventory's PART 2, so a step can be cited.

**Read first**

1. Read the release before touching the tree: the new dist-tag version, the cordis peer range,
   the include peer, any new `dsh-session-format-vN-to-vN+1` package, dsh-base row renames or
   removals (`cordis.patch.yml`), the CLI's `profile-boot` rewrite. Trap: `gh release view`
   takes the TAG (`dsh-v0.2.1-alpha.3`); the release name alone answers "not found".

**Freeze the home**

2. Stop everything on the harness home (`lsof`, `pgrep`), back it up
   (`cp -a ~/.dsh ~/.dsh.bak-pre-<ver>-<date>`, `diff -rq -x node_modules`, `.credentials.yaml`
   stays `0600`). The backup is stale the moment an older tool runs on the home again.

**Bump and prove offline** (`face/`)

3. Bump the pins together: `package.json` (every `dsh-*`, cordis, include, all exact) **and**
   `src/version.ts` (`DSH_PIN`, `CORDIS_PIN`, `CORDIS_INCLUDE_PIN`).
4. `npm install` first; the sweep reads the installed tree. Keep the lockfile committed.
5. `npm test`: `version.test.ts` fails first on any disagreement; `policy.test.ts` re-pins every
   policy target against the new dsh-base; `boot.test.ts` and `overlay.test.ts` re-pin the layer
   order and the thirteen overlay rows. Green is the precondition, not the evidence.
6. `npm run typecheck`: `skipLibCheck: false`, the overlay's `satisfies` checks against the
   plugins' own `Config` types, every named import (A11, A13).
7. Re-diff `src/boot.ts` against the CLI's current `profile-boot-*.js` chunk (`npm pack
   @deepseek-ai/dsh@<new>`, or the installed global CLI's `lib/`). The ten header divergences
   are deliberate; anything else is drift. Same pass: the `prepare` provides, `createAppReady`,
   the required-id set and the warn-only audit, `resolveTelemetryPatch`, the `hmr` and
   `settings` gating on `profileContext` (A9, B8, B10–B12).
8. Re-check the frame shapes: `client/api.js`, `client/mapper.js`, `tests/fixtures/events.jsonl`
   against the installed `.d.ts` of `dsh-api-gateway` (stream-protocol), `dsh-api-remotes`,
   `dsh-api-session-controller`, `dsh-session`, `dsh-llm`, `dsh-user-approval`,
   `dsh-user-questions`. The fixture is corrected by hand; there is no generator (E1–E9).
9. `npm run check:fixture`: the fixture through the installed dsh's own validators; a moved
   private path fails at load (E9).

**Prove on real boots**

10. `FACE_SMOKE=1 npm test`: the thirteen real boots. A dropped `snapshotEvents()` fails Gate 2
    and the room engine closed and loudly here (D7).

**Prove on a copy of the home** (never the live one)

11. Dry-run a COPY: `cp -a ~/.dsh $SCRATCH/dsh-dryrun`, `touch …/DRY-RUN-COPY`, `npx tsx
    scripts/check-home.ts $SCRATCH/dsh-dryrun` with `DSH_HOME` unset. Stop on exit 1, an
    `OTHER` refusal, any change under `sessions/`, or an MCP row still ENABLED. Delete the copy
    (it holds `.credentials.yaml`); re-run on a fresh copy after any profile edit (G11, I1).

**Decide**

12. Decide the operator decisions the new pin raises (§4), each a row in
    `~/.dsh/profiles/face/cordis.patch.yml` or a code change; refresh `PATCH_HEADER`'s prose
    in the installed patch file if the overlay's row set moved (B33).

**Rehearse on copies**

13. Rehearse the runbook §7 A checklist on a SECOND copy with the operator's MCP rows mounted
    (`DSH_HOME=$SCRATCH/dsh-drill FACE_PORT=3091 npm start`), then delete it.
14. Run the README drills in a FRESH scratch home (`npm run setup`, `npm start` on 3092): Gate 2
    / approval channel, order approval with Gate 1 armed in the scratch home only, ask-user,
    bots, room (§5).

**Go live**

15. Everything on `~/.dsh` stopped again; the backup re-taken or diffed; D12 settled; `cd face
    && npm start`; open the printed `?token=` URL; check the boot log's presets line and no
    warning; `grep -c 'client-connection/browser-session' ~/.dsh/.credentials.yaml` = 1;
    `ls ~/.dsh/storages/session_projcache/sessions | wc -l` non-zero; a cold session opens with
    no `session.v4.jsonl.zstd` written; the agent panel shows the D2 model;
    `/data/plugins.json` lists both MCP servers. Keep the backup until the live face is trusted.
16. Rollback = `mv ~/.dsh ~/.dsh.failed-<ver> && cp -a <backup> ~/.dsh`, then the OLD face only
    from an old checkout with its own `node_modules`. Never delete one session's v4 file and
    lock as a "rollback".

**Document**

17. Update what cites the pin (none moves by itself): `version.ts` comments, the chunk name in
    `boot.ts` and in the three documents, `DEVELOPMENT.md` §4 header / §4.1 / §6.7 / §7.1 counts
    / Appendix A, `face/README.md` "Upgrading dsh" and "Tests", `dsh/README.md` "Installed
    state", `CLAUDE.md`, `ROADMAP.md`'s built log, the runbook's expected-findings table, and
    §1 and §6 of this file.

## 3. What to re-check

### 3.1 By hand: the seams no test pins

These are the upgrade's real work. Everything else in §3.2 fails a test first.

| # | Re-check | Where | What moves it |
|---|---|---|---|
| A4 | the three transitive cordis plugins in the lockfile | `face/package-lock.json` | the Loader's row keying (last id wins), `group: true` nesting, `!!js` evaluation |
| A9 | `boot.ts` against the CLI's `profile-boot-*.js` (step 7) | `face/src/boot.ts` header | any new `provide`, required service or readiness rule boots a different tree with tsc green |
| B9, I7 | no proxy policy installed (D10); children still inherit `HTTP(S)_PROXY` | `boot.ts` divergence 3 | an upstream adapter that honours the variables on its own |
| B14 | `installFailLoud`, `StartupError`, the exit mapping | `face/src/main.ts` | a changed rejection or exit contract hangs or double-reports a startup failure |
| B15 | `process.chdir(<repo root>)`: SessionController's default dir and dsh-base's `sandbox-policy.workspaceRoot` both read `process.cwd()` | `main.ts`; installed `dsh-base/cordis.patch.yml` `sandbox-policy` | a config key for either, or a sandbox root off cwd (channel fencing changes) |
| B33 | `PATCH_HEADER` names every face-owned row and switch | `face/src/setup.ts` | the overlay's row set |
| D9 | `tools/execute` runs after the guard and re-resolves the tool by name (a gate, not containment) | `face/src/orders.ts` header | the recorded residual R2 changes if dispatch internals move |
| E12 | the face's own message sources survive the next format edge: `{kind:'room', …}` and the `@`'s `{kind:'user', mention:[…]}` | `face/src/room.ts` `say` | a v4→v5 edge enforcing key sets on known kinds refuses every room log with an `@` (§7.2) |
| G2 | stdio negotiation spawns a probe process before the serving one | behaviour | boot time and the mid-boot window |
| G3, H9 | a server's `instructions` become the unswitchable section `mcp:<server>`, seen by bots too; instructions over `maxInstructionBytes` fail the connection | behaviour; `face/src/akshare.ts` | a server whose instructions grow past the cap silently loses its tools |
| G7 | the MCP child's env is scrubbed (`KEY\|PASSWORD\|SECRET\|TOKEN`, `DSH_*`); the APCA keys ride the operator's row explicitly | `~/.dsh/profiles/face/cordis.patch.yml`; `dsh/README.md` step 5 | the account tools stop registering (7 tools, not 10), or keys leak into shell turns |
| G8 | `toolCallTimeoutMs: 300000` on the alpaca-kit row (a cold `screen` runs ~188 s; the 60 s default kills it) | the operator's row | a renamed key restores the default silently |
| G10 | the MCP server is a child of the face process; its writes bypass the sandbox | behaviour | residual R5 if dsh starts sandboxing MCP children |
| G12 | FastMCP (`mcp` 1.x) negotiates with dsh's `@modelcontextprotocol/client` 2.0 | `alpaca_kit/mcp/server.py`; the akshare-mcp install | both servers silently register zero tools (G4) |
| H2 | `SKILL.md` frontmatter `name` + `description`, or discovery drops the skill at warn level | `dsh/skills/*/*/SKILL.md` | a new required key empties the catalog with no error |
| H6 | the `agent-instructions` row's user-global file: hard-coded `$DSH_HOME/AGENTS.md`, outside the candidate lists the face restates | installed `dsh-agent-instructions/lib/index.js` (`USER_GLOBAL_FILE`); the candidates and the budget are the face's own patch, `face/src/instructions.ts` (H10) | 0.2.1 removes the per-row `dshHome` and reads the global file via `DSH_AGENTS_HOME` |
| I5 | credential precedence: `.credentials.yaml` refs outrank both `.env` layers, the inherited environment wins | `boot.ts` `loadLayeredEnv`; the operator's shell | 0.2.1 changes API-key precedence for headless runs |
| I12 | state outside `~/.dsh` and the repo is `tmpdir()` scratch only | `agents.ts`, `alpaca_kit/mcp/cache.py` | a new state directory the backup misses |
| — | the MCP live roster: `/data/plugins.json` = `alpaca-kit active 10`, `akshare active 14` | runbook §7 A | the only visible sign of G4 |

### 3.2 By test: the pinned seams and what fails first

Each row: the seam, the file that pins it. Depth: the inventory's row, `DEVELOPMENT.md` §4.1
(boot), §4.3 (overlay and policy), §4.7 (Gate 2), §5.2 (the wire), §6.8 (rooms), §3.7 (bots).

**A · pins and install.** A1–A3 the three constants vs manifest vs installed tree
(`version.test.ts`); A5 the retired packages never declared (`version.test.ts`); A6 the
fixture validator's private paths (`check:fixture`); A7–A8 the install anchor, `PluginPackages`
and its native addon (every `FACE_SMOKE` boot); A10 the profile manifest and patch-file shapes
`setup` writes (`setup.test.ts`); A11 the `satisfies` contract (tsc); A12 the structural `*Like`
types hide drift from tsc, so the thirteen real boots are the contract; A14 `FiberState.ACTIVE`
as the literal `2` (`smoke.test.ts`, `panels.test.ts`); A15 Node 22's `zstdDecompress`
(`sessions.test.ts`).

**B · boot and composition.** B1 the layer order ending with the face overlay (`boot.test.ts`);
B2 `<profile>/cordis.yml` rewritten to `[]` every boot (`boot.test.ts`); B3 a skipped bundle
refused (`boot.test.ts`); B4 the telemetry switch (`boot.test.ts`, `policy.test.ts`); B5 `hmr`
disabled (`boot.test.ts`); B6 the persona patch restating every inherited `system-prompt` key
(`boot.test.ts`, `bot-plugin.test.ts`); B7 the strict `{{model}}`/`{{cwd}}` template
(`persona.test.ts`); B8 no `profileContext` (`bot-runtime-smoke`, `subagents-smoke`); B10 what
`prepare` provides (every boot); B11 `appReady` last, unary `/api` live mid-boot
(`smoke.test.ts`, `order-gate-midboot-smoke`); B12 every enabled entry ACTIVE
(`smoke.test.ts`); B13 the four required service keys (`smoke.test.ts`); B16 `bootFace`
materializes `$DSH_HOME` once per process (`boot.test.ts`); B17 exactly thirteen overlay rows in
order, the thirteenth `preset-kairos`, the alias of the default (`overlay.test.ts`); B18 the four
storage rows composed once, from dsh-base (`boot.test.ts`);
B19–B23 each overlay row's config and inject (tsc, `overlay.test.ts`, every
boot); B24–B30 the policy rows D3–D7 and D9, each pinned against the installed dsh-base
(`policy.test.ts`, `smoke.test.ts`); B31 the policy guard reports a missing target on stderr
(`policy.test.ts`); B32 the `extraPatches` seam the dry run uses (`check-home.test.ts`); B34
every dsh-base row the face addresses by id (`boot.test.ts`, `policy.test.ts`).

**C · agent plane.** C1 the registry row and its `Pick<Config, "default">` (tsc,
`overlay.test.ts`); C2 `defaultId` = the default preset (every boot refuses otherwise); C3 the
static default-preset row present before the first `session/create` (`boot.test.ts`,
`bots-smoke`); C4 `definitionFor`'s rebasing onto the bot directory (`bot-presets.test.ts`,
`bots-smoke`); C5 declarations after boot, eager activation, dispose-then-declare
(`bot-presets.test.ts`, `bot-runtime-smoke`); C6 the scoped `deployment:persona-prefix`
section shadowing the global prefix (`bot-plugin.test.ts`, `bots-smoke`); C7 `tools.restrict`,
the unmasked `schemas()` view, re-expansion on `tools/change` (`bot-plugin.test.ts`,
`bots-smoke`); C8 `mcp__*__<raw>` expansion (`bot-plugin.test.ts`); C9 `DEFAULT_ALLOW`'s names
(`bots-smoke`); C10 `renderComposition`'s two rows (`bots.test.ts`, `bot-presets.test.ts`); C11
the bot-id grammar (`botId.test.ts`); C12 `stateOf(session, "agentPreset")`
(`bot-runtime-smoke`, `room-engine.test.ts`); C13 `agent/created`, `system-prompt/assemble`,
`agent/request`, `requestHeader()` (`bot-runtime-smoke`); C14 the journal as a runtime-context
snapshot (`bot-runtime-smoke`); C15 `agentPresets/read` and `/select` exist and are not called
(`bot-runtime-smoke`); C16 `SessionHeader` fields (`bots-smoke`, `room-smoke`,
`channels.test.ts`); C17 the subagent plane the client composes: relays, catalog, interrupt
(`subagents-smoke`, `subagents.test.ts`, `mapper.test.ts`); C18 the default model route and
`installModelSelection` (`room-engine`, `room-smoke`, `bot-runtime-smoke`); C19 `tool-ask-user`
configless = the blocking `legacy` mode (`smoke.test.ts`).

**D · gates and approvals.** D1 the prepended `tools/pre-execute` ask (`order-gate.test.ts`,
`orders.test.ts`); D2 the monotonic `tools.guard` reading the live description
(`order-gate.test.ts`, `order-gate-smoke`); D3 both halves armed inside `prepare` as inject
fibers (`order-gate-midboot-smoke`); D4 the effective approval policy reproduced from public
halves (`orders.test.ts`, `order-gate.test.ts`); D5 `never` denies in the gate's own words
(`orders.test.ts`); D6 the grant is the paired `approval/asked` + `approval/decided
allowed-once` in the log (`orders.test.ts`, `order-gate-smoke`, `smoke.test.ts`); D7
`snapshotEvents()` deprecated, the grant index its named successor (`orders.test.ts`,
`order-gate.test.ts`, `room-engine.test.ts`); D8 the `(operator-gated)` marker and the raw-name
suffix under dsh's `mcp__<server>__<raw>` minting (`orders.test.ts`, pytest); D10 an approval
needs an open turn (the four smokes); D11 `api-remotes` the sole `$events` source
(`smoke.test.ts`, `askuser-noclient-smoke`); D12 pending-gate replay, winner-never-cancelled,
late answers (`api.test.ts`, `client-mux-smoke`); D13 the client's answer vocabulary
(`api.test.ts`); D14 questions answered with the whole batch, agentless asks `NO_PROVIDER`
(`askuser-noclient-smoke`, `client-mux-smoke`); D15 `ask_user_question` in the live registry
(`smoke.test.ts`); D16 sandbox escalations as the other card producer, refusals inside tool
content (`bot-sandbox-smoke`, `mapper.test.ts`); D17 the `read-only` pin inside `setup` before
`session/created` (`room-smoke`, `room-engine`); D18 approval events in the catalog, questions
as plain tool pairs (`room-engine.test.ts`).

**E · sessions and the wire.** E1 the unary envelope and its refusals (`api.test.ts`,
`smoke.test.ts`); E2 every Remote method the page calls and its argument shape
(`client-mux-smoke`, `subagents-smoke`); E3 the `/api/remote.mux` frames (`api.test.ts`,
`client-mux-smoke`); E4 the `$events` stream, `ready` first (`api.test.ts`,
`client-mux-smoke`); E5 `session/control` projections (`client-mux-smoke`, `mapper.test.ts`);
E6 `session/follow` snapshot then gap-free events; a follow activates a cold session
(`client-mux-smoke`); E7 the two non-activating reads (`client-mux-smoke`, `subagents-smoke`,
`member-traces.test.ts`); E8 the v4 event shapes the mapper renders (`mapper.test.ts` on
`tests/fixtures/events.jsonl`, `check:fixture`); E9 the fixture validator (`check:fixture`);
E10 the on-disk format grammar, generations, lease, zstd frames (`sessions.test.ts`,
`check-home.test.ts`); E11 the migration edges and their refusal names (`room-engine`,
`check-home.test.ts`); E13 `sessionPersistence.list()` returns snapshots (`channels.test.ts`,
`room-engine`); E14 `agentPreset` rides the projection block (`summaries.test.ts`,
`channels.test.ts`, `room-smoke`); E15 the per-record projection cache (`room-smoke`); E16 the
projection-unit registration shape (`room-projection.test.ts`); E17 the browser-session cookie
on `/` and the Host/Origin fence (`smoke.test.ts`, `static.test.ts`); E18 the credentials store
record (`smoke.test.ts`, runbook §7 C); E19 the `/data` trust fence (`data.test.ts`); E20 the
webserver route contract (`static.test.ts`, `smoke.test.ts`); E21 reconnect re-opens every
stream (`api.test.ts`); E22 client-minted `requestId` (`api.test.ts`); E23 no session DELETE
Remote, the host archive 409 (`sessions.test.ts`); E24 the workspace registry service
(`channels.test.ts`, `room-smoke`); E25 `/data/host.json` (`panels.test.ts`); E26 the plugin
panel from `loader.entries()` (`panels.test.ts`).

**F · rooms.** F1 member create/resume with `setup(agentCtx, agent)` before announcement
(`room-engine`, `room-smoke`); F2 the host's `composeAgent` restated: model selection, preset
join, read-only pin (`room-smoke`); F3 cold rooms resumed through `sessionController.resolveAgent`
(`room-engine`, `room-smoke`); F4 the root `session/event` bus, `followup`, `cancel` with
`keepInbox`, `append` with `surfaceOp` (`room-engine`, `room-smoke`); F5 `createUserMessage`
(`room-smoke`); F6 the tool-definition shape for `dispatch` and `agent_<bin>` (`room-engine`,
`agents.test.ts`, `panels.test.ts`); F7 `dispatch` refused for a session that runs a bot
(`room-engine`); F8 member discovery from persisted snapshots, resume-not-recreate
(`room-engine`); F9 room facts on known event types only (`room-projection.test.ts`,
`room-smoke`); F10 a member's pending gate read off its log (`room-engine`); F11 the channel's
instruction chain reaches a member (`room-smoke`; landed in plan 1 as the `GRAVIT.md` chain,
`dbbd19a` and the patch `8983555`); F12
members attached to the channel workspace (`room-smoke`); F13 the legacy-format wording matched
by error name (`room-engine`); F14 the caps sentence generated from `ROOM_CAPS`
(`room-rules.test.ts`).

**G · MCP.** G1 the stdio row config keys (tsc, `boot.test.ts`, `check-home.test.ts`); G4
`failOnStartupError: false` leaves a dead server's row ACTIVE with no tools
(`order-gate-midboot-smoke`; runbook §7 checks); G5 `mcp__<server>__<raw>` minting and hashing
(`orders.test.ts`, `bot-plugin.test.ts`); G6 mcp-client hard-injects only `tools`, which makes
D7 safe (`policy.test.ts`, `smoke.test.ts`); G9 Gate 1 in the MCP child's env only, the marker
on both order tools (pytest, `order-gate.test.ts`); G11 the dry run disables MCP rows by package
and id (`check-home.test.ts`).

**H · skills and instructions.** H1 the operator's `skill-filesystem` patch and the bots' own
`skills` row (`bot-presets.test.ts`); H3 the skill-name grammar (`panels.test.ts`); H4 the
in-process `ctx.skills` service shapes (`panels.test.ts`); H5 `tool-skill` loads one `SKILL.md`
by catalog name (`smoke.test.ts`); H7 the prompt sections the face relies on:
`deployment:persona-prefix`, `mcp:<server>`, the `bot-journal` context (`persona.test.ts`,
`bot-plugin.test.ts`, `bots-smoke`, `bot-runtime-smoke`); H8 the system prompt as the leading
`role:'system'` message, `request/header` as the durable proof a tool was offered
(`bot-runtime-smoke`, `room-discussion-smoke`); H10 the face's instructions patch
(`boot.test.ts`, `instructions-smoke`); H11 the face's date section: `face/plugins/gravit.js`,
the first row of `bots/gravit/agent.cordis.yml`, registers `deployment:today` at
`getSectionOrder("DEPLOYMENT_PERSONA_PREFIX") + 1` with `interpolate: false` and a function text
re-evaluated at each assembly, scoped to the preset revision so a bot's prompt never carries it
(`gravit-plugin.test.ts`: order, shape, unload; `bots-smoke`: Gravit's prompt has it, a bot's
does not).

**I · environment and home layout.** I1 `DSH_HOME` resolution and the dry run's live-home
refusal (`check-home.test.ts`, `boot.test.ts`); I2 `DSH_PERMISSION_MODE` and `danger-full-access`
= approval `never`, which does not disarm Gate 2 (`orders.test.ts`); I3 `DSH_TELEMETRY_DISABLED`
and dsh-base's own `DSH_TELEMETRY_MODE` (`boot.test.ts`, `policy.test.ts`); I4
`DSH_WEB_FETCH_PROVIDER`, the `web` row's fallback (`policy.test.ts`); I6 the face's own
variables (`setup.test.ts`, `data.test.ts`); I8 the local-agent child scrub (`agents.test.ts`);
I9–I10 every file under `$DSH_HOME` the face reads and writes (`sessions.test.ts`,
`roster.test.ts`, `check-home.test.ts`; runbook §5); I11 the 0.1.1 ↔ 0.2.0 home hazards
(`check-home.test.ts`).

## 4. Decisions to re-take at every pin

The 0.2.0 re-host's D1–D18, one line each with what to re-check (`DEVELOPMENT.md` §4.8 is the
table with the defaults and the way to choose otherwise; `face/src/policy.ts` names D3–D7 and
D9 by id).

| # | Decision | Re-check when |
|---|---|---|
| D1 | no `profileContext` (no settings forms, no persisted model save, no hmr, no plugin manager) | upstream makes it required or un-gates `settings` (B8) |
| D2 | the default model is the operator's `agent-default-model` row | the DeepSeek catalog renames a model id (C18) |
| D3–D5 | telemetry, session-log upload, package inventory off | a policy target row is renamed: the face warns on stderr and the egress is ON (B24–B26) |
| D6 | `web_fetch` off, both configs restated whole | a new key on `tool-web` or `web` is dropped by the restatement (B27) |
| D7 | MCP resource tools off | mcp-client starts hard-injecting `mcpResources` (B28, G6) |
| D8 | the browser cookie only on `/` and `/api` | upstream's static posture changes (E17) |
| D9 | `ralph` re-enabled; `str_replace_editor` inserted | **0.2.1-alpha.3 moves `tool-ralph` out of dsh-base** (§7.1); dsh-base shipping the editor row again skips the insert (B29–B30) |
| D10 | no proxy policy | an adapter honours proxy variables on its own (B9, I7) |
| D11, D17 | the fourteen unreadable 0.1.1 sessions stay on disk, reported | a new migration edge, or an upstream fix for the descriptor-v2 refusal (E11) |
| D12, D13 | no older tool on the written home; the link farm deleted | every pin: the same hazard class between 0.2.0 and 0.2.x tools sharing a home (I11) |
| D14 | un-archiving a host archive refused | a session DELETE or unarchive Remote appears (E23) |
| D15 | telemetry opt-in is one operator row; the env switch still wins | the switch order in `composeFace` (B4) |
| D16 | a cold session opens page-only | `session/follow` or `session/page` activation semantics (E6–E7) |
| D18 | the spill budget stays dsh-base's `maxInlineTokens: 12500` | the row's key or default moves (B34) |

Decisions the 2026-10-15 agent redesign adds land here with their plans (§7.3).

## 5. Drills

Every drill named in `face/README.md` and `DEVELOPMENT.md` §7.4, with its runner and its state
at this pin (**automated** = a test; **manual** = a procedure with a recorded pass; **owed** =
named as still to run on 0.2.0).

| Drill | Runner | State |
|---|---|---|
| the upgrade drill (§2 steps 3–10) | tests and two manual re-diffs | last run 2026-09-30 |
| the home dry run (§2 step 11) | `scripts/check-home.ts` on a copy; `check-home.test.ts` | run 2026-09-30 on a copy; fixture-verified (runbook Appendix A) |
| Gate 2 / the approval channel | automated: `smoke.test.ts`, `client-mux-smoke`, `order-gate-smoke`; manual steps 1–7 | automated passes; deny half ran live 2026-09-30 on a scratch home; the approve half and the three card endings **owed** in a browser |
| order approval, automated half | `order-gate.test.ts`, `order-gate-smoke`, `order-gate-midboot-smoke` | passes; mutation-proven |
| order approval, manual half (a person reads the card against armed tools in a scratch home) | README steps 1–6 | **owed on every pin so far**; charter D3; the condition before the flag ever flips in `~/.dsh` |
| ask-user | automated: `smoke.test.ts`, `askuser-noclient-smoke`, `client-mux-smoke`; manual steps 1–7 | automated passes; manual **owed** on 0.2.0 (the instruction half never run) |
| client transport, automated | `client-mux-smoke`, `api.test.ts`, `mapper.test.ts`, `subagents.test.ts` | passes |
| transport, manual (sign-in, cold page-only, restart, `/compact`, agent panel, subagent dock, rename, fork, picker) | a browser | 2026-09-30 covered sign-in, cold page-only, restart, new session, agent panel; `/compact`, subagents, rename/fork/picker **owed** |
| bots, automated | `bots-smoke`, `bot-runtime-smoke`, `bot-sandbox-smoke`, `askuser-noclient-smoke` | passes |
| bots, manual (create, home conversation, tool list, `{{` refused, soul edit without restart) | README steps 1–7 | **owed** on 0.2.0 (last passed 2026-09-08 on 0.1.1) |
| room, automated | `room-smoke`, `room-discussion-smoke` + the offline room suites | passes |
| room, manual (a NEW round on `strategies/room-drill`) | README steps 1–8 | one round ran live 2026-09-30 on a scratch home; the `@`, an inline member question, a refused write, `left` and re-check, a restart **owed** |
| the subagents dock | `subagents-smoke`; the panel in a browser | manual **owed** |
| the MCP live roster | `curl …/data/plugins.json` | 10 + 14 on 2026-09-30 (scratch) and 2026-10-01 (live) |
| the first-live-boot checks (runbook §7 C) | the six checks | done 2026-10-01 (§6.1) |
| the runbook §7 A checklist on a COPY of the real home | `DSH_HOME=$SCRATCH/dsh-drill … npm start` | **owed** in full (the 2026-09-30 pass used a fresh scratch home) |

## 6. Records

### 6.1 0.1.1-rc.2 → 0.2.0-rc.2 (2026-09-30 to 2026-10-01)

**Not a version bump.** `dsh-host-apiproxy` was removed upstream and the face's whole wire
with it; the replacement is the Typert gateway (`POST /api/<ns>/<method>`, the `$events`
stream over `/api/remote.mux`) and the three controller rows. `dsh-agent-presets` became
`dsh-agent-preset` + `dsh-agent-preset-registry` (declarations, no directory scan). dsh-base
began mounting `storage`, `storage-json`, `storage-domain` and `session-projection-cache`
itself; `hmr`, `settings`, `config-editor` and `plugin-manager` became gated on
`profileContext`; telemetry's default moved DISABLED → FEEDBACK_ONLY; `web_fetch` turned on;
`tool-ralph` shipped disabled; `tool-str-replace-editor` left the bundle; the CLI's
`profile-boot` was rewritten; the session format went v3 → v4 with on-read migration. The
operator's ask was "把产品更新到最新的dsh上"; the survey of the change is in the memory of that
arc and in `DEVELOPMENT.md` §4.

**What the face did** (branch `worktree-dsh-0.2.0-rc.2`, five commits 3bbaa25..a6a6f45,
merged to local `main @ 23827c0`, pushed 2026-10-06 as part of `a6126d1`): S0 the pins; S1 the
boot mirror with its ten divergences; S2 the overlay rows (now thirteen); S3 the browser-cookie sign-in;
S4 the policy layer restoring the 0.1.1 posture (D3–D7, D9); S5 the server modules on the new
services; S6 bots as face-declared presets with `bot.js` re-expanding its mask on `tools/change`;
S7 Gate 2 on `snapshotEvents()`, armed inside `prepare` after a review proved the mid-boot
window, its approved path automated; S8 the client transport; `scripts/check-home.ts` for the
dry run; the go-live runbook; the docs pass. Suite at the end: 654 tests, 642 pass / 12
skipped offline, `FACE_SMOKE=1` 654/654, tsc clean.

**Decisions:** D1–D18 (§4).

**Losses, attributed:** fourteen 0.1.1 sessions the 0.2 migration refuses. Ten room sessions
carry the face's own `kind:'room'` source in v0 logs, which the v2→v3 edge refuses — the face's
debt, not dsh's; at v4 that kind is a sanctioned extension slot. Three subagent children carry
the `subagent/descriptor` version 2 that 0.1.1's own writer stamped, which 0.2.0's v0→v1 edge
refuses — an upstream rc→rc break of its stated format policy. One log has a sequence gap. All
thirty-nine sessions were exported losslessly with the old persistence library to
`~/dsh-session-exports-2026-10-01/` before the first 0.2 boot. A lossy rewrite (`kind:'room'` →
`kind:'plugin'` plus stripping the `@`'s `mention` member) recovers all ten room sessions on a
copy, text preserved and room structure lost; two lossless paths are untested. Live-apply
preconditions, if ever: stop the face, replace only `session.jsonl.zstd` atomically, never leave
a plain `session.jsonl` or two v0 generations.

**Go-live, 2026-10-01** (recorded in the repo for the first time here; `DEVELOPMENT.md` §10
item 14, `ROADMAP.md` and the runbook's §1 still read as if pending, §7.4): `~/.dsh` backed up
to `~/.dsh.bak-pre-0.2.0-20261001`; the dry run on a copy confirmed the fourteen refusals and
nothing else; the D2 row (`deepseek-official/deepseek-v4-pro`, `reasoningEffort: max`) appended
to `~/.dsh/profiles/face/cordis.patch.yml` (backup `cordis.patch.yml.bak-20261001`); the global
CLI upgraded to 0.2.0-rc.2 and never run; D13's 433-symlink link farm deleted; first live boot
from the primary checkout passed every §7 C check (no refusals, nine presets, token → cookie,
`/api` 401 without the cookie, `dsh 0.2.0-rc.2 / deepseek-v4-pro / max`, alpaca-kit 10 +
akshare 14, thirty-two sessions listed, a cold session page-only with zero writes under
`sessions/`); the boot wrote exactly `.credentials.yaml`, `profiles/face/cordis.yml` and
seventeen projcache records, as the dry run predicted. A smoke prompt in a new session streamed
in under ten seconds. Still owed from that day: the runbook §7 drills on the live home (§5).

### 6.2 2026-10-14 — version check

`latest` = `next` = 0.2.0-rc.2 still; face pin and global CLI match. Alpha line 0.2.1-alpha.1,
.2, .3 (2026-10-03, 10-09, 10-14) with cordis 4.0.5-alpha.2 and include 1.0.10-alpha.2 tagged
`dsh-0-2-1-alpha-3`. No v4→v5 session-format edge. Face impact found and parked in §7.1.

### 6.3 2026-10-15 — this guide

The seam inventory compiled (159 rows, nine groups, frozen at
`docs/research/2026-10-15-dsh-seams-inventory.md`) and this guide written on
`feat/agent-redesign`, beside the agent redesign spec
(`docs/superpowers/specs/2026-10-15-gravit-agent-redesign-design.md`), whose new dsh seams are
listed in §7.3 and enter §3 as their plans merge. The doc debts the compilation found are §7.4.

## 7. Watchlist for the next upgrade

### 7.1 Upstream changes already known (0.2.1-alpha.3, 2026-10-14)

- `dsh-tool-ralph` moves out of dsh-base into `dsh-experimental-ralph-bundle`: policy D9's
  `tool-ralph` patch has no row to patch (the face warns "dsh-base composes no row" and `ralph`
  leaves the roster). Decide: declare and insert the bundle, or retire `ralph` (the shipped
  presets gate it behind an explicit human request anyway).
- Subagent notifications unified: child ids returned at once, a `session/wait` Remote. Re-check
  C17 (`client/subagents.js`, `client/mapper.js`, `subagents-smoke`) and every prose that
  describes the settlement notice (the persona, `DEVELOPMENT.md` §3.6).
- `agent-instructions` drops the per-row `dshHome`; the user-global file is read via
  `DSH_AGENTS_HOME`. Re-check H6 and the face's own `instructionFileCandidates` patch (H10,
  landed in plan 1: the patch `8983555`, the smoke `2c494a1`) — whether the global file follows
  the candidate names.
- API-key precedence changes for headless runs: re-check I5 against `dsh/README.md` step 4.
- The chunk name (`lib/profile-boot-BZ2ZjNWi.js`) will be wrong: four places (§1).

### 7.2 Our own risks before the next session-format bump

- The operator's `@` is logged as `{kind:'user', mention:[…]}` (`room.ts` `say`): an extra
  member on a known kind, the pattern the v0→v1 edge refuses. Move `mention` into the face's own
  source kind before any v4→v5 edge exists, or every room log with an `@` in it becomes the next
  D11. Recorded nowhere else in the repo as of 2026-10-15.
- The room sources (`kind:'room'`, forms `answer` / `round-end` / `delta`) are admitted at v4 by
  the "any non-empty kind but `plugin`" rule; a stricter edge reopens D11 for 0.2-born rooms.
- Landed in plan 1 (`5d8c95d`): `dsh/profile/persona.md` named the `report` tool, deleted at
  0.2.0; the sentence is gone.

### 7.3 Seams the 2026-10-15 agent redesign adds (spec §8 and §11)

- the `agent-instructions` row patched by `composeFace`: `instructionFileCandidates`,
  `localInstructionFileCandidates`, `maxBytes` restated whole (a named config replaces the
  row's) — pinned by `boot.test.ts` and an instructions smoke. Landed in plan 1: the patch
  `8983555`, the smoke `2c494a1`, the `GRAVIT.md` it reads `dbbd19a` and `119c9da`; entered as
  H10 in §3.2;
- per-role `@deepseek-ai/dsh-tool-subagent` rows inside the default preset: `persona`,
  `toolFilter`, `backgroundMode: one-shot`, the `spawn` provider — the config keys, the
  capability flags the backend declares, and whether the row's persona shadows the global
  prefix for the child (spec §11 (a));
- preset-scoped tool rows under eager activation and the roster audit (spec §11 (b));
- `face/plugins/gravit.js`: `ctx.systemPrompt.section` with `interpolate: false`, the orders
  `getSectionOrder` allocates for the first-party tail (spec §11 (d)). Landed in plan 1
  (`6af2eb2`): the date section at `getSectionOrder("DEPLOYMENT_PERSONA_PREFIX") + 1`, entered as
  H11 in §3.2; the `roles` section (plan 2) and the `cycle` section (plan 3) are still to land;
- `dsh-goal` + `dsh-goal-round-driver` + `dsh-tool-goal`: the `<goal_round>` prompt text, the
  `round-limit` blocker, the disarm-after-resume rule (spec §11 (e));
- `dsh-compaction-tool-result-pruner` thresholds (8,192 / 4,096 / 1,024) that role reports are
  sized under (spec §11 (f));
- the generated default composition (`bots/<agent>/agent.cordis.yml` as a mirror of `roles/`),
  which `definitionFor` no longer reads from disk.

### 7.4 Doc debts found while compiling the inventory (fix in the next docs pass, after the rename lands)

- Fixed in plan 1: `face/README.md` "Tests" disagreed with itself on the number of real boots,
  and its table omitted `order-gate-midboot-smoke.test.ts`. It now says thirteen, the code's
  count with the instructions smoke, and its table lists thirteen files.
- The go-live of 2026-10-01 is recorded nowhere in the repo: `DEVELOPMENT.md` §10 item 14 and
  §7.4, `ROADMAP.md`, the runbook §1 (still "the global `dsh` (0.1.1-rc.2 …)") and
  `dsh/README.md` "Installed state" read as if pending; the runbook's §3 expected-findings table
  (39 / 25 / 14 sessions, 433 symlinks, `settings.yaml` present) is a 2026-09-30 snapshot a
  future dry run will not reproduce. §6.1 above is the record until those move.
- `dsh/README.md` says the approval-channel "live re-run is owed" without saying the deny half
  ran live on 2026-09-30 on a scratch home; `face/README.md` says so; `DEVELOPMENT.md` §7.4
  reconciles them.
- `DEVELOPMENT.md` Appendix A and §4.6 omit `DSH_WEB_FETCH_PROVIDER`, `DSH_TELEMETRY_MODE` and
  `PLAYWRIGHT_CLI_PATH`.
- Fixed in plan 1: `DEVELOPMENT.md` §4's size line (31 files, 9,759 lines measured on
  2026-10-15, one plain `.js` file) now reads 32 files, some 9,900 lines (9,866 measured on
  2026-10-18) and two plain `.js` files.
- `face/README.md` "What boot refuses" names three required rows "in this tree"; `boot.ts`
  cites upstream's seven; the three are a derived claim to re-derive at every pin.
- `face/README.md`'s "The Gate-2 drill" heading and its "Channels" line citations are the open
  doc debts `DEVELOPMENT.md` §10 item 4 already lists.
- `dsh-api-gateway`, `dsh-user-approval`, `dsh-user-questions` are named by the upgrade drill
  and imported by `scripts/validate-fixture.mjs` but not declared in `face/package.json`, so the
  pin sweep never sees them. Decide: declare them exact.
- The README "Run" sample boot line lists seven presets; the operator's live face declares nine
  (two untracked bots). Not an error; the sample will not match a real boot.
