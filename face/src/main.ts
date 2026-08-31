/** The face's entry point: boot the dsh tree, mount the client, hold the port.
 *
 * This module owns everything `boot.ts` deliberately left to it. In particular
 * the CLI's `installFailLoud` — its `unhandledRejection` handler — is NOT
 * installed by `composeFace`/`bootFace` (see boot.ts's header): process-level
 * failure belongs to the process's entry, and this is it.
 *
 * Configuration is two environment variables and nothing else. There is no
 * argument parsing on purpose: `bootFace` hands the tree an empty command line,
 * so a flag here would be a second, divergent notion of "the face's arguments".
 * @module
 */
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { bootFace } from "./boot.ts";
import { registerDataRoutes } from "./data.ts";
import { registerStatic } from "./static.ts";

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
 * never configures follow the working directory and nothing else. The pinned
 * `ApiProxyService` hardcodes `cwd: process.cwd()` with no config key to
 * override (dsh-host-apiproxy 0.1.1-rc.2, lib/index.js:5534), so that is the
 * project directory every `session.create` without an explicit project inherits
 * — and the sandbox's workspace root is that same directory. Left at the cwd of
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

/** Tear the tree down, then leave with `code`. A dispose that rejects still
 * exits, and says why: a signal the process has already acknowledged must not
 * end in a hang. The exit is unconditional for the same reason boot.ts keeps
 * `ctx.appExit` a bare `process.exit` — against a request to stop, a hard exit
 * beats waiting on an unbounded teardown. */
async function shutdown(code: number): Promise<void> {
  try {
    await dispose?.();
  } catch (err) {
    console.error(`${BIN}: dispose failed during shutdown:`, err);
    code ||= 1;
  }
  process.exit(code);
}

/* 130 is the shell's convention for "terminated by SIGINT" (128 + 2); a SIGTERM
 * is an orderly stop and leaves 0. */
for (const sig of ["SIGINT", "SIGTERM"] as const) {
  process.on(sig, () => void shutdown(sig === "SIGINT" ? 130 : 0));
}

/* The CLI's installFailLoud, restated here because boot.ts installs none: one
 * labelled diagnostic, then tear down and exit non-zero rather than run on in a
 * half-failed tree. */
process.on("unhandledRejection", (reason) => {
  console.error(`${BIN}: unhandled rejection - shutting down:`, reason);
  void shutdown(1);
});

const booted = await bootFace({ profileName, port });
dispose = booted.dispose;
registerStatic(booted.ctx.webServer, clientDir);
/* The instruments' data, on the same webserver as the page that reads it. Left
 * at its defaults on purpose: the producer is spawned with `$FACE_PYTHON` (else
 * `python3`) from the repo root this process just chdir'd to, and no injection
 * seam belongs on the entry point — `spawn`/`now` exist for the tests. */
registerDataRoutes(booted.ctx.webServer);
/* The URL line belongs to the shell, not to the webserver plugin (which states
 * outright that it never prints). This is that shell. Host and port are read
 * back off the service rather than off the config, so an OS-assigned port
 * reports the port that actually bound. */
console.log(
  `${BIN}: http://${booted.ctx.webServer.host}:${booted.ctx.webServer.port}/ (profile: ${profileName})`,
);
