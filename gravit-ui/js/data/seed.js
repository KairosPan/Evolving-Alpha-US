// gravit-ui/js/data/seed.js — the state the demo boots into: the four conversations of the boards, Memory, the account numbers
import { MIN, DAY } from '../time.js';

// 2: the controls round added edit, confirm, compose, mail, account activity and panels
export const SEED_VERSION = 2;

// the places Gravit may trade, as the draft's venue pick list and the Move form offer them
export const VENUES = ['Stand-in Exchange', 'Stand-in Broker', 'Stand-in Wallet'];

const msg = (from, kind, text, data = {}, extra = {}) => ({ from, kind, text, data, ...extra });

export function seed(now = Date.now()) {
  const ago = min => now - min * MIN;
  let n = 0;
  const stamp = (at, m) => ({ id: `m-${++n}`, at, ...m });

  const btc = {
    id: 'c-1', title: '小仓位 BTC，$70k 以下', kind: 'gravit', members: ['gravit'], unread: false, status: 'working',
    intent: { id: 'intent-0003', created: ago(6), until: now + 6 * DAY, limit: { perOrder: 25, total: 100, spent: 5, venue: 'Stand-in Exchange' } },
    plugins: ['pricefeed', 'fraud'],
    messages: [
      stamp(ago(6), msg('you', 'text', '小仓位买 BTC，$70k 以下，一次别超过 $25。')),
      stamp(ago(5.5), msg('gravit', 'text', '收到。看了 Stand-in Exchange 和 Stand-in Wallet 的 DEX，交易所便宜。先建 $5 试水。')),
      stamp(ago(5), msg('gravit', 'card', '要你答：买 0.00008 BTC', { title: '要你答：买 0.00008 BTC', venue: 'Stand-in Exchange', type: 'market', about: 'about $5.00', cardId: 'card-0001', by: now + 26 * MIN }, { answer: 'approved' })),
      stamp(ago(3), msg('you', 'text', 'Approved.')),
      stamp(ago(2.5), msg('gravit', 'receipt', '0.00008 BTC @ 62,500 · ord-0001 · 账本 #41', { status: 'filled' })),
      stamp(ago(2.4), msg('gravit', 'limit', '想再加 $30，但你的每单上限是 $25。改到 $50？', { from: 25, to: 50 })),
      stamp(ago(0), msg('gravit', 'install', 'Discover 里有个 News sentiment。装上我就能看情绪再加仓。', { plugin: 'news' })),
    ],
  };

  const pelosi = {
    id: 'c-2', title: '跟单 Pelosi 的交易', kind: 'bot', members: ['gravit', 'politician'], unread: true, status: 'working',
    intent: { id: 'intent-0002', created: ago(27), until: now + 6 * DAY, limit: { perOrder: 20, total: 100, spent: 20, venue: 'Stand-in Broker' } },
    plugins: ['politician'],
    messages: [
      stamp(ago(27), msg('you', 'text', '跟单 Pelosi 的交易，每笔 $20 以内。')),
      stamp(ago(26.5), msg('gravit', 'text', '好。美国政客 bot 在，披露一出来我就跟，在额度里的直接下单。')),
      stamp(ago(26), msg('politician', 'proposal', '披露：Pelosi 买 NVDA。照它买 $20，在额度里，直接成交。', { status: 'filled', ord: 'ord-0004', venue: 'Stand-in Broker' })),
    ],
  };

  const addr = {
    id: 'c-3', title: '查这个地址是不是骗子', kind: 'gravit', members: ['gravit'], unread: false, status: 'done',
    intent: { id: 'intent-0001', created: now - DAY - 40 * MIN, until: now + 5 * DAY, limit: null },
    plugins: ['fraud'],
    messages: [
      stamp(now - DAY - 40 * MIN, msg('you', 'text', '查这个地址是不是骗子：0x9f3a…c21e')),
      stamp(now - DAY - 39 * MIN, msg('fraud', 'signal', '0x9f3a…c21e · 在 3 份骗子名单里 · 合约可暂停转出', { source: '地址欺诈检测' })),
      stamp(now - DAY - 38 * MIN, msg('gravit', 'alert', '这个地址在骗子名单里，没有转。')),
    ],
  };

  const group = {
    id: 'c-4', title: '跟 Pelosi 和 Buffett 挑股', kind: 'group', members: ['gravit', 'politician', 'buffett'], unread: false, status: 'working',
    intent: { id: 'intent-0004', created: ago(27), until: now + 6 * DAY, limit: { perOrder: 25, total: 50, spent: 25, venue: 'Stand-in Broker' } },
    plugins: ['politician', 'buffett'],
    messages: [
      stamp(ago(27), msg('you', 'text', '两位，$50 以内，今天有什么值得买的？')),
      stamp(ago(26), msg('politician', 'text', '披露：Pelosi 10/7 买 NVDA $1–5M，今天公开。照我的规矩是跟 $25。')),
      stamp(ago(25), msg('buffett', 'text', 'NVDA 市盈率 55，不是我会出的价。KO 更像我的：看得懂、便宜、拿得住。')),
      stamp(ago(24), msg('gravit', 'card', '要你答：两笔，各 $25', { title: '要你答：两笔，各 $25', by: now + 20 * MIN, rows: [{ t: 'NVDA', why: '跟披露 · Stand-in Broker · market', amt: '$25' }, { t: 'KO', why: '照 Buffett · Stand-in Broker · limit 58.20', amt: '$25' }], note: '两条都在额度里。要只要一笔，回我一句就行。' }, { answer: 'approved' })),
      stamp(ago(21), msg('you', 'text', '两笔都要。')),
      stamp(ago(20.5), msg('gravit', 'receipt', 'NVDA $25 @ 187.40 · ord-0009 · 账本 #58', { status: 'filled', more: 'KO 挂着，58.20 还没到。到了我说一声。' })),
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
    counters: { intent: 4, ord: 9, card: 1, pay: 7, ledger: 58, msg: n, conv: 4, plugin: 0, mem: 9 },
    conversations: [btc, pelosi, addr, group],
    discover: { query: '', installedOnly: false, drawer: null, create: null, toast: null },
    plugins: { installed: ['pricefeed', 'fraud', 'politician', 'buffett', 'pairs'], mine: ['pairs'], uploaded: [] },
    memory: {
      entries: [
        mem(1, '风格', '偏价值，不追热点', '你说的', 7), mem(2, '风格', '不碰杠杆', '你说的', 7), mem(3, '风格', '盯科技产业链', '它从你的问题里学的', 3),
        mem(4, '规矩', '每单不超过 $25，真钱先过我', '来自额度', 1), mem(5, '规矩', 'Telegram 群的喊单只看不追', '你说的', 1), mem(6, '规矩', '加仓先问，别自己扩额度', '它从你拒掉的那次学的', 0),
        mem(7, '场所和人', 'BTC 去交易所，比 DEX 便宜', '它自己比出来的', 1), mem(8, '场所和人', '跟 Pelosi 的披露，用 Buffett 的挑法', '来自装的 bot', 0), mem(9, '场所和人', '早报 7:30，CPI 前不动', '你说的', 0),
      ],
      remember: true, askFirst: false, botsRead: false,
    },
    account: {
      mode: 'guard', netWorth: 12480, today: 86, todayPct: 0.7,
      alloc: [{ name: 'Cash', pct: 30, token: 'cash' }, { name: 'Stablecoins', pct: 20, token: 'stable' }, { name: 'Crypto', pct: 30, token: 'crypto' }, { name: 'Stocks', pct: 20, token: 'equity' }],
      holdings: [{ key: 'crypto:BTC', name: 'BTC', venue: 'Stand-in Exchange', value: 3740, chg: 1.2 }, { key: 'equity:AAPL', name: 'AAPL', venue: 'Stand-in Broker', value: 2510, chg: -0.4 }, { key: 'stable:USDC', name: 'USDC', venue: 'Stand-in Wallet', value: 2490, chg: null }],
      venues: [
        { name: 'Stand-in Exchange', line: 'Connected · key file · Gravit may trade', state: 'Healthy' },
        { name: 'Stand-in Broker', line: 'Connected · key file · Gravit may trade', state: 'Healthy' },
        { name: 'Stand-in Wallet', line: 'Connected · address proved · Gravit: read only', state: 'Healthy' },
        { name: 'Kalshi', line: 'Asked it first, without a key', state: 'Not served here' },
      ],
      wallet: { usdc: 12.4, chain: 'Base', address: '0xec4c…16c1' },
      // the statement, newest first: fills, moves, top-ups
      activity: [
        { at: ago(2.5), text: 'Fill · 0.00008 BTC @ 62,500 · ord-0001', amount: -5 },
        { at: ago(20.5), text: 'Fill · NVDA $25 @ 187.40 · ord-0009', amount: -25 },
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
      address: 'gravit@mail.stand-in', open: false, reading: null,
      items: [
        { id: 'mail-1', from: 'Stand-in Broker', subject: '10 月对账单', at: ago(120), read: false, body: '本月成交 2 笔：NVDA $25、KO 挂单中。持仓市值 $2,510。附件：statement-2026-10.pdf。' },
        { id: 'mail-2', from: 'SEC EDGAR', subject: 'Form 4：Pelosi 申报买入 NVDA', at: ago(300), read: false, body: '申报人 Nancy Pelosi，10/7 买入 NVDA，金额 $1–5M。美国政客 bot 已经读到这条。' },
        { id: 'mail-3', from: 'Gravit', subject: '每周小结', at: now - DAY - 3 * 60 * MIN, read: true, body: '这周替你下了 2 笔单，花了 $30，额度还剩 $95。没有碰到上限。' },
      ],
    },
  };
}

// the first-run state (F6): no conversations yet; Memory and the account as in the seed
export function firstRun(now = Date.now()) {
  return { ...seed(now), conversations: [], route: { screen: 'messages', id: null } };
}
