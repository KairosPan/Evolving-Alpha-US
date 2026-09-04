/** `/data/strategies.json` + `POST /data/strategies`: the strategy arena as
 * the session picker sees it.
 *
 * A face session's dsh workspace IS a strategy directory: `session.create`
 * takes the directory as `cwd`, and the sandbox's workspace-write boundary
 * follows it — so a strategy session writes its own `strategies/<name>/`
 * freely and everything else (the repo's `.git` included) only through a
 * Gate-2 escalation. These two routes feed that picker: the GET lists the
 * strategy directories with each one's lifecycle status, the POST births a
 * new strategy by copying `strategies/_template` (the AGENTS.md protocol,
 * done by the face host on the operator's click instead of by a shell turn).
 *
 * Same trust posture as data.ts: every request is fenced to a loopback `Host`
 * FIRST, the refused body is fixed text, and nothing attacker-controlled is
 * ever echoed. The POST reads a small JSON body; the strategy name is
 * validated against a closed character class before it touches a path, so the
 * routes cannot be steered outside `strategies/`.
 * @module
 */
import { cp, readFile, readdir, stat } from "node:fs/promises";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { RouteRegistrar } from "./static.ts";
import { isJsonBody, isTrustedDataRequest } from "./data.ts";
import { FORBIDDEN, HttpError, readBody } from "./http.ts";

/** A strategy name: lower-case, digits, `-`/`_`, must start alphanumeric.
 * A closed class — path separators, dots, and anything shell-meaningful are
 * unrepresentable, which is what lets the name touch a filesystem path. */
/** Exactly a strategy directory name: one path segment of letters and digits
 * in ANY script (a Chinese name is a name) plus `-` and `_`, 1–41 code
 * points, opening with a letter or digit — so `.`/`..`, dotfiles,
 * separators, spaces and control characters never reach a path. Names are
 * compared and created in NFC, so one word typed in two Unicode
 * normalizations is one directory, not two. */
const NAME_RE = /^[\p{L}\p{N}][\p{L}\p{N}\p{M}_-]{0,40}$/u;

/** The copy source every new strategy starts from, and never a valid pick. */
const TEMPLATE = "_template";

/** One row of the picker. */
export interface StrategyEntry {
  name: string;
  /** Absolute directory — the `cwd` the client hands to `session.create`. */
  cwd: string;
  /** The `status:` word from status.yaml, when the file has one. */
  status?: string;
}

/** List the strategy directories under `<root>/strategies`, template and
 * hidden names excluded, each with its declared lifecycle status.
 * @param root - absolute workbench repo root.
 */
export async function listStrategies(root: string): Promise<{ root: string; strategies: StrategyEntry[] }> {
  const dir = join(root, "strategies");
  const entries = await readdir(dir, { withFileTypes: true });
  const strategies: StrategyEntry[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    if (entry.name === TEMPLATE || entry.name.startsWith(".") || entry.name.startsWith("__")) continue;
    const cwd = join(dir, entry.name);
    let status: string | undefined;
    try {
      const text = await readFile(join(cwd, "status.yaml"), "utf8");
      status = /(?:^|\n)status:\s*(\S+)/.exec(text)?.[1];
    } catch { /* a strategy without status.yaml still lists — status is a badge, not a gate */ }
    strategies.push({ name: entry.name, cwd, status });
  }
  strategies.sort((a, b) => a.name.localeCompare(b.name));
  return { root, strategies };
}

/** Birth `strategies/<name>` from the template. Refuses a malformed name, a
 * name already taken, and a missing template — never overwrites anything.
 * @param root - absolute workbench repo root.
 * @param name - the new strategy's directory name; must match {@link NAME_RE}.
 */
export async function createStrategy(root: string, rawName: unknown): Promise<StrategyEntry> {
  const name = typeof rawName === "string" ? rawName.normalize("NFC") : rawName;
  if (typeof name !== "string" || !NAME_RE.test(name) || name === TEMPLATE) {
    throw new HttpError(400, "invalid strategy name (letters or digits in any script, plus - and _; no spaces, dots or slashes; up to 41 characters)");
  }
  const template = join(root, "strategies", TEMPLATE);
  try {
    await stat(template);
  } catch {
    throw new HttpError(500, "strategies/_template missing");
  }
  const target = join(root, "strategies", name);
  let exists = true;
  try {
    await stat(target);
  } catch {
    exists = false;
  }
  if (exists) throw new HttpError(409, "strategy already exists");
  await cp(template, target, {
    recursive: true,
    filter: (src) => !src.includes("__pycache__"),
  });
  return { name, cwd: target, status: "idea" };
}

/**
 * Mount the two strategy routes on the face's webserver.
 * @param webServer - the host webserver service, or a test recorder.
 * @param root - absolute workbench repo root the strategy tree lives under.
 */
export function registerStrategyRoutes(webServer: RouteRegistrar, root: string): void {
  const send = (res: ServerResponse, status: number, body: unknown): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(typeof body === "string" ? body : JSON.stringify(body));
  };

  webServer.register({
    kind: "exact",
    path: "/data/strategies.json",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      try {
        return send(res, 200, { ok: true, ...(await listStrategies(root)) });
      } catch {
        /* the reason stays on the server's stderr-free path: nothing from the
         * filesystem error reaches the body. */
        return send(res, 500, { ok: false, error: "listing failed" });
      }
    },
  });

  webServer.register({
    kind: "exact",
    path: "/data/strategies",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      if (req.method !== "POST") return send(res, 405, { ok: false, error: "POST only" });
      if (!isJsonBody(req)) return send(res, 415, { ok: false, error: "application/json only" });
      try {
        let name: unknown;
        try {
          name = (JSON.parse(await readBody(req)) as { name?: unknown }).name;
        } catch (err) {
          if (err instanceof HttpError) throw err;
          throw new HttpError(400, "body must be JSON: {\"name\": \"...\"}");
        }
        const entry = await createStrategy(root, name);
        return send(res, 200, { ok: true, ...entry });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        return send(res, 500, { ok: false, error: "create failed" });
      }
    },
  });
}
