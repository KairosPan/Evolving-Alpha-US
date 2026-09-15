import type { ProviderState, QuoteIdentity, QuoteStream, QuoteUpdate, StreamCallbacks } from "./quote-types.ts";

/** Public market-data sockets only. Credentials never leave the Alpaca auth frame.
 * Protocols: https://docs.alpaca.markets/us/docs/streaming-market-data
 * https://docs.cdp.coinbase.com/exchange/websocket-feed/channels */
export type QuoteSocket = Pick<WebSocket, "readyState" | "send" | "close" | "addEventListener" | "removeEventListener">;
type Timer = ReturnType<typeof setTimeout>;
export interface QuoteStreamOptions {
  env?: Record<string, string | undefined>;
  socketFactory?: (url: string) => QuoteSocket;
  now?: () => number;
  setTimeout?: (callback: () => void, delay: number) => Timer;
  clearTimeout?: (timer: Timer) => void;
}
const OPEN = 1;
const ACK_TIMEOUT = 10_000;
const HEALTH_INTERVAL = 30_000;
const IDLE_TIMEOUT = 45_000;
const MAX_RECONNECT = 30_000;
const MAX_ASSETS = 200;
const COINBASE_PACE = 250;
const MAX_MESSAGE_BYTES = 512 * 1024;
// Close-price exclusions documented by Alpaca; average-price codes vary by tape.
// https://alpaca.markets/learn/stock-minute-bars
const EXCLUDED_CONDITIONS = new Set(["4", "7", "9", "C", "G", "H", "I", "M", "N", "P", "Q", "R", "T", "U", "V", "Z"]);
type RecordValue = Record<string, unknown>;
const record = (value: unknown): value is RecordValue => value !== null && typeof value === "object" && !Array.isArray(value);
function number(value: unknown, zero = false): number | undefined {
  if (typeof value !== "number" && (typeof value !== "string" || !/^\d+(?:\.\d+)?$/.test(value))) return;
  const parsed = Number(value);
  return Number.isFinite(parsed) && (zero ? parsed >= 0 : parsed > 0) ? parsed : undefined;
}
/** Preserve provider nanoseconds so late ticks within one millisecond cannot rewind price. */
function timestamp(value: unknown): { text: string; order: bigint } | undefined {
  if (typeof value !== "string") return;
  const match = value.match(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.(\d{1,9}))?(?:Z|[+-]\d{2}:\d{2})$/);
  if (!match) return;
  const millis = Date.parse(value);
  if (!Number.isFinite(millis)) return;
  return { text: value, order: BigInt(millis) * 1_000_000n + BigInt((match[1] ?? "").padEnd(9, "0").slice(3)) };
}
function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}
function validTrade(row: RecordValue): boolean {
  if (!Array.isArray(row.c) || !row.c.every((condition) => typeof condition === "string")) return false;
  return !row.c.some((condition) => EXCLUDED_CONDITIONS.has(condition)
    || (condition === "B" && row.z !== "C") || (condition === "W" && row.z === "C"));
}

export function createQuoteStreams(callbacks: StreamCallbacks, options: QuoteStreamOptions = {}): QuoteStream {
  const env = options.env ?? process.env;
  const makeSocket = options.socketFactory ?? ((url: string) => new WebSocket(url));
  const now = options.now ?? Date.now;
  const schedule = options.setTimeout ?? ((callback, delay) => { const timer = setTimeout(callback, delay); timer.unref?.(); return timer; });
  const cancel = options.clearTimeout ?? clearTimeout;
  const requestedFeed = env.ALPHA_DATA_FEED?.trim() || "iex";
  const validFeed = ["iex", "sip", "delayed_sip"].includes(requestedFeed);
  const feed = validFeed ? requestedFeed : "iex";
  let closed = false;

  function controller(provider: "alpaca" | "coinbase") {
    const isAlpaca = provider === "alpaca";
    const source = isAlpaca ? "Alpaca" : "Coinbase";
    const providerFeed = isAlpaca ? feed : "exchange";
    const url = isAlpaca ? `wss://stream.data.alpaca.markets/v2/${feed}` : "wss://ws-feed.exchange.coinbase.com";
    let wanted = new Map<string, QuoteIdentity>();
    let subscribed = new Set<string>();
    let rejected = new Set<string>();
    let limitedInput = false;
    let socket: QuoteSocket | undefined;
    let disposeListeners: (() => void) | undefined;
    let generation = 0;
    let authenticated = false;
    let fatal = false;
    let attempts = 0;
    let started = 0;
    let lastMessage = 0;
    let reconnectTimer: Timer | undefined;
    let watchdog: Timer | undefined;
    let healthTimer: Timer | undefined;
    let paceTimer: Timer | undefined;
    let pending: { action: "subscribe" | "unsubscribe"; symbols: string[]; probe?: boolean } | undefined;
    const priceTimes = new Map<string, bigint>();
    const volumeTimes = new Map<string, bigint>();
    const sequences = new Map<string, number>();
    let lastStatus = "";

    function status(state: ProviderState["status"], message: string) {
      const signature = `${state}:${message}`;
      if (closed || signature === lastStatus) return;
      lastStatus = signature;
      callbacks.onStatus({ id: provider, market: isAlpaca ? "us" : "crypto", status: state,
        source, feed: providerFeed, transport: "stream", message });
    }
    function connectedStatus() {
      if (limitedInput || rejected.size) {
        status("limited", isAlpaca
          ? "部分美股未订阅推送；IEX 最多同时推送 30 个标的，其余保留定时行情。"
          : "部分交易对不受 Coinbase 支持或订阅被拒绝；其他交易对继续更新。");
      } else {
        status("connected", isAlpaca
          ? (feed === "iex" ? "IEX 实时推送，仅覆盖该交易所成交。" : feed === "delayed_sip" ? "SIP 行情延迟 15 分钟。" : "SIP 实时行情推送已连接。")
          : "Coinbase 实时行情推送已连接，涨跌幅以过去 24 小时为基准。");
      }
    }
    function clearTimer(kind: "watchdog" | "health" | "pace" | "reconnect") {
      const timer = kind === "watchdog" ? watchdog : kind === "health" ? healthTimer : kind === "pace" ? paceTimer : reconnectTimer;
      if (timer !== undefined) cancel(timer);
      if (kind === "watchdog") watchdog = undefined;
      else if (kind === "health") healthTimer = undefined;
      else if (kind === "pace") paceTimer = undefined;
      else reconnectTimer = undefined;
    }
    function detach() {
      generation++;
      for (const timer of ["watchdog", "health", "pace"] as const) clearTimer(timer);
      disposeListeners?.(); disposeListeners = undefined;
      const previous = socket; socket = undefined;
      authenticated = false; subscribed.clear(); pending = undefined;
      try { previous?.close(); } catch { /* A failed handshake can already be closed. */ }
    }
    function stop() { clearTimer("reconnect"); detach(); }
    function fail(message: string, permanent = false) {
      if (closed || !wanted.size) return;
      status("error", message);
      fatal = permanent;
      detach();
      if (permanent || reconnectTimer !== undefined) return;
      const delay = Math.min(MAX_RECONNECT, 1000 * 2 ** Math.min(attempts++, 5));
      reconnectTimer = schedule(() => { reconnectTimer = undefined; connect(); }, delay);
    }
    function deadline() {
      clearTimer("watchdog");
      watchdog = schedule(() => { watchdog = undefined; fail(`${source} 行情连接响应超时，正在重连。`); }, ACK_TIMEOUT);
    }
    function send(value: unknown): boolean {
      if (!socket || socket.readyState !== OPEN) return false;
      try { socket.send(JSON.stringify(value)); return true; }
      catch { fail(`${source} 行情发送失败，正在重连。`); return false; }
    }
    function sendCommand(command: NonNullable<typeof pending>) {
      pending = command;
      const sent = send(isAlpaca
        ? { action: command.action, trades: command.symbols, dailyBars: command.symbols }
        : { type: command.action, product_ids: command.symbols, channels: ["ticker", "heartbeat"] });
      if (sent) deadline();
    }
    function sync() {
      if (!authenticated || pending || paceTimer !== undefined || !socket || socket.readyState !== OPEN) return;
      const remove = [...subscribed].filter((symbol) => !wanted.has(symbol));
      if (remove.length) { sendCommand({ action: "unsubscribe", symbols: remove }); return; }
      const add = [...wanted.keys()].filter((symbol) => !subscribed.has(symbol) && !rejected.has(symbol));
      // Separate Coinbase products so one invalid product cannot reject valid ones.
      if (add.length) sendCommand({ action: "subscribe", symbols: isAlpaca ? add : add.slice(0, 1) });
    }
    function continueSync() {
      if (isAlpaca) sync();
      else if (paceTimer === undefined) paceTimer = schedule(() => { paceTimer = undefined; sync(); }, COINBASE_PACE);
    }
    function health() {
      clearTimer("health");
      if (!socket || !wanted.size) return;
      healthTimer = schedule(() => {
        healthTimer = undefined;
        if (!socket || closed) return;
        if (now() - lastMessage >= IDLE_TIMEOUT && !pending) {
          if (isAlpaca && authenticated && subscribed.size) {
            // Native WebSocket responds to server ping frames internally. Reaffirm
            // subscriptions to get an application ack even while markets are closed.
            sendCommand({ action: "subscribe", symbols: [...subscribed], probe: true });
          } else if (subscribed.size) {
            fail("Coinbase 行情心跳中断，正在重连。"); return;
          }
        }
        health();
      }, HEALTH_INTERVAL);
    }
    function alive() {
      lastMessage = now();
      if (lastMessage - started >= HEALTH_INTERVAL) attempts = 0;
    }
    function patch(asset: QuoteIdentity, values: Partial<QuoteUpdate>) {
      callbacks.onQuote({ id: asset.id, source, feed: providerFeed,
        basis: isAlpaca ? "previous_close" : "24h", ...values });
    }
    function alpaca(row: RecordValue) {
      if (row.T === "success") {
        alive();
        if (row.msg === "authenticated" && !authenticated) {
          authenticated = true; clearTimer("watchdog"); sync();
        }
        return;
      }
      if (row.T === "error") {
        const code = row.code;
        if (code === 405 && pending) {
          for (const symbol of pending.symbols) rejected.add(symbol);
          pending = undefined; clearTimer("watchdog"); connectedStatus(); continueSync();
        } else if (code === 402 || code === 409) fail("Alpaca 密钥无效或当前账号没有该行情源权限。", true);
        else if (code === 406) fail("Alpaca 行情连接数已达上限，正在等待可用连接。");
        else fail("Alpaca 行情服务返回错误，正在重连。");
        return;
      }
      if (!authenticated) return;
      if (row.T === "subscription") {
        alive();
        const trades = new Set(strings(row.trades));
        const bars = new Set(strings(row.dailyBars));
        subscribed = new Set([...trades].filter((symbol) => bars.has(symbol)));
        // A successful acknowledgement must actually include the pending symbols.
        if (pending && !pending.probe && pending.action === "subscribe") {
          for (const symbol of pending.symbols) if (!subscribed.has(symbol)) rejected.add(symbol);
        }
        pending = undefined; clearTimer("watchdog"); connectedStatus(); continueSync();
        return;
      }
      const symbol = typeof row.S === "string" ? row.S : "";
      const asset = wanted.get(symbol);
      if (!asset) return;
      if (row.T === "c" || row.T === "x") {
        alive(); patch(asset, { message: "成交发生更正或撤销，等待行情快照校准。" }); return;
      }
      const time = timestamp(row.t);
      if (!time) return;
      if (row.T === "t") {
        const price = number(row.p);
        if (price === undefined || !validTrade(row) || time.order < (priceTimes.get(symbol) ?? -1n)) return;
        alive(); priceTimes.set(symbol, time.order);
        patch(asset, { price, as_of: time.text, message: "" });
      } else if (row.T === "d") {
        const volume = number(row.v, true);
        if (volume === undefined || time.order < (volumeTimes.get(symbol) ?? -1n)) return;
        alive(); volumeTimes.set(symbol, time.order);
        // The daily bar timestamp identifies the day's bucket, not the latest trade.
        patch(asset, { volume, volume_as_of: time.text });
      }
    }
    function coinbase(row: RecordValue) {
      if (row.type === "error") {
        if (pending?.action === "subscribe") {
          alive();
          for (const symbol of pending.symbols) rejected.add(symbol);
          pending = undefined; clearTimer("watchdog"); connectedStatus(); continueSync();
        } else fail("Coinbase 行情服务返回错误，正在重连。");
        return;
      }
      if (row.type === "subscriptions") {
        if (!Array.isArray(row.channels)) return;
        alive();
        const channels = row.channels.filter(record);
        const tickers = new Set(channels.filter((channel) => channel.name === "ticker").flatMap((channel) => strings(channel.product_ids)));
        const heartbeats = new Set(channels.filter((channel) => channel.name === "heartbeat").flatMap((channel) => strings(channel.product_ids)));
        subscribed = new Set([...tickers].filter((symbol) => heartbeats.has(symbol)));
        if (pending?.action === "subscribe") {
          for (const symbol of pending.symbols) if (!subscribed.has(symbol)) rejected.add(symbol);
        }
        pending = undefined; clearTimer("watchdog"); connectedStatus(); continueSync();
        return;
      }
      const product = typeof row.product_id === "string" ? row.product_id : "";
      const asset = wanted.get(product);
      if (!asset) return;
      if (row.type === "heartbeat") { alive(); return; }
      if (row.type !== "ticker") return;
      const price = number(row.price);
      const time = timestamp(row.time);
      const sequence = typeof row.sequence === "number" && Number.isSafeInteger(row.sequence) && row.sequence >= 0 ? row.sequence : undefined;
      if (price === undefined || !time || time.order < (priceTimes.get(product) ?? -1n)
        || (sequence !== undefined && sequence <= (sequences.get(product) ?? -1))) return;
      alive(); priceTimes.set(product, time.order);
      if (sequence !== undefined) sequences.set(product, sequence);
      const prevClose = number(row.open_24h);
      const volume = number(row.volume_24h, true);
      patch(asset, { price, as_of: time.text, market_status: "open", message: "",
        // Missing fields stay missing; Number(null)/Number("") must never manufacture zero.
        ...(prevClose === undefined ? {} : { prev_close: prevClose }),
        ...(volume === undefined ? {} : { volume, volume_as_of: time.text }) });
    }
    function connect() {
      if (closed || fatal || !wanted.size || socket || reconnectTimer !== undefined) return;
      if (isAlpaca && (!env.APCA_API_KEY_ID?.trim() || !env.APCA_API_SECRET_KEY?.trim())) {
        status("unconfigured", "尚未配置 Alpaca 行情密钥。"); return;
      }
      if (isAlpaca && !validFeed) { status("error", "ALPHA_DATA_FEED 仅支持 iex、sip 或 delayed_sip。"); fatal = true; return; }
      status("connecting", `正在连接 ${source} 行情推送…`);
      const currentGeneration = ++generation;
      let current: QuoteSocket;
      try { current = makeSocket(url); socket = current; }
      catch { fail(`${source} 行情连接失败，正在重连。`); return; }
      started = now(); lastMessage = started; rejected.clear();
      const currentEvent = () => !closed && generation === currentGeneration && socket === current;
      const onOpen = () => {
        if (!currentEvent()) return;
        if (isAlpaca) {
          if (send({ action: "auth", key: env.APCA_API_KEY_ID, secret: env.APCA_API_SECRET_KEY })) deadline();
        } else { authenticated = true; clearTimer("watchdog"); sync(); }
        health();
      };
      const onMessage = (event: Event) => {
        if (!currentEvent()) return;
        const data: unknown = (event as MessageEvent).data;
        if (typeof data !== "string" || data.length > MAX_MESSAGE_BYTES) return;
        let payload: unknown;
        try { payload = JSON.parse(data); } catch { return; }
        const rows = isAlpaca ? (Array.isArray(payload) ? payload.slice(0, 2000) : []) : [payload];
        for (const row of rows) {
          if (!currentEvent()) break;
          if (record(row)) (isAlpaca ? alpaca : coinbase)(row);
        }
      };
      const onClose = () => { if (currentEvent()) fail(`${source} 行情连接中断，正在重连。`); };
      const handlers = { open: onOpen, message: onMessage, close: onClose, error: onClose };
      for (const [type, handler] of Object.entries(handlers)) current.addEventListener(type, handler);
      disposeListeners = () => { for (const [type, handler] of Object.entries(handlers)) current.removeEventListener(type, handler); };
      deadline();
    }
    return {
      setAssets(assets: QuoteIdentity[]) {
        const eligible = assets.filter((asset) => isAlpaca
          ? asset.market === "us" && /^[A-Z][A-Z0-9.-]{0,14}$/.test(asset.symbol) && asset.id === `us:${asset.symbol}`
          : asset.market === "crypto" && /^[A-Z0-9]{1,15}\/USD$/.test(asset.symbol) && asset.id === `crypto:${asset.symbol}`);
        eligible.sort((a, b) => a.symbol.localeCompare(b.symbol, "en"));
        const all = new Map(eligible.map((asset) => [isAlpaca ? asset.symbol : asset.symbol.replace("/", "-"), asset]));
        const limit = isAlpaca && feed === "iex" ? 30 : MAX_ASSETS;
        limitedInput = all.size > limit || (!isAlpaca && assets.some((asset) => asset.market === "crypto" && !eligible.includes(asset)));
        wanted = new Map([...all].slice(0, limit));
        for (const map of [priceTimes, volumeTimes, sequences]) for (const key of map.keys()) if (!wanted.has(key)) map.delete(key);
        for (const key of rejected) if (!wanted.has(key)) rejected.delete(key);
        if (!wanted.size) {
          stop(); rejected.clear(); attempts = 0; fatal = false;
          if (limitedInput) status("limited", "Coinbase 行情目前仅支持 USD 交易对。");
          return;
        }
        if (authenticated) { sync(); if (!pending) connectedStatus(); }
        else connect();
      },
      close() { wanted.clear(); stop(); priceTimes.clear(); volumeTimes.clear(); sequences.clear(); rejected.clear(); },
    };
  }
  const alpaca = controller("alpaca");
  const coinbase = controller("coinbase");
  return {
    setAssets(assets) { if (!closed) { alpaca.setAssets(assets); coinbase.setAssets(assets); } },
    close() { if (!closed) { closed = true; alpaca.close(); coinbase.close(); } },
  };
}
