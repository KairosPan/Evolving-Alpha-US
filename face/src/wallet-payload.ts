/** `/data/wallet.json`'s body, as pure functions of what the wallet holds.
 *
 * Split out of `wallet.ts` so the page's contract (spec
 * `docs/superpowers/specs/2026-09-20-agent-wallet-design.md` §4.4) is a
 * function of `(report, mandates, ledger rows, balance, now)` and nothing
 * else — no key, no RPC, no clock but the one passed in — the way
 * `market-model.js` and `wallet-model.js` are pure on the client side. Every
 * amount leaves here as a USD string with six decimals (`"0.001000"`); atomic
 * units never reach the client. Nothing in this module can throw on a row it
 * did not expect: a hand-edited store degrades to a stranger-looking row, not
 * to a blank page.
 * @module
 */

/** agentpay's `IntentMandate`, narrowed to what the page shows (never
 * `signature`/`mandateHash`: signing material stays in the store). */
export interface MandateLike {
  id: string;
  naturalLanguage: string;
  holder?: string;
  parentId?: string;
  category?: string;
  /** Atomic units, decimal strings. */
  limitAmount: string;
  spentAmount: string;
  pendingSpentAmount: string;
  perCallMax?: string;
  maxCallsPerMinute?: number;
  /** Unix seconds. */
  validFrom: number;
  validUntil: number;
  status: string;
  isEnabled: boolean;
}

/** agentpay's `LedgerEntry`, narrowed the same way (never `signature` or
 * `authorization`). */
export interface LedgerRowLike {
  nonce: string;
  /** Unix seconds of the last status change (`updateStatus` moves it). */
  timestamp: number;
  /** Unix seconds at signing; the row's own moment, never patched. */
  signedAt?: number;
  url: string;
  host: string;
  resource: string;
  amount: string;
  intentMandateId: string;
  status: string;
  error?: string;
  transaction?: string;
  httpStatus: number;
  context?: Record<string, string | undefined>;
}

/** The two totals the page needs of agentpay's `SpendReport`: root-only
 * sums, so a chain is never double-counted (spec §4.1 "Chain accounting"). */
export interface ReportTotalsLike {
  totals: { spent: string; pending: string };
}

/** What the face remembers between two looks at the page, for the outflow
 * alert (spec §2): the balance it last saw and what the ledger had settled by
 * then, both atomic. Kept in `<home>/face-state.json`. */
export interface FaceState {
  last_balance?: string;
  ledger_settled_at_that_time?: string;
}

/** One alert as the page groups it. */
export interface WalletAlert {
  kind: "budget_exhausted" | "budget_low" | "balance_low" | "unknown_rows" | "expiring"
    | "unexplained_outflow" | "unverified_mandate" | "rpc_unavailable";
  level: "warn" | "info";
  text: string;
  mandate?: string;
}

/** The balance as the route read it: a reading, or why there is none.
 * `ledgerSpent` is the ledger's settled total (atomic) AS OF the reading —
 * the outflow anchor pairs the two from one moment, because a reading is
 * served from cache for a minute while the ledger keeps moving. Absent (a
 * caller that did not capture it), the current report's total stands in. */
export type BalanceReading = { atomic: bigint; at: number; ledgerSpent?: string } | { unavailable: string };

/** Everything {@link buildWalletPayload} is a function of. */
export interface WalletPayloadInput {
  home: string;
  address: string;
  network: string;
  token: string;
  deployment?: string;
  report: ReportTotalsLike;
  mandates: MandateLike[];
  /** `effectiveRemaining(id)` per mandate, atomic — the chain-aware figure. */
  remaining: (id: string) => bigint;
  rows: LedgerRowLike[];
  balance: BalanceReading;
  /** Ids `verifyMandates()` named: their signature does not recover to the payer. */
  unverified: ReadonlySet<string>;
  state: FaceState;
  reconcile?: { at: string; settled: number; expired_unused: number; still_pending: number; error?: string };
  /** Unix milliseconds. */
  now: number;
}

/** Atomic USDC (six decimals) as the page's USD string. Total over any
 * decimal string: a value that is not one reads as zero rather than throwing
 * — the page is a report, and a bad row must not blank it. */
export function usd(atomic: bigint | string | undefined): string {
  let value: bigint;
  try {
    value = typeof atomic === "bigint" ? atomic : BigInt(atomic ?? "0");
  } catch {
    value = 0n;
  }
  const sign = value < 0n ? "-" : "";
  const digits = (value < 0n ? -value : value).toString().padStart(7, "0");
  return `${sign}${digits.slice(0, -6)}.${digits.slice(-6)}`;
}

const big = (value: string | undefined): bigint => {
  try {
    return BigInt(value ?? "0");
  } catch {
    return 0n;
  }
};

const iso = (unixSeconds: number): string => new Date(unixSeconds * 1000).toISOString();

/** Rows whose amount left the wallet, or may have: settled, plus `unknown`
 * (delivered without a usable settlement report) — the same two statuses
 * agentpay's `report()` sums (`pay:packages/wallet/src/wallet.ts` `isSpendStatus`). */
const isSpend = (status: string): boolean => status === "settled" || status === "unknown";

/** A mandate row as spec §4.4 lists it, snake_case, remaining over the chain. */
export function mandateView(m: MandateLike, effectiveRemaining: bigint, unverified: boolean): Record<string, unknown> {
  return {
    id: m.id,
    purpose: m.naturalLanguage,
    ...(m.holder ? { holder: m.holder } : {}),
    ...(m.parentId ? { parent_id: m.parentId } : {}),
    ...(m.category ? { category: m.category } : {}),
    limit_usd: usd(m.limitAmount),
    spent_usd: usd(m.spentAmount),
    pending_usd: usd(m.pendingSpentAmount),
    remaining_usd: usd(effectiveRemaining),
    ...(m.perCallMax !== undefined ? { per_call_usd: usd(m.perCallMax) } : {}),
    ...(m.maxCallsPerMinute !== undefined ? { max_calls_per_minute: m.maxCallsPerMinute } : {}),
    valid_from: iso(m.validFrom),
    valid_until: iso(m.validUntil),
    status: m.status,
    enabled: m.isEnabled,
    ...(unverified ? { unverified: true as const } : {}),
  };
}

/** The context keys the ledger stores (`PAYMENT_CONTEXT_KEYS`), copied one by
 * one so a row's context never carries anything the page did not ask for. */
const CONTEXT_KEYS = ["channel", "channelName", "session", "parentSession", "origin", "callId", "label"] as const;

/** When a row happened: its signing time, which a later reconcile does not
 * move (`timestamp` does — it is the last status change). */
const whenOf = (row: LedgerRowLike): number => row.signedAt ?? row.timestamp;

/** A ledger row as spec §4.4 lists it. */
export function paymentView(row: LedgerRowLike): Record<string, unknown> {
  const context: Record<string, string> = {};
  for (const key of CONTEXT_KEYS) {
    const value = row.context?.[key];
    if (typeof value === "string") context[key] = value;
  }
  return {
    nonce: row.nonce,
    at: iso(whenOf(row)),
    url: row.url,
    host: row.host,
    resource: row.resource,
    amount_usd: usd(row.amount),
    mandate: row.intentMandateId,
    status: row.status,
    ...(row.error !== undefined ? { error: row.error } : {}),
    ...(row.transaction !== undefined ? { tx: row.transaction } : {}),
    http_status: row.httpStatus,
    ...(Object.keys(context).length > 0 ? { context } : {}),
  };
}

/** Spend by channel and by session, keyed by WORKSPACE id (spec §9: basename
 * keying missed the workbench), the channel's name carried beside its figure
 * (the last name a row recorded for that id — a renamed directory reports its
 * current name). Rows with no channel are `unattributed` — a shell turn
 * running the CLI, R-W3 — and are counted, not hidden. */
export function spendOf(report: ReportTotalsLike, rows: readonly LedgerRowLike[]): {
  settled_usd: string;
  pending_usd: string;
  by_channel: Record<string, { name: string; usd: string }>;
  by_session: Record<string, string>;
  unattributed_usd: string;
} {
  const byChannel = new Map<string, { name: string; atomic: bigint }>();
  const bySession = new Map<string, bigint>();
  let unattributed = 0n;
  for (const row of rows) {
    if (!isSpend(row.status)) continue;
    const amount = big(row.amount);
    const channel = row.context?.channel;
    if (typeof channel === "string" && channel !== "") {
      const have = byChannel.get(channel) ?? { name: "", atomic: 0n };
      const name = row.context?.channelName;
      byChannel.set(channel, { name: typeof name === "string" && name !== "" ? name : have.name, atomic: have.atomic + amount });
    } else {
      unattributed += amount;
    }
    const session = row.context?.session;
    if (typeof session === "string" && session !== "") bySession.set(session, (bySession.get(session) ?? 0n) + amount);
  }
  return {
    settled_usd: usd(report.totals.spent),
    pending_usd: usd(report.totals.pending),
    by_channel: Object.fromEntries([...byChannel].map(([id, v]) => [id, { name: v.name, usd: usd(v.atomic) }])),
    by_session: Object.fromEntries([...bySession].map(([id, v]) => [id, usd(v)])),
    unattributed_usd: usd(unattributed),
  };
}

/** One channel's settled total and count, for the landing page's tile
 * (`ChannelRouteDeps.spendFor`); `null` when the channel has no payment, so
 * the overview omits the field rather than showing a zero tile. */
export function channelSpend(rows: readonly LedgerRowLike[], workspaceId: string): { settled_usd: string; count: number } | null {
  let atomic = 0n;
  let count = 0;
  for (const row of rows) {
    if (row.status !== "settled" || row.context?.channel !== workspaceId) continue;
    atomic += big(row.amount);
    count += 1;
  }
  return count === 0 ? null : { settled_usd: usd(atomic), count };
}

/** A mandate that can still be spent from: signed, enabled, inside its window. */
const isLive = (m: MandateLike, nowSec: number): boolean =>
  m.status === "signed" && m.isEnabled && m.validFrom <= nowSec && m.validUntil > nowSec;

/**
 * The alerts block (spec §2): what an operator should look at, in the order
 * the page groups them. Every kind is computed here, from the same inputs the
 * page shows, so an alert never says something the rows beside it contradict.
 *
 * `unexplained_outflow` compares two deltas since the face last looked: how
 * much the balance FELL and how much the ledger SETTLED. A fall larger than
 * the settlement is money that left by a path the ledger did not see — the
 * CLI or raw-key spend D16 admits, made visible. Only decidable when both
 * readings exist; the first look, and any look without a balance, records
 * nothing and alerts nothing.
 */
export function alertsOf(input: Pick<WalletPayloadInput, "mandates" | "remaining" | "rows" | "balance" | "unverified" | "state" | "report" | "now">): WalletAlert[] {
  const alerts: WalletAlert[] = [];
  const nowSec = Math.floor(input.now / 1000);
  let rootRemaining = 0n;
  for (const m of input.mandates) {
    if (!isLive(m, nowSec)) continue;
    const remaining = input.remaining(m.id);
    const limit = big(m.limitAmount);
    if (m.parentId === undefined) rootRemaining += remaining;
    if (limit > 0n && remaining <= 0n) {
      alerts.push({ kind: "budget_exhausted", level: "warn", text: `${m.id} has ${usd(remaining)} of ${usd(limit)} left`, mandate: m.id });
    } else if (limit > 0n && remaining * 10n < limit) {
      alerts.push({ kind: "budget_low", level: "warn", text: `${m.id} is under 10 % (${usd(remaining)} of ${usd(limit)} left)`, mandate: m.id });
    }
  }
  if ("atomic" in input.balance && input.balance.atomic < rootRemaining) {
    alerts.push({ kind: "balance_low", level: "warn", text: `balance ${usd(input.balance.atomic)} is below the sum of root budgets' remaining ${usd(rootRemaining)}` });
  }
  const unknown = input.rows.filter((row) => row.status === "unknown").length;
  if (unknown > 0) alerts.push({ kind: "unknown_rows", level: "info", text: `${unknown} payment${unknown === 1 ? "" : "s"} await${unknown === 1 ? "s" : ""} reconcile` });
  for (const m of input.mandates) {
    if (isLive(m, nowSec) && m.validUntil - nowSec < 86_400) {
      alerts.push({ kind: "expiring", level: "info", text: `${m.id} expires within a day (${iso(m.validUntil)})`, mandate: m.id });
    }
  }
  if ("atomic" in input.balance && input.state.last_balance !== undefined && input.state.ledger_settled_at_that_time !== undefined) {
    const fell = big(input.state.last_balance) - input.balance.atomic;
    const settled = settledAsOf(input) - big(input.state.ledger_settled_at_that_time);
    if (fell > settled) {
      alerts.push({ kind: "unexplained_outflow", level: "warn", text: `balance fell ${usd(fell - settled)} more than the ledger settled since the last look` });
    }
  }
  for (const id of input.unverified) {
    alerts.push({ kind: "unverified_mandate", level: "warn", text: `${id}'s signature does not recover to the payer; it was disabled`, mandate: id });
  }
  if ("unavailable" in input.balance) alerts.push({ kind: "rpc_unavailable", level: "info", text: `balance unavailable: ${input.balance.unavailable}` });
  return alerts;
}

/** How many payments the page lists, newest first. */
export const MAX_PAYMENTS = 50;

/** The configured body of `/data/wallet.json` (spec §4.4, second shape),
 * minus the `ok: true` the route shell adds. */
export function buildWalletPayload(input: WalletPayloadInput): Record<string, unknown> {
  /* Newest first. The ledger's seconds tie rows signed in one second, so the
   * file order (append order) breaks the tie: reversed, then a STABLE sort. */
  const rows = [...input.rows].reverse().sort((a, b) => whenOf(b) - whenOf(a));
  const balance = "atomic" in input.balance
    ? { usd: usd(input.balance.atomic), at: new Date(input.balance.at).toISOString() }
    : { unavailable: input.balance.unavailable };
  return {
    configured: true,
    generated_at: new Date(input.now).toISOString(),
    home: input.home,
    address: input.address,
    network: input.network,
    token: input.token,
    ...(input.deployment !== undefined ? { deployment: input.deployment } : {}),
    balance,
    mandates: input.mandates.map((m) => mandateView(m, input.remaining(m.id), input.unverified.has(m.id))),
    payments: rows.slice(0, MAX_PAYMENTS).map(paymentView),
    spend: spendOf(input.report, rows),
    ...(input.reconcile !== undefined ? { reconcile: input.reconcile } : {}),
    alerts: alertsOf(input),
  };
}

/** The ledger's settled total as of the balance reading (see {@link BalanceReading}). */
const settledAsOf = (input: Pick<WalletPayloadInput, "balance" | "report">): bigint =>
  "atomic" in input.balance && input.balance.ledgerSpent !== undefined ? big(input.balance.ledgerSpent) : big(input.report.totals.spent);

/** The state to remember after this look, or `undefined` to leave the file
 * alone: only a look that READ the balance can anchor the next outflow check,
 * and the ledger figure beside it is the one from the reading's own moment. */
export function nextFaceState(input: Pick<WalletPayloadInput, "balance" | "report">): FaceState | undefined {
  if (!("atomic" in input.balance)) return undefined;
  return { last_balance: input.balance.atomic.toString(), ledger_settled_at_that_time: settledAsOf(input).toString() };
}
