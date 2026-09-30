/** The face's entry point: boot the dsh tree, mount the client, hold the port.
 *
 * This module owns everything `boot.ts` deliberately left to it — process
 * lifetime above all. `bootFace` installs no signal handlers and no
 * `installFailLoud` (boot.ts, divergence 4); this entry installs app-boot's own
 * `installFailLoud` verbatim, before the boot it guards, exactly where the CLI
 * does (NEW apps/cli/src/profile-boot.ts:282-284).
 *
 * Configuration comes from environment variables. There is no
 * argument parsing on purpose: `bootFace` hands the tree an empty command line,
 * so a flag here would be a second, divergent notion of "the face's arguments".
 * @module
 */
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { installFailLoud, StartupError } from "@deepseek-ai/dsh-app-boot";
import { resolveDshHome } from "@deepseek-ai/dsh-home-paths";
import { bootFace, type BootedFace } from "./boot.ts";
import { listBots, registerBotRoutes } from "./bots.ts";
import { installBotRuntime, registerBotRuntimeRoutes } from "./bot-runtime.ts";
import { readBotJournal } from "./bot-journal.ts";
import { BOTS_ROOT } from "./overlay.ts";
import { registerDataRoutes } from "./data.ts";
import { registerStatic, type IndexAuth } from "./static.ts";
import { registerSessionRoutes } from "./sessions.ts";
import { listSessionHeads, registerChannelRoutes, type RegistryLike } from "./channels.ts";
import { hasExec, panelDeps, readAgentsMeta, registerPanelRoutes } from "./panels.ts";
import { installRoom, registerRoomRoutes, type RoomContextLike } from "./room.ts";

/** Diagnostic label, the same string boot.ts uses for `BIN`. Not imported
 * because boot.ts does not export it, and it is a label rather than a contract:
 * what matters is that a stack from the face never reads as one from `dsh`. */
const BIN = "kairos-face";

/* `||`, not `??`, on both — mirroring setup.ts. An env var exported empty is
 * one the operator meant to leave at its default, and `??` would take it
 * literally: `FACE_PROFILE=""` resolves to `$DSH_HOME/profiles` itself, and
 * `FACE_PORT=""` is `Number("") === 0`, which asks the OS for a free port — a
 * face whose URL silently moves on every restart. `"0"` is a non-empty string,
 * so deliberately asking for an OS-assigned port still works. */
const port = Number(process.env.FACE_PORT || 3090);
const profileName = process.env.FACE_PROFILE || "face";

/* Resolved from this module, never from the working directory: `npm start` runs
 * in face/, but the entry must find its own sibling client/ wherever it is
 * launched from. */
const moduleDir = dirname(fileURLToPath(import.meta.url));
const clientDir = join(moduleDir, "..", "client");

/* The workbench repo root: this file is face/src/main.ts, so up two.
 *
 * Anchor the PROCESS here, before `bootFace` below, because two things the face
 * never configures follow the working directory and nothing else. The
 * `SessionController` that replaced 0.1.1's `ApiProxyService` still hardcodes
 * `process.cwd()` as its default project directory, with no config key to
 * override it (`new SessionCommandController(ctx, this.agents, process.cwd())`,
 * NEW packages/api/session-controller/src/index.ts:139), so that is the
 * project directory every `session/create` without an explicit `cwd` or
 * `workspaceId` inherits — and dsh-base's sandbox workspace root is that same
 * directory (`sandbox-policy.workspaceRoot: !!js process.cwd()`, NEW
 * packages/bundle/base/cordis.patch.yml:229-233). Left at the cwd of
 * `cd face && npm start`, both would be `face/`, which is wrong in BOTH
 * directions: the agent could rewrite the face's own source un-asked while a
 * write to `strategies/` — its actual arena — needed a Gate-2 escalation. Spec
 * section 3.2 commits `cwd` = the workbench repo root; this is where that
 * commitment is kept.
 *
 * Safe against the other cwd reader in the boot path: `loadLayeredEnv` reads
 * `<cwd>/.env`, and no `.env` exists at either face/ or the repo root (the
 * repo's keys live in the differently-named `.env.deepseek` / `.env.alpaca`,
 * which are sourced by the operator, never auto-loaded). Every other path the
 * face resolves — `clientDir` above, boot.ts's `INSTALL_ANCHOR` — is
 * module-relative and does not move with this. */
process.chdir(join(moduleDir, "..", ".."));

/** The booted tree's disposer, once there is a tree. Left `undefined` until
 * then so the failure handlers below can be installed BEFORE the boot they
 * guard — a rejection thrown while plugins are still initializing is exactly
 * the case `installFailLoud` exists for, and a handler installed afterwards
 * would miss it. */
let dispose: (() => Promise<void>) | undefined;

/** The room engine's own unwind (the `dispatch` tool, the room projection, the
 * root bus listener and every armed member deadline). Separate from `dispose`
 * because the engine is installed ON the booted tree rather than by it, and a
 * deadline that outlives the process's stop can still cancel a member. */
let disposeRoom: (() => void) | undefined;
let disposeData: (() => void) | undefined;

/** Tear the tree down, then leave with `code`. A dispose that rejects still
 * exits, and says why: a signal the process has already acknowledged must not
 * end in a hang. The exit is unconditional for the same reason boot.ts keeps
 * `ctx.appExit` a bare `process.exit` — against a request to stop, a hard exit
 * beats waiting on an unbounded teardown. */
async function shutdown(code: number): Promise<void> {
  try {
    disposeRoom?.();
    disposeData?.();
    await dispose?.();
  } catch (err) {
    console.error(`${BIN}: dispose failed during shutdown:`, err);
    code ||= 1;
  }
  process.exit(code);
}

/* 130 is the shell's convention for "terminated by SIGINT" (128 + 2); a SIGTERM
 * is an orderly stop and leaves 0 — the CLI's own mapping (NEW
 * apps/cli/src/profile-boot.ts:275-281). */
for (const sig of ["SIGINT", "SIGTERM"] as const) {
  process.on(sig, () => void shutdown(sig === "SIGINT" ? 130 : 0));
}

/* app-boot's own process guard, replacing the hand-rolled `unhandledRejection`
 * handler 0.1.1 needed. Load-bearing, not cosmetic: under 0.2.0's best-effort
 * startup the Loader "derives and drops a rejected promise after a fiber
 * fails", and `installFailLoud` skips exactly the reasons boot's startup audit
 * already folded into its diagnostic (NEW packages/boot/app-boot/src/
 * index.ts:606-631, 715-716) — a naive handler would turn that expected echo
 * into a second, misleading fatal report. It also covers `uncaughtException`
 * (:720), writes one labelled `util.inspect` diagnostic, awaits `release`
 * under a 2 s bound, and exits 1 (:679-728). `release` unwinds what this entry
 * installed on the tree before the tree itself. */
installFailLoud(BIN, process, async () => {
  disposeRoom?.();
  disposeData?.();
  await dispose?.();
});

/* A `StartupError` is dsh's own grouped diagnostic for a required entry that
 * did not activate (failed plugins with their packages and stacks, plugins
 * waiting on services; NEW packages/boot/app-boot/src/index.ts:801-817,
 * 886-907): its message IS the report, so print it plain and exit. `bootFace`
 * has already disposed the tree. Anything else rethrows into `installFailLoud`
 * above, which prints it in full. */
let booted: BootedFace;
try {
  /* `deferReady`: the gateway admits no `/api/remote.mux` stream until this
   * entry calls `booted.commitReady()` - LAST, after every route below is
   * mounted. A tab still holding its 30-day cookie reconnects the moment the
   * gateway admits it, and its first `onReady` reads `/data/*`; committing
   * inside `bootFace` would let it find those routes missing (boot.ts
   * divergence 5; critique-boot-and-composition observation 3). */
  booted = await bootFace({ profileName, port, deferReady: true });
} catch (err) {
  if (err instanceof StartupError) {
    console.error(err.message);
    process.exit(1);
  }
  throw err;
}
dispose = booted.dispose;
/* The browser sign-in (static.ts). `connection` is the dsh-client-connection
 * service — a REQUIRED startup entry upstream and ACTIVE by bootFace's own row
 * audit, so a miss here means the service key itself moved: refuse rather than
 * serve a `/` that could never mint the cookie `/api` now demands. */
const connection = booted.ctx.get("connection") as
  | (IndexAuth & { authenticatedUrl(baseUrl: string): string })
  | undefined;
if (connection === undefined) {
  throw new Error(`${BIN}: the connection service is missing - / could not sign the browser in`);
}
registerStatic(booted.ctx.webServer, clientDir, connection);
/* The instruments' data, on the same webserver as the page that reads it. Left
 * at its defaults on purpose: the producer is spawned with `$FACE_PYTHON` (else
 * `python3`) from the repo root this process just chdir'd to, and no injection
 * seam belongs on the entry point — `spawn`/`now` exist for the tests. */
disposeData = registerDataRoutes(booted.ctx.webServer);
/* The channel picker's data (sidebar + landing page) and the new-channel copy
 * action. `process.cwd()` is the workbench repo root — the chdir above put it
 * there. `dshHome` is resolved the same way every other route family here
 * resolves it (sessions.ts, panels.ts): independently, from the same
 * unchanging env state, rather than threaded as a shared value.
 *
 * `workspaceRegistry`, `sessions` and `sessionPersistence` are read through
 * `ctx.get`, not property access: `dsh-workspace`, `dsh-session` and
 * `dsh-session-persistence` each declare a
 * `declare module "@deepseek-ai/cordis" { interface Context { ... } }`
 * augmentation for their service, but nothing in this program imports any of
 * those packages' TYPES (only their names, in comments and strings) - so tsc
 * never loads those augmentations and never learns `Context` carries them.
 * Same cast-through-`get` pattern boot.ts and panels.ts already use for
 * `approval`/`userQuestions`/`skills`/`tools`/`loader`. */
const dshHome = resolveDshHome(undefined);
const workspaceRegistry = booted.ctx.get("workspaceRegistry") as RegistryLike;
const sessions = booted.ctx.get("sessions") as {
  list(): { id: unknown; header: { cwd?: string; agentPreset?: string } }[];
};
/* `sessionPersistence` is guaranteed present whenever `workspaceRegistry` is:
 * the registry's own `static inject` names it as a hard dependency
 * (NEW packages/workspace/workspace/src/index.ts:171), so Cordis cannot have
 * composed the registry above without it. C1: `sessions.list()` alone answers
 * "All live sessions" (NEW packages/core/session/src/index.ts:1232-1235) —
 * sessions loaded into THIS process — never the durable history, so feeding
 * the reconcile from it alone strands every session that is not live at the
 * moment the sidebar polls in `ungrouped` (measured: 15 channel-eligible
 * sessions on disk, 5 attached). `sessionPersistence.list()` is the durable
 * listing; `mergeSessionHeads` unions it with the live one, live winning, the
 * same order `dsh-workspace`'s own bootstrap indexes them in.
 *
 * 0.2.0 changed what that listing RETURNS, silently: snapshots
 * `{header, revision, eventCount?, sizeBytes?}` instead of bare headers (NEW
 * packages/session/session-persistence/src/index.ts:50-58, 201; commit
 * bec6805d6a). Read the id off a snapshot's top level and every durable
 * session becomes `sessionId: "undefined"` with no error anywhere. The
 * workspace registry maps the same way (`snapshots.map(snapshot =>
 * snapshot.header)`, NEW packages/workspace/workspace/src/index.ts:824-827).
 *
 * Both listings also carry the header's `agentPreset`: `session/list` rows lost
 * their `agentPreset` field at 0.2.0 (NEW packages/api/session-controller/src/
 * types.ts:177-188), and a cold pre-upgrade session's projection cache holds
 * only the title hint, so the persisted header is the client's fallback for
 * bucketing bots vs Kairos (PLAN S8 "Server support for the client":
 * `/data/channels.json` gains `presets: Record<sessionId, agentPreset>` built
 * from these heads). A header's preset is the one it was CREATED with; a live
 * re-selection shows in the projection, which the client prefers. */
const sessionPersistence = booted.ctx.get("sessionPersistence") as {
  list(): Promise<readonly { header: { id: unknown; cwd?: string; agentPreset?: string } }[]>;
};
/* Bots: the preset roster's view comes from the live service the overlay
 * mounted (boot.ts asserts it is there); the directories are read from disk.
 * Hoisted above the channel routes, which read the same roster for their
 * overview's `allBots`. */
const agentPresets = booted.ctx.get("agentPresets") as { list(): Promise<{ id: string; broken?: string }[]> };
/* The face's own declarations (src/bot-presets.ts, PLAN S6): dsh 0.2.0 reads
 * no bot directory itself, so `bootFace` declared every `bots/<id>/` but the
 * default, and this handle re-declares one when the operator saves it. */
const botPresets = booted.botPresets;
/** Every bot row the routes, rooms, channels and bot runtime read: the
 * directories on disk, dsh's roster, and the face's own declaration failures
 * as broken reasons - one reader, so no surface can show a bot another hides. */
const allBots = () => listBots(BOTS_ROOT, () => agentPresets.list(), botPresets.errors);
registerChannelRoutes(booted.ctx.webServer, {
  registry: workspaceRegistry,
  root: process.cwd(),
  home: dshHome,
  listSessions: () => listSessionHeads(
    async () => (await sessionPersistence.list()).map((s) => ({
      sessionId: String(s.header.id), cwd: s.header.cwd, agentPreset: s.header.agentPreset,
    })),
    () => sessions.list().map((s) => ({ sessionId: String(s.id), cwd: s.header.cwd, agentPreset: s.header.agentPreset })),
    (err) => console.error(`${BIN}: the durable session listing failed; this listing groups only live sessions:`, err),
  ),
  /* Only a bin with a recipe can become an `agent_<bin>` tool (`hasExec`), so
   * only those are worth seeding into a newly adopted channel's roster. */
  connectedBins: async () => (await readAgentsMeta(dshHome)).connected
    .map((row) => row.bin).filter((bin) => hasExec(bin)),
  listBots: allBots,
});
/* Delete + archive, which the host's own Remote surface still lacks a delete
 * for (no delete Remote in session-controller or workspace-controller at
 * 0.2.0-rc.2). `root` is the same repo-root commitment `registerChannelRoutes`
 * above got, and for the same reason: `deleteSession` refuses any session
 * whose header cwd falls outside it — ids are unique across every project
 * under `$DSH_HOME/sessions/`, not just this repo's. `hostArchive` is the
 * already-resolved `workspaceRegistry`, reused here rather than re-fetched:
 * its `archivedSessionIds` is what tells `setArchived` an un-archive click is
 * one the face leaves to the host (PLAN D14). */
registerSessionRoutes(booted.ctx.webServer, { root: process.cwd(), home: dshHome, hostArchive: workspaceRegistry });
registerBotRoutes(booted.ctx.webServer, {
  botsRoot: BOTS_ROOT,
  listPresets: () => agentPresets.list(),
  declarationErrors: botPresets.errors,
  /* dsh 0.2.0 never re-reads bots/<id>/ (0.1.1 re-read it on every mount): a
   * create or save must re-declare the bot's preset before the route answers,
   * or the saved soul reaches nothing until a restart (src/bots.ts
   * BotRouteDeps.onBotChanged). Old conversations keep the revision they
   * joined; new ones get the saved files. */
  onBotChanged: (id) => botPresets.redeclare(id),
});
const botRuntime = installBotRuntime(booted.ctx, allBots, {
  readJournal: (id) => readBotJournal(BOTS_ROOT, id),
});
registerBotRuntimeRoutes(booted.ctx.webServer, botRuntime);
/* Rooms: the engine lives on the ROOT context (a root-created member is a
 * runtime root, so it can ask the operator a question; a root listener sees
 * every session). `channelFor` is the same lookup the agent tools use, now
 * carrying the channel directory a member session is created in. The booted
 * ctx carries `sessionController` (the overlay's session-controller row), which
 * the engine resumes cold rooms through. */
const deps = panelDeps(booted.ctx, process.cwd());
const room = installRoom({
  ctx: booted.ctx as unknown as RoomContextLike,
  home: dshHome,
  channelFor: deps.channelFor,
  listBots: allBots,
});
disposeRoom = () => { room.dispose(); botRuntime.dispose(); };
registerRoomRoutes(booted.ctx.webServer, room);
/* The master rail's feeds: in-process reads of the booted tree (skills /
 * tools / loader), plus the local-agent roster — awaited, because every agent
 * already on the roster is registered as a tool for Kairos before the face
 * reports itself up. */
await registerPanelRoutes(booted.ctx.webServer, deps);
/* Every route is mounted: only now may the gateway admit a browser stream
 * (bootFace was told `deferReady`). It re-checks that the root is still
 * active and throws otherwise - into `installFailLoud` above, which releases
 * the tree and exits 1 rather than serving a face that can never stream. */
booted.commitReady();
/* The URL line belongs to the shell, not to the webserver plugin (which states
 * outright that it never prints). This is that shell. Host and port are read
 * back off the service rather than off the config, so an OS-assigned port
 * reports the port that actually bound.
 *
 * The URL carries `?token=`: the per-process launch token Connection mints
 * (32 random bytes, new on every start; NEW packages/client/connection/src/
 * browser-auth.ts:52-58, 223-227), the ONLY input that mints the browser
 * cookie (static.ts). The upstream printer does the same (NEW
 * packages/bundle/web-app/src/index.ts:252-289). The cookie is bound to the
 * exact authority — `127.0.0.1:3090` and `localhost:3090` are two sign-ins
 * (browser-auth.ts:69-78, 106-108) — and its signing secret persists in the
 * credentials store, so it survives restarts for its 30 days. */
const baseUrl = `http://${booted.ctx.webServer.host}:${booted.ctx.webServer.port}/`;
console.log(`${BIN}: ${connection.authenticatedUrl(baseUrl)} (profile: ${profileName})`);
console.log(
  `${BIN}: the ?token= is a per-process secret: it mints a 30-day cookie for this host:port;` +
    ` later visits to the plain URL work`,
);
console.log(`${BIN}: rooms: dispatch registered; caps ${JSON.stringify(room.caps)}`);
