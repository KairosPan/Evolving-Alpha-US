/** Attributes the tool-schema block of a Gravit request to its tools (design spec section 7;
 * DEVELOPMENT.md section 4.3, R31): boots the face's own composition on a COPY of a harness home,
 * with the MCP rows as the home mounts them, opens one Gravit session and prints the `tools` its
 * model request carries. The alpaca-kit row is the operator's (its keys come from the shell the
 * face starts from, dsh/README.md step 4; keyless, only seven of its ten read-only tools
 * register), so the keyed group is the operator's run, in that shell:
 *
 *     SCRATCH=$(mktemp -d)
 *     cp -a ~/.dsh "$SCRATCH/dsh-sizes"
 *     cd face && DSH_HOME="$SCRATCH/dsh-sizes" npx tsx scripts/schema-sizes.ts | tail -8
 *     rm -rf "$SCRATCH/dsh-sizes"
 *
 * Tab-separated: a `#` line (tool count, preset, home); a `tool` header; one `<tool> <bytes of
 * JSON.stringify(schema)> <bytes/4> <chars/4>` line per tool, largest first; then a `group`
 * header, one line per prefix group (`mcp__alpaca-kit__`, `mcp__akshare__`, `agent_`, `role_`,
 * then the host's own tools) and the total, each with its tool count. `chars/4` is dsh's own
 * heuristic (the UTF-16 length of the JSON over four: the unit of the 2026-10-10 figure and of
 * `contextBreakdown`); `bytes/4` is larger wherever the text is not ASCII, as AKShare's is.
 * Exit: 0 printed; 1 the boot or the read failed; 2 refused, before any dsh plugin loads, because
 * `DSH_HOME` is, is inside or contains the live harness home (`liveHomeCandidates({})` of
 * check-home.ts, both paths canonicalized, then compared by device and inode). The guard knows only
 * the default `~/.dsh`: a live home set elsewhere - a `DSH_HOME` exported in the operator's shell
 * rc, which the command line above overrides - is not detected, so copy THAT home and point
 * `DSH_HOME` at the copy.
 * @module
 */
import { existsSync, realpathSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveDshHome } from "@deepseek-ai/dsh-home-paths";
import { EXIT_INCOMPLETE, EXIT_REFUSED, liveHomeCandidates } from "./check-home.ts";

/** Prefix groups in print order; a tool joins the first prefix it starts with, else the host's. */
const GROUPS = ["mcp__alpaca-kit__", "mcp__akshare__", "agent_", "role_"];
const HOST = "(host)";

const idOf = (path: string): string | undefined => {
  try {
    const st = statSync(path);
    return `${st.dev}:${st.ino}`;
  } catch {
    return undefined;
  }
};

/** The canonical spelling of an existing path (`realpathSync.native`, as check-home.ts's guard
 * canonicalizes its target before it walks), or the path as given when it does not exist yet. */
function canonical(path: string): string {
  try {
    return realpathSync.native(path);
  } catch {
    return path;
  }
}

/** Is `ancestor` the directory `path` or one of its parents? By device and inode, so case and `..`
 * cannot disguise it. The walk climbs `path` by `dirname`, a string operation, so both paths come
 * in canonical ({@link canonical}): a symlink to a directory INSIDE the live home, or a live home
 * that is itself a symlink, would otherwise climb a spelling that never meets it. */
function sameOrAbove(ancestor: string, path: string): boolean {
  const want = idOf(ancestor);
  for (let at = path; want !== undefined; at = dirname(at)) {
    if (idOf(at) === want) return true;
    if (dirname(at) === at) break;
  }
  return false;
}

/** Why `home` must not be booted, or `undefined`.
 * @param live - the homes that must never be booted. `DSH_HOME` names the target here, so these
 * are the homes an environment WITHOUT it resolves to: `liveHomeCandidates({})`. */
export function refusal(home: string, live: readonly string[], profile = "face"): string | undefined {
  const target = canonical(home);
  for (const l of live) {
    const liveHome = canonical(l);
    if (target === liveHome || sameOrAbove(liveHome, target)) {
      return `${home} is, or is inside, the live harness home ${l}. Point DSH_HOME at a COPY: cp -a ~/.dsh "$SCRATCH/dsh-sizes"`;
    }
    if (sameOrAbove(target, liveHome)) return `${home} contains the live harness home ${l}; pass the COPY itself`;
  }
  return existsSync(join(home, "profiles", profile, "package.json")) ? undefined
    : `${home} has no profiles/${profile}: copy a home the face has booted, or run DSH_HOME=${home} npm run setup`;
}

/** The run. Returns the exit code; never exits the process itself. */
export async function run(env: NodeJS.ProcessEnv = process.env): Promise<number> {
  const profile = env.FACE_PROFILE || "face";
  const home = resolveDshHome(undefined, env);
  const why = refusal(home, liveHomeCandidates({}), profile);
  if (why !== undefined) {
    process.stderr.write(`schema-sizes: REFUSED - ${why}\n`);
    return EXIT_REFUSED;
  }
  process.env.DSH_TELEMETRY_DISABLED = "1";
  process.chdir(fileURLToPath(new URL("../../", import.meta.url))); /* main.ts's cwd: the repo root */
  try {
    /* Loaded only now: a refused run never imports a dsh plugin. */
    const { bootFace } = await import("../src/boot.ts");
    const { SessionId } = await import("@deepseek-ai/dsh-session");
    const { ctx, dispose } = await bootFace({ profileName: profile, port: 0, dshHome: home });
    let lines: string[];
    try {
      const sessions = ctx.get("sessionController") as { create(request: { cwd: string }): Promise<{ sessionId: string; agentPreset?: string }> };
      const created = await sessions.create({ cwd: process.cwd() });
      const agent = ctx.agents.get(SessionId(created.sessionId));
      if (agent === undefined) throw new Error(`session ${created.sessionId} has no live agent`);
      const schemas = (ctx.get("tools") as { schemas(scope?: object): { name: string }[] }).schemas(agent);
      const rows = schemas.map((s) => {
        const json = JSON.stringify(s);
        return { name: s.name, bytes: Buffer.byteLength(json), chars: json.length };
      }).sort((a, b) => b.bytes - a.bytes || (a.name < b.name ? -1 : 1));
      const sum = (rs: typeof rows, key: "bytes" | "chars"): number => rs.reduce((n, r) => n + r[key], 0);
      const cells = (rs: typeof rows): string => `${sum(rs, "bytes")}\t${Math.ceil(sum(rs, "bytes") / 4)}\t${Math.ceil(sum(rs, "chars") / 4)}`;
      const inGroup = (g: string): typeof rows => rows.filter((r) => (GROUPS.find((p) => r.name.startsWith(p)) ?? HOST) === g);
      lines = [`# ${rows.length} tools in the ${created.agentPreset ?? "default"} preset's scope; home ${home}`, "tool\tbytes\tbytes/4\tchars/4",
        ...rows.map((r) => `${r.name}\t${cells([r])}`), "group\ttools\tbytes\tbytes/4\tchars/4",
        ...[...GROUPS, HOST].map((g) => `${g}\t${inGroup(g).length}\t${cells(inGroup(g))}`), `total\t${rows.length}\t${cells(rows)}`];
    } finally {
      await dispose();
    }
    process.stdout.write(`${lines.join("\n")}\n`);
    return 0;
  } catch (err) {
    process.stderr.write(`schema-sizes: ${err instanceof Error ? err.message : String(err)}\n`);
    return EXIT_INCOMPLETE;
  }
}

/* Run only as a script (the guard is importable). Compared as real paths, as check-home.ts does. */
const invokedAs = process.argv[1];
if (invokedAs !== undefined && existsSync(invokedAs) &&
  realpathSync(invokedAs) === realpathSync(fileURLToPath(import.meta.url))) {
  const code = await run();
  process.exitCode = code;
  /* Everything was disposed; this only guards against a handle a plugin leaked. Unref'd. */
  setTimeout(() => process.exit(code), 10_000).unref();
}
