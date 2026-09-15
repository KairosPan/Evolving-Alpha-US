import { normalizeAsset, number } from "./market-model.js";

/** @typedef {import('../src/quote-types.ts').LiveQuote} LiveQuote */
/** @typedef {import('../src/quote-types.ts').ProviderState} ProviderState */
/** @typedef {{quotes: Record<string, LiveQuote>, providers: ProviderState[], status: 'idle'|'connecting'|'streaming'|'polling'|'error'|'paused', refreshing: boolean, generatedAt: string|null, note: string, limited: number}} QuoteState */
/** @typedef {{addEventListener: (name: string, listener: (event: {data?: string}) => void) => void, close: () => void}} QuoteEvents */

const STATUSES = new Set(["live", "delayed", "stale", "unavailable"]);
const PROVIDER_STATUSES = new Set(["connecting", "connected", "unconfigured", "error", "limited"]);
const MARKETS = new Set(["us", "cn", "crypto"]);
const timestamp = (value) => typeof value === "string" && Number.isFinite(Date.parse(value));

/** Provider feed names are metadata, not product labels. Unknown enum values stay hidden.
 * @param {string} [source] @param {string} [feed]
 */
export function quoteSource(source = "", feed = "") {
  const labels = { iex: "IEX 单一交易所", sip: "SIP 综合行情", delayed_sip: "延迟综合行情", exchange: "现货", ticker: "现货", realtime: "定时行情" };
  return [source, labels[feed.toLowerCase()]].filter(Boolean).join(" · ");
}

/** SSE connectivity alone says nothing about whether a market's provider is usable.
 * @param {string} status @param {ProviderState[]} providers @param {string[]} markets
 */
export function quoteConnectionLabel(status, providers, markets) {
  if (!markets.length || status === "idle") return "添加自选后自动连接行情";
  if (status === "paused") return "行情连接已暂停";
  if (status === "error") return "行情连接暂不可用";
  const relevant = [...new Set(markets)].map((market) => providers.find((provider) => provider.market === market));
  if (relevant.every((provider) => provider?.status === "unconfigured")) {
    return markets.every((market) => market === "cn") ? "A 股行情待配置 iFinD" : "行情源待配置";
  }
  const connected = relevant.filter((provider) => provider?.status === "connected");
  if (connected.length === 0) {
    if (relevant.some((provider) => !provider || provider.status === "connecting")) return "正在连接行情…";
    return relevant.some((provider) => provider?.status === "error") ? "行情源暂不可用" : "行情订阅受限";
  }
  if (connected.length !== relevant.length) return "部分市场行情可用";
  if (status === "polling") return "备用行情 · 每 15 秒更新";
  if (status === "connecting") return "正在恢复行情连接…";
  if (connected.every((provider) => provider.transport === "poll")) return "行情定时更新";
  return connected.some((provider) => provider.transport === "poll") ? "行情已连接 · 部分定时更新" : "行情已连接";
}

/** The regular-session clock does not imply premarket/after-hours trading has stopped.
 * @param {{market: string, symbol: string}} asset
 * @param {Partial<LiveQuote>} quote
 * @param {ProviderState[]} providers
 * @param {string} transportStatus
 */
export function describeQuote(asset, quote, providers, transportStatus) {
  const provider = providers.find((item) => item.market === asset.market);
  const available = number(quote.price) !== null;
  let status;
  if (!available) {
    if (asset.market === "cn" && (!provider || provider.status === "unconfigured")) status = "行情待配置 iFinD";
    else if (provider?.status === "unconfigured") status = "行情待配置";
    else if (provider?.status === "connecting" || transportStatus === "connecting") status = "连接中";
    else status = "暂无报价";
  } else {
    status = quote.quote_status === "stale" ? "上次报价 · 待更新"
      : quote.quote_status === "delayed" ? "延迟报价"
      : quote.quote_status === "live" ? (quote.transport === "poll" || provider?.transport === "poll" || transportStatus === "polling" ? "定时更新" : "实时") : "上次报价";
    if (quote.market_status === "closed") status += " · 常规交易休市";
  }
  return {
    status,
    source: quoteSource(quote.source || provider?.source || (asset.market === "cn" ? "iFinD" : "等待行情源"), quote.feed || provider?.feed || ""),
    volumeUnit: asset.market === "crypto" ? `24h · ${asset.symbol.split("/")[0]}` : asset.market === "us" ? "股" : "",
  };
}

/** Full payload validation prevents an error or malformed snapshot from clearing good quotes. */
function parsePayload(raw) {
  if (!raw || raw.ok !== true || !timestamp(raw.generated_at) || !Array.isArray(raw.quotes) || !Array.isArray(raw.providers)) throw new Error("行情响应格式无效");
  const seen = new Set();
  for (const quote of raw.quotes) {
    const asset = normalizeAsset(quote);
    if (!asset || quote.id !== asset.id || seen.has(quote.id) || !STATUSES.has(quote.quote_status)
      || !["previous_close", "24h"].includes(quote.basis) || !["open", "closed", "unknown"].includes(quote.market_status)
      || typeof quote.source !== "string" || typeof quote.feed !== "string" || typeof quote.message !== "string"
      || (quote.transport !== undefined && !["stream", "poll"].includes(quote.transport))
      || ["price", "prev_close", "change", "change_pct", "volume"].some((key) => quote[key] !== null && (typeof quote[key] !== "number" || !Number.isFinite(quote[key])))
      || ["as_of", "received_at", "volume_as_of"].some((key) => quote[key] !== null && !timestamp(quote[key]))) throw new Error("行情响应格式无效");
    seen.add(asset.id);
  }
  for (const provider of raw.providers) {
    if (!provider || !["alpaca", "ifind", "coinbase"].includes(provider.id) || !MARKETS.has(provider.market)
      || !PROVIDER_STATUSES.has(provider.status) || !["stream", "poll"].includes(provider.transport)
      || ["source", "feed", "message"].some((key) => typeof provider[key] !== "string")) throw new Error("行情源状态无效");
  }
  return raw;
}

/** Selected-asset quote transport, independent of symbol search and browser DOM.
 * REST and stream callbacks carry revisions so cancellation remains effective even
 * when a transport ignores AbortSignal or delivers an event after close().
 * @param {(state: QuoteState) => void} onUpdate
 * @param {{fetcher?: typeof fetch, createEventSource?: ((url: string) => QuoteEvents)|null, schedule?: (callback: () => void, delay: number) => any, cancelTimer?: (timer: any) => void, requestTimeoutMs?: number, heartbeatTimeoutMs?: number, pollMs?: number, retryDelays?: number[]}} [options]
 */
export function createLiveQuotes(onUpdate, {
  fetcher = globalThis.fetch,
  createEventSource = typeof globalThis.EventSource === "function" ? (url) => new globalThis.EventSource(url) : null,
  schedule = setTimeout, cancelTimer = clearTimeout,
  requestTimeoutMs = 10_000, heartbeatTimeoutMs = 35_000, pollMs = 15_000,
  retryDelays = [1_000, 3_000, 10_000],
} = {}) {
  let ids = [];
  let visible = true;
  let disposed = false;
  let revision = 0;
  let requestRevision = 0;
  let streamRevision = 0;
  let stream = null;
  let streamReady = false;
  let controller = null;
  let requestTimer = null;
  let heartbeatTimer = null;
  let stableTimer = null;
  let pollTimer = null;
  let retryTimer = null;
  let retries = 0;
  /** @type {QuoteState} */
  let state = { quotes: Object.create(null), providers: [], status: "idle", refreshing: false, generatedAt: null, note: "", limited: 0 };

  function publish(patch = {}) {
    if (disposed) return;
    state = { ...state, ...patch };
    onUpdate(state);
  }
  function stale() {
    return Object.fromEntries(ids.filter((id) => state.quotes[id]).map((id) => {
      const quote = state.quotes[id];
      return [id, number(quote.price) === null ? quote : { ...quote, quote_status: "stale" }];
    }));
  }
  function cancelRequest() {
    requestRevision += 1;
    cancelTimer(requestTimer); requestTimer = null;
    controller?.abort(); controller = null;
  }
  function stopStream() {
    streamRevision += 1;
    stream?.close(); stream = null; streamReady = false;
    cancelTimer(heartbeatTimer); heartbeatTimer = null;
    cancelTimer(stableTimer); stableTimer = null;
  }
  function stop() {
    revision += 1;
    cancelRequest(); stopStream();
    cancelTimer(pollTimer); pollTimer = null;
    cancelTimer(retryTimer); retryTimer = null;
  }
  function url(path) { return `${path}?ids=${encodeURIComponent(ids.join(","))}`; }
  function active(token) { return !disposed && visible && ids.length > 0 && token === revision; }
  function applyPayload(data) {
    const incoming = new Map(data.quotes.map((quote) => [quote.id, quote]));
    const next = Object.create(null);
    for (const id of ids) {
      const quote = incoming.get(id);
      const previous = state.quotes[id];
      if (quote && number(quote.price) !== null) next[id] = { ...quote };
      else if (previous && number(previous.price) !== null) {
        // Last-good values keep their original event time and source.
        next[id] = { ...previous, quote_status: "stale", message: quote?.message || "暂未收到新报价" };
      } else if (quote) next[id] = { ...quote };
    }
    return { quotes: next, providers: data.providers.map((provider) => ({ ...provider })), generatedAt: data.generated_at };
  }
  function schedulePoll(token) {
    if (!active(token) || streamReady || pollTimer !== null) return;
    pollTimer = schedule(() => { pollTimer = null; void request(token); }, pollMs);
  }
  function requestFailed(token, message) {
    if (!active(token)) return;
    if (streamReady) { publish({ refreshing: false, status: "streaming", note: "手动刷新失败，实时行情连接仍保持。" }); return; }
    publish({ quotes: stale(), refreshing: false, status: "error", note: message });
    schedulePoll(token);
  }
  async function request(token = revision) {
    if (!active(token) || controller) return;
    cancelTimer(pollTimer); pollTimer = null;
    const requestToken = ++requestRevision;
    const ownController = new AbortController(); controller = ownController;
    publish({ refreshing: true });
    // Invalidate, do not just abort: a noncompliant fetch may still resolve later.
    requestTimer = schedule(() => {
      if (!active(token) || requestToken !== requestRevision) return;
      cancelRequest(); requestFailed(token, "行情读取超时；保留上次报价，稍后自动重试。");
    }, requestTimeoutMs);
    try {
      const response = await fetcher(url("/data/quotes"), { signal: ownController.signal, headers: { Accept: "application/json" }, cache: "no-store" });
      if (!active(token) || requestToken !== requestRevision) return;
      if (!response.ok) throw new Error("行情读取失败");
      const data = parsePayload(await response.json());
      if (!active(token) || requestToken !== requestRevision) return;
      if (!state.generatedAt || Date.parse(data.generated_at) >= Date.parse(state.generatedAt)) {
        publish({ ...applyPayload(data), refreshing: false, status: streamReady ? "streaming" : "polling", note: streamReady ? "" : "实时连接暂不可用，每 15 秒读取报价。" });
      } else publish({ refreshing: false });
    } catch {
      if (!active(token) || requestToken !== requestRevision) return;
      requestFailed(token, "行情读取失败；保留上次报价，稍后自动重试。");
    } finally {
      if (active(token) && requestToken === requestRevision) {
        cancelTimer(requestTimer); requestTimer = null; controller = null;
        schedulePoll(token);
      }
    }
  }
  function failStream(token, streamToken) {
    if (!active(token) || streamToken !== streamRevision) return;
    stopStream();
    publish({ quotes: stale(), status: "polling", note: "实时连接已断开，正在读取备用报价。" });
    void request(token);
    if (createEventSource && retries < retryDelays.length) {
      const delay = retryDelays[retries++];
      retryTimer = schedule(() => { retryTimer = null; connect(token); }, delay);
    }
  }
  function armHeartbeat(token, streamToken, delay) {
    cancelTimer(heartbeatTimer);
    heartbeatTimer = schedule(() => failStream(token, streamToken), delay);
  }
  function connect(token = revision) {
    if (!active(token)) return;
    if (!createEventSource) { publish({ status: "polling", note: "每 15 秒读取报价。" }); void request(token); return; }
    stopStream();
    const streamToken = streamRevision;
    publish({ status: "connecting" });
    try {
      stream = createEventSource(url("/data/quotes/stream"));
      armHeartbeat(token, streamToken, requestTimeoutMs);
      stream.addEventListener("quotes", (event) => {
        if (!active(token) || streamToken !== streamRevision) return;
        let data;
        try { data = parsePayload(JSON.parse(event.data)); }
        catch { failStream(token, streamToken); return; }
        armHeartbeat(token, streamToken, heartbeatTimeoutMs);
        // A fresh stream update wins over any earlier REST request, even its JSON parse.
        cancelRequest(); cancelTimer(pollTimer); pollTimer = null;
        streamReady = true;
        if (stableTimer === null) stableTimer = schedule(() => { if (active(token) && streamToken === streamRevision) retries = 0; stableTimer = null; }, 60_000);
        if (!state.generatedAt || Date.parse(data.generated_at) >= Date.parse(state.generatedAt)) {
          publish({ ...applyPayload(data), status: "streaming", refreshing: false, note: "" });
        } else publish({ status: "streaming", refreshing: false });
      });
      stream.addEventListener("heartbeat", () => {
        if (active(token) && streamToken === streamRevision && streamReady) armHeartbeat(token, streamToken, heartbeatTimeoutMs);
      });
      stream.addEventListener("error", () => failStream(token, streamToken));
    } catch { failStream(token, streamToken); }
  }
  function begin() {
    retries = 0;
    if (!ids.length) { publish({ status: "idle", refreshing: false, note: "添加自选后自动连接行情。", quotes: Object.create(null), providers: [], generatedAt: null }); return; }
    publish({ quotes: stale(), refreshing: false, status: visible ? "connecting" : "paused", note: visible ? "正在连接所选标的行情…" : "页面已隐藏，行情连接已暂停。" });
    if (visible) connect();
  }
  return {
    /** @param {unknown[]} assets */
    setAssets(assets) {
      if (disposed) return;
      const all = [...new Set(assets.map(normalizeAsset).filter(Boolean).map((asset) => asset.id))];
      const next = all.slice(0, 100);
      const same = next.length === ids.length && next.every((id) => ids.includes(id));
      const limited = Math.max(0, all.length - next.length);
      if (same) { if (limited !== state.limited) publish({ limited }); return; }
      stop(); ids = next;
      state = { ...state, limited, generatedAt: null };
      begin();
    },
    /** @param {boolean} next */
    setVisible(next) {
      if (disposed || visible === Boolean(next)) return;
      stop(); visible = Boolean(next); begin();
    },
    refresh() {
      if (disposed || !visible || !ids.length) return;
      cancelRequest();
      if (!streamReady) { cancelTimer(retryTimer); retryTimer = null; retries = 0; connect(); }
      void request();
    },
    close() { if (!disposed) { stop(); disposed = true; } },
  };
}
