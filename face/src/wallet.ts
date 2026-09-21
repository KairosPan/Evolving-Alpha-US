/** The agent wallet on the face: the eight `wallet_*` tools, `/data/wallet.json`,
 * and the two seams the channel and plugin panels read spend and tool names
 * through (spec `docs/superpowers/specs/2026-09-20-agent-wallet-design.md` §4.2).
 *
 * The substrate is agentpay (`payment/`, the submodule), imported by relative
 * path with the `.ts` extension the way the spec verified typechecks and loads
 * — provided `payment/node_modules` is installed (`(cd payment && npm ci)`).
 * agentpay owns the money: the mandate store, the ledger, the policy gate, the
 * x402 client, the tool table (`pay:packages/cli/src/tools.ts`) and its
 * handlers. This module owns what only the face can know:
 *
 * - WHO is calling. `execute(args, exec)` receives the calling agent, and the
 *   caller class is read off ITS session by the one rule Gate 3 uses
 *   (`budgets.ts` `requesterOf` + `classifyRequester`, spec §3): a bot has no
 *   wallet, a child may spend only what its parent delegated, and the
 *   principal-only tools refuse a child before agentpay is asked anything.
 *   Attribution is a fact the face reads, never a claim in the arguments
 *   (decision 4): the ledger row's `context` is built here from the header
 *   and `channelFor(cwd)`.
 * - WHERE a request may go. The charter disabled `tool-web`'s fetch on purpose
 *   (DEVELOPMENT §3.6); `wallet_offer`/`wallet_pay` are an HTTP client inside
 *   the face, so a loopback, link-local, private-range or `.local` host is
 *   refused before any request (decision 9, R-W7), and agentpay's
 *   `requireMandateHost` refuses every host no held mandate names.
 * - ONE process on the home. The wallet takes `wallet.lock` (decision 10); a
 *   home another live pid holds is reported, not fought over.
 *
 * Nothing here awaits before the tools are registered: `installWallet` is
 * synchronous through registration so the tools are in the tree before any
 * session (§4.2). Every promise the module does not await is caught — main.ts
 * turns an unhandled rejection into a shutdown.
 * @module
 */
import { existsSync, readFileSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import {
  CommandContext, ConfigError, PRINCIPAL, WALLET_TOOLS, createWalletToolHandlers, failure, readStoredConfig, resolveConfig,
  type Caller, type CliResult, type PaymentContext, type WalletTool, type WalletToolHandler,
} from "../../payment/packages/cli/src/index.ts";
import { lockedBy, type LedgerEntry, type MandateWallet } from "../../payment/packages/wallet/src/index.ts";
import { PolicyViolation } from "../../payment/packages/core/src/index.ts";
import { classifyRequester, requesterOf } from "./budgets.ts";
import type { ChannelRow } from "./channels.ts";
import { isTrustedDataRequest } from "./data.ts";
import { FORBIDDEN, HttpError } from "./http.ts";
import type { RouteRegistrar } from "./static.ts";
import {
  buildWalletPayload, channelSpend, nextFaceState,
  type BalanceReading, type FaceState, type LedgerRowLike, type WalletPayloadInput,
} from "./wallet-payload.ts";

const BIN = "kairos-face";

/* ---------- what the wallet reads of the tree, stated structurally ---------- */

/** dsh-tools' `ToolRunContext`, narrowed: the calling agent (whose session
 * header the caller rule reads) and the call id the ledger row records. */
export interface WalletToolExec {
  agent?: { id: string; session: unknown };
  callId?: unknown;
  signal?: AbortSignal;
}

/** dsh-tools' `ToolDefinition`, stated the way `room.ts` states it, plus the
 * two presentation hooks the pay card needs: a `fetch`/`read`/`other` kind
 * on the pending card (the tool table's own `kind`) and a result title. Not
 * `agents.ts`'s `AgentToolDefinition`, whose `kind` is fixed at `read`. */
export interface WalletToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  output: { schema: Record<string, unknown>; render(args: unknown, value: unknown): { type: "text"; text: string }[] };
  timeoutMs: number;
  execute(args: unknown, exec: WalletToolExec): Promise<unknown>;
  presentCall(args: unknown): { card: "generic"; title: string; kind: "fetch" | "read" | "other" };
  presentResult(args: unknown, result: { content: { type: string; text?: string }[]; isError: boolean }): { card: "generic"; title?: string } | undefined;
}

/** The root context, narrowed to the one registry the wallet writes to. */
export interface WalletContextLike {
  tools: { register(definition: WalletToolDefinition): () => void };
}

export interface WalletDeps {
  ctx: WalletContextLike;
  /** The harness home; the wallet home is `<home>/face/agentpay` unless `FACE_AGENTPAY_HOME` says otherwise. */
  home: string;
  /** Which channel a session's directory belongs to (panels.ts `channelFor`). */
  channelFor(cwd: string | undefined): Promise<{ workspaceId: string; name: string } | null>;
  log?: (line: string) => void;
  /** Injectable clock (unix milliseconds), for the tests. */
  now?: () => number;
}

/** What `installWallet` hands back, configured or not. */
export interface WalletInstall {
  configured: boolean;
  /** Why the wallet is not configured, in the words the page shows. */
  reason?: string;
  /** The wallet home that was (or would have been) used. */
  home: string;
  /** The registered tools by name and description, for the plugin panel; `[]` when not configured. */
  walletTools: { name: string; description: string }[];
  /** One channel's settled total, for the landing page's tile; `undefined` when not configured. */
  spendFor?: (channel: Pick<ChannelRow, "workspaceId">) => Promise<{ settled_usd: string; count: number } | null>;
  /** Mount `GET /data/wallet.json`. */
  registerRoutes(webServer: RouteRegistrar): void;
  /** Unregister the tools and release the lock. */
  dispose(): void;
}

/** The wallet home: `FACE_AGENTPAY_HOME` (`||`, the face's convention: an
 * empty export means "the default"), else the face's metadata directory in
 * the harness home (decision 7). */
export function walletHomeOf(dshHome: string, env: NodeJS.ProcessEnv = process.env): string {
  return env.FACE_AGENTPAY_HOME || join(dshHome, "face", "agentpay");
}

/* ---------- the private-host refusal (decision 9) ---------- */

/** The local chain: its payees are local by definition (spec §8's drill pays
 * `127.0.0.1:4021`), so the private-host refusal is lifted for it and for it
 * only. On any other network a private host is refused outright. */
export const LOCAL_NETWORK = "eip155:31337";

/**
 * Whether a URL's host is one the wallet must never be sent to: loopback
 * (127/8, `::1`, `localhost`), link-local (169.254/16, fe80::/10), RFC 1918
 * (10/8, 172.16/12, 192.168/16), IPv6 unique-local (fc00::/7 — RFC 1918's
 * twin), "this host" (0/8, `::`) and `*.local` (mDNS). An IPv4-mapped IPv6 address (`::ffff:a.b.c.d`)
 * is judged by its IPv4 half. Fail CLOSED on anything unparsable: a URL the
 * parser cannot read is not one to send.
 * @param url - the model's `url` argument.
 * @returns true when the host is private and the request must not leave.
 */
export function isPrivateHost(url: string): boolean {
  let hostname: string;
  try {
    hostname = new URL(url).hostname.toLowerCase();
  } catch {
    return true;
  }
  if (hostname === "" || hostname === "localhost" || hostname.endsWith(".localhost") || hostname.endsWith(".local")) return true;
  if (hostname.startsWith("[") && hostname.endsWith("]")) hostname = hostname.slice(1, -1);
  if (hostname.includes(":")) {
    /* WHATWG serializes a mapped address as two hextets (`::ffff:a00:1` for
     * 10.0.0.1), so the dotted form is only seen from a caller that bypassed
     * the parser; both are read back to IPv4 and judged there. */
    const dotted = /^::ffff:(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})$/.exec(hostname);
    if (dotted !== null) return isPrivateV4(dotted[1]);
    const hex = /^::ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/.exec(hostname);
    if (hex !== null) {
      const hi = Number.parseInt(hex[1], 16);
      const lo = Number.parseInt(hex[2], 16);
      return isPrivateV4(`${hi >> 8}.${hi & 255}.${lo >> 8}.${lo & 255}`);
    }
    if (hostname === "::1" || hostname === "::") return true;
    const head = hostname.split(":")[0];
    if (head === "") return false; // `::` prefixed public ranges (none private past the two above)
    const first = Number.parseInt(head.padStart(4, "0"), 16);
    if (Number.isNaN(first)) return true;
    return (first & 0xffc0) === 0xfe80 || (first & 0xfe00) === 0xfc00;
  }
  return isPrivateV4(hostname);
}

function isPrivateV4(hostname: string): boolean {
  const parts = hostname.split(".");
  if (parts.length !== 4 || !parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255)) return false;
  const [a, b] = parts.map(Number);
  return a === 127 || a === 10 || a === 0
    || (a === 169 && b === 254)
    || (a === 172 && b >= 16 && b <= 31)
    || (a === 192 && b === 168);
}

/**
 * The fetch the wallet is given: `globalThis.fetch` that never follows a
 * redirect. Both of the face's host rules ({@link isPrivateHost} and agentpay's
 * `requireMandateHost` pre-flight) judge the URL the model named; a 3xx from
 * that host would carry the request — and, on the retry, the signed payment
 * header — to a host neither rule saw (a public payee answering
 * `Location: http://169.254.169.254/…` is the SSRF `tool-web`'s fetch was
 * disabled for). So a redirect is a refusal in the same envelope, not a hop.
 * @param base - the fetch to wrap (`globalThis.fetch` in the face; a stub in the tests).
 */
export function noRedirectFetch(base: typeof globalThis.fetch): typeof globalThis.fetch {
  return async (input, init) => {
    const response = await base(input, { ...init, redirect: "manual" });
    if (response.status >= 300 && response.status < 400) {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      let host = "?";
      try {
        host = new URL(url).host;
      } catch { /* the hint says so */ }
      const location = response.headers.get("location") ?? "";
      throw new PolicyViolation("host_not_allowed", { host, url, status: response.status, location }, {
        protocol: "x402",
        reason: "host_not_allowed",
        summary: `host ${JSON.stringify(host)} answered ${response.status} with a redirect to ${JSON.stringify(location)}; the wallet never follows a redirect, because the host it lands on is not the one the budget and the face checked.`,
        remediation: ["Call the resource at its final URL, if a budget names that host."],
      });
    }
    return response;
  };
}

/** The refusal as the model reads it: agentpay's own `host_not_allowed`
 * envelope with a hint that says WHY in the face's words, produced through
 * the CLI's `failure()` so the shape is the one every other refusal has. */
export function privateHostRefusal(name: string, url: string): Record<string, unknown> {
  let host = "?";
  try {
    host = new URL(url).host;
  } catch { /* unparsable: the hint says so below */ }
  const violation = new PolicyViolation("host_not_allowed", { host, url }, {
    protocol: "x402",
    reason: "host_not_allowed",
    summary: `${name}: host ${JSON.stringify(host)} is a loopback, link-local, private-range or .local address; the face never sends a wallet request there.`,
    remediation: ["Pay a public host that a budget names. This refusal is the face's, not the budget's; requesting a budget for this host will not lift it."],
  });
  return { ...(failure(violation).output as Record<string, unknown>), url, host };
}

/* ---------- the caller rule (spec §3) ---------- */

/** The caller agentpay sees, or the refusal (an `Error` the tool THROWS, so
 * the model reads an error result in the face's words) for a class this tool
 * does not serve. `null` agent → an error too: with nobody to attribute to,
 * nothing is paid. */
export function callerOf(tool: Pick<WalletTool, "name" | "principalOnly">, exec: WalletToolExec): { caller: Caller; parentSession?: string; origin?: string; cwd?: string } {
  const agent = exec.agent;
  if (agent === undefined) throw new Error(`${tool.name} needs a session to run in`);
  const requester = requesterOf(agent.session);
  const who = classifyRequester(requester);
  if (who === "bot") {
    throw new Error(
      `${tool.name} is Kairos's tool: a bot voice (preset "${requester.agentPreset}") has no wallet. ` +
      `Say what the resource costs in your answer; Kairos decides whether to pay.`,
    );
  }
  if (who === "child" && tool.principalOnly) {
    throw new Error(
      `${tool.name} is the principal's tool: a child task (origin "subagent") cannot call it. ` +
      `Ask the parent session to delegate a sub-budget with wallet_budget_delegate and pay from that.`,
    );
  }
  const header = (agent.session as { header?: { cwd?: unknown } } | undefined)?.header;
  const cwd = typeof header?.cwd === "string" ? header.cwd : undefined;
  const caller: Caller = who === "principal"
    ? PRINCIPAL
    : { kind: "child", id: agent.id, ...(requester.parentSession !== undefined ? { parentSession: requester.parentSession } : {}) };
  return { caller, parentSession: requester.parentSession, origin: requester.origin, cwd };
}

/* ---------- presentation ---------- */

const argsOf = (args: unknown): Record<string, unknown> =>
  args !== null && typeof args === "object" && !Array.isArray(args) ? args as Record<string, unknown> : {};

/** The pending card's title: the tool, and for a fetch the method and target. */
export function callTitle(tool: Pick<WalletTool, "name" | "kind">, args: unknown): string {
  const a = argsOf(args);
  if (tool.kind === "fetch" && typeof a.url === "string") {
    let target = a.url;
    try {
      const u = new URL(a.url);
      target = `${u.host}${u.pathname}`;
    } catch { /* shown as typed */ }
    const method = typeof a.method === "string" ? a.method.toUpperCase() : a.body !== undefined ? "POST" : "GET";
    return `${tool.name} ${method} ${target}`;
  }
  if (tool.name === "wallet_budget_request" && typeof a.purpose === "string") return `${tool.name} "${a.purpose.slice(0, 60)}"`;
  if (tool.name === "wallet_budget_delegate" && typeof a.limit_usd === "string") return `${tool.name} $${a.limit_usd}`;
  if (tool.name === "wallet_budget_disable" && typeof a.id === "string") return `${tool.name} ${a.id}`;
  return tool.name;
}

/** The completed card's title, from the envelope: `$0.001 · settled` for a
 * payment, `refused · <reason>` for any `ok:false`, the id for a new budget.
 * `undefined` keeps the pending title (the tool errored, or the value is not
 * an envelope). */
export function resultTitle(tool: Pick<WalletTool, "name">, value: unknown): string | undefined {
  const v = argsOf(value);
  if (v.ok === false) return `refused · ${typeof v.error === "string" ? v.error : "?"}`;
  if (v.ok !== true) return undefined;
  switch (tool.name) {
    case "wallet_pay":
      return v.paid === true
        ? `$${String(v.amount_usd)} · ${String(v.ledger_status)}${typeof v.host === "string" ? ` · ${v.host}` : ""}`
        : `${String(v.status)} · unpaid${typeof v.host === "string" ? ` · ${v.host}` : ""}`;
    case "wallet_offer": {
      const offer = Array.isArray(v.offer) ? v.offer[0] as { amount_usd?: unknown } | undefined : undefined;
      return v.status === 402 ? `402 · $${String(offer?.amount_usd ?? "?")}` : `${String(v.status)} · not a paid resource`;
    }
    case "wallet_budget_request":
    case "wallet_budget_delegate": {
      const m = argsOf(v.mandate);
      return `budget ${String(m.id)} · $${String(m.limit_usd)}`;
    }
    case "wallet_budget_disable":
      return `${String(v.id)} · disabled`;
    case "wallet_budgets":
      return `${Array.isArray(v.mandates) ? v.mandates.length : 0} budget${Array.isArray(v.mandates) && v.mandates.length === 1 ? "" : "s"}`;
    case "wallet_reconcile":
      return `reconciled · ${String(v.settled)} settled, ${String(v.still_pending)} pending`;
    default:
      return `${tool.name} · ok`;
  }
}

/* ---------- install ---------- */

/** How long one balance reading is served (a page refresh is not an RPC
 * call), and how long the RPC gets before the page says `unavailable`. */
export const BALANCE_TTL_MS = 60_000;
export const BALANCE_TIMEOUT_MS = 3_000;
/** How often loading the page may run `reconcile()` (spec §2: at most once a minute). */
export const RECONCILE_MIN_INTERVAL_MS = 60_000;

const FACE_STATE = "face-state.json";

/**
 * Register the wallet tools on the root context, or report why not.
 * Synchronous through registration (§4.2): the tools are in the tree before
 * this returns. What can fail here fails into `{configured: false, reason}`
 * and one logged line, never a throw — an unconfigured wallet is a state the
 * face runs in, not an error.
 * @param deps - the tree, the harness home, the channel lookup, a logger.
 */
export function installWallet(deps: WalletDeps): WalletInstall {
  const log = deps.log ?? ((line: string) => console.log(`${BIN}: ${line}`));
  const now = deps.now ?? Date.now;
  const home = walletHomeOf(deps.home);

  const notConfigured = (reason: string): WalletInstall => {
    log(`wallet: not configured (${reason})`);
    return {
      configured: false, reason, home, walletTools: [],
      registerRoutes: (webServer) => registerWalletRoute(webServer, () => ({ configured: false, reason, home })),
      dispose: () => {},
    };
  };

  if (!existsSync(join(home, "config.json"))) return notConfigured(`no config.json at ${home}`);
  let ctx: CommandContext;
  let wallet: MandateWallet;
  try {
    /* An EMPTY env: the shell's `AGENTPAY_*` (a CLI session's key, RPC or
     * home) must never redirect the face's wallet — the face's home is the
     * config.json in it, and nothing else. */
    const config = resolveConfig({ home }, {});
    const holder = lockedBy(dirname(config.mandatesPath));
    /* Any LIVE holder, this process included: a second install on one home
     * (two faces, or one face installing twice) is the clobbering decision 10
     * exists to refuse. A dead pid's lock is removed by `lockedBy` itself. */
    if (holder !== undefined) return notConfigured(`locked by pid ${holder}`);
    ctx = new CommandContext(config, noRedirectFetch(globalThis.fetch), (line) => log(`agentpay: ${line}`), { lock: true, requireMandateHost: true });
    wallet = ctx.wallet(); // eager: the store is read, the lock taken, the key required, here and not on first call
  } catch (err) {
    return notConfigured(err instanceof ConfigError ? err.message : err instanceof Error ? err.message : String(err));
  }
  const network = ctx.config.network;
  const handle: WalletToolHandler = createWalletToolHandlers(ctx);
  const unverified = new Set<string>();

  const definitions = WALLET_TOOLS.map((tool) => walletToolDefinition(tool, {
    handle, network, channelFor: deps.channelFor,
  }));
  const unregisters = definitions.map((definition) => deps.ctx.tools.register(definition));

  /* Once, after registration (§4.1 "Lock and verification"): a mandate whose
   * signature does not recover to the payer is disabled and named on the
   * page. Async because viem's recovery is; both handlers, so the promise can
   * never reject unobserved. */
  void wallet.verifyMandates().then((ids) => {
    for (const id of ids) {
      unverified.add(id);
      try {
        wallet.setEnabled(id, false);
      } catch (err) {
        log(`wallet: could not disable unverified mandate ${id}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
    if (ids.length > 0) log(`wallet: ${ids.length} mandate(s) did not verify and were disabled: ${ids.join(", ")}`);
  }, (err: unknown) => log(`wallet: verifyMandates failed: ${err instanceof Error ? err.message : String(err)}`));

  /* The balance: single-flight, cached for a minute, three seconds on the
   * RPC. `then(clear, clear)` rather than `finally` — data.ts's lesson: a
   * `finally` on a rejecting promise derives a second rejected promise nobody
   * awaits, and main.ts shuts the face down on one. */
  let balanceCache: { reading: BalanceReading; at: number } | undefined;
  let balanceFlight: Promise<BalanceReading> | undefined;
  const readBalance = (): Promise<BalanceReading> => {
    if (balanceCache !== undefined && now() - balanceCache.at < BALANCE_TTL_MS) return Promise.resolve(balanceCache.reading);
    if (balanceFlight !== undefined) return balanceFlight;
    const flight = (async (): Promise<BalanceReading> => {
      if (!ctx.config.rpcUrl) return { unavailable: "no RPC configured" };
      let timer: NodeJS.Timeout | undefined;
      try {
        const atomic = await Promise.race([
          wallet.balance(),
          new Promise<never>((_, reject) => {
            timer = setTimeout(() => reject(new Error(`RPC did not answer within ${BALANCE_TIMEOUT_MS} ms`)), BALANCE_TIMEOUT_MS);
          }),
        ]);
        /* The ledger's settled total is read AFTER the chain answered, and
         * kept with the reading: the outflow check compares a balance with
         * the ledger as of that same moment. A cached reading paired with a
         * later ledger would read every payment settled in the minute since
         * as an unexplained outflow at the next fresh read. */
        return { atomic, at: now(), ledgerSpent: String(wallet.report().totals.spent) };
      } catch (err) {
        return { unavailable: (err instanceof Error ? err.message : String(err)).split("\n")[0] ?? "RPC failed" };
      } finally {
        if (timer !== undefined) clearTimeout(timer);
      }
    })();
    balanceFlight = flight;
    const clear = (): void => void (balanceFlight = undefined);
    void flight.then((reading) => { balanceCache = { reading, at: now() }; clear(); }, clear);
    return flight;
  };

  /* Reconcile on load (spec §2): only when something is unsettled, only with
   * an RPC, at most once a minute, and its failure is a field on the page,
   * never a throw out of the route. */
  let lastReconcileAt: number | undefined;
  const reconcileOnLoad = async (rows: readonly LedgerEntry[]): Promise<WalletPayloadInput["reconcile"]> => {
    if (!ctx.config.rpcUrl || !rows.some((row) => row.status === "rejected" || row.status === "unknown")) return undefined;
    if (lastReconcileAt !== undefined && now() - lastReconcileAt < RECONCILE_MIN_INTERVAL_MS) return undefined;
    lastReconcileAt = now();
    const at = new Date(now()).toISOString();
    try {
      const result = await wallet.reconcile();
      return { at, settled: result.settled.length, expired_unused: result.expiredUnused.length, still_pending: result.stillPending.length };
    } catch (err) {
      return { at, settled: 0, expired_unused: 0, still_pending: 0, error: (err instanceof Error ? err.message : String(err)).split("\n")[0] };
    }
  };

  const readState = (): FaceState => {
    try {
      const parsed: unknown = JSON.parse(readFileSync(join(home, FACE_STATE), "utf8"));
      if (parsed === null || typeof parsed !== "object") return {};
      const { last_balance, ledger_settled_at_that_time } = parsed as Record<string, unknown>;
      return {
        ...(typeof last_balance === "string" ? { last_balance } : {}),
        ...(typeof ledger_settled_at_that_time === "string" ? { ledger_settled_at_that_time } : {}),
      };
    } catch {
      return {};
    }
  };

  const ledgerRows = (): LedgerEntry[] => ctx.ledger().read();

  const payload = async (): Promise<Record<string, unknown>> => {
    const rows = ledgerRows();
    const [balance, reconcile] = await Promise.all([readBalance(), reconcileOnLoad(rows)]);
    const input: WalletPayloadInput = {
      home, address: wallet.address, network, token: ctx.config.token, deployment: readStoredConfig(home).deployment,
      report: wallet.report(),
      mandates: wallet.listMandates(),
      remaining: (id) => wallet.effectiveRemaining(id),
      rows: (reconcile === undefined ? rows : ledgerRows()) as LedgerRowLike[],
      balance, unverified, state: readState(), reconcile, now: now(),
    };
    const body = buildWalletPayload(input);
    const next = nextFaceState(input);
    if (next !== undefined) {
      /* Awaited so a read-after-write from the next look sees it; a failure
       * costs the next outflow check its anchor, not the page. */
      try {
        await mkdir(home, { recursive: true });
        await writeFile(join(home, FACE_STATE), JSON.stringify(next), "utf8");
      } catch (err) {
        log(`wallet: could not write ${FACE_STATE}: ${err instanceof Error ? err.message : String(err)}`);
      }
    }
    return body;
  };

  log(`wallet: ${definitions.length} tools registered, home ${home} (${network}, ${wallet.address})`);
  return {
    configured: true,
    home,
    walletTools: WALLET_TOOLS.map((tool) => ({ name: tool.name, description: tool.description })),
    spendFor: async (channel) => {
      try {
        return channelSpend(ledgerRows() as LedgerRowLike[], channel.workspaceId);
      } catch (err) {
        log(`wallet: spendFor could not read the ledger: ${err instanceof Error ? err.message : String(err)}`);
        return null;
      }
    },
    registerRoutes: (webServer) => registerWalletRoute(webServer, payload),
    dispose: () => {
      for (const unregister of unregisters) unregister();
      ctx.dispose();
    },
  };
}

/** `GET /data/wallet.json`, in panels.ts's GET shell: the same-origin fence
 * first, then `{ok: true, ...body}`, errors mapped like `/data`'s. */
function registerWalletRoute(webServer: RouteRegistrar, read: () => Promise<object> | object): void {
  const send = (res: ServerResponse, status: number, body: unknown): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
    res.end(JSON.stringify(body));
  };
  webServer.register({
    kind: "exact",
    path: "/data/wallet.json",
    handler: async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
      if (!isTrustedDataRequest(req)) return send(res, 403, FORBIDDEN);
      try {
        return send(res, 200, { ok: true, ...(await read()) });
      } catch (err) {
        if (err instanceof HttpError) return send(res, err.status, { ok: false, error: err.message });
        /* Fixed text: a store error names file paths and a chain error names
         * the RPC; neither belongs in a browser payload. */
        console.error(`${BIN}: /data/wallet.json failed:`, err);
        return send(res, 500, { ok: false, error: "request failed" });
      }
    },
  });
}

/** What one tool definition needs of the install: the handler, the network
 * (for the local-chain exemption) and the channel lookup. */
interface ToolWiring {
  handle: WalletToolHandler;
  network: string;
  channelFor: WalletDeps["channelFor"];
}

/**
 * One `wallet_*` tool as dsh registers it. `execute` is the whole of the
 * face's contribution to a call, in order: the caller rule (throws for a
 * class the tool refuses), the context from the header and the channel, the
 * private-host refusal for the two fetch tools, then agentpay's handler —
 * whose envelope is the tool's value whether `ok` is true or false, because
 * a refusal carries the hints the model needs (decision 3). Anything
 * unexpected past the caller rule becomes the CLI's failure envelope too, so
 * a throw the model cannot act on never reaches it as a bare error.
 */
export function walletToolDefinition(tool: WalletTool, wiring: ToolWiring): WalletToolDefinition {
  return {
    name: tool.name,
    description: tool.description,
    parameters: tool.parameters,
    /* An empty schema (annotation-only): the envelopes are agentpay's and
     * vary by tool and outcome; the client renders the JSON text. */
    output: { schema: {}, render: (_args, value) => [{ type: "text", text: JSON.stringify(value) }] },
    timeoutMs: 60_000,
    async execute(args, exec) {
      const { caller, parentSession, origin, cwd } = callerOf(tool, exec);
      const agent = exec.agent as NonNullable<WalletToolExec["agent"]>;
      try {
        const channel = await wiring.channelFor(cwd);
        const context: PaymentContext = {
          ...(channel !== null ? { channel: channel.workspaceId, channelName: channel.name } : {}),
          session: agent.id,
          ...(parentSession !== undefined ? { parentSession } : {}),
          ...(origin !== undefined ? { origin } : {}),
          ...(typeof exec.callId === "string" ? { callId: exec.callId } : {}),
        };
        if (tool.kind === "fetch") {
          const url = argsOf(args).url;
          /* Before agentpay sees the URL: the local chain's payees are local
           * (LOCAL_NETWORK); on every other network a private host never
           * gets a request, whatever mandate names it. */
          if (typeof url === "string" && wiring.network !== LOCAL_NETWORK && isPrivateHost(url)) {
            return privateHostRefusal(tool.name, url);
          }
        }
        const result: CliResult = await wiring.handle(tool.name, args, { context, caller, requesterSession: agent.id });
        return result.output;
      } catch (err) {
        return failure(err).output;
      }
    },
    presentCall: (args) => ({ card: "generic", title: callTitle(tool, args), kind: tool.kind }),
    presentResult(_args, result) {
      if (result.isError) return undefined;
      const text = result.content.find((block) => typeof block.text === "string")?.text;
      if (text === undefined) return undefined;
      let value: unknown;
      try {
        value = JSON.parse(text);
      } catch {
        return undefined;
      }
      const title = resultTitle(tool, value);
      return title === undefined ? undefined : { card: "generic", title };
    },
  };
}
