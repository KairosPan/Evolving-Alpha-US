/**
 * Capture the REAL Market/Account client with public fictional fixtures.
 * Never starts the backend, reads credentials, or connects to a broker/feed.
 *
 * node face/scripts/capture-demo-assets.mjs --capture
 *   Uses an installed @playwright/cli from the npm cache (or PLAYWRIGHT_CLI_PATH).
 * node face/scripts/capture-demo-assets.mjs
 *   Serves the isolated fixture at 127.0.0.1:4181 for manual CLI inspection.
 *
 * Only the capture document receives English DOM labels and a sample badge.
 * Production face/client sources are served unchanged.
 */
import { createServer } from 'node:http';
import { readFile, readdir, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, extname, basename } from 'node:path';
import { homedir } from 'node:os';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execute = promisify(execFile);
const face = dirname(dirname(fileURLToPath(import.meta.url)));
const project = dirname(face);
const origin = 'http://127.0.0.1:4181';
const stamp = '2026-09-15T14:30:00.000Z';
const assets = [
  { id: 'us:AAPL', market: 'us', symbol: 'AAPL', name: 'Apple', currency: 'USD', exchange: 'NASDAQ' },
  { id: 'us:MSFT', market: 'us', symbol: 'MSFT', name: 'Microsoft', currency: 'USD', exchange: 'NASDAQ' },
  { id: 'us:SPY', market: 'us', symbol: 'SPY', name: 'SPDR S&P 500 ETF', currency: 'USD', exchange: 'NYSE ARCA' },
  { id: 'cn:600519', market: 'cn', symbol: '600519', name: 'Kweichow Moutai', currency: 'CNY', exchange: 'SH' },
  { id: 'crypto:BTC/USD', market: 'crypto', symbol: 'BTC/USD', name: 'Bitcoin', currency: 'USD', exchange: 'CRYPTO' },
  { id: 'crypto:ETH/USD', market: 'crypto', symbol: 'ETH/USD', name: 'Ethereum', currency: 'USD', exchange: 'CRYPTO' },
];
const figures = [
  [210.5, 207.92, 2.58, 1.24, 18450000],
  [495.7, 498.02, -2.32, -0.47, 12100000],
  [560.2, 556.42, 3.78, 0.68, 21350000],
  [1420, 1426, -6, -0.42, 2541000],
  [85200, 83400, 1800, 2.16, 8421.35],
  [null, null, null, null, null],
];
const quotes = {
  ok: true, generated_at: stamp,
  quotes: assets.map((asset, index) => ({
    ...asset,
    ...Object.fromEntries(['price', 'prev_close', 'change', 'change_pct', 'volume'].map((key, i) => [key, figures[index][i]])),
    as_of: figures[index][0] === null ? null : stamp,
    received_at: stamp, volume_as_of: figures[index][0] === null ? null : stamp,
    source: 'Fictional sample', feed: '', basis: asset.market === 'crypto' ? '24h' : 'previous_close',
    quote_status: figures[index][0] === null ? 'unavailable' : 'delayed', market_status: 'unknown',
    message: 'Illustrative figures, not market data.', transport: 'poll',
  })),
  providers: ['us', 'cn', 'crypto'].map((market, i) => ({
    id: ['alpaca', 'ifind', 'coinbase'][i], market, status: 'connected',
    source: 'Fictional sample', feed: '', transport: 'poll', message: 'Offline fixture',
  })),
};
const account = {
  ok: true, available: true, stale: false, generated_at: stamp,
  host: 'paper-api.alpaca.markets',
  account: { status: 'ACTIVE', currency: 'USD', equity: '100000', last_equity: '99840', cash: '64860', buying_power: '64860' },
  positions: [
    { symbol: 'AAPL', side: 'long', qty: '40', avg_entry_price: '205', current_price: '210.50', market_value: '8420', unrealized_pl: '220', unrealized_plpc: String(220 / 8200) },
    { symbol: 'SPY', side: 'long', qty: '30', avg_entry_price: '552', current_price: '560.20', market_value: '16806', unrealized_pl: '246', unrealized_plpc: String(246 / 16560) },
    { symbol: 'MSFT', side: 'long', qty: '20', avg_entry_price: '498', current_price: '495.70', market_value: '9914', unrealized_pl: '-46', unrealized_plpc: String(-46 / 9960) },
  ],
  orders: [], orders_note: 'Fictional paper account. No broker connected.',
};

const labels = {
  'KAIROS': 'GRAVIT', 'Kairos': 'Gravit',
  '搜索股票、加密货币': 'Search stocks and crypto', '自选股': 'Watchlist',
  '美股、A 股与加密货币，关注尽在一处。': 'US equities, China A-shares and crypto assets, in one view.',
  '添加自选': 'Add asset', '按市场筛选': 'Filter by market', '全部市场': 'All markets',
  '全部': 'All', '美股': 'US stocks', 'A 股': 'A-shares', '加密货币': 'Crypto',
  '自选排序': 'Watchlist order', '添加顺序': 'Custom order', '代码 A → Z': 'Symbol A → Z',
  '涨幅优先': 'Top gainers', '跌幅优先': 'Top decliners', '刷新行情': 'Refresh quotes',
  '标的 / 名称': 'Asset / Name', '最新价': 'Price', '涨跌额': 'Change', '涨跌幅': 'Change %',
  '成交量': 'Volume', '行情来源 / 时间': 'Source / Status', '较昨收': 'vs. previous close',
  '24 小时': '24 hours', '延迟报价': 'Sample quote', '暂无报价': 'Unavailable',
  '贵州茅台': 'Kweichow Moutai', '贵': 'K', '股': 'shares',
  '原币报价': 'Original currency', '绿涨': 'Gains', '红跌': 'Losses',
  '自选保存在此浏览器': 'Watchlist stored in this browser', '行情定时更新': 'Sample snapshot',
  '自选行情；缺失数据以横线表示。各标的标明行情来源、事件时间及实时、延迟或过期状态。': 'Sample watchlist. Missing quotes remain unavailable.',
  '自选行情': 'Watchlist quotes', '关闭搜索': 'Close search',
  '搜索代码或名称，如 AAPL、茅台、BTC': 'Search a symbol or name, such as AAPL or BTC',
  '搜索代码或名称': 'Search a symbol or name', '搜索市场': 'Search markets',
  '自选与常用': 'Watchlist and suggestions', '输入名称或代码查询市场标的；搜索结果不代表实时报价。': 'Search by name or symbol. Search results are not live quotes.',
  '↑ ↓ 选择 · Enter 添加': '↑ ↓ Select · Enter Add', '撤销': 'Undo', '移除': 'Remove',
  '接收时间：': 'Received: ', '成交量时间：': 'Volume timestamp: ',
  '（本地）': ' (local)',
  '返回对话': 'Back to research', '账户总览': 'Account overview', '刷新中…': 'Refreshing…', '刷新': 'Refresh',
  '正在读取账户…': 'Loading account…', '资产概览': 'Asset overview', '账户总资产': 'Account equity',
  'Paper · 模拟': 'Paper · Sample', '较上日': 'vs. previous day', '可用现金': 'Cash available',
  '购买力': 'Buying power', '持仓浮动盈亏': 'Unrealized P&L', '账户记录': 'Account records',
  '持仓明细': 'Position details', '订单明细': 'Order details', '持仓': 'Positions', '订单': 'Orders',
  '搜索股票代码': 'Search ticker symbols', '搜索代码': 'Search symbols',
  '全部状态': 'All statuses', '进行中': 'Working', '已成交': 'Filled', '已结束': 'Closed',
  '股票': 'Asset', '持有数量': 'Quantity', '成本价': 'Average cost', '现价': 'Price',
  '持仓市值': 'Market value', '浮动盈亏': 'Unrealized P&L', '多头': 'Long', '空头': 'Short',
  '账户详情': 'Account details', '连接与交易权限': 'Connection and permissions',
  '账户状态': 'Account status', '货币': 'Currency', '连接地址': 'Connection host',
  '页面功能': 'Access', '账户查看': 'Read-only account view', '交易权限与数据来源': 'Permissions and data source',
  '本次数据未提供交易权限状态。': 'No trading permissions in this capture.',
  '本页仅查看账户。刷新读取服务端快照，账户数据最多缓存 60 秒。': 'Read-only account view. This capture uses a fictional snapshot with no broker connected.',
};

function captureDocumentSetup() {
  document.documentElement.lang = 'en';
  const replacements = Object.entries(window.__captureLabels).sort((a, b) => b[0].length - a[0].length);
  const translate = (input) => {
    let result = input;
    for (const [source, target] of replacements) result = result.split(source).join(target);
    return result.replace(/(\d+) 个自选/g, '$1 assets').replace(/(\d+) 项Positions/g, '$1 positions').replace(/(\d+) 笔Orders/g, '$1 orders');
  };
  let queued = false;
  const observer = new MutationObserver(() => {
    if (!queued) { queued = true; requestAnimationFrame(update); }
  });
  function update() {
    observer.disconnect(); queued = false;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      if (node.parentElement?.closest('script,style')) continue;
      const value = translate(node.nodeValue);
      if (value !== node.nodeValue) node.nodeValue = value;
    }
    for (const node of document.querySelectorAll('[aria-label],[title],[placeholder]')) {
      for (const attr of ['aria-label', 'title', 'placeholder']) {
        if (node.hasAttribute(attr)) node.setAttribute(attr, translate(node.getAttribute(attr)));
      }
    }
    for (const [selector, text] of [
      ['#data-status', 'Sample snapshot · No live feed'],
      ['#data-note', 'FICTIONAL FIGURES · Actual client UI with public sample data. US equities and A-shares use previous close; crypto uses 24 hours. Missing quotes remain visible.'],
      ['#stamp', 'FICTIONAL SNAPSHOT · 15 SEP 2026'],
    ]) {
      const node = document.querySelector(selector);
      if (node) node.textContent = text;
    }
    if (!document.querySelector('#capture-disclosure')) {
      const notice = document.createElement('div');
      notice.id = 'capture-disclosure';
      notice.className = document.body.classList.contains('market-body') ? 'market-notice' : 'account-notice';
      notice.style.cssText = 'margin-bottom:20px;padding:12px 16px;border:1px solid #d8e2ee;border-radius:8px;background:#eef3f9;color:#405976;font-size:11px;line-height:1.5;letter-spacing:.01em';
      const isMarket = document.body.classList.contains('market-body');
      notice.textContent = isMarket
        ? 'SAMPLE DATA / FICTIONAL FIGURES — An illustrative watchlist in the actual workbench. No live market connection.'
        : 'SAMPLE DATA / FICTIONAL ACCOUNT — Read-only portfolio view. No real account connected and no trades executed.';
      document.querySelector('.market-heading, .account-heading')?.after(notice);
    }
    if (document.querySelector('.market-table tbody tr, .account-table tbody tr')) document.documentElement.dataset.captureReady = 'true';
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  document.addEventListener('DOMContentLoaded', update, { once: true });
}
const setup = `window.__captureLabels=${JSON.stringify(labels)};localStorage.setItem('kairos.market.watchlist.v1',${JSON.stringify(JSON.stringify({ version: 1, items: assets }))});(${captureDocumentSetup.toString()})();`;
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml' };
const server = createServer(async (req, res) => {
  const url = new URL(req.url, origin);
  const send = (body, type = 'application/json') => { res.writeHead(200, { 'content-type': type, 'cache-control': 'no-store' }); res.end(body); };
  if (req.method !== 'GET') { res.writeHead(405); res.end('Read-only capture server'); return; }
  if (url.pathname === '/data/account.json') return send(JSON.stringify(account));
  if (url.pathname === '/data/quotes') return send(JSON.stringify(quotes));
  if (url.pathname === '/data/quotes/stream') {
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' });
    res.write(`event: quotes\ndata: ${JSON.stringify(quotes)}\n\n`);
    const heartbeat = setInterval(() => res.write('event: heartbeat\ndata: {}\n\n'), 10000);
    req.on('close', () => clearInterval(heartbeat));
    return;
  }
  if (url.pathname === '/capture-setup.js') return send(setup, mime['.js']);
  const route = { '/market': 'market.html', '/account': 'account.html' }[url.pathname];
  const filename = route || (url.pathname.startsWith('/client/') ? url.pathname.slice('/client/'.length) : null);
  if (!filename || basename(filename) !== filename || !mime[extname(filename)]) { res.writeHead(404); res.end('Not in capture fixture'); return; }
  try {
    let body = await readFile(join(face, 'client', filename), 'utf8');
    if (filename.endsWith('.html')) body = body.replace('</head>', '<script src="/capture-setup.js"></script></head>');
    send(body, mime[extname(filename)]);
  } catch { res.writeHead(404); res.end('Not found'); }
});
await new Promise((resolve, reject) => { server.once('error', reject); server.listen(4181, '127.0.0.1', resolve); });
console.log(`Isolated fictional capture fixture: ${origin}`);

if (process.argv.includes('--capture')) {
  try {
    let cli = process.env.PLAYWRIGHT_CLI_PATH;
    if (!cli) {
      const cache = join(homedir(), '.npm', '_npx');
      for (const entry of await readdir(cache)) {
        const candidate = join(cache, entry, 'node_modules', '@playwright', 'cli', 'playwright-cli.js');
        try { await readFile(candidate); cli = candidate; break; } catch { /* Try next installed package. */ }
      }
    }
    if (!cli) throw new Error('Set PLAYWRIGHT_CLI_PATH to an installed @playwright/cli/playwright-cli.js');
    const run = async (...args) => {
      const result = await execute(process.execPath, [cli, '-s=gravit-capture', ...args], { cwd: project, maxBuffer: 5 * 1024 * 1024 });
      console.log(result.stdout);
      if (result.stdout.includes('### Error')) throw new Error('Playwright capture command failed');
      return result.stdout;
    };
    await mkdir(join(project, 'output', 'playwright'), { recursive: true });
    await run('open', `${origin}/market`);
    for (const view of ['market', 'account']) {
      if (view === 'account') await run('goto', `${origin}/${view}`);
      await run('resize', '1440', '1080');
      await run('run-code', `async (page) => { await page.waitForFunction(() => document.documentElement.dataset.captureReady === 'true'); }`);
      await run('snapshot');
      await run('eval', `() => {
        const chinese = [...document.querySelectorAll('body *')]
          .filter(el => el.getClientRects().length && !el.closest('script,style,dialog:not([open])'))
          .filter(el => [...el.childNodes].some(n => n.nodeType === 3 && /[\\u3400-\\u9fff]/.test(n.textContent)));
        if (chinese.length || document.documentElement.scrollWidth > innerWidth) throw new Error('Untranslated text or horizontal overflow');
        return { ready: true, visibleChinese: 0, horizontalOverflow: false };
      }`);
      await run('screenshot', '--filename', join(face, 'landing', `demo-${view}.webp`));
    }
    await run('close');
    console.log('Saved actual-client screenshot assets with fictional sample data.');
  } finally {
    server.closeAllConnections();
    server.close();
  }
}
