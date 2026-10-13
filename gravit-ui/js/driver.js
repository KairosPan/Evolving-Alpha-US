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
const coinIn = t => (/\beth\b|ethereum/.test(t) ? 'ETH' : /\bsol\b|solana/.test(t) ? 'SOL' : 'BTC');

// what a bot says when it is named in a group (spec §5.8: bots argue, Gravit alone proposes)
const BOT_LINES = {
  buffett: 'KO at this price I would buy: I understand it, it is cheap, I can hold it. NVDA at 55 times earnings is too expensive.',
  politician: 'Latest disclosure: Pelosi bought NVDA on 10/7. Whether to follow is Gravit’s call.',
  serenity: 'Upstream of Nvidia: TSMC, ASML, SK Hynix. The bottleneck is packaging capacity.',
  kol: 'No call from him today. The last one was SOL, three days ago.',
};
// the plugin's second turn in its teaching conversation
const TEACH_REPLIES = {
  buffett: t => `Good. You can hold for “${t}”, so I pick by that: understandable, cheap, holdable. Every Monday I review your holdings here.`,
  politician: t => `Noted: “${t}”. The next disclosure, I say it here; whether I follow depends on your limit.`,
  moat: t => `“${t}”: moat 8/10 · brand, distribution, pricing power.`,
  cpi: () => 'Noted. The next CPI print, I explain it here in three lines.',
};
// the names a bot answers to after @: its id, its name, the name without "bot", and without "US " (politician)
const names = id => {
  const p = byId(id);
  if (!p) return [id];
  const bare = p.name.replace(/\s*bot$/i, '');
  return [p.id, p.name, bare, bare.replace(/^US /, '')].map(n => n.toLowerCase());
};
const mentioned = (t, members) => members.find(m => m !== 'gravit' && names(m).some(n => n && t.includes('@' + n)));
// the per-order cap the conversation really has (Details shows the same)
const capOf = ctx => ctx.limit?.perOrder ?? 25;

export function replyTo(text, ctx = {}) {
  const t = (text ?? '').toLowerCase();
  const installed = ctx.installed ?? [];
  const now = ctx.now ?? Date.now();
  const conv = ctx.conv ?? null;
  // files with no task in the words: Gravit reads them first
  const files = ctx.files ?? [];
  if (files.length && !/\bbtc\b|bitcoin|\beth\b|ethereum|\bsol\b|solana|pelosi|politician|0x[0-9a-f]{4,}|address|scam|\blimit\b|\bcap\b/.test(t)) {
    return [ev(1000, G('text', `Got ${files.join(', ')}. Let me see what is inside.`)), ev(2600, G('text', 'Read it. Nothing to act on. If you want me to do something from it, say so.'))];
  }
  if (conv?.teach) {
    // a numbered upload (moat-2) answers like its first
    const say = TEACH_REPLIES[conv.teach] ?? TEACH_REPLIES[conv.teach.replace(/-\d+$/, '')] ?? (() => 'Noted. Anything new, I say it here.');
    return [ev(1200, message(conv.teach, 'text', say((text ?? '').trim())))];
  }
  if (conv?.kind === 'group') {
    const bot = mentioned(t, conv.members ?? []);
    if (bot) return [ev(1200, message(bot, 'text', BOT_LINES[bot] ?? 'Looking. I will say here when I have a view.'))];
    if (/pelosi|politician/.test(t) && (conv.members ?? []).includes('politician')) {
      const title = 'Your call: follow NVDA $25';
      return [
        ev(1200, message('politician', 'text', 'Disclosure: Pelosi bought NVDA $1–5M on 10/7. By my rule that is a $25 follow.')),
        ev(2800, G('card', title, { title, venue: 'Stand-in Broker', type: 'market', about: '$25', cardId: '{card}', by: now + 20 * MIN })),
      ];
    }
  }
  // whole words only: "something" and "method" are not ETH
  if (/\bbtc\b|bitcoin|\beth\b|ethereum|\bsol\b|solana/.test(t)) {
    const coin = coinIn(t);
    const title = `Your call: buy ${COINS[coin].qty} ${coin}`;
    return [
      ev(1200, G('text', 'Got it. Checked Stand-in Exchange and the DEX in Stand-in Wallet; the exchange is cheaper. Starting with $5.')),
      // {card} {ord} {ledger} are numbered by the store's counters when the message lands (reducers/messages.js append)
      ev(2800, G('card', title, { title, coin, venue: 'Stand-in Exchange', type: 'market', about: 'about $5.00', cardId: '{card}', by: now + 26 * MIN })),
    ];
  }
  if (/pelosi|politician/.test(t)) {
    if (!installed.includes('politician')) return [ev(1200, G('install', 'To follow trades I need the US politician bot. It is in Discover.', { plugin: 'politician' }))];
    return [
      ev(1200, G('text', 'OK. The US politician bot is on it. I follow each disclosure as it lands; inside your limit I place it myself.')),
      ev(3200, message('politician', 'proposal', 'Disclosure: Pelosi bought NVDA. Bought $20 the same way, inside the limit, filled directly.', { status: 'filled', ord: '{ord}', venue: 'Stand-in Broker' })),
    ];
  }
  if (/0x[0-9a-f]{4,}|address|scam/.test(t)) {
    return [
      ev(1000, G('text', 'Checked.')),
      ev(1900, message('fraud', 'signal', '0x9f3a…c21e · on 3 scam lists · contract can pause withdrawals', { source: 'Address fraud check' })),
      ev(2800, G('alert', 'The address is on a scam list. Nothing was sent.')),
    ];
  }
  if (/\blimit\b|\bcap\b/.test(t)) { const cap = capOf(ctx); return [ev(1000, G('limit', `$${cap} an order is not enough. Raise it to $${cap * 2}?`, { from: cap, to: cap * 2 }))]; }
  return [ev(1000, G('text', 'Got it. Let me look.')), ev(2800, G('text', 'Looked. Nothing to act on. I will say if that changes.'))];
}

export function followUp(msg, answer, ctx = {}) {
  if (!msg || msg.answer) return [];
  if (msg.kind === 'card') {
    const coin = COINS[msg.data?.coin] ? msg.data.coin : 'BTC';
    if (answer !== 'approved') return [ev(1200, G('text', 'OK, not buying. I will ask again if things change.'))];
    const cap = capOf(ctx);
    // the next add is $30: ask to raise the cap only when the real cap is below it
    const ask = cap < 30 ? [ev(3400, G('limit', `I want to add $30, but your limit is $${cap} an order. Raise it to $${cap * 2}?`, { from: cap, to: cap * 2 }))] : [];
    return [ev(1500, G('receipt', `${COINS[coin].qty} ${coin} @ ${COINS[coin].price} · {ord} · ledger {ledger}`, { status: 'filled', amount: 5 })), ...ask];
  }
  if (msg.kind === 'limit') {
    if (answer !== 'granted') return [ev(1200, G('text', `Then it stays at $${msg.data.from}.`))];
    // no ask when it is installed, or when an earlier ask for it is still waiting in this conversation
    const ask = [...(ctx.installed ?? []), ...(ctx.pending ?? [])].includes('news') ? [] : [ev(2800, G('install', 'There is a News sentiment plugin in Discover. With it I can read sentiment before adding.', { plugin: 'news' }))];
    return [ev(1200, G('text', `Raised to $${msg.data.to}.`)), ...ask];
  }
  if (msg.kind === 'install') return answer === 'no' ? [ev(1000, G('text', 'OK, not installing.'))] : [];
  return [];
}

export const director = {
  brief: now => G('brief', 'Morning brief', { date: fmtDate(now), time: '7:30', lines: [
    'Overnight: Nasdaq +0.8%, {{BTC}} 63.1k (+1.4%)',
    'Today: CPI at 8:30 · first day after {{NVDA}} earnings',
    'Your holdings: {{BTC}} $3,740 · {{AAPL}} $2,510; no limit expiring',
    'My advice: nothing moves before CPI.',
  ] }),
  ta: () => G('ta', 'NVDA technicals', { ticker: 'NVDA', tf: '4h', support: 178, resistance: 192, candles: CANDLES, lines: ['Top of the range, volume rising. Support 178, resistance 192.', 'Verdict: to chase, wait for a pullback to 182; do not buy at the top.'] }),
  breaking: now => ({ id: 'b-' + now, headline: 'SEC sues Stand-in Exchange (stand-in news)', body: 'You hold {{BTC}} $3,740 there. Gravit has paused orders at this venue and waits for your word.', at: now }),
  // a call Gravit places: its topic, how long it needs, and what it says once you pick up
  call: () => ({ from: 'gravit', about: 'About BTC', length: '30 seconds', said: 'Hold until CPI is out; raise the order cap to $50 after.' }),
  // kind 7: a monitor posts a read-only signal; Gravit answers it in plain talk
  monitor: () => [
    ev(300, message('telegram', 'signal', 'SOL is about to take off, get in', { source: 'Telegram monitor · group “Alpha” · @kol_x' })),
    ev(1500, G('text', 'Seen. Not chasing.')),
  ],
  bot: () => message('buffett', 'text', 'One more thing: KO at this price I would buy.'),
  // kind 8, the door's refusal, and kind 10, the close (spec §6)
  refusal: () => G('refusal', 'Tried to place $30; the venue refused: above this limit’s $25 an order.', { code: 'E_MANDATE_PER_ORDER_CAP' }),
  done: now => G('done', `Done: bought 0.00008 BTC, spent $5, closed ${fmtDate(now)}.`, { foot: 'Ledger reconciled · $95 of the limit left' }),
};

// the plugins the scripted client uploads through shop.publish, in turn: one private, one public
const UPLOADS = [
  { id: 'moat', name: 'Moat score', kind: 'Data', blurb: 'Moat scores, ask by ticker', icon: null, tools: ['moat.score', 'moat.compare'], writes: ['message'], needs: 'none', visibility: 'private' },
  { id: 'cpi', name: 'CPI quick read', kind: 'Data', blurb: 'The moment CPI prints, three lines on what it means for your holdings', icon: 'bell', tools: ['cpi.latest', 'cpi.impact'], writes: ['message'], needs: 'none', visibility: 'public' },
];

// the next manifest not uploaded yet; after both, the same again with a number
export function nextUpload(uploaded = []) {
  const have = new Set(uploaded.map(p => p.id));
  for (let n = 1; ; n++) {
    for (const m of UPLOADS) {
      const id = n === 1 ? m.id : `${m.id}-${n}`;
      if (!have.has(id)) return { ...m, id, name: n === 1 ? m.name : `${m.name} ${n}`, tools: [...m.tools], writes: [...m.writes] };
    }
  }
}
