/** The wallet on the face, offline: the tool definitions over a real
 * agentpay `CommandContext` on a temp home, paying an in-process stub payee
 * (the wallet package's own `stub-payee.ts`: the real paywall on express over
 * a stub facilitator, no chain). What this proves is the FACE's contribution
 * to a call — the caller rule, the context derived from the session header,
 * the private-host refusal, holder routing, the envelopes coming back as
 * values — and the page's payload over the same home. The chain path
 * (balance, reconcile) is exercised against a closed port, so its failures
 * must show as fields, never as a rejection nobody caught.
 *
 * Network `eip155:31337` throughout, because the stub payee is on loopback
 * and only the local chain lifts the private-host refusal (`LOCAL_NETWORK`);
 * one home on `eip155:84532` proves the refusal holds everywhere else.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { WebRoute } from "@deepseek-ai/dsh-host-webserver";
import { MOCK_USDC_DOMAIN } from "../../payment/packages/contracts/src/index.ts";
import { writeStoredConfig } from "../../payment/packages/cli/src/index.ts";
import { PolicyViolation } from "../../payment/packages/core/src/index.ts";
import { accounts } from "../../payment/packages/payee/test/helpers.ts";
import { KEYS, startStubPayee, type StubPayee } from "../../payment/packages/wallet/test/stub-payee.ts";
import {
  BALANCE_TTL_MS, callTitle, installWallet, isPrivateHost, noRedirectFetch, resultTitle, walletHomeOf,
  type WalletInstall, type WalletToolDefinition, type WalletToolExec,
} from "../src/wallet.ts";
import { alertsOf, buildWalletPayload, channelSpend, nextFaceState, spendOf, usd } from "../src/wallet-payload.ts";

/* Hardhat's public dev accounts (never real funds), the same ones the wallet
 * suites use; the token address is MockUSDC's deterministic local deploy. */
const TOKEN = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";
const payeeAddress = accounts.payee.address;
const facilitatorAddress = accounts.facilitator.address;
/** Nothing listens here: balance and reconcile must degrade, never throw. */
const CLOSED_RPC = "http://127.0.0.1:1";

const WS = "5b0b3c2a-1111-4222-8333-444455556666";
const CHANNEL_DIR = "/repo/strategies/alpha";
const channelFor = async (cwd: string | undefined) => (cwd === CHANNEL_DIR ? { workspaceId: WS, name: "alpha" } : null);

type Out = Record<string, any>;

/** A fake root context whose `tools.register` records the definitions. */
function fakeCtx(): { ctx: { tools: { register(d: WalletToolDefinition): () => void } }; tools: Map<string, WalletToolDefinition> } {
  const tools = new Map<string, WalletToolDefinition>();
  return {
    tools,
    ctx: { tools: { register: (d) => { tools.set(d.name, d); return () => { tools.delete(d.name); }; } } },
  };
}

/** One call as dsh hands it to `execute`: the agent whose session HEADER the
 * caller rule reads. `agentPreset` unset is the principal (the dispatch rule). */
function exec(id: string, header: Record<string, unknown> = {}, callId = `call-${id}`): WalletToolExec {
  return { agent: { id, session: { header: { cwd: CHANNEL_DIR, ...header }, events: [] } }, callId };
}

function fakeRes(): { out: { status: number; body: string }; res: ServerResponse } {
  const out = { status: 0, body: "" };
  const res = {
    writeHead(status: number) { out.status = status; return res; },
    end(body?: string | Buffer) { out.body = String(body ?? ""); return res; },
  };
  return { out, res: res as unknown as ServerResponse };
}
const getReq = (host?: string): IncomingMessage => ({ headers: host === undefined ? {} : { host }, method: "GET" } as unknown as IncomingMessage);

function routeOf(wallet: WalletInstall): WebRoute {
  const routes: WebRoute[] = [];
  wallet.registerRoutes({ register: (route) => routes.push(route) });
  assert.deepEqual(routes.map((r) => r.path), ["/data/wallet.json"]);
  return routes[0];
}

async function page(wallet: WalletInstall): Promise<Out> {
  const { out, res } = fakeRes();
  await routeOf(wallet).handler(getReq("127.0.0.1:3090"), res);
  assert.equal(out.status, 200, out.body);
  return JSON.parse(out.body) as Out;
}

function configure(home: string, network: string): void {
  writeStoredConfig(home, { key: KEYS.payer, token: TOKEN, tokenDomain: { ...MOCK_USDC_DOMAIN }, network, rpcUrl: CLOSED_RPC, deployment: "localhost" });
}

/* A rejection nobody handled anywhere in this file is the failure main.ts
 * shuts the face down on; every test below asserts none happened. */
const unhandled: unknown[] = [];
const onUnhandled = (reason: unknown): void => { unhandled.push(reason); };
process.on("unhandledRejection", onUnhandled);

test("wallet home: FACE_AGENTPAY_HOME, else <dshHome>/face/agentpay; an empty export is the default", () => {
  assert.equal(walletHomeOf("/h", {}), join("/h", "face", "agentpay"));
  assert.equal(walletHomeOf("/h", { FACE_AGENTPAY_HOME: "" }), join("/h", "face", "agentpay"));
  assert.equal(walletHomeOf("/h", { FACE_AGENTPAY_HOME: "/elsewhere" }), "/elsewhere");
});

test("private hosts: loopback, link-local, RFC 1918, unique-local, .local; public hosts pass; unparsable fails closed", () => {
  for (const url of [
    "http://127.0.0.1:4021/predict", "http://127.9.9.9/", "http://localhost/", "http://api.localhost/", "http://[::1]:80/",
    "http://169.254.169.254/latest", "http://[fe80::1]/", "http://10.0.0.1/", "http://172.16.0.1/", "http://172.31.255.255/",
    "http://192.168.1.1/", "http://[fd00::1]/", "http://printer.local/", "http://[::ffff:10.0.0.1]/", "http://0.0.0.0/", "not a url",
  ]) assert.equal(isPrivateHost(url), true, url);
  for (const url of ["https://api.example.com/predict", "http://172.32.0.1/", "http://8.8.8.8/", "http://[2606:4700::1111]/", "http://11.0.0.1/"]) {
    assert.equal(isPrivateHost(url), false, url);
  }
});

test("titles: the pending card names the tool and its target; the result card reads the envelope", () => {
  assert.equal(callTitle({ name: "wallet_pay", kind: "fetch" }, { url: "https://api.example.com/predict?x=1" }), "wallet_pay GET api.example.com/predict");
  assert.equal(callTitle({ name: "wallet_pay", kind: "fetch" }, { url: "https://api.example.com/analyze", body: "{}" }), "wallet_pay POST api.example.com/analyze");
  assert.equal(callTitle({ name: "wallet_budgets", kind: "read" }, {}), "wallet_budgets");
  assert.equal(callTitle({ name: "wallet_budget_request", kind: "other" }, { purpose: "quotes" }), 'wallet_budget_request "quotes"');
  assert.equal(resultTitle({ name: "wallet_pay" }, { ok: true, paid: true, amount_usd: "0.001000", ledger_status: "settled", host: "api.example.com" }), "$0.001000 · settled · api.example.com");
  assert.equal(resultTitle({ name: "wallet_pay" }, { ok: false, error: "mandate_insufficient_budget" }), "refused · mandate_insufficient_budget");
  assert.equal(resultTitle({ name: "wallet_budgets" }, { ok: false, error: "usage" }), "refused · usage");
  assert.equal(resultTitle({ name: "wallet_budget_request" }, { ok: true, mandate: { id: "im_1", limit_usd: "5.000000" } }), "budget im_1 · $5.000000");
  assert.equal(resultTitle({ name: "wallet_budgets" }, { ok: true, mandates: [{}, {}] }), "2 budgets");
  assert.equal(resultTitle({ name: "wallet_pay" }, "not an envelope"), undefined);
});

test("payload builders: usd strings, spend keyed by workspace id, every alert kind from the same inputs", () => {
  assert.equal(usd(0n), "0.000000");
  assert.equal(usd("1000"), "0.001000");
  assert.equal(usd(12_400_000n), "12.400000");
  assert.equal(usd(-5n), "-0.000005");
  assert.equal(usd("garbage"), "0.000000");
  const nowSec = 1_800_000_000;
  const now = nowSec * 1000;
  const mandates = [
    { id: "root", naturalLanguage: "p", limitAmount: "5000000", spentAmount: "4600000", pendingSpentAmount: "0", validFrom: nowSec - 10, validUntil: nowSec + 3600, status: "signed", isEnabled: true },
    { id: "kid", naturalLanguage: "k", parentId: "root", holder: "children:s1", limitAmount: "3000", spentAmount: "3000", pendingSpentAmount: "0", validFrom: nowSec - 10, validUntil: nowSec + 100_000, status: "signed", isEnabled: true },
    { id: "off", naturalLanguage: "o", limitAmount: "1", spentAmount: "0", pendingSpentAmount: "0", validFrom: nowSec - 10, validUntil: nowSec + 100_000, status: "signed", isEnabled: false },
  ];
  const remaining = (id: string): bigint => ({ root: 400_000n, kid: 0n, off: 1n }[id] ?? 0n);
  const rows = [
    { nonce: "0x1", timestamp: nowSec - 5, url: "https://a/x", host: "a", resource: "GET /x", amount: "1000", intentMandateId: "root", status: "settled", httpStatus: 200, context: { channel: WS, channelName: "alpha", session: "s1" } },
    { nonce: "0x2", timestamp: nowSec - 4, url: "https://a/y", host: "a", resource: "GET /y", amount: "2000", intentMandateId: "root", status: "unknown", httpStatus: 200, context: { channel: WS, session: "s2" } },
    { nonce: "0x3", timestamp: nowSec - 3, url: "https://a/z", host: "a", resource: "GET /z", amount: "4000", intentMandateId: "root", status: "settled", httpStatus: 200 },
    { nonce: "0x4", timestamp: nowSec - 2, url: "https://a/r", host: "a", resource: "GET /r", amount: "9000", intentMandateId: "root", status: "rejected", httpStatus: 402, error: "nope" },
  ];
  const report = { totals: { spent: "7000", pending: "0" } };
  const spend = spendOf(report, rows);
  assert.deepEqual(spend, {
    settled_usd: "0.007000", pending_usd: "0.000000",
    by_channel: { [WS]: { name: "alpha", usd: "0.003000" } },
    by_session: { s1: "0.001000", s2: "0.002000" },
    unattributed_usd: "0.004000",
  });
  assert.deepEqual(channelSpend(rows, WS), { settled_usd: "0.001000", count: 1 });
  assert.equal(channelSpend(rows, "nowhere"), null);

  const state = { last_balance: "10000000", ledger_settled_at_that_time: "1000" };
  const balance = { atomic: 9_000_000n, at: now };
  const alerts = alertsOf({ mandates, remaining, rows, balance, unverified: new Set(["off"]), state, report, now });
  assert.deepEqual(alerts.map((a) => [a.kind, a.mandate]), [
    ["budget_low", "root"], ["budget_exhausted", "kid"], ["unknown_rows", undefined], ["expiring", "root"],
    ["unexplained_outflow", undefined], ["unverified_mandate", "off"],
  ]);
  /* balance 9 < root remaining 0.4? no - so no balance_low; fell 1.000000, ledger settled 0.006000 more → outflow 0.994000 */
  assert.match(alerts.find((a) => a.kind === "unexplained_outflow")!.text, /0\.994000/);
  const low = alertsOf({ mandates, remaining, rows, balance: { atomic: 100n, at: now }, unverified: new Set(), state: {}, report, now });
  assert.ok(low.some((a) => a.kind === "balance_low"));
  const off = alertsOf({ mandates, remaining, rows, balance: { unavailable: "closed" }, unverified: new Set(), state, report, now });
  assert.ok(off.some((a) => a.kind === "rpc_unavailable"));
  assert.ok(!off.some((a) => a.kind === "unexplained_outflow"), "no balance, no outflow verdict");
  assert.deepEqual(nextFaceState({ balance, report }), { last_balance: "9000000", ledger_settled_at_that_time: "7000" });
  assert.equal(nextFaceState({ balance: { unavailable: "x" }, report }), undefined);
  /* A reading served from cache carries the ledger total of ITS moment: the
   * 0.006000 settled since is not an outflow, and the anchor written pairs
   * the cached balance with that same total, not with today's. */
  const cached = { atomic: 10_000_000n, at: now, ledgerSpent: "1000" };
  const paired = alertsOf({ mandates, remaining, rows, balance: cached, unverified: new Set(), state, report, now });
  assert.ok(!paired.some((a) => a.kind === "unexplained_outflow"), "a stale reading is not an outflow");
  assert.deepEqual(nextFaceState({ balance: cached, report }), { last_balance: "10000000", ledger_settled_at_that_time: "1000" });

  const body = buildWalletPayload({ home: "/h", address: "0xabc", network: "eip155:31337", token: TOKEN, report, mandates, remaining, rows, balance, unverified: new Set(["off"]), state, now });
  assert.equal(body.configured, true);
  assert.deepEqual((body.payments as Out[]).map((p) => p.nonce), ["0x4", "0x3", "0x2", "0x1"], "newest first");
  assert.deepEqual((body.payments as Out[])[3].context, { channel: WS, channelName: "alpha", session: "s1" });
  assert.equal((body.mandates as Out[])[2].unverified, true);
  assert.equal((body.mandates as Out[])[0].remaining_usd, "0.400000");
  assert.doesNotMatch(JSON.stringify(body), /"signature"|mandateHash|0x59c6995e/, "never signing material");
});

test("installWallet: no config.json → nothing registered, the page says why, dispose is a no-op", async () => {
  const dshHome = mkdtempSync(join(tmpdir(), "face-wallet-none-"));
  const lines: string[] = [];
  const { ctx, tools } = fakeCtx();
  const wallet = installWallet({ ctx, home: dshHome, channelFor, log: (l) => lines.push(l) });
  assert.equal(wallet.configured, false);
  assert.match(wallet.reason ?? "", /no config\.json at /);
  assert.equal(wallet.home, join(dshHome, "face", "agentpay"));
  assert.equal(tools.size, 0);
  assert.deepEqual(wallet.walletTools, []);
  assert.equal(wallet.spendFor, undefined);
  assert.equal(lines.length, 1);
  assert.match(lines[0], /wallet: not configured \(no config\.json at /);
  const body = await page(wallet);
  assert.deepEqual(body, { ok: true, configured: false, reason: wallet.reason, home: wallet.home });
  const forged = fakeRes();
  await routeOf(wallet).handler(getReq("evil.example.com"), forged.res);
  assert.equal(forged.out.status, 403);
  wallet.dispose();
  rmSync(dshHome, { recursive: true, force: true });
});

test("installWallet: a config.json resolveConfig refuses is not configured, with its message; the shell's AGENTPAY_* are not consulted", () => {
  const dshHome = mkdtempSync(join(tmpdir(), "face-wallet-bad-"));
  const home = join(dshHome, "face", "agentpay");
  writeStoredConfig(home, { key: "0xnot-a-key", token: TOKEN, tokenDomain: { ...MOCK_USDC_DOMAIN }, network: "eip155:31337" });
  const before = process.env.AGENTPAY_KEY;
  process.env.AGENTPAY_KEY = KEYS.payer; // would rescue the key if the shell env were read
  try {
    const { ctx, tools } = fakeCtx();
    const wallet = installWallet({ ctx, home: dshHome, channelFor, log: () => {} });
    assert.equal(wallet.configured, false);
    assert.match(wallet.reason ?? "", /key must be a 0x-prefixed/);
    assert.equal(tools.size, 0);
  } finally {
    if (before === undefined) delete process.env.AGENTPAY_KEY; else process.env.AGENTPAY_KEY = before;
    rmSync(dshHome, { recursive: true, force: true });
  }
});

test("installWallet on a stub payee: eight tools, the caller rule, context from the header, holders, the page, spendFor, the lock", async () => {
  const dshHome = mkdtempSync(join(tmpdir(), "face-wallet-"));
  const home = join(dshHome, "face", "agentpay");
  const payee: StubPayee = await startStubPayee({ payTo: payeeAddress, token: TOKEN, assetDomain: { ...MOCK_USDC_DOMAIN }, network: "eip155:31337", price: "$0.001", facilitatorAddress });
  const stubHost = new URL(payee.url).host;
  configure(home, "eip155:31337");
  const lines: string[] = [];
  const { ctx, tools } = fakeCtx();
  /* A real clock with an offset the TTL step advances: a FROZEN clock would
   * fall behind a sub-mandate's `validFrom` (agentpay's own seconds) across
   * a second boundary and read a live budget as not yet valid. */
  let skew = 0;
  const wallet = installWallet({ ctx, home: dshHome, channelFor, log: (l) => lines.push(l), now: () => Date.now() + skew });
  try {
    assert.equal(wallet.configured, true, wallet.reason);
    assert.equal(wallet.home, home);
    assert.ok(existsSync(join(home, "wallet.lock")), "the lock is taken at install");
    assert.match(lines[0], /^wallet: 8 tools registered, home /);
    assert.deepEqual([...tools.keys()], [
      "wallet_offer", "wallet_pay", "wallet_budget_request", "wallet_budget_delegate",
      "wallet_budget_disable", "wallet_budgets", "wallet_report", "wallet_reconcile",
    ]);
    assert.deepEqual(wallet.walletTools.map((t) => t.name), [...tools.keys()]);
    const kinds = Object.fromEntries([...tools.values()].map((d) => [d.name, d.presentCall({ url: "https://x/y" }).kind]));
    assert.deepEqual(kinds, {
      wallet_offer: "fetch", wallet_pay: "fetch", wallet_budget_request: "other", wallet_budget_delegate: "other",
      wallet_budget_disable: "other", wallet_budgets: "read", wallet_report: "read", wallet_reconcile: "other",
    });
    for (const d of tools.values()) {
      assert.equal(d.timeoutMs, 60_000);
      assert.deepEqual(d.output.schema, {});
      assert.deepEqual(d.output.render({}, { ok: true }), [{ type: "text", text: '{"ok":true}' }]);
    }
    const call = (name: string, args: unknown, who: WalletToolExec): Promise<Out> => tools.get(name)!.execute(args, who) as Promise<Out>;
    const request = { purpose: "predictions", limit_usd: "0.0031", hosts: [stubHost], valid_for_hours: 1 };

    /* A second install on the same home while this one holds the lock. */
    const second = installWallet({ ctx: fakeCtx().ctx, home: dshHome, channelFor, log: () => {} });
    assert.equal(second.configured, false);
    assert.equal(second.reason, `locked by pid ${process.pid}`);

    /* THE CALLER RULE. A bot preset: refused in the face's words, a THROWN
     * error (the model reads it as an error result). A child: refused the
     * principal-only tool and pointed at delegation. Nobody: refused. */
    await assert.rejects(call("wallet_budget_request", request, exec("bot-1", { agentPreset: "drill-bull" })), /drill-bull.*no wallet/);
    await assert.rejects(call("wallet_budgets", {}, exec("bot-1", { agentPreset: "drill-bull" })), /no wallet/);
    await assert.rejects(call("wallet_budget_request", request, exec("kid-1", { origin: "subagent", parentSession: "p-1" })), /child task.*wallet_budget_delegate/);
    await assert.rejects(call("wallet_report", {}, exec("kid-1", { origin: "subagent", parentSession: "p-1" })), /principal's tool/);
    await assert.rejects(call("wallet_budgets", {}, { callId: "x" }), /needs a session/);

    /* THE PRINCIPAL requests a budget (the gate is boot.ts's; here the body
     * runs directly): a signed mandate, unheld. */
    const made = await call("wallet_budget_request", request, exec("kairos-1"));
    assert.equal(made.ok, true, JSON.stringify(made));
    const rootId = made.mandate.id as string;
    assert.equal(made.mandate.status, "signed");
    assert.equal(made.mandate.holder, undefined);
    assert.equal(made.mandate.limit_usd, "0.003100");
    assert.ok(!("signature" in made.mandate));

    /* A bad argument is the CLI's usage envelope (its `ConfigError` → `config`), not a throw. */
    const bad = await call("wallet_pay", { url: "not a url" }, exec("kairos-1"));
    assert.equal(bad.ok, false);
    assert.equal(bad.error, "config");
    assert.match(bad.message, /not a URL/);

    /* THE PRINCIPAL PAYS: settled, and the ledger row's context is what the
     * face READ - the workspace id `channelFor` resolved for the header's cwd,
     * the session id, the call id - not anything in the arguments. */
    const paid = await call("wallet_pay", { url: `${payee.url}/predict` }, exec("kairos-1", {}, "call-pay-1"));
    assert.equal(paid.ok, true, JSON.stringify(paid));
    assert.equal(paid.paid, true);
    assert.equal(paid.ledger_status, "settled");
    assert.equal(paid.amount_usd, "0.001000");
    assert.equal(paid.mandate, rootId);
    assert.equal(paid.host, stubHost);
    assert.deepEqual(paid.context, { channel: WS, channelName: "alpha", session: "kairos-1", callId: "call-pay-1" });
    assert.equal(payee.served, 1);
    const title = tools.get("wallet_pay")!.presentResult({}, { isError: false, content: [{ type: "text", text: JSON.stringify(paid) }] });
    assert.equal(title?.title, `$0.001000 · settled · ${stubHost}`);
    assert.equal(tools.get("wallet_pay")!.presentResult({}, { isError: true, content: [{ type: "text", text: "boom" }] }), undefined);

    /* A child with no delegated budget: an envelope naming the remedy. */
    const kid = exec("kid-1", { origin: "subagent", parentSession: "kairos-1" }, "call-kid-1");
    const unheld = await call("wallet_pay", { url: `${payee.url}/predict` }, kid);
    assert.equal(unheld.ok, false);
    assert.equal(unheld.error, "no_held_mandate");
    assert.ok(unheld.payment_model_context, "the model gets the hint");
    const kidBudgets = await call("wallet_budgets", {}, kid);
    assert.deepEqual(kidBudgets.mandates, []);
    assert.deepEqual(kidBudgets.caller, { kind: "child", id: "kid-1" });

    /* THE PRINCIPAL DELEGATES to its children; the child pays from it, and
     * the row carries the child's session, parent and origin. */
    const sub = await call("wallet_budget_delegate", { parent_id: rootId, limit_usd: "0.001", for: { children: true } }, exec("kairos-1"));
    assert.equal(sub.ok, true, JSON.stringify(sub));
    assert.equal(sub.mandate.holder, "children:kairos-1");
    assert.equal(sub.mandate.parent_id, rootId);
    const kidPaid = await call("wallet_pay", { url: `${payee.url}/predict` }, kid);
    assert.equal(kidPaid.ok, true, JSON.stringify(kidPaid));
    assert.equal(kidPaid.mandate, sub.mandate.id);
    assert.deepEqual(kidPaid.context, { channel: WS, channelName: "alpha", session: "kid-1", parentSession: "kairos-1", origin: "subagent", callId: "call-kid-1" });
    assert.equal(kidPaid.remaining_usd, "0.000000", "the sub-budget is spent");
    /* A sibling's second attempt: the shared sub-budget is exhausted - an envelope, no throw. */
    const sibling = await call("wallet_pay", { url: `${payee.url}/predict` }, exec("kid-2", { origin: "subagent", parentSession: "kairos-1" }));
    assert.equal(sibling.ok, false);
    assert.equal(sibling.error, "mandate_insufficient_budget");

    /* The principal's report and budgets; the listing is the principal's set only. */
    const budgets = await call("wallet_budgets", {}, exec("kairos-1"));
    assert.deepEqual(budgets.mandates.map((m: Out) => m.id), [rootId]);
    assert.deepEqual(budgets.balance, { unavailable: budgets.balance.unavailable });
    const report = await call("wallet_report", {}, exec("kairos-1"));
    assert.equal(report.ok, true);
    assert.equal(report.report.byChannel[WS], "2000");

    /* A /raw payment: the payee reports no settlement, the row is `unknown`. */
    const raw = await call("wallet_pay", { url: `${payee.url}/raw` }, exec("kairos-1", {}, "call-raw"));
    assert.equal(raw.ok, true, JSON.stringify(raw));
    assert.equal(raw.ledger_status, "unknown");

    /* THE PAGE. Mandates with effective remaining, payments newest first with
     * their context, spend keyed by workspace id, the alerts the rows imply:
     * the root is under 10 % (0.0001 of 0.0031), one row awaits reconcile,
     * the RPC is a closed port, so the balance is unavailable and the
     * on-load reconcile records what it could not settle rather than throwing. */
    const body = await page(wallet);
    assert.equal(body.configured, true);
    assert.equal(body.network, "eip155:31337");
    assert.equal(body.deployment, "localhost");
    assert.equal(body.address, accounts.payer.address);
    assert.ok(typeof body.balance.unavailable === "string", JSON.stringify(body.balance));
    assert.deepEqual(body.mandates.map((m: Out) => [m.id, m.remaining_usd]), [[rootId, "0.000100"], [sub.mandate.id, "0.000000"]]);
    assert.deepEqual(body.payments.map((p: Out) => [p.status, p.context?.session]), [["unknown", "kairos-1"], ["settled", "kid-1"], ["settled", "kairos-1"]]);
    assert.equal(body.payments[2].context.callId, "call-pay-1");
    assert.deepEqual(body.spend.by_channel, { [WS]: { name: "alpha", usd: "0.003000" } });
    assert.deepEqual(body.spend.by_session, { "kairos-1": "0.002000", "kid-1": "0.001000" });
    assert.equal(body.spend.settled_usd, "0.003000", "root-only totals: the child's spend is in the root's counters once");
    assert.equal(body.spend.unattributed_usd, "0.000000");
    const kinds2 = body.alerts.map((a: Out) => a.kind);
    for (const kind of ["budget_low", "budget_exhausted", "unknown_rows", "expiring", "rpc_unavailable"]) assert.ok(kinds2.includes(kind), `${kind} in ${kinds2}`);
    assert.ok(!kinds2.includes("balance_low"), "no balance, no balance verdict");
    /* agentpay's reconcile answers a dead RPC by leaving every row pending
     * (measured: no throw); either way the page carries the outcome as a field. */
    assert.equal(typeof body.reconcile?.at, "string", JSON.stringify(body.reconcile));
    assert.ok(body.reconcile.still_pending >= 1 || typeof body.reconcile.error === "string", JSON.stringify(body.reconcile));
    assert.doesNotMatch(JSON.stringify(body), /"signature"|mandateHash|0x59c6995e|"key"/, "never the key or signing material");
    assert.ok(!existsSync(join(home, "face-state.json")), "no balance read, no anchor written");

    /* The balance is single-flight and cached: a second look within the TTL
     * runs no second reconcile either (once a minute), and past it, both run again. */
    const again = await page(wallet);
    assert.equal(again.reconcile, undefined, "reconcile at most once a minute");
    skew += BALANCE_TTL_MS + 1;
    const later = await page(wallet);
    assert.equal(typeof later.reconcile?.at, "string", "past the minute, reconcile runs again");

    /* The channel tile's seam: settled rows in this channel, by workspace id. */
    assert.deepEqual(await wallet.spendFor!({ workspaceId: WS }), { settled_usd: "0.002000", count: 2 });
    assert.equal(await wallet.spendFor!({ workspaceId: "elsewhere" }), null);

    /* The forged-Host fence, first. */
    const forged = fakeRes();
    await routeOf(wallet).handler(getReq("evil.example.com"), forged.res);
    assert.equal(forged.out.status, 403);
  } finally {
    wallet.dispose();
    await payee.close();
  }
  assert.ok(!existsSync(join(home, "wallet.lock")), "dispose releases the lock");
  assert.equal(tools.size, 0, "dispose unregisters the tools");
  rmSync(dshHome, { recursive: true, force: true });
  assert.deepEqual(unhandled, []);
});

test("installWallet on eip155:84532: a loopback payee is refused before any request, with the hint; a public host reaches agentpay's own gate", async () => {
  const dshHome = mkdtempSync(join(tmpdir(), "face-wallet-sepolia-"));
  const home = join(dshHome, "face", "agentpay");
  const payee: StubPayee = await startStubPayee({ payTo: payeeAddress, token: TOKEN, assetDomain: { ...MOCK_USDC_DOMAIN }, network: "eip155:84532", price: "$0.001", facilitatorAddress });
  const stubHost = new URL(payee.url).host;
  configure(home, "eip155:84532");
  const { ctx, tools } = fakeCtx();
  const wallet = installWallet({ ctx, home: dshHome, channelFor, log: () => {} });
  try {
    assert.equal(wallet.configured, true, wallet.reason);
    const call = (name: string, args: unknown, who: WalletToolExec): Promise<Out> => tools.get(name)!.execute(args, who) as Promise<Out>;
    const made = await call("wallet_budget_request", { purpose: "p", limit_usd: "1", hosts: [stubHost, "api.example.com"] }, exec("kairos-1"));
    assert.equal(made.ok, true, JSON.stringify(made));
    for (const name of ["wallet_pay", "wallet_offer"]) {
      const refused = await call(name, { url: `${payee.url}/predict` }, exec("kairos-1"));
      assert.equal(refused.ok, false, name);
      assert.equal(refused.error, "host_not_allowed", name);
      assert.equal(refused.host, stubHost);
      assert.match(refused.payment_model_context.summary, /loopback, link-local, private-range/);
      assert.match(refused.payment_model_context.summary, new RegExp(name));
    }
    assert.equal(payee.requests, 0, "the stub was never reached");
    assert.equal(payee.served, 0);
    /* A public host the budget does not name meets agentpay's pre-flight
     * (requireMandateHost) - a different refusal, proving the two are
     * distinct and both stand. (No request leaves: the pre-flight is
     * before the first fetch.) */
    const unnamed = await call("wallet_offer", { url: "https://data.example.net/x" }, exec("kairos-1"));
    assert.equal(unnamed.ok, false);
    assert.equal(unnamed.error, "host_not_allowed");
    assert.doesNotMatch(unnamed.payment_model_context.summary, /loopback/);
  } finally {
    wallet.dispose();
    await payee.close();
  }
  rmSync(dshHome, { recursive: true, force: true });
  assert.deepEqual(unhandled, []);
});

test("the wallet's fetch never follows a redirect: a 3xx is a host_not_allowed refusal before the request lands anywhere", async () => {
  /* The wrapper alone, over a stub base. */
  const seen: RequestInit[] = [];
  const stub = (async (_input: string | URL | Request, init?: RequestInit) => {
    seen.push(init ?? {});
    return new Response("ok", { status: 200 });
  }) as unknown as typeof globalThis.fetch;
  const ok = await noRedirectFetch(stub)("https://api.example.com/x", { method: "POST" });
  assert.equal(ok.status, 200);
  assert.equal(seen[0].redirect, "manual");
  assert.equal(seen[0].method, "POST", "the caller's init is kept");
  const bouncing = (async () => new Response("", { status: 302, headers: { location: "http://169.254.169.254/latest" } })) as unknown as typeof globalThis.fetch;
  await assert.rejects(noRedirectFetch(bouncing)("https://api.example.com/x"), (err: unknown) => {
    assert.ok(err instanceof PolicyViolation);
    assert.equal(err.reason, "host_not_allowed");
    assert.match(err.payment_model_context?.summary ?? "", /redirect to "http:\/\/169\.254\.169\.254\/latest"/);
    return true;
  });

  /* Through the tool, on the local chain (the one network where the loopback
   * redirector may be named at all): the budget names the redirector, the
   * redirector answers 302, the model reads a refusal, and the redirect's
   * target (a closed port) is never asked. */
  const dshHome = mkdtempSync(join(tmpdir(), "face-wallet-redirect-"));
  const home = join(dshHome, "face", "agentpay");
  configure(home, "eip155:31337");
  let hits = 0;
  const redirector = createServer((_req, res) => {
    hits += 1;
    res.writeHead(302, { location: `${CLOSED_RPC}/x` });
    res.end();
  });
  await new Promise<void>((resolve) => redirector.listen(0, "127.0.0.1", resolve));
  const address = redirector.address();
  const redirectorUrl = `http://127.0.0.1:${typeof address === "object" && address !== null ? address.port : 0}`;
  const { ctx, tools } = fakeCtx();
  const wallet = installWallet({ ctx, home: dshHome, channelFor, log: () => {} });
  try {
    assert.equal(wallet.configured, true, wallet.reason);
    const call = (name: string, args: unknown): Promise<Out> => tools.get(name)!.execute(args, exec("kairos-1")) as Promise<Out>;
    const made = await call("wallet_budget_request", { purpose: "p", limit_usd: "1", hosts: [new URL(redirectorUrl).host] });
    assert.equal(made.ok, true, JSON.stringify(made));
    for (const name of ["wallet_pay", "wallet_offer"]) {
      const refused = await call(name, { url: `${redirectorUrl}/predict` });
      assert.equal(refused.ok, false, name);
      assert.equal(refused.error, "host_not_allowed", JSON.stringify(refused));
      assert.match(refused.payment_model_context.summary, /never follows a redirect/);
    }
    assert.equal(hits, 2, "one request each, none past the redirect");
  } finally {
    wallet.dispose();
    await new Promise<void>((resolve) => redirector.close(() => resolve()));
  }
  rmSync(dshHome, { recursive: true, force: true });
  assert.deepEqual(unhandled, []);
});

test.after(() => {
  process.off("unhandledRejection", onUnhandled);
});
