// gravit-ui/js/driver.js — driver c, scripted: what Gravit says back, and the events a demo director can fire
import { message } from './messages.js';
import { MIN, fmtDate } from './time.js';

const G = (kind, text, data = {}) => message('gravit', kind, text, data);
const ev = (delay, msg) => ({ delay, msg });

// fourteen 4h candles as [open, close, low, high] in SVG y (0 = top of a 68 px box); close < open = up
export const CANDLES = [
  [50, 42, 56, 38], [42, 46, 50, 38], [46, 36, 50, 30], [36, 30, 40, 24], [30, 35, 40, 26], [35, 28, 38, 22], [28, 33, 36, 24],
  [33, 26, 36, 20], [26, 20, 30, 14], [20, 25, 28, 16], [25, 18, 28, 12], [18, 22, 26, 14], [22, 16, 26, 10], [16, 20, 24, 12],
];

export function replyTo(text, ctx = {}) {
  const t = (text ?? '').toLowerCase();
  const installed = ctx.installed ?? [];
  const now = ctx.now ?? Date.now();
  if (/btc|比特币|eth|以太|sol\b/.test(t)) {
    return [
      ev(1200, G('text', '收到。看了 Stand-in Exchange 和 Stand-in Wallet 的 DEX，交易所便宜。先建 $5 试水。')),
      ev(2800, G('card', '要你答：买 0.00008 BTC', { title: '要你答：买 0.00008 BTC', venue: 'Stand-in Exchange', type: 'market', about: 'about $5.00', by: now + 26 * MIN })),
    ];
  }
  if (/pelosi|跟单|政客/.test(t)) {
    if (!installed.includes('politician')) return [ev(1200, G('install', '跟单要装 美国政客 bot，Discover 里有。', { plugin: 'politician' }))];
    return [
      ev(1200, G('text', '好。美国政客 bot 在，披露一出来我就跟，在额度里的直接下单。')),
      ev(3200, message('politician', 'proposal', '披露：Pelosi 买 NVDA。照它买 $20，在额度里，直接成交。', { status: 'filled', ord: 'ord-0004', venue: 'Stand-in Broker' })),
    ];
  }
  if (/0x[0-9a-f]{4,}|地址|骗子/.test(t)) {
    return [
      ev(1000, G('text', '查了。')),
      ev(1900, message('fraud', 'signal', '0x9f3a…c21e · 在 3 份骗子名单里 · 合约可暂停转出', { source: '地址欺诈检测' })),
      ev(2800, G('alert', '这个地址在骗子名单里，没有转。')),
    ];
  }
  if (/额度|上限/.test(t)) return [ev(1000, G('limit', '每单上限 $25 不够，改到 $50？', { from: 25, to: 50 }))];
  return [ev(1000, G('text', '收到，我先看看。')), ev(2800, G('text', '看了，没有要动的。有事我说。'))];
}

export function followUp(msg, answer, ctx = {}) {
  if (!msg || msg.answer) return [];
  if (msg.kind === 'card') {
    return answer === 'approved'
      ? [ev(1500, G('receipt', '0.00008 BTC @ 62,500 · ord-0001 · 账本 #41', { status: 'filled' })), ev(3400, G('limit', '想再加 $30，但你的每单上限是 $25。改到 $50？', { from: 25, to: 50 }))]
      : [ev(1200, G('text', '好，不买。有变化我再问。'))];
  }
  if (msg.kind === 'limit') {
    return answer === 'granted'
      ? [ev(1200, G('text', `改到 $${msg.data.to} 了。`)), ev(2800, G('install', 'Discover 里有个 News sentiment。装上我就能看情绪再加仓。', { plugin: 'news' }))]
      : [ev(1200, G('text', `那就还是 $${msg.data.from}。`))];
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
};
