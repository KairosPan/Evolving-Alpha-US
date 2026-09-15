/** A small search directory, never a source of prices or a full-market listing.
 * Shared by the browser fallback and the local watchlist data route.
 * BSE's current BTR code is verified by the exchange's 2026-02-12 disclosure:
 * https://www.bse.cn/disclosure/2026/2026-02-12/85e9dc6747ac41e697271a467b59df29.pdf
 */

/** @typedef {{id: string, market: string, symbol: string, name: string, currency: string, exchange: string, aliases: string[]}} ReferenceAsset */

/** @type {ReferenceAsset[]} */
export const REFERENCE_ASSETS = [
  { id: 'us:AAPL', market: 'us', symbol: 'AAPL', name: 'Apple', currency: 'USD', exchange: 'NASDAQ', aliases: ['苹果', 'apple'] },
  { id: 'us:MSFT', market: 'us', symbol: 'MSFT', name: 'Microsoft', currency: 'USD', exchange: 'NASDAQ', aliases: ['微软', 'microsoft'] },
  { id: 'us:NVDA', market: 'us', symbol: 'NVDA', name: 'NVIDIA', currency: 'USD', exchange: 'NASDAQ', aliases: ['英伟达', 'nvidia'] },
  { id: 'us:GOOGL', market: 'us', symbol: 'GOOGL', name: 'Alphabet', currency: 'USD', exchange: 'NASDAQ', aliases: ['谷歌', 'google', 'alphabet'] },
  { id: 'us:AMZN', market: 'us', symbol: 'AMZN', name: 'Amazon', currency: 'USD', exchange: 'NASDAQ', aliases: ['亚马逊', 'amazon'] },
  { id: 'us:META', market: 'us', symbol: 'META', name: 'Meta Platforms', currency: 'USD', exchange: 'NASDAQ', aliases: ['脸书', 'facebook', 'meta'] },
  { id: 'us:TSLA', market: 'us', symbol: 'TSLA', name: 'Tesla', currency: 'USD', exchange: 'NASDAQ', aliases: ['特斯拉', 'tesla'] },
  { id: 'us:AVGO', market: 'us', symbol: 'AVGO', name: 'Broadcom', currency: 'USD', exchange: 'NASDAQ', aliases: ['博通', 'broadcom'] },
  { id: 'us:AMD', market: 'us', symbol: 'AMD', name: 'Advanced Micro Devices', currency: 'USD', exchange: 'NASDAQ', aliases: ['超威半导体', 'amd'] },
  { id: 'us:PLTR', market: 'us', symbol: 'PLTR', name: 'Palantir', currency: 'USD', exchange: 'NASDAQ', aliases: ['帕兰提尔', 'palantir'] },
  { id: 'us:SPY', market: 'us', symbol: 'SPY', name: 'SPDR S&P 500 ETF', currency: 'USD', exchange: 'NYSE ARCA', aliases: ['标普500', '标普', 'sp500', 's&p 500'] },
  { id: 'us:QQQ', market: 'us', symbol: 'QQQ', name: 'Invesco QQQ', currency: 'USD', exchange: 'NASDAQ', aliases: ['纳指', '纳斯达克100', 'nasdaq100'] },
  { id: 'cn:600519', market: 'cn', symbol: '600519', name: '贵州茅台', currency: 'CNY', exchange: 'SH', aliases: ['茅台', 'maotai', 'moutai', 'gzmt'] },
  { id: 'cn:600036', market: 'cn', symbol: '600036', name: '招商银行', currency: 'CNY', exchange: 'SH', aliases: ['招行', 'cmb', 'zsyh'] },
  { id: 'cn:601318', market: 'cn', symbol: '601318', name: '中国平安', currency: 'CNY', exchange: 'SH', aliases: ['平安', 'pingan', 'zgpa'] },
  { id: 'cn:600900', market: 'cn', symbol: '600900', name: '长江电力', currency: 'CNY', exchange: 'SH', aliases: ['长电', 'cydl', 'cjdl', 'yangtze power'] },
  { id: 'cn:601899', market: 'cn', symbol: '601899', name: '紫金矿业', currency: 'CNY', exchange: 'SH', aliases: ['紫金', 'zijin', 'zjky'] },
  { id: 'cn:688981', market: 'cn', symbol: '688981', name: '中芯国际', currency: 'CNY', exchange: 'SH', aliases: ['中芯', 'smic', 'zxgj'] },
  { id: 'cn:688256', market: 'cn', symbol: '688256', name: '寒武纪', currency: 'CNY', exchange: 'SH', aliases: ['cambricon', 'hwj'] },
  { id: 'cn:000001', market: 'cn', symbol: '000001', name: '平安银行', currency: 'CNY', exchange: 'SZ', aliases: ['平银', 'pingan bank', 'payh'] },
  { id: 'cn:000333', market: 'cn', symbol: '000333', name: '美的集团', currency: 'CNY', exchange: 'SZ', aliases: ['美的', 'midea', 'mdjt'] },
  { id: 'cn:000858', market: 'cn', symbol: '000858', name: '五粮液', currency: 'CNY', exchange: 'SZ', aliases: ['wuliangye', 'wly'] },
  { id: 'cn:002594', market: 'cn', symbol: '002594', name: '比亚迪', currency: 'CNY', exchange: 'SZ', aliases: ['byd'] },
  { id: 'cn:300750', market: 'cn', symbol: '300750', name: '宁德时代', currency: 'CNY', exchange: 'SZ', aliases: ['宁王', 'catl', 'ndsd'] },
  { id: 'cn:300059', market: 'cn', symbol: '300059', name: '东方财富', currency: 'CNY', exchange: 'SZ', aliases: ['东财', 'eastmoney', 'dfcf'] },
  { id: 'cn:002415', market: 'cn', symbol: '002415', name: '海康威视', currency: 'CNY', exchange: 'SZ', aliases: ['海康', 'hikvision', 'hkws'] },
  { id: 'cn:920185', market: 'cn', symbol: '920185', name: '贝特瑞', currency: 'CNY', exchange: 'BJ', aliases: ['btr', 'beitrui', '835185'] },
  { id: 'crypto:BTC/USD', market: 'crypto', symbol: 'BTC/USD', name: 'Bitcoin', currency: 'USD', exchange: 'CRYPTO', aliases: ['比特币', 'btc', 'bitcoin'] },
  { id: 'crypto:ETH/USD', market: 'crypto', symbol: 'ETH/USD', name: 'Ethereum', currency: 'USD', exchange: 'CRYPTO', aliases: ['以太坊', 'eth', 'ethereum'] },
  { id: 'crypto:SOL/USD', market: 'crypto', symbol: 'SOL/USD', name: 'Solana', currency: 'USD', exchange: 'CRYPTO', aliases: ['索拉纳', 'sol', 'solana'] },
  { id: 'crypto:XRP/USD', market: 'crypto', symbol: 'XRP/USD', name: 'XRP', currency: 'USD', exchange: 'CRYPTO', aliases: ['瑞波币', 'xrp', 'ripple'] },
  { id: 'crypto:DOGE/USD', market: 'crypto', symbol: 'DOGE/USD', name: 'Dogecoin', currency: 'USD', exchange: 'CRYPTO', aliases: ['狗狗币', 'doge', 'dogecoin'] },
  { id: 'crypto:ADA/USD', market: 'crypto', symbol: 'ADA/USD', name: 'Cardano', currency: 'USD', exchange: 'CRYPTO', aliases: ['艾达币', 'ada', 'cardano'] },
  { id: 'crypto:AVAX/USD', market: 'crypto', symbol: 'AVAX/USD', name: 'Avalanche', currency: 'USD', exchange: 'CRYPTO', aliases: ['雪崩', 'avax', 'avalanche'] },
  { id: 'crypto:LINK/USD', market: 'crypto', symbol: 'LINK/USD', name: 'Chainlink', currency: 'USD', exchange: 'CRYPTO', aliases: ['预言机', 'link', 'chainlink'] },
];
