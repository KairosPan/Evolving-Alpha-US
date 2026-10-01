/** scripts/check-home.ts - the operator's dry run of a harness-home COPY.
 *
 * Offline: the guard that keeps the dry run off the live home, the pieces the
 * scan is built from (refusal classes, the multi-frame log reader, the
 * inventory diff, the MCP row walk), and the `FaceBootOptions.extraPatches`
 * seam in boot.ts that lets the dry run disable MCP rows without writing the
 * copy's patch files. The scan itself boots a whole tree and is proven by the
 * fixture run recorded in the go-live runbook, not here.
 *
 * No test here touches `~/.dsh`: every guard case passes its own "live home"
 * (a temp directory), and the CLI cases run the script in a child process
 * whose HOME and DSH_HOME both point into a temp directory.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, realpathSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { constants, zstdCompressSync } from "node:zlib";
import { composeEntries } from "@deepseek-ai/dsh-app-boot";
import { setupFaceProfile } from "../src/setup.ts";
import { composeFace } from "../src/boot.ts";
import { AKSHARE_MCP_ROW_ID } from "../src/akshare.ts";
import {
  EXIT_REFUSED, MARKER_FILE, MCP_CLIENT_PACKAGE, checkTarget, classifyRefusal, describeChanges, diffInventory, findPatchRow,
  inventory, liveHomeCandidates, mcpRowsIn, readLogText, reportPathFor, scanRawSessions, summarize, zstdFrames,
  type CheckHomeReport,
} from "../scripts/check-home.ts";

const FACE_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const SCRIPT = join(FACE_DIR, "scripts", "check-home.ts");

/** A temp directory, canonical (macOS puts tmpdir behind the /var -> /private/var link). */
function tempDir(prefix: string): string {
  return realpathSync.native(mkdtempSync(join(tmpdir(), prefix)));
}

/** A directory laid out like a face harness home, optionally marked as a dry-run copy. */
function faceHome(prefix: string, marked: boolean): string {
  const home = tempDir(prefix);
  setupFaceProfile(home);
  if (marked) writeFileSync(join(home, MARKER_FILE), "");
  return home;
}

/* ------------------------------------------------------------- the guard */

test("checkTarget refuses a missing argument with the usage line", () => {
  for (const arg of [undefined, "", "   "]) {
    const verdict = checkTarget(arg, [tempDir("live-")]);
    assert.equal(verdict.ok, false);
    assert.match(!verdict.ok ? verdict.reason : "", /^usage: /);
  }
});

test("checkTarget refuses a path that does not exist, and one that is a file", () => {
  const dir = tempDir("ch-");
  assert.match(String((checkTarget(join(dir, "nope"), []) as { reason: string }).reason), /does not exist/);
  writeFileSync(join(dir, "file"), "");
  assert.match(String((checkTarget(join(dir, "file"), []) as { reason: string }).reason), /not a directory/);
});

test("checkTarget refuses the live harness home itself, even when it carries the marker", () => {
  const live = faceHome("live-", true);
  const verdict = checkTarget(live, [live]);
  assert.equal(verdict.ok, false);
  assert.match(!verdict.ok ? verdict.reason : "", /IS the live harness home/);
});

test("checkTarget refuses the live home reached through a symlink", () => {
  const live = faceHome("live-", true);
  const link = join(tempDir("links-"), "looks-like-a-copy");
  symlinkSync(live, link);
  const verdict = checkTarget(link, [live]);
  assert.equal(verdict.ok, false);
  assert.match(!verdict.ok ? verdict.reason : "", /IS the live harness home/);
});

/* `realpath` keeps the caller's spelling of a name on a case-insensitive
 * volume (measured on APFS: realpathSync("/x/abc") of a directory created as
 * "AbC" returns ".../abc"), so a string comparison would let `~/.DSH` through.
 * The guard compares device + inode; this case runs where the temp volume is
 * case-insensitive (macOS default) and skips elsewhere. */
test("checkTarget refuses the live home spelled in another letter case", (t) => {
  const parent = tempDir("case-");
  const live = join(parent, "LiveHome");
  mkdirSync(live);
  setupFaceProfile(live);
  writeFileSync(join(live, MARKER_FILE), "");
  const other = join(parent, "livehome");
  if (!existsSync(other)) {
    t.skip("the temp volume is case-sensitive");
    return;
  }
  const verdict = checkTarget(other, [live]);
  assert.equal(verdict.ok, false);
  assert.match(!verdict.ok ? verdict.reason : "", /IS the live harness home/);
});

test("checkTarget refuses a path inside the live home, and one that contains it", () => {
  const live = faceHome("live-", false);
  const inside = join(live, "copy");
  mkdirSync(inside);
  setupFaceProfile(inside);
  writeFileSync(join(inside, MARKER_FILE), "");
  const verdictInside = checkTarget(inside, [live]);
  assert.equal(verdictInside.ok, false);
  assert.match(!verdictInside.ok ? verdictInside.reason : "", /inside the live harness home/);

  const parent = tempDir("parent-");
  const nestedLive = join(parent, "deep", ".dsh");
  mkdirSync(nestedLive, { recursive: true });
  setupFaceProfile(parent);
  writeFileSync(join(parent, MARKER_FILE), "");
  const verdictAbove = checkTarget(parent, [nestedLive]);
  assert.equal(verdictAbove.ok, false);
  assert.match(!verdictAbove.ok ? verdictAbove.reason : "", /contains the live harness home/);
});

test("checkTarget refuses a copy without the DRY-RUN-COPY marker (a directory of that name is not one)", () => {
  const live = tempDir("live-");
  const copy = faceHome("copy-", false);
  const verdict = checkTarget(copy, [live]);
  assert.equal(verdict.ok, false);
  assert.match(!verdict.ok ? verdict.reason : "", new RegExp(`no ${MARKER_FILE} marker`));
  assert.match(!verdict.ok ? verdict.reason : "", /touch '/, "the refusal says how to mark the copy");
  mkdirSync(join(copy, MARKER_FILE));
  assert.equal(checkTarget(copy, [live]).ok, false);
});

test("checkTarget refuses a marked directory that is not a face home", () => {
  const copy = tempDir("copy-");
  writeFileSync(join(copy, MARKER_FILE), "");
  const verdict = checkTarget(copy, [tempDir("live-")]);
  assert.equal(verdict.ok, false);
  assert.match(!verdict.ok ? verdict.reason : "", /no profiles\/face\/package\.json/);
});

test("checkTarget accepts a marked copy of a face home, whatever the live home is", () => {
  const copy = faceHome("copy-", true);
  const absentLive = join(tempDir("nohome-"), ".dsh");
  for (const live of [[tempDir("live-")], [absentLive], []]) {
    const verdict = checkTarget(copy, live);
    assert.deepEqual(verdict, { ok: true, copy });
  }
  assert.equal(reportPathFor(copy), `${copy}.check-home.json`, "the report lands BESIDE the copy");
});

test("liveHomeCandidates: $DSH_HOME as dsh resolves it, plus ~/.dsh; a blank DSH_HOME is unset", () => {
  const custom = tempDir("custom-");
  const both = liveHomeCandidates({ DSH_HOME: custom });
  assert.equal(both.length, 2);
  assert.equal(both[0], custom);
  assert.match(both[1] ?? "", /\/\.dsh$/);
  assert.deepEqual(liveHomeCandidates({ DSH_HOME: "  " }), [both[1]]);
});

/* ------------------------------------------------------ the CLI refusals */

/** Run the script in a child process whose HOME and DSH_HOME are temp
 * directories, so even a guard bug could reach nothing real. */
function runScript(args: string[], env: Record<string, string>): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    execFile(
      process.execPath,
      ["--import", "tsx", SCRIPT, ...args],
      { cwd: FACE_DIR, env: { ...process.env, ...env }, timeout: 60_000 },
      (err, stdout, stderr) => {
        const code = err === null ? 0 : typeof err.code === "number" ? err.code : -1;
        resolve({ code, stdout, stderr });
      },
    );
  });
}

test("the script refuses the live home with exit 2 before it loads or writes anything", async () => {
  const fakeUser = tempDir("user-");
  const live = faceHome("live-", true);
  const before = inventory(live);
  const byDshHome = await runScript([live], { HOME: fakeUser, DSH_HOME: live });
  assert.equal(byDshHome.code, EXIT_REFUSED);
  assert.match(byDshHome.stderr, /check-home: REFUSED - .* IS the live harness home/);
  assert.equal(byDshHome.stdout, "");
  assert.deepEqual(diffInventory(before, inventory(live)), [], "a refused run writes nothing in the target");
  assert.equal(existsSync(reportPathFor(live)), false, "and no report");

  /* the default home, ~/.dsh, is refused with DSH_HOME unset too */
  const defaultHome = join(fakeUser, ".dsh");
  mkdirSync(defaultHome);
  setupFaceProfile(defaultHome);
  writeFileSync(join(defaultHome, MARKER_FILE), "");
  const byDefault = await runScript(["~/.dsh"], { HOME: fakeUser, DSH_HOME: "" });
  assert.equal(byDefault.code, EXIT_REFUSED);
  assert.match(byDefault.stderr, /IS the live harness home/);
});

test("the script refuses an unmarked copy and a missing argument with exit 2", async () => {
  const fakeUser = tempDir("user-");
  const copy = faceHome("copy-", false);
  const before = inventory(copy);
  const unmarked = await runScript([copy], { HOME: fakeUser, DSH_HOME: join(fakeUser, ".dsh") });
  assert.equal(unmarked.code, EXIT_REFUSED);
  assert.match(unmarked.stderr, new RegExp(`no ${MARKER_FILE} marker`));
  assert.deepEqual(diffInventory(before, inventory(copy)), []);
  const bare = await runScript([], { HOME: fakeUser, DSH_HOME: join(fakeUser, ".dsh") });
  assert.equal(bare.code, EXIT_REFUSED);
  assert.match(bare.stderr, /usage: npx tsx scripts\/check-home\.ts/);
});

/* ------------------------------------------------- the scan's building blocks */

test("classifyRefusal: the three measured classes by upstream's own text, everything else is 'other'", () => {
  const room = { name: "SessionFormatUnsupportedError", message: "cannot safely transform unclassified message source; source v0 artifact remains unchanged (raw log: /x)" };
  assert.equal(classifyRefusal(room, ["model", "room", "user"]), "room-source");
  assert.equal(classifyRefusal(room, ["model", "user"]), "other", "an unclassified source that is not a room is covered by no decision");
  assert.equal(classifyRefusal(room, undefined), "other", "an unreadable raw log cannot confirm the room kind");
  assert.equal(classifyRefusal({
    name: "SessionFormatUnsupportedError",
    message: "subagent/descriptor 0 uses unsupported descriptor version 2; source v0 artifact remains unchanged (raw log: /x)",
  }, undefined), "subagent-descriptor");
  assert.equal(classifyRefusal({
    name: "SessionPersistenceCorruptionError",
    message: 'session "s": stored log is corrupt: SessionFormatError: released Session row 195 has seq gap (expected 3455, got 3427) (raw log: /x)',
  }, undefined), "seq-gap");
  assert.equal(classifyRefusal({ name: "SessionFormatUnsupportedError", message: "format v2 to v3 cannot safely transform unclassified event x/y" }, ["room"]), "other");
});

const frame = (text: string): Buffer => zstdCompressSync(Buffer.from(text), { params: { [constants.ZSTD_c_checksumFlag]: 1 } });

test("zstdFrames/readLogText decode EVERY frame of a multi-frame log (node:zlib alone reads the first)", () => {
  const dir = tempDir("zstd-");
  const one = frame('{"type":"session"}\n');
  const two = frame('{"type":"a","seq":0}\n{"type":"b","seq":1}\n');
  const file = join(dir, "session.jsonl.zstd");
  writeFileSync(file, Buffer.concat([one, two]));
  assert.deepEqual(zstdFrames(Buffer.concat([one, two])).frames, [[0, one.length], [one.length, one.length + two.length]]);
  assert.equal(readLogText(file).text.split("\n").filter(Boolean).length, 3);
  const torn = zstdFrames(Buffer.concat([one, two.subarray(0, two.length - 3)]));
  assert.equal(torn.torn, true);
  assert.equal(torn.frames.length, 1, "a frame EOF interrupts is not decoded");
  assert.throws(() => zstdFrames(Buffer.from("not zstd at all")), /not a Zstandard frame/);
});

test("scanRawSessions picks the highest generation per directory and counts raw events and source kinds", () => {
  const home = tempDir("raw-");
  const v0 = join(home, "sessions", "--work--", "session-a");
  const both = join(home, "sessions", "--work--", "session-b");
  mkdirSync(v0, { recursive: true });
  mkdirSync(both, { recursive: true });
  writeFileSync(join(v0, "session.jsonl.zstd"), Buffer.concat([
    frame('{"type":"session","version":0,"id":"session-a"}\n'),
    frame('{"type":"user/message","data":{"source":{"kind":"room"}}}\n{"type":"assistant/message","data":{"message":{"source":{"kind":"model"}}}}\n'),
  ]));
  writeFileSync(join(both, "session.jsonl.zstd"), frame('{"type":"session","version":0,"id":"session-b"}\n{"type":"x"}\n'));
  writeFileSync(join(both, "session.v4.jsonl.zstd"), Buffer.concat([
    frame('{"type":"session","version":4,"id":"session-b"}\n'), frame('{"type":"x"}\n{"type":"y"}\n{"type":"z"}\n'),
  ]));
  writeFileSync(join(both, "session.lock"), "");
  const raw = scanRawSessions(home);
  assert.deepEqual({ ...raw.get("session-a"), dir: undefined, bytes: undefined }, {
    dir: undefined, bytes: undefined, files: ["session.jsonl.zstd"], log: "session.jsonl.zstd", generation: 0,
    rawEvents: 2, sourceKinds: ["model", "room"],
  });
  const b = raw.get("session-b");
  assert.equal(b?.log, "session.v4.jsonl.zstd", "dsh reads the highest canonical generation");
  assert.equal(b?.rawEvents, 3);
  assert.deepEqual(b?.files, ["session.jsonl.zstd", "session.lock", "session.v4.jsonl.zstd"]);
});

test("inventory/diffInventory tell added, removed, modified and rewritten apart, and never follow a link", async () => {
  const root = tempDir("inv-");
  writeFileSync(join(root, "same"), "x");
  writeFileSync(join(root, "changed"), "a");
  writeFileSync(join(root, "gone"), "g");
  symlinkSync("/nonexistent/target", join(root, "link"));
  const before = inventory(root);
  assert.equal(before.get("link")?.kind, "link");
  await new Promise((r) => setTimeout(r, 20));
  writeFileSync(join(root, "same"), "x");
  writeFileSync(join(root, "changed"), "b");
  writeFileSync(join(root, "new"), "n");
  rmSync(join(root, "gone"));
  assert.deepEqual(diffInventory(before, inventory(root)).map((c) => `${c.change} ${c.path}`), [
    "modified changed", "removed gone", "added new", "rewritten same",
  ]);
});

test("mcpRowsIn finds every MCP client row, inside groups too; findPatchRow reports the last write", () => {
  const entries = [
    { id: "mcp-akshare", name: MCP_CLIENT_PACKAGE, config: { serverName: "akshare" } },
    { id: "tools", name: "@deepseek-ai/dsh-tools" },
    { id: "grp", name: "@deepseek-ai/cordis-plugin-group", group: true, config: [
      { id: "mcp-nested", name: MCP_CLIENT_PACKAGE, config: { serverName: "nested" } },
    ] },
    { name: MCP_CLIENT_PACKAGE, config: { serverName: "anonymous" } },
  ];
  assert.deepEqual(mcpRowsIn(entries), [
    { id: "mcp-akshare", serverName: "akshare" }, { id: "mcp-nested", serverName: "nested" }, { serverName: "anonymous" },
  ]);
  assert.equal(findPatchRow([{ insert: [{ id: "x" }] }], "agent-default-model"), undefined);
  assert.deepEqual(findPatchRow([
    { insert: [{ id: "agent-default-model", name: "@deepseek-ai/dsh-agent-default-model", config: { provider: "a", model: "b" } }] },
    { id: "agent-default-model", config: { provider: "deepseek-official", model: "deepseek-v4-pro", reasoningEffort: "max" } },
  ], "agent-default-model"), {
    source: "patch", config: { provider: "deepseek-official", model: "deepseek-v4-pro", reasoningEffort: "max" }, disabled: undefined,
  });
});

/* ------------------------------------ the boot.ts seam the dry run stands on */

/** A composed row by id. */
function row(patches: Parameters<typeof composeEntries>[0][number], id: string): Record<string, unknown> | undefined {
  return composeEntries([patches]).find((r) => r.id === id) as Record<string, unknown> | undefined;
}

test("extraPatches: unset composes exactly the stack it composed before the option existed", () => {
  const home = faceHome("seam-", false);
  const plain = composeFace({ profileName: "face", port: 3090, dshHome: home }).patches;
  const empty = composeFace({ profileName: "face", port: 3090, dshHome: home, extraPatches: [] }).patches;
  assert.deepEqual(empty, plain);
});

test("extraPatches compose AFTER the operator's layers: they disable an operator MCP row and beat an operator re-enable", () => {
  const home = faceHome("seam-", false);
  writeFileSync(join(home, "profiles", "face", "cordis.patch.yml"), [
    "- insert:",
    "    - id: mcp-alpaca-kit",
    `      name: '${MCP_CLIENT_PACKAGE}'`,
    "      config: { transport: stdio, serverName: alpaca-kit, command: /bin/false }",
    `- id: ${AKSHARE_MCP_ROW_ID}`,
    "  disabled: false",
    "",
  ].join("\n"));
  const extra = [{ id: "mcp-alpaca-kit", disabled: true }, { id: AKSHARE_MCP_ROW_ID, disabled: true }];
  const callerCopy = structuredClone(extra);
  const { patches } = composeFace({ profileName: "face", port: 3090, dshHome: home, extraPatches: extra });
  assert.equal(row(patches, "mcp-alpaca-kit")?.disabled, true, "the operator's inserted row is disabled");
  assert.equal(row(patches, AKSHARE_MCP_ROW_ID)?.disabled, true, "the operator's re-enable loses to the extra layer");
  assert.deepEqual(extra, callerCopy, "the caller's patch objects are not rewritten by the composition");
  const without = composeFace({ profileName: "face", port: 3090, dshHome: home }).patches;
  assert.notEqual(row(without, "mcp-alpaca-kit")?.disabled, true, "and without it the operator's row stays enabled");
});

test("extraPatches compose BEFORE the face's own rows: they cannot move a face-owned row", () => {
  const home = faceHome("seam-", false);
  const { patches } = composeFace({
    profileName: "face", port: 3090, dshHome: home, extraPatches: [{ id: "webserver", config: { port: 1 } }],
  });
  assert.equal((row(patches, "webserver")?.config as { port?: number } | undefined)?.port, 3090);
});

test("describeChanges folds a directory of same-kind changes; summarize always ends with the delete reminder", () => {
  const changes = [
    { path: ".credentials.yaml", change: "modified" as const, kind: "file" as const },
    ...[1, 2, 3, 4].map((n) => ({ path: `storages/session_projcache/sessions/s${n}.json`, change: "added" as const, kind: "file" as const })),
  ];
  assert.deepEqual(describeChanges(changes), [
    "~ .credentials.yaml (modified)", "+ storages/session_projcache/sessions/ (4 files added)",
  ]);
  const report: CheckHomeReport = {
    tool: "face/scripts/check-home.ts", dshPin: "0.2.0-rc.2", generatedAt: "", copy: "/tmp/x/dsh-dryrun", liveHomes: ["/h/.dsh"],
    profile: "face", boot: { ok: false, error: "boom", mcpRowsDisabled: [] }, defaultModel: {},
    settingsYaml: { present: false, importedCopyPresent: false }, linkFarm: { present: false }, roster: [],
    sessions: {
      listed: 0, readable: 0, refused: 0, byClass: { "room-source": [], "subagent-descriptor": [], "seq-gap": [], other: [] },
      orphanedPresets: [], rawEvents: { total: 0, refused: 0 }, bytes: { total: 0, refused: 0 }, notListed: [], items: [],
    },
    writes: { boot: [], scanWindow: [], dispose: [], sessionsTouchedByScan: [] }, warnings: [],
  };
  const failed = summarize(report, "/tmp/x/dsh-dryrun.check-home.json");
  assert.match(failed, /boot: {7}FAILED - boom/);
  assert.match(failed, /DELETE THE COPY NOW/);
  assert.match(failed, /rm -rf '\/tmp\/x\/dsh-dryrun'/);
  assert.doesNotMatch(failed, /signing secret/, "no grant was written, so none is claimed");
});
