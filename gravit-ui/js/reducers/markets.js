// gravit-ui/js/reducers/markets.js — Markets' view (tab, sort, search, chart interval, the watchlist) and Trade's ticket:
// prepare, Sign and place, the stand-in venue's answer, and cancelling an order
import { nextId } from '../ids.js';
import { TABS, SORTS, KINDS, INTERVALS, instrument, listed, kindOf } from '../data/markets.js';
import { prepare, fillPrice, applyFill, legsOf, buyingPower, feeOf, saidOf } from '../trade.js';
import { px, cents, dollars, round2 } from '../market-fmt.js';
import { reducers as messages } from './messages.js';

const mk = (s, patch) => ({ ...s, markets: { ...s.markets, ...patch } });
const tr = (s, patch) => ({ ...s, trade: { ...s.trade, ...patch } });
const tk = (s, patch) => tr(s, { ticket: { ...s.trade.ticket, ...patch } });
// the ticket fields a person types or picks; null = free text
const FIELDS = { amount: null, unit: ['usd', 'qty'], orderType: ['market', 'limit'], limit: null };
// a change to the order prepares it again: a new ten minutes, and the last word goes
const changed = (s, patch, now) => tk(s, { ...patch, preparedAt: now, said: null });

export const reducers = {
  // a tab starts from Most traded, as Linqi's does
  setMarketsTab: (s, tab) => ([...TABS.map(t => t[0]), 'watching', ''].includes(tab) && tab !== s.markets.tab ? mk(s, { tab, sort: 'volume' }) : s),
  setMarketsSort(s, v) {
    const hit = SORTS.find(([id, label]) => id === v || label === v);
    return hit && hit[0] !== s.markets.sort ? mk(s, { sort: hit[0] }) : s;
  },
  // a search leaves Watching for All results; clearing it comes back to All
  setMarketsQuery(s, q) {
    const v = String(q ?? '');
    if (v === s.markets.q) return s;
    let { tab } = s.markets;
    if (v && !s.markets.q && tab === 'watching') tab = '';
    if (!v && tab === '') tab = 'all';
    return mk(s, { q: v, tab });
  },
  setMarketsInterval: (s, iv) => (iv in INTERVALS && iv !== s.markets.interval ? mk(s, { interval: iv }) : s),
  toggleWatch(s, id) {
    const inst = instrument(id);
    if (!inst || !listed(inst)) return s;
    const w = s.markets.watch;
    return mk(s, { watch: w.includes(inst.id) ? w.filter(x => x !== inst.id) : [...w, inst.id] });
  },

  setTradeKind: (s, kind) => (KINDS.some(k => k.id === kind) && kind !== s.trade.kind ? tr(s, { kind, q: '' }) : s),
  setTradeQuery(s, q) {
    const v = String(q ?? '');
    return v === s.trade.q ? s : tr(s, { q: v });
  },
  // the ticket on a market: the venue asked for if the account trades there, else where it is held (a sell), else the best one
  openTicket(s, { id, side = 'buy', outcome = 0, venue = null, now }) {
    const inst = instrument(id);
    if (!inst || !kindOf(inst)) return s;
    const ev = inst.kind === 'event';
    const o = ev && outcome === 1 ? 1 : 0;
    const able = legsOf(inst, s.account, o).filter(l => l.state === 'able');
    const label = ev ? inst.outcomes[o].label : null;
    const heldAt = side === 'sell' ? s.account.holdings.find(h => h.name === inst.base && (!ev || h.outcome === label) && able.some(l => l.venue === h.venue))?.venue : null;
    const kind = kindOf(inst);
    return tr(s, { kind, ticket: {
      id: inst.id, kind, venue: able.find(l => l.venue === venue)?.venue ?? heldAt ?? able[0]?.venue ?? null, side: side === 'sell' ? 'sell' : 'buy', outcome: o,
      amount: '', unit: 'usd', orderType: 'market', limit: '', preparedAt: now, placing: null, said: null, signs: false,
    } });
  },
  closeTicket: s => (s.trade.ticket ? tr(s, { ticket: null }) : s),
  setTicket(s, { field, value, now }) {
    const t = s.trade.ticket;
    if (!t?.id || !(field in FIELDS)) return s;
    const v = String(value ?? '').slice(0, 20);
    if ((FIELDS[field] && !FIELDS[field].includes(v)) || t[field] === v) return s;
    return changed(s, { [field]: v }, now);
  },
  ticketSide(s, { side, now }) {
    const t = s.trade.ticket;
    return t?.id && (side === 'buy' || side === 'sell') && side !== t.side ? changed(s, { side }, now) : s;
  },
  ticketOutcome(s, { outcome, now }) {
    const t = s.trade.ticket;
    return t?.id && instrument(t.id).kind === 'event' && (outcome === 0 || outcome === 1) && outcome !== t.outcome ? changed(s, { outcome }, now) : s;
  },
  ticketVenue(s, { venue, now }) {
    const t = s.trade.ticket;
    if (!t?.id || t.venue === venue || !legsOf(instrument(t.id), s.account, t.outcome).some(l => l.state === 'able' && l.venue === venue)) return s;
    return changed(s, { venue }, now);
  },
  toggleSigns: s => (s.trade.ticket?.id ? tk(s, { signs: !s.trade.ticket.signs }) : s),
  // the ten minutes ran out: the same order, prepared again
  requote: (s, { now }) => (s.trade.ticket?.id ? tk(s, { preparedAt: now }) : s),

  // Sign and place: the owner's signature on what the quote shows; the venue answers a moment later (settleOrder)
  placeOrder(s, { now }) {
    const t = s.trade.ticket;
    if (!t?.id || t.placing) return s;
    const p = prepare(s, now);
    if (p.state !== 'ready') return s;
    if (now >= p.deadline) return tk(s, { said: { ok: false, text: 'this order was good for ten minutes after it was prepared: prepare it again' }, preparedAt: now });
    const { id, counters } = nextId(s.counters, 'ord');
    const order = {
      id, at: now, inst: p.inst.id, venue: p.leg.venue, symbol: p.symbol, side: t.side, type: t.orderType, qty: p.qty,
      limit: t.orderType === 'limit' ? p.px : null, outcome: p.label, status: 'pending', price: null, usd: null, fee: 0, by: 'you', how: null, conv: null, note: `${p.leg.venue} took it`,
    };
    return tk({ ...s, counters, account: { ...s.account, orders: [order, ...s.account.orders] } }, { placing: id, said: null });
  },
  settleOrder(s, { id, now }) {
    const o = s.account.orders.find(x => x.id === id);
    if (!o || o.status !== 'pending') return s;
    const inst = instrument(o.inst);
    const price = fillPrice(o, inst);
    let account = s.account;
    let done;
    if (price == null) done = { ...o, status: 'open', note: `on ${o.venue}’s book at ${inst.kind === 'event' ? cents(o.limit) : px(o.limit)}` };
    else {
      const bp = buyingPower(account, o.venue);
      const cost = round2(o.qty * price);
      if (o.side === 'buy' && bp < cost + feeOf(o.venue, cost)) done = { ...o, status: 'rejected', note: `${o.venue} has ${dollars(bp)} to trade with` };
      else ({ account, order: done } = applyFill(account, o, price, now));
    }
    const next = { ...s, account: { ...account, orders: account.orders.map(x => (x.id === id ? done : x)) } };
    if (s.trade.ticket?.placing !== id) return next;
    return tk(next, { placing: null, said: { ok: done.status !== 'rejected', text: saidOf(done) }, amount: '', limit: '', preparedAt: now });
  },
  // cancel an order still on its way or on a book; Gravit's own leaves a line in the conversation it came from
  cancelOrder(s, { id, now }) {
    const o = s.account.orders.find(x => x.id === id);
    if (!o || (o.status !== 'open' && o.status !== 'pending')) return s;
    let next = { ...s, account: { ...s.account, orders: s.account.orders.map(x => (x.id === id ? { ...x, status: 'canceled', note: 'canceled by you' } : x)) } };
    if (next.trade.ticket?.placing === id) next = tk(next, { placing: null });
    if (o.by === 'gravit' && o.conv) {
      const text = `You canceled ${o.id} (${instrument(o.inst).base}${o.limit != null ? ` limit ${px(o.limit)}` : ''}) in Trade.`;
      next = messages.append(next, { convId: o.conv, msg: { from: 'system', kind: 'text', text, data: {} }, at: now });
    }
    return next;
  },
};
