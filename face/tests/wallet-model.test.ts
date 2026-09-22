import test from "node:test";
import assert from "node:assert/strict";
import {
  balanceView, fileSize, groupAlerts, hasAlerts, holderLabel, mandateRows, mandateStatus, payFields, payLine,
  paymentContext, paymentRows, payStatus, remainingPct, savedFile, setupCommand, shortHex, shortSession, spendRows,
  txLink, usd, usdCompact, usdNumber,
} from "../client/wallet-model.js";
import { EMPTY, FULL, NOT_CONFIGURED, NOW, PAY_402, PAY_OK, PAY_REFUSED, PAY_SAVED } from "./wallet-fixture.ts";

/* Amounts are USD strings by contract (§4.4). A missing one is an em-dash,
 * never a zero: the page must not print a balance the server did not give. */
test("usd strings format at six decimals; blanks and non-numbers never become a figure", () => {
  assert.equal(usd("0.001000"), "$0.001000");
  assert.equal(usd("5"), "$5.000000");
  assert.equal(usd("1234.5"), "$1,234.500000");
  assert.equal(usd(-0.5), "-$0.500000");
  assert.equal(usdCompact("0.001000"), "$0.001");
  assert.equal(usdCompact("5.000000"), "$5.00");
  assert.equal(usdCompact("0.010000"), "$0.01");
  for (const value of [undefined, null, "", "  ", "n/a", NaN, Infinity, {}, [], true]) {
    assert.equal(usdNumber(value), null);
    assert.equal(usd(value), "—");
    assert.equal(usdCompact(value), "—");
  }
});

test("identifiers shorten for a cell and stay whole when already short", () => {
  assert.equal(shortHex("0xe833f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c9c9d"), "0xe833f1…9c9d");
  assert.equal(shortHex("0xe833f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c9c9d", 6, 4), "0xe833…9c9d");
  assert.equal(shortHex("im_1f3218efc2a7"), "im_1f3218efc2a7");
  assert.equal(shortHex(""), "—");
  assert.equal(shortHex(42), "—");
  assert.equal(shortSession("session-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"), "0a1b2c3d");
  assert.equal(shortSession("plain"), "plain");
  assert.equal(shortSession("a-long-opaque-id"), "a-long-o…");
  assert.equal(shortSession(undefined), "—");
});

/* The explorer rule (§1 of the model file): Base Sepolia links, the local
 * chain does not, and a tx that is not a 64-hex hash never becomes a URL —
 * that string would otherwise be pasted into a link the operator clicks. */
test("tx links exist only for Base Sepolia and only for a real hash", () => {
  const tx = "0xe833f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c9c9d";
  assert.equal(txLink("eip155:84532", tx), `https://sepolia.basescan.org/tx/${tx}`);
  assert.equal(txLink("eip155:31337", tx), null);
  assert.equal(txLink("eip155:8453", tx), null);
  assert.equal(txLink("eip155:84532", "not-a-hash"), null);
  assert.equal(txLink("eip155:84532", "0x1234"), null);
  assert.equal(txLink(undefined, tx), null);
  assert.equal(txLink("eip155:84532", undefined), null);
});

test("the not-configured body renders nothing but the setup step", () => {
  assert.equal(NOT_CONFIGURED.configured, false);
  assert.equal(setupCommand(NOT_CONFIGURED.home), "agentpay init --home /home/op/.dsh/face/agentpay --from-deployment <name> --key 0x…");
  assert.equal(setupCommand(undefined), "agentpay init --home $DSH_HOME/face/agentpay --from-deployment <name> --key 0x…");
  assert.equal(hasAlerts(NOT_CONFIGURED), false);
  // The projections tolerate the fields being absent: no rows, no alerts, no figures.
  assert.deepEqual(mandateRows((NOT_CONFIGURED as Record<string, unknown>).mandates, NOW), []);
  assert.deepEqual(paymentRows((NOT_CONFIGURED as Record<string, unknown>).payments, undefined), []);
  assert.deepEqual(groupAlerts((NOT_CONFIGURED as Record<string, unknown>).alerts), { warn: [], info: [], total: 0 });
  assert.deepEqual(spendRows(undefined), { settled: "—", pending: "—", unattributed: "—", byChannel: [], bySession: [] });
});

test("an empty configured wallet has a balance, an address line and no rows or alerts", () => {
  assert.deepEqual(balanceView(EMPTY.balance), { text: "$10.000000", available: true, at: "2026-09-20T11:59:29.000Z", reason: null });
  assert.deepEqual(mandateRows(EMPTY.mandates, NOW), []);
  assert.deepEqual(paymentRows(EMPTY.payments, EMPTY.network), []);
  assert.deepEqual(spendRows(EMPTY.spend), { settled: "$0.000000", pending: "$0.000000", unattributed: "$0.000000", byChannel: [], bySession: [] });
  assert.equal(hasAlerts(EMPTY), false);
});

/* The alerts block groups by level and keeps a kind it has never heard of
 * (Rule 5), dropping only entries with no text to show. */
test("alerts group by level, keep unknown kinds and drop textless entries", () => {
  const { warn, info, total } = groupAlerts(FULL.alerts);
  assert.equal(total, 9);
  assert.deepEqual(warn.map((a) => a.kind), ["budget_exhausted", "budget_low", "balance_low", "unexplained_outflow", "unverified_mandate", "something_new"]);
  assert.deepEqual(info.map((a) => a.kind), ["unknown_rows", "expiring", "rpc_unavailable"]);
  assert.equal(warn[0].mandate, "im_cc3f74a85f72");
  assert.equal("mandate" in warn[2], false);
  assert.equal(hasAlerts(FULL), true);
  assert.equal(hasAlerts({ alerts: [{ kind: "malformed" }] }), false);
  assert.equal(hasAlerts(null), false);
});

test("an unavailable balance is a word with its reason, never a zero", () => {
  assert.deepEqual(balanceView(FULL.balance), { text: "unavailable", available: false, at: null, reason: "rpc did not answer within 3s" });
  assert.deepEqual(balanceView(undefined), { text: "—", available: false, at: null, reason: null });
  assert.deepEqual(balanceView({ usd: "abc" }), { text: "—", available: false, at: null, reason: null });
});

/* The mandate row: effective remaining is what the server sent (over the
 * chain, §4.1), the percentage is derived from it, and the status a row wears
 * is disabled > unverified > stored. Expiry is judged against the passed
 * instant, so a fixture expired an hour ago says so and one valid until next
 * week does not. */
test("mandate rows carry holder, effective remaining, percentage, expiry and a status the badge can wear", () => {
  const rows = mandateRows(FULL.mandates, NOW);
  assert.equal(rows.length, 5);
  const [root, child, disabled, unverified, draft] = rows;
  assert.equal(root.holder, "Kairos");
  assert.equal(root.isChild, false);
  assert.equal(root.remaining, "$4.977000");
  assert.equal(root.limit, "$5.000000");
  assert.equal(root.pct, 99); // 99.54 floors to 99: the figure never says more is left than there is
  assert.equal(root.perCall, "$0.010000");
  assert.equal(root.category, "data");
  assert.equal(root.expired, false);
  assert.equal(root.status, "signed");

  assert.equal(child.holder, "子任务 · 0a1b2c3d");
  assert.equal(child.isChild, true);
  assert.equal(child.parentId, "im_1f3218efc2a7");
  assert.equal(child.pct, 0);
  assert.equal(child.expired, true); // valid_until 11:00Z, NOW is 12:00Z
  assert.equal(child.status, "signed");

  assert.equal(disabled.status, "disabled");
  assert.equal(disabled.perCall, "—");
  assert.equal(disabled.pct, 38);

  assert.equal(unverified.holder, "会话 · ffeeddcc");
  assert.equal(unverified.status, "unverified");

  assert.equal(draft.status, "draft");
  assert.equal(draft.pct, null); // a zero limit has no percentage, not 100 %
});

test("mandate status precedence and the holder vocabulary", () => {
  assert.equal(mandateStatus({ status: "signed", enabled: false, unverified: true }), "disabled");
  assert.equal(mandateStatus({ status: "signed", enabled: true, unverified: true }), "unverified");
  assert.equal(mandateStatus({ status: "draft", enabled: true }), "draft");
  assert.equal(mandateStatus({}), "unknown");
  assert.equal(holderLabel(undefined), "Kairos");
  assert.equal(holderLabel(""), "Kairos");
  assert.equal(holderLabel("children:session-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"), "子任务 · 0a1b2c3d");
  assert.equal(holderLabel("session:session-ffeeddcc-0000-4000-8000-000000000001"), "会话 · ffeeddcc");
  assert.equal(holderLabel("bot:drill-bull"), "bot:drill-bull"); // agentpay's vocabulary, shown as written
  assert.equal(remainingPct("4.977", "5"), 99);
  assert.equal(remainingPct("5", "5"), 100);
  assert.equal(remainingPct("0.5", "5"), 10);
  assert.equal(remainingPct("0.01", "1"), 1);
  assert.equal(remainingPct("0.009", "1"), 0);
  assert.equal(remainingPct("-1", "5"), 0);
  assert.equal(remainingPct("9", "5"), 100);
  assert.equal(remainingPct("1", "0"), null);
  assert.equal(remainingPct(undefined, "5"), null);
});

/* Payments: newest first as delivered; the tx link resolved against the
 * wallet's network; the attribution read from `context` (decision 4). */
test("payment rows link a real tx on Base Sepolia, print an unlinkable one, and attribute by channel name and short session", () => {
  const rows = paymentRows(FULL.payments, FULL.network);
  assert.equal(rows.length, 3);
  const [settled, rejected, unknown] = rows;
  assert.equal(settled.resource, "GET /predict");
  assert.equal(settled.host, "api.example.com");
  assert.equal(settled.amount, "$0.001000");
  assert.equal(settled.status, "settled");
  assert.equal(settled.error, null);
  assert.equal(settled.http, "200");
  assert.equal(settled.txShort, "0xe833f1…9c9d");
  assert.equal(settled.txHref, `https://sepolia.basescan.org/tx/${FULL.payments[0].tx}`);
  assert.deepEqual(settled.context, { primary: "aapl-momentum", secondary: "0a1b2c3d · 子任务" });

  assert.equal(rejected.status, "rejected");
  assert.equal(rejected.error, "invalid_exact_evm_insufficient_balance");
  assert.equal(rejected.http, "402");
  assert.equal(rejected.tx, null);
  assert.equal(rejected.txShort, "—");
  assert.equal(rejected.txHref, null);
  assert.deepEqual(rejected.context, { primary: "5b0b3c2a…", secondary: "99999999" }); // no channelName: the workspace id's first block

  assert.equal(unknown.status, "unknown");
  assert.equal(unknown.tx, "not-a-hash");
  assert.equal(unknown.txHref, null); // printed, never linked
  assert.deepEqual(unknown.context, { primary: "—", secondary: "—" });

  // The local chain has no explorer: the same settled row loses its link and keeps its text.
  assert.equal(paymentRows(FULL.payments, "eip155:31337")[0].txHref, null);
  assert.equal(paymentRows(FULL.payments, "eip155:31337")[0].txShort, "0xe833f1…9c9d");
  assert.deepEqual(paymentContext({ label: "backfill", session: "session-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d" }), { primary: "—", secondary: "0a1b2c3d · backfill" });
});

test("spend groups by strategy (keyed by workspace id, named) and by session, largest first", () => {
  const spend = spendRows(FULL.spend);
  assert.equal(spend.settled, "$0.025000");
  assert.equal(spend.pending, "$0.001000");
  assert.equal(spend.unattributed, "$0.000000");
  assert.deepEqual(spend.byChannel, [
    { id: "5b0b3c2a-1111-4222-8333-444455556666", name: "aapl-momentum", usd: "$0.013000" },
    { id: "7c7c7c7c-2222-4333-8444-555566667777", name: "market-sentiment", usd: "$0.012000" },
  ]);
  assert.deepEqual(spend.bySession, [
    { session: "session-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d", short: "0a1b2c3d", usd: "$0.013000" },
    { session: "session-99999999-4e5f-4a6b-8c7d-9e0f1a2b3c4d", short: "99999999", usd: "$0.012000" },
  ]);
  // A channel with no name shows its id; a malformed value shows a dash, never zero.
  assert.deepEqual(spendRows({ by_channel: { abc: {} } }).byChannel, [{ id: "abc", name: "abc", usd: "—" }]);
});

/* The pay card's one line, spec §2 verbatim: `$0.001 · GET
 * api.example.com/predict · settled · tx 0xe833…9c9d`; `refused before
 * signing · <reason>`; `402 · <reason>`. The three are told apart by `ok`
 * and by whether an HTTP status exists — a refusal without one never left
 * the face. */
test("the pay line and its fields, for a settled call, a pre-signing refusal and a 402", () => {
  assert.equal(payLine(PAY_OK), "$0.001 · GET api.example.com/predict · settled · tx 0xe833…9c9d");
  assert.equal(payStatus(PAY_OK), "settled");
  assert.deepEqual(payFields(PAY_OK), [
    ["amount", "$0.001000"], ["resource", "GET /predict"], ["host", "api.example.com"],
    ["url", "https://api.example.com/predict"], ["http", "200"], ["ledger", "settled"],
    ["mandate", "im_1f3218efc2a7"], ["remaining", "$4.977000"],
    ["tx", "0xe833f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c9c9d"],
  ]);

  assert.equal(payLine(PAY_REFUSED), "refused before signing · mandate_insufficient_budget · Remaining budget 0 is below the price 1000 (atomic units).");
  assert.deepEqual(payFields(PAY_REFUSED), [
    ["error", "mandate_insufficient_budget"], ["url", "https://api.example.com/quote/ETH-USD"], ["host", "api.example.com"],
    ["reason", "mandate_insufficient_budget"], ["summary", "Remaining budget 0 is below the price 1000 (atomic units)."],
    ["next", "Do not retry: the same call will be refused until the budget changes."],
    ["", "Ask the user to approve a larger or additional intent mandate."],
    ["mandateId", "im_cc3f74a85f72"], ["remaining", "0"], ["price", "1000"],
  ]);

  assert.equal(payLine(PAY_402), "402 · invalid_exact_evm_insufficient_balance · The payer holds less USDC than the price.");
  assert.equal(payFields(PAY_402)[1][0], "http");
  assert.equal(payFields(PAY_402)[1][1], "402");

  // A paid:false 2xx (the resource was free) and a paid call the ledger has not reconciled.
  assert.equal(payLine({ ok: true, status: 200, paid: false, resource: "GET /free", host: "h" }), "free · GET h/free · free");
  assert.equal(payStatus({ ok: true, paid: true }), "unknown");
  assert.equal(payLine({ ok: true, paid: true, amount_usd: "0.5", body_truncated: true }), "$0.50 · — · unknown");
  assert.deepEqual(payFields({ ok: true, paid: true, amount_usd: "0.5", body_truncated: true }), [["amount", "$0.500000"], ["ledger", "unknown"], ["body", "truncated to 8 KB — raw has what was kept"]]);
  assert.equal(payLine({ ok: false }), "refused before signing · refused");
});

/* A bought file (bought-data spec): the line says it was kept and how big,
 * the fields name the path, the size, the sha256 receipt (short) and the
 * preview; the body is absent by contract, so no `body` row appears. A
 * `saved.error` (paid for, over the cap) is named as not saved. */
test("a saved pay envelope: the line's size, the file fields, the preview; a failed save is named", () => {
  assert.equal(fileSize(0), "0 B");
  assert.equal(fileSize(512), "512 B");
  assert.equal(fileSize(23621), "23.1 KB");
  assert.equal(fileSize(1024 * 1024 * 1.25), "1.3 MB");
  assert.equal(fileSize("23621"), "—");
  assert.equal(fileSize(-1), "—");
  assert.deepEqual(savedFile(PAY_SAVED), {
    path: "massive/AAPL/2016-01-01_2016-12-31.json", bytes: 23621, size: "23.1 KB",
    sha256: "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", contentType: "application/json",
  });
  assert.equal(savedFile(PAY_OK), null);
  assert.equal(savedFile({ saved: { error: "body_too_large", path: "x", bytes: 1 } }), null, "no sha256, no file");
  assert.equal(payLine(PAY_SAVED), "$0.01 · GET api.massive.example/v2/aggs/ticker/AAPL/range/1/day/2016-01-01/2016-12-31 · settled · tx 0xe833…9c9d · saved 23.1 KB");
  const fields = payFields(PAY_SAVED);
  assert.deepEqual(fields.slice(-5), [
    ["file", "massive/AAPL/2016-01-01_2016-12-31.json"], ["size", "23.1 KB"], ["sha256", "9f86d081…f00a08"], ["type", "application/json"],
    ["preview", `${PAY_SAVED.preview}…`],
  ]);
  assert.ok(!fields.some(([k]) => k === "body"));
  const tooBig = payFields({ ok: true, paid: true, amount_usd: "0.01", saved: { error: "body_too_large", path: "big.json", bytes: 40_000_000, limit: 33_554_432 } });
  assert.deepEqual(tooBig.at(-1), ["file", "not saved · body_too_large · big.json"]);
  assert.equal(payLine({ ok: true, paid: true, amount_usd: "0.01", saved: { error: "body_too_large" } }), "$0.01 · — · unknown");
  /* The /wallet table: the row's label becomes its file column; a row with none has null. */
  const rows = paymentRows([PAY_SAVED_ROW, FULL.payments[0]], "eip155:84532");
  assert.equal(rows[0].file, "massive/AAPL/2016-01-01_2016-12-31.json");
  assert.equal(rows[1].file, null);
});

/** The page's row for the PAY_SAVED payment (spec §4.4 `paymentView`): the label rides in `context`. */
const PAY_SAVED_ROW = {
  nonce: "0xaa11", at: "2026-09-20T11:59:00.000Z", url: PAY_SAVED.url, host: PAY_SAVED.host, resource: PAY_SAVED.resource,
  amount_usd: "0.010000", mandate: "im_1f3218efc2a7", status: "settled", tx: PAY_SAVED.tx, http_status: 200, context: PAY_SAVED.context,
};
