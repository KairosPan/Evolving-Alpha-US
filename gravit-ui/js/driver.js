// gravit-ui/js/driver.js — driver c, scripted: what Gravit says back, and the events a demo director can fire
import { message } from './messages.js';
import { MIN, fmtDate } from './time.js';
import { byId } from './data/plugins.js';

const G = (kind, text, data = {}) => message('gravit', kind, text, data);
const ev = (delay, msg) => ({ delay, msg });

// fourteen 4h candles as [open, close, low, high] in SVG y (0 = top of a 68 px box); close < open = up
export const CANDLES = [
  [50, 42, 56, 38], [42, 46, 50, 38], [46, 36, 50, 30], [36, 30, 40, 24], [30, 35, 40, 26], [35, 28, 38, 22], [28, 33, 36, 24],
  [33, 26, 36, 20], [26, 20, 30, 14], [20, 25, 28, 16], [25, 18, 28, 12], [18, 22, 26, 14], [22, 16, 26, 10], [16, 20, 24, 12],
];

// about $5 of each coin at the stand-in prices
const COINS = { BTC: { qty: '0.00008', price: '62,500' }, ETH: { qty: '0.0019', price: '2,630' }, SOL: { qty: '0.034', price: '147' } };
const coinIn = t => (/\beth\b|以太/.test(t) ? 'ETH' : /\bsol\b/.test(t) ? 'SOL' : 'BTC');

// what a bot says when it is named in a group (spec §5.8: bots argue, Gravit alone proposes)
const BOT_LINES = {
  buffett: 'KO 这个价我会买：看得懂、便宜、拿得住。NVDA 市盈率 55，太贵。',
  politician: '最近一条披露：Pelosi 10/7 买 NVDA。跟不跟，Gravit 说了算。',
  serenity: '英伟达的上游：台积电、ASML、海力士。卡脖子的是封装产能。',
  kol: '他今天没喊单。上一笔是 SOL，三天前。',
};
// the plugin's second turn in its teaching conversation
const TEACH_REPLIES = {
  buffett: t => `好，能拿「${t}」，我就照这个挑：看得懂、便宜、拿得住。每周一我在这里点评你的仓。`,
  politician: t => `好，记下了：「${t}」。下一条披露一出来，我就在这里说；跟不跟按你的额度。`,
};
// the names a bot answers to after @: its id, its name, the name without "bot", and without "美国" (政客)
const names = id => {
  const p = byId(id);
  if (!p) return [id];
  const bare = p.name.replace(/\s*bot$/i, '');
  return [p.id, p.name, bare, bare.replace(/^美国/, '')].map(n => n.toLowerCase());
};
const mentioned = (t, members) => members.find(m => m !== 'gravit' && names(m).some(n => n && t.includes('@' + n)));
// the per-order cap the conversation really has (Details shows the same)
const capOf = ctx => ctx.limit?.perOrder ?? 25;

export function replyTo(text, ctx = {}) {
  const t = (text ?? '').toLowerCase();
  const installed = ctx.installed ?? [];
  const now = ctx.now ?? Date.now();
  const conv = ctx.conv ?? null;
  if (conv?.teach) {
    const say = TEACH_REPLIES[conv.teach] ?? (() => '好，记下了。有新的我在这里说。');
    return [ev(1200, message(conv.teach, 'text', say((text ?? '').trim())))];
  }
  if (conv?.kind === 'group') {
    const bot = mentioned(t, conv.members ?? []);
    if (bot) return [ev(1200, message(bot, 'text', BOT_LINES[bot] ?? '我看看，有结论在这里说。'))];
    if (/pelosi|跟单|政客/.test(t) && (conv.members ?? []).includes('politician')) {
      const title = '要你答：跟 NVDA $25';
      return [
        ev(1200, message('politician', 'text', '披露：Pelosi 10/7 买 NVDA $1–5M。照我的规矩是跟 $25。')),
        ev(2800, G('card', title, { title, venue: 'Stand-in Broker', type: 'market', about: '$25', cardId: '{card}', by: now + 20 * MIN })),
      ];
    }
  }
  // whole words only: "something" and "method" are not ETH; JS \b treats Chinese as a boundary, so 买btc still matches
  if (/\bbtc\b|比特币|\beth\b|以太|\bsol\b/.test(t)) {
    const coin = coinIn(t);
    const title = `要你答：买 ${COINS[coin].qty} ${coin}`;
    return [
      ev(1200, G('text', '收到。看了 Stand-in Exchange 和 Stand-in Wallet 的 DEX，交易所便宜。先建 $5 试水。')),
      // {card} {ord} {ledger} are numbered by the store's counters when the message lands (reducers/messages.js append)
      ev(2800, G('card', title, { title, coin, venue: 'Stand-in Exchange', type: 'market', about: 'about $5.00', cardId: '{card}', by: now + 26 * MIN })),
    ];
  }
  if (/pelosi|跟单|政客/.test(t)) {
    if (!installed.includes('politician')) return [ev(1200, G('install', '跟单要装 美国政客 bot，Discover 里有。', { plugin: 'politician' }))];
    return [
      ev(1200, G('text', '好。美国政客 bot 在，披露一出来我就跟，在额度里的直接下单。')),
      ev(3200, message('politician', 'proposal', '披露：Pelosi 买 NVDA。照它买 $20，在额度里，直接成交。', { status: 'filled', ord: '{ord}', venue: 'Stand-in Broker' })),
    ];
  }
  if (/0x[0-9a-f]{4,}|地址|骗子/.test(t)) {
    return [
      ev(1000, G('text', '查了。')),
      ev(1900, message('fraud', 'signal', '0x9f3a…c21e · 在 3 份骗子名单里 · 合约可暂停转出', { source: '地址欺诈检测' })),
      ev(2800, G('alert', '这个地址在骗子名单里，没有转。')),
    ];
  }
  if (/额度|上限/.test(t)) { const cap = capOf(ctx); return [ev(1000, G('limit', `每单上限 $${cap} 不够，改到 $${cap * 2}？`, { from: cap, to: cap * 2 }))]; }
  return [ev(1000, G('text', '收到，我先看看。')), ev(2800, G('text', '看了，没有要动的。有事我说。'))];
}

export function followUp(msg, answer, ctx = {}) {
  if (!msg || msg.answer) return [];
  if (msg.kind === 'card') {
    const coin = COINS[msg.data?.coin] ? msg.data.coin : 'BTC';
    if (answer !== 'approved') return [ev(1200, G('text', '好，不买。有变化我再问。'))];
    const cap = capOf(ctx);
    // the next add is $30: ask to raise the cap only when the real cap is below it
    const ask = cap < 30 ? [ev(3400, G('limit', `想再加 $30，但你的每单上限是 $${cap}。改到 $${cap * 2}？`, { from: cap, to: cap * 2 }))] : [];
    return [ev(1500, G('receipt', `${COINS[coin].qty} ${coin} @ ${COINS[coin].price} · {ord} · 账本 {ledger}`, { status: 'filled', amount: 5 })), ...ask];
  }
  if (msg.kind === 'limit') {
    if (answer !== 'granted') return [ev(1200, G('text', `那就还是 $${msg.data.from}。`))];
    // no ask when it is installed, or when an earlier ask for it is still waiting in this conversation
    const ask = [...(ctx.installed ?? []), ...(ctx.pending ?? [])].includes('news') ? [] : [ev(2800, G('install', 'Discover 里有个 News sentiment。装上我就能看情绪再加仓。', { plugin: 'news' }))];
    return [ev(1200, G('text', `改到 $${msg.data.to} 了。`)), ...ask];
  }
  if (msg.kind === 'install') return answer === 'no' ? [ev(1000, G('text', '好，不装。'))] : [];
  return [];
}

export const director = {
  brief: now => G('brief', '早报', { date: fmtDate(now), time: '7:30', lines: [
    '隔夜：纳指 +0.8%，{{BTC}} 63.1k（+1.4%）',
    '今天：CPI 8:30 · {{NVDA}} 财报后第一天',
    '你的仓：{{BTC}} $3,740 · {{AAPL}} $2,510，没有要到期的额度',
    '我的建议：CPI 出来前不动。',
  ] }),
  ta: () => G('ta', 'NVDA 技术面', { ticker: 'NVDA', tf: '4h', support: 178, resistance: 192, candles: CANDLES, lines: ['区间上沿，量在放。支撑 178，压力 192。', '结论：要追等回踩 182，别在上沿接。'] }),
  breaking: now => ({ id: 'b-' + now, headline: 'SEC 起诉 Stand-in Exchange（替身新闻）', body: '你在那儿有 BTC $3,740。Gravit 已经停了这家的单，等你一句。', at: now }),
  call: () => ({ from: 'gravit', about: '想说 BTC 的事，30 秒' }),
  bot: () => message('buffett', 'text', '补一句：KO 这个价我会买。'),
  // kind 8, the door's refusal, and kind 10, the close (spec §6)
  refusal: () => G('refusal', '想下 $30，场所拒了：超过这份额度的每单上限 $25。', { code: 'E_MANDATE_PER_ORDER_CAP' }),
  done: now => G('done', `办完了：买了 0.00008 BTC，花了 $5，${fmtDate(now)} 收尾。`, { foot: '账本对上 · 额度还剩 $95' }),
};
