import { normalizeAsset } from "./market-model.js";

const REQUEST_TIMEOUT_MS = 10_000;
const UNAVAILABLE = "搜索服务暂时不可用，请稍后重试。";
const INVALID_RESPONSE = "搜索服务返回了无法识别的数据，请稍后重试。";

/** @typedef {import('./market-model.js').Asset} Asset */
/** @typedef {{query: string, market: string, status: 'idle'|'loading'|'success'|'error', assets: Asset[], partial: boolean, truncated: boolean, note: string}} SearchState */

/** Validate the whole result: a malformed response is never a successful empty search.
 * @param {unknown} payload
 * @param {string} market
 */
function parseResult(payload, market) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)
    || payload.ok !== true || !Array.isArray(payload.assets) || !Array.isArray(payload.providers)
    || typeof payload.partial !== "boolean" || typeof payload.truncated !== "boolean"
    || (payload.note !== undefined && typeof payload.note !== "string")
    || payload.providers.some((provider) => !provider || typeof provider !== "object"
      || typeof provider.id !== "string" || !provider.id.trim()
      || typeof provider.status !== "string" || !provider.status.trim()
      || (provider.message !== undefined && typeof provider.message !== "string"))) {
    throw new Error(INVALID_RESPONSE);
  }
  const assets = [];
  const seen = new Set();
  for (const raw of payload.assets) {
    const asset = normalizeAsset(raw);
    if (!asset || (market !== "all" && asset.market !== market)) throw new Error(INVALID_RESPONSE);
    if (!seen.has(asset.id)) {
      seen.add(asset.id);
      assets.push(asset);
    }
  }
  const note = payload.note?.trim() || [
    payload.partial ? "部分市场搜索暂不可用，已显示可用结果。" : "",
    payload.truncated ? "结果较多，请输入更完整的代码或名称。" : "",
  ].filter(Boolean).join(" ");
  return { assets, partial: payload.partial, truncated: payload.truncated, note };
}

/** Search on demand, debounce typing, and let only the latest request update the UI.
 * The server owns caching. Closing the search UI must call cancel().
 * @param {(state: SearchState) => void} onUpdate
 * @param {{fetcher?: typeof fetch, delayMs?: number}} [options]
 */
export function createSymbolSearch(onUpdate, { fetcher = fetch, delayMs = 250 } = {}) {
  let revision = 0;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let debounceTimer = null;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let timeoutTimer = null;
  /** @type {AbortController | null} */
  let controller = null;
  let lastMarket = "all";

  function stop() {
    revision += 1;
    clearTimeout(debounceTimer);
    clearTimeout(timeoutTimer);
    debounceTimer = null;
    timeoutTimer = null;
    controller?.abort();
    controller = null;
    return revision;
  }

  /** @param {string} query @param {string} market @param {SearchState['status']} status @param {string} [note] */
  function emptyState(query, market, status, note = "") {
    return { query, market, status, assets: [], partial: false, truncated: false, note };
  }

  /** @param {string} query @param {string} market @param {number} token */
  async function request(query, market, token) {
    if (token !== revision) return;
    debounceTimer = null;
    const activeController = new AbortController();
    controller = activeController;
    // An abort alone is insufficient: fetch implementations may ignore its signal.
    timeoutTimer = setTimeout(() => {
      if (token !== revision) return;
      stop();
      onUpdate(emptyState(query, market, "error", "搜索超时，请检查网络后重试。"));
    }, REQUEST_TIMEOUT_MS);
    try {
      const response = await fetcher(`/data/symbols/search?q=${encodeURIComponent(query)}&market=${market}`, {
        signal: activeController.signal,
        headers: { Accept: "application/json" },
      });
      if (token !== revision) return;
      if (!response.ok) {
        throw new Error(response.status === 429 ? "请求较频繁，请稍后重试。" : UNAVAILABLE);
      }
      let payload;
      try { payload = await response.json(); }
      catch { throw new Error(INVALID_RESPONSE); }
      if (token !== revision) return;
      const result = parseResult(payload, market);
      onUpdate({ query, market, status: "success", ...result });
    } catch (error) {
      if (token !== revision) return;
      const message = error instanceof Error && [UNAVAILABLE, INVALID_RESPONSE, "请求较频繁，请稍后重试。"].includes(error.message)
        ? error.message : UNAVAILABLE;
      onUpdate(emptyState(query, market, "error", message));
    } finally {
      if (token === revision) {
        clearTimeout(timeoutTimer);
        timeoutTimer = null;
        controller = null;
      }
    }
  }

  return {
    /** @param {string} query @param {string} [market] */
    search(query, market = "all") {
      const token = stop();
      const term = typeof query === "string" ? query.trim() : "";
      const selectedMarket = ["all", "us", "cn", "crypto"].includes(market) ? market : "all";
      lastMarket = selectedMarket;
      onUpdate(emptyState(term, selectedMarket, term ? "loading" : "idle"));
      if (term && token === revision) {
        debounceTimer = setTimeout(() => { void request(term, selectedMarket, token); }, Math.max(0, delayMs));
      }
    },
    cancel() {
      stop();
      onUpdate(emptyState("", lastMarket, "idle"));
    },
  };
}
