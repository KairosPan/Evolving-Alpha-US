/** Formatting and view-only filters for the account snapshot. */

const EM = "—";

/** Broker amounts are numbers or decimal strings; missing values stay missing.
 * @param {unknown} value
 * @returns {number | null}
 */
export function number(value) {
  if (typeof value !== "number" && typeof value !== "string") return null;
  if (typeof value === "string" && value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? (parsed === 0 ? 0 : parsed) : null;
}

/** @param {number} value @param {unknown} currency */
function amount(value, currency) {
  const code = typeof currency === "string" ? currency.trim().toUpperCase() : "";
  const prefix = !code || code === "USD" ? "$" : `${code} `;
  return `${prefix}${Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

/** @param {unknown} value @param {unknown} [currency] */
export function money(value, currency) {
  const parsed = number(value);
  return parsed === null ? EM : `${parsed < 0 ? "-" : ""}${amount(parsed, currency)}`;
}

/** @param {unknown} value @param {unknown} [currency] */
export function signedMoney(value, currency) {
  const parsed = number(value);
  if (parsed === null) return EM;
  return `${parsed > 0 ? "+" : parsed < 0 ? "-" : ""}${amount(parsed, currency)}`;
}

/** @param {unknown} value */
export function pct(value) {
  const parsed = number(value);
  if (parsed === null || !Number.isFinite(parsed * 100)) return EM;
  return `${parsed > 0 ? "+" : ""}${(parsed * 100).toFixed(2)}%`;
}

/** @param {unknown} value */
export function sign(value) {
  const parsed = number(value);
  return parsed === null || parsed === 0 ? "" : parsed > 0 ? "pos" : "neg";
}

/** @param {unknown} value */
export function text(value) {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "")
    ? EM : String(value);
}

/** The snapshot's read host identifies its environment. The mutation pin does not.
 * @param {unknown} data
 * @returns {{label: string, tone: "paper" | "live" | "neutral"}}
 */
export function accountMode(data) {
  const snapshot = data && typeof data === "object" ? data : {};
  if (snapshot.available === false) return { label: "未连接", tone: "neutral" };
  if (snapshot.host === "paper-api.alpaca.markets") return { label: "Paper · 模拟", tone: "paper" };
  if (snapshot.host === "api.alpaca.markets") return { label: "Live · 实盘", tone: "live" };
  return {
    label: typeof snapshot.host === "string" && snapshot.host.trim() ? "自定义账户" : "账户类型未知",
    tone: "neutral",
  };
}

/** Never turn a partially reported set of positions into an apparent total.
 * @param {unknown} positions
 * @returns {number | null}
 */
export function unrealizedTotal(positions) {
  if (!Array.isArray(positions)) return null;
  let total = 0;
  for (const position of positions) {
    const value = number(position && typeof position === "object" ? position.unrealized_pl : null);
    if (value === null) return null;
    total += value;
  }
  return Number.isFinite(total) ? total : null;
}

const WORKING = new Set([
  "new", "accepted", "pending_new", "partially_filled", "pending_cancel", "pending_replace", "held",
]);
const CLOSED = new Set(["canceled", "expired", "rejected", "replaced"]);

/** These filters describe only rows present in the recent-order snapshot.
 * Unknown or ambiguous statuses remain visible under All, without being guessed.
 * @param {unknown} order
 * @param {string} filter
 */
export function orderMatches(order, filter) {
  if (filter === "all") return true;
  const status = order && typeof order === "object" ? order.status : null;
  if (typeof status !== "string") return false;
  if (filter === "working") return WORKING.has(status);
  if (filter === "filled") return status === "filled";
  if (filter === "closed") return CLOSED.has(status);
  return false;
}
