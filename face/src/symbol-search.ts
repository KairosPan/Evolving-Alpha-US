/** On-demand instrument discovery. Only individual queries are cached, in
 * memory; this service never downloads or persists a market directory.
 * Provider suggestions identify instruments, and deliberately carry no quote.
 */
import type { IncomingMessage, ServerResponse } from "node:http";
import type { RouteRegistrar } from "./static.ts";
import { FORBIDDEN, HttpError } from "./http.ts";

export type SearchMarket = "all" | "us" | "cn" | "crypto";
export interface SearchAsset {
  id: string;
  market: Exclude<SearchMarket, "all">;
  symbol: string;
  name: string;
  currency: string;
  exchange: string;
  aliases: string[];
}
interface ProviderResult { assets: SearchAsset[]; truncated: boolean }
interface ProviderStatus { id: string; status: "ok" | "error"; message?: string }
export interface SearchResult {
  ok: boolean;
  assets: SearchAsset[];
  providers: ProviderStatus[];
  partial: boolean;
  truncated: boolean;
  error?: string;
  note?: string;
}
export const SEARCH_TTL_MS = 60_000;
export const SEARCH_TIMEOUT_MS = 6_000;
export const SEARCH_CACHE_LIMIT = 128;
export const SEARCH_FLIGHT_LIMIT = 32;
export const SEARCH_RESPONSE_LIMIT = 256 * 1024;
const RESULT_LIMIT = 30;
const YAHOO_LIMIT = 20;
export type SearchFetch = (url: URL, options: RequestInit) => Promise<Response>;

/** Normalize only user input. Market selection controls provider filtering,
 * never a host or path. The bounded query is always URL-encoded upstream. */
export function parseSearchRequest(rawUrl: string): { query: string; market: SearchMarket } {
  if (rawUrl.length > 2048 || /%(?![a-f\d]{2})/i.test(rawUrl)) throw new HttpError(400, "invalid search query");
  const url = new URL(rawUrl, "http://localhost");
  if (url.searchParams.getAll("q").length !== 1 || url.searchParams.getAll("market").length > 1) {
    throw new HttpError(400, "invalid search query");
  }
  const raw = url.searchParams.get("q") ?? "";
  if (/[\u0000-\u001f\u007f-\u009f\ufffd]/u.test(raw)) throw new HttpError(400, "invalid search query");
  const query = raw.trim().normalize("NFKC");
  if (!query || [...query].length > 80 || Buffer.byteLength(query) > 240) throw new HttpError(400, "invalid search query");
  const market = url.searchParams.get("market") ?? "all";
  if (!["all", "us", "cn", "crypto"].includes(market)) throw new HttpError(400, "invalid market");
  return { query, market: market as SearchMarket };
}

/** Tencent's smartbox returns a JavaScript string assignment, not executable
 * data. Parse the quoted string as JSON; never evaluate vendor JavaScript. */
export function parseTencentSearch(body: string): ProviderResult {
  const match = /^\s*v_hint\s*=\s*("(?:[^"\\]|\\.)*")\s*;?\s*$/s.exec(body);
  if (!match) throw new Error("invalid provider response");
  const value: unknown = JSON.parse(match[1]!);
  if (typeof value !== "string") throw new Error("invalid provider response");
  // Tencent explicitly uses "N" for a successful query with no suggestions.
  const rows = value && value !== "N" ? value.split("^").filter(Boolean) : [];
  const assets = new Map<string, SearchAsset>();
  for (const row of rows) {
    if (row.split("~").length < 5) throw new Error("invalid provider response");
    const [venue, symbol, name, alias, kind] = row.split("~");
    if (!venue || !["sh", "sz", "bj"].includes(venue) || kind !== "GP-A"
      || !symbol || !/^\d{6}$/.test(symbol) || !name?.trim()) continue;
    const asset: SearchAsset = {
      id: `cn:${symbol}`, market: "cn", symbol, name: name.trim(), currency: "CNY",
      exchange: venue.toUpperCase(), aliases: alias ? [alias] : [],
    };
    assets.set(asset.id, asset);
  }
  return { assets: [...assets.values()], truncated: rows.length >= 10 };
}

const US_EXCHANGES = new Set(["NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS", "PNK", "OQB", "OQX", "OEM"]);
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Yahoo includes foreign listings, indices and non-USD crypto pairs in its
 * suggestions. Only supported US stocks/ETFs and USD crypto pairs become
 * watchlist assets, retaining the application's existing stable ids. */
export function parseYahooSearch(body: string, market: "us" | "crypto" | "all"): ProviderResult {
  const payload: unknown = JSON.parse(body);
  if (!record(payload) || !Array.isArray(payload.quotes)) throw new Error("invalid provider response");
  const assets = new Map<string, SearchAsset>();
  for (const row of payload.quotes) {
    if (!record(row) || typeof row.symbol !== "string") continue;
    const name = typeof row.longname === "string" ? row.longname : row.shortname;
    if (typeof name !== "string" || !name.trim()) continue;
    if (market !== "us" && row.quoteType === "CRYPTOCURRENCY" && /^[A-Z0-9]{1,15}-USD$/.test(row.symbol)) {
      const symbol = row.symbol.replace(/-USD$/, "/USD");
      assets.set(`crypto:${symbol}`, { id: `crypto:${symbol}`, market: "crypto", symbol,
        name: name.trim(), currency: "USD", exchange: "CRYPTO", aliases: [row.symbol, symbol.split("/")[0]!] });
    } else if (market !== "crypto" && ["EQUITY", "ETF"].includes(String(row.quoteType))
      && US_EXCHANGES.has(String(row.exchange)) && /^[A-Z][A-Z0-9.-]{0,14}$/.test(row.symbol)) {
      const symbol = row.symbol;
      assets.set(`us:${symbol}`, { id: `us:${symbol}`, market: "us", symbol,
        name: name.trim(), currency: "USD", exchange: typeof row.exchDisp === "string" ? row.exchDisp : String(row.exchange), aliases: [] });
    }
  }
  return { assets: [...assets.values()], truncated: payload.quotes.length >= YAHOO_LIMIT };
}

/** Read a bounded streaming body, including providers without Content-Length. */
async function readProvider(response: Response, encoding: string): Promise<string> {
  if (!response.ok || !response.body) {
    await response.body?.cancel();
    throw new Error("provider unavailable");
  }
  if (Number(response.headers.get("content-length")) > SEARCH_RESPONSE_LIMIT) {
    await response.body.cancel();
    throw new Error("provider response too large");
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      size += chunk.value.byteLength;
      if (size > SEARCH_RESPONSE_LIMIT) throw new Error("provider response too large");
      chunks.push(chunk.value);
    }
  } catch (error) {
    await reader.cancel().catch(() => undefined);
    throw error;
  } finally { reader.releaseLock(); }
  return new TextDecoder(encoding).decode(Buffer.concat(chunks));
}

/** Test seams replace network/clock/deadline; production always uses these two
 * fixed HTTPS endpoints, without redirects or user-supplied credentials. */
export function createSymbolSearch(options: { fetch?: SearchFetch; now?: () => number; timeoutMs?: number } = {}):
  (query: string, market: SearchMarket) => Promise<SearchResult> {
  const fetcher = options.fetch ?? fetch;
  const now = options.now ?? Date.now;
  const cache = new Map<string, { at: number; result: SearchResult }>();
  const inflight = new Map<string, Promise<SearchResult>>();

  async function upstream(id: string, query: string, market: SearchMarket): Promise<ProviderResult> {
    const url = id === "tencent" ? new URL("https://smartbox.gtimg.cn/s3/")
      : new URL("https://query1.finance.yahoo.com/v1/finance/search");
    // Yahoo searches its dash spelling; the watchlist displays BTC/USD.
    const providerQuery = id === "yahoo" && /^[A-Z0-9]{1,15}\/USD$/i.test(query)
      ? query.toUpperCase().replace("/", "-") : query;
    url.searchParams.set("q", providerQuery);
    if (id === "tencent") url.searchParams.set("t", "all");
    else {
      url.searchParams.set("quotesCount", String(YAHOO_LIMIT));
      url.searchParams.set("newsCount", "0");
      url.searchParams.set("listsCount", "0");
      url.searchParams.set("enableFuzzyQuery", "false");
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const deadline = new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(new Error("provider timeout"));
      }, options.timeoutMs ?? SEARCH_TIMEOUT_MS);
    });
    const request = async (): Promise<ProviderResult> => {
      const response = await fetcher(url, { signal: controller.signal, redirect: "error",
        headers: { accept: "application/json, text/plain, */*", "user-agent": "Mozilla/5.0 Kairos-Symbol-Search" } });
      const body = await readProvider(response, id === "tencent" ? "gb18030" : "utf-8");
      return id === "tencent" ? parseTencentSearch(body) : parseYahooSearch(body, market === "cn" ? "all" : market);
    };
    try { return await Promise.race([request(), deadline]); }
    finally { clearTimeout(timer); controller.abort(); }
  }

  async function run(query: string, market: SearchMarket): Promise<SearchResult> {
    const ids = market === "cn" ? ["tencent"] : market === "all" ? ["tencent", "yahoo"] : ["yahoo"];
    const responses = await Promise.allSettled(ids.map((id) => upstream(id, query, market)));
    const providers: ProviderStatus[] = [];
    const assets = new Map<string, SearchAsset>();
    let truncated = false;
    responses.forEach((response, index) => {
      const id = ids[index]!;
      if (response.status === "rejected") {
        providers.push({ id, status: "error", message: "搜索服务暂时不可用，请稍后重试。" });
      } else {
        providers.push({ id, status: "ok" });
        truncated ||= response.value.truncated;
        for (const asset of response.value.assets) assets.set(asset.id, asset);
      }
    });
    const failed = providers.filter((provider) => provider.status === "error").length;
    return { ok: failed < providers.length, assets: [...assets.values()].slice(0, RESULT_LIMIT), providers,
      partial: failed > 0 && failed < providers.length, truncated: truncated || assets.size > RESULT_LIMIT,
      ...(failed === providers.length ? { error: "搜索服务暂时不可用，请稍后重试。" } : {}),
      note: failed === providers.length ? "搜索服务暂时不可用，请稍后重试。"
        : failed > 0 ? "部分搜索服务暂时不可用，结果可能不完整，请稍后重试。"
          : "在线搜索结果由数据服务提供；搜索结果不含实时行情。" };
  }

  return async (query, market) => {
    const key = JSON.stringify([market, query.toLocaleLowerCase("en-US")]);
    const hit = cache.get(key);
    if (hit && now() - hit.at < SEARCH_TTL_MS) {
      cache.delete(key);
      cache.set(key, hit);
      return hit.result;
    }
    cache.delete(key);
    const pending = inflight.get(key);
    if (pending) return pending;
    if (inflight.size >= SEARCH_FLIGHT_LIMIT) throw new HttpError(429, "搜索请求过多，请稍后重试。");
    const flight = run(query, market).then((result) => {
      // Retry a failed provider on the next query instead of masking its outage.
      if (result.ok && !result.partial) {
        cache.set(key, { at: now(), result });
        if (cache.size > SEARCH_CACHE_LIMIT) cache.delete(cache.keys().next().value!);
      }
      return result;
    });
    inflight.set(key, flight);
    const clear = (): void => { inflight.delete(key); };
    void flight.then(clear, clear);
    return flight;
  };
}

/** Mount behind the same browser trust predicate as the existing data routes.
 * The predicate is injected by data.ts to avoid a circular module dependency. */
export function registerSymbolSearchRoutes(webServer: RouteRegistrar,
  options: { isTrusted: (req: IncomingMessage) => boolean; fetch?: SearchFetch; now?: () => number }): void {
  const search = createSymbolSearch(options);
  const send = (res: ServerResponse, status: number, body: string): void => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
    res.end(body);
  };
  webServer.register({ kind: "exact", path: "/data/symbols/search", handler: async (req, res) => {
    if (!options.isTrusted(req)) return send(res, 403, FORBIDDEN);
    if (req.method !== "GET") return send(res, 405, JSON.stringify({ ok: false, error: "method not allowed" }));
    try {
      const { query, market } = parseSearchRequest(req.url ?? "");
      const result = await search(query, market);
      send(res, result.ok ? 200 : 503, JSON.stringify(result));
    } catch (error) {
      send(res, error instanceof HttpError ? error.status : 503,
        JSON.stringify({ ok: false, error: error instanceof HttpError ? error.message : "搜索服务暂时不可用，请稍后重试。" }));
    }
  } });
}
