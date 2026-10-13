// gravit-ui/js/data/seed.js — the state the demo boots into: the four conversations of the boards, Memory, the account numbers
import { MIN, DAY } from '../time.js';

// 2: the controls round added edit, confirm, compose, mail, account activity and panels
// 3: round 3 made the mailbox a screen and Create Discover's own MCP face
// 4: Markets and Trade: holdings with quantities, cash at the venues, the account's orders, the watchlist, the ticket
export const SEED_VERSION = 5;

// the places Gravit may trade, as the draft's venue pick list and the Move form offer them
export const VENUES = ['Stand-in Exchange', 'Stand-in Broker', 'Stand-in Wallet'];
// the accounts Connect an account offers (stand-ins: connecting one asks nothing real)
export const CONNECTABLE = ['Coinbase', 'Interactive Brokers', 'Polymarket', 'Hyperliquid'];

const msg = (from, kind, text, data = {}, extra = {}) => ({ from, kind, text, data, ...extra });

export function seed(now = Date.now()) {
  const ago = min => now - min * MIN;
  let n = 0;
  const stamp = (at, m) => ({ id: `m-${++n}`, at, ...m });

  const btc = {
    id: 'c-1', title: 'Small BTC position under $70k', kind: 'gravit', members: ['gravit'], unread: false, status: 'working',
    intent: { id: 'intent-0003', created: ago(6), until: now + 6 * DAY, limit: { perOrder: 25, total: 100, spent: 5, venue: 'Stand-in Exchange' } },
    plugins: ['pricefeed', 'fraud'],
    messages: [
      stamp(ago(6), msg('you', 'text', 'Buy a small BTC position under $70k, no more than $25 at a time.')),
      stamp(ago(5.5), msg('gravit', 'text', 'Got it. Checked Stand-in Exchange and the DEX in Stand-in Wallet; the exchange is cheaper. Starting with $5.')),
      stamp(ago(5), msg('gravit', 'card', 'Your call: buy 0.00008 BTC', { title: 'Your call: buy 0.00008 BTC', venue: 'Stand-in Exchange', type: 'market', about: 'about $5.00', cardId: 'card-0001', by: now + 26 * MIN }, { answer: 'approved' })),
      stamp(ago(3), msg('you', 'text', 'Approved.')),
      stamp(ago(2.5), msg('gravit', 'receipt', '0.00008 BTC @ 62,500 · ord-0001 · ledger #41', { status: 'filled' })),
      stamp(ago(2.4), msg('gravit', 'limit', 'I want to add $30, but your limit is $25 an order. Raise it to $50?', { from: 25, to: 50 })),
      stamp(ago(0), msg('gravit', 'install', 'There is a News sentiment plugin in Discover. With it I can read sentiment before adding.', { plugin: 'news' })),
    ],
  };

  const pelosi = {
    id: 'c-2', title: 'Follow Pelosi’s trades', kind: 'bot', members: ['gravit', 'politician'], unread: true, status: 'working',
    intent: { id: 'intent-0002', created: ago(27), until: now + 6 * DAY, limit: { perOrder: 20, total: 100, spent: 20, venue: 'Stand-in Broker' } },
    plugins: ['politician'],
    messages: [
      stamp(ago(27), msg('you', 'text', 'Follow Pelosi’s trades, $20 or less each.')),
      stamp(ago(26.5), msg('gravit', 'text', 'OK. The US politician bot is on it. I follow each disclosure as it lands; inside your limit I place it myself.')),
      stamp(ago(26), msg('politician', 'proposal', 'Disclosure: Pelosi bought NVDA. Bought $20 the same way, inside the limit, filled directly.', { status: 'filled', ord: 'ord-0004', venue: 'Stand-in Broker' })),
    ],
  };

  const addr = {
    id: 'c-3', title: 'Is this address a scam?', kind: 'gravit', members: ['gravit'], unread: false, status: 'done',
    intent: { id: 'intent-0001', created: now - DAY - 40 * MIN, until: now + 5 * DAY, limit: null },
    plugins: ['fraud'],
    messages: [
      stamp(now - DAY - 40 * MIN, msg('you', 'text', 'Is this address a scam? 0x9f3a…c21e')),
      stamp(now - DAY - 39 * MIN, msg('fraud', 'signal', '0x9f3a…c21e · on 3 scam lists · contract can pause withdrawals', { source: 'Address fraud check' })),
      stamp(now - DAY - 38 * MIN, msg('gravit', 'alert', 'The address is on a scam list. Nothing was sent.')),
    ],
  };

  const group = {
    id: 'c-4', title: 'Pick stocks with Pelosi and Buffett', kind: 'group', members: ['gravit', 'politician', 'buffett'], unread: false, status: 'working',
    intent: { id: 'intent-0004', created: ago(27), until: now + 6 * DAY, limit: { perOrder: 25, total: 50, spent: 25, venue: 'Stand-in Broker' } },
    plugins: ['politician', 'buffett'],
    messages: [
      stamp(ago(27), msg('you', 'text', 'You two, $50 at most: anything worth buying today?')),
      stamp(ago(26), msg('politician', 'text', 'Disclosure: Pelosi bought NVDA $1–5M on 10/7, public today. By my rule that is a $25 follow.')),
      stamp(ago(25), msg('buffett', 'text', 'NVDA at 55 times earnings is not a price I would pay. KO is more my style: I understand it, it is cheap, I can hold it.')),
      stamp(ago(24), msg('gravit', 'card', 'Your call: two orders, $25 each', { title: 'Your call: two orders, $25 each', by: now + 20 * MIN, rows: [{ t: 'NVDA', why: 'per disclosure · Stand-in Broker · market', amt: '$25' }, { t: 'KO', why: 'per Buffett · Stand-in Broker · limit 58.20', amt: '$25' }], note: 'Both inside the limit. Want just one? Say which.' }, { answer: 'approved' })),
      stamp(ago(21), msg('you', 'text', 'Both.')),
      stamp(ago(20.5), msg('gravit', 'receipt', 'NVDA $25 @ 187.40 · ord-0009 · ledger #58', { status: 'filled', more: 'KO is on the book; 58.20 not reached yet. I will say when it fills.' })),
    ],
  };

  const mem = (id, group, text, source, daysAgo) => ({ id: `mem-${id}`, group, text, source, at: now - daysAgo * DAY });

  return {
    v: SEED_VERSION,
    theme: 'system',
    route: { screen: 'messages', id: 'c-1' },
    lastConv: 'c-1',
    railCollapsed: false,
    draft: null,
    detailsOpen: false,
    settingsOpen: false,
    counters: { intent: 4, ord: 9, card: 1, pay: 7, ledger: 58, msg: n, conv: 4, plugin: 0, mem: 9, mail: 3 },
    conversations: [btc, pelosi, addr, group],
    discover: { query: '', installedOnly: false, create: null, toast: null },
    // Markets' view and watchlist, and Trade's kind, search and ticket (the ticket is moment-only)
    markets: { tab: 'all', sort: 'volume', q: '', interval: '1h', watch: ['BTC', 'FED-DEC', 'DOGE'] },
    trade: { kind: 'crypto', q: '', ticket: null },
    plugins: { installed: ['pricefeed', 'fraud', 'politician', 'buffett', 'pairs'], mine: ['pairs'], uploaded: [] },
    memory: {
      entries: [
        mem(1, 'Style', 'Value over hype', 'You said', 7), mem(2, 'Style', 'No leverage', 'You said', 7), mem(3, 'Style', 'Watches the tech supply chain', 'Learned from your questions', 3),
        mem(4, 'Rules', 'No order over $25; real money passes me first', 'From your limit', 1), mem(5, 'Rules', 'Telegram calls: read, never chase', 'You said', 1), mem(6, 'Rules', 'Ask before adding; never widen a limit alone', 'Learned when you declined', 0),
        mem(7, 'Venues and people', 'BTC on the exchange, cheaper than the DEX', 'Compared on its own', 1), mem(8, 'Venues and people', 'Follow Pelosi’s disclosures, pick like Buffett', 'From installed bots', 0), mem(9, 'Venues and people', 'Brief at 7:30; hold before CPI', 'You said', 0),
      ],
      remember: true, askFirst: false, botsRead: false,
    },
    account: {
      mode: 'guard', netWorth: 12480, today: 86, todayPct: 0.7,
      alloc: [{ name: 'Cash', pct: 30, token: 'cash' }, { name: 'Stablecoins', pct: 20, token: 'stable' }, { name: 'Crypto', pct: 30, token: 'crypto' }, { name: 'Stocks', pct: 20, token: 'equity' }],
      // quantities at the stand-in quotes of js/data/markets.js; value = quantity × price
      holdings: [
        { key: 'crypto:BTC', name: 'BTC', venue: 'Stand-in Exchange', qty: 0.05955, value: 3739.74, chg: 1.2 },
        { key: 'equity:AAPL', name: 'AAPL', venue: 'Stand-in Broker', qty: 10.99, value: 2510.12, chg: -0.4 },
        { key: 'stable:USDC', name: 'USDC', venue: 'Stand-in Wallet', qty: 2490, value: 2490, chg: null },
        { key: 'equity:NVDA', name: 'NVDA', venue: 'Stand-in Broker', qty: 0.2402, value: 45.01, chg: 1.9 },
      ],
      // dollars at the venues that hold cash; net worth = cash + holdings + Gravit's wallet
      cash: { 'Stand-in Exchange': 1182.73, 'Stand-in Broker': 2500 },
      // every order, by Gravit or by you, newest first (KO's limit is the one still on the book)
      orders: [
        { id: 'ord-0001', at: ago(2.5), inst: 'BTC', venue: 'Stand-in Exchange', symbol: 'BTC/USDT', side: 'buy', type: 'market', qty: 0.00008, limit: null, outcome: null, status: 'filled', price: 62500, usd: 5, fee: 0, by: 'gravit', how: 'approved', conv: 'c-1', note: 'filled at 62,500' },
        { id: 'ord-0009', at: ago(20.5), inst: 'NVDA', venue: 'Stand-in Broker', symbol: 'NVDA', side: 'buy', type: 'market', qty: 0.1334, limit: null, outcome: null, status: 'filled', price: 187.4, usd: 25, fee: 0, by: 'gravit', how: 'approved', conv: 'c-4', note: 'filled at 187.4' },
        { id: 'ord-0008', at: ago(20.5), inst: 'KO', venue: 'Stand-in Broker', symbol: 'KO', side: 'buy', type: 'limit', qty: 0.4295, limit: 58.2, outcome: null, status: 'open', price: null, usd: null, fee: 0, by: 'gravit', how: 'approved', conv: 'c-4', note: 'on Stand-in Broker’s book at 58.2' },
        { id: 'ord-0004', at: ago(26), inst: 'NVDA', venue: 'Stand-in Broker', symbol: 'NVDA', side: 'buy', type: 'market', qty: 0.1068, limit: null, outcome: null, status: 'filled', price: 187.2, usd: 20, fee: 0, by: 'gravit', how: 'limit', conv: 'c-2', note: 'filled at 187.2' },
      ],
      venues: [
        { name: 'Stand-in Exchange', line: 'Connected · key file · Gravit may trade', state: 'Healthy' },
        { name: 'Stand-in Broker', line: 'Connected · key file · Gravit may trade', state: 'Healthy' },
        { name: 'Stand-in Wallet', line: 'Connected · address proved · Gravit: read only', state: 'Healthy' },
        { name: 'Kalshi', line: 'Asked it first, without a key', state: 'Not served here' },
      ],
      wallet: { usdc: 12.4, chain: 'Base', address: '0xec4c…16c1', full: '0xec4c3e9d5b7a2f1c8e6d4b2a9f7c5e3d1b8a16c1' },
      // the owner's own Stand-in Wallet: where Account's Receive takes money in (Gravit's wallet is topped up from Details)
      receive: { venue: 'Stand-in Wallet', asset: 'USDC', chain: 'Base', address: '0x9a7c…d41e', full: '0x9a7c5e2b8f1d4a6c3e9b7f2d5a8c1e4b6d3fd41e' },
      // the statement, newest first: fills, moves, top-ups
      activity: [
        { at: ago(2.5), text: 'Fill · 0.00008 BTC @ 62,500 · ord-0001', amount: -5 },
        { at: ago(20.5), text: 'Fill · NVDA $25 @ 187.40 · ord-0009', amount: -25 },
        { at: ago(26), text: 'Fill · NVDA $20 @ 187.20 · ord-0004', amount: -20 },
        { at: now - 2 * DAY, text: 'Deposit · USDC $500 · Stand-in Wallet', amount: 500 },
      ],
      panel: null, connecting: null, copied: false, panelError: null,
    },
    banner: null,
    call: null,
    edit: null,
    confirm: null,
    compose: { files: [], listening: false },
    // Gravit's own mailbox (docs/research/2026-10-06-agent-phone-and-email.md: the agent's own address)
    mail: {
      address: 'gravit@mail.stand-in',
      items: [
        { id: 'mail-1', from: 'Stand-in Broker', subject: 'October statement', at: ago(120), read: false, files: ['statement-2026-10.pdf'], body: 'Two fills this month: NVDA $25, KO still on the book. Holdings worth $2,510.' },
        { id: 'mail-2', from: 'SEC EDGAR', subject: 'Form 4: Pelosi reports buying NVDA', at: ago(300), read: false, body: 'Filer Nancy Pelosi, bought NVDA on 10/7, $1–5M. The US politician bot has read this.' },
        { id: 'mail-3', from: 'Gravit', subject: 'Weekly summary', at: now - DAY - 3 * 60 * MIN, read: true, body: 'Placed 2 orders for you this week, $30 spent, $95 of the limit left. Never hit the cap.' },
      ],
    },
  };
}

// the first-run state (F6): no conversations yet; Memory and the account as in the seed
export function firstRun(now = Date.now()) {
  return { ...seed(now), conversations: [], route: { screen: 'messages', id: null } };
}
