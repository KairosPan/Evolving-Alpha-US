// gravit-ui/js/trade.js — the owner's hand orders, after Linqi's live-orders rules (buyer-agent-demo ui/trade.js):
// which venues can take a market, what an order would be (prepare), how a stand-in venue fills it, and what the fill changes
import { CAP_USD, QUOTE_MS, FEES, instrument } from './data/markets.js';
import { VENUES } from './data/seed.js';
import { usd, dollars, px, cents, qtyFmt, floorTo, round2 } from './market-fmt.js';

export const connectedNames = account => account.venues.filter(v => v.state === 'Healthy').map(v => v.name);
const tidy = n => Number(n.toFixed(8));

// a market's legs: venues the account trades at first, cheapest ask first and marked best; public listings after
export function legsOf(inst, account, outcome = 0) {
  const on = connectedNames(account);
  const o = inst.kind === 'event' ? inst.outcomes[outcome] : null;
  const legs = inst.at.map(l => ({ ...l, ...(o ? { bid: o.bid, ask: o.ask } : {}), state: on.includes(l.venue) ? 'able' : l.public ? 'public' : null })).filter(l => l.state);
  const able = legs.filter(l => l.state === 'able').sort((a, b) => a.ask - b.ask);
  if (able[0]) able[0] = { ...able[0], best: true };
  return [...able, ...legs.filter(l => l.state === 'public')];
}

// the one thing a market row offers: Trade where the account trades it, else Connect to trade at its public venue
export function routeOf(inst, account) {
  const legs = legsOf(inst, account);
  if (legs.some(l => l.state === 'able')) return { act: 'trade' };
  const pub = legs.find(l => l.state === 'public');
  return pub ? { act: 'connect', venue: pub.venue } : { act: null };
}

// dollars to trade with at a venue: the wallet spends its USDC, the others their cash
export const buyingPower = (account, venue) => (venue === 'Stand-in Wallet'
  ? account.holdings.find(h => h.name === 'USDC' && h.venue === venue)?.qty ?? 0
  : account.cash?.[venue] ?? 0);
export const heldQty = (account, inst, venue, label) => account.holdings.find(h => h.name === inst.base && h.venue === venue && (inst.kind !== 'event' || h.outcome === label))?.qty ?? 0;
export const feeOf = (venue, amount) => (FEES[venue] ? Math.max(0.01, round2(amount * FEES[venue])) : 0);

// what the ticket would place, or why it cannot yet: rest · pick · incomplete · refused · ready
export function prepare(state, now) {
  const t = state.trade.ticket;
  if (!t?.id) return { state: 'rest' };
  const inst = instrument(t.id);
  const ev = inst.kind === 'event';
  const out = ev ? inst.outcomes[t.outcome] : null;
  const legs = legsOf(inst, state.account, t.outcome);
  const leg = legs.find(l => l.state === 'able' && l.venue === t.venue);
  if (!leg) return { state: 'pick', inst, legs };
  const shown = t.side === 'buy' ? leg.ask : leg.bid;
  const base = { inst, legs, leg, shown, label: out?.label ?? null };
  const no = text => ({ ...base, state: 'refused', text });
  const limit = t.orderType === 'limit' ? Number(t.limit) : null;
  if (ev && t.orderType === 'limit' && t.limit.trim() !== '' && !(limit >= 0 && limit <= 100)) return { ...base, state: 'incomplete', text: 'A price in cents is between 0 and 100: a contract pays $1.00 at most.' };
  const amount = Number(t.amount);
  if (!(amount > 0)) return { ...base, state: 'incomplete', text: 'Type an amount.' };
  if (t.orderType === 'limit' && !(limit > 0)) return { ...base, state: 'incomplete', text: 'Type the limit price.' };
  const price = t.orderType === 'limit' ? (ev ? limit / 100 : limit) : shown;
  const qty = floorTo(t.unit === 'qty' ? amount : amount / price, inst.qtyStep);
  if (!(qty > 0) || qty < inst.minQty) {
    return no(ev ? `${leg.venue}: the smallest order in ${leg.symbol} is 1 contract (${cents(price)})` : `${leg.venue}: the smallest order in ${leg.symbol} is ${qtyFmt(inst.minQty)} ${inst.base} (${usd(inst.minQty * price)} at ${px(price)})`);
  }
  if (inst.minUsd && qty * price < inst.minUsd) return no(`${leg.venue}: the smallest order in ${leg.symbol} is worth ${dollars(inst.minUsd)}`);
  const notional = round2(qty * price);
  // a market buy may pay up to 2% over the ask before the venue stops it
  const worst = ev ? Math.min(1, leg.ask * 1.02) : leg.ask * 1.02;
  const maxUsd = t.orderType === 'market' && t.side === 'buy' ? round2(qty * worst) : notional;
  if (maxUsd > CAP_USD) return no(`${dollars(maxUsd)} is more than the most one order may be (${dollars(CAP_USD)}).`);
  if (t.side === 'buy') {
    const bp = buyingPower(state.account, leg.venue);
    if (bp < maxUsd + feeOf(leg.venue, maxUsd)) return no(`${leg.venue} has ${dollars(bp)} to trade with.`);
  } else {
    const have = heldQty(state.account, inst, leg.venue, out?.label);
    if (qty > have + 1e-9) return no(`Sells only what you hold · ${qtyFmt(have)} held.`);
  }
  const deadline = t.preparedAt + QUOTE_MS;
  const symbol = ev ? `${inst.id}:${out.label.toUpperCase()}` : leg.symbol;
  const fields = [['venue', leg.venue], ['symbol', symbol], ['side', t.side], ['orderType', t.orderType], ['qty', String(qty)],
    ['limitPrice', limit == null ? '' : String(ev ? limit / 100 : limit)], ['maxNotional', String(maxUsd)], ['deadline', String(deadline)], ['nonce', String(t.preparedAt)]];
  return { ...base, state: 'ready', qty, px: price, notional, maxUsd, fee: feeOf(leg.venue, notional), deadline, nonce: t.preparedAt, symbol, fields, limit };
}

// what a stand-in venue fills at: market at the touch; a limit only when it crosses (prices hold still, so a resting one stays)
export function fillPrice(order, inst) {
  const o = inst.kind === 'event' ? inst.outcomes.find(x => x.label === order.outcome) : null;
  const leg = inst.at.find(l => l.venue === order.venue);
  const bid = o ? o.bid : leg.bid, ask = o ? o.ask : leg.ask;
  if (order.type === 'market') return order.side === 'buy' ? ask : bid;
  if (order.side === 'buy') return order.limit >= ask ? ask : null;
  return order.limit <= bid ? bid : null;
}

// a holding's price now: the instrument's mid, the outcome's price for a prediction, a dollar for a stablecoin
export function markOf(h) {
  const inst = instrument(h.name);
  if (!inst) return null;
  if (inst.kind === 'event') return inst.outcomes.find(o => o.label === h.outcome)?.price ?? inst.price;
  return inst.kind === 'stable' ? 1 : inst.price;
}
const CLASS = { coin: 'crypto', stock: 'equity', stable: 'stable', rwa: 'rwa', event: 'event' };

// values from quantities, net worth (cash + holdings + Gravit's wallet) and the allocation bar, whole percents summing to 100
export function revalue(account) {
  const holdings = account.holdings.map(h => { const m = markOf(h); return h.qty != null && m != null ? { ...h, value: round2(h.qty * m) } : h; });
  const of = token => holdings.filter(h => CLASS[instrument(h.name)?.kind] === token).reduce((a, h) => a + h.value, 0);
  const cash = Object.values(account.cash ?? {}).reduce((a, b) => a + b, 0);
  const parts = [['Cash', 'cash', cash], ['Stablecoins', 'stable', of('stable') + account.wallet.usdc], ['Crypto', 'crypto', of('crypto')], ['Stocks', 'equity', of('equity')], ['RWA', 'rwa', of('rwa')], ['Predictions', 'event', of('event')]].filter(p => p[2] > 0);
  const total = parts.reduce((a, p) => a + p[2], 0);
  const raw = parts.map(p => (total ? (p[2] / total) * 100 : 0));
  const pct = raw.map(Math.floor);
  const left = total ? 100 - pct.reduce((a, b) => a + b, 0) : 0;
  raw.map((r, i) => [r - Math.floor(r), i]).sort((a, b) => b[0] - a[0] || a[1] - b[1]).slice(0, left).forEach(([, i]) => { pct[i]++; });
  return { ...account, holdings, netWorth: round2(total), alloc: parts.map((p, i) => ({ name: p[0], pct: pct[i], token: p[1] })) };
}

// a fill: the holding, the money at the venue, the statement line; then everything revalued
export function applyFill(account, order, price, now) {
  const inst = instrument(order.inst);
  const ev = inst.kind === 'event';
  const amount = round2(order.qty * price);
  const fee = feeOf(order.venue, amount);
  const buy = order.side === 'buy';
  const pay = round2(buy ? -(amount + fee) : amount - fee);
  const match = h => h.name === inst.base && h.venue === order.venue && (!ev || h.outcome === order.outcome);
  let holdings = account.holdings;
  const h = holdings.find(match);
  if (h) {
    const qty = tidy(h.qty + (buy ? order.qty : -order.qty));
    holdings = qty > 1e-9 ? holdings.map(x => (x === h ? { ...x, qty } : x)) : holdings.filter(x => x !== h);
  } else if (buy) {
    const key = ev ? `event:${inst.id}:${order.outcome}` : holdings.some(x => x.key === inst.key) ? `${inst.key}@${order.venue}` : inst.key;
    holdings = [...holdings, { key, name: inst.base, venue: order.venue, qty: order.qty, value: 0, chg: ev ? null : inst.chg, ...(ev ? { outcome: order.outcome } : {}) }];
  }
  let cash = account.cash ?? {};
  if (order.venue === 'Stand-in Wallet') holdings = holdings.map(x => (x.name === 'USDC' && x.venue === 'Stand-in Wallet' ? { ...x, qty: round2(x.qty + pay) } : x));
  else cash = { ...cash, [order.venue]: round2((cash[order.venue] ?? 0) + pay) };
  const at = ev ? cents(price) : px(price);
  const activity = [{ at: now, text: `Fill · ${qtyFmt(order.qty)} ${ev ? `${inst.id} ${order.outcome}` : inst.base} @ ${at} · ${order.id}`, amount: pay }, ...account.activity];
  return {
    account: revalue({ ...account, holdings, cash, activity }),
    order: { ...order, status: 'filled', price, usd: amount, fee, note: `filled at ${at}${fee ? ` · fee ${dollars(fee)}` : ''}` },
  };
}

// the ticket's last word on an order
export function saidOf(o) {
  if (o.status === 'filled') return `${o.side === 'buy' ? 'Bought' : 'Sold'}: ${o.id} · ${o.note}`;
  if (o.status === 'open') return `Placed: ${o.id} · ${o.note}`;
  return `Not filled: ${o.note}`;
}

// Hand to Gravit instead: the ticket in words for the composer, and the draft's limit chips where Gravit may trade
export function handOver(state, t) {
  const inst = t?.id ? instrument(t.id) : null;
  if (!inst) return { words: '', venue: null, perOrder: null, attach: true };
  const ev = inst.kind === 'event';
  const legs = legsOf(inst, state.account, t.outcome ?? 0).filter(l => l.state === 'able');
  const venue = legs.find(l => l.venue === t.venue)?.venue ?? legs[0]?.venue ?? null;
  const a = Number(t.amount);
  const dollarsTyped = a > 0 && (t.unit ?? 'usd') === 'usd' ? a : null;
  const qtyTyped = a > 0 && t.unit === 'qty' ? a : null;
  const what = ev ? `${inst.outcomes[t.outcome ?? 0].label} · ${inst.name}` : inst.base;
  const words = `${t.side === 'sell' ? '卖' : '买'}${dollarsTyped ? ` $${t.amount} 的` : qtyTyped ? ` ${t.amount}` : ''} ${what}${t.orderType === 'limit' && Number(t.limit) > 0 ? `，限价 ${t.limit}` : ''}`;
  return { words, venue, perOrder: dollarsTyped, attach: VENUES.includes(venue) };
}

// does a line of text name this market? (ETH, not ETH-3K)
export function mentions(text, base) {
  const b = base.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`(?<=^|[\\s·(（$])${b}(?=[\\s·),，。:：]|$)`).test(text ?? '');
}
