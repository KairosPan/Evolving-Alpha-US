/** The /wallet page's DOM: address and balance, alerts, budgets, payments,
 * spend by strategy and by session — all figures from `/data/wallet.json`.
 *
 * Mirrors `account-view.js`: the same `el()` builder, the same account-*
 * classes (account.css) so the two money pages fold and scroll alike, plus
 * the few wallet-* classes wallet.css adds. Every judgement — which alerts
 * stand, what a mandate's effective remaining is, whether a tx has an
 * explorer — was made server-side or in `wallet-model.js`; this file only
 * decides where each answer goes. No innerHTML anywhere: every string is
 * host data and lands via `textContent`, links via `href` on an element the
 * model already vetted as an explorer URL.
 * @module
 */
import { readingTime } from "./account-view.js";
import {
  balanceView, groupAlerts, mandateRows, paymentRows, setupCommand, spendRows, shortHex,
} from "./wallet-model.js";

const EM = "—";

/** @param {string} tag @param {string} [cls] @param {string} [value] */
function el(tag, cls, value) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (value !== undefined) node.textContent = value;
  return node;
}

/** A status badge in the channel page's vocabulary (`.ch-badge[data-status]`,
 * chat.css) so `settled` reads the same on the pay card and on this page.
 * @param {string} status */
function badge(status) {
  const node = el("span", "ch-badge", status);
  node.dataset.status = status;
  return node;
}

function metric(label, value, cls = "") {
  const item = el("div", "account-metric");
  item.append(el("dt", "", label), el("dd", cls, value));
  return item;
}

/** The account page's empty-state card, verbatim in shape. */
function emptyState(title, description, action) {
  const empty = el("div", "account-empty");
  const icon = el("div", "account-empty-icon");
  icon.setAttribute("aria-hidden", "true");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 32 32");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M5 10h22v14H5z M5 14h22 M20 19h4");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.5");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  icon.append(svg);
  empty.append(icon, el("h2", "", title), el("p", "", description));
  if (action) empty.append(action);
  return empty;
}

/** A two-line cell: a strong primary and a dim secondary (the account page's
 * symbol cell). @param {string} primary @param {string} [secondary] @param {boolean} [mono] */
function pair(primary, secondary, mono = false) {
  const node = el("div", "account-symbol");
  node.append(el("strong", mono ? "mono" : "", primary));
  if (secondary !== undefined && secondary !== EM) node.append(el("span", "account-subvalue", secondary));
  return node;
}

/**
 * The account page's table, with one addition: a column whose label carries
 * `text: true` is left-aligned (account.css right-aligns every column past
 * the first; a host or a status is not a figure).
 * @param {any[]} rows
 * @param {Array<[string, (row: any) => string | HTMLElement, boolean?]>} columns
 * @param {string} label
 */
function table(rows, columns, label) {
  const scroll = el("div", "account-table-scroll");
  scroll.tabIndex = 0;
  scroll.setAttribute("aria-label", label);
  const node = el("table", "account-table");
  const caption = el("caption", "account-sr-only", label);
  const head = el("thead");
  const header = el("tr");
  for (const [name, , text] of columns) {
    const th = el("th", text ? "text" : "", name);
    th.scope = "col";
    header.append(th);
  }
  head.append(header);
  const body = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    for (const [, render, text] of columns) {
      const td = el("td", text ? "text" : "");
      const value = render(row);
      if (typeof value === "string") td.textContent = value;
      else td.append(value);
      tr.append(td);
    }
    body.append(tr);
  }
  node.append(caption, head, body);
  scroll.append(node);
  return scroll;
}

/** A records card with a static tab label (the wallet's groups are single
 * tables — the tab is a label, not a control), a panel and a footer. */
function records(label, count, content, footer) {
  const card = el("section", "account-records");
  card.setAttribute("aria-label", label);
  const toolbar = el("div", "account-toolbar");
  const tabs = el("div", "account-tabs");
  const tab = el("span", "account-tab static");
  tab.setAttribute("aria-selected", "true");
  tab.append(el("span", "", label), el("span", "account-tab-count", String(count)));
  tabs.append(tab);
  toolbar.append(tabs);
  const panel = el("div", "account-records-panel");
  panel.append(content);
  const foot = el("div", "account-table-footer", footer);
  foot.setAttribute("role", "status");
  card.append(toolbar, panel, foot);
  return card;
}

/* ---------- blocks ---------- */

/** The alerts block (spec §2): warnings first, then notes; absent when none
 * stand, so a clean wallet has no empty box saying so. */
function alertsBlock(data) {
  const { warn, info, total } = groupAlerts(data.alerts);
  if (total === 0) return null;
  const box = el("section", "wallet-alerts");
  box.setAttribute("role", warn.length ? "alert" : "status");
  box.setAttribute("aria-label", "钱包提醒");
  box.append(el("h2", "wallet-alerts-title", `提醒 · ${total}`));
  const list = el("ul", "wallet-alert-list");
  for (const [level, entries] of [["warn", warn], ["info", info]]) {
    for (const alert of entries) {
      const item = el("li", `wallet-alert ${level}`);
      item.dataset.kind = alert.kind;
      item.append(el("span", "wallet-alert-kind", alert.kind.replaceAll("_", " ")), el("span", "", alert.text));
      if (alert.mandate) item.append(el("span", "wallet-alert-mandate mono", alert.mandate));
      list.append(item);
    }
  }
  box.append(list);
  return box;
}

/** Address + balance, the "send USDC here" line, and the three totals. */
function overview(data) {
  const balance = balanceView(data.balance);
  const spend = spendRows(data.spend);
  const card = el("section", "account-overview");
  card.setAttribute("aria-label", "链上余额");
  const heading = el("div", "account-overview-head");
  const network = typeof data.network === "string" && data.network !== "" ? data.network : EM;
  heading.append(el("span", "account-label", `链上余额 · ${typeof data.token === "string" && data.token !== "" ? data.token : "USDC"}`));
  const chip = el("span", `account-badge ${network === "eip155:8453" ? "live" : "paper"}`, network === EM ? "网络未知" : network);
  chip.title = typeof data.deployment === "string" ? `deployment ${data.deployment}` : "";
  heading.append(chip);
  const amount = el("div", "account-balance", balance.text);
  if (!balance.available) amount.classList.add("is-unavailable");
  const line = el("div", "account-change");
  if (balance.available) {
    line.append(el("span", "", `把 USDC 发到下面这个地址（${network}）即可充值`));
    if (balance.at) line.append(el("span", "", `余额读取于 ${readingTime(balance.at)}`));
  } else {
    line.append(el("span", "neg", balance.reason ? `余额不可用 · ${balance.reason}` : "余额不可用"));
    line.append(el("span", "", `把 USDC 发到下面这个地址（${network}）即可充值`));
  }
  const address = el("div", "wallet-address");
  address.append(el("span", "wallet-address-label", "付款地址"), el("code", "wallet-address-value", typeof data.address === "string" && data.address !== "" ? data.address : EM));
  const metrics = el("dl", "account-metrics");
  metrics.append(
    metric("累计已结算", spend.settled),
    metric("待确认", spend.pending),
    metric("未归属", spend.unattributed),
  );
  card.append(heading, amount, line, address, metrics);
  return card;
}

/** Every mandate as a row (spec §2): purpose · holder · effective remaining /
 * limit · per call · valid until · status. */
function mandatesBlock(data, now) {
  const rows = mandateRows(data.mandates, now);
  const content = rows.length === 0
    ? emptyState("暂无预算", "Kairos 在对话中请求预算，你在卡片上批准后，预算会出现在这里。")
    : table(rows, [
      ["预算", (row) => {
        const cell = pair(row.id, row.purpose, true);
        if (row.isChild) cell.append(el("span", "account-subvalue", `子预算 · 父 ${row.parentId}`));
        return cell;
      }, true],
      ["持有者", (row) => row.holder, true],
      ["剩余 / 额度", (row) => {
        const cell = el("div", "account-pnl");
        cell.append(el("span", "", `${row.remaining} / ${row.limit}`));
        cell.append(el("span", "account-subvalue", row.pct === null ? `已花 ${row.spent}` : `剩 ${row.pct}% · 已花 ${row.spent}${row.pending !== "$0.000000" ? ` · 预留 ${row.pending}` : ""}`));
        return cell;
      }],
      ["每次上限", (row) => row.perCall],
      ["有效期至", (row) => {
        const cell = el("div", "account-pnl");
        cell.append(el("span", row.expired ? "neg" : "", row.validUntil === null ? EM : readingTime(row.validUntil)));
        if (row.expired) cell.append(el("span", "account-subvalue neg", "已过期"));
        return cell;
      }],
      ["状态", (row) => {
        const cell = el("div", "account-symbol");
        cell.append(badge(row.status));
        if (row.category) cell.append(el("span", "account-subvalue", row.category));
        return cell;
      }, true],
    ], "预算明细");
  return records("预算", rows.length, content, `${rows.length} 个预算 · 剩余按整条预算链取最小值 · 预算是承诺上限，不是余额`);
}

/** Recent payments, newest first, tx linked when the network has an explorer. */
function paymentsBlock(data) {
  const rows = paymentRows(data.payments, data.network);
  const content = rows.length === 0
    ? emptyState("暂无支付记录", "Kairos 用 wallet_pay 付费后，每一笔都会记在这里，并归属到发起它的策略与会话。")
    : table(rows, [
      ["时间", (row) => row.at === null ? EM : readingTime(row.at)],
      ["资源", (row) => pair(row.resource, row.host), true],
      ["金额", (row) => row.amount],
      ["来源", (row) => pair(row.context.primary, row.context.secondary), true],
      // The bought file's path (the ledger row's label), relative to the strategy's vendor/.
      ["文件", (row) => {
        if (row.file === null) return EM;
        const cell = el("span", "mono", row.file);
        cell.title = `strategies/<name>/vendor/${row.file}`;
        return cell;
      }, true],
      ["mandate", (row) => {
        const cell = el("span", "mono", shortHex(row.mandate, 10, 4));
        cell.title = row.mandate;
        return cell;
      }, true],
      ["状态", (row) => {
        const cell = el("div", "account-symbol");
        cell.append(badge(row.status));
        if (row.error) cell.append(el("span", "account-subvalue", `${row.http !== EM ? `${row.http} ` : ""}${row.error}`));
        else if (row.http !== EM) cell.append(el("span", "account-subvalue", `HTTP ${row.http}`));
        return cell;
      }, true],
      ["结算 tx", (row) => {
        if (row.tx === null) return EM;
        if (row.txHref === null) {
          const cell = el("span", "mono", row.txShort);
          cell.title = row.tx;
          return cell;
        }
        const link = el("a", "wallet-tx mono", row.txShort);
        link.href = row.txHref;
        link.title = row.tx;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        return link;
      }, true],
    ], "支付记录明细");
  const reconcile = data.reconcile && typeof data.reconcile === "object" ? data.reconcile : null;
  const footer = [`最近 ${rows.length} 条 · 来自本地 ledger.jsonl`];
  if (reconcile) {
    footer.push(typeof reconcile.error === "string" && reconcile.error !== ""
      ? `上次对账失败 · ${reconcile.error}`
      : `上次对账 ${readingTime(reconcile.at)} · 结算 ${reconcile.settled ?? 0} · 作废 ${reconcile.expired_unused ?? 0} · 待定 ${reconcile.still_pending ?? 0}`);
  }
  return records("支付记录", rows.length, content, footer.join(" · "));
}

/** Spend by strategy and by session, side by side. */
function spendBlock(data) {
  const spend = spendRows(data.spend);
  const grid = el("div", "wallet-spend");
  const one = (label, rows, columns, empty) => {
    const content = rows.length === 0 ? el("p", "account-detail-note wallet-spend-empty", empty) : table(rows, columns, label);
    grid.append(records(label, rows.length, content, `${rows.length} 项 · 只计已结算与未确认的记录`));
  };
  one("按策略", spend.byChannel, [
    ["策略", (row) => { const cell = pair(row.name); cell.title = row.id; return cell; }, true],
    ["已结算", (row) => row.usd],
  ], "还没有归属到策略的支付。");
  one("按会话", spend.bySession, [
    ["会话", (row) => { const cell = el("span", "mono", row.short); cell.title = row.session; return cell; }, true],
    ["已结算", (row) => row.usd],
  ], "还没有归属到会话的支付。");
  return grid;
}

/** The setup step when the wallet is not configured (spec §4.2): the home the
 * face looked in, why it registered nothing, and the one command that fixes it. */
function notConfigured(data) {
  const card = el("section", "account-records wallet-setup");
  card.setAttribute("aria-label", "钱包设置");
  const guide = el("div", "account-connect-guide");
  guide.append(el("h2", "", "钱包尚未配置"));
  guide.append(el("p", "", "在运行 Kairos 的机器上，用 agentpay 把付款密钥写进 face 的钱包目录，然后重启服务并刷新此页。密钥文件只有你能写，Kairos 只能在你批准的预算内花它。"));
  guide.append(el("pre", "wallet-command", setupCommand(data.home)));
  const notes = el("p", "account-detail-note");
  notes.append(el("span", "", "钱包目录："), el("code", "mono", typeof data.home === "string" && data.home !== "" ? data.home : EM));
  guide.append(notes);
  if (typeof data.reason === "string" && data.reason !== "") guide.append(el("p", "account-detail-note", `未注册原因：${data.reason}`));
  guide.append(el("p", "account-detail-note", "<name> 是 agentpay 部署名（本地链或 Base Sepolia），--key 是付款私钥；两者都不要贴到本页。配置前 Kairos 没有任何钱包工具。"));
  card.append(emptyState("Kairos 还没有钱包", "配置后，这里会显示地址、余额、预算、支付记录和按策略的花费。"), guide);
  return card;
}

/** The fold under the page: where the wallet lives and when it was read. */
function walletDetails(data, state) {
  const details = el("details", "account-details");
  details.open = state.detailsOpen;
  details.addEventListener("toggle", () => { if (details.isConnected) state.detailsOpen = details.open; });
  const summary = el("summary");
  summary.append(el("span", "", "钱包详情"), el("span", "account-details-hint", "目录与读取时间"));
  const content = el("div", "account-details-content");
  const info = el("dl", "account-info");
  info.append(
    metric("钱包目录", typeof data.home === "string" ? data.home : EM),
    metric("网络", typeof data.network === "string" ? data.network : EM),
    metric("部署", typeof data.deployment === "string" ? data.deployment : EM),
    metric("读取于", readingTime(data.generated_at)),
  );
  content.append(info);
  content.append(el("p", "account-detail-note", "本页只读。预算由 Kairos 在对话中请求、由你在卡片上批准；付款不再弹卡片，每一笔都记在这里。刷新会在有待定记录时对账一次（每分钟最多一次）。"));
  details.append(summary, content);
  return details;
}

/**
 * Draw the page into `root` from one `/data/wallet.json` body.
 * @param {HTMLElement} root
 * @param {Record<string, any>} data
 * @param {{detailsOpen: boolean}} [state]
 * @param {number} [now] - epoch ms, for the expiry mark; defaults to the clock.
 */
export function renderWallet(root, data, state = { detailsOpen: false }, now = Date.now()) {
  if (data.configured !== true) {
    root.replaceChildren(notConfigured(data));
    return;
  }
  const nodes = [];
  const alerts = alertsBlock(data);
  if (alerts) nodes.push(alerts);
  nodes.push(overview(data), mandatesBlock(data, now), paymentsBlock(data), spendBlock(data), walletDetails(data, state));
  root.replaceChildren(...nodes);
}

/** The failure state, the account page's: a retry button and the reason folded. */
export function renderWalletError(root, message, retry) {
  const button = el("button", "account-button primary", "重新加载");
  button.type = "button";
  button.addEventListener("click", retry);
  const error = emptyState("暂时无法读取钱包", "请确认服务在运行后重试。", button);
  error.classList.add("account-error");
  error.setAttribute("role", "alert");
  const detail = el("details", "account-error-detail");
  detail.append(el("summary", "", "查看原因"), el("p", "account-technical", message));
  error.append(detail);
  root.replaceChildren(error);
}
