/** Pure projections of the wallet payloads (spec §4.4) for the /wallet page
 * and the pay card.
 *
 * Everything here is a function of its argument and nothing else — no DOM, no
 * clock unless one is passed in — so `tests/wallet-model.test.ts` can pin every
 * rule under node --test while `wallet-view.js` and `render.js` stay the thin
 * DOM layers. The payloads are the two contracts in the design spec
 * (`docs/superpowers/specs/2026-09-20-agent-wallet-design.md` §4.4):
 * `GET /data/wallet.json` and the `wallet_*` tool values. Every amount crosses
 * as a USD STRING (`"0.001000"`); atomic units never reach the client, and no
 * function here ever re-derives one. Absent or malformed values render as an
 * em-dash rather than a zero: a missing balance is not a balance of nothing.
 * @module
 */

const EM = "—";

/** Where a settled payment can be looked up, by CAIP-2 network. Only the one
 * public testnet the wallet has settled on (Base Sepolia, agentpay README) has
 * an explorer; the local hardhat chain (`eip155:31337`) has none, so its tx is
 * printed but never linked — a link to nowhere reads as a broken page. */
const EXPLORERS = {
  "eip155:84532": "https://sepolia.basescan.org/tx/",
};

/** A USD string or number as a finite number, else `null`. The wallet's
 * amounts are strings by contract, but the rule tolerates a number so a tool
 * payload that slipped one through still reads — and refuses blanks, NaN and
 * infinities, which would otherwise print as a figure.
 * @param {unknown} value @returns {number | null} */
export function usdNumber(value) {
  if (typeof value !== "number" && typeof value !== "string") return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** `$0.001000`: six decimals, the USDC atomic precision, so two amounts on
 * the page always line up and a sub-cent price is never rounded to `$0.00`.
 * @param {unknown} value @returns {string} */
export function usd(value) {
  const parsed = usdNumber(value);
  if (parsed === null) return EM;
  const sign = parsed < 0 ? "-" : "";
  return `${sign}$${Math.abs(parsed).toLocaleString("en-US", { minimumFractionDigits: 6, maximumFractionDigits: 6 })}`;
}

/** `$0.001` / `$5.00`: the same amount with trailing zeros trimmed past two
 * decimals — the pay card's one-liner (spec §2: `$0.001 · GET …`) where a
 * six-digit tail would push the resource off the row.
 * @param {unknown} value @returns {string} */
export function usdCompact(value) {
  const parsed = usdNumber(value);
  if (parsed === null) return EM;
  const sign = parsed < 0 ? "-" : "";
  return `${sign}$${Math.abs(parsed).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 6 })}`;
}

/** A hex identifier shortened for a table cell: `0xe83312…9c9d`. Any string
 * is cut the same way — a nonce, a workspace id — but only when the cut saves
 * at least four characters; a mandate id (`im_` + 12 hex) stays whole, since
 * `im_1f321…c2a7` is no shorter to the eye and loses the part that tells two
 * apart.
 * @param {unknown} value @param {number} [head] @param {number} [tail]
 * @returns {string} */
export function shortHex(value, head = 8, tail = 4) {
  if (typeof value !== "string" || value === "") return EM;
  if (value.length <= head + tail + 4) return value;
  return `${value.slice(0, head)}…${value.slice(-tail)}`;
}

/** A dsh session id (`session-<uuid>`) as its first hex block, which is how
 * the chat's own tooltips and the room strip abbreviate one; anything else is
 * cut to eight characters.
 * @param {unknown} id @returns {string} */
export function shortSession(id) {
  if (typeof id !== "string" || id === "") return EM;
  const m = /^session-([0-9a-f]{8})/i.exec(id);
  return m ? m[1] : id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

/** The explorer URL for a settled tx, or `null` when the network has no
 * explorer (local chain) or the tx is not a `0x` hex hash.
 * @param {unknown} network - CAIP-2, e.g. `eip155:84532`.
 * @param {unknown} tx
 * @returns {string | null} */
export function txLink(network, tx) {
  if (typeof network !== "string" || typeof tx !== "string") return null;
  if (!/^0x[0-9a-f]{64}$/i.test(tx)) return null;
  const base = EXPLORERS[network];
  return base === undefined ? null : `${base}${tx}`;
}

/** The alert kinds §4.4 names. An unknown kind is still shown (Rule 5: a
 * warning the server thought worth raising is never dropped for its label),
 * under the level it declares, `warn` when it declares none. */
const ALERT_KINDS = new Set([
  "budget_exhausted", "budget_low", "balance_low", "unknown_rows", "expiring",
  "unexplained_outflow", "unverified_mandate", "rpc_unavailable",
]);

/** Alerts split by level, malformed entries (no text) dropped.
 * @param {unknown} alerts
 * @returns {{warn: Array<{kind: string, text: string, mandate?: string}>,
 *            info: Array<{kind: string, text: string, mandate?: string}>, total: number}} */
export function groupAlerts(alerts) {
  const warn = [], info = [];
  for (const alert of Array.isArray(alerts) ? alerts : []) {
    if (!alert || typeof alert !== "object" || typeof alert.text !== "string" || alert.text === "") continue;
    const kind = typeof alert.kind === "string" && ALERT_KINDS.has(alert.kind) ? alert.kind : String(alert.kind ?? "alert");
    const entry = { kind, text: alert.text };
    if (typeof alert.mandate === "string") entry.mandate = alert.mandate;
    (alert.level === "info" ? info : warn).push(entry);
  }
  return { warn, info, total: warn.length + info.length };
}

/** Whether the rail item should carry its dot (spec §2): any standing alert.
 * @param {unknown} data - the `/data/wallet.json` body. @returns {boolean} */
export function hasAlerts(data) {
  return data !== null && typeof data === "object" && groupAlerts(/** @type {any} */ (data).alerts).total > 0;
}

/** Who may spend a mandate, from its `holder` (spec §3 decision 5): none is
 * the principal's own; `children:<session>` the direct child tasks of that
 * session; `session:<id>` one session; `bot:<id>` a vocabulary agentpay keeps
 * for other hosts and the face never sets, shown as written.
 * @param {unknown} holder @returns {string} */
export function holderLabel(holder) {
  if (typeof holder !== "string" || holder === "") return "Kairos";
  const [kind, ...rest] = holder.split(":");
  const id = rest.join(":");
  if (kind === "children") return `子任务 · ${shortSession(id)}`;
  if (kind === "session") return `会话 · ${shortSession(id)}`;
  return holder;
}

/** Effective remaining as a percentage of the limit, 0–100, or `null` when
 * either is missing or the limit is not positive — a zero-limit mandate has
 * no percentage, not 100 %. Floored, not rounded: `$4.977 of $5` is 99 %,
 * and a budget with a cent left of a dollar is 0 %, not 1 % — the figure
 * must never say more is left than there is.
 * @param {unknown} remaining @param {unknown} limit @returns {number | null} */
export function remainingPct(remaining, limit) {
  const r = usdNumber(remaining), l = usdNumber(limit);
  if (r === null || l === null || l <= 0) return null;
  return Math.max(0, Math.min(100, Math.floor((r / l) * 100)));
}

/** The badge a mandate row wears. `disabled` beats everything (a reclaimed
 * budget cannot be spent whatever its signature says); an `unverified` row
 * — a signature that did not recover to the payer — is named as such rather
 * than as `signed`, which it would otherwise claim; else the stored status.
 * @param {{status?: unknown, enabled?: unknown, unverified?: unknown}} m
 * @returns {string} */
export function mandateStatus(m) {
  if (m.enabled === false) return "disabled";
  if (m.unverified === true) return "unverified";
  return typeof m.status === "string" && m.status !== "" ? m.status : "unknown";
}

/**
 * One table row per mandate, in the payload's order. `expired` is derived
 * against the `now` the caller passes (a test's fixed instant, the page's
 * `Date.now()`), never read from a clock in here.
 * @param {unknown} mandates - `data.mandates`.
 * @param {number} now - epoch ms.
 * @returns {Array<{id: string, purpose: string, holder: string, isChild: boolean, parentId: string | null,
 *   category: string | null, limit: string, spent: string, pending: string, remaining: string,
 *   pct: number | null, perCall: string, validUntil: string | null, expired: boolean, status: string}>}
 */
export function mandateRows(mandates, now) {
  const rows = [];
  for (const m of Array.isArray(mandates) ? mandates : []) {
    if (!m || typeof m !== "object") continue;
    const validUntil = typeof m.valid_until === "string" ? m.valid_until : null;
    const until = validUntil === null ? NaN : Date.parse(validUntil);
    rows.push({
      id: typeof m.id === "string" ? m.id : EM,
      purpose: typeof m.purpose === "string" && m.purpose !== "" ? m.purpose : EM,
      holder: holderLabel(m.holder),
      isChild: typeof m.parent_id === "string" && m.parent_id !== "",
      parentId: typeof m.parent_id === "string" && m.parent_id !== "" ? m.parent_id : null,
      category: typeof m.category === "string" && m.category !== "" ? m.category : null,
      limit: usd(m.limit_usd),
      spent: usd(m.spent_usd),
      pending: usd(m.pending_usd),
      remaining: usd(m.remaining_usd),
      pct: remainingPct(m.remaining_usd, m.limit_usd),
      perCall: m.per_call_usd === undefined || m.per_call_usd === null ? EM : usd(m.per_call_usd),
      validUntil,
      expired: Number.isFinite(until) && until < now,
      status: mandateStatus(m),
    });
  }
  return rows;
}

/** The attribution a payment carries (decision 4): the strategy first, by
 * name; the session as its short id; a child task's payment says so.
 * @param {unknown} context - a payment row's `context`.
 * @returns {{primary: string, secondary: string}} */
export function paymentContext(context) {
  const ctx = context && typeof context === "object" ? /** @type {Record<string, unknown>} */ (context) : {};
  // A workspace id is a UUID (dsh-workspace mints it); its first block is enough to tell two apart.
  const channel = typeof ctx.channelName === "string" && ctx.channelName !== "" ? ctx.channelName
    : typeof ctx.channel === "string" && ctx.channel !== "" ? `${ctx.channel.slice(0, 8)}…` : EM;
  const parts = [];
  if (typeof ctx.session === "string" && ctx.session !== "") parts.push(shortSession(ctx.session));
  if (ctx.origin === "subagent") parts.push("子任务");
  if (typeof ctx.label === "string" && ctx.label !== "") parts.push(ctx.label);
  return { primary: channel, secondary: parts.length ? parts.join(" · ") : EM };
}

/**
 * Payment rows for the table, newest first as the payload delivers them; the
 * tx link is resolved here so the view only decides between `<a>` and text.
 * @param {unknown} payments - `data.payments`.
 * @param {unknown} network - `data.network`.
 * @returns {Array<{nonce: string, at: string | null, resource: string, host: string, amount: string,
 *   mandate: string, status: string, error: string | null, http: string, tx: string | null,
 *   txShort: string, txHref: string | null, context: {primary: string, secondary: string}}>}
 */
export function paymentRows(payments, network) {
  const rows = [];
  for (const p of Array.isArray(payments) ? payments : []) {
    if (!p || typeof p !== "object") continue;
    const tx = typeof p.tx === "string" && p.tx !== "" ? p.tx : null;
    rows.push({
      nonce: typeof p.nonce === "string" ? p.nonce : EM,
      at: typeof p.at === "string" ? p.at : null,
      resource: typeof p.resource === "string" && p.resource !== "" ? p.resource : typeof p.url === "string" ? p.url : EM,
      host: typeof p.host === "string" && p.host !== "" ? p.host : EM,
      amount: usd(p.amount_usd),
      mandate: typeof p.mandate === "string" && p.mandate !== "" ? p.mandate : EM,
      status: typeof p.status === "string" && p.status !== "" ? p.status : "unknown",
      error: typeof p.error === "string" && p.error !== "" ? p.error : null,
      http: typeof p.http_status === "number" ? String(p.http_status) : EM,
      tx,
      txShort: tx === null ? EM : shortHex(tx),
      txHref: txLink(network, tx),
      context: paymentContext(p.context),
    });
  }
  return rows;
}

/**
 * Spend by strategy and by session, largest first, plus what no context
 * claimed. `by_channel` is keyed by workspace id (decision 4: a basename is
 * not an identity) and carries the name for display.
 * @param {unknown} spend - `data.spend`.
 * @returns {{settled: string, pending: string, unattributed: string,
 *   byChannel: Array<{id: string, name: string, usd: string}>,
 *   bySession: Array<{session: string, short: string, usd: string}>}}
 */
export function spendRows(spend) {
  const s = spend && typeof spend === "object" ? /** @type {Record<string, any>} */ (spend) : {};
  const desc = (a, b) => (usdNumber(b.raw) ?? 0) - (usdNumber(a.raw) ?? 0);
  const byChannel = Object.entries(s.by_channel && typeof s.by_channel === "object" ? s.by_channel : {})
    .map(([id, v]) => ({ id, name: typeof v?.name === "string" && v.name !== "" ? v.name : id, raw: v?.usd, usd: usd(v?.usd) }))
    .sort(desc).map(({ id, name, usd: u }) => ({ id, name, usd: u }));
  const bySession = Object.entries(s.by_session && typeof s.by_session === "object" ? s.by_session : {})
    .map(([session, v]) => ({ session, short: shortSession(session), raw: v, usd: usd(v) }))
    .sort(desc).map(({ session, short, usd: u }) => ({ session, short, usd: u }));
  return { settled: usd(s.settled_usd), pending: usd(s.pending_usd), unattributed: usd(s.unattributed_usd), byChannel, bySession };
}

/** The balance line: `{usd, at}` reads as an amount; `{unavailable}` names
 * why (the RPC did not answer within 3 s, spec §2) instead of showing a zero.
 * @param {unknown} balance @returns {{text: string, available: boolean, at: string | null, reason: string | null}} */
export function balanceView(balance) {
  const b = balance && typeof balance === "object" ? /** @type {Record<string, unknown>} */ (balance) : {};
  if (typeof b.unavailable === "string") return { text: "unavailable", available: false, at: null, reason: b.unavailable };
  const parsed = usdNumber(b.usd);
  if (parsed === null) return { text: EM, available: false, at: null, reason: null };
  return { text: usd(parsed), available: true, at: typeof b.at === "string" ? b.at : null, reason: null };
}

/** The operator's one setup step when the wallet is not configured (spec
 * §4.2: `agentpay init --home <home> …`). `<name>` and the key stay
 * placeholders — the deployment is the operator's choice and the key never
 * belongs on a page.
 * @param {unknown} home @returns {string} */
export function setupCommand(home) {
  const path = typeof home === "string" && home !== "" ? home : "$DSH_HOME/face/agentpay";
  return `agentpay init --home ${path} --from-deployment <name> --key 0x…`;
}

/* ---------- the pay card: `wallet_pay` tool values (spec §4.4) ---------- */

/** The ledger word a settled-or-not pay envelope wears, for `data-status`.
 * `ledger_status` is agentpay's own (settled / unknown / rejected /
 * expired-unused); a paid call that carries none is `unknown` (recorded, not
 * yet reconciled), an unpaid 2xx (`paid:false`, the resource was free) is
 * `free`.
 * @param {Record<string, any>} payload - an `ok:true` `wallet_pay` value.
 * @returns {string} */
export function payStatus(payload) {
  if (typeof payload.ledger_status === "string" && payload.ledger_status !== "") return payload.ledger_status;
  return payload.paid === true ? "unknown" : "free";
}

/** A pay envelope's one line, spec §2: `$0.001 · GET api.example.com/predict
 * · settled · tx 0xe833…c9d`; a refusal `refused before signing ·
 * mandate_insufficient_budget`, or `402 · invalid_exact_evm_insufficient_balance`
 * when the payee answered. The distinction is `status`: a refusal with no
 * HTTP status never left the face.
 * @param {Record<string, any>} payload - either `wallet_pay` envelope.
 * @returns {string} */
export function payLine(payload) {
  if (payload.ok === true) {
    // `resource` is "GET /predict" and `host` "api.example.com": the line joins them as
    // "GET api.example.com/predict", the spelling §2 shows the operator.
    const [method, ...pathParts] = (typeof payload.resource === "string" ? payload.resource : "").split(" ");
    const host = typeof payload.host === "string" ? payload.host : "";
    const where = [method, `${host}${pathParts.join(" ")}`].filter((x) => x !== "").join(" ");
    const bits = [payload.paid === true ? usdCompact(payload.amount_usd) : "free", where || EM, payStatus(payload)];
    if (typeof payload.tx === "string" && payload.tx !== "") bits.push(`tx ${shortHex(payload.tx, 6, 4)}`);
    return bits.join(" · ");
  }
  const error = typeof payload.error === "string" && payload.error !== "" ? payload.error : "refused";
  const head = typeof payload.status === "number" ? String(payload.status) : "refused before signing";
  const summary = typeof payload.payment_model_context?.summary === "string" ? payload.payment_model_context.summary : "";
  return [head, error, summary].filter((x) => x !== "").join(" · ");
}

/** The key/value block under the pay line: every scalar the envelope carries
 * that the operator would look for, in a fixed order, absent ones skipped.
 * @param {Record<string, any>} payload - either `wallet_pay` envelope.
 * @returns {Array<[string, string]>} */
export function payFields(payload) {
  /** @type {Array<[string, string]>} */
  const out = [];
  const add = (k, v) => { if (v !== undefined && v !== null && v !== "") out.push([k, String(v)]); };
  if (payload.ok === true) {
    add("amount", payload.paid === true ? usd(payload.amount_usd) : "free");
    add("resource", payload.resource);
    add("host", payload.host);
    add("url", payload.url);
    add("http", payload.status);
    add("ledger", payStatus(payload));
    add("mandate", payload.mandate);
    add("remaining", payload.remaining_usd === undefined ? undefined : usd(payload.remaining_usd));
    add("tx", payload.tx);
    if (payload.body_truncated === true) add("body", "truncated to 8 KB — raw has what was kept");
    return out;
  }
  add("error", payload.error);
  add("http", payload.status);
  add("url", payload.url);
  add("host", payload.host);
  const ctx = payload.payment_model_context;
  if (ctx && typeof ctx === "object") {
    add("reason", ctx.reason);
    add("summary", ctx.summary);
    if (Array.isArray(ctx.remediation)) ctx.remediation.forEach((step, i) => add(i === 0 ? "next" : "", step));
  }
  const detail = payload.detail;
  if (detail && typeof detail === "object") {
    for (const [k, v] of Object.entries(detail)) {
      if (v === null || ["string", "number", "boolean"].includes(typeof v)) add(k, v);
    }
  }
  return out;
}
