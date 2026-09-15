/** Personal cross-market watchlist. Search discovers instruments on demand;
 * reference suggestions contain identities, never sample quotations. */
import { REFERENCE_ASSETS } from "./market-catalog.js";
import { createSymbolSearch } from "./market-search.js";
import { createLiveQuotes, describeQuote, quoteConnectionLabel, quoteSource } from "./market-quotes.js";
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
let quoteState = { status: "idle", refreshing: false, providers: [], note: "添加自选后自动连接行情。", limited: 0 };
let undo = null;
let toastTimer;
let returnFocus;
let unsavedChanges = false;
let composingSearch = false;
let searchState = { status: "idle", assets: [], partial: false, truncated: false, note: "" };
const SEARCH_NOTE = "输入名称或代码查询市场标的；搜索结果不代表实时报价。";
const symbolSearch = createSymbolSearch((next) => {
  searchState = next;
  if (next.status === "success") {
    const merged = new Map(catalog.map((asset) => [asset.id, asset]));
    for (const asset of next.assets) merged.set(asset.id, asset);
    catalog = [...merged.values()];
  }
  if (dialog.open) renderSearch();
});
const liveQuotes = createLiveQuotes((next) => {
  quoteState = next;
  quotes = next.quotes;
  renderQuoteStatus();
  renderWatchlist();
});

function renderQuoteStatus() {
  $("#data-status").textContent = quoteConnectionLabel(quoteState.status, quoteState.providers, state.items.map((asset) => asset.market));
  $("#refresh").disabled = !state.items.length || quoteState.refreshing;
  $("#refresh").setAttribute("aria-label", quoteState.refreshing ? "正在刷新行情" : "刷新行情");
  const selectedMarkets = new Set(state.items.map((asset) => asset.market));
  const providerNotes = quoteState.providers.filter((provider) => selectedMarkets.has(provider.market)).map((provider) => {
    const label = MARKET_INFO[provider.market].label;
    if (provider.id === "ifind" && provider.status === "unconfigured") return "A 股行情待配置 iFinD";
    const status = { connecting: "连接中", connected: provider.transport === "poll" ? "定时更新" : "已连接", unconfigured: "待配置", error: "连接异常", limited: "订阅受限" }[provider.status];
    const source = quoteSource(provider.source, provider.feed);
    return `${label}：${source} ${status}${provider.message ? ` · ${provider.message}` : ""}`;
  });
  if (selectedMarkets.has("cn") && !quoteState.providers.some((provider) => provider.market === "cn")) providerNotes.push("A 股行情待配置 iFinD");
  $("#data-note").textContent = [quoteState.note, ...providerNotes,
    state.items.length ? "美股与 A 股涨跌以昨收为基准；加密货币为过去 24 小时。时间显示行情事件时间，非页面刷新时间。" : "",
    quoteState.limited ? `最多连接 100 个标的；另有 ${quoteState.limited} 个暂未订阅。` : "",
  ].filter(Boolean).join(" ");
}

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
  if (state.items.length >= 100) { toast("最多添加 100 个自选，请先移除一个标的。"); return; }
  state.items.push(asset);
  // Adding from another market should make the new row visible immediately.
  if (state.market !== "all" && state.market !== asset.market) state.market = "all";
  const error = persist();
  liveQuotes.setAssets(state.items);
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
  liveQuotes.setAssets(state.items);
  renderWatchlist();
  toast(`已移除 ${asset.name}${error ? " · 本次修改尚未保存" : ""}`, true);
}
function openSearch(market = state.market) {
  returnFocus = document.activeElement;
  state.searchMarket = market;
  query.value = "";
  composingSearch = false;
  symbolSearch.search("", market);
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
    (row?.querySelector(".watchlist-remove") || root.querySelector(".market-empty .market-button") || $("#add-symbol")).focus({ preventScroll: true });
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
  table.append(el("caption", "market-sr-only", "自选行情；缺失数据以横线表示。各标的标明行情来源、事件时间及实时、延迟或过期状态。"));
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
    const description = describeQuote(asset, quote, quoteState.providers, quoteState.status);
    const status = description.status;
    const shortTime = available ? quoteTime(quote.as_of) : status;
    // The quote date stays visible even when the source column folds on mobile.
    latest.append(el("span", "quote-unit", `${asset.currency} · ${shortTime}`));
    if (available) latest.append(el("span", "quote-unit", status));
    const change = el("td", `quote-change-col ${tone(quote.change)}`, signed(quote.change));
    const percentage = el("td");
    percentage.append(el("span", `quote-change-pill ${tone(quote.change_pct)}`, percent(quote.change_pct)),
      el("span", "quote-unit", quote.basis === "24h" || asset.market === "crypto" ? "24 小时" : "较昨收"));
    const volume = number(quote.volume);
    const quantity = el("td", "quote-volume-col", volume === null ? "—" : volume.toLocaleString("zh-CN", { maximumFractionDigits: asset.market === "crypto" ? 8 : 2 }));
    if (volume !== null && description.volumeUnit) quantity.append(el("span", "quote-unit", description.volumeUnit));
    const source = el("td", "quote-source-col");
    const sourceText = el("div", "quote-source", description.source);
    sourceText.title = [quote.message, quote.received_at ? `接收时间：${quoteTime(quote.received_at)}` : ""].filter(Boolean).join(" · ");
    source.append(sourceText, el("span", "quote-time", status));
    if (volume !== null && quote.volume_as_of) quantity.title = `成交量时间：${quoteTime(quote.volume_as_of)}`;
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
  const previousScroll = root.querySelector(".market-table-scroll")?.scrollLeft || 0;
  table.append(head, body); scroll.append(table); root.replaceChildren(scroll); scroll.scrollLeft = previousScroll; restoreFocus();
}
function renderSearch() {
  const focusedId = document.activeElement?.dataset?.searchId;
  updateMarketButtons($("#search-filters"), state.searchMarket);
  const searching = composingSearch || Boolean(query.value.trim());
  const pending = searching && (composingSearch || searchState.status === "loading");
  const failed = searching && searchState.status === "error";
  const suggestions = [...new Map([...REFERENCE_ASSETS, ...state.items].map((asset) => [asset.id, asset])).values()];
  const matches = searching
    ? searchState.status === "success" && !composingSearch ? searchState.assets : []
    : filterWatchlist(suggestions, state.searchMarket);
  const rows = matches.slice(0, 60);
  $("#search-results-label").textContent = searching ? "搜索结果" : "自选与常用";
  $("#search-count").textContent = pending ? "正在搜索…" : failed ? "搜索暂不可用"
    : `${matches.length} 个标的${searching && searchState.partial ? " · 部分结果" : ""}${matches.length > rows.length ? ` · 显示前 ${rows.length} 个` : ""}`;
  $("#search-catalog-note").textContent = [
    searching && searchState.note ? searchState.note : SEARCH_NOTE,
    searching && searchState.truncated ? "显示最相关的匹配，输入更完整的名称或代码可缩小范围。" : "",
  ].filter(Boolean).join(" ");
  const results = $("#search-results");
  results.setAttribute("aria-busy", String(pending));
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
  if (!nodes.length) {
    const message = pending ? (composingSearch ? "输入名称或代码…" : "正在查询市场标的…")
      : failed ? (searchState.note || "搜索服务暂不可用，请稍后重试。")
      : searching ? (searchState.partial ? "暂未找到匹配标的；部分市场查询未成功，请重试。"
        : "未找到匹配标的，请检查名称、代码或切换市场。") : "这里还没有常用标的，输入名称或代码开始搜索。";
    const empty = el("div", "symbol-result-empty", message);
    if (failed || (searching && searchState.partial)) {
      const retry = el("button", "market-button", "重新搜索"); retry.type = "button";
      retry.addEventListener("click", () => symbolSearch.search(query.value, state.searchMarket));
      empty.append(retry);
    }
    nodes.push(empty);
  }
  results.replaceChildren(...nodes);
  if (focusedId) (Array.from(results.querySelectorAll("button")).find((button) => button.dataset.searchId === focusedId) || query).focus();
}
$("#search-open").setAttribute("aria-label", "搜索股票、加密货币");
$("#search-open").addEventListener("click", () => openSearch("all"));
$("#add-symbol").addEventListener("click", () => openSearch());
$("#search-close").addEventListener("click", () => dialog.close());
dialog.addEventListener("close", () => {
  symbolSearch.cancel();
  composingSearch = false;
  document.body.append($("#market-toast"));
  (returnFocus?.isConnected ? returnFocus : $("#add-symbol")).focus();
});
dialog.addEventListener("click", (event) => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } });
query.addEventListener("compositionstart", () => { composingSearch = true; symbolSearch.cancel(); renderSearch(); });
query.addEventListener("compositionend", () => { composingSearch = false; symbolSearch.search(query.value, state.searchMarket); });
query.addEventListener("input", (event) => {
  if (event.isComposing || composingSearch) renderSearch();
  else symbolSearch.search(query.value, state.searchMarket);
});
$("#search-filters").addEventListener("click", (event) => { const button = event.target.closest("button[data-market]"); if (!button) return; state.searchMarket = button.dataset.market; symbolSearch.search(query.value, state.searchMarket); renderSearch(); });
$("#market-filters").addEventListener("click", (event) => { const button = event.target.closest("button[data-market]"); if (!button) return; state.market = button.dataset.market; renderWatchlist(); });
$("#watchlist-sort").addEventListener("change", (event) => { const [key, direction = "asc"] = event.target.value.split(":"); state.sort = { key, direction }; renderWatchlist(); });
$("#refresh").addEventListener("click", () => liveQuotes.refresh());
$("#undo-remove").addEventListener("click", () => {
  if (!undo || has(undo.asset.id)) return;
  const { asset, index } = undo; undo = null;
  state.items.splice(Math.min(index, state.items.length), 0, asset);
  const error = persist();
  liveQuotes.setAssets(state.items);
  renderWatchlist(); if (dialog.open) renderSearch();
  toast(`已恢复 ${asset.name}${error ? " · 本次修改尚未保存" : ""}`);
  (dialog.open ? query : $("#add-symbol")).focus();
});
dialog.addEventListener("keydown", (event) => {
  // Candidate confirmation/cancellation belongs to the IME, not the dialog.
  if (composingSearch || event.isComposing || event.keyCode === 229) {
    if (event.key === "Escape") event.preventDefault();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    dialog.close();
    return;
  }
  const buttons = Array.from($("#search-results").querySelectorAll("button[data-search-id]"));
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
  liveQuotes.setAssets(state.items);
  setNotice(null); renderWatchlist(); if (dialog.open) renderSearch();
});
setNotice(saved.error);
$("#search-catalog-note").textContent = SEARCH_NOTE;
document.addEventListener("visibilitychange", () => liveQuotes.setVisible(document.visibilityState !== "hidden"));
window.addEventListener("pagehide", () => liveQuotes.setVisible(false));
window.addEventListener("pageshow", () => liveQuotes.setVisible(document.visibilityState !== "hidden"));
liveQuotes.setVisible(document.visibilityState !== "hidden");
liveQuotes.setAssets(state.items);
renderQuoteStatus();
renderWatchlist();
