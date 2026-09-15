/** Join real US snapshots with the browser's reference-only search catalog. */
import { REFERENCE_ASSETS } from "../client/market-catalog.js";

export interface WatchlistAsset {
  id: string;
  market: string;
  symbol: string;
  name: string;
  currency: string;
  exchange: string;
  aliases: string[];
  price: number | null;
  change: number | null;
  change_pct: number | null;
  volume: number | null;
  as_of: string | null;
  source: string | null;
  quote_status: "snapshot" | "unavailable";
  spark: Array<number | null>;
}

/** A reference row is searchable and saveable but makes no market reading. */
function withoutQuote(asset: typeof REFERENCE_ASSETS[number]): WatchlistAsset {
  return { ...asset, price: null, change: null, change_pct: null, volume: null,
    as_of: null, source: null, quote_status: "unavailable", spark: [] };
}

/** Only this route interprets its producer's JSON. Other data routes retain
 * their existing byte-for-byte response/cache contract. */
export function withWatchlistCatalog(body: string): string {
  const payload = JSON.parse(body) as Record<string, unknown>;
  if (!payload || payload.ok !== true || !Array.isArray(payload.assets) || !Array.isArray(payload.markets)) {
    throw new Error("invalid watchlist payload");
  }
  const references = new Map(REFERENCE_ASSETS.map((asset) => [asset.id, asset]));
  const assets = new Map(REFERENCE_ASSETS.map((asset) => [asset.id, withoutQuote(asset)]));
  for (const row of payload.assets as WatchlistAsset[]) {
    if (!row || row.market !== "us" || typeof row.symbol !== "string" || row.id !== `us:${row.symbol}`) continue;
    const reference = references.get(row.id);
    assets.set(row.id, {
      ...row,
      name: reference && (!row.name || row.name === row.symbol) ? reference.name : row.name,
      aliases: reference?.aliases ?? row.aliases ?? [],
      exchange: reference?.exchange ?? row.exchange,
    });
  }
  return JSON.stringify({
    ...payload,
    assets: [...assets.values()],
    markets: [
      ...payload.markets,
      { id: "cn", label: "A股", status: "unavailable", source: null, as_of: null,
        note: "参考标的目录；A股行情尚未连接。" },
      { id: "crypto", label: "加密货币", status: "unavailable", source: null, as_of: null,
        note: "参考标的目录；加密货币行情尚未连接。" },
    ],
    note: "美股为本地历史快照，非实时行情；A 股和加密货币报价尚未连接。添加自选时通过搜索服务按需查询标的。",
  });
}
