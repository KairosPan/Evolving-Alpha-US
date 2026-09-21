/** The budget CARD's positive path, end to end (spec R-W5) - what Gate 2's
 * order card never had a drill for: a scripted model asks for a budget, an
 * operator stand-in answers the card, and the mandate the answer creates is
 * the one the next payment spends.
 *
 * Three sessions on one booted tree, one stub model, one wallet home:
 * - DENY first (case B), while the home holds no mandate at all, so "the
 *   script's next step never pays" is measured against an empty home rather
 *   than against a budget some other session won;
 * - APPROVE (case A): the `approval/asked` + `approval/decided{allowed-once}`
 *   pair for the call, the tool result with a signed mandate, the same
 *   mandate on `/data/wallet.json`, then `wallet_pay` settling ONE request
 *   through it with the session's id in the ledger context;
 * - NEVER (case C): the `danger-full-access` preset applied through the
 *   public `permissionPresets.set`, and the gate's own words with no card.
 *
 * THE ANSWERER. `dsh-host-apiproxy` parks every approval in `pendingApprovals`
 * for a browser (`lib/index.js:1903-1955`) and pushes a frame to the mux
 * queues; with no client attached the ask would block forever. This test
 * registers its own `approval/request` listener on the root context with
 * `prepend: true` so it runs BEFORE the apiproxy answerer (cordis waterfalls
 * are last-prepend-first), and answers per session id from a table - a
 * session not in the table falls through with `next()`. Chosen over the
 * `/api/respond` route because that route needs a mux client to have
 * received the `approval/requested` frame's rpcId first; a listener is what
 * a browser IS to the service, and the audit pair is still written by
 * `ApprovalService.request` itself, not by us.
 *
 * Gated behind `FACE_SMOKE=1` and in its own FILE: one boot per process.
 * @module
 */
import test from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { mkdir, realpath, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import type { GenerateOptions } from "@deepseek-ai/dsh-llm";
import { MOCK_USDC_DOMAIN } from "../../payment/packages/contracts/src/index.ts";
import { writeStoredConfig } from "../../payment/packages/cli/src/index.ts";
import { accounts } from "../../payment/packages/payee/test/helpers.ts";
import { KEYS, startStubPayee } from "../../payment/packages/wallet/test/stub-payee.ts";
import { setupFaceProfile } from "../src/setup.ts";
import { bootFace } from "../src/boot.ts";
import { panelDeps } from "../src/panels.ts";
import { installWallet, type WalletContextLike } from "../src/wallet.ts";
import { makeRepoBotsRoot } from "./bots-fixture.ts";
import { StubAdapter, type StubReply } from "./stub-llm.ts";

const gated = process.env.FACE_SMOKE !== "1";
const TOKEN = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512";
const PURPOSE = "smoke budget";

type Out = Record<string, any>;
interface Ev { type: string; seq: number; data?: Record<string, unknown> }

async function waitFor(what: string, check: () => boolean, ms = 30_000): Promise<void> {
  const until = Date.now() + ms;
  while (!check()) {
    if (Date.now() > until) throw new Error(`timed out waiting for ${what}`);
    await new Promise((r) => setTimeout(r, 50));
  }
}

/** The tool results of one session's log, in order, as the model read them. */
function toolResults(events: readonly Ev[]): { callId: string; isError: boolean; out: Out }[] {
  return events.filter((e) => e.type === "tool/result").map((e) => {
    /* `createToolResultMessage` (dsh-llm): a user message whose one block is
     * `{type:'tool-result', toolCallId, content:[{text}], isError}`. */
    const message = e.data?.message as { source?: { callId?: string }; content?: { toolCallId?: string; content?: { text?: string }[]; isError?: boolean }[] } | undefined;
    const block = message?.content?.[0];
    const text = block?.content?.[0]?.text ?? "";
    let out: Out;
    try {
      out = JSON.parse(text) as Out;
    } catch {
      out = { text };
    }
    return { callId: String(block?.toolCallId ?? message?.source?.callId), isError: block?.isError === true, out };
  });
}

test("wallet approve smoke: the budget card answered allowed-once mints the mandate the next payment spends; rejected mints nothing; policy never raises no card", {
  skip: gated && "set FACE_SMOKE=1",
}, async () => {
  const bots = await makeRepoBotsRoot();
  const root = mkdtempSync(join(tmpdir(), "face-wallet-approve-root-"));
  const home = mkdtempSync(join(tmpdir(), "face-walletapprove-"));
  const walletHome = mkdtempSync(join(tmpdir(), "face-agentpay-approve-"));
  const payee = await startStubPayee({
    payTo: accounts.payee.address, token: TOKEN, assetDomain: { ...MOCK_USDC_DOMAIN }, network: "eip155:31337",
    price: "$0.001", facilitatorAddress: accounts.facilitator.address,
  });
  const stubHost = new URL(payee.url).host;
  const envBefore = process.env.FACE_AGENTPAY_HOME;
  try {
    /* The home as `agentpay init` writes it, and NO mandate: every budget in
     * this drill is one a card produced. */
    writeStoredConfig(walletHome, { key: KEYS.payer, token: TOKEN, tokenDomain: { ...MOCK_USDC_DOMAIN }, network: "eip155:31337", rpcUrl: "http://127.0.0.1:1" });
    process.env.FACE_AGENTPAY_HOME = walletHome;

    const channelDir = await realpath(await (async () => { const d = join(root, "strategies", "approve-test"); await mkdir(d, { recursive: true }); return d; })());
    setupFaceProfile(home);
    const patchPath = join(home, "profiles", "face", "cordis.patch.yml");
    const patch = readFileSync(patchPath, "utf8").replace(/^\[\][ \t]*$/m, "");
    // This smoke owns a scratch profile and must not start the operator's data server.
    writeFileSync(patchPath, `${patch}\n- id: mcp-akshare\n  disabled: true\n`);
    const { ctx, dispose } = await bootFace({ profileName: "face", port: 0, dshHome: home, botsRoot: bots });
    let disposeWallet: (() => void) | undefined;
    try {
      const sessions = ctx.get("sessions") as unknown as { get(id: string): { id: string; header: Record<string, unknown>; events: Ev[] } | undefined };
      const agents = ctx.get("agents") as { get(id: string): { id: string; session: { id: string; header: Record<string, unknown>; events: Ev[] } } | undefined };
      const registry = ctx.get("workspaceRegistry") as { create(path: string): Promise<{ id: string; path: string }> };
      const llm = ctx.get("llm") as { registerAdapter(providers: string[], adapter: object): () => void };
      const presets = ctx.get("permissionPresets") as { set(session: object, name: string): void; current(events: readonly Ev[]): string };
      const on = ctx as unknown as {
        on(name: "approval/request", listener: (req: { agent: { session: { id: string } }; toolName: string; callId?: unknown; reason?: string }, next: () => Promise<string>) => Promise<string> | string, options?: { prepend?: boolean }): () => void;
      };

      /* THE OPERATOR STAND-IN: one outcome per session, outermost. */
      const answers = new Map<string, "allowed-once" | "rejected">();
      const asked: { session: string; toolName: string; callId: unknown; reason?: string }[] = [];
      const disposeAnswerer = on.on("approval/request", (req, next) => {
        const outcome = answers.get(req.agent.session.id);
        if (outcome === undefined) return next();
        asked.push({ session: req.agent.session.id, toolName: req.toolName, callId: req.callId, ...req.reason === undefined ? {} : { reason: req.reason } });
        return outcome;
      }, { prepend: true });

      /* THE SCRIPT, the same for every session: budget → pay → "paid". Where
       * the conversation is = how many tool results the model has read. */
      llm.registerAdapter(["stub"], new StubAdapter((o: GenerateOptions): StubReply => {
        if (o.purpose !== undefined) return { kind: "text", text: "approve smoke" }; // titles, compaction
        const results = o.messages.filter((m) => String((m.source as { kind?: unknown } | undefined)?.kind) === "tool").length;
        if (results === 0) return { kind: "tool", name: "wallet_budget_request", args: { purpose: PURPOSE, limit_usd: "0.05", hosts: [stubHost], valid_for_hours: 1 } };
        if (results === 1) return { kind: "tool", name: "wallet_pay", args: { url: `${payee.url}/predict` } };
        return { kind: "text", text: "paid" };
      }));

      const ws = await registry.create(channelDir);
      const deps = panelDeps(ctx, root, home);
      const wallet = installWallet({ ctx: ctx as unknown as WalletContextLike, home, channelFor: deps.channelFor, log: () => {} });
      disposeWallet = () => {
        wallet.dispose();
        disposeAnswerer();
      };
      wallet.registerRoutes(ctx.webServer);
      assert.equal(wallet.configured, true, wallet.reason);

      const base = `http://127.0.0.1:${ctx.webServer.port}`;
      let n = 0;
      const rpc = async (method: string, payload: object): Promise<Record<string, unknown>> => {
        const res = await fetch(`${base}/api/${method}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ type: "client-request", rpcId: `r${++n}`, method, payload }) });
        const body = await res.json() as { result?: { ok?: boolean; value?: Record<string, unknown>; error?: unknown } };
        assert.equal(body.result?.ok, true, `${method}: ${JSON.stringify(body.result?.error)}`);
        return body.result!.value!;
      };
      /** A principal session in the channel on the stub route, its script run to the turn's end. */
      const principal = async (): Promise<string> => {
        const created = await rpc("session.create", { workspaceId: ws.id });
        assert.equal(created.agentPreset, "kairos");
        const id = String(created.sessionId);
        await rpc("session.selectModel", { sessionId: id, provider: "stub", model: "echo" });
        return id;
      };
      const runScript = async (id: string): Promise<Ev[]> => {
        const log = () => sessions.get(id)!.events;
        const before = log().length;
        await rpc("session.prompt", { sessionId: id, mode: "queue", content: [{ type: "text", text: "buy one prediction" }] });
        await waitFor(`session ${id}'s turn to end`, () => log().slice(before).some((e) => e.type === "turn/end"), 60_000);
        return log();
      };
      const mandatesOnPage = async (): Promise<Out[]> => {
        const res = await fetch(`${base}/data/wallet.json`);
        const page = await res.json() as Out;
        assert.equal(page.ok, true);
        return page.mandates as Out[];
      };

      /* ---- CASE B: rejected, on an empty home ---- */
      const denied = await principal();
      answers.set(denied, "rejected");
      const deniedLog = await runScript(denied);
      const deniedAsked = deniedLog.filter((e) => e.type === "approval/asked");
      assert.equal(deniedAsked.length, 1, "one card was raised");
      const deniedDecided = deniedLog.find((e) => e.type === "approval/decided" && e.data?.id === deniedAsked[0].data?.id);
      assert.equal(deniedDecided?.data?.outcome, "rejected");
      const deniedResults = toolResults(deniedLog);
      assert.equal(deniedResults.length, 2, `budget, then the pay the script tries anyway; saw ${JSON.stringify(deniedResults)}`);
      assert.equal(deniedResults[0].isError, true, "a rejected card is an error the model reads");
      assert.match(JSON.stringify(deniedResults[0].out), /rejected/);
      assert.notEqual(deniedResults[1].out.paid, true, `with no mandate the pay does not pay; saw ${JSON.stringify(deniedResults[1].out)}`);
      assert.notEqual(deniedResults[1].out.ledger_status, "settled");
      assert.equal(payee.served, 0, "nothing was paid");
      assert.deepEqual(await mandatesOnPage(), [], "no mandate exists for a rejected card");
      assert.ok(!existsSync(join(walletHome, "ledger.jsonl")) || readFileSync(join(walletHome, "ledger.jsonl"), "utf8").trim() === "", "no ledger row");

      /* ---- CASE A: allowed-once ---- */
      const approved = await principal();
      answers.set(approved, "allowed-once");
      const log = await runScript(approved);
      const askedEvents = log.filter((e) => e.type === "approval/asked");
      assert.equal(askedEvents.length, 1, "one budget = one card");
      const ask = askedEvents[0].data as { id: string; toolName: string; callId: string; reason?: string };
      assert.equal(ask.toolName, "wallet_budget_request");
      assert.ok(ask.reason?.includes(PURPOSE), `the card names the purpose; saw ${JSON.stringify(ask.reason)}`);
      assert.ok(ask.reason?.includes(stubHost), `the card names the host in full; saw ${JSON.stringify(ask.reason)}`);
      assert.match(ask.reason ?? "", /limit \$0\.05/);
      assert.match(ask.reason ?? "", /by principal$/);
      const decided = log.find((e) => e.type === "approval/decided" && e.data?.id === ask.id);
      assert.equal(decided?.data?.outcome, "allowed-once", "the pair is logged for that card");
      assert.deepEqual(asked.filter((a) => a.session === approved).map((a) => a.toolName), ["wallet_budget_request"]);
      assert.equal(asked.find((a) => a.session === approved)?.callId, ask.callId, "the answerer saw the same callId the audit logged");

      const results = toolResults(log);
      assert.equal(results.length, 2, JSON.stringify(results));
      const [budget, paid] = results;
      assert.equal(budget.callId, ask.callId, "the approved call is the budget call");
      assert.equal(budget.isError, false, JSON.stringify(budget.out));
      assert.equal(budget.out.ok, true);
      const mandate = budget.out.mandate as Out;
      assert.equal(mandate.status, "signed", "the card's yes is a signed mandate");
      assert.equal(mandate.purpose, PURPOSE);
      assert.deepEqual(mandate.hosts, [stubHost]);
      assert.equal(mandate.limit_usd, "0.050000");
      const onPage = await mandatesOnPage();
      assert.deepEqual(onPage.map((m) => m.id), [mandate.id], "the same mandate is on /data/wallet.json");
      assert.equal(onPage[0].status, "signed");

      assert.equal(paid.isError, false, JSON.stringify(paid.out));
      assert.equal(paid.out.ok, true);
      assert.equal(paid.out.paid, true);
      assert.equal(paid.out.ledger_status, "settled");
      assert.equal(paid.out.mandate, mandate.id, "the payment spent the mandate the card minted");
      assert.equal(paid.out.context.session, approved);
      assert.equal(paid.out.context.channel, ws.id);
      assert.equal(payee.served, 1, "exactly one paid request");
      const rows = readFileSync(join(walletHome, "ledger.jsonl"), "utf8").trim().split("\n").map((line) => JSON.parse(line) as Out);
      assert.equal(rows.length, 1);
      assert.equal(rows[0].status, "settled");
      assert.equal(rows[0].context.session, approved);
      assert.equal(rows[0].intentMandateId, mandate.id);
      const said = log.filter((e) => e.type === "assistant/message");
      assert.ok(said.some((e) => JSON.stringify(e.data).includes("paid")), "the script reached its last line");

      /* ---- CASE C: policy never, through the public preset switch ---- */
      const never = await principal();
      answers.set(never, "allowed-once"); // would approve - must never be asked
      const neverAgent = agents.get(never);
      assert.ok(neverAgent);
      presets.set(neverAgent.session, "danger-full-access");
      assert.equal(presets.current(neverAgent.session.events), "danger-full-access");
      const servedBefore = payee.served;
      const neverLog = await runScript(never);
      assert.equal(neverLog.filter((e) => e.type === "approval/asked").length, 0, "no card under policy never");
      assert.equal(asked.filter((a) => a.session === never).length, 0, "the answerer was never reached");
      const neverResults = toolResults(neverLog);
      assert.equal(neverResults[0].isError, true);
      const neverText = String(neverResults[0].out.text ?? JSON.stringify(neverResults[0].out));
      assert.match(neverText, /approval policy is "never"/, `the gate's own words; saw ${neverText}`);
      assert.match(neverText, /Nobody has refused it; nobody was asked/);
      assert.doesNotMatch(neverText, /the user rejected tool/, "never dsh's false 'the user rejected'");
      assert.deepEqual((await mandatesOnPage()).map((m) => m.id), [mandate.id], "no new mandate");
      /* The pay the script tries next: a principal, so it CAN spend the case-A
       * mandate (holders are by class, not by session) - which is the spec's
       * rule, not a leak; what case C asserts is the card, not the wallet. */
      assert.ok(payee.served >= servedBefore);
    } finally {
      disposeWallet?.();
      await dispose();
    }
  } finally {
    if (envBefore === undefined) delete process.env.FACE_AGENTPAY_HOME; else process.env.FACE_AGENTPAY_HOME = envBefore;
    await payee.close();
    await rm(bots, { recursive: true, force: true });
    await rm(root, { recursive: true, force: true });
    await rm(walletHome, { recursive: true, force: true });
  }
});
