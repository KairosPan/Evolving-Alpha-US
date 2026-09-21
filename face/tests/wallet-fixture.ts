// face/tests/wallet-fixture.ts
/** Three `/data/wallet.json` bodies and the two `wallet_pay` envelopes, in
 *  the exact shapes spec §4.4 (2026-09-20-agent-wallet-design.md) pins for
 *  the server ↔ client contract. Amounts are USD STRINGS with six decimals,
 *  times ISO-8601 UTC. The full wallet is the Base Sepolia run's vocabulary
 *  (eip155:84532, a 0x tx) plus one local-chain payment, one child mandate,
 *  one disabled and one unverified one, and every alert kind the page groups.
 *  The server route lands later; until it does, this is the only reader of
 *  the contract on the client side. */

/** The instant the "full" fixture is read at, for the expiry mark. */
export const NOW = Date.parse("2026-09-20T12:00:00Z");

export const NOT_CONFIGURED = {
  ok: true,
  configured: false,
  reason: "no config.json at /home/op/.dsh/face/agentpay",
  home: "/home/op/.dsh/face/agentpay",
};

/** A configured wallet that has never held a mandate or paid for anything. */
export const EMPTY = {
  ok: true,
  configured: true,
  generated_at: "2026-09-20T11:59:30.000Z",
  home: "/home/op/.dsh/face/agentpay",
  address: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
  network: "eip155:31337",
  token: "USDC",
  deployment: "localhost",
  balance: { usd: "10.000000", at: "2026-09-20T11:59:29.000Z" },
  mandates: [],
  payments: [],
  spend: { settled_usd: "0.000000", pending_usd: "0.000000", by_channel: {}, by_session: {}, unattributed_usd: "0.000000" },
  alerts: [],
};

export const FULL = {
  ok: true,
  configured: true,
  generated_at: "2026-09-20T11:59:30.000Z",
  home: "/home/op/.dsh/face/agentpay",
  address: "0x90F79bf6EB2c4f870365E785982E1f101E93b906",
  network: "eip155:84532",
  token: "USDC",
  deployment: "baseSepolia",
  balance: { unavailable: "rpc did not answer within 3s" },
  mandates: [
    {
      id: "im_1f3218efc2a7", purpose: "market data for AAPL thesis", category: "data",
      limit_usd: "5.000000", spent_usd: "0.022000", pending_usd: "0.001000", remaining_usd: "4.977000",
      per_call_usd: "0.010000", max_calls_per_minute: 30,
      valid_from: "2026-09-19T12:00:00.000Z", valid_until: "2026-09-26T12:00:00.000Z",
      status: "signed", enabled: true,
    },
    {
      id: "im_cc3f74a85f72", purpose: "three quotes", parent_id: "im_1f3218efc2a7",
      holder: "children:session-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
      limit_usd: "0.003000", spent_usd: "0.003000", pending_usd: "0.000000", remaining_usd: "0.000000",
      per_call_usd: "0.001000",
      valid_from: "2026-09-20T10:00:00.000Z", valid_until: "2026-09-20T11:00:00.000Z",
      status: "signed", enabled: true,
    },
    {
      id: "im_a91c5e0d27b4", purpose: "backtest dataset (retired channel)",
      limit_usd: "20.000000", spent_usd: "12.400000", pending_usd: "0.000000", remaining_usd: "7.600000",
      valid_from: "2026-09-01T00:00:00.000Z", valid_until: "2026-09-30T00:00:00.000Z",
      status: "signed", enabled: false,
    },
    {
      id: "im_7d02c41e9b50", purpose: "news full text", holder: "session:session-ffeeddcc-0000-4000-8000-000000000001",
      limit_usd: "3.000000", spent_usd: "0.000000", pending_usd: "0.000000", remaining_usd: "3.000000",
      valid_from: "2026-09-20T00:00:00.000Z", valid_until: "2026-09-21T00:00:00.000Z",
      status: "signed", enabled: true, unverified: true,
    },
    {
      id: "im_0000000draft", purpose: "a CLI draft", limit_usd: "0.000000", spent_usd: "0.000000",
      pending_usd: "0.000000", remaining_usd: "0.000000",
      valid_from: "2026-09-20T00:00:00.000Z", valid_until: "2026-09-27T00:00:00.000Z",
      status: "draft", enabled: true,
    },
  ],
  payments: [
    {
      nonce: "0xf2424453a1b2c3d4e5f60718293a4b5c6d7e8f9011223344556677889900aabb",
      at: "2026-09-20T11:58:00.000Z", url: "https://api.example.com/predict", host: "api.example.com",
      resource: "GET /predict", amount_usd: "0.001000", mandate: "im_1f3218efc2a7", status: "settled",
      tx: "0xe833f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c9c9d", http_status: 200,
      context: { channel: "5b0b3c2a-1111-4222-8333-444455556666", channelName: "aapl-momentum",
        session: "session-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d", origin: "subagent", callId: "call_1" },
    },
    {
      nonce: "0x5c0e19b3", at: "2026-09-20T11:50:00.000Z", url: "https://api.example.com/analyze",
      host: "api.example.com", resource: "POST /analyze", amount_usd: "0.010000", mandate: "im_1f3218efc2a7",
      status: "rejected", error: "invalid_exact_evm_insufficient_balance", http_status: 402,
      context: { channel: "5b0b3c2a-1111-4222-8333-444455556666", session: "session-99999999-4e5f-4a6b-8c7d-9e0f1a2b3c4d" },
    },
    {
      nonce: "0x3ecce516", at: "2026-09-20T11:40:00.000Z", url: "https://api.example.com/quote/AAPL",
      host: "api.example.com", resource: "GET /quote/AAPL", amount_usd: "0.001000", mandate: "im_1f3218efc2a7",
      status: "unknown", tx: "not-a-hash", http_status: 200,
    },
  ],
  spend: {
    settled_usd: "0.025000", pending_usd: "0.001000",
    by_channel: {
      "5b0b3c2a-1111-4222-8333-444455556666": { name: "aapl-momentum", usd: "0.013000" },
      "7c7c7c7c-2222-4333-8444-555566667777": { name: "market-sentiment", usd: "0.012000" },
    },
    by_session: {
      "session-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d": "0.013000",
      "session-99999999-4e5f-4a6b-8c7d-9e0f1a2b3c4d": "0.012000",
    },
    unattributed_usd: "0.000000",
  },
  reconcile: { at: "2026-09-20T11:59:00.000Z", settled: 1, expired_unused: 0, still_pending: 1 },
  alerts: [
    { kind: "budget_exhausted", level: "warn", text: "im_cc3f74a85f72 has $0.000000 of $0.003000 left", mandate: "im_cc3f74a85f72" },
    { kind: "budget_low", level: "warn", text: "im_1f3218efc2a7 is under 10 %", mandate: "im_1f3218efc2a7" },
    { kind: "balance_low", level: "warn", text: "balance is below the sum of root budgets' remaining" },
    { kind: "unknown_rows", level: "info", text: "1 payment awaits reconcile" },
    { kind: "expiring", level: "info", text: "im_7d02c41e9b50 expires within a day", mandate: "im_7d02c41e9b50" },
    { kind: "unexplained_outflow", level: "warn", text: "balance fell $1.000000 more than the ledger settled since the last look" },
    { kind: "unverified_mandate", level: "warn", text: "im_7d02c41e9b50's signature does not recover to the payer", mandate: "im_7d02c41e9b50" },
    { kind: "rpc_unavailable", level: "info", text: "balance unavailable: rpc did not answer within 3s" },
    { kind: "something_new", text: "an alert kind this client has never heard of" },
    { kind: "malformed" },
  ],
};

/** `wallet_pay`, settled (spec §4.4, first shape). */
export const PAY_OK = {
  ok: true, status: 200, paid: true, amount_usd: "0.001000", mandate: "im_1f3218efc2a7",
  remaining_usd: "4.977000", tx: "0xe833f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c9c9d",
  ledger_status: "settled", url: "https://api.example.com/predict", resource: "GET /predict",
  host: "api.example.com", body: { prediction: 0.61 },
};

/** `wallet_pay`, refused before signing (second shape, no HTTP status). */
export const PAY_REFUSED = {
  ok: false, error: "mandate_insufficient_budget",
  detail: { mandateId: "im_cc3f74a85f72", remaining: "0", price: "1000" },
  payment_model_context: {
    protocol: "x402", reason: "mandate_insufficient_budget",
    summary: "Remaining budget 0 is below the price 1000 (atomic units).",
    remediation: ["Do not retry: the same call will be refused until the budget changes.", "Ask the user to approve a larger or additional intent mandate."],
  },
  url: "https://api.example.com/quote/ETH-USD", host: "api.example.com",
};

/** `wallet_pay`, the payee answered 402 (second shape WITH a status). */
export const PAY_402 = {
  ok: false, status: 402, error: "invalid_exact_evm_insufficient_balance",
  payment_model_context: { protocol: "x402", reason: "invalid_exact_evm_insufficient_balance", summary: "The payer holds less USDC than the price.", remediation: [] },
  url: "https://api.example.com/analyze", host: "api.example.com",
};

/** `wallet_pay` with `save_to` (bought-data spec): the body went to a file
 *  under the channel's `vendor/`, so the envelope carries `saved` (the path
 *  relative to that root, the byte count, the sha256 receipt, the content
 *  type) and a 1 KB `preview` cut short, and NO `body`; the ledger row's
 *  label is the path. 23 621 bytes is what one year of Massive-shaped daily
 *  bars weighs (`23.1 KB` on the card). */
export const PAY_SAVED = {
  ok: true, status: 200, paid: true, amount_usd: "0.010000", mandate: "im_1f3218efc2a7",
  remaining_usd: "0.040000", tx: "0xe833f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c9c9d",
  ledger_status: "settled", url: "https://api.massive.example/v2/aggs/ticker/AAPL/range/1/day/2016-01-01/2016-12-31?adjusted=false",
  resource: "GET /v2/aggs/ticker/AAPL/range/1/day/2016-01-01/2016-12-31", host: "api.massive.example",
  network: "eip155:84532",
  context: { channel: "5b0b3c2a-1111-4222-8333-444455556666", channelName: "aapl-momentum",
    session: "session-0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d", callId: "call_7", label: "massive/AAPL/2016-01-01_2016-12-31.json" },
  saved: { path: "massive/AAPL/2016-01-01_2016-12-31.json", bytes: 23621,
    sha256: "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", content_type: "application/json" },
  preview: '{"ticker":"AAPL","adjusted":false,"status":"OK","results":[{"t":1451970000000,"o":102.61,"h":105.37',
  preview_truncated: true,
};
