/** On-demand quote snapshots; no instrument directory or on-disk market cache.
 * Official schemas: docs.alpaca.markets/us/reference/stocksnapshotsingle,
 * docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker,
 * quantapi.10jqka.com.cn/gwstatic/static/ds_web/quantapi-web/help-center/manual.html
 */
import type { MarketStatus, ProviderState, QuoteIdentity, QuoteUpdate, SnapshotResult, SnapshotSource } from "./quote-types.ts";

export type QuoteFetch = (url: URL, options: RequestInit) => Promise<Response>;
export interface QuoteSnapshotOptions {
  fetcher?: QuoteFetch;
  env?: NodeJS.ProcessEnv;
  now?: () => number;
  timeoutMs?: number;
  /** Test override. Production starts at most eight Coinbase requests/second. */
  coinbaseSpacingMs?: number;
}
export const QUOTE_RESPONSE_LIMIT = 1024 * 1024;
export const QUOTE_TIMEOUT_MS = 7_000;
const FEEDS = new Set(["iex", "sip", "delayed_sip"]);
const IFIND_ROOT = "https://quantapi.51ifind.com/api/v1/";
const US_DATE = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" });
class ProviderError extends Error {
  constructor(readonly kind: "http" | "payload" | "timeout" | "abort", readonly status = 0) { super(kind); }
}
const object = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === "object" && !Array.isArray(value);
function number(value: unknown, positive = false): number | null {
  if (typeof value !== "number" && (typeof value !== "string" || !value.trim())) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && (positive ? parsed > 0 : parsed >= 0) ? parsed : null;
}
function timestamp(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/i.test(value)) return null;
  const time = Date.parse(value);
  return Number.isFinite(time) ? value : null;
}
function field(row: Record<string, unknown>, key: string): unknown {
  const value = row[key];
  return Array.isArray(value) ? value[0] : value;
}
/** iFinD mainland timestamps are Beijing local time. A date alone is never
 * promoted to a live timestamp, and receipt time never fills missing dates. */
function ifindTimestamp(row: Record<string, unknown>, table: Record<string, unknown>): string | null {
  const day = String(field(table, "tradeDate") ?? "").replace(/-/g, "");
  let time = String(field(table, "tradeTime") ?? "");
  if (/^\d{1,6}$/.test(time)) time = time.padStart(6, "0").replace(/(\d{2})(\d{2})(\d{2})/, "$1:$2:$3");
  let local = /^\d{8}$/.test(day) && /^\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(time)
    ? `${day.slice(0, 4)}-${day.slice(4, 6)}-${day.slice(6, 8)}T${time}` : null;
  if (!local) {
    const supplied = field(row, "time") ?? field(table, "time");
    const absolute = timestamp(supplied);
    if (absolute) return absolute;
    if (typeof supplied === "string" && /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(supplied)) local = supplied.replace(" ", "T");
  }
  return local ? timestamp(`${local}+08:00`) : null;
}
function blank(asset: QuoteIdentity, source: string, feed: string, message: string): QuoteUpdate {
  return { id: asset.id, source, feed, basis: asset.market === "crypto" ? "24h" : "previous_close", message };
}
function state(id: ProviderState["id"], status: ProviderState["status"], feed: string, message: string): ProviderState {
  return { id, market: id === "alpaca" ? "us" : id === "ifind" ? "cn" : "crypto", status,
    source: id === "alpaca" ? "Alpaca" : id === "ifind" ? "iFinD" : "Coinbase", feed, transport: "poll", message };
}
function failureMessage(provider: string, error: unknown): string {
  if (error instanceof ProviderError) {
    if (error.status === 401 || error.status === 403) return `${provider} 凭据或行情权限不可用`;
    if (error.status === 429) return `${provider} 行情请求达到限额，稍后重试`;
    if (error.kind === "timeout") return `${provider} 行情请求超时，稍后重试`;
  }
  // Never echo a vendor response, URL, thrown diagnostic, or credential.
  return `${provider} 行情暂不可用，稍后重试`;
}

export function createQuoteSnapshots(options: QuoteSnapshotOptions = {}): SnapshotSource {
  const fetcher = options.fetcher ?? ((url, init) => fetch(url, init));
  const env = options.env ?? process.env;
  const now = options.now ?? Date.now;
  const timeoutMs = options.timeoutMs ?? QUOTE_TIMEOUT_MS;
  const spacing = options.coinbaseSpacingMs ?? 125;
  let nextCoinbaseRequest = 0;
  let token: { value: string; until: number } | null = null;
  let tokenFlight: Promise<string> | null = null;

  async function request(url: URL, init: RequestInit, outer?: AbortSignal): Promise<unknown> {
    if (outer?.aborted) throw new ProviderError("abort");
    const controller = new AbortController();
    let rejectAbort!: (reason: unknown) => void;
    const aborted = new Promise<never>((_, reject) => { rejectAbort = reject; });
    const abort = (error: ProviderError) => { controller.abort(); rejectAbort(error); };
    const onAbort = () => abort(new ProviderError("abort"));
    outer?.addEventListener("abort", onAbort, { once: true });
    const timer = setTimeout(() => abort(new ProviderError("timeout")), timeoutMs);
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    const work = (async () => {
      const response = await fetcher(url, { ...init, redirect: "error", signal: controller.signal });
      if (controller.signal.aborted) { void response.body?.cancel(); throw new ProviderError("abort"); }
      if (!response.ok) { void response.body?.cancel(); throw new ProviderError("http", response.status); }
      if (!response.body || Number(response.headers.get("content-length")) > QUOTE_RESPONSE_LIMIT) {
        void response.body?.cancel(); throw new ProviderError("payload");
      }
      reader = response.body.getReader();
      const chunks: Uint8Array[] = [];
      let length = 0;
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        length += part.value.byteLength;
        if (length > QUOTE_RESPONSE_LIMIT) throw new ProviderError("payload");
        chunks.push(part.value);
      }
      try { return JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown; }
      catch { throw new ProviderError("payload"); }
    })();
    try { return await Promise.race([work, aborted]); }
    finally {
      clearTimeout(timer);
      outer?.removeEventListener("abort", onAbort);
      controller.abort();
      void reader?.cancel().catch(() => {});
    }
  }

  function unavailable(assets: QuoteIdentity[], provider: ProviderState): SnapshotResult {
    return { updates: assets.map((asset) => blank(asset, provider.source, provider.feed, provider.message)), providers: [provider] };
  }

  async function alpaca(assets: QuoteIdentity[], signal?: AbortSignal): Promise<SnapshotResult> {
    const feed = env.ALPHA_DATA_FEED?.trim().toLowerCase() || "iex";
    if (!FEEDS.has(feed)) return unavailable(assets, state("alpaca", "unconfigured", "", "美股行情源配置无效，请选择 IEX、SIP 或延迟 SIP"));
    const key = env.APCA_API_KEY_ID?.trim(), secret = env.APCA_API_SECRET_KEY?.trim();
    if (!key || !secret) return unavailable(assets, state("alpaca", "unconfigured", feed, "美股行情待配置 Alpaca API 凭据"));
    const headers = { "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret, Accept: "application/json" };
    const url = new URL("https://data.alpaca.markets/v2/stocks/snapshots");
    url.searchParams.set("symbols", assets.map((asset) => asset.symbol).join(","));
    url.searchParams.set("feed", feed);
    const accountHost = (env.APCA_API_BASE_URL || "https://paper-api.alpaca.markets").replace(/\/$/, "");
    const clock = ["https://paper-api.alpaca.markets", "https://api.alpaca.markets"].includes(accountHost)
      ? request(new URL(`${accountHost}/v2/clock`), { headers }, signal).then((value): MarketStatus =>
        object(value) && typeof value.is_open === "boolean" && timestamp(value.timestamp)
          && Math.abs(now() - Date.parse(String(value.timestamp))) < 120_000 ? value.is_open ? "open" : "closed" : "unknown").catch((): MarketStatus => "unknown")
      : Promise.resolve<MarketStatus>("unknown");
    try {
      const [payload, marketStatus] = await Promise.all([request(url, { headers }, signal), clock]);
      if (!object(payload)) throw new ProviderError("payload");
      const updates = assets.map((asset): QuoteUpdate => {
        const row = payload[asset.symbol];
        if (!object(row)) return blank(asset, "Alpaca", feed, "该标的暂无 Alpaca 行情");
        const trade = object(row.latestTrade) ? row.latestTrade : {};
        const daily = object(row.dailyBar) ? row.dailyBar : {};
        const previous = object(row.prevDailyBar) ? row.prevDailyBar : {};
        const asOf = timestamp(trade.t), dailyTime = timestamp(daily.t);
        // Before a new daily bar exists, its close is the previous session's
        // close. Once today's bar exists, use prevDailyBar instead.
        const useDailyClose = asOf && dailyTime && US_DATE.format(new Date(dailyTime)) < US_DATE.format(new Date(asOf));
        const price = number(trade.p, true);
        return { id: asset.id, source: "Alpaca", feed, basis: "previous_close", price,
          prev_close: number(useDailyClose ? daily.c : previous.c, true), volume: useDailyClose ? null : number(daily.v),
          as_of: asOf, volume_as_of: useDailyClose ? null : dailyTime, market_status: marketStatus,
          message: price === null ? "该标的暂无成交价" : !asOf ? "行情时间缺失" : "" };
      });
      const missing = updates.some((update) => !update.price || !update.as_of);
      const note = feed === "iex" ? "IEX 单交易所行情" : feed === "delayed_sip" ? "SIP 行情延迟 15 分钟" : "SIP 综合行情";
      return { updates, providers: [state("alpaca", missing ? "limited" : "connected", feed, missing ? `${note}；部分标的暂无行情` : note)] };
    } catch (error) { return unavailable(assets, state("alpaca", "error", feed, failureMessage("Alpaca", error))); }
  }

  async function accessToken(signal?: AbortSignal): Promise<string> {
    if (env.IFIND_ACCESS_TOKEN?.trim()) return env.IFIND_ACCESS_TOKEN.trim();
    if (token && token.until > now()) return token.value;
    if (tokenFlight) return tokenFlight;
    tokenFlight = request(new URL(`${IFIND_ROOT}get_access_token`), { method: "POST", headers: {
      "Content-Type": "application/json", refresh_token: env.IFIND_REFRESH_TOKEN!.trim(),
    } }, signal).then((payload) => {
      if (!object(payload) || payload.errorcode !== 0 || !object(payload.data) || typeof payload.data.access_token !== "string" || !payload.data.access_token.trim()) throw new ProviderError("payload");
      const value = payload.data.access_token.trim();
      // Fetch the currently valid token hourly; never rotate/invalidate tokens.
      token = { value, until: now() + 3_600_000 };
      return value;
    }).finally(() => { tokenFlight = null; });
    return tokenFlight;
  }

  async function ifind(assets: QuoteIdentity[], signal?: AbortSignal): Promise<SnapshotResult> {
    if (!env.IFIND_ACCESS_TOKEN?.trim() && !env.IFIND_REFRESH_TOKEN?.trim()) return unavailable(assets,
      state("ifind", "unconfigured", "realtime", "A 股实时行情待开通 iFinD 账号并配置接口凭据"));
    const codes = new Map(assets.map((asset) => [asset.id, /^[6]\d{5}$/.test(asset.symbol) ? `${asset.symbol}.SH`
      : /^[03]\d{5}$/.test(asset.symbol) ? `${asset.symbol}.SZ` : /^[489]\d{5}$/.test(asset.symbol) ? `${asset.symbol}.BJ` : null]));
    const supported = [...codes.values()].filter((value): value is string => value !== null);
    if (!supported.length) return unavailable(assets, state("ifind", "limited", "realtime", "iFinD 暂不支持这些证券代码"));
    try {
      const access = await accessToken(signal);
      const payload = await request(new URL(`${IFIND_ROOT}real_time_quotation`), { method: "POST",
        headers: { "Content-Type": "application/json", access_token: access, ifindlang: "cn" },
        body: JSON.stringify({ codes: supported.join(","), indicators: "latest,preClose,tradeDate,tradeTime" }),
      }, signal);
      if (!object(payload) || payload.errorcode !== 0 || !Array.isArray(payload.tables)) {
        token = null;
        throw new ProviderError("payload");
      }
      const rows = new Map<string, Record<string, unknown>>();
      for (const row of payload.tables) if (object(row) && typeof row.thscode === "string") rows.set(row.thscode.toUpperCase(), row);
      const updates = assets.map((asset): QuoteUpdate => {
        const code = codes.get(asset.id), row = code ? rows.get(code) : null;
        if (!row) return blank(asset, "iFinD", "realtime", code ? "该标的暂无 iFinD 行情" : "iFinD 暂不支持该证券代码");
        const table = object(row.table) ? row.table : row;
        const asOf = ifindTimestamp(row, table), price = number(field(table, "latest"), true);
        return { id: asset.id, source: "iFinD", feed: "realtime", basis: "previous_close", price,
          prev_close: number(field(table, "preClose"), true),
          // Public iFinD docs do not establish the volume unit. Enable only
          // after credentialed validation confirms shares versus lots.
          volume: null, volume_as_of: null, as_of: asOf, market_status: "unknown",
          message: price === null ? "该标的暂无成交价" : !asOf ? "行情时间缺失" : "" };
      });
      const missing = updates.some((update) => !update.price || !update.as_of);
      return { updates, providers: [state("ifind", missing ? "limited" : "connected", "realtime", missing ? "部分 A 股标的暂无完整行情" : "iFinD 实时行情")] };
    } catch (error) { return unavailable(assets, state("ifind", "error", "realtime", failureMessage("iFinD", error))); }
  }

  async function coinbaseRequest(url: URL, signal?: AbortSignal): Promise<unknown> {
    if (signal?.aborted) throw new ProviderError("abort");
    // Reservations serialize request starts across overlapping loads, too.
    const wait = Math.max(0, nextCoinbaseRequest - Date.now());
    nextCoinbaseRequest = Math.max(Date.now(), nextCoinbaseRequest) + spacing;
    if (wait) await new Promise<void>((resolve, reject) => {
      if (signal?.aborted) { reject(new ProviderError("abort")); return; }
      const timer = setTimeout(() => { signal?.removeEventListener("abort", abort); resolve(); }, wait);
      const abort = () => { clearTimeout(timer); reject(new ProviderError("abort")); };
      signal?.addEventListener("abort", abort, { once: true });
    });
    return request(url, { headers: { Accept: "application/json" } }, signal);
  }

  async function coinbase(assets: QuoteIdentity[], signal?: AbortSignal): Promise<SnapshotResult> {
    const updates: QuoteUpdate[] = new Array(assets.length);
    let cursor = 0;
    let endpointSuccess = false;
    async function worker() {
      while (cursor < assets.length) {
        const index = cursor++, asset = assets[index]!;
        if (signal?.aborted) { updates[index] = blank(asset, "Coinbase", "exchange", "行情请求已取消"); continue; }
        if (!/^[A-Z0-9]{1,15}\/USD$/.test(asset.symbol)) { updates[index] = blank(asset, "Coinbase", "exchange", "Coinbase 暂不支持该交易对"); continue; }
        const product = asset.symbol.replace("/", "-");
        const base = `https://api.exchange.coinbase.com/products/${product}`;
        try {
          const ticker = await coinbaseRequest(new URL(`${base}/ticker`), signal);
          if (!object(ticker)) throw new ProviderError("payload");
          const price = number(ticker.price, true), asOf = timestamp(ticker.time);
          if (price === null || !asOf) throw new ProviderError("payload");
          endpointSuccess = true;
          let prevClose: number | null = null;
          let message = "";
          try {
            const stats = await coinbaseRequest(new URL(`${base}/stats`), signal);
            if (object(stats)) prevClose = number(stats.open, true);
            if (prevClose === null) message = "24 小时涨跌幅暂不可用";
          } catch { message = "24 小时涨跌幅暂不可用"; }
          updates[index] = { id: asset.id, source: "Coinbase", feed: "exchange", basis: "24h", price,
            prev_close: prevClose, volume: number(ticker.volume), as_of: asOf,
            // REST ticker volume is a rolling 24h snapshot without its own event time.
            volume_as_of: null, market_status: "open", message };
        } catch (error) {
          updates[index] = blank(asset, "Coinbase", "exchange", error instanceof ProviderError && error.status === 404
            ? "Coinbase 暂不支持该交易对" : failureMessage("Coinbase", error));
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(3, assets.length) }, worker));
    const incomplete = updates.some((update) => !update.price || !update.as_of || update.message);
    return { updates, providers: [state("coinbase", incomplete ? endpointSuccess ? "limited" : "error" : "connected", "exchange",
      incomplete ? "部分 Coinbase 行情暂不可用或交易对未支持" : "Coinbase 交易所行情，涨跌幅按 24 小时计算")] };
  }

  return { async load(assets, signal) {
    const groups: Promise<SnapshotResult>[] = [];
    const unique = [...new Map(assets.map((asset) => [asset.id, asset])).values()];
    for (const [market, loader] of [["us", alpaca], ["cn", ifind], ["crypto", coinbase]] as const) {
      const requested = unique.filter((asset) => asset.market === market);
      if (requested.length) groups.push(loader(requested, signal));
    }
    const results = await Promise.all(groups);
    return { updates: results.flatMap((result) => result.updates), providers: results.flatMap((result) => result.providers) };
  } };
}
