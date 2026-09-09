/** Paper-trading-style portfolio view; all figures come from the account payload. */
import { number, money, signedMoney, pct, sign, text, accountMode, unrealizedTotal, orderMatches } from "./account-model.js";

function el(tag, cls, value) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (value !== undefined) node.textContent = value;
  return node;
}

export function readingTime(value) {
  if (typeof value !== "string" || !value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false, timeZoneName: "short",
  }).format(date);
}

function badge(label, tone = "neutral") { return el("span", `account-badge ${tone}`, label); }

function metric(label, value, cls = "") {
  const item = el("div", "account-metric");
  item.append(el("dt", "", label), el("dd", cls, value));
  return item;
}

function overview(data, positions, available) {
  const account = available ? data.account ?? {} : {};
  const mode = accountMode(data);
  const card = el("section", "account-overview");
  card.setAttribute("aria-label", "资产概览");
  const heading = el("div", "account-overview-head");
  heading.append(el("span", "account-label", "账户总资产"), badge(mode.label, mode.tone));
  const balance = el("div", "account-balance", money(account.equity, account.currency));
  const equity = number(account.equity), previous = number(account.last_equity);
  const change = el("div", "account-change");
  if (equity !== null && previous !== null && previous > 0 && Number.isFinite(equity - previous)) {
    const delta = equity - previous;
    change.append(el("span", sign(delta), `${signedMoney(delta, account.currency)} (${pct(delta / previous)})`), el("span", "", "较上日"));
  } else {
    change.textContent = available ? `账户净值 · ${text(account.currency)}` : "连接账户后查看资产";
  }
  const total = available && Array.isArray(data.positions) ? unrealizedTotal(positions) : null;
  const metrics = el("dl", "account-metrics");
  metrics.append(
    metric("可用现金", money(account.cash, account.currency)),
    metric("购买力", money(account.buying_power, account.currency)),
    metric("持仓浮动盈亏", signedMoney(total, account.currency), sign(total)),
  );
  card.append(heading, balance, change, metrics);
  return card;
}

function emptyState(title, description, action) {
  const empty = el("div", "account-empty");
  const icon = el("div", "account-empty-icon");
  icon.setAttribute("aria-hidden", "true");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 32 32");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M7 8h18v18H7z M11 8V5h10v3 M11 14h10 M11 19h6");
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

const orderLabels = {
  new: "待成交", accepted: "已受理", pending_new: "提交中", partially_filled: "部分成交",
  filled: "已成交", canceled: "已撤销", expired: "已过期", rejected: "已拒绝",
  pending_cancel: "撤单中", pending_replace: "改单中", replaced: "已替换",
  done_for_day: "当日结束", held: "等待中", stopped: "已停止", suspended: "已暂停", calculated: "结算中",
};
const typeLabels = { market: "市价", limit: "限价", stop: "止损", stop_limit: "止损限价", trailing_stop: "移动止损" };

function symbolCell(row, position = false) {
  const node = el("div", "account-symbol");
  node.append(el("strong", "", text(row.symbol)));
  if (position && (row.side === "long" || row.side === "short")) {
    node.append(el("span", "account-subvalue", row.side === "long" ? "多头" : "空头"));
  }
  return node;
}

function pnlCell(row, currency) {
  const node = el("div", `account-pnl ${sign(row.unrealized_pl)}`);
  node.append(el("span", "", signedMoney(row.unrealized_pl, currency)), el("span", `account-subvalue ${sign(row.unrealized_plpc)}`, pct(row.unrealized_plpc)));
  return node;
}

function table(rows, columns, label) {
  const scroll = el("div", "account-table-scroll");
  scroll.tabIndex = 0;
  scroll.setAttribute("aria-label", label);
  const table = el("table", "account-table");
  const caption = el("caption", "account-sr-only", label);
  const head = el("thead");
  const header = el("tr");
  for (const [name] of columns) {
    const th = el("th", "", name);
    th.scope = "col";
    header.append(th);
  }
  head.append(header);
  const body = el("tbody");
  for (const row of rows) {
    const tr = el("tr");
    for (const [, render] of columns) {
      const td = el("td");
      const value = render(row);
      if (typeof value === "string") td.textContent = value;
      else td.append(value);
      tr.append(td);
    }
    body.append(tr);
  }
  table.append(caption, head, body);
  scroll.append(table);
  return scroll;
}

function records(data, positions, orders, available, state, openDetails) {
  const card = el("section", "account-records");
  const toolbar = el("div", "account-toolbar");
  const tabs = el("div", "account-tabs");
  tabs.setAttribute("role", "tablist");
  tabs.setAttribute("aria-label", "账户记录");
  const tabButtons = [];
  for (const [id, label, count] of [["positions", "持仓", positions.length], ["orders", "订单", orders.length]]) {
    const button = el("button", "account-tab");
    button.type = "button";
    button.id = `account-tab-${id}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", "account-records-panel");
    button.append(el("span", "", label), el("span", "account-tab-count", available ? String(count) : "—"));
    button.addEventListener("click", () => { state.tab = id; update(); });
    tabButtons.push(button);
    tabs.append(button);
  }
  tabs.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const index = event.key === "Home" ? 0 : event.key === "End" ? 1 : state.tab === "positions" ? 1 : 0;
    tabButtons[index].click();
    tabButtons[index].focus();
  });
  const controls = el("div", "account-filters");
  const filter = el("select", "account-select");
  filter.setAttribute("aria-label", "订单状态");
  for (const [value, label] of [["all", "全部状态"], ["working", "进行中"], ["filled", "已成交"], ["closed", "已结束"]]) {
    const option = el("option", "", label);
    option.value = value;
    filter.append(option);
  }
  filter.value = state.orderFilter;
  filter.disabled = !available;
  filter.addEventListener("change", () => { state.orderFilter = filter.value; update(); });
  const search = el("input", "account-search");
  search.type = "search";
  search.placeholder = "搜索代码";
  search.setAttribute("aria-label", "搜索股票代码");
  search.autocomplete = "off";
  search.spellcheck = false;
  search.value = state.query;
  search.disabled = !available;
  search.addEventListener("input", () => { state.query = search.value; update(); });
  controls.append(filter, search);
  toolbar.append(tabs, controls);
  const content = el("div", "account-records-panel");
  content.id = "account-records-panel";
  content.setAttribute("role", "tabpanel");
  const footer = el("div", "account-table-footer");
  footer.setAttribute("role", "status");
  card.append(toolbar, content, footer);

  function update() {
    const isPositions = state.tab === "positions";
    tabButtons.forEach((button, index) => {
      const selected = isPositions === (index === 0);
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    });
    filter.hidden = isPositions;
    content.setAttribute("aria-labelledby", `account-tab-${state.tab}`);
    const source = isPositions ? positions : orders;
    const query = state.query.trim().toUpperCase();
    const rows = source.filter((row) => String(row.symbol ?? "").toUpperCase().includes(query) && (isPositions || orderMatches(row, state.orderFilter)));
    if (!available) {
      const connect = el("button", "account-button primary", "查看连接说明");
      connect.type = "button";
      connect.addEventListener("click", openDetails);
      content.replaceChildren(emptyState("连接你的交易账户", "连接 Alpaca 后，在这里查看资产、持仓与订单。", connect));
    } else if (!rows.length) {
      const filtered = query !== "" || (!isPositions && state.orderFilter !== "all");
      const clear = filtered ? el("button", "account-button", "清除筛选") : null;
      if (clear) {
        clear.type = "button";
        clear.addEventListener("click", () => {
          state.query = ""; state.orderFilter = "all"; search.value = ""; filter.value = "all"; update(); search.focus();
        });
      }
      content.replaceChildren(emptyState(
        filtered ? "没有匹配的记录" : isPositions ? "暂无持仓" : "暂无订单",
        filtered ? "试试其他股票代码或订单状态。" : isPositions ? "持仓建立后，可在这里跟踪市值和盈亏。" : "本次读取没有返回订单记录。",
        clear,
      ));
    } else {
      const currency = data.account?.currency;
      content.replaceChildren(table(rows, isPositions ? [
        ["股票", (row) => symbolCell(row, true)],
        ["持有数量", (row) => text(row.qty)],
        ["成本价", (row) => money(row.avg_entry_price, currency)],
        ["现价", (row) => money(row.current_price, currency)],
        ["持仓市值", (row) => money(row.market_value, currency)],
        ["浮动盈亏", (row) => pnlCell(row, currency)],
      ] : [
        ["股票", (row) => symbolCell(row)],
        ["方向", (row) => badge(row.side === "buy" ? "买入" : row.side === "sell" ? "卖出" : text(row.side), row.side === "buy" ? "buy" : "neutral")],
        ["类型", (row) => text(typeLabels[row.type] ?? row.type)],
        ["数量 / 已成交", (row) => `${text(row.qty)} / ${text(row.filled_qty)}`],
        ["成交均价", (row) => money(row.filled_avg_price, currency)],
        ["状态", (row) => badge(orderLabels[row.status] ?? text(row.status), row.status === "filled" ? "paper" : row.status === "rejected" ? "live" : "neutral")],
        ["提交时间", (row) => readingTime(row.submitted_at)],
      ], isPositions ? "持仓明细" : "订单明细"));
    }
    const scope = typeof data.orders_note === "string" ? (data.orders_note === "Alpaca's most recent 50 orders, all statuses" ? "Alpaca 最近 50 笔订单 · 包含所有状态" : data.orders_note) : "";
    footer.textContent = !available ? "账户尚未连接" : `${rows.length} / ${source.length} ${isPositions ? "项持仓" : "笔订单"}${!isPositions && scope ? ` · ${scope}` : ""}`;
  }
  update();
  return card;
}

function accountDetails(data, available, state) {
  const details = el("details", "account-details");
  details.open = state.detailsOpen;
  details.addEventListener("toggle", () => { if (details.isConnected) state.detailsOpen = details.open; });
  const summary = el("summary");
  summary.append(el("span", "", "账户详情"), el("span", "account-details-hint", available ? "连接与交易权限" : "连接说明"));
  const content = el("div", "account-details-content");
  if (!available) {
    const guide = el("section", "account-connect-guide");
    guide.append(el("h2", "", "连接 Alpaca 模拟账户"), el("p", "", "在运行 Kairos 的环境中配置 Alpaca Paper 的 API Key 和 Secret，然后重启服务并刷新此页。"));
    guide.append(el("p", "account-technical", "APCA_API_KEY_ID · APCA_API_SECRET_KEY"));
    if (typeof data.reason === "string") guide.append(el("p", "account-detail-note", data.reason));
    content.append(guide);
  }
  const info = el("dl", "account-info");
  const account = available ? data.account ?? {} : {};
  info.append(metric("账户状态", text(account.status)), metric("货币", text(account.currency)), metric("连接地址", text(data.host)), metric("页面功能", "账户查看"));
  content.append(info);
  const gate = data.orders_gate;
  const technical = el("details", "account-technical-details");
  technical.append(el("summary", "", "交易权限与数据来源"));
  const gateText = (value, yes, no) => value === true ? yes : value === false ? no : "未知";
  if (gate && typeof gate === "object") {
    technical.append(el("p", "", `订单工具 · ${gateText(gate.gate1_registered, "已注册", "未注册")}　/　人工审批演练 · ${gateText(gate.gate2_validated, "已验证", "未验证")}`));
    for (const value of [gate.gate1_rule, gate.gate2_note, gate.paper_pin]) {
      if (typeof value === "string" && value) technical.append(el("p", "account-technical", value));
    }
  } else technical.append(el("p", "", "本次数据未提供交易权限状态。"));
  if (typeof data.raw === "string" && data.raw) technical.append(el("p", "account-technical", data.raw));
  technical.append(el("p", "account-detail-note", "本页仅查看账户。刷新读取服务端快照，账户数据最多缓存 60 秒。"));
  content.append(technical);
  details.append(summary, content);
  return details;
}

export function renderAccount(root, data, state = { tab: "positions", query: "", orderFilter: "all", detailsOpen: false }) {
  const available = data.available !== false;
  const positions = available && Array.isArray(data.positions) ? data.positions : [];
  const orders = available && Array.isArray(data.orders) ? data.orders : [];
  const details = accountDetails(data, available, state);
  const openDetails = () => { state.detailsOpen = true; details.open = true; details.scrollIntoView({ block: "nearest" }); details.querySelector("summary").focus(); };
  const nodes = [];
  if (data.stale) {
    const stale = el("p", "account-notice", "暂时无法更新，当前显示的是上次成功读取的账户数据。");
    stale.setAttribute("role", "status");
    nodes.push(stale);
  }
  nodes.push(overview(data, positions, available), records(data, positions, orders, available, state, openDetails), details);
  root.replaceChildren(...nodes);
}

export function renderAccountError(root, message, retry) {
  const button = el("button", "account-button primary", "重新加载");
  button.type = "button";
  button.addEventListener("click", retry);
  const error = emptyState("暂时无法读取账户", "请检查账户连接后重试。", button);
  error.classList.add("account-error");
  error.setAttribute("role", "alert");
  const detail = el("details", "account-error-detail");
  detail.append(el("summary", "", "查看原因"), el("p", "account-technical", message));
  error.append(detail);
  root.replaceChildren(error);
}
