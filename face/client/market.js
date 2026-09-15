/** Personal cross-market watchlist. Prices only come from the producer; the
 * shared reference directory contains identities, never sample quotations. */
import { REFERENCE_ASSETS } from "./market-catalog.js";
import { STORAGE_KEY, MARKET_INFO, normalizeAsset, readWatchlist, saveWatchlist, filterWatchlist, sortWatchlist, number, price, signed, percent, quoteTime } from "./market-model.js";

const $ = (selector) => document.querySelector(selector);
const dialog = $("#symbol-search");
const query = $("#symbol-query");
let storage;
try { storage = window.localStorage; } catch { storage = null; }
const saved = readWatchlist(storage);
const state = { items: saved.items, market: "all", searchMarket: "all", sort: { key: "default", direction: "asc" } };
let catalog = REFERENCE_ASSETS.map(normalizeAsset).filter(Boolean);
for (const asset of state.items) if (!catalog.some((entry) => entry.id === asset.id)) catalog.push(asset);
let quotes = Object.create(null);
let loading = false;
let payload = null;
let refreshFailed = false;
let undo = null;
let toastTimer;
let returnFocus;
let unsavedChanges = false;

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function tone(value) { const n = number(value); return n === null || n === 0 ? "" : n > 0 ? "market-up" : "market-down"; }
function setNotice(message) { $("#storage-notice").textContent = message || ""; $("#storage-notice").hidden = !message; }
function persist() {
  const error = saveWatchlist(storage, state.items);
  unsavedChanges = Boolean(error);
  setNotice(error);
  return error;
}
function has(id) { return state.items.some((item) => item.id === id); }
function assetIdentity(asset) {
  const wrap = el("div", "market-asset");
  const mark = asset.market === "cn" ? asset.name.slice(0, 1) : asset.symbol.split("/")[0].slice(0, 3);
  const info = el("div");
  const symbol = el("span", "asset-symbol", asset.symbol);
  symbol.append(el("span", "asset-market", MARKET_INFO[asset.market].label));
  info.append(symbol, el("span", "asset-name", asset.name));
  wrap.append(el("span", `asset-mark ${asset.market}`, mark), info);
  return wrap;
}
function toast(message, canUndo = false) {
  clearTimeout(toastTimer);
  if (!canUndo) undo = null;
  $("#market-toast span").textContent = message;
  $("#undo-remove").hidden = !canUndo;
  $("#market-toast").hidden = false;
  toastTimer = setTimeout(() => {
    if (document.activeElement === $("#undo-remove")) (dialog.open ? query : $("#add-symbol")).focus();
    $("#market-toast").hidden = true;
    undo = null;
  }, 6000);
}
function addAsset(asset) {
  if (has(asset.id)) return;
  state.items.push(asset);
  // Adding from another market should make the new row visible immediately.
  if (state.market !== "all" && state.market !== asset.market) state.market = "all";
  const error = persist();
  renderWatchlist();
  toast(`已添加 ${asset.name}${error ? " · 本次修改尚未保存" : ""}`);
}
function removeAsset(id) {
  const index = state.items.findIndex((asset) => asset.id === id);
  if (index < 0) return;
  const asset = state.items[index];
  undo = { asset, index };
  state.items.splice(index, 1);
  const error = persist();
  renderWatchlist();
  toast(`已移除 ${asset.name}${error ? " · 本次修改尚未保存" : ""}`, true);
}
function openSearch(market = state.market) {
  returnFocus = document.activeElement;
  state.searchMarket = market;
  query.value = "";
  renderSearch();
  // A modal makes sibling content inert, including an otherwise visible undo.
  dialog.append($("#market-toast"));
  dialog.showModal();
  query.focus();
}
function updateMarketButtons(container, market) {
  for (const button of container.querySelectorAll("button[data-market]")) {
    const active = button.dataset.market === market;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
}
function renderEmpty() {
  const empty = el("div", "market-empty");
  const symbol = el("div", "market-empty-symbol");
  symbol.setAttribute("aria-hidden", "true");
  // Fixed decorative markup, never interpolated with provider data.
  symbol.innerHTML = '<svg viewBox="0 0 30 30" width="30" height="30"><path d="m15 3 3.5 7.1 7.8 1.1-5.6 5.5 1.3 7.8-7-3.7-7 3.7 1.3-7.8-5.6-5.5 7.8-1.1Z"/></svg>';
  const title = state.items.length ? `还没有${MARKET_INFO[state.market]?.label || ""}自选` : "从你关注的第一个标的开始";
  const description = state.items.length ? "搜索并添加这个市场的标的，建立你的关注列表。" : "把关注的公司与加密货币加入自选，在这里查看它们的行情。";
  const button = el("button", "market-button", "搜索并添加");
  button.type = "button";
  button.addEventListener("click", () => openSearch());
  empty.append(symbol, el("h2", "", title), el("p", "", description), button);
  const suggestions = el("div", "market-suggestions");
  const samples = ["us:AAPL", "cn:600519", "crypto:BTC/USD"];
  for (const id of samples) {
    const asset = catalog.find((item) => item.id === id);
    if (!asset || has(id) || (state.market !== "all" && asset.market !== state.market)) continue;
    const chip = el("button", "market-suggestion");
    chip.type = "button";
    chip.setAttribute("aria-label", `添加 ${asset.name} 到自选`);
    chip.append(el("span", "", MARKET_INFO[asset.market].label), el("strong", "", asset.symbol.split("/")[0]), el("b", "", "+"));
    chip.addEventListener("click", () => { addAsset(asset); $("#add-symbol").focus(); });
    suggestions.append(chip);
  }
  empty.append(suggestions);
  return empty;
}
function renderWatchlist() {
  const root = $("#watchlist-content");
  const active = document.activeElement;
  const focusWasInside = root.contains(active);
  const focusedId = active?.closest("tr[data-asset-id]")?.dataset.assetId;
  const restoreFocus = () => {
    if (!focusWasInside) return;
    const row = Array.from(root.querySelectorAll("tr[data-asset-id]")).find((node) => node.dataset.assetId === focusedId);
    (row?.querySelector(".watchlist-remove") || root.querySelector(".market-empty .market-button") || $("#add-symbol")).focus();
  };
  updateMarketButtons($("#market-filters"), state.market);
  for (const node of document.querySelectorAll("[data-count]")) {
    node.textContent = node.dataset.count === "all" ? state.items.length : state.items.filter((item) => item.market === node.dataset.count).length;
  }
  const assets = state.items.map((item) => catalog.find((entry) => entry.id === item.id) || item);
  const rows = sortWatchlist(filterWatchlist(assets, state.market), quotes, state.sort);
  $("#list-summary").textContent = state.market === "all" ? `${state.items.length} 个自选` : `${rows.length} 个${MARKET_INFO[state.market].label}自选 · 共 ${state.items.length} 个`;
  if (!rows.length) { root.replaceChildren(renderEmpty()); restoreFocus(); return; }
  const scroll = el("div", "market-table-scroll");
  const table = el("table", "market-table");
  table.append(el("caption", "market-sr-only", "自选股行情；缺失数据以横线表示，历史快照不是实时价格。"));
  const head = el("thead");
  const header = el("tr");
  for (const [label, cls] of [["标的 / 名称", ""], ["最新价", ""], ["涨跌额", "quote-change-col"], ["涨跌幅", ""], ["成交量", "quote-volume-col"], ["行情来源 / 时间", "quote-source-col"], ["", ""]]) {
    const cell = el("th", cls, label); cell.scope = "col"; header.append(cell);
  }
  head.append(header);
  const body = el("tbody");
  for (const asset of rows) {
    const quote = quotes[asset.id] || {};
    const available = number(quote.price) !== null;
    const row = el("tr"); row.dataset.assetId = asset.id;
    const identity = el("td"); identity.append(assetIdentity(asset));
    const latest = el("td", "quote-price", price(quote.price, asset.currency));
    const shortTime = available ? quoteTime(quote.as_of) : "暂无报价";
    // The quote date stays visible even when the source column folds on mobile.
    latest.append(el("span", "quote-unit", `${asset.currency} · ${shortTime}`));
    const change = el("td", `quote-change-col ${tone(quote.change)}`, signed(quote.change));
    const percentage = el("td"); percentage.append(el("span", `quote-change-pill ${tone(quote.change_pct)}`, percent(quote.change_pct)));
    const volume = number(quote.volume);
    const quantity = el("td", "quote-volume-col", volume === null ? "—" : volume.toLocaleString("zh-CN", { maximumFractionDigits: 2 }));
    const source = el("td", "quote-source-col");
    const status = available ? (refreshFailed || payload?.stale ? "上次快照" : quote.quote_status === "snapshot" ? "历史快照" : "报价") : "暂无报价";
    const sourceText = el("div", "quote-source", status);
    sourceText.title = typeof quote.source === "string" ? quote.source : "";
    source.append(sourceText, el("span", "quote-time", typeof quote.source === "string" ? quote.source : "行情未接入"));
    const actions = el("td");
    const remove = el("button", "watchlist-remove", "×");
    remove.type = "button";
    remove.setAttribute("aria-label", `移除 ${asset.name}`);
    remove.title = `移除 ${asset.name}`;
    remove.addEventListener("click", () => { const index = rows.findIndex((item) => item.id === asset.id); removeAsset(asset.id); const buttons = root.querySelectorAll(".watchlist-remove"); (buttons[Math.min(index, buttons.length - 1)] || $("#add-symbol")).focus(); });
    actions.append(remove);
    row.append(identity, latest, change, percentage, quantity, source, actions);
    body.append(row);
  }
  table.append(head, body); scroll.append(table); root.replaceChildren(scroll); restoreFocus();
}
function renderSearch() {
  const focusedId = document.activeElement?.dataset?.searchId;
  updateMarketButtons($("#search-filters"), state.searchMarket);
  const matches = filterWatchlist(catalog, state.searchMarket, query.value);
  const rows = matches.slice(0, 60);
  $("#search-results-label").textContent = query.value.trim() ? "搜索结果" : "浏览标的";
  $("#search-count").textContent = `${matches.length} 个标的${matches.length > rows.length ? ` · 显示前 ${rows.length} 个` : ""}`;
  const results = $("#search-results");
  const nodes = rows.map((asset) => {
    const result = el("button", "symbol-result"); result.type = "button";
    result.dataset.searchId = asset.id;
    const selected = has(asset.id);
    result.setAttribute("aria-pressed", String(selected));
    result.setAttribute("aria-label", `${selected ? "移除" : "添加"} ${asset.name} ${asset.symbol}，${MARKET_INFO[asset.market].label}`);
    const meta = el("div", "symbol-result-meta");
    meta.append(el("span", "symbol-exchange", asset.exchange || asset.currency), el("span", "symbol-add-mark", selected ? "✓" : "+"));
    result.append(assetIdentity(asset), meta);
    result.addEventListener("click", () => { if (has(asset.id)) removeAsset(asset.id); else addAsset(asset); renderSearch(); });
    return result;
  });
  if (!nodes.length) nodes.push(el("div", "symbol-result-empty", "未找到已收录的标的。试试其他代码或名称，或切换到全部市场。"));
  results.replaceChildren(...nodes);
  if (focusedId) (Array.from(results.querySelectorAll("button")).find((button) => button.dataset.searchId === focusedId) || query).focus();
}
async function load() {
  if (loading) return;
  loading = true;
  $("#refresh").disabled = true;
  $("#refresh").setAttribute("aria-label", "正在刷新行情");
  $("#data-status").textContent = "正在读取行情目录…";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);
  try {
    const res = await fetch("/data/watchlist.json", { signal: controller.signal });
    let data;
    try { data = await res.json(); } catch { throw new Error("行情服务未连接"); }
    if (!res.ok || data?.ok !== true || !Array.isArray(data.assets)) throw new Error("行情暂不可用");
    const merged = new Map(REFERENCE_ASSETS.map((asset) => [asset.id, normalizeAsset(asset)]));
    const nextQuotes = Object.create(null);
    for (const row of data.assets) {
      const asset = normalizeAsset(row);
      if (!asset) continue;
      merged.set(asset.id, asset); nextQuotes[asset.id] = row;
    }
    // Saved identities remain searchable when a newer directory no longer lists them.
    for (const asset of state.items) if (!merged.has(asset.id)) merged.set(asset.id, asset);
    catalog = Array.from(merged.values()).filter(Boolean);
    quotes = nextQuotes;
    payload = data; refreshFailed = false;
    $("#data-status").textContent = `${data.stale ? "保留上次行情 · " : "目录读取于 "}${quoteTime(data.generated_at)}`;
    $("#data-note").textContent = typeof data.note === "string" ? data.note : "美股显示历史日线快照；A 股与加密货币暂无报价。";
    $("#search-catalog-note").textContent = "搜索已收录标的，目录不代表全市场；报价以标注日期为准。";
  } catch {
    refreshFailed = true;
    $("#data-status").textContent = payload ? "刷新失败，保留上次行情。" : "行情未连接 · 仍可搜索、添加与管理自选";
    $("#data-note").textContent = payload ? `上次读取：${quoteTime(payload.generated_at)}。各标的报价时间见列表，点击刷新重试。` : "当前可搜索基础标的目录；完整目录及报价需连接本地行情服务。";
    $("#search-catalog-note").textContent = "基础标的目录，非完整市场；连接行情服务后可读取更多标的。";
  } finally {
    clearTimeout(timeout); loading = false; $("#refresh").disabled = false; $("#refresh").setAttribute("aria-label", "刷新行情");
    renderWatchlist(); if (dialog.open) renderSearch();
  }
}

$("#search-open").setAttribute("aria-label", "搜索股票、加密货币");
$("#search-open").addEventListener("click", () => openSearch("all"));
$("#add-symbol").addEventListener("click", () => openSearch());
$("#search-close").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => {
  document.body.append($("#market-toast"));
  (returnFocus?.isConnected ? returnFocus : $("#add-symbol")).focus();
});
dialog.addEventListener("click", (event) => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } });
query.addEventListener("input", renderSearch);
$("#search-filters").addEventListener("click", (event) => { const button = event.target.closest("button[data-market]"); if (!button) return; state.searchMarket = button.dataset.market; renderSearch(); });
$("#market-filters").addEventListener("click", (event) => { const button = event.target.closest("button[data-market]"); if (!button) return; state.market = button.dataset.market; renderWatchlist(); });
$("#watchlist-sort").addEventListener("change", (event) => { const [key, direction = "asc"] = event.target.value.split(":"); state.sort = { key, direction }; renderWatchlist(); });
$("#refresh").addEventListener("click", () => void load());
$("#undo-remove").addEventListener("click", () => {
  if (!undo || has(undo.asset.id)) return;
  const { asset, index } = undo; undo = null;
  state.items.splice(Math.min(index, state.items.length), 0, asset);
  const error = persist();
  renderWatchlist(); if (dialog.open) renderSearch();
  toast(`已恢复 ${asset.name}${error ? " · 本次修改尚未保存" : ""}`);
  (dialog.open ? query : $("#add-symbol")).focus();
});
dialog.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !event.isComposing) {
    event.preventDefault();
    dialog.close();
    return;
  }
  // Enter confirms a Chinese IME candidate before it can act on a search result.
  if (event.isComposing || event.keyCode === 229) return;
  const buttons = Array.from($("#search-results").querySelectorAll("button"));
  if (!buttons.length) return;
  const index = buttons.indexOf(document.activeElement);
  if (document.activeElement !== query && index < 0) return;
  if (event.key === "ArrowDown") { event.preventDefault(); buttons[Math.min(index + 1, buttons.length - 1)].focus(); }
  if (event.key === "ArrowUp") { event.preventDefault(); if (index <= 0) query.focus(); else buttons[index - 1].focus(); }
  if (event.key === "Enter" && document.activeElement === query) {
    event.preventDefault();
    if (has(buttons[0].dataset.searchId)) toast("该标的已在自选中");
    else buttons[0].click();
    query.focus();
  }
});
const apple = /Mac|iPhone|iPad/.test(navigator.platform);
$("#search-shortcut").textContent = apple ? "⌘ K" : "Ctrl K";
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); if (!dialog.open) openSearch("all"); else query.focus(); }
});
window.addEventListener("storage", (event) => {
  if (event.key !== STORAGE_KEY && event.key !== null) return;
  if (event.storageArea && event.storageArea !== storage) return;
  const latest = readWatchlist(storage);
  if (latest.error) { setNotice(`${latest.error} 页面当前自选已保留。`); return; }
  if (unsavedChanges) { setNotice("其他页面已更新自选；本页有未保存的修改，当前列表已保留。"); return; }
  state.items = latest.items;
  for (const asset of state.items) if (!catalog.some((entry) => entry.id === asset.id)) catalog.push(asset);
  setNotice(null); renderWatchlist(); if (dialog.open) renderSearch();
});
setNotice(saved.error);
renderWatchlist();
void load();
