/** The wallet on a REAL composed tree: `installWallet` on the booted root
 * context, the tools dispatched through dsh's own registry (`tools.execute`)
 * for a gateway-created principal session, and the ledger row carrying that
 * session's id — the attribution claim of spec decision 4, measured where
 * the face reads it (the agent dsh hands `execute`), not where a fake said
 * so. `wallet.test.ts` proves the same logic over a fake context; this
 * proves the registration and the header the real session store stamps.
 *
 * The payee is the wallet package's in-process stub on loopback, and the
 * home is on network `eip155:31337` so the private-host refusal lifts for it
 * (`LOCAL_NETWORK`); the root mandate is signed beforehand through the
 * wallet API, because the budget CARD (Gate 3) is the operator's half and
 * the budget-gate drill already covers its ask/deny paths.
 *
 * Gated behind `FACE_SMOKE=1` and in its own FILE: `bootFace` sets
 * `process.env.DSH_HOME` permanently, so one boot per process.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { mkdir, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MOCK_USDC_DOMAIN } from "../../payment/packages/contracts/src/index.ts";
import { writeStoredConfig } from "../../payment/packages/cli/src/index.ts";
import { MandateWallet } from "../../payment/packages/wallet/src/index.ts";
import { accounts } from "../../payment/packages/payee/test/helpers.ts";
import { KEYS, startStubPayee } from "../../payment/packages/wallet/test/stub-payee.ts";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { createBot, renderComposition } from "../src/bots.ts";
import { panelDeps } from "../src/panels.ts";
import { installWallet, type WalletContextLike } from "../src/wallet.ts";
import { makeRepoBotsRoot } from "./bots-fixture.ts";

const gated = process.env.FACE_SMOKE !== "1";
const TOKEN = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";

type Out = Record<string, any>;

test("wallet smoke: installed on a booted tree, a gateway session pays through dsh's registry and the ledger names it; a bot is refused", {
  skip: gated && "set FACE_SMOKE=1",
}, async () => {
  const bots = await makeRepoBotsRoot();
  const root = mkdtempSync(join(tmpdir(), "face-wallet-root-"));
  const home = mkdtempSync(join(tmpdir(), "face-walletsmoke-"));
  const walletHome = mkdtempSync(join(tmpdir(), "face-agentpay-"));
  const payee = await startStubPayee({
    payTo: accounts.payee.address, token: TOKEN, assetDomain: { ...MOCK_USDC_DOMAIN }, network: "eip155:31337",
    price: "$0.001", facilitatorAddress: accounts.facilitator.address,
  });
  const stubHost = new URL(payee.url).host;
  const envBefore = process.env.FACE_AGENTPAY_HOME;
  try {
    /* The home: config.json as `agentpay init` writes it (a closed RPC port,
     * so the chain path degrades), and one signed root mandate made through
     * the wallet API - the operator's approval, stood in for. No lock here:
     * the face takes it on install. */
    writeStoredConfig(walletHome, { key: KEYS.payer, token: TOKEN, tokenDomain: { ...MOCK_USDC_DOMAIN }, network: "eip155:31337", rpcUrl: "http://127.0.0.1:1" });
    const pre = new MandateWallet({
      key: KEYS.payer, token: TOKEN, assetDomain: { ...MOCK_USDC_DOMAIN }, network: "eip155:31337",
      mandatesPath: join(walletHome, "mandates.json"), ledgerPath: join(walletHome, "ledger.jsonl"), log: () => {},
    });
    const rootMandate = await pre.createIntentMandate({ naturalLanguage: "smoke predictions", limitAmount: "$0.01", validForSeconds: 3600, hostAllowlist: [stubHost] }, { approve: true });
    assert.equal(rootMandate.status, "signed");
    pre.dispose();
    process.env.FACE_AGENTPAY_HOME = walletHome;

    await createBot(bots, { id: "voice", name: "Voice", soul: "You are Voice, a test bot with no wallet.", model: "stub/echo" });
    /* A second bot whose composition WAS given `wallet_pay` - the charter §8
     * trigger, done here on purpose: the mask is the first refusal, the tool
     * itself must be the second. */
    const grabby = await createBot(bots, { id: "grabby", name: "Grabby", soul: "You are Grabby, a test bot handed a wallet tool.", model: "stub/echo" });
    writeFileSync(join(bots, grabby.id, "agent.cordis.yml"), renderComposition({ soul: "You are Grabby, a test bot handed a wallet tool.", allow: ["wallet_pay", "wallet_budgets"] }));
    const channelDir = await realpath(await (async () => { const d = join(root, "strategies", "wallet-test"); await mkdir(d, { recursive: true }); return d; })());
    setupFaceProfile(home);
    const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
    const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
    // This smoke owns a scratch profile and must not start the operator's data server.
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
    const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    let disposeWallet: (() => void) | undefined;
    try {
      const agents = ctx.get("agents") as { get(id: string): { id: string; session: { header: Record<string, unknown> } } | undefined };
      const tools = ctx.get("tools") as {
        schemas(scope?: object): { name: string }[];
        execute(exec: object): Promise<{ isError: boolean; content?: { text?: string }[] }>;
      };
      const registry = ctx.get("workspaceRegistry") as { create(path: string): Promise<{ id: string; path: string }> };
      const ws = await registry.create(channelDir);

      /* Installed exactly as main.ts installs it: on the root context, with
       * the panel seams' `channelFor`, the home from FACE_AGENTPAY_HOME. */
      const lines: string[] = [];
      const deps = panelDeps(ctx, root, home);
      const wallet = installWallet({ ctx: ctx as unknown as WalletContextLike, home, channelFor: deps.channelFor, log: (l) => lines.push(l) });
      disposeWallet = wallet.dispose;
      wallet.registerRoutes(ctx.webServer);
      assert.equal(wallet.configured, true, wallet.reason);
      assert.equal(wallet.home, walletHome);
      assert.match(lines[0], /^wallet: 8 tools registered, home /);
      assert.ok(existsSync(join(walletHome, "wallet.lock")));

      const base = `http://127.0.0.1:${ctx.webServer.port}`;
      let n = 0;
      const rpc = async (method: string, payload: object): Promise<Record<string, unknown>> => {
        const res = await fetch(`${base}/api/${method}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ type: "client-request", rpcId: `r${++n}`, method, payload }) });
        const body = await res.json() as { result?: { ok?: boolean; value?: Record<string, unknown>; error?: unknown } };
        assert.equal(body.result?.ok, true, `${method}: ${JSON.stringify(body.result?.error)}`);
        return body.result!.value!;
      };
      const run = async (name: string, args: object, agent: object, callId: string): Promise<{ isError: boolean; out: Out }> => {
        const result = await tools.execute({ callId, name, arguments: args, agent, signal: new AbortController().signal });
        const text = result.content?.[0]?.text ?? "";
        let out: Out = {};
        try {
          out = JSON.parse(text) as Out;
        } catch {
          out = { text };
        }
        return { isError: result.isError, out };
      };

      /* THE PRINCIPAL: a gateway-created session in the channel (the default
       * preset - what `classifyRequester` calls the principal). Its roster
       * carries the eight tools; nothing in this test masked them. */
      const created = await rpc("session.create", { workspaceId: ws.id });
      const sessionId = String(created.sessionId);
      assert.equal(created.agentPreset, "kairos");
      const agent = agents.get(sessionId);
      assert.ok(agent, "the session is live as an agent");
      assert.equal(agent.session.header.cwd, channelDir);
      const names = tools.schemas(agent as object).map((s) => s.name);
      for (const name of ["wallet_offer", "wallet_pay", "wallet_budget_request", "wallet_budgets", "wallet_report"]) assert.ok(names.includes(name), `${name} in the principal's roster`);

      const budgets = await run("wallet_budgets", {}, agent, "smoke-budgets");
      assert.equal(budgets.isError, false, JSON.stringify(budgets.out));
      assert.equal(budgets.out.ok, true);
      assert.deepEqual(budgets.out.mandates.map((m: Out) => m.id), [rootMandate.id]);
      assert.deepEqual(budgets.out.caller, { kind: "principal" });
      assert.ok("unavailable" in budgets.out.balance, "a closed RPC port reads as unavailable, not as an error");

      const paid = await run("wallet_pay", { url: `${payee.url}/predict` }, agent, "smoke-pay-1");
      assert.equal(paid.isError, false, JSON.stringify(paid.out));
      assert.equal(paid.out.ok, true);
      assert.equal(paid.out.paid, true);
      assert.equal(paid.out.ledger_status, "settled");
      assert.equal(paid.out.mandate, rootMandate.id);
      assert.equal(payee.served, 1);
      /* THE CLAIM: the row names the session dsh ran the call in, and the
       * channel the registry resolved for its directory - read, not told. */
      assert.deepEqual(paid.out.context, { channel: ws.id, channelName: "wallet-test", session: sessionId, callId: "smoke-pay-1" });
      const rows = readFileSync(join(walletHome, "ledger.jsonl"), "utf8").trim().split("\n").map((line) => JSON.parse(line) as Out);
      assert.equal(rows.length, 1);
      assert.equal(rows[0].status, "settled");
      assert.equal(rows[0].context.session, sessionId);
      assert.equal(rows[0].context.channel, ws.id);

      /* The page, on the real webserver, same-origin: the payment and its context. */
      const pageRes = await fetch(`${base}/data/wallet.json`);
      const pageText = await pageRes.text();
      assert.equal(pageRes.status, 200, pageText);
      const page = JSON.parse(pageText) as Out;
      assert.equal(page.ok, true);
      assert.equal(page.configured, true);
      assert.equal(page.payments[0].context.session, sessionId);
      assert.deepEqual(page.spend.by_channel, { [ws.id]: { name: "wallet-test", usd: "0.001000" } });
      assert.equal("configured" in page && !("key" in page), true);

      /* A BOT SESSION (a rostered preset, created through the same gateway).
       * Two refusals, in order. The default composition's mask does not
       * name the tool, so dsh's registry refuses it as unknown - a tool
       * registered after boot is invisible to a bot unless its allow list
       * names it (spec decision 1c). And a bot whose composition WAS given
       * `wallet_pay` meets the tool's own refusal, in the words of the rule:
       * an error result, no payment, the stub untouched. */
      const voiceSession = await rpc("session.create", { cwd: channelDir, agentPreset: "voice" });
      const voice = agents.get(String(voiceSession.sessionId));
      assert.ok(voice);
      assert.equal(voice.session.header.agentPreset, "voice");
      const masked = await run("wallet_pay", { url: `${payee.url}/predict` }, voice, "smoke-voice-pay");
      assert.equal(masked.isError, true, JSON.stringify(masked.out));
      assert.match(JSON.stringify(masked.out), /unknown tool/);

      const grabbySession = await rpc("session.create", { cwd: channelDir, agentPreset: "grabby" });
      const bot = agents.get(String(grabbySession.sessionId));
      assert.ok(bot);
      assert.equal(bot.session.header.agentPreset, "grabby");
      assert.ok(tools.schemas(bot as object).some((s) => s.name === "wallet_pay"), "grabby's mask names the tool");
      const refused = await run("wallet_pay", { url: `${payee.url}/predict` }, bot, "smoke-bot-pay");
      assert.equal(refused.isError, true, JSON.stringify(refused.out));
      assert.match(JSON.stringify(refused.out), /grabby.*no wallet/);
      assert.equal(payee.served, 1, "nothing was paid");
      assert.equal(readFileSync(join(walletHome, "ledger.jsonl"), "utf8").trim().split("\n").length, 1);
    } finally {
      disposeWallet?.();
      await dispose();
    }
    assert.ok(!existsSync(join(walletHome, "wallet.lock")), "dispose released the lock");
  } finally {
    if (envBefore === undefined) delete process.env.FACE_AGENTPAY_HOME; else process.env.FACE_AGENTPAY_HOME = envBefore;
    await payee.close();
    await rm(bots, { recursive: true, force: true });
    await rm(root, { recursive: true, force: true });
    await rm(walletHome, { recursive: true, force: true });
  }
});
